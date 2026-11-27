"""Tests for the agent graph: human-in-the-loop approve, edit, reject, auto-approve, grounding."""

import json
import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from src import config
from src.agent.graph import build_graph, system_prompt
from src.agent.runner import (
    InputRejected,
    StaleDecision,
    check_input,
    decision_problem,
    resume_turn,
    start_turn,
)
from tests.fakes import ScriptedChatModel

CONTEXT = {"country": "DE", "city": "Berlin", "children": ["3-5"]}


def _call(name: str, args: dict, call_id: str) -> AIMessage:
    """Build a model message that calls one tool."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


@pytest.fixture
def calls():
    """Record every tool run as (name, args)."""
    return []


@pytest.fixture
def tools(calls):
    """Two fake tools: an internal knowledge base search and an external weather call."""

    def search_knowledge_base(query: str) -> str:
        """Fake internal search."""
        calls.append(("search_knowledge_base", {"query": query}))
        return json.dumps({"results": [{"name": "Zoo Berlin", "website": "https://zoo.example"}]})

    def get_weather_forecast(city: str) -> str:
        """Fake external weather tool."""
        calls.append(("get_weather_forecast", {"city": city}))
        return json.dumps({"days": [{"summary": "rain"}]})

    return [
        StructuredTool.from_function(search_knowledge_base),
        StructuredTool.from_function(get_weather_forecast),
    ]


def _graph(responses, tools):
    """Compile the agent graph around a scripted model."""
    model = ScriptedChatModel(responses=responses)
    return build_graph(model, tools, InMemorySaver()), model


def test_internal_tool_runs_without_asking(tools, calls):
    """The knowledge base search stays in the app, so no approval is needed."""
    graph, _ = _graph(
        [
            _call("search_knowledge_base", {"query": "zoo"}, "c1"),
            AIMessage("[Zoo](https://zoo.example)"),
        ],
        tools,
    )
    result = start_turn(graph, "t1", "zoo?", **CONTEXT)
    assert result.status == "done"
    assert calls == [("search_knowledge_base", {"query": "zoo"})]
    assert result.grounding == {"verified": ["https://zoo.example"], "removed": []}


def test_external_tool_pauses_and_runs_after_approval(tools, calls):
    """An external call waits for the parent; approving runs it and finishes the turn."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("It will rain.")],
        tools,
    )
    paused = start_turn(graph, "t2", "weather?", **CONTEXT)
    assert paused.status == "needs_approval"
    assert paused.needs_approval == ["w1"]
    assert paused.pending_tool_calls[0]["args"] == {"city": "Berlin"}
    assert calls == []

    done = resume_turn(graph, "t2", {"action": "approve"}, turn_start_index=paused.start_index)
    assert done.status == "done" and done.answer == "It will rain."
    assert calls == [("get_weather_forecast", {"city": "Berlin"})]
    assert done.tools_used == [
        {"name": "get_weather_forecast", "args": {"city": "Berlin"}, "ran": True}
    ]


def test_edit_changes_the_arguments_before_the_tool_runs(tools, calls):
    """The parent's edited arguments are the ones the tool receives."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("Done.")], tools
    )
    paused = start_turn(graph, "t3", "weather?", **CONTEXT)
    resume_turn(
        graph,
        "t3",
        {"action": "edit", "tool_calls": [{"id": "w1", "args": {"city": "Potsdam"}}]},
        turn_start_index=paused.start_index,
    )
    assert calls == [("get_weather_forecast", {"city": "Potsdam"})]


def test_reject_skips_the_tool_and_tells_the_model_why(tools, calls):
    """A rejected call never runs; the model sees the parent's feedback and answers."""
    graph, model = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("OK, no weather.")],
        tools,
    )
    paused = start_turn(graph, "t4", "weather?", **CONTEXT)
    done = resume_turn(
        graph,
        "t4",
        {"action": "reject", "feedback": "indoor only please"},
        turn_start_index=paused.start_index,
    )
    assert calls == []
    assert done.answer == "OK, no weather."
    last_input = model.received[-1]
    rejection = [m for m in last_input if isinstance(m, ToolMessage)][-1]
    assert "rejected" in rejection.content and "indoor only please" in rejection.content


