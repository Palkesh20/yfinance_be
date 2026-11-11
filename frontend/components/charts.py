"""Plotly charts for the Streamlit pages."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go


def price_chart(bars: list[dict[str, Any]], ticker: str) -> go.Figure:
    """Build a close-price line chart."""
    closes = [float(bar["close"]) for bar in bars]
    rose = bool(closes) and closes[-1] >= closes[0]
    figure = go.Figure(
        data=[
            go.Scatter(
                x=[bar["timestamp"] for bar in bars],
                y=closes,
                mode="lines",
                name=ticker,
                line={"color": "#3DDC97" if rose else "#FF6B6B", "width": 2},
            )
        ]
    )
    figure.update_layout(
        title=f"{ticker} close",
        margin={"l": 16, "r": 16, "t": 48, "b": 16},
        height=420,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#E8EEF4"},
        xaxis={"showgrid": False, "title": None},
        yaxis={"gridcolor": "rgba(232,238,244,0.08)", "title": None},
    )
    return figure
