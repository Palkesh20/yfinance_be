"""Settings profiles, overrides, and prod fail-fast checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from finance_poc.core.config import get_settings, load_settings
from finance_poc.core.constants import (
    COMPANY_PROVIDERS,
    DEFAULT_LLM_PROVIDER,
    FILING_PROVIDERS,
    FINANCIAL_PROVIDERS,
    GROK_API_BASE_URL,
    GROK_MODEL,
    LOCAL_DATABASE_URL,
    NEWS_PROVIDERS,
    PRICE_PROVIDERS,
    QUOTE_PROVIDERS,
    TEST_DATABASE_URL,
    LlmProvider,
    Provider,
)
from finance_poc.core.exceptions import ConfigurationError

ROOT = Path(__file__).resolve().parents[3]


def test_provider_order_and_llm() -> None:
    assert PRICE_PROVIDERS == (Provider.YFINANCE, Provider.TWELVEDATA)
    assert QUOTE_PROVIDERS == (Provider.FINNHUB, Provider.YFINANCE)
    assert NEWS_PROVIDERS == (Provider.FINNHUB,)
    assert COMPANY_PROVIDERS == (Provider.YFINANCE, Provider.FINNHUB)
    assert FILING_PROVIDERS == (Provider.EDGAR,)
    assert FINANCIAL_PROVIDERS == (Provider.EDGAR,)
    assert DEFAULT_LLM_PROVIDER is LlmProvider.GROK


def test_test_profile_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = load_settings()

    assert settings.log_level == "WARNING"
    assert settings.log_format == "console"
    assert settings.database_url == TEST_DATABASE_URL
    assert settings.docs_enabled() is False


def test_dev_file_uses_local_postgres_and_grok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SETTINGS_ENV_FILE", str(ROOT / "config" / "dev.env.example"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GROK_MODEL", raising=False)
    monkeypatch.delenv("GROK_API_BASE_URL", raising=False)

    settings = load_settings()

    assert settings.database_url == LOCAL_DATABASE_URL
    assert "127.0.0.1" in settings.database_url
    assert settings.grok_model == GROK_MODEL
    assert settings.grok_api_base_url == GROK_API_BASE_URL
    assert settings.docs_enabled() is True
    assert settings.sec_user_agent() == "Example Services research@example.com"


def test_environment_overrides_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    override = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/override"
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SETTINGS_ENV_FILE", str(ROOT / "config" / "dev.env.example"))
    monkeypatch.setenv("DATABASE_URL", override)

    settings = load_settings()

    assert settings.database_url == override


def test_xai_api_key_alias_fills_grok_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "alias-key-value")

    settings = load_settings()

    assert settings.grok_api_key.get_secret_value() == "alias-key-value"
    assert "alias-key-value" not in repr(settings)


def test_grok_api_key_wins_over_xai_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("GROK_API_KEY", "primary-key-value")
    monkeypatch.setenv("XAI_API_KEY", "alias-key-value")

    settings = load_settings()

    assert settings.grok_api_key.get_secret_value() == "primary-key-value"


def test_prod_missing_grok_key_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("DATABASE_URL", LOCAL_DATABASE_URL)
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-should-not-leak")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "twelve-test")
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("SEC_COMPANY_NAME", "Example Services")
    monkeypatch.setenv("SEC_CONTACT_EMAIL", "research@example.com")

    with pytest.raises(ConfigurationError, match="GROK_API_KEY") as caught:
        load_settings()

    assert "finnhub-should-not-leak" not in str(caught.value)


def test_prod_with_required_values_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("DATABASE_URL", LOCAL_DATABASE_URL)
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-test")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "twelve-test")
    monkeypatch.setenv("GROK_API_KEY", "grok-test")
    monkeypatch.setenv("SEC_COMPANY_NAME", "Example Services")
    monkeypatch.setenv("SEC_CONTACT_EMAIL", "research@example.com")

    settings = load_settings()

    assert settings.app_env == "prod"
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.docs_enabled() is False
    assert settings.database_url == LOCAL_DATABASE_URL


def test_invalid_app_env_is_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")

    with pytest.raises(ConfigurationError, match="app_env") as caught:
        load_settings()

    assert "staging" not in str(caught.value)


def test_cors_origins_split_on_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:8501, http://127.0.0.1:8501")

    settings = load_settings()

    assert settings.cors_allowed_origins == [
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ]


def test_non_positive_ttl_is_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("CACHE_TTL_PRICES_SECONDS", "0")

    with pytest.raises(ConfigurationError, match="cache_ttl_prices_seconds"):
        load_settings()


def test_cors_json_list_and_ordered_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:8501", ""]')

    settings = load_settings()

    assert settings.cors_allowed_origins == ["http://localhost:8501"]

    monkeypatch.setenv("HTTP_RETRY_MIN_SECONDS", "10")
    monkeypatch.setenv("HTTP_RETRY_MAX_SECONDS", "1")
    with pytest.raises(ConfigurationError, match="HTTP_RETRY_MIN_SECONDS"):
        load_settings()


def test_unsupported_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("LOG_LEVEL", "verbose")

    with pytest.raises(ConfigurationError, match="log_level") as caught:
        load_settings()

    assert "verbose" not in str(caught.value)


def test_missing_settings_file_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETTINGS_ENV_FILE", "missing.env")

    with pytest.raises(ConfigurationError, match=r"missing\.env"):
        load_settings()


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
