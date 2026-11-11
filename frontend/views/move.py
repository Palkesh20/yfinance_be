"""Explain why a stock rose or fell over a chosen window."""

from __future__ import annotations

import streamlit as st

from api_client import ApiClient, ApiError
from ui import prepare

ticker = prepare()
st.title("Why it moved")
st.caption("Primary research, secondary research, then an analyst note.")

WINDOWS = {
    "Last day": "1d",
    "Last week": "1w",
    "Last month": "1m",
    "Last year": "1y",
}

window = st.pills("Window", list(WINDOWS), default="Last week", key="window")
selected = WINDOWS.get(str(window or "Last week"), "1w")
if st.button("Explain the move", type="primary"):
    client = ApiClient()
    try:
        note, envelope = client.explain_move(ticker, selected)
    except ApiError as exc:
        st.error(exc.message)
    else:
        name = note.company_name or note.ticker
        change_col, price_col, benchmark_col = st.columns(3)
        change_col.metric(note.period_label.capitalize(), f"{note.move.change_percent:+.2f}%")
        price_col.metric(
            name,
            f"{note.move.end_price:.2f}",
            delta=f"{note.move.start_price:.2f} start",
        )
        if note.benchmark_ticker and note.benchmark_change_percent is not None:
            benchmark_col.metric(note.benchmark_ticker, f"{note.benchmark_change_percent:+.2f}%")
        else:
            benchmark_col.metric("Benchmark", "n/a")
        st.caption(
            f"{note.move.window_start} to {note.move.window_end}. "
            f"High {note.move.high:.2f}, low {note.move.low:.2f}. Source {envelope.source}."
        )
        st.subheader("Analyst note")
        with st.container(border=True):
            st.write(note.note)
        primary_col, secondary_col = st.columns(2)
        with primary_col:
            st.markdown("**Primary research**")
            st.write(note.primary_research)
        with secondary_col:
            st.markdown("**Secondary research**")
            st.write(note.secondary_research)
        if note.evidence_gaps:
            st.warning("\n\n".join(note.evidence_gaps))
    finally:
        client.close()
