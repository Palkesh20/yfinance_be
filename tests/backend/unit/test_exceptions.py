"""Exception hierarchy and cause chaining."""

from __future__ import annotations

from finance_poc.core.exceptions import (
    AllProvidersFailedError,
    AuthenticationError,
    ConfigurationError,
    ConnectorError,
    DataNotFoundError,
    FinancePocError,
    InvalidResponseError,
    ProviderUnavailableError,
    RateLimitExceededError,
    StorageError,
    ValidationError,
)


def test_connector_errors_share_the_base_type() -> None:
    errors = (
        ProviderUnavailableError("down"),
        RateLimitExceededError("slow", retry_after=12),
        DataNotFoundError("missing"),
        InvalidResponseError("bad payload"),
        AuthenticationError("rejected"),
    )
    for error in errors:
        assert isinstance(error, ConnectorError)
        assert isinstance(error, FinancePocError)
        assert error.code


def test_rate_limit_keeps_retry_after() -> None:
    error = RateLimitExceededError("slow", retry_after=12)
    assert error.retry_after == 12
    assert error.code == "rate_limit_exceeded"


def test_all_providers_failed_keeps_failures() -> None:
    error = AllProvidersFailedError("none responded", failures=("yfinance", "twelvedata"))
    assert error.failures == ("yfinance", "twelvedata")
    assert isinstance(error, FinancePocError)
    assert error.code == "all_providers_failed"


def test_project_validation_error_is_not_a_connector_error() -> None:
    error = ValidationError("bad ticker")
    assert isinstance(error, FinancePocError)
    assert not isinstance(error, ConnectorError)
    assert error.code == "validation_error"
    assert ValidationError.__module__ == "finance_poc.core.exceptions"


def test_storage_and_configuration_codes() -> None:
    assert ConfigurationError.code == "configuration_error"
    assert StorageError.code == "storage_error"


def test_provider_error_preserves_the_cause() -> None:
    try:
        try:
            raise TimeoutError("timed out")
        except TimeoutError as exc:
            raise ProviderUnavailableError("provider down") from exc
    except ProviderUnavailableError as error:
        assert isinstance(error.__cause__, TimeoutError)
