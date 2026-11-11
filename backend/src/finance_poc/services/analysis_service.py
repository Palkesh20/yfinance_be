"""Explain a price move with a primary researcher, a secondary researcher, and an analyst."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from datetime import UTC, date, datetime, timedelta
from typing import TypeVar

from finance_poc.core.exceptions import (
    AllProvidersFailedError,
    AuthenticationError,
    DataNotFoundError,
    InvalidResponseError,
    ProviderUnavailableError,
    RateLimitExceededError,
    ValidationError,
)
from finance_poc.llm.grok_client import GrokClient
from finance_poc.models.schemas import (
    AnalysisNote,
    CompanyProfile,
    DataResponse,
    Filing,
    FinancialStatementItem,
    NewsFeed,
    NewsItem,
    PriceBar,
    PriceMove,
)
from finance_poc.services.market_data_service import MarketDataService, normalize_ticker

logger = logging.getLogger(__name__)

PERIOD_LABELS = {
    "1d": "last day",
    "1w": "last week",
    "1m": "last month",
    "1y": "last year",
}
_FETCH_DAYS = {"1d": 10, "1w": 7, "1m": 31, "1y": 366}
_NEWS_LIMIT = {"1d": 40, "1w": 40, "1m": 50, "1y": 50}
_FILING_LIMIT = {"1d": 10, "1w": 15, "1m": 20, "1y": 40}
_OPTIONAL_ERRORS = (
    DataNotFoundError,
    AllProvidersFailedError,
    ProviderUnavailableError,
    InvalidResponseError,
    AuthenticationError,
    RateLimitExceededError,
)
T = TypeVar("T")

_PRIMARY_PROMPT = (
    "You are the primary research agent at a financial services firm. "
    "Explain the company-specific reasons the stock rose or fell in this window. "
    "Use only the evidence in the user message. "
    "If headlines or filings are missing, say the company-specific evidence is incomplete. "
    "Do not invent events, prices, or a buy or sell recommendation."
)
_SECONDARY_PROMPT = (
    "You are the secondary research agent at a financial services firm. "
    "Explain the market and business context around the move: benchmark, sector, sentiment, "
    "and reported financial facts when those facts are present. "
    "Use only the evidence in the user message. "
    "Do not invent numbers or a buy or sell recommendation."
)
_ANALYST_PROMPT = (
    "You are the analyst. Write a short client note in plain language. "
    "Open with whether the stock rose, fell, or was flat, and the size of the move. "
    "Then explain the likely drivers using the primary research and the secondary research. "
    "Keep what the evidence supports separate from what is unknown. "
    "Do not invent prices, headlines, filings, or a recommendation."
)


def resolve_period(period: str) -> str:
    """Return a supported lookback code or raise ValidationError."""
    selected = period.strip().lower()
    if selected not in PERIOD_LABELS:
        raise ValidationError("Period must be 1d, 1w, 1m, or 1y")
    return selected


def measure_move(bars: list[PriceBar], period: str) -> PriceMove:
    """Measure the last session, or the first close to the last close for longer windows."""
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    if not ordered:
        raise DataNotFoundError("No prices for the selected window")
    if period == "1d" and len(ordered) >= 2:
        used = ordered[-2:]
        start_price = used[0].close
    else:
        used = ordered
        start_price = used[0].open if period == "1d" else used[0].close
    end_price = used[-1].close
    if start_price == 0:
        raise InvalidResponseError("Price series has no usable start price")
    change_percent = ((end_price - start_price) / start_price) * 100
    if change_percent > 0:
        direction = "rose"
    elif change_percent < 0:
        direction = "fell"
    else:
        direction = "flat"
    return PriceMove(
        start_price=start_price,
        end_price=end_price,
        change_percent=change_percent,
        high=max(bar.high for bar in used),
        low=min(bar.low for bar in used),
        direction=direction,
        window_start=_bar_date(used[0]),
        window_end=_bar_date(used[-1]),
    )


class AnalysisService:
    """Gather evidence, then ask the three Grok roles to explain the move."""

    def __init__(self, market: MarketDataService, grok: GrokClient) -> None:
        self._market = market
        self._grok = grok

    async def explain(self, ticker: str, period: str) -> DataResponse[AnalysisNote]:
        """Return the analyst note for one ticker and lookback window."""
        symbol = normalize_ticker(ticker)
        selected = resolve_period(period)
        today = datetime.now(UTC).date()
        fetch_start = today - timedelta(days=_FETCH_DAYS[selected])
        prices = await self._market.get_prices(symbol, start=fetch_start, end=today, interval="1d")
        move = measure_move(prices.data, selected)
        gaps = _standing_gaps(selected)
        profile, profile_gap = await self._optional(
            "company profile", self._market.get_company_profile(symbol)
        )
        news, news_gap = await self._optional(
            "news", self._market.get_news(symbol, limit=_NEWS_LIMIT[selected])
        )
        filings, filing_gap = await self._optional(
            "filings", self._market.get_filings(symbol, limit=_FILING_LIMIT[selected])
        )
        financials: list[FinancialStatementItem] = []
        financial_gap: str | None = None
        if selected == "1y":
            loaded, financial_gap = await self._optional(
                "financials", self._market.get_financials(symbol)
            )
            financials = [] if loaded is None else loaded.data
        benchmark_ticker = "QQQ" if symbol == "SPY" else "SPY"
        benchmark, benchmark_gap = await self._optional(
            f"{benchmark_ticker} prices",
            self._market.get_prices(benchmark_ticker, start=fetch_start, end=today, interval="1d"),
        )
        for gap in (profile_gap, news_gap, filing_gap, financial_gap, benchmark_gap):
            if gap is not None:
                gaps.append(gap)

        headlines = _headlines_in_window(news, move.window_start, move.window_end)
        if news is not None and not headlines:
            gaps.append("No headlines fell inside the selected window.")
        filing_rows = _filings_in_window(filings, move.window_start, move.window_end)
        benchmark_move = _benchmark_move(benchmark, selected)
        company_name = None if profile is None else profile.data.name
        facts = _price_facts(symbol, selected, move, company_name)
        primary_text, secondary_text = await asyncio.gather(
            self._grok.write(
                system_prompt=_PRIMARY_PROMPT,
                user_prompt=_primary_evidence(facts, headlines, filing_rows, gaps),
            ),
            self._grok.write(
                system_prompt=_SECONDARY_PROMPT,
                user_prompt=_secondary_evidence(
                    facts,
                    None if profile is None else profile.data,
                    news,
                    financials,
                    benchmark_ticker,
                    benchmark_move,
                    gaps,
                ),
            ),
        )
        note = await self._grok.write(
            system_prompt=_ANALYST_PROMPT,
            user_prompt=_analyst_evidence(facts, primary_text, secondary_text, gaps),
        )
        logger.info(
            "analysis completed ticker=%s period=%s direction=%s",
            symbol,
            selected,
            move.direction,
        )
        return DataResponse(
            data=AnalysisNote(
                ticker=symbol,
                period=selected,
                period_label=PERIOD_LABELS[selected],
                company_name=company_name,
                move=move,
                benchmark_ticker=None if benchmark_move is None else benchmark_ticker,
                benchmark_change_percent=(
                    None if benchmark_move is None else benchmark_move.change_percent
                ),
                primary_research=primary_text,
                secondary_research=secondary_text,
                note=note,
                evidence_gaps=gaps,
                source="grok",
            ),
            source="grok",
            cached=False,
            as_of=datetime.now(UTC),
        )

    async def _optional(self, label: str, awaitable: Awaitable[T]) -> tuple[T | None, str | None]:
        try:
            return await awaitable, None
        except _OPTIONAL_ERRORS as exc:
            logger.warning("analysis continuing without %s error=%s", label, type(exc).__name__)
            return None, f"{label} unavailable"


def _standing_gaps(period: str) -> list[str]:
    if period == "1y":
        return ["Headlines cover roughly the last 30 days, not the full year."]
    return []


def _bar_date(bar: PriceBar) -> date:
    if bar.timestamp.tzinfo is None:
        return bar.timestamp.date()
    return bar.timestamp.astimezone(UTC).date()


def _headlines_in_window(
    news: DataResponse[NewsFeed] | None, start: date, end: date
) -> list[NewsItem]:
    """Keep headlines from the day before the window through the day after it.

    Coverage of the last session is often published the next morning.
    """
    if news is None:
        return []
    window_start = start - timedelta(days=1)
    window_end = end + timedelta(days=1)
    selected = [
        item
        for item in news.data.items
        if window_start <= item.published_at.astimezone(UTC).date() <= window_end
    ]
    selected.sort(key=lambda item: item.published_at, reverse=True)
    return selected[:12]


def _filings_in_window(
    filings: DataResponse[list[Filing]] | None, start: date, end: date
) -> list[Filing]:
    if filings is None:
        return []
    return [row for row in filings.data if start <= row.filed_at <= end][:8]


def _benchmark_move(prices: DataResponse[list[PriceBar]] | None, period: str) -> PriceMove | None:
    if prices is None:
        return None
    try:
        return measure_move(prices.data, period)
    except (DataNotFoundError, InvalidResponseError):
        return None


def _price_facts(ticker: str, period: str, move: PriceMove, company_name: str | None) -> str:
    window = f"{move.window_start.isoformat()} to {move.window_end.isoformat()}"
    return "\n".join(
        [
            f"Company: {company_name or ticker} ({ticker})",
            f"Window: {PERIOD_LABELS[period]} ({window})",
            f"Direction: {move.direction}",
            f"Start price: {move.start_price:.2f}",
            f"End price: {move.end_price:.2f}",
            f"Change: {move.change_percent:+.2f}%",
            f"High: {move.high:.2f}",
            f"Low: {move.low:.2f}",
        ]
    )


def _headline_line(item: NewsItem) -> str:
    published = item.published_at.astimezone(UTC).date().isoformat()
    line = f"- {published}: {item.headline}"
    if item.summary:
        line = f"{line} — {item.summary}"
    return line


def _primary_evidence(
    facts: str, headlines: list[NewsItem], filings: list[Filing], gaps: list[str]
) -> str:
    headline_lines = [_headline_line(item) for item in headlines] or [
        "- No company headlines were available in this window."
    ]
    filing_lines = [
        f"- {row.filed_at.isoformat()} {row.form}" + (f" {row.url}" if row.url else "")
        for row in filings
    ] or ["- No SEC filings were available in this window."]
    return "\n".join(
        [
            facts,
            "Headlines:",
            *headline_lines,
            "Filings:",
            *filing_lines,
            "Gaps:",
            *_gap_lines(gaps),
        ]
    )


def _secondary_evidence(
    facts: str,
    profile: CompanyProfile | None,
    news: DataResponse[NewsFeed] | None,
    financials: list[FinancialStatementItem],
    benchmark_ticker: str,
    benchmark_move: PriceMove | None,
    gaps: list[str],
) -> str:
    sector = None if profile is None else profile.sector
    industry = None if profile is None else profile.industry
    sentiment = "unavailable"
    if news is not None and news.data.sentiment_label:
        sentiment = news.data.sentiment_label
    if benchmark_move is None:
        benchmark_line = f"{benchmark_ticker}: unavailable"
    else:
        benchmark_line = (
            f"{benchmark_ticker}: {benchmark_move.start_price:.2f} to "
            f"{benchmark_move.end_price:.2f} ({benchmark_move.change_percent:+.2f}%)"
        )
    fact_lines = [
        (
            f"- {item.label}: {item.value} {item.unit} "
            f"for period ending {item.period_end.isoformat()}"
        )
        for item in financials[:6]
    ] or ["- No financial facts were requested for this window."]
    return "\n".join(
        [
            facts,
            f"Sector: {sector or 'unknown'}",
            f"Industry: {industry or 'unknown'}",
            f"News sentiment: {sentiment}",
            f"Benchmark: {benchmark_line}",
            "Financial facts:",
            *fact_lines,
            "Gaps:",
            *_gap_lines(gaps),
        ]
    )


def _analyst_evidence(facts: str, primary: str, secondary: str, gaps: list[str]) -> str:
    return "\n".join(
        [
            facts,
            "Primary research:",
            primary,
            "Secondary research:",
            secondary,
            "Gaps:",
            *_gap_lines(gaps),
        ]
    )


def _gap_lines(gaps: list[str]) -> list[str]:
    return [f"- {gap}" for gap in gaps] or ["- None."]
