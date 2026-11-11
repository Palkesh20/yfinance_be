"""Provider clients with the network and yfinance library faked."""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd
import pytest
import respx

from finance_poc.connectors.edgar_client import EdgarClient
from finance_poc.connectors.finnhub_client import FinnhubClient
from finance_poc.connectors.twelvedata_client import TwelveDataClient
from finance_poc.connectors.yfinance_client import YFinanceClient
from finance_poc.core.config import load_settings
from finance_poc.core.exceptions import DataNotFoundError


def _settings(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("HTTP_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-test")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "twelve-test")
    monkeypatch.setenv("SEC_COMPANY_NAME", "Example Services")
    monkeypatch.setenv("SEC_CONTACT_EMAIL", "research@example.com")
    return load_settings()


@pytest.mark.asyncio
async def test_yfinance_reads_nested_news(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {
            "content": {
                "title": "Huang controversy",
                "summary": "<p>Alleged Chinese spy.</p>",
                "pubDate": "2026-11-11T14:00:00Z",
                "canonicalUrl": {"url": "https://example.com/huang"},
                "provider": {"displayName": "CNBC"},
            }
        }
    ]
    monkeypatch.setattr("finance_poc.connectors.yfinance_client._load_news", lambda *args: payload)
    client = YFinanceClient(_settings(monkeypatch))  # type: ignore[arg-type]
    feed = await client.get_news("NVDA", limit=5)
    assert feed.items[0].headline == "Huang controversy"
    assert feed.items[0].summary == "Alleged Chinese spy."
    assert feed.items[0].publisher == "CNBC"


@pytest.mark.asyncio
async def test_finnhub_keeps_the_newest_headlines(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    async with httpx.AsyncClient() as http:
        client = FinnhubClient(http, settings)  # type: ignore[arg-type]
        with respx.mock:
            respx.get("https://finnhub.io/api/v1/company-news").respond(
                json=[
                    {
                        "headline": "Older note",
                        "url": "https://example.com/old",
                        "datetime": 1762000000,
                        "source": "Reuters",
                    },
                    {
                        "headline": "Huang controversy",
                        "url": "https://example.com/new",
                        "datetime": 1762800000,
                        "source": "CNBC",
                        "summary": "Spy reports",
                    },
                ]
            )
            respx.get("https://finnhub.io/api/v1/news-sentiment").respond(status_code=404)
            feed = await client.get_news("NVDA", limit=1)
    assert feed.items[0].headline == "Huang controversy"


@pytest.mark.asyncio
async def test_yfinance_normalizes_bars_and_rejects_an_empty_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [10.0]},
        index=pd.to_datetime(["2024-01-02T00:00:00Z"]),
    )
    monkeypatch.setattr("finance_poc.connectors.yfinance_client._load_history", lambda *args: frame)
    client = YFinanceClient(_settings(monkeypatch))  # type: ignore[arg-type]
    bars = await client.get_prices("AAPL", date(2024, 1, 1), date(2024, 2, 1), "1d")
    assert bars[0].close == 1.5
    assert bars[0].source == "yfinance"
    monkeypatch.setattr(
        "finance_poc.connectors.yfinance_client._load_history", lambda *args: pd.DataFrame()
    )
    with pytest.raises(DataNotFoundError):
        await client.get_prices("AAPL", date(2024, 1, 1), date(2024, 2, 1), "1d")


@pytest.mark.asyncio
async def test_finnhub_quote_and_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    async with httpx.AsyncClient() as http:
        client = FinnhubClient(http, settings)  # type: ignore[arg-type]
        with respx.mock:
            respx.get("https://finnhub.io/api/v1/quote").respond(
                json={"c": 190.5, "d": 1.5, "dp": 0.8, "pc": 189.0, "t": 1700000000}
            )
            quote = await client.get_quote("AAPL")
    assert quote.price == 190.5
    assert quote.source == "finnhub"
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    empty = FinnhubClient(http, load_settings())
    assert await empty.health_check() is False


@pytest.mark.asyncio
async def test_twelve_data_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    async with httpx.AsyncClient() as http:
        client = TwelveDataClient(http, settings)  # type: ignore[arg-type]
        with respx.mock:
            respx.get("https://api.twelvedata.com/time_series").respond(
                json={
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
            )
            bars = await client.get_prices("AAPL", date(2024, 1, 1), date(2024, 1, 3), "1d")
    assert bars[0].close == 1.5
    assert bars[0].source == "twelvedata"


@pytest.mark.asyncio
async def test_edgar_filings_resolve_cik(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    async with httpx.AsyncClient() as http:
        client = EdgarClient(http, settings)  # type: ignore[arg-type]
        with respx.mock:
            respx.get("https://www.sec.gov/files/company_tickers.json").respond(
                json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
            )
            respx.get("https://data.sec.gov/submissions/CIK0000320193.json").respond(
                json={
                    "filings": {
                        "recent": {
                            "form": ["10-K"],
                            "filingDate": ["2024-11-01"],
                            "accessionNumber": ["0000320193-24-000123"],
                            "primaryDocument": ["aapl-20240928.htm"],
                        }
                    }
                }
            )
            filings = await client.get_filings("AAPL", limit=5)
    assert filings[0].form == "10-K"
    assert filings[0].url is not None
    assert "320193" in filings[0].url
