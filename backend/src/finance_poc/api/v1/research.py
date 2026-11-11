"""Grok research route. The model sees headlines fetched by the market service."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from finance_poc.api.deps import get_research_service
from finance_poc.models.schemas import DataResponse, ResearchAnswer, ResearchRequest
from finance_poc.services.research_service import ResearchService

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=DataResponse[ResearchAnswer])
async def research(
    body: ResearchRequest,
    service: ResearchService = Depends(get_research_service),
) -> DataResponse[ResearchAnswer]:
    """Answer a question about a ticker with Grok."""
    return await service.answer(body.ticker, body.question)
