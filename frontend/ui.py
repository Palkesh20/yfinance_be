"""Shared page chrome. This module does not import the backend package."""

from __future__ import annotations

import streamlit as st

PAGE_CSS = """
<style>
.block-container { padding-top: 1.6rem; max-width: 1080px; }
div[data-testid="stSidebar"] { border-right: 1px solid rgba(232, 238, 244, 0.08); }
div[data-testid="stMetric"] {
    background: #17202A;
    border: 1px solid rgba(232, 238, 244, 0.08);
    border-radius: 12px;
    padding: 0.75rem 1rem;
}
</style>
"""


def prepare() -> str:
    """Return the ticker from the sidebar. The entrypoint owns the page config."""
    st.sidebar.markdown("**Research desk**")
    st.sidebar.caption("Prices, filings, and a note on why the price moved.")
    st.sidebar.text_input("Ticker", value="AAPL", key="ticker")
    symbol = str(st.session_state.get("ticker", "AAPL")).strip().upper()
    return symbol or "AAPL"
