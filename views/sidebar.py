"""The sidebar: country and city dropdowns, child's age, model and agent settings."""

from dataclasses import dataclass

import streamlit as st

from src import config
from src.fares import parse_ages

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
    trip: dict | None = None


def _render_trip(country: str) -> dict | None:
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
            "Adults and teens (15+)", *config.TRIP_TRAVELLERS_RANGE, value=2, key="trip_adults"
        )
        ages_text = st.text_input(
            "Children's ages (0-14)", value="4, 8", key="trip_ages", help="Separate with commas."
        )
        holders = st.number_input(
            "How many of the adults have a Deutschlandticket?",
            min_value=0,
            max_value=int(adults),
            value=0,
            key="trip_holders",
        )
        try:
            ages = parse_ages(ages_text)
        except ValueError as exc:
            st.error(str(exc))
            return None
        st.caption("Ticket prices come from the app's fare table; you fill in entry fees and food.")
    return {
        "budget_eur": float(budget),
        "adults": int(adults),
        "children_ages": list(ages),
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
        add_age = st.checkbox("Filter by child's age", value=True)
        age = (
            st.slider("Child's age (years)", *config.CHILD_AGE_RANGE, value=5) if add_age else None
        )
        st.caption("Only the age is used. Please don't type names or other personal details.")
        trip = _render_trip(country)

        st.divider()
        st.header("🤖 Agent settings")
        model = st.selectbox("Model", config.ALLOWED_MODELS, key="model")
        auto_approve = st.toggle(
            "Auto-approve external tools",
            value=False,
            help="Off: you approve every call to an outside service (OpenStreetMap, "
            "Ticketmaster, Open-Meteo, Transitous) and fill in prices for the budget check "
            "before they run. This is the human-in-the-loop step.",
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
        trip=trip,
    )
