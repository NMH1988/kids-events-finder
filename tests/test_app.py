"""Smoke tests of the Streamlit page with AppTest (no API key, no network)."""

from pathlib import Path

import pytest
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
    from types import SimpleNamespace

    import streamlit as st

    from views.chat import _budget_editor

    call = {
        "id": "b1",
        "args": {
            "budget_eur": 80,
            "items": [{"label": "Train", "amount_eur": 34}, {"label": "Zoo entry"}],
        },
    }
    settings = SimpleNamespace(
        trip={"budget_eur": 120, "adults": 2, "deutschlandticket_holders": 0}
    )
    st.session_state["edited"] = _budget_editor(call, settings)


def test_budget_editor_keeps_unknown_amounts_empty():
    """Empty amounts stay None; the budget comes from the trip settings, not the model."""
    at = AppTest.from_function(_budget_page, default_timeout=30).run()
    assert not at.exception
    edited = at.session_state["edited"]
    assert edited["budget_eur"] == 120.0
    assert edited["items"][0]["amount_eur"] == 34.0 and edited["items"][1]["amount_eur"] is None


def _calculations_page():
    """Render an answer's calculation box, attributions and AI label parts."""
    import streamlit as st

    from views.chat import AI_LABEL, _render_attributions, _render_calculations

    st.caption(AI_LABEL)
    message = {
        "tools": [{"name": "get_weather_forecast", "args": {}}],
        "calculations": {
            "compare_train_tickets": {
                "options": [
                    {"label": "One Bayern-Ticket", "total_eur": 44.0, "checked_on": "2026-11-19"}
                ],
                "warnings": [],
            },
            "check_budget": {
                "budget_eur": 100.0,
                "items": [{"label": "Train", "amount_eur": 44.0}, {"label": "Zoo"}],
                "known_total_eur": 44.0,
                "remaining_eur": 56.0,
                "unknown_items": ["Zoo"],
            },
        },
    }
    _render_calculations(message)
    _render_attributions(message)


def test_money_and_sources_are_shown_by_the_app():
    """Ticket and budget figures come from the tool results; the source credit is set in code."""
    at = AppTest.from_function(_calculations_page, default_timeout=30).run()
    assert not at.exception
    assert len(at.dataframe) == 2
    assert any("56.00 EUR left" in t.value and "Zoo" in t.value for t in at.text)
    assert any("Open-Meteo" in c.value for c in at.caption)
    assert any("AI-generated" in c.value for c in at.caption)


def test_privacy_warning_for_the_parents_own_text_in_the_approval_panel():
    """A reject reason or an edited budget note with health data is not sent."""
    from src.agent.runner import decision_problem

    assert decision_problem({"action": "reject", "feedback": "my son has asthma"}, [])
    edit = {"action": "edit", "tool_calls": [{"id": "1", "args": {"items": [{"label": "Arzt"}]}}]}
    assert decision_problem(edit, [])
    fine = {
        "action": "edit",
        "tool_calls": [
            {"id": "1", "args": {"city": "Halle (Saale)", "travel_date": "2026-11-21"}},
            {"id": "2", "args": {"depart_after": "08:30", "budget_eur": 80}},
        ],
    }
    assert decision_problem(fine, []) is None
    assert decision_problem({"action": "reject", "feedback": "only indoor places"}, []) is None


def _marker_page():
    """Render an answer's AI label and machine-readable marker as the chat does."""
    import streamlit as st

    from views.chat import AI_LABEL, AI_MARKER_HTML

    st.caption(AI_LABEL)
    st.html(AI_MARKER_HTML)


def test_every_answer_gets_the_machine_readable_ai_marker():
    """AI Act Art. 50: the hidden data-ai-generated element is sent to the page."""
    at = AppTest.from_function(_marker_page, default_timeout=30).run()
    assert not at.exception
    bodies = [h.proto.body for h in at.get("html")]
    assert any('data-ai-generated="true"' in b for b in bodies)


def _over_budget_page():
    """Render a budget check that is over budget."""
    from src.budget import BudgetItem, check_budget
    from views.chat import _render_calculations

    budget = check_budget(30, [BudgetItem(label="Train", amount_eur=40)])
    _render_calculations({"calculations": {"check_budget": budget}})


