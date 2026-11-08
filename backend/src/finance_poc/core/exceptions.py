"""Project exception hierarchy.

Catch a specific error and wrap it with ``raise NewError(...) from exc``.
Log with ``logger.exception`` only at the boundary that handles the failure.
"""

from __future__ import annotations


class FinancePocError(Exception):
    """Base error for every failure this project raises."""

    code = "finance_poc_error"


class ConfigurationError(FinancePocError):
    """Settings are missing or invalid."""

    code = "configuration_error"


class ConnectorError(FinancePocError):
    """A provider call failed."""

    code = "connector_error"


class ProviderUnavailableError(ConnectorError):
    """The provider could not be reached or returned a server error."""

    code = "provider_unavailable"


class RateLimitExceededError(ConnectorError):
    """The provider rejected the call because the rate limit was exceeded."""

    code = "rate_limit_exceeded"

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class DataNotFoundError(ConnectorError):
    """The provider has no data for the requested identifier."""

    code = "data_not_found"


class InvalidResponseError(ConnectorError):
    """The provider returned a payload that failed validation."""

    code = "invalid_response"


class AuthenticationError(ConnectorError):
    """The provider rejected the credentials."""

    code = "authentication_error"


class StorageError(FinancePocError):
    """The database or cache failed."""

    code = "storage_error"


class AllProvidersFailedError(FinancePocError):
    """Every provider that supports the operation failed."""

    code = "all_providers_failed"

    def __init__(self, message: str, *, failures: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.failures = failures


class ValidationError(FinancePocError):
    """Caller input is invalid, such as a malformed ticker."""

    code = "validation_error"