def test_auto_approve_runs_external_tools_without_pausing(tools, calls):
    """With auto-approve on, external tools run straight away."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("Sunny.")], tools
    )
    result = start_turn(graph, "t5", "weather?", auto_approve=True, **CONTEXT)
    assert result.status == "done" and calls == [("get_weather_forecast", {"city": "Berlin"})]


def test_invented_link_is_removed_from_the_final_answer(tools):
    """A link no tool returned is stripped from the answer the parent sees."""
    graph, _ = _graph([AIMessage("Visit [Fake Park](https://fake.example) today!")], tools)
    result = start_turn(graph, "t6", "ideas?", **CONTEXT)
    assert "fake.example" not in result.answer
    assert result.grounding["removed"] == ["https://fake.example"]


def test_system_prompt_holds_the_sidebar_context():
    """The chosen country, city and age reach the model in the system prompt."""
    state = {"country": "GB", "city": None, "children": ["3-5", "10-14"], "messages": []}
    prompt = system_prompt(state)
    assert "United Kingdom (GB)" in prompt and "All cities" in prompt
    assert "Child 1: 3-5 years; Child 2: 10-14 years" in prompt


def test_input_check_rejects_empty_and_too_long_text():
    """Empty or very long messages are rejected before any model call."""
    with pytest.raises(InputRejected):
        check_input("   ")
    with pytest.raises(InputRejected):
        check_input("x" * 5000)
    assert check_input("  hi ") == "hi"


def test_text_that_grows_when_folded_is_rejected():
    """A short message of ligatures that fold into many letters is rejected as too long."""
    with pytest.raises(InputRejected, match="special characters"):
        check_input("ﷺ" * 200)
    assert decision_problem({"feedback": "ﷺ" * 600}, []) is not None


def test_system_prompt_describes_the_trip_settings():
    """The trip budget and party reach the model; without them trip planning is off."""
    trip = {"budget_eur": 80, "adults": 2, "deutschlandticket_holders": 1}
    prompt = system_prompt({"country": "DE", "city": "Munich", "children": ["3-5"], "trip": trip})
    assert "budget 80 EUR" in prompt and "adults: 2" in prompt
    assert "Deutschlandticket holders (aged 15+): 1" in prompt
    assert "Budget day trip: off" in system_prompt({"country": "DE", "messages": []})


def test_budget_check_waits_for_the_parent_even_with_auto_approve():
    """check_budget always pauses, so the parent's amounts replace any the model guessed."""

    def check_budget(budget_eur: float, items: list[dict]) -> str:
        """Fake budget tool."""
        return json.dumps({"items": items})

    graph, _ = _graph(
        [
            _call("check_budget", {"budget_eur": 80, "items": [{"label": "Zoo"}]}, "b1"),
            AIMessage("Done."),
        ],
        [StructuredTool.from_function(check_budget)],
    )
    paused = start_turn(graph, "t9", "budget?", auto_approve=True, **CONTEXT)
    assert paused.status == "needs_approval" and paused.needs_approval == ["b1"]


def test_approved_budget_runs_with_the_parents_amounts():
    """Resuming a paused budget check with the parent's table runs the tool with those amounts."""
    received = []

    def check_budget(budget_eur: float, items: list[dict]) -> str:
        """Fake budget tool that records what it got."""
        received.append((budget_eur, items))
        return json.dumps({"ok": True})

    graph, _ = _graph(
        [
            _call("check_budget", {"budget_eur": 80, "items": [{"label": "Zoo"}]}, "b1"),
            AIMessage("Done."),
        ],
        [StructuredTool.from_function(check_budget)],
    )
    paused = start_turn(graph, "t10", "budget?", **CONTEXT)
    parent_table = {"budget_eur": 90, "items": [{"label": "Zoo", "amount_eur": 25}]}
    resume_turn(
        graph,
        "t10",
        {"action": "edit", "tool_calls": [{"id": "b1", "args": parent_table}]},
        turn_start_index=paused.start_index,
    )
    assert received == [(90, [{"label": "Zoo", "amount_eur": 25}])]


def test_grounding_always_stores_the_cleaned_answer(tools):
    """Even with nothing removed, the stored answer is the escaped, cleaned text."""
    graph, _ = _graph([AIMessage("Tickets $15 [optional]")], tools)
    result = start_turn(graph, "t11", "price?", **CONTEXT)
    assert result.answer == r"Tickets \$15 \[optional\]"
    assert result.grounding == {"verified": [], "removed": []}


FORGED = {
    "from_state": "BY",
    "to_state": "BY",
    "travel_date": "2026-11-21",
    "trip": {"budget_eur": 1, "adults": 1, "deutschlandticket_holders": 5},
    "children": [],
    "adults": 1,
}
TRIP = {"budget_eur": 80, "adults": 2, "deutschlandticket_holders": 0}


def _ticket_tool():
    """The real ticket comparison tool from the registry."""
    from src.rag.retriever import AdvancedRetriever
    from src.tools.registry import RagSettings, build_tools

    built = build_tools(AdvancedRetriever(None), RagSettings(multi_query=False))
    return [t for t in built if t.name == "compare_train_tickets"]


def test_forged_party_from_the_model_is_ignored():
    """Security R1-4: a party the model writes is replaced by the sidebar's trip settings."""
    graph, _ = _graph(
        [_call("compare_train_tickets", FORGED, "c1"), AIMessage("Done.")], _ticket_tool()
    )
    result = start_turn(
        graph, "t20", "tickets?", country="DE", city="Munich", children=["3-5", "6-9"], trip=TRIP
    )
    tickets = result.calculations["compare_train_tickets"]
    assert tickets["options"][0]["total_eur"] == 44.0
    assert "for 2 person(s)" in tickets["options"][0]["tickets"][0]


