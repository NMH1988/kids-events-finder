r"""The LangGraph agent: a tool-calling loop with a human-in-the-loop approval step and a
grounding check on every final answer.

    START -> agent --(tool calls that leave the app, not auto-approved)--> human_review
               |  \--(only internal tool calls, or auto-approved)--------> tools -> agent
               \--(final answer)--> grounding -> END

human_review pauses the graph with `interrupt()`. The UI shows the planned calls and resumes the
graph with the parent's decision: approve, edit the arguments, or reject with feedback.

Memory: the checkpointer keeps each conversation (short-term; the model sees its trimmed history),
and the store keeps the family's preferences across conversations when the parent switched
long-term memory on (T5.11).
"""

import json
from datetime import date
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, interrupt

from src import config, family, memory
from src.grounding import allowed_urls, enforce_grounding
from src.safe_text import clean_ai_message

_SYSTEM_TEMPLATE = (config.PROMPTS_DIR / "agent_system.md").read_text(encoding="utf-8")


class AgentState(MessagesState):
    """The conversation plus the context chosen in the sidebar and the last grounding report."""

    country: str
    city: str | None
    # Children's age groups only ("Child 1", "Child 2" by position); never names or exact ages.
    children: list[str]
    # Budget day trip settings (Germany): budget_eur, adults, deutschlandticket_holders.
    # None when the parent has not switched trip planning on.
    trip: dict | None
    grounding: dict | None


def message_text(message: AIMessage) -> str:
    """Return the text of a model message whose content may be a string or content blocks."""
    if isinstance(message.content, str):
        return message.content
    return "".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in message.content
    )


def trip_context(trip: dict | None) -> str:
    """Describe the budget day trip settings for the system prompt."""
    if not trip:
        return "off (the parent has not switched on budget day trip planning)"
    return (
        f"on · budget {trip['budget_eur']:g} EUR · adults: {trip['adults']} · "
        f"Deutschlandticket holders (aged 15+): {trip['deutschlandticket_holders']}"
    )


def system_prompt(
    state: AgentState,
    today: date | None = None,
    store: BaseStore | None = None,
    memory_on: bool = False,
) -> str:
    """Fill the system prompt with the date, place, children, trip settings and preferences."""
    country = state.get("country") or "DE"
    today = today or date.today()
    return _SYSTEM_TEMPLATE.format(
        today=f"{today.isoformat()} ({today.strftime('%A')})",
        country=country,
        country_name=config.COUNTRIES.get(country, country),
        city=state.get("city") or "All cities",
        children=family.describe_children(state.get("children") or []),
        trip=trip_context(state.get("trip")),
        memory=memory.describe(store, memory_on),
    )


def history_for_model(
    messages: list[AnyMessage], max_tokens: int | None = None
) -> list[AnyMessage]:
    """Return the messages the model sees: the latest question whole, earlier turns trimmed."""
    max_tokens = max_tokens or config.MAX_HISTORY_TOKENS
    last_question = next(
        (i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)),
        None,
    )
    if last_question is None:
        return list(messages)
    current = list(messages[last_question:])
    budget = max_tokens - count_tokens_approximately(current)
    if budget <= 0 or last_question == 0:
        return current
    # Earlier turns are cut from the oldest end, at a question, so a tool call is never separated
    # from its result.
    earlier = trim_messages(
        messages[:last_question],
        max_tokens=budget,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
    )
    return [*earlier, *current]


def needs_approval(message: AIMessage) -> list[dict]:
    """Return the tool calls in a message that need the parent's approval."""
    return [tc for tc in message.tool_calls if tc["name"] in config.TOOLS_REQUIRING_APPROVAL]


def always_reviewed(message: AIMessage, memory_on: bool = True) -> bool:
    """Return True when a message calls a tool that pauses even with auto-approve on."""
    # With memory off the memory tool only refuses, so it is not worth a pause.
    return any(
        tc["name"] in config.TOOLS_ALWAYS_REVIEWED
        and (memory_on or tc["name"] != "remember_preference")
        for tc in message.tool_calls
    )


def goes_to_review(message: AIMessage, auto_approve: bool, memory_on: bool = True) -> bool:
    """Return True when the graph pauses for the parent before running this message's tools."""
    return always_reviewed(message, memory_on) or (
        bool(needs_approval(message)) and not auto_approve
    )


