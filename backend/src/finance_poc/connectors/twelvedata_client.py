"""Twelve Data client used as the backup source for prices and quotes."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx

from finance_poc.connectors.base import Connector
from finance_poc.core.config import Settings
from finance_poc.core.constants import TWELVE_DATA_BASE_URL, Capability, Provider
from finance_poc.core.exceptions import AuthenticationError, DataNotFoundError, InvalidResponseError
from finance_poc.models.schemas import PriceBar, Quote, coerce_datetime, coerce_float
from finance_poc.utils.http import request_json
from finance_poc.utils.rate_limiter import AsyncRateLimiter

_INTERVALS = {"1d": "1day", "1wk": "1week", "1h": "1h"}


class TwelveDataClient(Connector):
    """Backup market-data provider."""

    name = Provider.TWELVEDATA.value
    capabilities = frozenset({Capability.PRICES, Capability.QUOTE})

    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        limiter: AsyncRateLimiter | None = None,
    ) -> None:
        self._http = http
        self._settings = settings
        self._limiter = limiter or AsyncRateLimiter(
            settings.rate_limit_twelvedata_calls,
            settings.rate_limit_twelvedata_period_seconds,
        )

    def _params(self, extra: dict[str, Any]) -> dict[str, Any]:
        key = self._settings.twelvedata_api_key.get_secret_value().strip()
        if not key:
            raise AuthenticationError("Twelve Data API key is not configured")
        return {**extra, "apikey": key}

    async def _get(self, path: str, extra: dict[str, Any]) -> Any:
        payload = await request_json(
            self._http,
            "GET",
            f"{TWELVE_DATA_BASE_URL}{path}",
            settings=self._settings,
            provider=self.name,
            params=self._params(extra),
            limiter=self._limiter,
        )
        if isinstance(payload, dict) and payload.get("status") == "error":
            message = str(payload.get("message", "Twelve Data request failed"))
            if "not found" in message.lower() or "invalid symbol" in message.lower():
                raise DataNotFoundError(message)
            raise InvalidResponseError("Twelve Data returned an error")
        return payload

    async def get_prices(
        self, ticker: str, start: date, end: date, interval: str
    ) -> list[PriceBar]:
        provider_interval = _INTERVALS.get(interval)
        if provider_interval is None:
            raise InvalidResponseError("Unsupported price interval")
        payload = await self._get(
            "/time_series",
            {
                "symbol": ticker,
                "interval": provider_interval,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "order": "ASC",
            },
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("values"), list):
            raise InvalidResponseError("Twelve Data price payload is invalid")
        bars: list[PriceBar] = []
        for row in payload["values"]:
            if not isinstance(row, dict):
                continue
            bars.append(
                PriceBar(
                    ticker=ticker,
                    timestamp=coerce_datetime(row.get("datetime"), field_name="timestamp"),
                    open=coerce_float(row.get("open"), field_name="open"),
                    high=coerce_float(row.get("high"), field_name="high"),
                    low=coerce_float(row.get("low"), field_name="low"),
                    close=coerce_float(row.get("close"), field_name="close"),
                    volume=(
                        coerce_float(row.get("volume"), field_name="volume")
                        if row.get("volume")
                        else None
                    ),
                    source=self.name,
                )
            )
        if not bars:
            raise DataNotFoundError(f"No prices for {ticker}")
        return bars

    async def get_quote(self, ticker: str) -> Quote:
        payload = await self._get("/quote", {"symbol": ticker})
        if not isinstance(payload, dict) or payload.get("close") is None:
            raise DataNotFoundError(f"No quote for {ticker}")
        price = coerce_float(payload.get("close"), field_name="price")
        previous_raw = payload.get("previous_close")
        previous = (
            coerce_float(previous_raw, field_name="previous_close")
            if previous_raw is not None
            else None
        )
        change = None if previous is None else price - previous
        percent_raw = payload.get("percent_change")
        percent = (
            coerce_float(percent_raw, field_name="change_percent")
            if percent_raw is not None
            else None
        )
        timestamp = payload.get("timestamp") or payload.get("datetime")
        as_of = coerce_datetime(timestamp, field_name="as_of") if timestamp else datetime.now(UTC)
        currency = payload.get("currency")
        return Quote(
            ticker=ticker,
            price=price,
            change=change,
            change_percent=percent,
            previous_close=previous,
            currency=str(currency) if currency else None,
            as_of=as_of,
            source=self.name,
        )

    async def health_check(self) -> bool:
        return bool(self._settings.twelvedata_api_key.get_secret_value().strip())
