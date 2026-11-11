"""Sliding-window limiter."""

from __future__ import annotations

import time

import pytest

from finance_poc.utils.rate_limiter import AsyncRateLimiter


@pytest.mark.asyncio
async def test_second_call_waits_for_the_window() -> None:
    limiter = AsyncRateLimiter(1, 0.05)
    await limiter.acquire()
    started = time.monotonic()
    await limiter.acquire()
    assert time.monotonic() - started >= 0.04
