"""Map project exceptions to one JSON error shape."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from finance_poc.core.exceptions import (
    AllProvidersFailedError,
    AuthenticationError,
    ConfigurationError,
    DataNotFoundError,
    FinancePocError,
    ProviderUnavailableError,
    RateLimitExceededError,
    StorageError,
    ValidationError,
)
from finance_poc.core.logging_config import request_id_var

logger = logging.getLogger(__name__)


def _payload(code: str, message: str) -> dict[str, dict[str, str | None]]:
    return {"error": {"code": code, "message": message, "request_id": request_id_var.get()}}


def register_error_handlers(app: FastAPI) -> None:
    """Install the global exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            loc for err in exc.errors() if (loc := ".".join(str(item) for item in err["loc"]))
        ]
        logger.warning(
            "request validation failed path=%s fields=%s", request.url.path, ",".join(fields)
        )
        return JSONResponse(
            status_code=422,
            content=_payload("validation_error", "Invalid request: " + ", ".join(fields)),
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        logger.warning("validation failed path=%s", request.url.path)
        return JSONResponse(status_code=422, content=_payload(exc.code, str(exc)))

    @app.exception_handler(DataNotFoundError)
    async def not_found_handler(request: Request, exc: DataNotFoundError) -> JSONResponse:
        logger.warning("data not found path=%s", request.url.path)
        return JSONResponse(status_code=404, content=_payload(exc.code, str(exc)))

    @app.exception_handler(AuthenticationError)
    async def authentication_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        logger.error("provider authentication failed path=%s", request.url.path)
        return JSONResponse(
            status_code=502, content=_payload(exc.code, "Upstream provider rejected the request")
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(request: Request, exc: RateLimitExceededError) -> JSONResponse:
        logger.warning("rate limit path=%s", request.url.path)
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        return JSONResponse(status_code=429, content=_payload(exc.code, str(exc)), headers=headers)

    @app.exception_handler(ProviderUnavailableError)
    async def provider_handler(request: Request, exc: ProviderUnavailableError) -> JSONResponse:
        logger.error("provider unavailable path=%s", request.url.path)
        return JSONResponse(status_code=503, content=_payload(exc.code, str(exc)))

    @app.exception_handler(AllProvidersFailedError)
    async def all_failed_handler(request: Request, exc: AllProvidersFailedError) -> JSONResponse:
        logger.error("all providers failed path=%s", request.url.path)
        return JSONResponse(status_code=503, content=_payload(exc.code, str(exc)))

    @app.exception_handler(ConfigurationError)
    async def configuration_handler(request: Request, exc: ConfigurationError) -> JSONResponse:
        logger.error("configuration error path=%s", request.url.path)
        return JSONResponse(status_code=503, content=_payload(exc.code, str(exc)))

    @app.exception_handler(StorageError)
    async def storage_handler(request: Request, exc: StorageError) -> JSONResponse:
        logger.exception("storage failure path=%s", request.url.path)
        return JSONResponse(
            status_code=500, content=_payload(exc.code, "The data store is unavailable")
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error path=%s", request.url.path)
        return JSONResponse(
            status_code=500, content=_payload("internal_error", "An unexpected error occurred")
        )

    @app.exception_handler(FinancePocError)
    async def finance_handler(request: Request, exc: FinancePocError) -> JSONResponse:
        logger.error("request failed path=%s code=%s", request.url.path, exc.code)
        return JSONResponse(status_code=500, content=_payload(exc.code, str(exc)))
