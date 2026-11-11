"""HTTP routes, error mapping, and the request id header."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from finance_poc.api.deps import get_analysis_service, get_market_service
from finance_poc.core.exceptions import DataNotFoundError, RateLimitExceededError
from finance_poc.main import create_app
from finance_poc.models.schemas import AnalysisNote, DataResponse, PriceMove, Quote
from finance_poc.services.market_data_service import normalize_ticker


class _Market:
    async def get_quote(self, ticker: str) -> DataResponse[Quote]:
        symbol = normalize_ticker(ticker)
        return DataResponse(
            data=Quote(ticker=symbol, price=10, as_of=datetime.now(UTC), source="finnhub"),
            source="finnhub",
            cached=False,
            as_of=datetime.now(UTC),
        )

    async def get_prices(
        self, ticker: str, *, start: object = None, end: object = None, interval: str = "1d"
    ) -> object:
        raise DataNotFoundError(f"No prices for {ticker}")


class _Limited:
    async def get_quote(self, ticker: str) -> object:
        raise RateLimitExceededError("slow down", retry_after=9)


def test_health_and_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"X-Request-ID": "req-abc"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"] == "req-abc"


def test_quote_route_uses_the_service() -> None:
    app = create_app()
    app.dependency_overrides[get_market_service] = lambda: _Market()
    with TestClient(app) as client:
        response = client.get("/api/v1/quotes/AAPL")
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["data"]["price"] == 10
    assert body["source"] == "finnhub"


def test_not_found_and_rate_limit_mapping() -> None:
    app = create_app()
    app.dependency_overrides[get_market_service] = lambda: _Market()
    with TestClient(app) as client:
        missing = client.get("/api/v1/prices/AAPL")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "data_not_found"
    assert "Traceback" not in missing.text

    limited = create_app()
    limited.dependency_overrides[get_market_service] = lambda: _Limited()
    with TestClient(limited) as client:
        response = client.get("/api/v1/quotes/AAPL")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "9"


def test_analysis_route_returns_the_note() -> None:
    move = PriceMove(
        start_price=100,
        end_price=110,
        change_percent=10,
        high=112,
        low=99,
        direction="rose",
        window_start=datetime(2026, 11, 3, tzinfo=UTC).date(),
        window_end=datetime(2026, 11, 6, tzinfo=UTC).date(),
    )
    note = AnalysisNote(
        ticker="AAPL",
        period="1w",
        period_label="last week",
        company_name="Apple Inc.",
        move=move,
        benchmark_ticker="SPY",
        benchmark_change_percent=1,
        primary_research="Guidance raise.",
        secondary_research="Beat the market.",
        note="Apple rose 10 percent.",
        evidence_gaps=[],
        source="grok",
    )

    class _Analysis:
        async def explain(self, ticker: str, period: str) -> DataResponse[AnalysisNote]:
            return DataResponse(data=note, source="grok", cached=False, as_of=datetime.now(UTC))

    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: _Analysis()
    with TestClient(app) as client:
        accepted = client.post("/api/v1/analysis", json={"ticker": "AAPL", "period": "1w"})
        rejected = client.post("/api/v1/analysis", json={"ticker": "AAPL", "period": "2d"})
    assert accepted.status_code == 200
    assert accepted.json()["data"]["note"] == "Apple rose 10 percent."
    assert accepted.json()["data"]["move"]["direction"] == "rose"
    assert rejected.status_code == 422


def test_invalid_ticker_is_422() -> None:
    app = create_app()
    app.dependency_overrides[get_market_service] = lambda: _Market()
    with TestClient(app) as client:
        response = client.get("/api/v1/quotes/!!!")
    assert response.status_code == 422
    assert response.json()["error"]["request_id"]