def test_over_budget_is_shown_as_over_budget():
    """A negative remainder reads "over budget", not "-10.00 EUR left"."""
    at = AppTest.from_function(_over_budget_page, default_timeout=30).run()
    assert any("10.00 EUR over budget" in t.value for t in at.text)


def _later_turn_page():
    """Render an answer that names a price without any calculation in that turn."""
    from views.chat import _render_calculations

    _render_calculations({"content": "The ticket is about 9 EUR.", "calculations": {}})


def test_amounts_without_a_calculation_get_a_warning():
    """Security finding 6: a model-written amount alone is marked as not calculated."""
    at = AppTest.from_function(_later_turn_page, default_timeout=30).run()
    assert any("not calculated by the app" in c.value for c in at.caption)


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


def _money_page(text: str):
    """Render an answer with an amount but no calculation."""
    from views.chat import _render_calculations

    _render_calculations({"content": text, "calculations": {}})


@pytest.mark.parametrize(
    "text",
    [
        "EUR44",
        "44EUR",
        "£12",
        "$15",
        "12 GBP",
        "15 USD",
        "kostet 44,-",
        "12 pounds",
        "15 dollars",
        "44 Pfund",
        "CHF 20",
        "44.- pro Person",
        "￡12",
    ],
)
def test_every_currency_spelling_gets_the_warning(text):
    """Security round 2: any money spelling without a calculation gets the caption."""
    at = AppTest.from_function(_money_page, args=(text,), default_timeout=30).run()
    assert any("not calculated by the app" in c.value for c in at.caption)


def _chat_page():
    """Render the chat with a fake key, so the input box is shown without any model."""
    from src import config
    from views.chat import render_chat
    from views.sidebar import Settings

    original = config.get_api_key
    config.get_api_key = lambda: "test-key"
    try:
        render_chat(
            Settings(
                country="DE",
                city="Berlin",
                children=("3-5",),
                model="openai/gpt-5-mini",
                multi_query=False,
                rerank=False,
                auto_approve=False,
                trip=None,
            )
        )
    finally:
        config.get_api_key = original


def test_blocked_chat_message_is_never_stored():
    """A message with health data is rejected before it reaches the conversation history."""
    at = AppTest.from_function(_chat_page, default_timeout=30).run()
    at.chat_input[0].set_value("My daughter has asthma, ideas?").run()
    assert not at.exception
    assert at.session_state["history"] == []
    assert any("not sent" in w.value for w in at.warning)
    assert not any("asthma" in w.value for w in at.warning)


@pytest.mark.parametrize("text", ["44,–", "50 Cent pro Kind", "50p", "20 Franken", "¥12"])
def test_more_money_spellings_get_the_warning(text):
    """Security round 4: more ways to write an amount get the caption."""
    at = AppTest.from_function(_money_page, args=(text,), default_timeout=30).run()
    assert any("not calculated by the app" in c.value for c in at.caption)


def test_class_ranges_are_no_money():
    """'1.-4. Klasse' is a school year range, not a price."""
    from views.chat import _MONEY

    assert not _MONEY.search("Für die 1.-4. Klasse")


@pytest.mark.parametrize("text", ["[1, 2]", '"Munich"', "null", "{broken", "42"])
def test_edit_box_applies_only_json_objects(text):
    """Code review round 4: anything but a JSON object is not applied as the edited arguments."""
    from views.chat import parse_edited_args

    assert parse_edited_args(text) is None
    assert parse_edited_args('{"city": "Munich"}') == {"city": "Munich"}


def test_bracket_hint_in_the_privacy_message():
    """A blocked 'Word (N)' gets a hint to write '3x' instead."""
    from src.privacy_check import explain, find_sensitive

    assert '"3x"' in explain(find_sensitive("Lena (5)"))


@pytest.mark.parametrize("text", ["Ausflüge in Franken", "Hartford, CT", "1080p video"])
def test_words_that_look_like_units_are_no_money(text):
    """Code review round 5: a region, a state or a video size is no amount."""
    from views.chat import _MONEY

    assert not _MONEY.search(text)


@pytest.mark.parametrize("text", ["￥500", "kostet 12,50 pro Person", "20 Franken"])
def test_yen_and_decimal_amounts_get_the_caption(text):
    """Security round 5: more amounts get the caption."""
    from views.chat import _MONEY

    assert _MONEY.search(text)
