"""Runs one chat turn of the agent and reports whether it finished or waits for approval."""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src import config, family, privacy_check
from src.agent.graph import message_text


class InputRejected(ValueError):
    """The user's message was empty, too long or held sensitive data; no model call was made."""


@dataclass
class TurnResult:
    """What one run of the graph produced."""

    status: Literal["done", "needs_approval"]
    # Index of the turn's first message in the thread, so a resumed turn reports only its own.
    start_index: int = 0
    answer: str = ""
    pending_tool_calls: list[dict] = field(default_factory=list)
    needs_approval: list[str] = field(default_factory=list)
    tools_used: list[dict] = field(default_factory=list)
    # The app's own calculations in this turn (latest ticket comparison and budget check), shown
    # by the UI from the tool results, so money never depends on the model's text.
    calculations: dict[str, dict] = field(default_factory=dict)
    grounding: dict | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


def check_input(text: str) -> str:
    """Return the trimmed message, or raise InputRejected before any model call."""
    text = (text or "").strip()
    if not text:
        raise InputRejected("Please type a question.")
    if len(text) > config.MAX_USER_MESSAGE_CHARS:
        raise InputRejected(
            f"Please keep questions under {config.MAX_USER_MESSAGE_CHARS} characters."
        )
    # Unicode folding can make text much longer (one ligature becomes 18 letters), so the folded
    # length is capped too.
    if privacy_check.folded_length(text) > 2 * config.MAX_USER_MESSAGE_CHARS:
        raise InputRejected(
            "This message is too long once its special characters are spelled out. "
            "Please use plain letters."
        )
    findings = privacy_check.find_sensitive(text)
    if findings:
        raise InputRejected(privacy_check.explain(findings))
    return text


def decision_problem(decision: dict, original_calls: list[dict]) -> str | None:
    """Return a privacy warning when the parent's own text in a decision holds sensitive data."""
    # Only what the parent typed or changed is checked: the reject reason and edited values that
    # were not already in the model's arguments (the model's own text is not the parent's).
    known = {
        s.strip() for call in original_calls for s in privacy_check.string_values(call.get("args"))
    }
    too_long = "This is too long. Please keep the reason and your edits short."
    if privacy_check.json_depth(decision) > config.MAX_EDIT_DEPTH + 3:
        return too_long
    dumped = json.dumps(decision, ensure_ascii=False, default=str)
    if len(dumped) > config.MAX_DECISION_CHARS:
        return too_long
    if privacy_check.folded_length(dumped) > 2 * config.MAX_DECISION_CHARS:
        return too_long
    texts = [decision.get("feedback") or ""]
    # Only values the parent typed or changed; the model's own unchanged values are not capped.
    changed = [
        s
        for call in decision.get("tool_calls", [])
        for s in privacy_check.string_values(call.get("args"))
        if s.strip() not in known
    ]
    if any(len(s) > config.MAX_EDIT_VALUE_CHARS for s in changed):
        return "An edited value is too long. Please keep each value short."
    texts += changed
    findings = [f for text in texts for f in privacy_check.find_sensitive(text)]
    return privacy_check.explain(findings) if findings else None


def _run_config(thread_id: str, auto_approve: bool) -> dict:
    """Return the LangGraph run config for a conversation thread."""
    return {
        "configurable": {"thread_id": thread_id, "auto_approve": auto_approve},
        "recursion_limit": config.AGENT_RECURSION_LIMIT,
    }


def calculations(messages: list) -> dict[str, dict]:
    """Return the latest successful result of each calculation tool among the messages."""
    found: dict[str, dict] = {}
    for message in messages:
        if isinstance(message, ToolMessage) and message.name in config.CALCULATION_TOOLS:
            try:
                data = json.loads(message.content)
            except json.JSONDecodeError, TypeError:
                continue
            if isinstance(data, dict) and not data.get("error"):
                found[message.name] = data
    return found


def _summarise(graph, run_config: dict, start_index: int, started: float) -> TurnResult:
    """Read the graph's state after a run and build the turn's result."""
    snapshot = graph.get_state(run_config)
    messages = snapshot.values.get("messages", [])
    new = messages[start_index:]
    tools_used = [
        {"name": tc["name"], "args": tc["args"]}
        for m in new
        if isinstance(m, AIMessage)
        for tc in m.tool_calls
        if any(isinstance(t, ToolMessage) and t.tool_call_id == tc["id"] for t in new)
    ]
    usage = [m.usage_metadata for m in new if isinstance(m, AIMessage) and m.usage_metadata]
    result = TurnResult(
        status="done",
        start_index=start_index,
        tools_used=tools_used,
        calculations=calculations(new),
        input_tokens=sum(u.get("input_tokens", 0) for u in usage),
        output_tokens=sum(u.get("output_tokens", 0) for u in usage),
        seconds=round(time.perf_counter() - started, 2),
    )
    interrupts = [i for task in snapshot.tasks for i in task.interrupts]
    if interrupts:
        payload: dict[str, Any] = interrupts[0].value
        result.status = "needs_approval"
        result.pending_tool_calls = payload["tool_calls"]
        result.needs_approval = payload["needs_approval"]
        return result
    if messages and isinstance(messages[-1], AIMessage):
        result.answer = message_text(messages[-1])
    result.grounding = snapshot.values.get("grounding")
    return result


def _message_count(graph, run_config: dict) -> int:
    """Return how many messages the thread holds before this run."""
    return len(graph.get_state(run_config).values.get("messages", []))


def start_turn(
    graph,
    thread_id: str,
    text: str,
    *,
    country: str,
    city: str | None,
    children: list[str] | tuple[str, ...] = (),
    trip: dict | None = None,
    auto_approve: bool = False,
    turn_start_index: int | None = None,
) -> TurnResult:
    """Send the parent's message with the chosen context and run until done or a pause."""
    text = check_input(text)
    run_config = _run_config(thread_id, auto_approve)
    start = turn_start_index if turn_start_index is not None else _message_count(graph, run_config)
    started = time.perf_counter()
    graph.invoke(
        {
            "messages": [HumanMessage(text)],
            "country": country,
            "city": city,
            "children": list(family.check_bands(children)),
            "trip": trip,
            "grounding": None,
        },
        run_config,
    )
    return _summarise(graph, run_config, start, started)


def resume_turn(
    graph, thread_id: str, decision: dict, *, turn_start_index: int, auto_approve: bool = False
) -> TurnResult:
    """Resume a paused turn with the parent's decision (approve, edit or reject)."""
    if decision.get("action") not in ("approve", "edit", "reject"):
        raise ValueError("Unknown decision.")
    run_config = _run_config(thread_id, auto_approve)
    messages = graph.get_state(run_config).values.get("messages", [])
    pending = messages[-1].tool_calls if messages and isinstance(messages[-1], AIMessage) else []
    problem = decision_problem(decision, [dict(tc) for tc in pending])
    if problem:
        raise InputRejected(problem)
    started = time.perf_counter()
    graph.invoke(Command(resume=decision), run_config)
    return _summarise(graph, run_config, turn_start_index, started)
