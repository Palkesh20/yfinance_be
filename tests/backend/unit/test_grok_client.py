"""Grok chat client."""

from __future__ import annotations

import httpx
import pytest
import respx

from finance_poc.core.config import load_settings
from finance_poc.core.exceptions import ConfigurationError, InvalidResponseError
from finance_poc.llm.grok_client import GrokClient


def _settings(monkeypatch: pytest.MonkeyPatch, key: str = "grok-test") -> object:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("HTTP_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("GROK_API_KEY", key)
    return load_settings()


@pytest.mark.asyncio
async def test_complete_returns_the_assistant_text(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    async with httpx.AsyncClient() as http:
        client = GrokClient(http, settings)  # type: ignore[arg-type]
        with respx.mock:
            route = respx.post("https://api.x.ai/v1/chat/completions").respond(
                json={"choices": [{"message": {"content": "Headlines are mixed."}}]}
            )
            text = await client.complete(
                ticker="AAPL", question="What is the tone?", headlines=["Apple rises"]
            )
    body = route.calls[0].request.content.decode()
    assert text == "Headlines are mixed."
    assert "Apple rises" in body
    assert "grok-test" not in body


@pytest.mark.asyncio
async def test_missing_key_and_empty_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    async with httpx.AsyncClient() as http:
        client = GrokClient(http, _settings(monkeypatch, key=""))  # type: ignore[arg-type]
        with pytest.raises(ConfigurationError):
            await client.complete(ticker="AAPL", question="Tone?", headlines=[])
        keyed = GrokClient(http, _settings(monkeypatch))  # type: ignore[arg-type]
        with respx.mock:
            respx.post("https://api.x.ai/v1/chat/completions").respond(json={"choices": []})
            with pytest.raises(InvalidResponseError):
                await keyed.complete(ticker="AAPL", question="Tone?", headlines=[])
