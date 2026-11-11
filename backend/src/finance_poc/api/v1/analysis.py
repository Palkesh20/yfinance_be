"""Move explanation. Three Grok roles share evidence gathered by the market service."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from finance_poc.api.deps import get_analysis_service
from finance_poc.models.schemas import AnalysisNote, AnalysisRequest, DataResponse
from finance_poc.services.analysis_service import AnalysisService

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=DataResponse[AnalysisNote])
async def explain_move(
    body: AnalysisRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> DataResponse[AnalysisNote]:
    """Explain why a stock rose or fell over the last day, week, month, or year."""
    return await service.explain(body.ticker, body.period)
