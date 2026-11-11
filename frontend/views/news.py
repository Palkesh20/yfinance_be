"""News page with a Grok question against the fetched headlines."""

from __future__ import annotations

import streamlit as st

from api_client import ApiClient, ApiError
from ui import prepare

ticker = prepare()
st.title("News")
question = st.text_area("Question", value="What is the tone of the latest headlines?")
if st.button("Load news", type="primary"):
    client = ApiClient()
    try:
        feed, envelope = client.get_news(ticker)
    except ApiError as exc:
        st.error(exc.message)
    else:
        label = feed.sentiment_label or "n/a"
        st.caption(f"Sentiment {label}. Source {envelope.source}. Cached {envelope.cached}.")
        for item in feed.items:
            publisher = f" · {item.publisher}" if item.publisher else ""
            st.markdown(f"**[{item.headline}]({item.url})**")
            st.caption(f"{item.published_at}{publisher}")
        try:
            answer, research_envelope = client.research(ticker, question)
        except ApiError as exc:
            st.warning(exc.message)
        else:
            st.subheader("Grok")
            st.caption(f"Source {research_envelope.source}.")
            with st.container(border=True):
                st.write(answer.answer)
    finally:
        client.close()
