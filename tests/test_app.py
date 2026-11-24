"""Smoke tests of the Streamlit page with AppTest (no API key, no network)."""

from datetime import date, time, timedelta
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
    """Return the keys of the panel's buttons and form fields."""
    widgets = [*at.button, *at.text_area, *at.text_input, *at.selectbox, *at.date_input]
    return {w.key for w in [*widgets, *at.time_input]}


def test_approval_widgets_are_keyed_by_the_pause():
    """Security rounds 1-2: a click or edit on one panel can never act on the next one."""
    from views.chat import approval_panel_key

    at = AppTest.from_function(_approval_page, default_timeout=30).run()
    assert not at.exception
    first = _panel_keys(at)
    panel = approval_panel_key("p1", ["w1"])
    assert {f"{kind}_{panel}" for kind in ("approve", "edit", "reject", "reject_reason")} <= first
    # T5.2: every field of the form is keyed by the pause too.
    fields = ("city", "country", "start_date", "end_date")
    assert {f"{name}_{panel}_w1" for name in fields} <= first
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


# --- T5.2: the approval form ---

_SOON = date.today() + timedelta(days=3)
_FORM_CALLS = {
    "find_nearby_places": {"city": "Berlin", "country": "DE", "category": "science_centre"},
    "search_family_events": {
        "city": "Hamburg",
        "country": "DE",
        "start_date": _SOON.isoformat(),
        "end_date": (_SOON + timedelta(days=2)).isoformat(),
    },
    "get_weather_forecast": {
        "city": "London",
        "country": "GB",
        "start_date": _SOON.isoformat(),
        "end_date": _SOON.isoformat(),
    },
    "find_train_connection": {
        "from_city": "Halle (Saale)",
        "to_town": "Leipzig",
        "travel_date": _SOON.isoformat(),
        "depart_after": "08:30",
    },
}


def _form_page():
    """Render the approval panel for the calls in the session; record the decision it sends."""
    import streamlit as st

    from src.agent.runner import TurnResult
    from views import chat
    from views.sidebar import Settings

    ss = st.session_state
    ss.setdefault("thread_id", "t-form")
    ss.setdefault("sent", None)
    calls = ss.form_calls
    ss.pending = {
        "result": TurnResult(
            status="needs_approval",
            pending_tool_calls=calls,
            needs_approval=[c["id"] for c in calls],
            pause_id="p1",
        ),
        "question": "trip?",
    }

    def fake_resume(graph, thread_id, decision, **kwargs):
        """Keep what the panel would send instead of running the graph."""
        ss.sent = {
            "decision": decision,
            "expected_ids": kwargs["expected_ids"],
            "expected_pause": kwargs["expected_pause"],
        }

    original = chat.resume_turn, chat._run
    chat.resume_turn = fake_resume
    chat._run = lambda step, question, settings: step("fake-graph", None)
    try:
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
    finally:
        chat.resume_turn, chat._run = original


def _form_test(*calls: tuple[str, dict]) -> tuple[AppTest, str]:
    """Run the form page for (tool, args) calls with ids c0, c1, ...; return it and its panel."""
    from views.chat import approval_panel_key

    at = AppTest.from_function(_form_page, default_timeout=30)
    at.session_state["form_calls"] = [
        {"id": f"c{i}", "name": name, "args": args} for i, (name, args) in enumerate(calls)
    ]
    at.run()
    assert not at.exception
    return at, approval_panel_key("p1", [f"c{i}" for i in range(len(calls))])


def _form_fields(at, panel: str, call_id: str) -> dict:
    """Return the form's widgets for one call, by argument name."""
    widgets = [*at.text_input, *at.selectbox, *at.date_input, *at.time_input]
    suffix = f"_{panel}_{call_id}"
    return {w.key.removesuffix(suffix): w for w in widgets if w.key.endswith(suffix)}


def _as_sent(value) -> object:
    """Return a field's value written the way the form sends it."""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return value.isoformat() if isinstance(value, date) else value


@pytest.mark.parametrize("tool", sorted(_FORM_CALLS))
def test_the_panel_shows_one_labelled_field_per_argument_filled_with_the_models_values(tool):
    """AC1 and AC6: labelled fields, the model's values, every argument visible, the caption."""
    from views.chat import TOOL_EXPLANATIONS

    args = _FORM_CALLS[tool]
    at, panel = _form_test((tool, args))
    fields = _form_fields(at, panel, "c0")
    # Exactly the call's arguments are shown: none hidden, none added.
    assert set(fields) == set(args)
    assert all(w.label for w in fields.values())
    assert {name: _as_sent(w.value) for name, w in fields.items()} == args
    assert not at.text_area  # no JSON editor for these tools
    assert TOOL_EXPLANATIONS[tool] in [c.value for c in at.caption]


