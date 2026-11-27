"""Runs one chat turn of the agent and reports whether it finished or waits for approval."""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src import config, family, memory, privacy_check
from src.agent.graph import goes_to_review, message_text
from src.safe_text import clean_decision

logger = logging.getLogger(__name__)

# Receives one fixed progress label at a time (config.PROGRESS_*), never model or tool text.
ProgressCallback = Callable[[str], None]


class InputRejected(ValueError):
    """The user's message was empty, too long or held sensitive data; no model call was made."""


class StaleDecision(InputRejected):
    """The parent decided on a pause the conversation no longer waits on; nothing was run."""

    def __init__(self, message: str, current: TurnResult | None = None) -> None:
        """Keep the pause the conversation waits on now (None when it waits on none)."""
        super().__init__(message)
        self.current = current


@dataclass
class TurnResult:
    """What one run of the graph produced."""

    status: Literal["done", "needs_approval"]
    # Index of the turn's first message in the thread, so a resumed turn reports only its own.
    start_index: int = 0
    answer: str = ""
    pending_tool_calls: list[dict] = field(default_factory=list)
    needs_approval: list[str] = field(default_factory=list)
    # The id LangGraph gives this pause; unique per pause, unlike the model's tool-call ids.
    pause_id: str | None = None
    # Every answered tool call: name, args and "ran" (False when the parent rejected it); a memory
    # save also has "saved" (True only when its result holds the saved preference). T5.7.
    tools_used: list[dict] = field(default_factory=list)
    # The app's own calculations in this turn (latest ticket comparison and budget check), shown
    # by the UI from the tool results, so money never depends on the model's text.
    calculations: dict[str, dict] = field(default_factory=dict)
    grounding: dict | None = None
    # Preferences saved to long-term memory in this turn (topic and feeling), shown by the UI.
    remembered: list[dict] = field(default_factory=list)
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
    reason = decision.get("feedback") or ""
    if not isinstance(reason, str) or len(reason) > config.MAX_REJECT_REASON_CHARS:
        return too_long
    texts = [reason]
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


