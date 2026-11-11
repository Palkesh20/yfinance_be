"""Request id and access logging."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from finance_poc.core.logging_config import provider_var, request_id_var, ticker_var

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id, emit an access line, and clear task context."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request_token = request_id_var.set(request_id)
        provider_token = provider_var.set(None)
        ticker_token = ticker_var.set(None)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "%s %s %s %.1f",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - started) * 1000,
            )
            return response
        finally:
            request_id_var.reset(request_token)
            provider_var.reset(provider_token)
            ticker_var.reset(ticker_token)