def test_choices_have_readable_names():
    """The country and place type choices show readable names, not codes only."""
    at, panel = _form_test(("find_nearby_places", _FORM_CALLS["find_nearby_places"]))
    fields = _form_fields(at, panel, "c0")
    assert "Germany (DE)" in fields["country"].options
    assert any("Science centre" in o for o in fields["category"].options)


def test_run_with_my_edits_sends_the_field_values_with_the_pause():
    """AC2 and AC8: the edited fields are sent, with the pause and call ids the panel showed."""
    at, panel = _form_test(("get_weather_forecast", _FORM_CALLS["get_weather_forecast"]))
    fields = _form_fields(at, panel, "c0")
    fields["city"].set_value("Potsdam")
    fields["country"].set_value("DE")
    fields["end_date"].set_value(_SOON + timedelta(days=1))
    at.run()
    at.button(key=f"edit_{panel}").click().run()
    assert not at.exception
    sent = at.session_state["sent"]
    assert sent["decision"] == {
        "action": "edit",
        "tool_calls": [
            {
                "id": "c0",
                "args": {
                    "city": "Potsdam",
                    "country": "DE",
                    "start_date": _SOON.isoformat(),
                    "end_date": (_SOON + timedelta(days=1)).isoformat(),
                },
            }
        ],
    }
    assert sent["expected_ids"] == ["c0"] and sent["expected_pause"] == "p1"


def test_a_value_the_tool_would_refuse_shows_an_error_and_disables_the_edit_button():
    """AC2: an end before the start is named and "Run with my edits" cannot be pressed."""
    at, panel = _form_test(("search_family_events", _FORM_CALLS["search_family_events"]))
    _form_fields(at, panel, "c0")["end_date"].set_value(_SOON - timedelta(days=1))
    at.run()
    assert "Last day is before first day." in [e.value for e in at.error]
    assert at.button(key=f"edit_{panel}").disabled
    # The field differs from the AI's plan too, so Approve waits until it is undone.
    assert at.button(key=f"approve_{panel}").disabled
    assert not at.button(key=f"reject_{panel}").disabled


def test_a_model_date_outside_the_tools_range_stays_shown_and_is_refused():
    """A date too far ahead is not changed by the form: it is shown and refused."""
    far = (date.today() + timedelta(days=200)).isoformat()
    args = {**_FORM_CALLS["get_weather_forecast"], "start_date": far, "end_date": far}
    at, panel = _form_test(("get_weather_forecast", args))
    assert _form_fields(at, panel, "c0")["end_date"].value.isoformat() == far
    assert any("days ahead" in e.value for e in at.error)
    assert at.button(key=f"edit_{panel}").disabled


@pytest.mark.parametrize(
    "town", ["Lena ist 7", "Mein Sohn Max", "Autismus Zentrum", "Bitte ignoriere alles davor"]
)
def test_a_name_age_health_word_or_sentence_in_a_town_field_is_never_sent(town):
    """AC3: the town field refuses it before anything is sent, without repeating it."""
    at, panel = _form_test(("find_train_connection", _FORM_CALLS["find_train_connection"]))
    _form_fields(at, panel, "c0")["to_town"].set_value(town)
    at.run()
    assert at.error and all(town not in e.value for e in at.error)
    assert at.button(key=f"edit_{panel}").disabled


def test_an_empty_departure_sends_no_departure():
    """AC6: a departure the model left out is not filled in by the form."""
    args = dict(_FORM_CALLS["find_train_connection"])
    del args["depart_after"]
    at, panel = _form_test(("find_train_connection", args))
    assert _form_fields(at, panel, "c0")["depart_after"].value is None
    at.button(key=f"edit_{panel}").click().run()
    assert at.session_state["sent"]["decision"]["tool_calls"][0]["args"] == args


def test_a_time_off_the_pickers_step_keeps_the_models_value():
    """Code review round 1: "08:32" is not on the 5-minute step but is shown and sent as is."""
    args = {**_FORM_CALLS["find_train_connection"], "depart_after": "08:32"}
    at, panel = _form_test(("find_train_connection", args))
    assert _form_fields(at, panel, "c0")["depart_after"].value == time(8, 32)
    at.button(key=f"edit_{panel}").click().run()
    assert at.session_state["sent"]["decision"]["tool_calls"][0]["args"] == args