def _edited_args(call: dict, edits: dict[str, dict], fields: dict[str, set[str]]) -> dict:
    """Return a call's arguments after the parent's edit, keeping only the tool's own fields."""
    # Extra keys typed into the JSON editor would stay in the history the model reads, so only
    # fields the tool schema knows (or the original call had) are kept.
    edit = edits.get(call["id"])
    if not isinstance(edit, dict):
        return call["args"]
    allowed = set(call["args"]) | fields.get(call["name"], set())
    return {k: v for k, v in edit.items() if k in allowed}


def build_graph(
    llm: BaseChatModel,
    tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver,
    store: BaseStore | None = None,
):
    """Compile the agent graph with its tools, a checkpointer (for interrupts) and a store."""
    model = llm.bind_tools(tools)
    # The argument names the model may use for each tool (injected fields are not among them).
    fields = {t.name: set(getattr(t.tool_call_schema, "model_fields", {}) or {}) for t in tools}

    # LangGraph passes the run's config only to a parameter named `config`, which shadows the
    # settings module inside these functions.
    def agent(state: AgentState, config: RunnableConfig, store: BaseStore) -> dict:  # noqa: F811
        """Ask the model for the next step: tool calls or the final answer."""
        # The memory switch is read from the run's config at every step, so switching it off
        # during an approval pause takes effect at once (LEGAL_COMPLIANCE 2.8, 2.11).
        prompt = system_prompt(state, store=store, memory_on=memory.switched_on(config))
        response = model.invoke([SystemMessage(prompt), *history_for_model(state["messages"])])
        # A lone surrogate in the model's text, tool calls or ids would break the next model
        # request and the stored history (T5.7): it becomes U+FFFD before anything uses it.
        if isinstance(response, AIMessage):
            response = clean_ai_message(response)
        return {"messages": [response]}

    def route_after_agent(state: AgentState, config: RunnableConfig) -> str:  # noqa: F811
        """Route tool calls to review or to the tools, and answers to the grounding check."""
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return "grounding"
        auto = config.get("configurable", {}).get("auto_approve", False)
        review = goes_to_review(last, auto, memory.switched_on(config))
        return "human_review" if review else "tools"

    def human_review(state: AgentState) -> Command:
        """Pause for the parent's decision on the planned tool calls, then apply it."""
        last: AIMessage = state["messages"][-1]
        decision: dict[str, Any] = interrupt(
            {
                "tool_calls": [dict(tc) for tc in last.tool_calls],
                "needs_approval": [tc["id"] for tc in needs_approval(last)],
            }
        )
        action = decision.get("action")
        if action == "approve":
            return Command(goto="tools")
        if action == "edit":
            edits = {e["id"]: e["args"] for e in decision.get("tool_calls", [])}
            calls = [{**tc, "args": _edited_args(tc, edits, fields)} for tc in last.tool_calls]
            edited = AIMessage(content=last.content, tool_calls=calls, id=last.id)
            return Command(goto="tools", update={"messages": [edited]})
        feedback = (decision.get("feedback") or "").strip() or "No reason given."
        rejected = [
            ToolMessage(
                content=json.dumps(
                    {"error": f"The parent rejected this tool call. Feedback: {feedback}"}
                ),
                tool_call_id=tc["id"],
                name=tc["name"],
                # The app's fixed marker that this call did not run (T5.7).
                artifact=config.REJECTED_BY_PARENT,
            )
            for tc in last.tool_calls
        ]
        return Command(goto="agent", update={"messages": rejected})

    def grounding(state: AgentState) -> dict:
        """Remove links that no tool returned from the final answer and record a report."""
        last: AIMessage = state["messages"][-1]
        cleaned, report = enforce_grounding(message_text(last), allowed_urls(state["messages"]))
        # The cleaned text is always stored: even with nothing removed, link syntax is escaped.
        # Same id, so the message is replaced; its token usage is kept for the cost report.
        return {
            "grounding": {"verified": report.verified, "removed": report.removed},
            "messages": [last.model_copy(update={"content": cleaned})],
        }

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent)
    builder.add_node("human_review", human_review, destinations=("tools", "agent"))
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("grounding", grounding)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", route_after_agent, ["human_review", "tools", "grounding"]
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("grounding", END)
    # Without a store (tests, evaluation scripts) the memory lives only as long as the graph.
    return builder.compile(
        checkpointer=checkpointer, store=store if store is not None else InMemoryStore()
    )
