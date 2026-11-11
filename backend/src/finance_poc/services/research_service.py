"""Ask Grok a question using headlines already fetched by the market service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from finance_poc.core.exceptions import DataNotFoundError, ValidationError
from finance_poc.llm.grok_client import GrokClient
from finance_poc.models.schemas import DataResponse, ResearchAnswer
from finance_poc.services.market_data_service import MarketDataService, normalize_ticker

logger = logging.getLogger(__name__)


class ResearchService:
    """Ground a Grok answer in the latest stored or freshly fetched headlines."""

    def __init__(self, market: MarketDataService, grok: GrokClient) -> None:
        self._market = market
        self._grok = grok

    async def answer(self, ticker: str, question: str) -> DataResponse[ResearchAnswer]:
        """Return a Grok answer for one ticker. Answers are not cached."""
        symbol = normalize_ticker(ticker)
        text = question.strip()
        if len(text) < 3 or len(text) > 1000:
            raise ValidationError("Question must be between 3 and 1000 characters")
        headlines = await self._headlines(symbol)
        answer_text = await self._grok.complete(ticker=symbol, question=text, headlines=headlines)
        logger.info("research completed ticker=%s", symbol)
        return DataResponse(
            data=ResearchAnswer(ticker=symbol, question=text, answer=answer_text, source="grok"),
            source="grok",
            cached=False,
            as_of=datetime.now(UTC),
        )

    async def _headlines(self, ticker: str) -> list[str]:
        try:
            news = await self._market.get_news(ticker, limit=5)
        except DataNotFoundError:
            logger.warning("research continuing without headlines ticker=%s", ticker)
            return []
        return [item.headline for item in news.data.items]
