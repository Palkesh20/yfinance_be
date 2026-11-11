"""Fallback order and the circuit breaker."""

from __future__ import annotations

from datetime import date

import pytest

from finance_poc.connectors.base import Connector
from finance_poc.connectors.router import CircuitBreaker, ConnectorRouter
from finance_poc.core.config import load_settings
from finance_poc.core.constants import Capability
from finance_poc.core.exceptions import (
    AllProvidersFailedError,
    DataNotFoundError,
    ProviderUnavailableError,
)
from finance_poc.models.schemas import PriceBar


class _Prices(Connector):
    capabilities = frozenset({Capability.PRICES})

    def __init__(
        self, name: str, bars: list[PriceBar] | None = None, error: Exception | None = None
    ) -> None:
        self.name = name
        self._bars = bars or []
        self._error = error
        self.calls = 0

    async def get_prices(
        self, ticker: str, start: date, end: date, interval: str
    ) -> list[PriceBar]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._bars


def _bar(source: str) -> PriceBar:
    return PriceBar(
        ticker="AAPL",
        timestamp="2024-01-02T00:00:00Z",  # type: ignore[arg-type]
        open=1,
        high=2,
        low=0.5,
        close=1.5,
        volume=10,
        source=source,
    )


@pytest.mark.asyncio
async def test_router_falls_back_when_the_primary_is_unavailable() -> None:
    primary = _Prices("yfinance", error=ProviderUnavailableError("down"))
    backup = _Prices("twelvedata", bars=[_bar("twelvedata")])
    router = ConnectorRouter([primary, backup], load_settings())
    bars = await router.get_prices("AAPL", date(2024, 1, 1), date(2024, 1, 3), "1d")
    assert bars[0].source == "twelvedata"
    assert primary.calls == 1
    assert backup.calls == 1


@pytest.mark.asyncio
async def test_router_returns_not_found_when_every_provider_has_no_data() -> None:
    primary = _Prices("yfinance", error=DataNotFoundError("missing"))
    backup = _Prices("twelvedata", error=DataNotFoundError("missing"))
    router = ConnectorRouter([primary, backup], load_settings())
    with pytest.raises(DataNotFoundError):
        await router.get_prices("AAPL", date(2024, 1, 1), date(2024, 1, 3), "1d")


def test_breaker_opens_and_allows_one_trial_after_recovery() -> None:
    now = {"value": 100.0}
    breaker = CircuitBreaker(2, 30, clock=lambda: now["value"])
    breaker.record_failure("finnhub")
    assert breaker.allow("finnhub") is True
    breaker.record_failure("finnhub")
    assert breaker.allow("finnhub") is False
    now["value"] = 131.0
    assert breaker.allow("finnhub") is True
    assert breaker.allow("finnhub") is False
    breaker.record_success("finnhub")
    assert breaker.allow("finnhub") is True


@pytest.mark.asyncio
async def test_open_circuit_skips_to_the_next_provider() -> None:
    primary = _Prices("yfinance", error=ProviderUnavailableError("down"))
    backup = _Prices("twelvedata", bars=[_bar("twelvedata")])
    breaker = CircuitBreaker(1, 60)
    router = ConnectorRouter([primary, backup], load_settings(), breaker)
    await router.get_prices("AAPL", date(2024, 1, 1), date(2024, 1, 3), "1d")
    await router.get_prices("AAPL", date(2024, 1, 1), date(2024, 1, 3), "1d")
    assert primary.calls == 1
    assert backup.calls == 2


@pytest.mark.asyncio
async def test_all_providers_failed() -> None:
    primary = _Prices("yfinance", error=ProviderUnavailableError("down"))
    backup = _Prices("twelvedata", error=ProviderUnavailableError("down"))
    router = ConnectorRouter([primary, backup], load_settings())
    with pytest.raises(AllProvidersFailedError) as caught:
        await router.get_prices("AAPL", date(2024, 1, 1), date(2024, 1, 3), "1d")
    assert "yfinance" in caught.value.failures[0]
