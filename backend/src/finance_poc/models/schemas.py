"""Normalized models shared by connectors and the HTTP API."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from finance_poc.core.exceptions import InvalidResponseError

T = TypeVar("T")


class PriceBar(BaseModel):
    """One OHLCV bar."""

    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str


class Quote(BaseModel):
    """A latest or delayed price."""

    ticker: str
    price: float
    change: float | None = None
    change_percent: float | None = None
    previous_close: float | None = None
    currency: str | None = None
    as_of: datetime
    source: str


class NewsItem(BaseModel):
    """One headline from a news provider."""

    ticker: str | None = None
    headline: str
    summary: str | None = None
    url: str
    published_at: datetime
    source: str
    publisher: str | None = None


class NewsFeed(BaseModel):
    """Headlines plus an optional company-level sentiment score."""

    items: list[NewsItem]
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    source: str


class CompanyProfile(BaseModel):
    """Identity and descriptive fields for one company."""

    ticker: str
    name: str
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    website: str | None = None
    cik: str | None = None
    source: str


class Filing(BaseModel):
    """One SEC filing index entry."""

    ticker: str
    form: str
    filed_at: date
    accession_number: str
    primary_document: str | None = None
    url: str | None = None
    source: str


class FinancialStatementItem(BaseModel):
    """One reported fact from a financial statement."""

    ticker: str
    statement: str
    concept: str
    label: str
    value: float | None
    unit: str
    period_end: date
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    source: str


class ResearchAnswer(BaseModel):
    """A Grok answer grounded in headlines the platform already fetched."""

    ticker: str
    question: str
    answer: str
    source: str


class DataResponse(BaseModel, Generic[T]):
    """Envelope returned by every data endpoint."""

    data: T
    source: str
    cached: bool
    as_of: datetime


class HealthResponse(BaseModel):
    """Process and provider readiness."""

    status: str
    providers: dict[str, str]


class ResearchRequest(BaseModel):
    """Question asked about one ticker."""

    ticker: str = Field(min_length=1, max_length=10)
    question: str = Field(min_length=3, max_length=1000)


class PriceMove(BaseModel):
    """How the price changed across the bars used for one window."""

    start_price: float
    end_price: float
    change_percent: float
    high: float
    low: float
    direction: str
    window_start: date
    window_end: date


class AnalysisNote(BaseModel):
    """Primary research, secondary research, and the analyst's client note."""

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


class AnalysisRequest(BaseModel):
    """Ticker and lookback window for a move explanation."""

    ticker: str = Field(min_length=1, max_length=10)
    period: str = Field(pattern="^(1d|1w|1m|1y)$")


def coerce_float(value: object, *, field_name: str) -> float:
    """Parse a finite float from a provider payload."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise InvalidResponseError(f"Invalid {field_name}") from exc
    if not math.isfinite(number):
        raise InvalidResponseError(f"Invalid {field_name}")
    return number


def coerce_datetime(value: object, *, field_name: str) -> datetime:
    """Parse a timestamp and return an aware UTC datetime."""
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = datetime.fromtimestamp(value, tz=UTC)
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        if len(text) == 10:
            text = f"{text}T00:00:00"
        text = text.replace(" ", "T", 1)
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise InvalidResponseError(f"Invalid {field_name}") from exc
    else:
        raise InvalidResponseError(f"Invalid {field_name}")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def coerce_date(value: object, *, field_name: str) -> date:
    """Parse a calendar date from a provider payload."""
    return coerce_datetime(value, field_name=field_name).date()