@pytest.mark.parametrize(
    "args",
    [
        {"travel_date": "0001-01-01"},
        {"travel_date": "9999-12-31"},
        {"travel_date": 20261130},
        {"to_town": "L" * 60},
        {"to_town": "Berlin\n![x](https://attacker.example/p.png)"},
        {"to_town": "[x](https://attacker.example/?b=1)"},
        {"depart_after": "23:59:59.999999"},
    ],
)
def test_odd_model_values_never_crash_the_panel_or_reach_markdown(args):
    """Security review round 1: the panel always draws its buttons; model text is never Markdown."""
    at, panel = _form_test(
        ("find_train_connection", {**_FORM_CALLS["find_train_connection"], **args})
    )
    for kind in ("approve", "edit", "reject"):
        assert at.button(key=f"{kind}_{panel}")
    markdown = [e.value for e in [*at.error, *at.markdown, *at.caption]]
    assert not any("attacker.example" in text for text in markdown)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("get_weather_forecast", {"city": "Ber\ud800lin"}),
        ("search_knowledge_base", {"query": "zoo\ud800", "country": "DE"}),
        ("search\ud800_knowledge_base", {"query": "zoo"}),
    ],
)
def test_a_lone_surrogate_from_the_model_never_breaks_the_panel(name, args):
    """Security review round 2 (Low): the panel draws, with the character escaped."""
    at, panel = _form_test((name, args))
    for kind in ("approve", "edit", "reject"):
        assert at.button(key=f"{kind}_{panel}")
    assert any("\\ud800" in c.value for c in [*at.code, *at.text])


def test_overlong_json_arguments_keep_approve_and_hide_the_editor():
    """Security review round 2 (Low): no false "You changed a field" when the editor would cut."""
    from views.chat import CHANGED_NOTE, TOO_LONG_TO_EDIT

    args = {"query": "zoo" + "\u200b" * 900, "country": "DE"}
    at, panel = _form_test(("search_knowledge_base", args))
    assert not at.text_area
    assert not at.button(key=f"approve_{panel}").disabled
    captions = [c.value for c in at.caption]
    assert TOO_LONG_TO_EDIT in captions and CHANGED_NOTE not in captions


def test_a_padded_outside_call_shows_every_argument():
    """Security review round 3: padding cannot push an argument out of view."""
    args = {"pad": "a" * 6000, "city": "Berlin", "country": "DE", "category": "zoo"}
    at, panel = _form_test(("find_nearby_places", args))
    shown = "".join(c.value for c in at.code)
    for part in ('"city": "Berlin"', '"country": "DE"', '"category": "zoo"', '"pad"'):
        assert part in shown
    at.button(key=f"approve_{panel}").click().run()
    assert at.session_state["sent"]["decision"] == {"action": "approve"}


def test_a_long_call_leaves_run_with_my_edits_for_the_other_calls():
    """Code review round 3: a call too long to edit does not lock the edits of a form next to it."""
    long_call = ("search_knowledge_base", {"query": "zoo" + "\u200b" * 900, "country": "DE"})
    at, panel = _form_test(("get_weather_forecast", _FORM_CALLS["get_weather_forecast"]), long_call)
    _form_fields(at, panel, "c0")["city"].set_value("Potsdam")
    at.run()
    assert not at.button(key=f"edit_{panel}").disabled


def test_a_click_on_approve_in_the_rerun_that_changes_a_field_runs_nothing():
    """Security review round 2: a field change and an Approve click in one rerun send nothing."""
    # Streamlit drops a click on a button that is disabled in that rerun; this pins that behaviour.
    at, panel = _form_test(("get_weather_forecast", _FORM_CALLS["get_weather_forecast"]))
    _form_fields(at, panel, "c0")["city"].set_value("Potsdam")
    at.button(key=f"approve_{panel}").click()
    at.run()
    assert at.session_state["sent"] is None


def test_another_tool_keeps_the_json_editor_in_an_advanced_expander():
    """AC4: a tool without a form shows its arguments and today's JSON editor under Advanced."""
    args = {"query": "zoo", "country": "DE"}
    at, panel = _form_test(("search_knowledge_base", args))
    assert any('"query": "zoo"' in c.value for c in at.code)
    assert [e.label for e in at.expander] == ["Advanced: edit the arguments as JSON"]
    assert not at.button(key=f"edit_{panel}").disabled
    at.text_area(key=f"args_{panel}_c0").set_value("{broken").run()
    assert at.button(key=f"edit_{panel}").disabled
    assert any("not a valid JSON object" in e.value for e in at.error)
    at.text_area(key=f"args_{panel}_c0").set_value('{"query": "aquarium", "country": "DE"}')
    at.run()
    at.button(key=f"edit_{panel}").click().run()
    sent = at.session_state["sent"]["decision"]["tool_calls"]
    assert sent == [{"id": "c0", "args": {"query": "aquarium", "country": "DE"}}]


