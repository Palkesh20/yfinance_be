"""Company news route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from finance_poc.api.deps import get_market_service
from finance_poc.models.schemas import DataResponse, NewsFeed
from finance_poc.services.market_data_service import MarketDataService

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=DataResponse[NewsFeed])
async def get_news(
    ticker: str,
    limit: int = Query(default=10, ge=1, le=50),
    service: MarketDataService = Depends(get_market_service),
) -> DataResponse[NewsFeed]:
    """Return recent headlines for a ticker."""
    return await service.get_news(ticker, limit=limit)
