"""Process health, including a database ping and provider configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from finance_poc.api.deps import get_router, get_session
from finance_poc.connectors.router import ConnectorRouter
from finance_poc.models.schemas import HealthResponse
from finance_poc.storage.db import check_db

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    session: AsyncSession = Depends(get_session),
    connector_router: ConnectorRouter = Depends(get_router),
) -> HealthResponse:
    """Report whether the process can use its database and how providers are configured."""
    await check_db(session)
    providers = {
        connector.name: "ok" if await connector.health_check() else "unavailable"
        for connector in connector_router.connectors
    }
    return HealthResponse(status="ok", providers=providers)
