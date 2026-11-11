"""Cache miss falls back from yfinance to Twelve Data, then the next call is cached."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from finance_poc.core.config import get_settings
from finance_poc.core.exceptions import ProviderUnavailableError
from finance_poc.main import create_app


@pytest.fixture
def twelve_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("HTTP_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "twelve-test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "finance_poc.connectors.yfinance_client._load_history",
        lambda *args: (_ for _ in ()).throw(ProviderUnavailableError("down")),
    )
    app = create_app()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def test_fallback_then_cache_hit(twelve_app: TestClient) -> None:
    payload = {
        "status": "ok",
        "values": [
            {
                "datetime": "2024-01-02",
                "open": "1",
                "high": "2",
                "low": "0.5",
                "close": "1.5",
                "volume": "10",
            }
        ],
    }
    with respx.mock:
        route = respx.get("https://api.twelvedata.com/time_series").mock(
            return_value=httpx.Response(200, json=payload)
        )
        first = twelve_app.get("/api/v1/prices/AAPL")
        second = twelve_app.get("/api/v1/prices/AAPL")
    assert first.status_code == 200
    assert first.json()["source"] == "twelvedata"
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert route.call_count == 1
