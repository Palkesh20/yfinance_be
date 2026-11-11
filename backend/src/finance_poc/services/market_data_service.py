"""Cache-then-fetch orchestration for normalized market data."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import TypeVar

from pydantic import TypeAdapter

from finance_poc.connectors.router import ConnectorRouter
from finance_poc.core.config import Settings
from finance_poc.core.constants import (
    DEFAULT_PRICE_INTERVAL,
    DEFAULT_PRICE_LOOKBACK_DAYS,
    PRICE_INTERVALS,
)
from finance_poc.core.exceptions import ValidationError
from finance_poc.core.logging_config import ticker_var
from finance_poc.models.schemas import (
    CompanyProfile,
    DataResponse,
    Filing,
    FinancialStatementItem,
    NewsFeed,
    PriceBar,
    Quote,
)
from finance_poc.storage.cache import ResponseCache

T = TypeVar("T")

_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
_PRICES = TypeAdapter(DataResponse[list[PriceBar]])
_QUOTE = TypeAdapter(DataResponse[Quote])
_NEWS = TypeAdapter(DataResponse[NewsFeed])
_PROFILE = TypeAdapter(DataResponse[CompanyProfile])
_FILINGS = TypeAdapter(DataResponse[list[Filing]])
_FINANCIALS = TypeAdapter(DataResponse[list[FinancialStatementItem]])


def normalize_ticker(value: str) -> str:
    """Return an uppercase ticker or raise ValidationError."""
    ticker = value.strip().upper()
    if _TICKER.fullmatch(ticker) is None:
        raise ValidationError(
            "Ticker must be 1-10 characters using letters, digits, dots, or hyphens"
        )
    return ticker


class MarketDataService:
    """Read the cache, then ask the connector router on a miss."""

    def __init__(self, router: ConnectorRouter, cache: ResponseCache, settings: Settings) -> None:
        self._router = router
        self._cache = cache
        self._settings = settings

    async def get_prices(
        self,
        ticker: str,
        *,
        start: date | None = None,
        end: date | None = None,
        interval: str = DEFAULT_PRICE_INTERVAL,
    ) -> DataResponse[list[PriceBar]]:
        """Return historical bars for one ticker."""
        symbol = normalize_ticker(ticker)
        if interval not in PRICE_INTERVALS:
            raise ValidationError("Interval must be 1d, 1wk, or 1h")
        end_date = end or datetime.now(UTC).date()
        start_date = start or (end_date - timedelta(days=DEFAULT_PRICE_LOOKBACK_DAYS))
        if start_date > end_date:
            raise ValidationError("Start date must be on or before the end date")
        key = f"prices:{symbol}:{interval}:{start_date.isoformat()}:{end_date.isoformat()}"

        async def fetch() -> tuple[list[PriceBar], str]:
            bars = await self._router.get_prices(symbol, start_date, end_date, interval)
            return bars, bars[0].source

        return await self._cached(
            symbol, key, _PRICES, self._settings.cache_ttl_prices_seconds, fetch
        )

    async def get_quote(self, ticker: str) -> DataResponse[Quote]:
        """Return the latest quote."""
        symbol = normalize_ticker(ticker)

        async def fetch() -> tuple[Quote, str]:
            quote = await self._router.get_quote(symbol)
            return quote, quote.source

        return await self._cached(
            symbol, f"quote:{symbol}", _QUOTE, self._settings.cache_ttl_quotes_seconds, fetch
        )

    async def get_news(self, ticker: str, *, limit: int = 10) -> DataResponse[NewsFeed]:
        """Return recent headlines and an optional sentiment score."""
        symbol = normalize_ticker(ticker)
        bounded = _bounded_limit(limit, maximum=50)

        async def fetch() -> tuple[NewsFeed, str]:
            feed = await self._router.get_news(symbol, bounded)
            return feed, feed.source

        return await self._cached(
            symbol,
            f"news:{symbol}:{bounded}",
            _NEWS,
            self._settings.cache_ttl_news_seconds,
            fetch,
        )

    async def get_company_profile(self, ticker: str) -> DataResponse[CompanyProfile]:
        """Return the company profile."""
        symbol = normalize_ticker(ticker)

        async def fetch() -> tuple[CompanyProfile, str]:
            profile = await self._router.get_company_profile(symbol)
            return profile, profile.source

        return await self._cached(
            symbol,
            f"company:{symbol}",
            _PROFILE,
            self._settings.cache_ttl_company_seconds,
            fetch,
        )

    async def get_filings(self, ticker: str, *, limit: int = 10) -> DataResponse[list[Filing]]:
        """Return recent filings."""
        symbol = normalize_ticker(ticker)
        bounded = _bounded_limit(limit, maximum=40)

        async def fetch() -> tuple[list[Filing], str]:
            filings = await self._router.get_filings(symbol, bounded)
            return filings, filings[0].source

        return await self._cached(
            symbol,
            f"filings:{symbol}:{bounded}",
            _FILINGS,
            self._settings.cache_ttl_filings_seconds,
            fetch,
        )

    async def get_financials(self, ticker: str) -> DataResponse[list[FinancialStatementItem]]:
        """Return annual statement facts."""
        symbol = normalize_ticker(ticker)

        async def fetch() -> tuple[list[FinancialStatementItem], str]:
            items = await self._router.get_financials(symbol)
            return items, items[0].source

        return await self._cached(
            symbol,
            f"financials:{symbol}",
            _FINANCIALS,
            self._settings.cache_ttl_financials_seconds,
            fetch,
        )

    async def _cached(
        self,
        ticker: str,
        key: str,
        adapter: TypeAdapter[DataResponse[T]],
        ttl_seconds: int,
        fetch: Callable[[], Awaitable[tuple[T, str]]],
    ) -> DataResponse[T]:
        token = ticker_var.set(ticker)
        try:
            stored = await self._cache.get_json(key)
            if stored is not None:
                return adapter.validate_python({**stored, "cached": True})
            data, source = await fetch()
            body: DataResponse[T] = DataResponse(
                data=data,
                source=source,
                cached=False,
                as_of=datetime.now(UTC),
            )
            await self._cache.set_json(
                key, body.model_dump(mode="json"), source=source, ttl_seconds=ttl_seconds
            )
            return body
        finally:
            ticker_var.reset(token)


def _bounded_limit(value: int, *, maximum: int) -> int:
    if value < 1 or value > maximum:
        raise ValidationError(f"Limit must be between 1 and {maximum}")
    return value
