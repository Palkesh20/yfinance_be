"""Research desk. All data comes from the FastAPI service."""

from __future__ import annotations

import streamlit as st

from config import configure_logging
from ui import PAGE_CSS

configure_logging()
st.set_page_config(page_title="Research desk", layout="wide", initial_sidebar_state="expanded")
st.markdown(PAGE_CSS, unsafe_allow_html=True)

navigation = st.navigation(
    [
        st.Page("views/move.py", title="Why it moved", default=True),
        st.Page("views/prices.py", title="Prices"),
        st.Page("views/news.py", title="News"),
        st.Page("views/filings.py", title="Filings"),
    ]
)
navigation.run()
