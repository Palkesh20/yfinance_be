"""Cache read, write, and expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from finance_poc.storage.cache import ResponseCache
from finance_poc.storage.db import create_db_engine, create_session_factory, init_db
from finance_poc.storage.models import CacheEntry


@pytest.mark.asyncio
async def test_cache_returns_a_fresh_payload_and_drops_an_expired_one() -> None:
    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        cache = ResponseCache(session)
        await cache.set_json(
            "quote:AAPL", {"source": "finnhub", "cached": False}, source="finnhub", ttl_seconds=60
        )
        stored = await cache.get_json("quote:AAPL")
        assert stored is not None
        assert stored["source"] == "finnhub"
        session.add(
            CacheEntry(
                cache_key="quote:OLD",
                payload='{"source": "yfinance"}',
                source="yfinance",
                expires_at=datetime.now(UTC) - timedelta(seconds=5),
            )
        )
        await session.commit()
        assert await cache.get_json("quote:OLD") is None
    await engine.dispose()
