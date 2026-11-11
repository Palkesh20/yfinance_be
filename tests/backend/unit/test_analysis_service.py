"""Price-move math and the three research roles."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from finance_poc.core.exceptions import AllProvidersFailedError, DataNotFoundError, ValidationError
from finance_poc.models.schemas import (
    CompanyProfile,
    DataResponse,
    NewsFeed,
    NewsItem,
    PriceBar,
)
from finance_poc.services.analysis_service import (
    AnalysisService,
    _headlines_in_window,
    measure_move,
    resolve_period,
)


def _bar(day: int, close: float, *, open_price: float | None = None) -> PriceBar:
    return PriceBar(
        ticker="AAPL",
        timestamp=datetime(2026, 11, day, tzinfo=UTC),
        open=close if open_price is None else open_price,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=10,
        source="yfinance",
    )


def _envelope(data: object, source: str = "yfinance") -> DataResponse[object]:
    return DataResponse(data=data, source=source, cached=False, as_of=datetime.now(UTC))


class _Market:
    def __init__(self) -> None:
        self.price_calls: list[str] = []

    async def get_prices(
        self, ticker: str, *, start: object = None, end: object = None, interval: str = "1d"
    ) -> DataResponse[list[PriceBar]]:
        self.price_calls.append(ticker)
        if ticker == "SPY":
            return _envelope([_bar(3, 100), _bar(6, 101)])  # type: ignore[return-value]
        return _envelope([_bar(3, 100, open_price=99), _bar(4, 90), _bar(6, 110)])  # type: ignore[return-value]

    async def get_company_profile(self, ticker: str) -> DataResponse[CompanyProfile]:
        profile = CompanyProfile(
            ticker=ticker,
            name="Apple Inc.",
            sector="Technology",
            industry="Consumer Electronics",
            source="yfinance",
        )
        return _envelope(profile)  # type: ignore[return-value]

    async def get_news(self, ticker: str, *, limit: int = 10) -> DataResponse[NewsFeed]:
        feed = NewsFeed(
            items=[
                NewsItem(
                    ticker=ticker,
                    headline="Apple raises guidance",
                    url="https://example.com/apple",
                    published_at=datetime(2026, 11, 6, tzinfo=UTC),
                    source="finnhub",
                )
            ],
            sentiment_label="bullish",
            source="finnhub",
        )
        return _envelope(feed, source="finnhub")  # type: ignore[return-value]

    async def get_filings(self, ticker: str, *, limit: int = 10) -> object:
        raise AllProvidersFailedError("filings down")


class _Grok:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def write(self, *, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(system_prompt)
        if "primary research agent" in system_prompt:
            return "Guidance raise is the company-specific lead."
        if "secondary research agent" in system_prompt:
            return "The stock outpaced the benchmark."
        return "Apple rose about 10 percent. Guidance is the lead, and the move beat the market."


def test_last_day_uses_the_prior_close_and_longer_windows_use_the_span() -> None:
    bars = [_bar(3, 100, open_price=99), _bar(4, 90), _bar(6, 110)]
    day = measure_move(bars, "1d")
    week = measure_move(bars, "1w")
    assert day.start_price == 90
    assert day.end_price == 110
    assert day.direction == "rose"
    assert day.window_start.isoformat() == "2026-11-04"
    assert week.start_price == 100
    assert week.end_price == 110
    assert week.direction == "rose"


def test_headlines_include_the_morning_after_the_window() -> None:
    feed = NewsFeed(
        items=[
            NewsItem(
                headline="Huang controversy",
                summary="Reports describe an alleged Chinese spy.",
                url="https://example.com/huang",
                published_at=datetime(2026, 11, 11, 14, tzinfo=UTC),
                source="yfinance",
            ),
            NewsItem(
                headline="Too late",
                url="https://example.com/late",
                published_at=datetime(2026, 11, 13, tzinfo=UTC),
                source="yfinance",
            ),
        ],
        source="yfinance",
    )
    envelope = DataResponse(data=feed, source="yfinance", cached=False, as_of=datetime.now(UTC))
    selected = _headlines_in_window(envelope, date(2026, 11, 4), date(2026, 11, 10))
    assert [item.headline for item in selected] == ["Huang controversy"]


def test_a_decline_and_an_unknown_period() -> None:
    move = measure_move([_bar(3, 50, open_price=40), _bar(4, 40)], "1m")
    assert move.direction == "fell"
    assert move.change_percent == pytest.approx(-20)
    with pytest.raises(ValidationError):
        resolve_period("2d")


@pytest.mark.asyncio
async def test_explain_asks_primary_secondary_and_analyst() -> None:
    market = _Market()
    grok = _Grok()
    service = AnalysisService(market, grok)  # type: ignore[arg-type]
    result = await service.explain("aapl", "1w")
    assert result.data.move.direction == "rose"
    assert result.data.company_name == "Apple Inc."
    assert result.data.benchmark_ticker == "SPY"
    assert "Guidance raise" in result.data.primary_research
    assert "outpaced" in result.data.secondary_research
    assert result.data.note.startswith("Apple rose")
    assert any("filings unavailable" in gap for gap in result.data.evidence_gaps)
    assert len(grok.prompts) == 3
    assert grok.prompts[-1].startswith("You are the analyst")
    assert any("primary research agent" in prompt for prompt in grok.prompts)
    assert any("secondary research agent" in prompt for prompt in grok.prompts)
    assert market.price_calls == ["AAPL", "SPY"]


@pytest.mark.asyncio
async def test_missing_prices_stop_the_analysis() -> None:
    class _Empty(_Market):
        async def get_prices(
            self, ticker: str, *, start: object = None, end: object = None, interval: str = "1d"
        ) -> DataResponse[list[PriceBar]]:
            raise DataNotFoundError(f"No prices for {ticker}")

    service = AnalysisService(_Empty(), _Grok())  # type: ignore[arg-type]
    with pytest.raises(DataNotFoundError):
        await service.explain("AAPL", "1d")