def test_forged_party_in_an_approval_edit_is_ignored():
    """An edit in the approval panel cannot set the party either."""
    from src import config

    both = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_weather_forecast", "args": {"city": "Munich"}, "id": "w1"},
            {"name": "compare_train_tickets", "args": {**FORGED, "trip": None}, "id": "c1"},
        ],
    )
    graph, _ = _graph([both, AIMessage("Done.")], [*_ticket_tool(), *_weather_tool()])
    assert "compare_train_tickets" not in config.TOOLS_REQUIRING_APPROVAL
    paused = start_turn(
        graph, "t21", "trip?", country="DE", city="Munich", children=["3-5", "6-9"], trip=TRIP
    )
    assert paused.status == "needs_approval"
    resume_turn(
        graph,
        "t21",
        {
            "action": "edit",
            "tool_calls": [
                {"id": "w1", "args": {"city": "Munich"}},
                {"id": "c1", "args": FORGED},
            ],
        },
        turn_start_index=paused.start_index,
    )
    state = graph.get_state({"configurable": {"thread_id": "t21"}}).values
    result = [m for m in state["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "c1"]
    assert json.loads(result[0].content)["options"][0]["total_eur"] == 44.0


def _weather_tool():
    """A fake external weather tool."""

    def get_weather_forecast(city: str) -> str:
        """Fake external weather tool."""
        return json.dumps({"days": []})

    return [StructuredTool.from_function(get_weather_forecast)]


def test_calculations_keep_the_latest_successful_result():
    """Only JSON results without an error count; the latest one of each tool wins."""
    from src.agent.runner import calculations

    messages = [
        ToolMessage('{"total": 1}', tool_call_id="1", name="check_budget"),
        ToolMessage('{"total": 2}', tool_call_id="2", name="check_budget"),
        ToolMessage('{"error": "x"}', tool_call_id="3", name="check_budget"),
        ToolMessage("Error: bad", tool_call_id="4", name="compare_train_tickets"),
        ToolMessage('{"total": 9}', tool_call_id="5", name="search_knowledge_base"),
    ]
    assert calculations(messages) == {"check_budget": {"total": 2}}


def test_resume_rejects_sensitive_text_the_parent_typed():
    """The approval check also runs in resume_turn, not only in the page."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("ok")],
        _weather_tool(),
    )
    paused = start_turn(graph, "t22", "weather?", **CONTEXT)
    with pytest.raises(InputRejected):
        resume_turn(
            graph,
            "t22",
            {"action": "reject", "feedback": "my son has asthma"},
            turn_start_index=paused.start_index,
        )


def test_model_written_arguments_do_not_block_an_approval():
    """Text the model wrote (e.g. "kids aged 6") is not the parent's, so approving works."""
    from src.agent.runner import decision_problem

    original = [{"id": "b1", "args": {"items": [{"label": "Zoo", "note": "kids aged 6 free"}]}}]
    same = {"action": "edit", "tool_calls": original}
    assert decision_problem(same, original) is None
    changed = {"action": "edit", "tool_calls": [{"id": "b1", "args": {"note": "Kinderarzt"}}]}
    assert decision_problem(changed, original)


def test_extra_keys_in_an_edit_are_dropped_or_blocked():
    """Text typed as a new JSON key never reaches the model: blocked, or dropped when harmless."""
    from src.agent.runner import decision_problem

    original = [{"id": "w1", "name": "get_weather_forecast", "args": {"city": "Berlin"}}]
    sneaky = {
        "action": "edit",
        "tool_calls": [{"id": "w1", "args": {"city": "Berlin", "Lena hat ADHS": 1}}],
    }
    assert decision_problem(sneaky, original)

    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("ok")],
        _weather_tool(),
    )
    paused = start_turn(graph, "t23", "weather?", **CONTEXT)
    resume_turn(
        graph,
        "t23",
        {"action": "edit", "tool_calls": [{"id": "w1", "args": {"city": "Munich", "extra": "x"}}]},
        turn_start_index=paused.start_index,
    )
    state = graph.get_state({"configurable": {"thread_id": "t23"}}).values
    calls = [tc for m in state["messages"] if isinstance(m, AIMessage) for tc in m.tool_calls]
    assert calls[0]["args"] == {"city": "Munich"}


def test_long_decisions_are_refused_and_short_ones_pass():
    """Security round 7/8: an over-long reason or edited value is refused before any check."""
    from src import config
    from src.agent.runner import decision_problem

    long_reason = {"action": "reject", "feedback": "x " * config.MAX_DECISION_CHARS}
    assert "too long" in decision_problem(long_reason, [])
    # Security round 20: the reject reason is capped on the server, not only by the text box.
    reason_301 = {"action": "reject", "feedback": "a" * (config.MAX_REJECT_REASON_CHARS + 1)}
    assert "too long" in decision_problem(reason_301, [])
    assert decision_problem({"action": "reject", "feedback": "only indoor places"}, []) is None
    long_value = {"action": "edit", "tool_calls": [{"id": "1", "args": {"city": "a" * 500}}]}
    assert "too long" in decision_problem(long_value, [])
    short = {"action": "edit", "tool_calls": [{"id": "1", "args": {"city": "Munich"}}]}
    assert decision_problem(short, []) is None


def test_deeply_nested_json_in_the_edit_box_is_not_applied():
    """Security round 8: nested JSON too deep to read is treated like invalid JSON."""
    from views.chat import parse_edited_args

    assert parse_edited_args('{"a":' + "[" * 200000) is None


def test_deep_valid_json_edit_is_refused_without_crashing():
    """Security round 9: valid but deeply nested JSON is not applied and does not crash."""
    from src.agent.runner import decision_problem
    from views.chat import parse_edited_args

    deep = '{"q": ' + "[" * 1200 + "]" * 1200 + "}"
    assert parse_edited_args(deep) is None
    nested: object = "x"
    for _ in range(1200):
        nested = [nested]
    decision = {"action": "edit", "tool_calls": [{"id": "1", "args": {"q": nested}}]}
    assert "too long" in decision_problem(decision, [])