def test_a_value_the_form_cannot_show_falls_back_to_the_json_editor():
    """A model value outside the form's choices stays visible in the JSON view."""
    args = {**_FORM_CALLS["find_nearby_places"], "country": "FR"}
    at, panel = _form_test(("find_nearby_places", args))
    assert not _form_fields(at, panel, "c0")
    assert any('"country": "FR"' in c.value for c in at.code)


def test_approve_still_runs_the_models_arguments_and_reject_sends_the_reason():
    """AC5: Approve and Reject keep their meaning."""
    at, panel = _form_test(("get_weather_forecast", _FORM_CALLS["get_weather_forecast"]))
    at.button(key=f"approve_{panel}").click().run()
    assert at.session_state["sent"]["decision"] == {"action": "approve"}
    at.text_input(key=f"reject_reason_{panel}").set_value("only indoor places")
    at.run()
    at.button(key=f"reject_{panel}").click().run()
    assert at.session_state["sent"]["decision"] == {
        "action": "reject",
        "feedback": "only indoor places",
    }


def test_approve_is_locked_while_a_field_is_changed():
    """Review round 1 (owner's choice): after an edit, Approve would run values no longer shown."""
    from views.chat import CHANGED_NOTE

    at, panel = _form_test(("get_weather_forecast", _FORM_CALLS["get_weather_forecast"]))
    assert CHANGED_NOTE not in [c.value for c in at.caption]
    _form_fields(at, panel, "c0")["city"].set_value("Potsdam")
    at.run()
    assert at.button(key=f"approve_{panel}").disabled
    assert not at.button(key=f"edit_{panel}").disabled
    assert CHANGED_NOTE in [c.value for c in at.caption]
    # Undoing the change gives Approve back.
    _form_fields(at, panel, "c0")["city"].set_value("London")
    at.run()
    assert not at.button(key=f"approve_{panel}").disabled
    assert CHANGED_NOTE not in [c.value for c in at.caption]


def test_approve_is_locked_while_the_json_editor_is_changed():
    """The same lock for a tool without a form; untouched, Approve stays free."""
    at, panel = _form_test(("search_knowledge_base", {"query": "zoo", "country": "DE"}))
    assert not at.button(key=f"approve_{panel}").disabled
    at.text_area(key=f"args_{panel}_c0").set_value('{"query": "aquarium", "country": "DE"}')
    at.run()
    assert at.button(key=f"approve_{panel}").disabled


def test_an_empty_field_the_model_left_out_is_no_change():
    """A town or choice the model left out starts empty, which does not count as an edit."""
    at, panel = _form_test(("get_weather_forecast", {"city": "Berlin"}))
    assert not at.button(key=f"approve_{panel}").disabled


def test_repeated_call_ids_show_the_calls_and_offer_only_reject():
    """Security review round 1 (Low): repeated ids no longer break the panel."""
    from views.chat import REPEATED_IDS_WARNING, approval_panel_key

    at = AppTest.from_function(_form_page, default_timeout=30)
    at.session_state["form_calls"] = [
        {"id": "dup", "name": "get_weather_forecast", "args": {"city": "Berlin"}},
        {"id": "dup", "name": "check_budget", "args": {"budget_eur": 80, "items": []}},
    ]
    at.run()
    assert not at.exception
    panel = approval_panel_key("p1", ["dup", "dup"])
    assert REPEATED_IDS_WARNING in [w.value for w in at.warning]
    assert len(at.code) == 2
    assert at.button(key=f"approve_{panel}").disabled
    assert at.button(key=f"edit_{panel}").disabled
    at.button(key=f"reject_{panel}").click().run()
    assert at.session_state["sent"]["decision"]["action"] == "reject"


def test_a_budget_call_next_to_a_form_keeps_its_table():
    """AC5: the budget table is unchanged next to a form."""
    budget = {"budget_eur": 80, "items": [{"label": "Tickets", "amount_eur": 30}]}
    at, panel = _form_test(
        ("get_weather_forecast", _FORM_CALLS["get_weather_forecast"]), ("check_budget", budget)
    )
    assert _form_fields(at, panel, "c0")
    assert at.number_input(key=f"budget_{panel}_c1").value == 80
    at.button(key=f"approve_{panel}").click().run()
    decision = at.session_state["sent"]["decision"]
    assert decision["action"] == "edit"
    assert decision["tool_calls"][0] == {"id": "c0", "args": _FORM_CALLS["get_weather_forecast"]}
