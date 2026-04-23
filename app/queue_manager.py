#!/usr/bin/env python3
"""Global FIFO request queue with worker pool."""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.models import ChatgptImageResult, GeneratedImageItem
from app.service import is_account_routeable, is_token_invalid_error


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
        await self._queue.put(job)
        return job.request_id

    def get_status(self) -> dict[str, int]:
        """Return current queue length and processing count."""
        return {
            "queued": self._queue.qsize(),
            "processing": len(self._processing),
        }

    def get_result(self, request_id: str) -> dict[str, Any] | None:
        """Return result if available, else None."""
        return self._results.get(request_id)

    def get_position(self, request_id: str) -> int:
        """Estimate queue position (0 = currently processing or next)."""
        if request_id in self._processing:
            return 0
        # asyncio.Queue does not expose internal list, so we drain+re-queue
        # to count.  This is O(n) but fine for modest queue depths.
        pos = 0
        temp: list[GenerationJob] = []
        found = False
        while not self._queue.empty():
            try:
                job = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            temp.append(job)
            if not found:
                if job.request_id == request_id:
                    found = True
                else:
                    pos += 1
        for job in temp:
            self._queue.put_nowait(job)
        return pos if found else -1

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            self._processing.add(job.request_id)
            try:
                result = await self._execute_job(job)
                self._results[job.request_id] = {
                    "status": "done",
                    "data": result,
                    "finished_at": time.monotonic(),
                }
            except Exception as e:
                self._results[job.request_id] = {
                    "status": "error",
                    "detail": str(e),
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
            account = self.service.select_best_account()
            if account is None:
                raise RuntimeError("no available accounts")

            account = await self.service._refresh_account_if_needed(account)
            if not is_account_routeable(account):
                last_error = "account not routeable"
                continue

            # Acquire per-account lease (max concurrency enforced)
            lease = await self.service._acquire_account_lease(account)
            try:
                result = await self.service.upstream.generate_image(
                    account, job.prompt, job.model
                )
                resolved_model = result.resolved_model or resolved_model
                images.extend(result.data)
                self.service._record_account_success(account)
            except Exception as e:
                self.service._record_account_failure(account, str(e))
                last_error = str(e)
                if is_token_invalid_error(str(e)):
                    continue
            finally:
                lease.release()

        if not images:
            raise RuntimeError(last_error or "image generation failed")

        return {
            "created": int(time.time()),
            "data": [
                {"b64_json": img.b64_json, "revised_prompt": img.revised_prompt}
                for img in images
            ],
            "resolved_model": resolved_model or job.model,
        }
