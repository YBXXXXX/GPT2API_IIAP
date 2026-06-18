#!/usr/bin/env python3
"""Global FIFO request queue with worker pool."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.models import ChatgptImageResult, GeneratedImageItem
from app.service import (
    is_prompt_rejection_error,
    is_account_routeable,
    is_token_invalid_error,
    should_backoff_account_error,
)


def classify_generation_error(message: str) -> str:
    if is_prompt_rejection_error(message):
        return "prompt_rejection"
    if is_token_invalid_error(message):
        return "token_invalid"
    if should_backoff_account_error(message):
        return "upstream_transient"
    return "generation_error"


@dataclass
class GenerationJob:
    """One image generation job submitted to the global queue."""

    prompt: str
    model: str
    n: int
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    submitted_at: float = field(default_factory=time.monotonic)


class QueueManager:
    """In-memory FIFO queue with async worker pool.

    NOTE: Currently asyncio-based for simplicity.  Swapping in Redis later
    only requires replacing the internal queue and result store.
    """

    def __init__(self, service: Any, workers: int = 4) -> None:
        self.service = service
        self._queue: asyncio.Queue[GenerationJob] = asyncio.Queue()
        self._results: dict[str, dict[str, Any]] = {}
        self._processing: set[str] = set()
        self._pending_request_ids: list[str] = []
        self._workers = workers
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start worker coroutines."""
        for _ in range(self._workers):
            self._tasks.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        """Cancel workers."""
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    async def submit(self, job: GenerationJob) -> str:
        """Enqueue a job and return its request id."""
        self._pending_request_ids.append(job.request_id)
        await self._queue.put(job)
        return job.request_id

    def get_status(self) -> dict[str, int]:
        """Return current queue length and processing count."""
        return {
            "queued": len(self._pending_request_ids),
            "processing": len(self._processing),
        }

    def get_result(self, request_id: str) -> dict[str, Any] | None:
        """Return result if available, else None."""
        return self._results.get(request_id)

    def is_processing(self, request_id: str) -> bool:
        return request_id in self._processing

    def get_position(self, request_id: str) -> int:
        """Return zero-based queue position for pending jobs only."""
        try:
            return self._pending_request_ids.index(request_id)
        except ValueError:
            return -1

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                self._pending_request_ids.remove(job.request_id)
            except ValueError:
                pass
            self._processing.add(job.request_id)
            self._results[job.request_id] = {
                "status": "processing",
                "phase": "starting",
                "message": "任务已开始，正在准备生成",
                "created": int(time.time()),
                "completed": 0,
                "requested_n": job.n,
                "data": {
                    "created": int(time.time()),
                    "data": [],
                    "resolved_model": job.model,
                },
            }
            try:
                result = await self._execute_job(job)
                self._results[job.request_id] = {
                    "status": "done",
                    "completed": len(result["data"]),
                    "requested_n": job.n,
                    "data": result,
                    "finished_at": time.monotonic(),
                }
            except Exception as e:
                detail = str(e)
                self._results[job.request_id] = {
                    "status": "error",
                    "error_type": classify_generation_error(detail),
                    "detail": detail,
                    "upstream_message": detail if is_prompt_rejection_error(detail) else None,
                    "finished_at": time.monotonic(),
                }
            finally:
                self._processing.discard(job.request_id)
                self._queue.task_done()

    async def _execute_job(self, job: GenerationJob) -> dict[str, Any]:
        """Run the generation through service layer."""
        images = []
        resolved_model = ""
        last_error: str | None = None

        for _ in range(job.n):
            try:
                result = await self._generate_one_image(job)
            except Exception as e:
                last_error = str(e)
                if is_prompt_rejection_error(last_error):
                    if not images:
                        raise RuntimeError(last_error)
                    break
                continue

            resolved_model = result.resolved_model or resolved_model
            images.extend(result.data)
            self._results[job.request_id] = {
                "status": "processing",
                "phase": "partial_ready" if len(images) < job.n else "finalizing",
                "message": (
                    f"已生成 {len(images)}/{job.n} 张，继续处理中"
                    if len(images) < job.n
                    else "正在整理最终结果"
                ),
                "created": int(time.time()),
                "completed": len(images),
                "requested_n": job.n,
                "data": {
                    "created": int(time.time()),
                    "data": [
                        {
                            "b64_json": img.b64_json,
                            "revised_prompt": img.revised_prompt,
                        }
                        for img in images
                    ],
                    "resolved_model": resolved_model or job.model,
                },
                "partial_error": last_error,
                "upstream_message": last_error if last_error and is_prompt_rejection_error(last_error) else None,
            }

        if not images:
            raise RuntimeError(last_error or "image generation failed")

        return {
            "created": int(time.time()),
            "data": [
                {"b64_json": img.b64_json, "revised_prompt": img.revised_prompt}
                for img in images
            ],
            "resolved_model": resolved_model or job.model,
            "partial_error": last_error if len(images) < job.n else None,
        }

    async def _generate_one_image(self, job: GenerationJob) -> Any:
        """Generate one image with account retry for transient/account-level failures."""
        max_attempts = max(1, len(self.service.storage.list_accounts()))
        last_error: str | None = None

        for _ in range(max_attempts):
            self._results[job.request_id] = {
                **self._results.get(job.request_id, {}),
                "status": "processing",
                "phase": "selecting_account",
                "message": "正在选择可用账号",
            }
            account, lease = await self.service.acquire_best_account_for_queue()
            try:
                account = await self.service._refresh_account_if_needed(account)
                if not is_account_routeable(account):
                    last_error = "account not routeable"
                    continue

                self._results[job.request_id] = {
                    **self._results.get(job.request_id, {}),
                    "status": "processing",
                    "phase": "generating",
                    "message": f"正在通过账号 {account.name} 生成图片",
                }
                result = await self.service.upstream.generate_image(
                    account, job.prompt, job.model
                )
                self.service._record_account_success(account)
                return result
            except Exception as e:
                error_message = str(e)
                self.service._record_account_failure(account, error_message)
                last_error = error_message
                if is_token_invalid_error(error_message) or should_backoff_account_error(error_message):
                    continue
                raise RuntimeError(error_message)
            finally:
                lease.release()

        raise RuntimeError(last_error or "image generation failed")
