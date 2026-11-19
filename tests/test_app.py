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


def test_children_are_age_groups_and_trip_settings_are_germany_only():
    """Each child is "Child N" with an age group; a 15-17 child can hold a Deutschlandticket."""
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert at.sidebar.selectbox(key="child_band_0").value == "3-5"
    assert not any(t.key == "trip_ages" for t in at.sidebar.text_input)
    at.sidebar.number_input(key="child_count").set_value(2).run()
    at.sidebar.selectbox(key="child_band_1").set_value("15-17").run()
    assert at.sidebar.selectbox(key="child_band_1").label == "Child 2"
    at.sidebar.toggle(key="trip_on").set_value(True).run()
    assert at.sidebar.number_input(key="trip_budget").value == 100.0
    # Two adults plus the 15-17 child: up to three Deutschlandticket holders.
    assert at.sidebar.number_input(key="trip_holders").max == 3
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


def test_idle_conversations_are_deleted_from_server_memory(monkeypatch):
    """A thread idle longer than the retention limit is deleted from the checkpointer."""
    from views import chat

    deleted = []

    class FakeSaver:
        """Records which threads were deleted."""

        def delete_thread(self, thread_id):
            """Remember the deleted thread."""
            deleted.append(thread_id)

    activity = {"old": 0.0, "fresh": 10_000.0}
    monkeypatch.setattr(chat, "_thread_activity", lambda: activity)
    monkeypatch.setattr(chat, "_checkpointer", lambda: FakeSaver())
    now = 2 * 60 * 60 + 5_000.0
    chat._forget_old_threads(now=now)
    assert deleted == ["old"] and set(activity) == {"fresh"}


def test_new_conversation_deletes_the_thread_from_server_memory(monkeypatch):
    """Ending a conversation deletes it from the checkpointer, not only from the page."""
    from views import chat

    deleted = []

    class FakeSaver:
        """Records which threads were deleted."""

        def delete_thread(self, thread_id):
            """Remember the deleted thread."""
            deleted.append(thread_id)

    activity = {"t1": 1.0}
    monkeypatch.setattr(chat, "_thread_activity", lambda: activity)
    monkeypatch.setattr(chat, "_checkpointer", lambda: FakeSaver())
    chat.end_conversation("t1")
    chat.end_conversation(None)
    assert deleted == ["t1"] and activity == {}


def test_lowering_children_keeps_the_holders_field_valid():
    """Fewer 15-17 children lower the Deutschlandticket holders limit without an error."""
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.number_input(key="child_count").set_value(2).run()
    at.sidebar.selectbox(key="child_band_1").set_value("15-17").run()
    at.sidebar.toggle(key="trip_on").set_value(True).run()
    at.sidebar.number_input(key="trip_holders").set_value(3).run()
    at.sidebar.number_input(key="child_count").set_value(1).run()
    assert not at.exception
    holders = at.sidebar.number_input(key="trip_holders")
    assert holders.max == 2 and holders.value <= 2


def _details_page():
    """Render only an answer's details with a model-written tool name and arguments."""
    from views.chat import _render_details

    _render_details(
        {
            "tools": [{"name": "x` ![a](https://evil.example/p.png) `", "args": {"q": "`[b](c)`"}}],
            "grounding": {"verified": [], "removed": []},
            "tokens": (1, 1),
            "model": "m",
            "seconds": 0.1,
        }
    )


def test_tool_names_and_arguments_are_shown_as_plain_code():
    """Model-written tool text is shown as code, so no Markdown link or image is rendered."""
    at = AppTest.from_function(_details_page, default_timeout=30).run()
    assert not at.exception
    assert any("evil.example" in c.value for c in at.code)
    assert not any("evil.example" in m.value for m in at.markdown)
