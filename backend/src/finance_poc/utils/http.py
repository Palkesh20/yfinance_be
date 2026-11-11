"""HTTP calls with redaction, status mapping, and retries for transient failures."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from finance_poc.core.config import Settings
from finance_poc.core.exceptions import (
    AuthenticationError,
    DataNotFoundError,
    InvalidResponseError,
    ProviderUnavailableError,
    RateLimitExceededError,
)
from finance_poc.utils.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)

_SECRET_PARAMS = frozenset({"token", "apikey", "api_key", "api-key"})
_RETRYABLE = (
    httpx.TimeoutException,
    httpx.TransportError,
    ProviderUnavailableError,
    RateLimitExceededError,
)


def _retry_after(response: httpx.Response) -> int | None:
    raw = response.headers.get("Retry-After", "")
    if raw.isdigit():
        return int(raw)
    return None


def _raise_for_status(response: httpx.Response, provider: str) -> None:
    status = response.status_code
    if 200 <= status < 300:
        return
    if status in (401, 403):
        raise AuthenticationError(f"{provider} rejected the credentials")
    if status == 404:
        raise DataNotFoundError(f"{provider} has no data for this request")
    if status == 429:
        raise RateLimitExceededError(
            f"{provider} rate limit exceeded", retry_after=_retry_after(response)
        )
    if status >= 500:
        raise ProviderUnavailableError(f"{provider} returned status {status}")
    raise InvalidResponseError(f"{provider} returned status {status}")


def _redact_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    if params is None:
        return {}
    redacted: dict[str, Any] = {}
    for key, value in params.items():
        redacted[key] = "***" if key.lower() in _SECRET_PARAMS else value
    return redacted


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    settings: Settings,
    provider: str,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    json_body: Mapping[str, Any] | None = None,
    limiter: AsyncRateLimiter | None = None,
    timeout_seconds: float | None = None,
) -> Any:
    """Perform an HTTP request and return the decoded JSON body.

    Timeouts, transport errors, HTTP 429, and HTTP 5xx are retried.
    Authentication and other 4xx responses are not.
    """
    retrying = AsyncRetrying(
        stop=stop_after_attempt(settings.http_retry_attempts),
        wait=wait_exponential(
            multiplier=settings.http_retry_min_seconds,
            max=settings.http_retry_max_seconds,
        ),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    )
    async for attempt in retrying:
        with attempt:
            if limiter is not None:
                await limiter.acquire()
            logger.debug(
                "%s request method=%s params=%s",
                provider,
                method,
                _redact_params(params),
            )
            request_timeout = (
                settings.http_timeout_seconds if timeout_seconds is None else timeout_seconds
            )
            response = await client.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json_body,
                timeout=request_timeout,
            )
            logger.debug("%s response status=%s", provider, response.status_code)
            _raise_for_status(response, provider)
            try:
                return response.json()
            except ValueError as exc:
                raise InvalidResponseError(f"{provider} returned invalid JSON") from exc
    raise ProviderUnavailableError(f"{provider} request failed")