def test_a_deep_forged_decision_is_refused_before_it_is_cleaned(tools, calls):
    """T5.7 code round 2: resume_turn checks the depth before the recursive cleaning runs."""
    nested: object = "x"
    for _ in range(1200):
        nested = [nested]
    decision = {"action": "edit", "tool_calls": [{"id": "w1", "args": {"city": nested}}]}
    graph, _ = _graph([_call("get_weather_forecast", {"city": "Berlin"}, "w1")], tools)
    paused = start_turn(graph, "d1", "weather?", **CONTEXT)
    with pytest.raises(InputRejected, match="too long"):
        resume_turn(graph, "d1", decision, turn_start_index=paused.start_index)
    assert calls == []


def test_long_model_values_do_not_block_approve():
    """Security round 9: the per-value cap applies only to values the parent changed."""
    from src.agent.runner import decision_problem

    original = [{"id": "1", "args": {"query": "museum " * 70}}]
    assert decision_problem({"action": "edit", "tool_calls": original}, original) is None


def test_blank_city_is_a_tool_error_not_a_crash():
    """Security round 10: a blank city becomes a tool error, and the next turn still runs."""
    from src.rag.retriever import AdvancedRetriever
    from src.tools.registry import RagSettings, build_tools

    built = build_tools(AdvancedRetriever(None), RagSettings(multi_query=False))
    kb = [t for t in built if t.name == "search_knowledge_base"]
    blank = {"query": "zoo", "country": "DE", "city": "   "}
    graph, _ = _graph(
        [_call("search_knowledge_base", blank, "k1"), AIMessage("ok"), AIMessage("again")], kb
    )
    first = start_turn(graph, "t30", "zoo?", **CONTEXT)
    assert first.status == "done"
    state = graph.get_state({"configurable": {"thread_id": "t30"}}).values
    assert any(isinstance(m, ToolMessage) and m.tool_call_id == "k1" for m in state["messages"])
    second = start_turn(graph, "t30", "and now?", **CONTEXT)
    assert second.status == "done"


# T5.1: live progress while the agent works.
START, NEXT = config.PROGRESS_START, config.PROGRESS_NEXT_STEP
GROUNDING, APPROVAL = config.PROGRESS_GROUNDING, config.PROGRESS_APPROVAL
ALLOWED_LABELS = {
    START,
    NEXT,
    GROUNDING,
    APPROVAL,
    config.PROGRESS_UNKNOWN_TOOL,
    *config.PROGRESS_TOOL_LABELS.values(),
}


def test_progress_reports_each_step_in_order(tools):
    """An internal tool turn reports: start, the tool, the next step, the link check."""
    graph, _ = _graph(
        [_call("search_knowledge_base", {"query": "zoo"}, "c1"), AIMessage("Zoo Berlin")], tools
    )
    events: list[str] = []
    result = start_turn(graph, "p1", "zoo?", progress=events.append, **CONTEXT)
    assert result.status == "done"
    assert events == [START, "Searching the curated places", NEXT, GROUNDING]


def test_progress_waits_for_approval_and_continues_after_it(tools):
    """A paused turn reports the wait; approving reports the tool, then the rest."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("Rain.")], tools
    )
    events: list[str] = []
    paused = start_turn(graph, "p2", "weather?", progress=events.append, **CONTEXT)
    assert paused.status == "needs_approval"
    # The weather label is not shown before the parent approves: the tool has not run.
    assert events == [START, APPROVAL]
    events.clear()
    resume_turn(
        graph,
        "p2",
        {"action": "approve"},
        turn_start_index=paused.start_index,
        progress=events.append,
    )
    assert events == ["Checking the weather", NEXT, GROUNDING]


def test_progress_after_a_reject_skips_the_tool(tools, calls):
    """A rejected call never shows a tool label; the agent goes on to its next step."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("Okay.")], tools
    )
    paused = start_turn(graph, "p3", "weather?", **CONTEXT)
    events: list[str] = []
    resume_turn(
        graph,
        "p3",
        {"action": "reject", "feedback": "no weather"},
        turn_start_index=paused.start_index,
        progress=events.append,
    )
    assert events == [NEXT, GROUNDING]
    assert calls == []


def test_progress_with_auto_approve_shows_the_outside_tool(tools):
    """With auto-approve on, the outside tool runs at once and is reported."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("Rain.")], tools
    )
    events: list[str] = []
    start_turn(graph, "p4", "weather?", auto_approve=True, progress=events.append, **CONTEXT)
    assert events == [START, "Checking the weather", NEXT, GROUNDING]


def test_progress_never_carries_model_or_tool_text(caplog):
    """Only fixed labels reach the page: not the answer, the arguments or the tool result."""
    marker = "MARKER-7731"

    def search_knowledge_base(query: str) -> str:
        """Fake internal search whose result carries the marker."""
        return json.dumps({"results": [{"name": marker, "website": "https://zoo.example"}]})

    graph, _ = _graph(
        [
            _call("search_knowledge_base", {"query": marker}, "c1"),
            _call("made_up_tool_" + marker, {"x": marker}, "c2"),
            AIMessage(f"{marker} [Zoo](https://zoo.example)"),
        ],
        [StructuredTool.from_function(search_knowledge_base)],
    )
    events: list[str] = []
    with caplog.at_level(logging.DEBUG):
        start_turn(graph, "p5", "zoo?", auto_approve=True, progress=events.append, **CONTEXT)
    assert config.PROGRESS_UNKNOWN_TOOL in events
    assert set(events) <= ALLOWED_LABELS
    assert not any(marker in e for e in events)
    # Progress events are not logged.
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert not any(label in logged for label in ALLOWED_LABELS)


@pytest.mark.parametrize("auto", [False, True])
def test_budget_check_is_reported_as_a_wait_even_with_auto_approve(auto):
    """check_budget always pauses, so its label never shows before the parent's amounts."""
    from src.agent.runner import progress_labels

    budget = _call("check_budget", {"budget_eur": 50, "items": []}, "b1")
    labels = progress_labels({"agent": {"messages": [budget]}}, auto)
    labels += progress_labels({"__interrupt__": ()}, auto)
    assert labels == [APPROVAL]


