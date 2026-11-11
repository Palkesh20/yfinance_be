"""FastAPI dependencies. Resources are created in the application lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from finance_poc.connectors.router import ConnectorRouter
from finance_poc.core.config import Settings
from finance_poc.llm.grok_client import GrokClient
from finance_poc.services.analysis_service import AnalysisService
from finance_poc.services.market_data_service import MarketDataService
from finance_poc.services.research_service import ResearchService
from finance_poc.storage.cache import ResponseCache
from finance_poc.storage.db import session_scope


def get_settings_dep(request: Request) -> Settings:
    """Return the settings stored on the application."""
    return request.app.state.settings  # type: ignore[no-any-return]


def get_router(request: Request) -> ConnectorRouter:
    """Return the shared connector router."""
    return request.app.state.router  # type: ignore[no-any-return]


def get_grok(request: Request) -> GrokClient:
    """Return the shared Grok client."""
    return request.app.state.grok  # type: ignore[no-any-return]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session for the current request."""
    factory = request.app.state.session_factory
    async with session_scope(factory) as session:
        yield session


def get_market_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    router: Annotated[ConnectorRouter, Depends(get_router)],
) -> MarketDataService:
    """Build the market-data service for one request."""
    return MarketDataService(router, ResponseCache(session), settings)


def get_research_service(
    market: Annotated[MarketDataService, Depends(get_market_service)],
    grok: Annotated[GrokClient, Depends(get_grok)],
) -> ResearchService:
    """Build the research service for one request."""
    return ResearchService(market, grok)


def get_analysis_service(
    market: Annotated[MarketDataService, Depends(get_market_service)],
    grok: Annotated[GrokClient, Depends(get_grok)],
) -> AnalysisService:
    """Build the move-analysis service for one request."""
    return AnalysisService(market, grok)
