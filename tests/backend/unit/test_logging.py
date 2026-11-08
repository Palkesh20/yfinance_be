"""Log format, context fields, and secret redaction."""

from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path

import pytest

from finance_poc.core.config import load_settings
from finance_poc.core.constants import LOCAL_DATABASE_URL
from finance_poc.core.logging_config import (
    provider_var,
    request_id_var,
    reset_logging,
    setup_logging,
    ticker_var,
)


def _flush() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_console_line_includes_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "console")
    settings = load_settings()
    buffer = StringIO()
    request_token = request_id_var.set("req-123")
    provider_token = provider_var.set("finnhub")
    ticker_token = ticker_var.set("AAPL")
    try:
        setup_logging(settings, stream=buffer)
        logging.getLogger("finance_poc.sample").info("hello %s", "world")
        _flush()
        text = buffer.getvalue()
        assert "hello world" in text
        assert "req-123" in text
        assert "finnhub" in text
        assert "AAPL" in text
        assert "finance_poc.sample" in text
    finally:
        request_id_var.reset(request_token)
        provider_var.reset(provider_token)
        ticker_var.reset(ticker_token)
        reset_logging()


def test_warning_profile_drops_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("LOG_FORMAT", "console")
    settings = load_settings()
    buffer = StringIO()
    try:
        setup_logging(settings, stream=buffer)
        logger = logging.getLogger("finance_poc.sample")
        logger.debug("hidden detail")
        logger.warning("visible problem")
        _flush()
        text = buffer.getvalue()
        assert "hidden detail" not in text
        assert "visible problem" in text
    finally:
        reset_logging()


def test_prod_json_file_omits_secrets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SETTINGS_ENV_FILE", "")
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", LOCAL_DATABASE_URL)
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-test")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "twelve-test")
    monkeypatch.setenv("GROK_API_KEY", "grok-secret-value")
    monkeypatch.setenv("SEC_COMPANY_NAME", "Example Services")
    monkeypatch.setenv("SEC_CONTACT_EMAIL", "research@example.com")
    settings = load_settings()
    buffer = StringIO()
    try:
        setup_logging(settings, stream=buffer)
        logging.getLogger("finance_poc.sample").info("loaded %s", settings)
        _flush()
        console_line = buffer.getvalue().strip()
        file_line = (tmp_path / "finance_poc.log").read_text(encoding="utf-8").strip()
        payload = json.loads(console_line)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "finance_poc.sample"
        assert payload["function"] == "test_prod_json_file_omits_secrets"
        assert payload["message"].startswith("loaded")
        assert json.loads(file_line)["message"] == payload["message"]
        assert "grok-secret-value" not in console_line
        assert "grok-secret-value" not in file_line
        uvicorn_logger = logging.getLogger("uvicorn")
        assert uvicorn_logger.propagate is True
        assert uvicorn_logger.handlers == []
    finally:
        reset_logging()
