"""Grok chat client. The API key is sent as a bearer token and is never logged."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from finance_poc.core.config import Settings
from finance_poc.core.constants import GROK_CHAT_PATH
from finance_poc.core.exceptions import ConfigurationError, InvalidResponseError
from finance_poc.utils.http import request_json

_SYSTEM_PROMPT = (
    "You are a research assistant for a financial services firm. "
    "Answer only from the headlines provided. "
    "If they are not enough, say what is missing. Do not invent prices or filings."
)


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _ChatResponse(BaseModel):
    choices: list[_Choice]


class GrokClient:
    """Call the xAI chat completions endpoint."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    async def complete(self, *, ticker: str, question: str, headlines: list[str]) -> str:
        """Return the assistant text for one research question."""
        bullet_list = (
            "\n".join(f"- {headline}" for headline in headlines) or "- No headlines were available."
        )
        return await self.write(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=f"Ticker: {ticker}\nQuestion: {question}\nHeadlines:\n{bullet_list}",
        )

    async def write(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return assistant text for one role prompt. The key is not logged."""
        key = self._settings.grok_api_key.get_secret_value().strip()
        if not key:
            raise ConfigurationError("GROK_API_KEY is not configured")
        payload: dict[str, Any] = {
            "model": self._settings.grok_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        body = await request_json(
            self._http,
            "POST",
            f"{self._settings.grok_api_base_url.rstrip('/')}{GROK_CHAT_PATH}",
            settings=self._settings,
            provider="grok",
            headers={"Authorization": f"Bearer {key}"},
            json_body=payload,
            timeout_seconds=float(self._settings.grok_timeout_seconds),
        )
        return _answer_text(body)


def _answer_text(body: object) -> str:
    try:
        parsed = _ChatResponse.model_validate(body)
    except ValidationError as exc:
        raise InvalidResponseError("Grok response is invalid") from exc
    if not parsed.choices:
        raise InvalidResponseError("Grok response is empty")
    text = parsed.choices[0].message.content.strip()
    if not text:
        raise InvalidResponseError("Grok response is empty")
    return text
