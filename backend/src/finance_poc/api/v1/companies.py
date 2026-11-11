"""Company profile and financial statement routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from finance_poc.api.deps import get_market_service
from finance_poc.models.schemas import CompanyProfile, DataResponse, FinancialStatementItem
from finance_poc.services.market_data_service import MarketDataService

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/{ticker}", response_model=DataResponse[CompanyProfile])
async def get_company(
    ticker: str,
    service: MarketDataService = Depends(get_market_service),
) -> DataResponse[CompanyProfile]:
    """Return a normalized company profile."""
    return await service.get_company_profile(ticker)


@router.get("/{ticker}/financials", response_model=DataResponse[list[FinancialStatementItem]])
async def get_financials(
    ticker: str,
    service: MarketDataService = Depends(get_market_service),
) -> DataResponse[list[FinancialStatementItem]]:
    """Return annual statement facts."""
    return await service.get_financials(ticker)
