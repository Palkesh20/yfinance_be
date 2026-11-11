"""Version 1 route collection."""

from __future__ import annotations

from fastapi import APIRouter

from finance_poc.api.v1 import analysis, companies, filings, news, prices, quotes, research

router = APIRouter()
router.include_router(prices.router)
router.include_router(quotes.router)
router.include_router(news.router)
router.include_router(filings.router)
router.include_router(companies.router)
router.include_router(research.router)
router.include_router(analysis.router)
