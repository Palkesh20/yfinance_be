"""Async engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from finance_poc.core.exceptions import StorageError
from finance_poc.storage.models import Base


def create_db_engine(url: str) -> AsyncEngine:
    """Create an async engine. SQLite uses one shared connection so tests can use memory."""
    if url.startswith("sqlite"):
        return create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_async_engine(url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory that keeps attributes available after commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create tables. This phase uses create_all instead of a migration tool."""
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except SQLAlchemyError as exc:
        raise StorageError("database initialization failed") from exc


async def check_db(session: AsyncSession) -> None:
    """Raise StorageError when the database cannot answer a trivial query."""
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise StorageError("database unavailable") from exc


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Yield a session and close it when the caller finishes."""
    session = factory()
    try:
        yield session
    except SQLAlchemyError as exc:
        await session.rollback()
        raise StorageError("database operation failed") from exc
    finally:
        await session.close()
