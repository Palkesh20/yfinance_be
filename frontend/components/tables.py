"""Table helpers for Streamlit dataframes."""

from __future__ import annotations

from typing import Any


def select_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    """Keep a stable column order for display."""
    return [{column: row.get(column) for column in columns} for row in rows]
