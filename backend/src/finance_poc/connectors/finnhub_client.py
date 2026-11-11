"""Finnhub client for quotes, company news, and profiles."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from finance_poc.connectors.base import Connector
from finance_poc.core.config import Settings
from finance_poc.core.constants import FINNHUB_BASE_URL, Capability, Provider
from finance_poc.core.exceptions import (
    AuthenticationError,
    ConnectorError,
    DataNotFoundError,
    InvalidResponseError,
)
from finance_poc.models.schemas import (
    CompanyProfile,
    NewsFeed,
    NewsItem,
    Quote,
    coerce_datetime,
    coerce_float,
)
from finance_poc.utils.http import request_json
from finance_poc.utils.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


class FinnhubClient(Connector):
    """Live or delayed quotes and company news. Limited to 60 calls per minute."""

    name = Provider.FINNHUB.value
    capabilities = frozenset({Capability.QUOTE, Capability.NEWS, Capability.COMPANY_PROFILE})

    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        limiter: AsyncRateLimiter | None = None,
    ) -> None:
        self._http = http
        self._settings = settings
        self._limiter = limiter or AsyncRateLimiter(
            settings.rate_limit_finnhub_calls,
            settings.rate_limit_finnhub_period_seconds,
        )

    def _params(self, extra: dict[str, Any]) -> dict[str, Any]:
        key = self._settings.finnhub_api_key.get_secret_value().strip()
        if not key:
            raise AuthenticationError("Finnhub API key is not configured")
        return {**extra, "token": key}

    async def _get(self, path: str, extra: dict[str, Any]) -> Any:
        return await request_json(
            self._http,
            "GET",
            f"{FINNHUB_BASE_URL}{path}",
            settings=self._settings,
            provider=self.name,
            params=self._params(extra),
            limiter=self._limiter,
        )

    async def get_quote(self, ticker: str) -> Quote:
        payload = await self._get("/quote", {"symbol": ticker})
        if not isinstance(payload, dict):
            raise InvalidResponseError("Finnhub quote payload is invalid")
        price = coerce_float(payload.get("c"), field_name="price")
        timestamp = payload.get("t")
        if price == 0 and (timestamp in (None, 0)):
            raise DataNotFoundError(f"No quote for {ticker}")
        previous_raw = payload.get("pc")
        previous = (
            coerce_float(previous_raw, field_name="previous_close")
            if previous_raw not in (None, 0)
            else None
        )
        change_raw = payload.get("d")
        change = coerce_float(change_raw, field_name="change") if change_raw is not None else None
        percent_raw = payload.get("dp")
        percent = (
            coerce_float(percent_raw, field_name="change_percent")
            if percent_raw is not None
            else None
        )
        as_of = (
            datetime.now(UTC)
            if timestamp in (None, 0)
            else coerce_datetime(timestamp, field_name="as_of")
        )
        return Quote(
            ticker=ticker,
            price=price,
            change=change,
            change_percent=percent,
            previous_close=previous,
            as_of=as_of,
            source=self.name,
        )

    async def get_news(self, ticker: str, limit: int) -> NewsFeed:
        end = datetime.now(UTC).date()
        start = end - timedelta(days=30)
        payload = await self._get(
            "/company-news",
            {"symbol": ticker, "from": start.isoformat(), "to": end.isoformat()},
        )
        if not isinstance(payload, list):
            raise InvalidResponseError("Finnhub news payload is invalid")
        items: list[NewsItem] = []
        for row in payload:
            if not isinstance(row, dict) or not row.get("headline") or not row.get("url"):
                continue
            items.append(
                NewsItem(
                    ticker=ticker,
                    headline=str(row["headline"]),
                    summary=str(row["summary"]) if row.get("summary") else None,
                    url=str(row["url"]),
                    published_at=coerce_datetime(row.get("datetime"), field_name="published_at"),
                    source=self.name,
                    publisher=str(row["source"]) if row.get("source") else None,
                )
            )
        items.sort(key=lambda item: item.published_at, reverse=True)
        items = items[:limit]
        if not items:
            raise DataNotFoundError(f"No news for {ticker}")
        score, label = await self._sentiment(ticker)
        return NewsFeed(items=items, sentiment_score=score, sentiment_label=label, source=self.name)

    async def _sentiment(self, ticker: str) -> tuple[float | None, str | None]:
        try:
            payload = await self._get("/news-sentiment", {"symbol": ticker})
        except ConnectorError:
            logger.warning("finnhub sentiment unavailable ticker=%s", ticker)
            return None, None
        if not isinstance(payload, dict):
            return None, None
        raw_score = payload.get("companyNewsScore")
        score = (
            coerce_float(raw_score, field_name="sentiment_score") if raw_score is not None else None
        )
        sentiment = payload.get("sentiment")
        label = None
        if isinstance(sentiment, dict):
            bullish = sentiment.get("bullishPercent")
            bearish = sentiment.get("bearishPercent")
            if isinstance(bullish, (int, float)) and isinstance(bearish, (int, float)):
                label = "bullish" if bullish >= bearish else "bearish"
        return score, label

    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        payload = await self._get("/stock/profile2", {"symbol": ticker})
        if not isinstance(payload, dict) or not payload.get("name"):
            raise DataNotFoundError(f"No company profile for {ticker}")
        return CompanyProfile(
            ticker=ticker,
            name=str(payload["name"]),
            exchange=str(payload["exchange"]) if payload.get("exchange") else None,
            industry=str(payload["finnhubIndustry"]) if payload.get("finnhubIndustry") else None,
            website=str(payload["weburl"]) if payload.get("weburl") else None,
            source=self.name,
        )

    async def health_check(self) -> bool:
        return bool(self._settings.finnhub_api_key.get_secret_value().strip())
