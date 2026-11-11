"""Read and write JSON payloads in the cache table."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from finance_poc.core.exceptions import StorageError
from finance_poc.storage.models import CacheEntry

logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ResponseCache:
    """Cache-aside store keyed by resource and request parameters."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Return a stored object, or None when the key is missing or expired."""
        try:
            result = await self._session.execute(
                select(CacheEntry).where(CacheEntry.cache_key == key)
            )
            row = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise StorageError("cache read failed") from exc
        if row is None:
            return None
        if _as_utc(row.expires_at) <= datetime.now(UTC):
            try:
                await self._session.delete(row)
                await self._session.commit()
            except SQLAlchemyError as exc:
                raise StorageError("cache delete failed") from exc
            return None
        try:
            payload = json.loads(row.payload)
        except json.JSONDecodeError as exc:
            raise StorageError("cache payload is invalid") from exc
        if not isinstance(payload, dict):
            raise StorageError("cache payload is invalid")
        return payload

    async def set_json(
        self, key: str, payload: dict[str, Any], *, source: str, ttl_seconds: int
    ) -> None:
        """Insert or replace a payload with a TTL."""
        entry = CacheEntry(
            cache_key=key,
            payload=json.dumps(payload),
            source=source,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        try:
            await self._session.merge(entry)
            await self._session.commit()
        except SQLAlchemyError as exc:
            raise StorageError("cache write failed") from exc
        logger.debug("cache write key=%s source=%s ttl=%s", key, source, ttl_seconds)
