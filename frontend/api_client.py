"""Typed HTTP client for the finance API. The UI imports only this module for data."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel

from config import api_base_url


class ApiError(Exception):
    """The API returned an error body or an unexpected status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class PriceBar(BaseModel):
    ticker: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str


class Quote(BaseModel):
    ticker: str
    price: float
    change: float | None = None
    change_percent: float | None = None
    currency: str | None = None
    as_of: str
    source: str


class NewsItem(BaseModel):
    headline: str
    summary: str | None = None
    url: str
    published_at: str
    publisher: str | None = None
    source: str


class NewsFeed(BaseModel):
    items: list[NewsItem]
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    source: str


class CompanyProfile(BaseModel):
    ticker: str
    name: str
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    website: str | None = None
    source: str


class Filing(BaseModel):
    form: str
    filed_at: str
    accession_number: str
    url: str | None = None
    source: str


class ResearchAnswer(BaseModel):
    ticker: str
    question: str
    answer: str
    source: str


class PriceMove(BaseModel):
    start_price: float
    end_price: float
    change_percent: float
    high: float
    low: float
    direction: str
    window_start: str
    window_end: str


class AnalysisNote(BaseModel):
    ticker: str
    period: str
    period_label: str
    company_name: str | None = None
    move: PriceMove
    benchmark_ticker: str | None = None
    benchmark_change_percent: float | None = None
    primary_research: str
    secondary_research: str
    note: str
    evidence_gaps: list[str]
    source: str


class Envelope(BaseModel):
    data: Any
    source: str
    cached: bool
    as_of: str


class ApiClient:
    """Synchronous wrapper around the version 1 routes."""

    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self._base_url = (base_url or api_base_url()).rstrip("/")
        self._client = client or httpx.Client(base_url=self._base_url, timeout=30.0)
        self._owns_client = client is None

    def close(self) -> None:
        """Close the underlying client when this wrapper created it."""
        if self._owns_client:
            self._client.close()

    def get_prices(self, ticker: str, *, interval: str = "1d") -> tuple[list[PriceBar], Envelope]:
        """Return price bars and the response envelope."""
        payload = self._get(f"/api/v1/prices/{ticker}", params={"interval": interval})
        envelope = Envelope.model_validate(payload)
        return [PriceBar.model_validate(item) for item in envelope.data], envelope

    def get_company(self, ticker: str) -> tuple[CompanyProfile, Envelope]:
        """Return a company profile and the response envelope."""
        payload = self._get(f"/api/v1/companies/{ticker}")
        envelope = Envelope.model_validate(payload)
        return CompanyProfile.model_validate(envelope.data), envelope

    def get_news(self, ticker: str, *, limit: int = 10) -> tuple[NewsFeed, Envelope]:
        """Return a news feed and the response envelope."""
        payload = self._get("/api/v1/news", params={"ticker": ticker, "limit": limit})
        envelope = Envelope.model_validate(payload)
        return NewsFeed.model_validate(envelope.data), envelope

    def get_filings(self, ticker: str, *, limit: int = 10) -> tuple[list[Filing], Envelope]:
        """Return filings and the response envelope."""
        payload = self._get(f"/api/v1/filings/{ticker}", params={"limit": limit})
        envelope = Envelope.model_validate(payload)
        return [Filing.model_validate(item) for item in envelope.data], envelope

    def research(self, ticker: str, question: str) -> tuple[ResearchAnswer, Envelope]:
        """Ask Grok a question through the API."""
        payload = self._post("/api/v1/research", json={"ticker": ticker, "question": question})
        envelope = Envelope.model_validate(payload)
        return ResearchAnswer.model_validate(envelope.data), envelope

    def explain_move(self, ticker: str, period: str) -> tuple[AnalysisNote, Envelope]:
        """Ask the research agents why the price moved over one window."""
        payload = self._post(
            "/api/v1/analysis",
            json={"ticker": ticker, "period": period},
            timeout=180.0,
        )
        envelope = Envelope.model_validate(payload)
        return AnalysisNote.model_validate(envelope.data), envelope

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._decode(self._send(lambda: self._client.get(path, params=params)))

    def _post(
        self, path: str, json: dict[str, Any], timeout: float | None = None
    ) -> dict[str, Any]:
        response = self._send(lambda: self._client.post(path, json=json, timeout=timeout))
        return self._decode(response)

    def _send(self, call: Callable[[], httpx.Response]) -> httpx.Response:
        try:
            response = call()
        except httpx.RequestError as exc:
            raise ApiError(0, "The API is not running at " + self._base_url) from exc
        return response

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        if response.is_success:
            body = response.json()
            if not isinstance(body, dict):
                raise ApiError(response.status_code, "The API returned an unexpected payload")
            return body
        raise ApiError(response.status_code, _error_message(response))


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except json.JSONDecodeError:
        return "The API request failed"
    if isinstance(body, dict):
        error = body.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str):
            return message
    return "The API request failed"