def test_progress_labels_ignore_other_nodes_and_empty_updates():
    """Updates without messages, from review or grounding, add no label of their own."""
    from src.agent.runner import progress_labels

    assert progress_labels({"human_review": None}) == []
    assert progress_labels({"grounding": {"messages": []}}) == []
    assert progress_labels({"agent": None}) == [GROUNDING]


@pytest.mark.parametrize("failing_label", [START, "Checking the weather", NEXT, GROUNDING])
def test_a_failing_progress_callback_never_cuts_the_turn(tools, calls, caplog, failing_label):
    """Security round 1 (Low): a callback error drops progress; the graph still finishes."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("Rain.")], tools
    )

    def progress(label: str) -> None:
        """Fail on one label, as a broken page element would."""
        if label == failing_label:
            raise RuntimeError("page element failed")

    with caplog.at_level(logging.WARNING):
        result = start_turn(
            graph, "p6", "weather?", auto_approve=True, progress=progress, **CONTEXT
        )
    assert result.status == "done" and result.answer == "Rain."
    assert result.grounding is not None
    assert calls == [("get_weather_forecast", {"city": "Berlin"})]
    state = graph.get_state({"configurable": {"thread_id": "p6"}}).values["messages"]
    answered = {m.tool_call_id for m in state if isinstance(m, ToolMessage)}
    assert answered == {"w1"}
    assert [r.getMessage() for r in caplog.records if r.name == "src.agent.runner"] == [
        "progress_failed"
    ]


# Security round 1 (High, Medium): a decision runs only the calls the parent saw.
def _two_pauses(tools):
    """A graph that pauses on the weather, then on an events search after approval."""

    def search_family_events(city: str) -> str:
        """Fake outside event search."""
        tools_calls.append(("search_family_events", {"city": city}))
        return json.dumps({"results": []})

    tools_calls: list = []
    graph, _ = _graph(
        [
            _call("get_weather_forecast", {"city": "Berlin"}, "w1"),
            _call("search_family_events", {"city": "Hamburg"}, "e1"),
            AIMessage("Done."),
        ],
        [*tools, StructuredTool.from_function(search_family_events)],
    )
    return graph, tools_calls


@pytest.mark.parametrize(
    "decision",
    [
        {"action": "approve"},
        {"action": "reject", "feedback": "no"},
        {"action": "edit", "tool_calls": [{"id": "w1", "args": {"city": "Potsdam"}}]},
    ],
)
def test_resume_refuses_a_decision_for_other_calls(tools, calls, decision):
    """A decision made on panel w1 never runs e1, which the parent has not seen."""
    graph, event_calls = _two_pauses(tools)
    first = start_turn(graph, "s1", "weather?", **CONTEXT)
    second = resume_turn(
        graph, "s1", {"action": "approve"}, turn_start_index=first.start_index, expected_ids=["w1"]
    )
    assert second.status == "needs_approval" and second.needs_approval == ["e1"]
    with pytest.raises(StaleDecision):
        resume_turn(graph, "s1", decision, turn_start_index=first.start_index, expected_ids=["w1"])
    assert event_calls == []
    # The panel the parent sees now still works.
    done = resume_turn(
        graph, "s1", {"action": "approve"}, turn_start_index=first.start_index, expected_ids=["e1"]
    )
    assert done.status == "done" and event_calls == [("search_family_events", {"city": "Hamburg"})]


@pytest.mark.parametrize("action", [{"action": "approve"}, {"action": "reject", "feedback": "no"}])
def test_a_thread_that_does_not_wait_runs_nothing_on_resume(tools, calls, action):
    """A run left before its tools step (no pause) is never resumed by an old panel's click."""
    graph, _ = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("Rain.")], tools
    )
    run_config = {"configurable": {"thread_id": "s2", "auto_approve": True}}
    stream = graph.stream(
        {"messages": [HumanMessage("weather?")], **CONTEXT, "trip": None, "grounding": None},
        run_config,
        stream_mode="updates",
    )
    next(stream)  # the agent step plans the call; the run then stops before the tools step
    stream.close()
    assert graph.get_state(run_config).next == ("tools",)
    with pytest.raises(StaleDecision):
        resume_turn(graph, "s2", action, turn_start_index=0, expected_ids=["w1"])
    assert calls == []


def test_a_finished_turn_is_not_resumed(tools, calls):
    """Once a turn has its answer, a decision from an old panel is refused."""
    graph, _ = _graph([AIMessage("Hello.")], tools)
    start_turn(graph, "s3", "hi", **CONTEXT)
    with pytest.raises(StaleDecision):
        resume_turn(graph, "s3", {"action": "approve"}, turn_start_index=0)
    assert calls == []


