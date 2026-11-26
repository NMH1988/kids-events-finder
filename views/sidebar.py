"""The sidebar: country and city, children's age groups, trip, memory and agent settings."""

from dataclasses import dataclass, field

import streamlit as st

from src import config, family
from views.memory import render_memory_settings

FLAGS = {"DE": "🇩🇪", "GB": "🇬🇧", "US": "🇺🇸"}
ALL_CITIES = "All cities"


@dataclass
class Settings:
    """Everything the parent chose in the sidebar."""

    country: str
    city: str | None
    model: str
    auto_approve: bool
    multi_query: bool
    rerank: bool
    # Age groups by position: index 0 is "Child 1". No names, no exact ages.
    children: tuple[str, ...] = field(default_factory=tuple)
    trip: dict | None = None
    # Long-term memory switch (T5.11); off by default.
    memory_on: bool = False


def _render_children() -> tuple[str, ...]:
    """Draw one age-group dropdown per child and return the chosen groups."""
    st.subheader("👧 Children")
    count = st.number_input(
        "Number of children", min_value=0, max_value=family.MAX_CHILDREN, value=1, key="child_count"
    )
    bands = tuple(
        st.selectbox(
            f"Child {i + 1}",
            family.AGE_BANDS,
            index=1,
            format_func=family.BAND_LABELS.get,
            key=f"child_band_{i}",
        )
        for i in range(int(count))
    )
    st.caption(
        "Only age groups are used, never names or exact ages. Please don't type names, health "
        "details or other personal information in the chat."
    )
    return bands


def _render_trip(country: str, children: tuple[str, ...]) -> dict | None:
    """Draw the budget day trip settings (Germany only) and return them, or None when off."""
    if country != "DE":
        return None
    with st.expander("💶 Budget day trip by train", expanded=False):
        on = st.toggle("Plan a day trip within a budget", key="trip_on")
        if not on:
            return None
        budget = st.number_input(
            "Budget for the whole family (EUR)",
            min_value=float(config.BUDGET_RANGE_EUR[0]),
            max_value=float(config.BUDGET_RANGE_EUR[1]),
            value=100.0,
            step=10.0,
            key="trip_budget",
        )
        adults = st.number_input(
            "Adults", *config.TRIP_TRAVELLERS_RANGE, value=2, key="trip_adults"
        )
        teens = sum(1 for b in children if b in family.ADULT_FARE_BANDS)
        holders = st.number_input(
            "How many travellers aged 15+ have a Deutschlandticket?",
            min_value=0,
            max_value=int(adults) + teens,
            value=0,
            key="trip_holders",
        )
        st.caption(
            "The children above travel too. Ticket prices come from the app's fare table; "
            "you fill in entry fees and food."
        )
    return {
        "budget_eur": float(budget),
        "adults": int(adults),
        "deutschlandticket_holders": int(holders),
    }


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
        children = _render_children()
        trip = _render_trip(country, children)
        memory_on = render_memory_settings()

        st.divider()
        st.header("🤖 Agent settings")
        model = st.selectbox("Model", config.ALLOWED_MODELS, key="model")
        auto_approve = st.toggle(
            "Auto-approve external tools",
            value=False,
            help="Off: you approve every call to an outside service (OpenStreetMap, "
            "Ticketmaster, Open-Meteo, Transitous) before it runs. This is the human-in-the-loop "
            "step. The budget check always waits for your prices, even when this is on.",
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
            # The chat view deletes this thread from server memory on the next run.
            st.session_state["delete_thread"] = st.session_state.get("thread_id")
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
        children=children,
        model=model,
        auto_approve=auto_approve,
        multi_query=multi_query,
        rerank=rerank,
        trip=trip,
        memory_on=memory_on,
    )
