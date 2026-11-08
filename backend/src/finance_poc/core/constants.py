"""Stable names shared by configuration and later provider code."""

from __future__ import annotations

from enum import StrEnum

APP_NAME = "finance-poc"

LOCAL_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/finance_poc"
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

GROK_API_BASE_URL = "https://api.x.ai/v1"
GROK_MODEL = "grok-4.7"
GROK_TIMEOUT_SECONDS = 60

LOG_FILE_NAME = "finance_poc.log"
LOG_MAX_BYTES = 5_000_000
LOG_BACKUP_COUNT = 5

LIBRARY_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")


class Provider(StrEnum):
    """External data providers."""

    YFINANCE = "yfinance"
    FINNHUB = "finnhub"
    EDGAR = "edgar"
    TWELVEDATA = "twelvedata"


class LlmProvider(StrEnum):
    """Model providers. Grok is the only one configured in this phase."""

    GROK = "grok"


class Capability(StrEnum):
    """Operations a connector may declare."""

    PRICES = "prices"
    QUOTE = "quote"
    NEWS = "news"
    COMPANY_PROFILE = "company_profile"
    FILINGS = "filings"
    FINANCIALS = "financials"


PRICE_PROVIDERS: tuple[Provider, ...] = (Provider.YFINANCE, Provider.TWELVEDATA)
QUOTE_PROVIDERS: tuple[Provider, ...] = (Provider.FINNHUB, Provider.YFINANCE)
NEWS_PROVIDERS: tuple[Provider, ...] = (Provider.FINNHUB,)
COMPANY_PROVIDERS: tuple[Provider, ...] = (Provider.YFINANCE, Provider.FINNHUB)
FILING_PROVIDERS: tuple[Provider, ...] = (Provider.EDGAR,)
FINANCIAL_PROVIDERS: tuple[Provider, ...] = (Provider.EDGAR,)

DEFAULT_LLM_PROVIDER = LlmProvider.GROK
