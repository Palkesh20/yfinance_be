"""Database URL normalization for the async engine."""

from __future__ import annotations

from finance_poc.storage.db import _async_postgres_target, create_db_engine


def test_render_internal_url_uses_asyncpg() -> None:
    url, connect_args = _async_postgres_target("postgresql://user:secret@dpg-abc-a/finance_poc")

    assert url.startswith("postgresql+asyncpg://")
    assert "@dpg-abc-a/finance_poc" in url
    assert connect_args == {}


def test_render_external_url_enables_ssl() -> None:
    raw = "postgres://user:secret@dpg-abc.oregon-postgres.render.com/finance_poc?sslmode=require"
    url, connect_args = _async_postgres_target(raw)

    assert url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in url
    assert connect_args == {"ssl": True}


async def test_plain_postgres_engine_loads_asyncpg() -> None:
    engine = create_db_engine("postgresql://user:secret@dpg-abc-a/finance_poc")
    try:
        assert engine.url.drivername == "postgresql+asyncpg"
    finally:
        await engine.dispose()
