"""Kids Outing Finder: Streamlit entry point; it only composes the page from views/."""

import streamlit as st

from views.about import render_about
from views.browse import render_browse
from views.chat import render_chat, start_cleaner
from views.sidebar import render_sidebar

st.set_page_config(page_title="Kids Outing Finder", page_icon="🎈", layout="wide")
start_cleaner()  # enforces the retention limits in the background (LEGAL_COMPLIANCE 2.7)
st.title("🎈 Kids Outing Finder")
st.caption(
    "Events and places for children in Germany, the UK and the USA, with links and directions. "
    "AI-generated suggestions: always check the official website before you go."
)

settings = render_sidebar()
chat_tab, browse_tab, about_tab = st.tabs(["💬 Chat agent", "🗂️ Browse places", "ℹ️ About"])
with chat_tab:
    render_chat(settings)
with browse_tab:
    render_browse(settings)
with about_tab:
    render_about()
