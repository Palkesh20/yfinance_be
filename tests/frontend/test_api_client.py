"""The UI client talks to the API and never imports the backend package."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from api_client import ApiClient, ApiError


def test_frontend_sources_do_not_import_the_backend() -> None:
    root = Path(__file__).resolve().parents[2] / "frontend"
    offenders = [
        path.name
        for path in root.rglob("*.py")
        if "finance_poc" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_client_reads_prices_and_surfaces_api_errors() -> None:
    payload = {
        "data": [
            {
                "ticker": "AAPL",
                "timestamp": "2024-01-02T00:00:00Z",
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 10,
                "source": "yfinance",
            }
        ],
        "source": "yfinance",
        "cached": False,
        "as_of": "2024-01-02T00:00:00Z",
    }
    with respx.mock(base_url="http://api.test") as mock:
        mock.get("/api/v1/prices/AAPL").respond(json=payload)
        mock.get("/api/v1/companies/NOPE").respond(
            status_code=404,
            json={
                "error": {
                    "code": "data_not_found",
                    "message": "No company profile",
                    "request_id": "r1",
                }
            },
        )
        client = ApiClient("http://api.test", httpx.Client(base_url="http://api.test"))
        bars, envelope = client.get_prices("AAPL")
        assert bars[0].close == 1.5
        assert envelope.source == "yfinance"
        try:
            client.get_company("NOPE")
            raise AssertionError("expected API error")
        except ApiError as exc:
            assert exc.status_code == 404
            assert exc.message == "No company profile"


def test_client_reads_a_move_note() -> None:
    payload = {
        "data": {
            "ticker": "AAPL",
            "period": "1w",
            "period_label": "last week",
            "company_name": "Apple Inc.",
            "move": {
                "start_price": 100,
                "end_price": 110,
                "change_percent": 10,
                "high": 112,
                "low": 99,
                "direction": "rose",
                "window_start": "2026-11-03",
                "window_end": "2026-11-06",
            },
            "benchmark_ticker": "SPY",
            "benchmark_change_percent": 1,
            "primary_research": "Guidance raise.",
            "secondary_research": "Beat the market.",
            "note": "Apple rose 10 percent.",
            "evidence_gaps": [],
            "source": "grok",
        },
        "source": "grok",
        "cached": False,
        "as_of": "2026-11-08T00:00:00Z",
    }
    with respx.mock(base_url="http://api.test") as mock:
        mock.post("/api/v1/analysis").respond(json=payload)
        client = ApiClient("http://api.test", httpx.Client(base_url="http://api.test"))
        note, envelope = client.explain_move("AAPL", "1w")
    assert note.note == "Apple rose 10 percent."
    assert note.move.direction == "rose"
    assert envelope.source == "grok"
