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


@pytest.mark.parametrize(
    "text",
    ["￥500", "kostet 12,50 pro Person", "20 Franken", "500 yen", "50 Rappen", "₹200", "₩5000"],
)
def test_yen_and_decimal_amounts_get_the_caption(text):
    """Security round 5: more amounts get the caption."""
    from views.chat import _MONEY

    assert _MONEY.search(text)


def _progress_page():
    """Write progress labels into the chat's status box, with one repeated label."""
    import streamlit as st

    from views.chat import PROGRESS_TITLE, ProgressWriter

    with st.status(PROGRESS_TITLE, expanded=True) as status:
        report = ProgressWriter(status.text)
        labels = ("Thinking about your question", "Checking the weather", "Checking the weather")
        for label in labels:
            report(label)


def test_progress_box_shows_each_step_once_as_plain_text():
    """T5.1: the status box lists the fixed labels as plain text, a repeat only once."""
    at = AppTest.from_function(_progress_page, default_timeout=30).run()
    assert not at.exception
    assert [t.value for t in at.text] == ["Thinking about your question", "Checking the weather"]
    assert not at.markdown


def test_a_rerun_request_during_a_write_is_kept_not_raised():
    """Code review round 1: a page rerun or stop asked for mid-turn never cuts the graph run."""
    from streamlit.runtime.scriptrunner_utils.exceptions import StopException

    from views.chat import ProgressWriter

    written: list[str] = []

    def write(label: str) -> None:
        """Write a label; the second write meets a waiting stop request."""
        if written:
            raise StopException()
        written.append(label)

    report = ProgressWriter(write)
    report("one")
    report("two")  # raises inside write, kept instead of raised
    report("three")  # nothing more is written once a request is waiting
    assert written == ["one"]
    assert isinstance(report.deferred, StopException)


def _run_page(kind: str):
    """Call the chat's _run once with a fake graph; st.rerun only records that it was called."""
    import streamlit as st
    from streamlit.runtime.scriptrunner_utils.exceptions import StopException

    from src.agent.runner import TurnResult
    from views import chat
    from views.sidebar import Settings

    ss = st.session_state
    ss.history, ss.pending, ss.reruns = [], None, 0

    def step(graph, progress):
        """Record what _run passed, report two steps and finish as asked."""
        ss.step_args = (graph, callable(progress))
        progress("Thinking about your question")
        progress("Checking the links in the answer")
        if kind == "deferred":
            progress.deferred = StopException()  # as if the parent clicked during the turn
        if kind == "approval":
            return TurnResult(status="needs_approval", pending_tool_calls=[{"id": "w1"}])
        return TurnResult(status="done", answer="Fine.")

    def fake_rerun(*args, **kwargs):
        """Count the rerun instead of starting one."""
        ss.reruns += 1

    settings = Settings(
        country="DE",
        city="Berlin",
        model="openai/gpt-5-mini",
        auto_approve=False,
        multi_query=False,
        rerank=False,
    )
    original_graph, original_rerun = chat._graph, chat.st.rerun
    chat._graph = lambda *args: "fake-graph"
    chat.st.rerun = fake_rerun
    try:
        chat._run(step, "zoo?", settings)
    finally:
        chat._graph, chat.st.rerun = original_graph, original_rerun


def test_run_shows_the_steps_stores_the_answer_and_closes_the_box():
    """T5.1: _run passes a callback, shows its labels, keeps the answer and marks the box done."""
    from views.chat import PROGRESS_DONE

    at = AppTest.from_function(_run_page, args=("done",), default_timeout=30).run()
    assert not at.exception
    assert at.session_state["step_args"] == ("fake-graph", True)
    assert [t.value for t in at.text] == [
        "Thinking about your question",
        "Checking the links in the answer",
    ]
    assert [s.label for s in at.status] == [PROGRESS_DONE]
    assert [m["content"] for m in at.session_state["history"]] == ["Fine."]
    assert at.session_state["reruns"] == 1


def test_run_keeps_the_approval_and_closes_the_box():
    """T5.1: a paused turn is kept as pending and the box is closed before the panel shows."""
    from views.chat import PROGRESS_DONE

    at = AppTest.from_function(_run_page, args=("approval",), default_timeout=30).run()
    assert not at.exception
    assert at.session_state["pending"]["question"] == "zoo?"
    assert at.session_state["history"] == []
    assert [s.label for s in at.status] == [PROGRESS_DONE]


def test_run_stores_the_turn_before_a_waiting_rerun_is_raised():
    """Code review round 1: a request kept during the turn is raised only after storing it."""
    at = AppTest.from_function(_run_page, args=("deferred",), default_timeout=30).run()
    assert not at.exception
    assert [m["content"] for m in at.session_state["history"]] == ["Fine."]
    assert at.session_state["reruns"] == 0  # the kept request runs instead of a new rerun


