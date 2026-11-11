"""yfinance adapter. Synchronous library calls run in a worker thread."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from functools import partial
from typing import Any

import anyio
import pandas as pd

from finance_poc.connectors.base import Connector
from finance_poc.core.config import Settings
from finance_poc.core.constants import Capability, Provider
from finance_poc.core.exceptions import DataNotFoundError, ProviderUnavailableError
from finance_poc.models.schemas import (
    CompanyProfile,
    NewsFeed,
    NewsItem,
    PriceBar,
    Quote,
    coerce_datetime,
    coerce_float,
)
from finance_poc.utils.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


def _read(obj: object, name: str) -> object:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _load_history(ticker: str, start: date, end: date, interval: str) -> pd.DataFrame:
    import yfinance as yf

    return yf.Ticker(ticker).history(
        start=start.isoformat(), end=end.isoformat(), interval=interval, auto_adjust=False
    )


def _load_quote(ticker: str) -> dict[str, object]:
    import yfinance as yf

    info = yf.Ticker(ticker).fast_info
    return {
        "price": _read(info, "last_price"),
        "previous_close": _read(info, "previous_close"),
        "currency": _read(info, "currency"),
    }


def _load_news(ticker: str) -> list[object]:
    import yfinance as yf

    raw = yf.Ticker(ticker).news
    if not isinstance(raw, list):
        raise DataNotFoundError(f"No news for {ticker}")
    return raw


def _load_profile(ticker: str) -> dict[str, Any]:
    import yfinance as yf

    info = yf.Ticker(ticker).info
    if not isinstance(info, dict):
        raise DataNotFoundError(f"No company profile for {ticker}")
    return info


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class YFinanceClient(Connector):
    """Primary source for prices, quotes, and company profiles."""

    name = Provider.YFINANCE.value
    capabilities = frozenset(
        {Capability.PRICES, Capability.QUOTE, Capability.NEWS, Capability.COMPANY_PROFILE}
    )

    def __init__(self, settings: Settings, limiter: AsyncRateLimiter | None = None) -> None:
        self._settings = settings
        self._limiter = limiter or AsyncRateLimiter(
            settings.rate_limit_yfinance_calls,
            settings.rate_limit_yfinance_period_seconds,
        )

    async def _call(self, func: Any, *args: Any) -> Any:
        if self._limiter is not None:
            await self._limiter.acquire()
        try:
            return await anyio.to_thread.run_sync(partial(func, *args))
        except DataNotFoundError:
            raise
        except Exception as exc:
            logger.warning("yfinance request failed error=%s", type(exc).__name__)
            raise ProviderUnavailableError("yfinance request failed") from exc

    async def get_prices(
        self, ticker: str, start: date, end: date, interval: str
    ) -> list[PriceBar]:
        frame = await self._call(_load_history, ticker, start, end, interval)
        return _bars_from_frame(ticker, frame)

    async def get_quote(self, ticker: str) -> Quote:
        payload = await self._call(_load_quote, ticker)
        price_raw = payload.get("price")
        if price_raw is None:
            raise DataNotFoundError(f"No quote for {ticker}")
        price = coerce_float(price_raw, field_name="price")
        previous_raw = payload.get("previous_close")
        previous = (
            coerce_float(previous_raw, field_name="previous_close")
            if previous_raw is not None
            else None
        )
        change = None if previous is None else price - previous
        change_percent = None
        if previous not in (None, 0) and change is not None:
            change_percent = (change / previous) * 100
        currency = payload.get("currency")
        return Quote(
            ticker=ticker,
            price=price,
            change=change,
            change_percent=change_percent,
            previous_close=previous,
            currency=str(currency) if currency else None,
            as_of=datetime.now(UTC),
            source=self.name,
        )

    async def get_news(self, ticker: str, limit: int) -> NewsFeed:
        rows = await self._call(_load_news, ticker)
        items = _news_items(ticker, rows)[:limit]
        if not items:
            raise DataNotFoundError(f"No news for {ticker}")
        return NewsFeed(items=items, source=self.name)

    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        info = await self._call(_load_profile, ticker)
        name = _optional_text(info.get("longName")) or _optional_text(info.get("shortName"))
        if name is None:
            raise DataNotFoundError(f"No company profile for {ticker}")
        return CompanyProfile(
            ticker=ticker,
            name=name,
            exchange=_optional_text(info.get("exchange")),
            sector=_optional_text(info.get("sector")),
            industry=_optional_text(info.get("industry")),
            description=_optional_text(info.get("longBusinessSummary")),
            website=_optional_text(info.get("website")),
            source=self.name,
        )

    async def health_check(self) -> bool:
        try:
            import yfinance  # noqa: F401
        except ImportError:
            return False
        return True


def _news_items(ticker: str, rows: list[object]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        content = row.get("content")
        payload = content if isinstance(content, dict) else row
        title = _optional_text(payload.get("title"))
        url = _news_url(payload)
        published = payload.get("pubDate") or payload.get("providerPublishTime")
        if title is None or url is None or published is None:
            continue
        summary = _plain_text(payload.get("summary") or payload.get("description"))
        provider = payload.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else None
        items.append(
            NewsItem(
                ticker=ticker,
                headline=title,
                summary=summary,
                url=url,
                published_at=coerce_datetime(published, field_name="published_at"),
                source=Provider.YFINANCE.value,
                publisher=_optional_text(publisher) or _optional_text(payload.get("publisher")),
            )
        )
    items.sort(key=lambda item: item.published_at, reverse=True)
    return items


def _news_url(payload: Mapping[str, Any]) -> str | None:
    for key in ("canonicalUrl", "clickThroughUrl"):
        value = payload.get(key)
        if isinstance(value, dict):
            url = _optional_text(value.get("url"))
            if url is not None:
                return url
    return _optional_text(payload.get("link"))


def _plain_text(value: object) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:400] or None


def _bars_from_frame(ticker: str, frame: pd.DataFrame) -> list[PriceBar]:
    if frame is None or frame.empty:
        raise DataNotFoundError(f"No prices for {ticker}")
    bars: list[PriceBar] = []
    for timestamp, row in frame.iterrows():
        close_raw = row.get("Close")
        if close_raw is None or pd.isna(close_raw):
            continue
        moment = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
        if not isinstance(moment, datetime):
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        volume_raw = row.get("Volume")
        volume = (
            None
            if volume_raw is None or pd.isna(volume_raw)
            else coerce_float(volume_raw, field_name="volume")
        )
        bars.append(
            PriceBar(
                ticker=ticker,
                timestamp=moment,
                open=coerce_float(row.get("Open"), field_name="open"),
                high=coerce_float(row.get("High"), field_name="high"),
                low=coerce_float(row.get("Low"), field_name="low"),
                close=coerce_float(close_raw, field_name="close"),
                volume=volume,
                source=Provider.YFINANCE.value,
            )
        )
    if not bars:
        raise DataNotFoundError(f"No prices for {ticker}")
    return bars
