"""The sidebar: country and city dropdowns, child's age, model and agent settings."""

from dataclasses import dataclass

import streamlit as st

from src import config

FLAGS = {"DE": "🇩🇪", "GB": "🇬🇧", "US": "🇺🇸"}
ALL_CITIES = "All cities"


@dataclass
class Settings:
    """Everything the parent chose in the sidebar."""

    country: str
    city: str | None
    child_age: int | None
    model: str
    auto_approve: bool
    multi_query: bool
    rerank: bool


def render_sidebar() -> Settings:
    """Draw the sidebar and return the chosen settings."""
    with st.sidebar:
        st.header("🔎 Where and who")
        country = st.selectbox(
            "Country",
            list(config.COUNTRIES),
            format_func=lambda c: f"{FLAGS[c]} {config.COUNTRIES[c]}",
            key="country",
        )
        city = st.selectbox("City", [ALL_CITIES, *config.CITIES[country]], key=f"city_{country}")
        add_age = st.checkbox("Filter by child's age", value=True)
        age = (
            st.slider("Child's age (years)", *config.CHILD_AGE_RANGE, value=5) if add_age else None
        )
        st.caption("Only the age is used. Please don't type names or other personal details.")

        st.divider()
        st.header("🤖 Agent settings")
        model = st.selectbox("Model", config.ALLOWED_MODELS, key="model")
        auto_approve = st.toggle(
            "Auto-approve external tools",
            value=False,
            help="Off: you approve every call to an outside service (OpenStreetMap, "
            "Ticketmaster, Open-Meteo) before it runs. This is the human-in-the-loop step.",
        )
        with st.expander("Advanced RAG"):
            multi_query = st.toggle(
                "Multi-query rewriting",
                value=True,
                help="An LLM rewrites your question into several English search queries.",
            )
            rerank = st.toggle(
                "LLM reranking", value=False, help="An LLM re-scores the top results (slower)."
            )
        if st.button("🧹 New conversation", use_container_width=True):
            for key in ("thread_id", "history", "pending", "feedback_saved"):
                st.session_state.pop(key, None)
            st.rerun()

        if not config.get_api_key():
            st.warning("No OpenRouter key: the chat is off. Browse still works.")
        if not config.get_secret(config.TICKETMASTER_KEY_NAME):
            st.caption("No Ticketmaster key: live event search is off.")
    return Settings(
        country=country,
        city=None if city == ALL_CITIES else city,
        child_age=age,
        model=model,
        auto_approve=auto_approve,
        multi_query=multi_query,
        rerank=rerank,
    )