def test_every_tool_has_its_own_progress_label():
    """A new tool must get a label, not the generic "Using a tool"."""
    from src import config
    from src.rag.retriever import AdvancedRetriever
    from src.tools.registry import build_tools

    names = {t.name for t in build_tools(AdvancedRetriever(None))}
    assert names == set(config.PROGRESS_TOOL_LABELS)


def _approval_page():
    """Render the approval panel for the pause and calls held in the session state."""
    import streamlit as st

    from src.agent.runner import TurnResult
    from views import chat
    from views.sidebar import Settings

    ss = st.session_state
    ss.setdefault("thread_id", "t-panel")
    ids = ss.get("panel_ids", ["w1"])
    calls = [{"id": i, "name": "get_weather_forecast", "args": {"city": "Berlin"}} for i in ids]
    ss.pending = {
        "result": TurnResult(
            status="needs_approval",
            pending_tool_calls=calls,
            needs_approval=ids,
            pause_id=ss.get("pause_id", "p1"),
        ),
        "question": "weather?",
    }
    chat._render_approval(
        Settings(
            country="DE",
            city="Berlin",
            model="openai/gpt-5-mini",
            auto_approve=False,
            multi_query=False,
            rerank=False,
        )
    )


def _panel_keys(at) -> set[str]:
    """Return the keys of the panel's buttons and text fields."""
    return {w.key for w in [*at.button, *at.text_area, *at.text_input]}


def test_approval_widgets_are_keyed_by_the_pause():
    """Security rounds 1-2: a click or edit on one panel can never act on the next one."""
    from views.chat import approval_panel_key

    at = AppTest.from_function(_approval_page, default_timeout=30).run()
    assert not at.exception
    first = _panel_keys(at)
    panel = approval_panel_key("p1", ["w1"])
    assert {f"{kind}_{panel}" for kind in ("approve", "edit", "reject", "reject_reason")} <= first
    assert f"args_{panel}_w1" in first
    # The next pause reuses the model's call id (round 2, Low): the pause id still tells it apart.
    at.session_state["pause_id"] = "p2"
    at.run()
    second = _panel_keys(at)
    assert not first & second
    at.session_state["panel_ids"] = ["e1"]
    at.run()
    assert not second & _panel_keys(at)


def _stale_run_page(current_status: str | None):
    """Let _run meet a stale decision; the conversation waits on e1 now, or on nothing."""
    import streamlit as st

    from src.agent.runner import StaleDecision, TurnResult
    from views import chat
    from views.sidebar import Settings

    ss = st.session_state
    ss.history, ss.reruns = [], 0
    ss.pending = {"result": TurnResult(status="needs_approval"), "question": "weather?"}
    current = None
    if current_status:
        current = TurnResult(
            status=current_status,
            pending_tool_calls=[{"id": "e1", "name": "search_family_events", "args": {}}],
            pause_id="p2",
        )

    def step(graph, progress):
        """Refuse the decision like resume_turn does for a pause it no longer waits on."""
        raise StaleDecision("The steps changed or ended while you were deciding.", current)

    def fake_rerun(*args, **kwargs):
        """Count the rerun instead of starting one."""
        ss.reruns += 1

    original, original_rerun = chat._graph, chat.st.rerun
    chat._graph = lambda *args: "fake-graph"
    chat.st.rerun = fake_rerun
    try:
        chat._run(
            step,
            "weather?",
            Settings(
                country="DE",
                city="Berlin",
                model="openai/gpt-5-mini",
                auto_approve=False,
                multi_query=False,
                rerank=False,
            ),
        )
    finally:
        chat._graph, chat.st.rerun = original, original_rerun


def test_a_stale_decision_shows_the_pause_the_conversation_waits_on():
    """Security round 2 (Low): the panel is reloaded from the thread, not just cleared."""
    at = AppTest.from_function(_stale_run_page, args=("needs_approval",), default_timeout=30)
    at.run()
    assert not at.exception
    assert at.session_state["pending"]["result"].pause_id == "p2"
    # The page redraws at once and shows the warning after the rerun (code review round 3).
    assert at.session_state["reruns"] == 1
    assert "changed or ended" in at.session_state["stale_warning"]


def test_a_stale_panel_is_cleared_when_nothing_waits():
    """Security round 1 (Medium): with no pause left, the old panel goes away with a warning."""
    at = AppTest.from_function(_stale_run_page, args=(None,), default_timeout=30).run()
    assert not at.exception
    assert at.session_state["pending"] is None
    assert at.session_state["reruns"] == 1
    assert "changed or ended" in at.session_state["stale_warning"]


def test_the_chat_shows_a_kept_stale_warning_once():
    """After the rerun, the chat shows the stale-decision warning one time."""
    at = AppTest.from_function(_chat_page, default_timeout=30)
    at.session_state["stale_warning"] = "The steps changed or ended while you were deciding."
    at.run()
    assert not at.exception
    assert [w.value for w in at.warning].count(
        "The steps changed or ended while you were deciding."
    ) == 1
    at.run()
    assert not any("changed or ended" in w.value for w in at.warning)
