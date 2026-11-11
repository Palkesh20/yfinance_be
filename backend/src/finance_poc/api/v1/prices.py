"""Historical price route."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from finance_poc.api.deps import get_market_service
from finance_poc.core.constants import DEFAULT_PRICE_INTERVAL
from finance_poc.models.schemas import DataResponse, PriceBar
from finance_poc.services.market_data_service import MarketDataService

router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/{ticker}", response_model=DataResponse[list[PriceBar]])
async def get_prices(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
    interval: str = Query(default=DEFAULT_PRICE_INTERVAL, pattern="^(1d|1wk|1h)$"),
    service: MarketDataService = Depends(get_market_service),
) -> DataResponse[list[PriceBar]]:
    """Return normalized price bars."""
    return await service.get_prices(ticker, start=start, end=end, interval=interval)
