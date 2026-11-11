"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finance_poc import __version__
from finance_poc.api.error_handlers import register_error_handlers
from finance_poc.api.middleware import RequestContextMiddleware
from finance_poc.api.v1.health import router as health_router
from finance_poc.api.v1.router import router as v1_router
from finance_poc.connectors.router import build_router
from finance_poc.core.config import get_settings
from finance_poc.core.constants import APP_NAME
from finance_poc.core.logging_config import setup_logging
from finance_poc.llm.grok_client import GrokClient
from finance_poc.storage.db import create_db_engine, create_session_factory, init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the database, HTTP client, and provider router for the process."""
    settings = get_settings()
    setup_logging(settings)
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    await init_db(engine)
    http = httpx.AsyncClient()
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.http = http
    app.state.router = build_router(settings, http)
    app.state.grok = GrokClient(http, settings)
    try:
        yield
    finally:
        await http.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    """Build the API. Interactive docs are enabled only in the dev profile."""
    settings = get_settings()
    docs_url = "/docs" if settings.docs_enabled() else None
    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url="/redoc" if settings.docs_enabled() else None,
        openapi_url="/openapi.json" if settings.docs_enabled() else None,
    )
    register_error_handlers(app)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(v1_router, prefix="/api/v1")
    return app


app = create_app()