def _run_config(thread_id: str, auto_approve: bool, memory_on: bool = False) -> dict:
    """Return the LangGraph run config for a conversation thread and the sidebar switches."""
    return {
        "configurable": {
            "thread_id": thread_id,
            "auto_approve": auto_approve,
            "memory_on": bool(memory_on),
        },
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


def saved_entry(message: ToolMessage) -> dict | None:
    """Return the preference a `remember_preference` result says it saved, or None."""
    try:
        data = json.loads(message.content)
    except json.JSONDecodeError, TypeError:
        return None
    if isinstance(data, dict) and isinstance(data.get("saved"), dict):
        return data["saved"]
    return None


def remembered(messages: list) -> list[dict]:
    """Return the preferences `remember_preference` saved, the last one per topic (as stored)."""
    saved: dict[str, dict] = {}
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == "remember_preference":
            entry = saved_entry(message)
            if entry is not None:
                saved.pop(entry.get("topic"), None)
                saved[entry.get("topic")] = entry
    return list(saved.values())


def tool_runs(messages: list) -> list[dict]:
    """Return each answered tool call with whether it ran (and, for a memory save, was saved)."""
    used = []
    for i, message in enumerate(messages):
        if not isinstance(message, AIMessage):
            continue
        # Only the results right after this step: the model's call ids can repeat in a later
        # step, whose rejection must not mark this step's calls (legal and security round 1).
        results: dict[str, list[ToolMessage]] = {}
        for later in messages[i + 1 :]:
            if not isinstance(later, ToolMessage):
                break
            results.setdefault(later.tool_call_id, []).append(later)
        for tc in message.tool_calls:
            answers = results.get(tc["id"])
            if not answers:
                continue
            # Known from the fixed marker `human_review` sets, never from the result's text.
            ran = not any(t.artifact == config.REJECTED_BY_PARENT for t in answers)
            entry = {"name": tc["name"], "args": tc["args"], "ran": ran}
            if tc["name"] == "remember_preference":
                # The tool also refuses an approved save (memory off, a topic the parent did not
                # name, ...): saved only when its result says so, as `remembered()` reads it.
                entry["saved"] = ran and any(
                    t.name == "remember_preference" and saved_entry(t) is not None for t in answers
                )
            used.append(entry)
    return used


def _summarise(graph, run_config: dict, start_index: int, started: float) -> TurnResult:
    """Read the graph's state after a run and build the turn's result."""
    snapshot = graph.get_state(run_config)
    messages = snapshot.values.get("messages", [])
    new = messages[start_index:]
    tools_used = tool_runs(new)
    usage = [m.usage_metadata for m in new if isinstance(m, AIMessage) and m.usage_metadata]
    result = TurnResult(
        status="done",
        start_index=start_index,
        tools_used=tools_used,
        calculations=calculations(new),
        remembered=remembered(new),
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
        result.pause_id = interrupts[0].id
        return result
    if messages and isinstance(messages[-1], AIMessage):
        result.answer = message_text(messages[-1])
    result.grounding = snapshot.values.get("grounding")
    return result


def waiting_pause(snapshot) -> tuple[str, list[str]] | None:
    """Return the pause the thread waits on (its id and the call ids), or None if it waits not."""
    interrupts = [i for task in snapshot.tasks for i in task.interrupts]
    if not interrupts:
        return None
    return interrupts[0].id, [tc["id"] for tc in interrupts[0].value.get("tool_calls", [])]


def _message_count(graph, run_config: dict) -> int:
    """Return how many messages the thread holds before this run."""
    return len(graph.get_state(run_config).values.get("messages", []))


def tool_label(name: str) -> str:
    """Return the app's own progress label for a tool; unknown names get a generic label."""
    return config.PROGRESS_TOOL_LABELS.get(name, config.PROGRESS_UNKNOWN_TOOL)


def tool_labels(calls: list[dict], memory_on: bool) -> list[str]:
    """Return the progress labels for tool calls about to run, in the app's own words."""
    # With memory off the memory tool refuses to save, so it is not shown as
    # "Remembering your preference" (code review T5.11 rounds 7 and 8).
    return [
        tool_label(tc["name"]) for tc in calls if memory_on or tc["name"] != "remember_preference"
    ]


def progress_labels(chunk: dict, auto_approve: bool = False, memory_on: bool = False) -> list[str]:
    """Turn one streamed graph update into fixed progress labels (no model or tool text)."""
    labels: list[str] = []
    for node, update in chunk.items():
        if node == "__interrupt__":
            labels.append(config.PROGRESS_APPROVAL)
        elif node == "agent":
            messages = (update or {}).get("messages") or []
            last = messages[-1] if messages else None
            if not isinstance(last, AIMessage) or not last.tool_calls:
                labels.append(config.PROGRESS_GROUNDING)
            elif goes_to_review(last, auto_approve, memory_on):
                continue  # the graph pauses next; the interrupt reports it
            else:
                labels += tool_labels(last.tool_calls, memory_on)
        elif node == "tools":
            labels.append(config.PROGRESS_NEXT_STEP)
    return labels


def _execute(
    graph, graph_input, run_config: dict, progress: ProgressCallback | None, auto: bool
) -> None:
    """Run the graph until it ends or pauses, reporting each step's label as it finishes."""
    memory_on = memory.switched_on(run_config)
    for chunk in graph.stream(graph_input, run_config, stream_mode="updates"):
        if progress and isinstance(chunk, dict):
            progress = _report(progress, progress_labels(chunk, auto, memory_on))


def _report(progress: ProgressCallback, labels: list[str]) -> ProgressCallback | None:
    """Pass labels to the callback; a failing callback is dropped so it never cuts a turn."""
    try:
        for label in labels:
            progress(label)
    except Exception as exc:  # noqa: BLE001 - progress is optional; the graph must finish its run
        logger.warning("progress_failed", extra={"type": type(exc).__name__})
        return None
    return progress


def start_turn(
    graph,
    thread_id: str,
    text: str,
    *,
    country: str,
    city: str | None,
    children: list[str] | tuple[str, ...] = (),
    trip: dict | None = None,
    memory_on: bool = False,
    auto_approve: bool = False,
    turn_start_index: int | None = None,
    progress: ProgressCallback | None = None,
) -> TurnResult:
    """Send the parent's message with the chosen context and run until done or a pause."""
    text = check_input(text)
    run_config = _run_config(thread_id, auto_approve, memory_on)
    start = turn_start_index if turn_start_index is not None else _message_count(graph, run_config)
    started = time.perf_counter()
    if progress:
        progress = _report(progress, [config.PROGRESS_START])
    _execute(
        graph,
        {
            "messages": [HumanMessage(text)],
            "country": country,
            "city": city,
            "children": list(family.check_bands(children)),
            "trip": trip,
            "grounding": None,
        },
        run_config,
        progress,
        auto_approve,
    )
    return _summarise(graph, run_config, start, started)


def resume_turn(
    graph,
    thread_id: str,
    decision: dict,
    *,
    turn_start_index: int,
    auto_approve: bool = False,
    memory_on: bool = False,
    progress: ProgressCallback | None = None,
    expected_ids: list[str] | None = None,
    expected_pause: str | None = None,
) -> TurnResult:
    """Resume a paused turn with the parent's decision (approve, edit or reject)."""
    if decision.get("action") not in ("approve", "edit", "reject"):
        raise ValueError("Unknown decision.")
    # The parent's edits and reason may hold a lone surrogate (a JSON edit can write the escape
    # of one): replaced before any check or the graph sees it (T5.7).
    decision = clean_decision(decision)
    run_config = _run_config(thread_id, auto_approve, memory_on)
    snapshot = graph.get_state(run_config)
    # Resume only a thread that waits for the parent, and (when the page says which pause and
    # calls it showed) on exactly that pause. Otherwise a stale panel's decision would run what
    # the thread holds next: a later call the parent never saw, or a call left by a failed run.
    # The pause id is LangGraph's own; the call ids are the model's and could repeat.
    waiting = waiting_pause(snapshot)
    if (
        waiting is None
        or (expected_pause is not None and expected_pause != waiting[0])
        or (expected_ids is not None and list(expected_ids) != waiting[1])
    ):
        current = (
            _summarise(graph, run_config, turn_start_index, time.perf_counter())
            if waiting
            else None
        )
        raise StaleDecision(
            "The steps changed or ended while you were deciding. Please check what is shown "
            "now, or ask again.",
            current,
        )
    messages = snapshot.values.get("messages", [])
    pending = messages[-1].tool_calls if messages and isinstance(messages[-1], AIMessage) else []
    problem = decision_problem(decision, [dict(tc) for tc in pending])
    if problem:
        raise InputRejected(problem)
    started = time.perf_counter()
    if progress:
        first = (
            [config.PROGRESS_NEXT_STEP]
            if decision["action"] == "reject"
            else tool_labels(pending, memory_on)
        )
        progress = _report(progress, first)
    _execute(graph, Command(resume=decision), run_config, progress, auto_approve)
    return _summarise(graph, run_config, turn_start_index, started)
