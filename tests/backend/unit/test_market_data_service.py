"""Cache hit and cache miss in the market service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from finance_poc.core.config import load_settings
from finance_poc.core.exceptions import ValidationError
from finance_poc.models.schemas import Quote
from finance_poc.services.market_data_service import MarketDataService
from finance_poc.storage.cache import ResponseCache
from finance_poc.storage.db import create_db_engine, create_session_factory, init_db


class _Router:
    def __init__(self, quote: Quote) -> None:
        self.quote = quote
        self.calls = 0

    async def get_quote(self, ticker: str) -> Quote:
        self.calls += 1
        return self.quote


@pytest.mark.asyncio
async def test_second_quote_is_served_from_cache() -> None:
    quote = Quote(ticker="AAPL", price=10, as_of=datetime.now(UTC), source="finnhub")
    router = _Router(quote)
    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        service = MarketDataService(router, ResponseCache(session), load_settings())  # type: ignore[arg-type]
        first = await service.get_quote("aapl")
        second = await service.get_quote("AAPL")
    await engine.dispose()
    assert first.cached is False
    assert second.cached is True
    assert second.data.price == 10
    assert router.calls == 1


@pytest.mark.asyncio
async def test_invalid_ticker_is_rejected() -> None:
    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        quote = Quote(ticker="AAPL", price=1, as_of=datetime.now(UTC), source="x")
        service = MarketDataService(
            _Router(quote),  # type: ignore[arg-type]
            ResponseCache(session),
            load_settings(),
        )
        with pytest.raises(ValidationError):
            await service.get_quote("!!!")
    await engine.dispose()
