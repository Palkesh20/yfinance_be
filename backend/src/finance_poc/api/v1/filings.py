"""SEC filing route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from finance_poc.api.deps import get_market_service
from finance_poc.models.schemas import DataResponse, Filing
from finance_poc.services.market_data_service import MarketDataService

router = APIRouter(prefix="/filings", tags=["filings"])


@router.get("/{ticker}", response_model=DataResponse[list[Filing]])
async def get_filings(
    ticker: str,
    limit: int = Query(default=10, ge=1, le=40),
    service: MarketDataService = Depends(get_market_service),
) -> DataResponse[list[Filing]]:
    """Return recent SEC filings."""
    return await service.get_filings(ticker, limit=limit)
