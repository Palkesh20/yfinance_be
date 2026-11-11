"""Streamlit settings. This module does not import the backend package."""

from __future__ import annotations

import logging
import os


def api_base_url() -> str:
    """Return the FastAPI base URL."""
    return os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def configure_logging() -> None:
    """Install a simple console logger for the UI process."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
