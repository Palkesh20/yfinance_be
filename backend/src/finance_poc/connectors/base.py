"""Connector contract. Unsupported operations raise ConnectorError."""

from __future__ import annotations

from abc import ABC
from datetime import date

from finance_poc.core.constants import Capability
from finance_poc.core.exceptions import ConnectorError
from finance_poc.models.schemas import (
    CompanyProfile,
    Filing,
    FinancialStatementItem,
    NewsFeed,
    PriceBar,
    Quote,
)


class Connector(ABC):
    """Async provider client with a declared set of capabilities."""

    name: str
    capabilities: frozenset[Capability]

    def supports(self, capability: Capability) -> bool:
        """Return whether this provider implements the capability."""
        return capability in self.capabilities

    def _unsupported(self, capability: Capability) -> ConnectorError:
        return ConnectorError(f"{self.name} does not support {capability.value}")

    async def get_prices(
        self,
        ticker: str,
        start: date,
        end: date,
        interval: str,
    ) -> list[PriceBar]:
        """Return historical bars."""
        raise self._unsupported(Capability.PRICES)

    async def get_quote(self, ticker: str) -> Quote:
        """Return the latest quote."""
        raise self._unsupported(Capability.QUOTE)

    async def get_news(self, ticker: str, limit: int) -> NewsFeed:
        """Return recent headlines."""
        raise self._unsupported(Capability.NEWS)

    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        """Return company identity fields."""
        raise self._unsupported(Capability.COMPANY_PROFILE)

    async def get_filings(self, ticker: str, limit: int) -> list[Filing]:
        """Return recent filings."""
        raise self._unsupported(Capability.FILINGS)

    async def get_financials(self, ticker: str) -> list[FinancialStatementItem]:
        """Return statement line items."""
        raise self._unsupported(Capability.FINANCIALS)

    async def health_check(self) -> bool:
        """Return whether the provider is configured and importable."""
        return True