def test_a_reused_call_id_does_not_pass_as_the_same_pause(tools, calls):
    """Security round 2 (Low): the pause id, not the model's call id, ties a decision to a panel."""

    def search_family_events(city: str) -> str:
        """Fake outside event search."""
        event_calls.append(city)
        return json.dumps({"results": []})

    event_calls: list[str] = []
    graph, _ = _graph(
        [
            _call("get_weather_forecast", {"city": "Berlin"}, "call_0"),
            _call("search_family_events", {"city": "Hamburg"}, "call_0"),
            AIMessage("Done."),
        ],
        [*tools, StructuredTool.from_function(search_family_events)],
    )
    first = start_turn(graph, "s4", "weather?", **CONTEXT)
    second = resume_turn(
        graph,
        "s4",
        {"action": "approve"},
        turn_start_index=first.start_index,
        expected_ids=["call_0"],
        expected_pause=first.pause_id,
    )
    assert second.status == "needs_approval"
    assert first.pause_id and second.pause_id and first.pause_id != second.pause_id
    with pytest.raises(StaleDecision) as stale:
        resume_turn(
            graph,
            "s4",
            {"action": "approve"},
            turn_start_index=first.start_index,
            expected_ids=["call_0"],
            expected_pause=first.pause_id,
        )
    assert event_calls == []
    # The refusal carries the pause the conversation waits on now, for the page to show.
    assert stale.value.current.pause_id == second.pause_id


def test_a_stale_decision_on_a_finished_turn_carries_no_pause(tools):
    """With nothing waiting, the refusal has no current pause, so the page clears the panel."""
    graph, _ = _graph([AIMessage("Hello.")], tools)
    start_turn(graph, "s5", "hi", **CONTEXT)
    with pytest.raises(StaleDecision) as stale:
        resume_turn(graph, "s5", {"action": "reject"}, turn_start_index=0, expected_pause="p1")
    assert stale.value.current is None


def _train_tool(train_calls: list) -> list[StructuredTool]:
    """A fake train tool with the real argument schema, so `PlaceName` checks its towns."""
    from src.tools.registry import TrainArgs

    def find_train_connection(from_city, to_town, travel_date, depart_after=None) -> str:
        """Fake train search that records what it received."""
        train_calls.append({"from_city": from_city, "to_town": to_town, "date": travel_date})
        return json.dumps({"journeys": []})

    return [StructuredTool.from_function(find_train_connection, args_schema=TrainArgs)]


def test_the_forms_edited_arguments_reach_the_tool():
    """T5.2 AC2: what the form sends after an edit is what the train tool receives."""
    from datetime import date, timedelta

    from src.approval_form import form_to_args, initial_values

    soon = date.today() + timedelta(days=2)
    model_args = {"from_city": "Berlin", "to_town": "Potsdam", "travel_date": soon.isoformat()}
    train_calls: list = []
    graph, _ = _graph(
        [_call("find_train_connection", model_args, "t1"), AIMessage("ok")],
        _train_tool(train_calls),
    )
    paused = start_turn(graph, "f1", "train?", **CONTEXT)
    call = paused.pending_tool_calls[0]
    values = initial_values(call)
    values["to_town"] = "Brandenburg an der Havel"
    values["travel_date"] = soon + timedelta(days=1)
    args, problems = form_to_args("find_train_connection", values)
    assert problems == []
    decision = {"action": "edit", "tool_calls": [{"id": "t1", "args": args}]}
    assert decision_problem(decision, paused.pending_tool_calls) is None
    resume_turn(
        graph,
        "f1",
        decision,
        turn_start_index=paused.start_index,
        expected_ids=["t1"],
        expected_pause=paused.pause_id,
    )
    assert train_calls == [
        {
            "from_city": "Berlin",
            "to_town": "Brandenburg an der Havel",
            "date": soon + timedelta(days=1),
        }
    ]


def _forged_town_turn(town: str, thread: str):
    """Pause on a train call and return the graph, the pause, a forged edit and the tool log."""
    from datetime import date, timedelta

    soon = (date.today() + timedelta(days=2)).isoformat()
    model_args = {"from_city": "Berlin", "to_town": "Potsdam", "travel_date": soon}
    train_calls: list = []
    graph, _ = _graph(
        [_call("find_train_connection", model_args, "t1"), AIMessage("ok")],
        _train_tool(train_calls),
    )
    paused = start_turn(graph, thread, "train?", **CONTEXT)
    forged = {
        "action": "edit",
        "tool_calls": [{"id": "t1", "args": {**model_args, "to_town": town}}],
    }
    return graph, paused, forged, train_calls


@pytest.mark.parametrize("town", ["Lena ist 7", "Mein Sohn Max", "Autismus Zentrum"])
def test_a_name_age_or_health_word_that_skips_the_form_is_refused_on_the_server(town):
    """T5.2 AC3: resume_turn runs decision_problem itself, so nothing runs or reaches the model."""
    graph, paused, forged, train_calls = _forged_town_turn(town, "f2")
    assert decision_problem(forged, paused.pending_tool_calls)
    with pytest.raises(InputRejected):
        resume_turn(graph, "f2", forged, turn_start_index=paused.start_index)
    assert train_calls == []


@pytest.mark.parametrize("town", ["berlin bitte", "Potsdam, dann weiter nach Werder"])
def test_a_sentence_that_skips_the_form_is_refused_by_the_tools_place_name_check(town):
    """T5.2 AC3: a sentence that holds no personal data is still no town: PlaceName refuses it."""
    graph, paused, forged, train_calls = _forged_town_turn(town, "f3")
    assert decision_problem(forged, paused.pending_tool_calls) is None
    resume_turn(graph, "f3", forged, turn_start_index=paused.start_index)
    assert train_calls == []


