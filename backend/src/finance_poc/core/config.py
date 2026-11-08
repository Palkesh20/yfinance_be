"""Profile-aware settings.

``APP_ENV`` selects ``dev``, ``test``, or ``prod``. A ``config/<env>.env`` file
is loaded when present, otherwise the project ``.env``. Process environment
variables win over the file. ``SETTINGS_ENV_FILE`` overrides that lookup and
an empty value loads no file.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

from finance_poc.core.constants import (
    GROK_API_BASE_URL,
    GROK_MODEL,
    GROK_TIMEOUT_SECONDS,
    LOCAL_DATABASE_URL,
    TEST_DATABASE_URL,
)
from finance_poc.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

AppEnv = Literal["dev", "test", "prod"]
LogLevelName = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["console", "json"]

_PROFILE_LOG_LEVEL: dict[AppEnv, LogLevelName] = {
    "dev": "DEBUG",
    "test": "WARNING",
    "prod": "INFO",
}
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_PROD_SECRETS = (
    ("FINNHUB_API_KEY", "finnhub_api_key"),
    ("TWELVEDATA_API_KEY", "twelvedata_api_key"),
    ("GROK_API_KEY", "grok_api_key"),
)


def find_project_root() -> Path:
    """Return the directory that contains ``pyproject.toml``."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise ConfigurationError("Project root not found")


def resolve_env_file(app_env: str, *, root: Path | None = None) -> Path | None:
    """Pick the env file for this process, if one should be loaded."""
    override = os.environ.get("SETTINGS_ENV_FILE")
    if override is not None:
        if override.strip() == "":
            return None
        path = Path(override)
        if not path.is_file():
            raise ConfigurationError(f"Settings file not found: {path.name}")
        return path

    project_root = root or find_project_root()
    profile = project_root / "config" / f"{app_env}.env"
    if profile.is_file():
        return profile
    dotenv = project_root / ".env"
    if dotenv.is_file():
        return dotenv
    return None


class Settings(BaseSettings):
    """Runtime configuration. Secret fields stay masked in ``repr``."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnv = "dev"
    log_level: LogLevelName = "INFO"
    log_format: LogFormat = "console"
    log_dir: Path = Path("logs")

    database_url: str = ""

    cache_ttl_prices_seconds: int = Field(default=300, gt=0)
    cache_ttl_quotes_seconds: int = Field(default=30, gt=0)
    cache_ttl_news_seconds: int = Field(default=300, gt=0)
    cache_ttl_filings_seconds: int = Field(default=3600, gt=0)
    cache_ttl_company_seconds: int = Field(default=86400, gt=0)
    cache_ttl_financials_seconds: int = Field(default=86400, gt=0)

    finnhub_api_key: SecretStr = SecretStr("")
    twelvedata_api_key: SecretStr = SecretStr("")
    sec_company_name: str = ""
    sec_contact_email: str = ""

    grok_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("GROK_API_KEY", "XAI_API_KEY"),
    )
    grok_api_base_url: str = GROK_API_BASE_URL
    grok_model: str = GROK_MODEL
    grok_timeout_seconds: int = Field(default=GROK_TIMEOUT_SECONDS, gt=0)

    http_timeout_seconds: float = Field(default=15, gt=0)
    http_retry_attempts: int = Field(default=3, gt=0)
    http_retry_min_seconds: float = Field(default=0.5, gt=0)
    http_retry_max_seconds: float = Field(default=8, gt=0)

    rate_limit_finnhub_calls: int = Field(default=60, gt=0)
    rate_limit_finnhub_period_seconds: float = Field(default=60, gt=0)
    rate_limit_edgar_calls: int = Field(default=8, gt=0)
    rate_limit_edgar_period_seconds: float = Field(default=1, gt=0)
    rate_limit_twelvedata_calls: int = Field(default=8, gt=0)
    rate_limit_twelvedata_period_seconds: float = Field(default=60, gt=0)
    rate_limit_yfinance_calls: int = Field(default=2, gt=0)
    rate_limit_yfinance_period_seconds: float = Field(default=1, gt=0)

    circuit_breaker_failure_threshold: int = Field(default=3, gt=0)
    circuit_breaker_recovery_seconds: float = Field(default=30, gt=0)

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    api_base_url: str = "http://127.0.0.1:8000"

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized not in _LOG_LEVELS:
                raise ValueError("unsupported log level")
            return normalized
        return value

    @field_validator("log_format", mode="before")
    @classmethod
    def normalize_log_format(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if stripped == "":
            return []
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
                raise ValueError("CORS_ALLOWED_ORIGINS must be a list of strings")
            return [item.strip() for item in parsed if item.strip()]
        return [item.strip() for item in stripped.split(",") if item.strip()]

    @model_validator(mode="after")
    def apply_profile_defaults(self) -> Self:
        if "log_level" not in self.model_fields_set:
            self.log_level = _PROFILE_LOG_LEVEL[self.app_env]
        if "log_format" not in self.model_fields_set:
            self.log_format = "json" if self.app_env == "prod" else "console"
        if "database_url" not in self.model_fields_set or self.database_url.strip() == "":
            if self.app_env == "test":
                self.database_url = TEST_DATABASE_URL
            elif self.app_env == "dev":
                self.database_url = LOCAL_DATABASE_URL
        if self.http_retry_min_seconds > self.http_retry_max_seconds:
            raise ValueError("HTTP_RETRY_MIN_SECONDS exceeds HTTP_RETRY_MAX_SECONDS")
        return self

    def docs_enabled(self) -> bool:
        """Interactive API docs are available in the dev profile."""
        return self.app_env == "dev"

    def sec_user_agent(self) -> str:
        """SEC fair-access user agent built from the configured contact."""
        return f"{self.sec_company_name} {self.sec_contact_email}".strip()


def _validation_message(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err["loc"]) or "settings"
        parts.append(f"{loc}: {err['msg']}")
    return "Invalid configuration: " + ", ".join(parts)


def _require_prod(settings: Settings) -> None:
    if settings.app_env != "prod":
        return
    missing: list[str] = []
    if settings.database_url.strip() == "":
        missing.append("DATABASE_URL")
    for label, attr in _PROD_SECRETS:
        secret = getattr(settings, attr)
        if not isinstance(secret, SecretStr) or secret.get_secret_value().strip() == "":
            missing.append(label)
    if settings.sec_company_name.strip() == "":
        missing.append("SEC_COMPANY_NAME")
    if settings.sec_contact_email.strip() == "":
        missing.append("SEC_CONTACT_EMAIL")
    if missing:
        raise ConfigurationError("Missing required prod settings: " + ", ".join(missing))


def load_settings() -> Settings:
    """Load settings once for the current environment."""
    app_env = os.environ.get("APP_ENV", "dev")
    env_file = resolve_env_file(app_env)
    try:
        # pydantic-settings accepts _env_file at runtime; its stub omits the argument.
        settings = (
            Settings() if env_file is None else Settings(_env_file=env_file)  # type: ignore[call-arg]
        )
    except ValidationError as exc:
        raise ConfigurationError(_validation_message(exc)) from exc
    except SettingsError as exc:
        raise ConfigurationError("Invalid configuration file") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError("Invalid CORS_ALLOWED_ORIGINS JSON") from exc
    _require_prod(settings)
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    settings = load_settings()
    logger.info("configuration loaded for env=%s", settings.app_env)
    return settings
