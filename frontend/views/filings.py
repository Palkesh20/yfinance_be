"""SEC filings page."""

from __future__ import annotations

import streamlit as st

from api_client import ApiClient, ApiError
from ui import prepare

ticker = prepare()
st.title("Filings")
if st.button("Load filings", type="primary"):
    client = ApiClient()
    try:
        filings, envelope = client.get_filings(ticker)
    except ApiError as exc:
        st.error(exc.message)
    else:
        st.caption(f"Source {envelope.source}. Cached {envelope.cached}.")
        for filing in filings:
            label = f"**{filing.form}** · {filing.filed_at}"
            if filing.url:
                st.markdown(f"{label} · [document]({filing.url})")
            else:
                st.markdown(label)
            st.caption(filing.accession_number)
    finally:
        client.close()
