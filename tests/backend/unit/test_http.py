"""Status mapping and retries for the shared HTTP helper."""

from __future__ import annotations

import httpx
import pytest
import respx

from finance_poc.core.config import load_settings
from finance_poc.core.exceptions import (
    AuthenticationError,
    ProviderUnavailableError,
    RateLimitExceededError,
)
from finance_poc.utils.http import request_json


def _settings(monkeypatch: pytest.MonkeyPatch, *, attempts: int = 1) -> object:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("HTTP_RETRY_ATTEMPTS", str(attempts))
    monkeypatch.setenv("HTTP_RETRY_MIN_SECONDS", "0.01")
    monkeypatch.setenv("HTTP_RETRY_MAX_SECONDS", "0.02")
    return load_settings()


@pytest.mark.asyncio
async def test_retries_server_errors_then_returns_json(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, attempts=2)
    async with httpx.AsyncClient() as client:
        with respx.mock:
            route = respx.get("https://example.test/quote").mock(
                side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": True})]
            )
            payload = await request_json(
                client,
                "GET",
                "https://example.test/quote",
                settings=settings,  # type: ignore[arg-type]
                provider="finnhub",
                params={"token": "secret-token"},
            )
    assert payload == {"ok": True}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_authentication_errors_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, attempts=3)
    async with httpx.AsyncClient() as client:
        with respx.mock:
            route = respx.get("https://example.test/quote").respond(401)
            with pytest.raises(AuthenticationError):
                await request_json(
                    client,
                    "GET",
                    "https://example.test/quote",
                    settings=settings,  # type: ignore[arg-type]
                    provider="finnhub",
                )
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_rate_limit_includes_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get("https://example.test/quote").respond(429, headers={"Retry-After": "12"})
            with pytest.raises(RateLimitExceededError) as caught:
                await request_json(
                    client,
                    "GET",
                    "https://example.test/quote",
                    settings=settings,  # type: ignore[arg-type]
                    provider="finnhub",
                )
    assert caught.value.retry_after == 12


@pytest.mark.asyncio
async def test_server_error_without_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get("https://example.test/quote").respond(503)
            with pytest.raises(ProviderUnavailableError):
                await request_json(
                    client,
                    "GET",
                    "https://example.test/quote",
                    settings=settings,  # type: ignore[arg-type]
                    provider="finnhub",
                )
