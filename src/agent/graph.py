r"""The LangGraph agent: a tool-calling loop with a human-in-the-loop approval step and a
grounding check on every final answer.

    START -> agent --(tool calls that leave the app, not auto-approved)--> human_review
               |  \--(only internal tool calls, or auto-approved)--------> tools -> agent
               \--(final answer)--> grounding -> END

human_review pauses the graph with `interrupt()`. The UI shows the planned calls and resumes the
graph with the parent's decision: approve, edit the arguments, or reject with feedback.
"""

import json
from datetime import date
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from src import config
from src.grounding import allowed_urls, enforce_grounding

_SYSTEM_TEMPLATE = (config.PROMPTS_DIR / "agent_system.md").read_text(encoding="utf-8")


class AgentState(MessagesState):
    """The conversation plus the context chosen in the sidebar and the last grounding report."""

    country: str
    city: str | None
    child_age: int | None
    # Budget day trip settings (Germany): budget_eur, adults, children_ages,
    # deutschlandticket_holders. None when the parent has not switched trip planning on.
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
    ages = ", ".join(str(a) for a in trip.get("children_ages", [])) or "none"
    return (
        f"on · budget {trip['budget_eur']:.0f} EUR · adults (15+): {trip['adults']} · "
        f"children's ages: {ages} · Deutschlandticket holders: "
        f"{trip['deutschlandticket_holders']}"
    )


def system_prompt(state: AgentState, today: date | None = None) -> str:
    """Fill the system prompt with today's date, the chosen place, age and trip settings."""
    country = state.get("country") or "DE"
    age = state.get("child_age")
    today = today or date.today()
    return _SYSTEM_TEMPLATE.format(
        today=f"{today.isoformat()} ({today.strftime('%A')})",
        country=country,
        country_name=config.COUNTRIES.get(country, country),
        city=state.get("city") or "All cities",
        child_age=f"{age} years" if age is not None else "not given",
        trip=trip_context(state.get("trip")),
    )


def needs_approval(message: AIMessage) -> list[dict]:
    """Return the tool calls in a message that need the parent's approval."""
    return [tc for tc in message.tool_calls if tc["name"] in config.TOOLS_REQUIRING_APPROVAL]


def build_graph(llm: BaseChatModel, tools: list[BaseTool], checkpointer: BaseCheckpointSaver):
    """Compile the agent graph with its tools and a checkpointer (needed for interrupts)."""
    model = llm.bind_tools(tools)

    def agent(state: AgentState) -> dict:
        """Ask the model for the next step: tool calls or the final answer."""
        response = model.invoke([SystemMessage(system_prompt(state)), *state["messages"]])
        return {"messages": [response]}

    # LangGraph passes the run's config only to a parameter named `config`, which shadows the
    # settings module inside this one function.
    def route_after_agent(state: AgentState, config: RunnableConfig) -> str:  # noqa: F811
        """Route tool calls to review or to the tools, and answers to the grounding check."""
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return "grounding"
        auto = config.get("configurable", {}).get("auto_approve", False)
        return "tools" if auto or not needs_approval(last) else "human_review"

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
            calls = [{**tc, "args": edits.get(tc["id"], tc["args"])} for tc in last.tool_calls]
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
            )
            for tc in last.tool_calls
        ]
        return Command(goto="agent", update={"messages": rejected})

    def grounding(state: AgentState) -> dict:
        """Remove links that no tool returned from the final answer and record a report."""
        last: AIMessage = state["messages"][-1]
        cleaned, report = enforce_grounding(message_text(last), allowed_urls(state["messages"]))
        update: dict[str, Any] = {
            "grounding": {"verified": report.verified, "removed": report.removed}
        }
        if report.removed:
            # Same id, so the message is replaced; its token usage is kept for the cost report.
            update["messages"] = [last.model_copy(update={"content": cleaned})]
        return update

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
    return builder.compile(checkpointer=checkpointer)
