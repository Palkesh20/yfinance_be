"""ORM models. The cache table is the Phase 1 store and is portable to Postgres."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared metadata for create_all."""


class CacheEntry(Base):
    """JSON response cached until ``expires_at``."""

    __tablename__ = "cache_entries"

    cache_key: Mapped[str] = mapped_column("cache_key", String(512), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
