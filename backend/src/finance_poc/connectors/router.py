"""Fallback across providers, with a per-provider circuit breaker."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import date
from typing import TypeVar

import httpx

from finance_poc.connectors.base import Connector
from finance_poc.connectors.edgar_client import EdgarClient
from finance_poc.connectors.finnhub_client import FinnhubClient
from finance_poc.connectors.twelvedata_client import TwelveDataClient
from finance_poc.connectors.yfinance_client import YFinanceClient
from finance_poc.core.config import Settings
from finance_poc.core.constants import (
    COMPANY_PROVIDERS,
    FILING_PROVIDERS,
    FINANCIAL_PROVIDERS,
    NEWS_PROVIDERS,
    PRICE_PROVIDERS,
    QUOTE_PROVIDERS,
    Capability,
    Provider,
)
from finance_poc.core.exceptions import AllProvidersFailedError, ConnectorError, DataNotFoundError
from finance_poc.core.logging_config import provider_var
from finance_poc.models.schemas import (
    CompanyProfile,
    Filing,
    FinancialStatementItem,
    NewsFeed,
    NewsItem,
    PriceBar,
    Quote,
)

logger = logging.getLogger(__name__)


def _merge_news(feeds: list[NewsFeed], limit: int) -> NewsFeed:
    seen: set[str] = set()
    items: list[NewsItem] = []
    for feed in feeds:
        for item in feed.items:
            key = item.url.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
    items.sort(key=lambda item: item.published_at, reverse=True)
    sentiment_score = next(
        (feed.sentiment_score for feed in feeds if feed.sentiment_score is not None), None
    )
    sentiment_label = next((feed.sentiment_label for feed in feeds if feed.sentiment_label), None)
    sources = ",".join(dict.fromkeys(feed.source for feed in feeds))
    return NewsFeed(
        items=items[:limit],
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        source=sources,
    )


T = TypeVar("T")


class CircuitBreaker:
    """Open after repeated failures and allow one trial after the recovery window."""

    def __init__(
        self, threshold: int, recovery_seconds: float, *, clock: Callable[[], float] | None = None
    ) -> None:
        self._threshold = threshold
        self._recovery = recovery_seconds
        self._clock = clock or time.monotonic
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}
        self._trial: set[str] = set()

    def allow(self, name: str) -> bool:
        """Return whether a call to this provider may proceed."""
        opened = self._opened_at.get(name)
        if opened is None:
            return True
        if self._clock() - opened < self._recovery or name in self._trial:
            return False
        self._trial.add(name)
        return True

    def record_success(self, name: str) -> None:
        """Close the breaker after a successful call."""
        self._failures.pop(name, None)
        self._opened_at.pop(name, None)
        self._trial.discard(name)

    def record_failure(self, name: str) -> None:
        """Count a failure and open the breaker at the threshold."""
        self._trial.discard(name)
        count = self._failures.get(name, 0) + 1
        self._failures[name] = count
        if count >= self._threshold:
            self._opened_at[name] = self._clock()


def build_router(settings: Settings, http: httpx.AsyncClient) -> ConnectorRouter:
    """Build the provider router from process settings and the shared HTTP client."""
    return ConnectorRouter(
        [
            YFinanceClient(settings),
            FinnhubClient(http, settings),
            EdgarClient(http, settings),
            TwelveDataClient(http, settings),
        ],
        settings,
    )


class ConnectorRouter:
    """Try providers in the configured order and skip open circuits."""

    def __init__(
        self, connectors: list[Connector], settings: Settings, breaker: CircuitBreaker | None = None
    ) -> None:
        self._connectors = {connector.name: connector for connector in connectors}
        self.connectors = tuple(connectors)
        self._breaker = breaker or CircuitBreaker(
            settings.circuit_breaker_failure_threshold,
            settings.circuit_breaker_recovery_seconds,
        )

    async def get_prices(
        self, ticker: str, start: date, end: date, interval: str
    ) -> list[PriceBar]:
        """Return prices from the first healthy price provider."""
        return await self._first(
            Capability.PRICES,
            PRICE_PROVIDERS,
            ticker,
            lambda connector: connector.get_prices(ticker, start, end, interval),
        )

    async def get_quote(self, ticker: str) -> Quote:
        """Return a quote from the first healthy quote provider."""
        return await self._first(
            Capability.QUOTE, QUOTE_PROVIDERS, ticker, lambda connector: connector.get_quote(ticker)
        )

    async def get_news(self, ticker: str, limit: int) -> NewsFeed:
        """Merge headlines from every healthy news provider, newest first."""
        feeds: list[NewsFeed] = []
        not_found: list[str] = []
        failures: list[str] = []
        for provider in NEWS_PROVIDERS:
            connector = self._connectors.get(provider.value)
            if connector is None or not connector.supports(Capability.NEWS):
                continue
            if not self._breaker.allow(connector.name):
                logger.warning("circuit open provider=%s ticker=%s", connector.name, ticker)
                failures.append(f"{connector.name}: circuit open")
                continue
            token = provider_var.set(connector.name)
            try:
                feeds.append(await connector.get_news(ticker, limit))
                self._breaker.record_success(connector.name)
            except DataNotFoundError:
                not_found.append(connector.name)
                self._breaker.record_success(connector.name)
            except ConnectorError as exc:
                self._breaker.record_failure(connector.name)
                logger.warning(
                    "news provider failed provider=%s ticker=%s error=%s",
                    connector.name,
                    ticker,
                    exc.code,
                )
                failures.append(f"{connector.name}: {exc.code}")
            finally:
                provider_var.reset(token)
        if feeds:
            return _merge_news(feeds, limit)
        if not_found and not failures:
            raise DataNotFoundError(f"No news for {ticker}")
        detail = ", ".join([*failures, *not_found]) or "no news provider is configured"
        raise AllProvidersFailedError(f"All providers failed for news ({detail})")

    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        """Return a profile from the first healthy profile provider."""
        return await self._first(
            Capability.COMPANY_PROFILE,
            COMPANY_PROVIDERS,
            ticker,
            lambda connector: connector.get_company_profile(ticker),
        )

    async def get_filings(self, ticker: str, limit: int) -> list[Filing]:
        """Return filings from the first healthy filings provider."""
        return await self._first(
            Capability.FILINGS,
            FILING_PROVIDERS,
            ticker,
            lambda connector: connector.get_filings(ticker, limit),
        )

    async def get_financials(self, ticker: str) -> list[FinancialStatementItem]:
        """Return statement items from the first healthy financials provider."""
        return await self._first(
            Capability.FINANCIALS,
            FINANCIAL_PROVIDERS,
            ticker,
            lambda connector: connector.get_financials(ticker),
        )

    async def _first(
        self,
        capability: Capability,
        order: tuple[Provider, ...],
        ticker: str,
        call: Callable[[Connector], Awaitable[T]],
    ) -> T:
        not_found: list[str] = []
        failures: list[str] = []
        for provider in order:
            connector = self._connectors.get(provider.value)
            if connector is None or not connector.supports(capability):
                continue
            if not self._breaker.allow(connector.name):
                logger.warning("circuit open provider=%s ticker=%s", connector.name, ticker)
                failures.append(f"{connector.name}: circuit open")
                continue
            token = provider_var.set(connector.name)
            try:
                result = await call(connector)
            except DataNotFoundError:
                not_found.append(connector.name)
                self._breaker.record_success(connector.name)
            except ConnectorError as exc:
                self._breaker.record_failure(connector.name)
                logger.warning(
                    "fallback triggered provider=%s ticker=%s error=%s",
                    connector.name,
                    ticker,
                    exc.code,
                )
                failures.append(f"{connector.name}: {exc.code}")
            else:
                self._breaker.record_success(connector.name)
                return result
            finally:
                provider_var.reset(token)
        if not_found and not failures:
            raise DataNotFoundError(f"No {capability.value} for {ticker}")
        raise AllProvidersFailedError(
            f"All providers failed for {capability.value}",
            failures=tuple(failures + not_found),
        )
