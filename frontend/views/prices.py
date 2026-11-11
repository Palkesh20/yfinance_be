"""Price history page."""

from __future__ import annotations

import streamlit as st

from api_client import ApiClient, ApiError
from components.charts import price_chart
from components.tables import select_columns
from ui import prepare

ticker = prepare()
st.title("Prices")
interval = st.segmented_control("Interval", ["1d", "1wk", "1h"], default="1d", key="interval")
if st.button("Load prices", type="primary"):
    client = ApiClient()
    try:
        bars, envelope = client.get_prices(ticker, interval=str(interval or "1d"))
    except ApiError as exc:
        st.error(exc.message)
    else:
        st.caption(f"Source {envelope.source}. Cached {envelope.cached}.")
        records = [bar.model_dump() for bar in bars]
        st.plotly_chart(price_chart(records, ticker), use_container_width=True)
        st.dataframe(
            select_columns(
                records, ["timestamp", "open", "high", "low", "close", "volume", "source"]
            ),
            use_container_width=True,
            hide_index=True,
        )
    finally:
        client.close()
