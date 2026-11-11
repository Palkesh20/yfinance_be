"""Logging setup for the API process.

The Streamlit app configures its own logger and does not import this module.

Dev writes a readable console line at DEBUG. Test stays at WARNING.
Prod writes JSON to the console and to a rotating file at INFO.
A context filter adds request id, provider, and ticker to every record.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from collections.abc import Mapping
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TextIO, cast

from finance_poc.core.config import Settings
from finance_poc.core.constants import (
    LIBRARY_LOGGERS,
    LOG_BACKUP_COUNT,
    LOG_FILE_NAME,
    LOG_MAX_BYTES,
)
from finance_poc.core.exceptions import ConfigurationError

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
provider_var: ContextVar[str | None] = ContextVar("provider", default=None)
ticker_var: ContextVar[str | None] = ContextVar("ticker", default=None)

_CONSOLE_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s %(funcName)s "
    "[request_id=%(request_id)s provider=%(provider)s ticker=%(ticker)s] %(message)s"
)
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


class _ContextLogRecord(logging.LogRecord):
    """Log record carrying the request context fields."""

    request_id: str
    provider: str
    ticker: str


class ContextFilter(logging.Filter):
    """Copy request context onto the log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context_record = cast(_ContextLogRecord, record)
        context_record.request_id = request_id_var.get() or "-"
        context_record.provider = provider_var.get() or "-"
        context_record.ticker = ticker_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line for the prod profile."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "provider": getattr(record, "provider", None),
            "ticker": getattr(record, "ticker", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=_json_default)


def _json_default(value: object) -> str:
    return str(value)


def reset_logging() -> None:
    """Close and remove root handlers so setup can run again in tests."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)
    for existing in list(root.filters):
        root.removeFilter(existing)


def _align_library_loggers(level: int) -> None:
    for name in LIBRARY_LOGGERS:
        lib_logger = logging.getLogger(name)
        for handler in list(lib_logger.handlers):
            handler.close()
            lib_logger.removeHandler(handler)
        lib_logger.propagate = True
        lib_logger.setLevel(level)


def setup_logging(settings: Settings, *, stream: TextIO | None = None) -> None:
    """Install the profile's handlers on the root logger."""
    reset_logging()
    level = logging.getLevelName(settings.log_level)
    if not isinstance(level, int):
        raise ConfigurationError("Invalid log level")

    root = logging.getLogger()
    root.setLevel(level)
    context = ContextFilter()
    root.addFilter(context)

    formatter: logging.Formatter
    if settings.log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(stream)
    console.setFormatter(formatter)
    console.addFilter(context)
    root.addHandler(console)

    if settings.app_env == "prod":
        try:
            settings.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigurationError("Cannot create log directory") from exc
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_dir / LOG_FILE_NAME,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context)
        root.addHandler(file_handler)

    _align_library_loggers(level)


def current_log_context() -> Mapping[str, str | None]:
    """Return the context values attached to the active task."""
    return {
        "request_id": request_id_var.get(),
        "provider": provider_var.get(),
        "ticker": ticker_var.get(),
    }