# T5.7: a lone surrogate never reaches a model request or the stored history.
SURROGATE, FFFD = "\ud800", "�"


def _requests_encode(model: ScriptedChatModel) -> None:
    """Check that every request the model received can be written as UTF-8, as sent."""
    from langchain_openai.chat_models.base import _convert_message_to_dict

    assert model.received
    for batch in model.received:
        sent = [_convert_message_to_dict(m) for m in batch]
        json.dumps(sent, ensure_ascii=False).encode("utf-8")
        json.dumps([m.model_dump() for m in batch], ensure_ascii=False, default=str).encode()


def _stored(graph, thread: str) -> list:
    """Return the messages the checkpointer holds for a thread."""
    return graph.get_state({"configurable": {"thread_id": thread}}).values["messages"]


def _no_surrogate(value) -> bool:
    """Return True when no string in the value holds a lone surrogate."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    return not any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


@pytest.mark.parametrize("name", ["search_knowledge_base", "search_knowledge_base" + SURROGATE])
def test_a_surrogate_in_a_call_that_runs_without_a_pause_is_replaced(tools, calls, name):
    """T5.7 AC2: the tool call, its id and the answer hold U+FFFD; the next request encodes."""
    graph, model = _graph(
        [
            _call(name, {"query": "zoo" + SURROGATE}, "c" + SURROGATE),
            AIMessage("Zoo " + SURROGATE + " [Zoo](https://zoo.example)"),
        ],
        tools,
    )
    result = start_turn(graph, "u1", "zoo?", **CONTEXT)
    assert result.status == "done"
    assert len(model.received) == 2
    _requests_encode(model)
    stored = _stored(graph, "u1")
    call = stored[1].tool_calls[0]
    assert call["args"] == {"query": "zoo" + FFFD} and call["name"] == name.replace(SURROGATE, FFFD)
    assert call["id"].startswith("c" + FFFD) and stored[2].tool_call_id == call["id"]
    assert FFFD in stored[-1].content and FFFD in result.answer
    assert _no_surrogate([m.model_dump() for m in stored])
    if name == "search_knowledge_base":
        assert calls == [("search_knowledge_base", {"query": "zoo" + FFFD})]


def test_a_surrogate_in_a_call_that_pauses_is_replaced_before_the_pause(tools, calls):
    """T5.7 AC2: the pause payload holds U+FFFD, and approving runs the cleaned call."""
    graph, model = _graph(
        [
            _call("get_weather_forecast", {"city": "Ber" + SURROGATE + "lin"}, "w" + SURROGATE),
            AIMessage("Rain."),
        ],
        tools,
    )
    paused = start_turn(graph, "u2", "weather?", **CONTEXT)
    pending = paused.pending_tool_calls[0]
    assert pending["args"] == {"city": "Ber" + FFFD + "lin"}
    assert _no_surrogate(pending) and pending["id"] == paused.needs_approval[0]
    done = resume_turn(
        graph,
        "u2",
        {"action": "approve"},
        turn_start_index=paused.start_index,
        expected_ids=[pending["id"]],
        expected_pause=paused.pause_id,
    )
    assert done.status == "done"
    assert calls == [("get_weather_forecast", {"city": "Ber" + FFFD + "lin"})]
    _requests_encode(model)
    assert _no_surrogate([m.model_dump() for m in _stored(graph, "u2")])


def test_a_surrogate_in_an_answer_is_replaced(tools):
    """T5.7 AC2: the stored answer holds U+FFFD, and the next turn's request encodes."""
    graph, model = _graph([AIMessage("Hi " + SURROGATE), AIMessage("Again.")], tools)
    first = start_turn(graph, "u3", "hi", **CONTEXT)
    assert first.answer == "Hi " + FFFD
    assert _stored(graph, "u3")[-1].content == "Hi " + FFFD
    start_turn(graph, "u3", "and?", **CONTEXT)
    _requests_encode(model)


def test_a_surrogate_in_the_parents_edit_is_replaced(tools, calls):
    """T5.7 AC2: a JSON edit holding a lone surrogate reaches the tool and the model as U+FFFD."""
    graph, model = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("Done.")], tools
    )
    paused = start_turn(graph, "u4", "weather?", **CONTEXT)
    # The six-character JSON escape a parent can type in the editor, read by json.loads.
    edit = json.loads(r'{"city": "Pots\ud800dam"}')
    assert edit["city"] == "Pots" + SURROGATE + "dam"
    resume_turn(
        graph,
        "u4",
        {"action": "edit", "tool_calls": [{"id": "w1", "args": edit}]},
        turn_start_index=paused.start_index,
    )
    assert calls == [("get_weather_forecast", {"city": "Pots" + FFFD + "dam"})]
    _requests_encode(model)
    stored = _stored(graph, "u4")
    assert stored[1].tool_calls[0]["args"] == {"city": "Pots" + FFFD + "dam"}
    assert _no_surrogate([m.model_dump() for m in stored])


