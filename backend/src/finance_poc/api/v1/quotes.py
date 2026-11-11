"""Latest quote route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from finance_poc.api.deps import get_market_service
from finance_poc.models.schemas import DataResponse, Quote
from finance_poc.services.market_data_service import MarketDataService

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("/{ticker}", response_model=DataResponse[Quote])
async def get_quote(
    ticker: str,
    service: MarketDataService = Depends(get_market_service),
) -> DataResponse[Quote]:
    """Return the latest quote."""
    return await service.get_quote(ticker)
