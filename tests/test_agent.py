"""Tests for the agent graph: human-in-the-loop approve, edit, reject, auto-approve, grounding."""

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.graph import build_graph, system_prompt
from src.agent.runner import (
    InputRejected,
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
    assert done.tools_used == [{"name": "get_weather_forecast", "args": {"city": "Berlin"}}]


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