def test_a_surrogate_in_a_reject_reason_is_replaced(tools, calls):
    """T5.7 AC2: the rejection the model reads holds U+FFFD, not the surrogate or its escape."""
    graph, model = _graph(
        [_call("get_weather_forecast", {"city": "Berlin"}, "w1"), AIMessage("OK.")], tools
    )
    paused = start_turn(graph, "u5", "weather?", **CONTEXT)
    resume_turn(
        graph,
        "u5",
        {"action": "reject", "feedback": "indoor " + SURROGATE + " only"},
        turn_start_index=paused.start_index,
    )
    assert calls == []
    _requests_encode(model)
    rejection = [m for m in _stored(graph, "u5") if isinstance(m, ToolMessage)][-1]
    assert "indoor " + FFFD + " only" in json.loads(rejection.content)["error"]


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ("a" + SURROGATE, "a\udc00", False),  # differ only by the surrogate
        ("a" + SURROGATE, "a" + FFFD, False),  # a real U+FFFD at the same place
        ("x" + SURROGATE, "x" + SURROGATE, True),  # repeated id stays repeated
    ],
)
def test_call_ids_compare_the_same_after_the_replacement(tools, first, second, same):
    """T5.7 AC2: distinct ids stay distinct and equal ids stay equal (repeated ids: only Reject)."""
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_weather_forecast", "args": {"city": "Berlin"}, "id": first},
            {"name": "get_weather_forecast", "args": {"city": "Potsdam"}, "id": second},
        ],
    )
    graph, _ = _graph([message], tools)
    paused = start_turn(graph, "u6", "weather?", **CONTEXT)
    ids = [tc["id"] for tc in paused.pending_tool_calls]
    assert _no_surrogate(ids)
    assert (ids[0] == ids[1]) is same


def test_cleaning_an_id_twice_keeps_it():
    """T5.7: an id the page sends back unchanged is the id the thread holds."""
    from src.safe_text import clean_decision, clean_id

    once = clean_id("w" + SURROGATE)
    assert clean_id(once) == once and clean_id("w1") == "w1"
    decision = {"action": "edit", "tool_calls": [{"id": "w" + SURROGATE, "args": {}}]}
    assert clean_decision(decision)["tool_calls"][0]["id"] == once


def test_surrogates_in_additional_kwargs_and_invalid_calls_are_replaced(tools):
    """T5.7 AC2 (code round 1): extra fields and malformed calls are cleaned and sent as UTF-8."""
    from langchain_core.messages.tool import invalid_tool_call

    broken = AIMessage(
        content="Hi",
        additional_kwargs={"note": "a" + SURROGATE, "nested": {"k" + SURROGATE: ["b" + SURROGATE]}},
        invalid_tool_calls=[
            invalid_tool_call(
                name="bad" + SURROGATE, args="{" + SURROGATE, id="i" + SURROGATE, error=None
            )
        ],
    )
    graph, model = _graph([broken, AIMessage("Again.")], tools)
    start_turn(graph, "u7", "hi", **CONTEXT)
    start_turn(graph, "u7", "and?", **CONTEXT)
    _requests_encode(model)
    stored = _stored(graph, "u7")
    assert _no_surrogate([m.model_dump() for m in stored])
    first = stored[1]
    assert first.additional_kwargs["note"] == "a" + FFFD
    assert first.invalid_tool_calls[0]["args"] == "{" + FFFD
    assert first.invalid_tool_calls[0]["id"].startswith("i" + FFFD)


def test_message_ids_that_differ_only_by_a_surrogate_stay_distinct(tools, calls):
    """Security round 1: two steps whose ids differ by a surrogate are both kept."""
    step = _call("search_knowledge_base", {"query": "zoo"}, "c1")
    step.id = "m" + SURROGATE
    answer = AIMessage("[Zoo](https://zoo.example)", id="m\udc00")
    graph, model = _graph([step, answer], tools)
    result = start_turn(graph, "u8", "zoo?", **CONTEXT)
    assert result.status == "done" and calls
    ids = [m.id for m in _stored(graph, "u8") if isinstance(m, AIMessage)]
    assert len(ids) == 2 and ids[0] != ids[1] and _no_surrogate(ids)
    _requests_encode(model)


def test_a_call_id_reused_after_a_rejection_still_counts_as_run(tools, calls):
    """Legal and security round 1: a later step's rejection never marks an earlier call."""
    graph, _ = _graph(
        [
            _call("get_weather_forecast", {"city": "Berlin"}, "call_0"),
            _call("get_weather_forecast", {"city": "Potsdam"}, "call_0"),
            AIMessage("Done."),
        ],
        tools,
    )
    first = start_turn(graph, "u9", "weather?", **CONTEXT)
    second = resume_turn(graph, "u9", {"action": "reject"}, turn_start_index=first.start_index)
    done = resume_turn(graph, "u9", {"action": "approve"}, turn_start_index=second.start_index)
    assert [t["ran"] for t in done.tools_used] == [False, True]
    assert calls == [("get_weather_forecast", {"city": "Potsdam"})]


def test_an_approved_call_stays_run_when_a_later_step_reusing_its_id_is_rejected(tools, calls):
    """Legal round 1: approved first, a reused id rejected next: only the second did not run."""
    graph, _ = _graph(
        [
            _call("get_weather_forecast", {"city": "Berlin"}, "call_0"),
            _call("get_weather_forecast", {"city": "Potsdam"}, "call_0"),
            AIMessage("Done."),
        ],
        tools,
    )
    first = start_turn(graph, "u10", "weather?", **CONTEXT)
    second = resume_turn(graph, "u10", {"action": "approve"}, turn_start_index=first.start_index)
    done = resume_turn(graph, "u10", {"action": "reject"}, turn_start_index=second.start_index)
    assert [t["ran"] for t in done.tools_used] == [True, False]
