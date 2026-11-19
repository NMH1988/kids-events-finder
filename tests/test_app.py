"""Smoke tests of the Streamlit page with AppTest (no API key, no network)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_runs_without_key_and_browse_shows_places():
    """Without a key the page renders, the chat explains what is missing, Browse has cards."""
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("OPENROUTER_API_KEY" in i.value for i in at.info)
    assert any("places · opening times" in c.value for c in at.caption)


def test_changing_country_changes_city_list():
    """Choosing the United States offers US cities in the city dropdown."""
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.selectbox(key="country").set_value("US").run()
    city_box = at.sidebar.selectbox(key="city_US")
    assert "Chicago" in city_box.options


def test_trip_settings_are_offered_in_germany_and_validate_ages():
    """The budget trip settings appear for Germany only and reject a 15+ child's age."""
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.toggle(key="trip_on").set_value(True).run()
    assert at.sidebar.number_input(key="trip_budget").value == 100.0
    at.sidebar.text_input(key="trip_ages").set_value("4, 20").run()
    assert any("15+ count as adults" in e.value for e in at.sidebar.error)
    at.sidebar.text_input(key="trip_ages").set_value("4, 8").run()
    assert not at.sidebar.error
    at.sidebar.selectbox(key="country").set_value("GB").run()
    assert not [t for t in at.sidebar.toggle if t.key == "trip_on"]


def _budget_page():
    """Render only the budget editor of the approval panel and keep its result."""
    import streamlit as st

    from views.chat import _budget_editor

    call = {
        "id": "b1",
        "args": {
            "budget_eur": 80,
            "items": [{"label": "Train", "amount_eur": 34}, {"label": "Zoo entry"}],
        },
    }
    st.session_state["edited"] = _budget_editor(call)


def test_budget_editor_keeps_unknown_amounts_empty():
    """The parent sees the agent's items; empty amounts stay None instead of a guess."""
    at = AppTest.from_function(_budget_page, default_timeout=30).run()
    assert not at.exception
    edited = at.session_state["edited"]
    assert edited["budget_eur"] == 80.0
    assert edited["items"][0]["amount_eur"] == 34.0 and edited["items"][1]["amount_eur"] is None
