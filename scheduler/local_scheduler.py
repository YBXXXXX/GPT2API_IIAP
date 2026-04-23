#!/usr/bin/env python3
"""Local concurrency and pacing scheduler (migrated from Rust src/scheduler.rs)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Rejection:
    """Rejection metadata returned when a local scheduler cannot start a request."""

    reason: str
    wait_ms: int = 0


@dataclass
class _Entry:
    in_flight: int = 0
    next_start_at: float = 0.0


@dataclass
class Lease:
    """Lease that releases one in-flight slot when dropped."""

    scheduler: "LocalRequestScheduler"
    key: str

    def release(self) -> None:
        self.scheduler._release(self.key)


class LocalRequestScheduler:
    """In-memory scheduler enforcing per-key concurrency and pacing windows."""

    def __init__(self) -> None:
        self._states: dict[str, _Entry] = {}
        self._notify = asyncio.Condition()

    def try_acquire(
        self,
        key: str,
        max_concurrency: int | None,
        min_start_interval_ms: int | None,
    ) -> Lease | Rejection:
        now = time.monotonic()
        entry = self._states.setdefault(key, _Entry(in_flight=0, next_start_at=now))

        if max_concurrency is not None and max_concurrency > 0:
            if entry.in_flight >= max_concurrency:
                return Rejection(reason="local_concurrency_limit")

        if min_start_interval_ms is not None and min_start_interval_ms > 0:
            if now < entry.next_start_at:
                wait_ms = int((entry.next_start_at - now) * 1000)
                return Rejection(reason="local_start_interval", wait_ms=wait_ms)
            entry.next_start_at = now + (min_start_interval_ms / 1000.0)

        entry.in_flight += 1
        return Lease(scheduler=self, key=key)

    def _release(self, key: str) -> None:
        entry = self._states.get(key)
        if entry is not None:
            if entry.in_flight > 0:
                entry.in_flight -= 1
        # Notify waiters
        asyncio.get_event_loop().call_soon(self._notify_notify)

    def _notify_notify(self) -> None:
        # Fire-and-forget notification
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(self._do_notify())

    async def _do_notify(self) -> None:
        async with self._notify:
            self._notify.notify_all()

    async def wait_for_available(self, wait_ms: int) -> None:
        if wait_ms <= 0:
            async with self._notify:
                await self._notify.wait()
            return
        try:
            async with self._notify:
                await asyncio.wait_for(self._notify.wait(), timeout=wait_ms / 1000.0)
        except asyncio.TimeoutError:
            pass
