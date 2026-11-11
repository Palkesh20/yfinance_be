"""SEC EDGAR client for the ticker map, filings, and company facts."""

from __future__ import annotations

from typing import Any

import httpx

from finance_poc.connectors.base import Connector
from finance_poc.core.config import Settings
from finance_poc.core.constants import (
    EDGAR_ARCHIVES_URL,
    EDGAR_FACTS_URL,
    EDGAR_SUBMISSIONS_URL,
    EDGAR_TICKERS_URL,
    Capability,
    Provider,
)
from finance_poc.core.exceptions import DataNotFoundError, InvalidResponseError
from finance_poc.models.schemas import Filing, FinancialStatementItem, coerce_date, coerce_float
from finance_poc.utils.http import request_json
from finance_poc.utils.rate_limiter import AsyncRateLimiter

_CONCEPTS = (
    ("income", "Revenues", "Revenues"),
    ("income", "NetIncomeLoss", "Net income"),
    ("balance", "Assets", "Assets"),
    ("balance", "Liabilities", "Liabilities"),
    ("balance", "StockholdersEquity", "Stockholders' equity"),
    ("cashflow", "NetCashProvidedByUsedInOperatingActivities", "Operating cash flow"),
)


class EdgarClient(Connector):
    """Filings and annual statement facts from data.sec.gov."""

    name = Provider.EDGAR.value
    capabilities = frozenset({Capability.FILINGS, Capability.FINANCIALS})

    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        limiter: AsyncRateLimiter | None = None,
    ) -> None:
        self._http = http
        self._settings = settings
        self._limiter = limiter or AsyncRateLimiter(
            settings.rate_limit_edgar_calls,
            settings.rate_limit_edgar_period_seconds,
        )
        self._cik_by_ticker: dict[str, str] | None = None

    def _headers(self) -> dict[str, str]:
        user_agent = self._settings.sec_user_agent()
        if not user_agent:
            raise InvalidResponseError("SEC user agent is not configured")
        return {"User-Agent": user_agent, "Accept": "application/json"}

    async def _get(self, url: str) -> Any:
        return await request_json(
            self._http,
            "GET",
            url,
            settings=self._settings,
            provider=self.name,
            headers=self._headers(),
            limiter=self._limiter,
        )

    async def _cik(self, ticker: str) -> str:
        if self._cik_by_ticker is None:
            payload = await self._get(EDGAR_TICKERS_URL)
            self._cik_by_ticker = _parse_ticker_map(payload)
        cik = self._cik_by_ticker.get(ticker)
        if cik is None:
            raise DataNotFoundError(f"No CIK for {ticker}")
        return cik

    async def get_filings(self, ticker: str, limit: int) -> list[Filing]:
        cik = await self._cik(ticker)
        payload = await self._get(EDGAR_SUBMISSIONS_URL.format(cik=cik))
        if not isinstance(payload, dict):
            raise InvalidResponseError("SEC submissions payload is invalid")
        filings = payload.get("filings")
        recent = filings.get("recent") if isinstance(filings, dict) else None
        if not isinstance(recent, dict):
            raise InvalidResponseError("SEC submissions payload is invalid")
        forms = recent.get("form")
        dates = recent.get("filingDate")
        accessions = recent.get("accessionNumber")
        documents = recent.get("primaryDocument")
        if not (
            isinstance(forms, list)
            and isinstance(dates, list)
            and isinstance(accessions, list)
            and isinstance(documents, list)
        ):
            raise InvalidResponseError("SEC filings columns are invalid")
        rows: list[Filing] = []
        total = min(len(forms), len(dates), len(accessions), len(documents), limit)
        for index in range(total):
            accession = str(accessions[index])
            document = str(documents[index]) if documents[index] else None
            rows.append(
                Filing(
                    ticker=ticker,
                    form=str(forms[index]),
                    filed_at=coerce_date(dates[index], field_name="filed_at"),
                    accession_number=accession,
                    primary_document=document,
                    url=_archive_url(cik, accession, document),
                    source=self.name,
                )
            )
        if not rows:
            raise DataNotFoundError(f"No filings for {ticker}")
        return rows

    async def get_financials(self, ticker: str) -> list[FinancialStatementItem]:
        cik = await self._cik(ticker)
        payload = await self._get(EDGAR_FACTS_URL.format(cik=cik))
        if not isinstance(payload, dict):
            raise InvalidResponseError("SEC company facts payload is invalid")
        facts = payload.get("facts")
        gaap = facts.get("us-gaap") if isinstance(facts, dict) else None
        if not isinstance(gaap, dict):
            raise DataNotFoundError(f"No financials for {ticker}")
        items: list[FinancialStatementItem] = []
        for statement, concept, label in _CONCEPTS:
            concept_payload = gaap.get(concept)
            if not isinstance(concept_payload, dict):
                continue
            units = concept_payload.get("units")
            usd = units.get("USD") if isinstance(units, dict) else None
            if not isinstance(usd, list):
                continue
            for row in _latest_annual(usd):
                items.append(
                    FinancialStatementItem(
                        ticker=ticker,
                        statement=statement,
                        concept=concept,
                        label=str(concept_payload.get("label") or label),
                        value=coerce_float(row.get("val"), field_name="value"),
                        unit="USD",
                        period_end=coerce_date(row.get("end"), field_name="period_end"),
                        fiscal_year=row.get("fy") if isinstance(row.get("fy"), int) else None,
                        fiscal_period=str(row.get("fp")) if row.get("fp") else None,
                        source=self.name,
                    )
                )
        if not items:
            raise DataNotFoundError(f"No financials for {ticker}")
        return items

    async def health_check(self) -> bool:
        return bool(self._settings.sec_user_agent())


def _parse_ticker_map(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise InvalidResponseError("SEC ticker map is invalid")
    mapping: dict[str, str] = {}
    for item in payload.values():
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("ticker", "")).upper()
        cik = item.get("cik_str")
        if symbol and isinstance(cik, int):
            mapping[symbol] = f"{cik:010d}"
    if not mapping:
        raise InvalidResponseError("SEC ticker map is empty")
    return mapping


def _archive_url(cik: str, accession: str, document: str | None) -> str | None:
    if document is None:
        return None
    accession_path = accession.replace("-", "")
    return f"{EDGAR_ARCHIVES_URL}/{int(cik)}/{accession_path}/{document}"


def _latest_annual(rows: list[object]) -> list[dict[str, Any]]:
    annual = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("fp") == "FY"
        and row.get("end")
        and row.get("val") is not None
    ]
    annual.sort(key=lambda row: str(row.get("end")), reverse=True)
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in annual:
        end = str(row.get("end"))
        if end in seen:
            continue
        seen.add(end)
        chosen.append(row)
        if len(chosen) == 4:
            break
    return chosen
