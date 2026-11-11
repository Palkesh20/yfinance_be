"""Async sliding-window rate limiter used by provider clients."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class AsyncRateLimiter:
    """Allow at most ``calls`` acquisitions in each rolling window."""

    def __init__(self, calls: int, period_seconds: float) -> None:
        if calls < 1 or period_seconds <= 0:
            raise ValueError("rate limit must be positive")
        self._calls = calls
        self._period = period_seconds
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until the next call is inside the configured window."""
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._stamps and now - self._stamps[0] >= self._period:
                    self._stamps.popleft()
                if len(self._stamps) < self._calls:
                    self._stamps.append(now)
                    return
                wait_seconds = self._period - (now - self._stamps[0])
            await asyncio.sleep(wait_seconds)
