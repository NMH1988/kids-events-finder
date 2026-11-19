"""The Chat tab: the agent conversation, the human-in-the-loop approval panel and feedback."""

import json
import logging
import threading
import time
import uuid

import streamlit as st
from langgraph.checkpoint.memory import InMemorySaver

from src import config, services
from src.agent.runner import InputRejected, TurnResult, resume_turn, start_turn
from src.feedback import delete_shared_feedback, purge_old_feedback, save_feedback
from src.llm import MissingAPIKeyError
from src.tools.external import TRANSITOUS_SOURCES_URL
from src.tools.registry import RagSettings
from views.sidebar import Settings

logger = logging.getLogger(__name__)

TOOL_EXPLANATIONS = {
    "search_knowledge_base": "Searches the app's own curated list. Nothing leaves the app.",
    "find_nearby_places": "Sends the city and a place category to OpenStreetMap (Overpass API).",
    "search_family_events": "Sends the city, country and dates to Ticketmaster's event search.",
    "get_weather_forecast": "Sends the city, country and dates to Open-Meteo's weather service.",
    "find_train_connection": "Looks up the two towns with Open-Meteo, then sends their "
    "coordinates and the date and time to Transitous (journey planner, regional trains only).",
    "compare_train_tickets": "Compares day tickets from the app's own fare table. Nothing leaves "
    "the app.",
    "check_budget": "Adds up the costs inside the app. Fill in the amounts you know (entry fees, "
    "food); leave a cell empty if you don't know it yet.",
}
EXAMPLES = (
    "Rainy-day ideas for this weekend?",
    "Free things to do with a toddler",
    "Family events in the next two weeks",
    "Cuối tuần này cho bé đi đâu chơi?",
)
TRIP_EXAMPLES = (
    "Day trip by regional train this Saturday?",
    "Chuyến đi trong ngày bằng tàu, không quá ngân sách",
)


@st.cache_resource
def _checkpointer() -> InMemorySaver:
    """Return the in-memory checkpointer shared by all conversations (one thread each)."""
    return InMemorySaver()


@st.cache_resource(show_spinner="Loading the knowledge base…")
def _retriever():
    """Build the retriever once per app process."""
    return services.build_retriever()


@st.cache_resource
def _graph(model: str, multi_query: bool, rerank: bool):
    """Build the agent graph once per model and RAG settings."""
    return services.build_agent(
        model, RagSettings(multi_query=multi_query, rerank=rerank), _checkpointer(), _retriever()
    )


@st.cache_resource
def _thread_activity() -> dict[str, float]:
    """Return when each conversation thread was last used (shared by all sessions)."""
    return {}


def _forget_old_threads(now: float | None = None) -> None:
    """Delete conversations from server memory that were idle longer than the retention limit."""
    activity = _thread_activity()
    now = now or time.time()
    for thread_id, last_used in list(activity.items()):
        if now - last_used > config.CONVERSATION_RETENTION_SECONDS:
            _checkpointer().delete_thread(thread_id)
            activity.pop(thread_id, None)


def _cleanup_loop() -> None:
    """Every few minutes, delete idle conversations and expired feedback, even with no visitors."""
    while True:
        try:
            _forget_old_threads()
            purge_old_feedback()
        except Exception as exc:  # noqa: BLE001 - keep the cleaner alive; log only the type
            logger.warning("cleanup_failed", extra={"type": type(exc).__name__})
        time.sleep(config.CLEANUP_INTERVAL_SECONDS)


@st.cache_resource
def start_cleaner() -> threading.Thread:
    """Start the background cleaner once per app process (called from app.py)."""
    thread = threading.Thread(target=_cleanup_loop, name="retention-cleaner", daemon=True)
    thread.start()
    return thread


def end_conversation(thread_id: str | None) -> None:
    """Delete a conversation from server memory ("New conversation"), not only from the page."""
    if thread_id:
        _checkpointer().delete_thread(thread_id)
        _thread_activity().pop(thread_id, None)


def _state() -> dict:
    """Return the chat's session state, creating it on first use."""
    start_cleaner()
    ss = st.session_state
    end_conversation(ss.pop("delete_thread", None))
    if "thread_id" in ss and ss.thread_id not in _thread_activity() and ss.get("history"):
        # The cleaner deleted this idle conversation: drop the page's copy too.
        for key in ("thread_id", "history", "pending", "feedback_saved"):
            ss.pop(key, None)
    ss.setdefault("thread_id", str(uuid.uuid4()))
    _thread_activity()[ss.thread_id] = time.time()
    ss.setdefault("history", [])
    ss.setdefault("pending", None)
    ss.setdefault("feedback_saved", set())
    # Random id of this browser session; stored only with feedback the parent chose to share.
    ss.setdefault("feedback_session", uuid.uuid4().hex)
    return ss


@st.fragment(run_every=config.CLEANUP_INTERVAL_SECONDS)
def _watch_retention() -> None:
    """While the tab stays open, drop the page's copy once the cleaner deleted the conversation."""
    ss = st.session_state
    if ss.get("history") and ss.get("thread_id") not in _thread_activity():
        st.rerun(scope="app")


def _store_result(result: TurnResult, question: str, model: str) -> None:
    """Keep a finished answer in the history, or the pending approval in the session."""
    ss = st.session_state
    if result.status == "needs_approval":
        ss.pending = {"result": result, "question": question}
        return
    ss.pending = None
    ss.history.append(
        {
            "role": "assistant",
            "content": result.answer,
            "question": question,
            "model": model,
            "tools": result.tools_used,
            "grounding": result.grounding,
            "tokens": (result.input_tokens, result.output_tokens),
            "seconds": result.seconds,
        }
    )


def _render_details(message: dict) -> None:
    """Show how an answer was made: tools, grounding check, tokens and time."""
    grounding = message.get("grounding") or {}
    removed, verified = grounding.get("removed", []), grounding.get("verified", [])
    if removed:
        st.warning(f"⚠️ {len(removed)} link(s) were not in any tool result and were removed.")
    elif verified:
        st.caption(
            f"✅ All {len(verified)} links come from tool results (official websites, maps, "
            "OpenStreetMap, Ticketmaster); outside data, so check them before you go."
        )
    with st.expander("How this answer was made"):
        tools = message.get("tools") or []
        if tools:
            for tool in tools:
                # Model-written names and arguments are shown as plain code, never as Markdown,
                # so a backtick in them cannot open a link or an image.
                st.code(
                    f"{tool['name']} {json.dumps(tool['args'], ensure_ascii=False)}",
                    language=None,
                )
        else:
            st.markdown("- No tools were called.")
        if any(t["name"] == "find_train_connection" for t in tools):
            st.caption(f"Journeys by [Transitous]({TRANSITOUS_SOURCES_URL}) and its data sources.")
        tin, tout = message.get("tokens", (0, 0))
        st.caption(
            f"{message.get('model')} · {tin} input / {tout} output tokens · "
            f"{message.get('seconds')} s"
        )


def _render_feedback(index: int, message: dict, settings: Settings) -> None:
    """Show thumbs up/down under an answer and save the rating once."""
    key = f"{st.session_state.thread_id}_{index}"
    share = st.checkbox(
        "Also share my question and this answer: stored on this app's server only to improve "
        f"the answers, deleted after {config.FEEDBACK_RETENTION_DAYS} days. You can delete it "
        "again with the button at the end of the chat while this page is open.",
        value=False,
        key=f"fb_share_{key}",
    )
    rating = st.feedback("thumbs", key=f"fb_{key}")
    saved: set = st.session_state.feedback_saved
    if rating is not None and index not in saved:
        save_feedback(
            rating,
            message.get("question", ""),
            message["content"],
            model=message.get("model", ""),
            country=settings.country,
            tools_used=[t["name"] for t in message.get("tools") or []],
            grounded=not (message.get("grounding") or {}).get("removed"),
            share_text=share,
            session_id=st.session_state.feedback_session,
        )
        if share:
            st.session_state.shared_feedback = True
        saved.add(index)
        st.toast("Thanks for the feedback!")


def _budget_editor(call: dict) -> dict:
    """Let the parent fill in or correct the budget items; return the edited arguments."""
    args = call["args"]
    budget = st.number_input(
        "Budget (EUR)",
        min_value=float(config.BUDGET_RANGE_EUR[0]),
        max_value=float(config.BUDGET_RANGE_EUR[1]),
        value=float(args.get("budget_eur") or 0),
        key=f"budget_{call['id']}",
    )
    rows = [
        {
            "label": i.get("label", ""),
            "amount_eur": i.get("amount_eur"),
            "note": i.get("note", ""),
        }
        for i in args.get("items", [])
    ]
    table = st.data_editor(
        rows,
        num_rows="dynamic",
        key=f"items_{call['id']}",
        column_config={
            "label": st.column_config.TextColumn("Cost", required=True, max_chars=80),
            "amount_eur": st.column_config.NumberColumn(
                "Amount (EUR)", min_value=0.0, max_value=float(config.BUDGET_RANGE_EUR[1])
            ),
            "note": st.column_config.TextColumn("Note", max_chars=160),
        },
        use_container_width=True,
    )
    st.caption(
        "Amounts already filled in were written by the AI (for example the ticket price from the "
        "fare comparison). Please check every amount; leave a cell empty if you don't know it."
    )
    items = [
        {
            "label": str(r["label"]).strip(),
            "amount_eur": None if r.get("amount_eur") in (None, "") else float(r["amount_eur"]),
            "note": r.get("note") or "",
        }
        for r in table
        if r.get("label") and str(r["label"]).strip()
    ]
    return {"budget_eur": float(budget), "items": items}


def _render_approval(settings: Settings) -> None:
    """Show the planned tool calls and let the parent approve, edit or reject them."""
    pending = st.session_state.pending
    result: TurnResult = pending["result"]
    with st.chat_message("assistant", avatar="🛑"):
        st.markdown("**The agent is waiting for you. Do you approve these steps?**")
        edited: list[dict] = []
        # What "Approve" runs: the original arguments, except the parent's budget table.
        approved: list[dict] = []
        bad_json = False
        has_budget = False
        for call in result.pending_tool_calls:
            with st.container(border=True):
                needs = call["id"] in result.needs_approval
                st.text(f"{'🌍' if needs else '📚'} {call['name']}")
                st.caption(TOOL_EXPLANATIONS.get(call["name"], ""))
                if call["name"] == "check_budget":
                    has_budget = True
                    budget_args = {"id": call["id"], "args": _budget_editor(call)}
                    edited.append(budget_args)
                    approved.append(budget_args)
                    continue
                approved.append({"id": call["id"], "args": call["args"]})
                text = st.text_area(
                    "Arguments (you can edit them)",
                    json.dumps(call["args"], indent=2, ensure_ascii=False),
                    key=f"args_{call['id']}",
                    height=130,
                )
                try:
                    edited.append({"id": call["id"], "args": json.loads(text)})
                except json.JSONDecodeError:
                    bad_json = True
                    edited.append({"id": call["id"], "args": call["args"]})
                    st.error("This is not valid JSON. Approve will send the original arguments.")
        feedback = st.text_input(
            "Reason if you reject (optional)",
            key="reject_reason",
            placeholder="e.g. only indoor places, please",
        )
        c1, c2, c3 = st.columns(3)
        decision = None
        if c1.button("✅ Approve", type="primary", use_container_width=True):
            # Approve runs the original arguments; with a budget call, the parent's table is part
            # of approving, so their amounts always replace the model's.
            decision = (
                {"action": "edit", "tool_calls": approved} if has_budget else {"action": "approve"}
            )
        if c2.button("✏️ Run with my edits", disabled=bad_json, use_container_width=True):
            decision = {"action": "edit", "tool_calls": edited}
        if c3.button("❌ Reject", use_container_width=True):
            decision = {"action": "reject", "feedback": feedback}
    if decision:
        _run(
            lambda graph: resume_turn(
                graph,
                st.session_state.thread_id,
                decision,
                turn_start_index=result.start_index,
                auto_approve=settings.auto_approve,
            ),
            pending["question"],
            settings,
        )


def _run(step, question: str, settings: Settings) -> None:
    """Run a graph step with a spinner, store its result and redraw the page."""
    try:
        graph = _graph(settings.model, settings.multi_query, settings.rerank)
        with st.spinner("Searching for ideas…"):
            result = step(graph)
    except InputRejected as exc:
        st.warning(str(exc))
        return
    except MissingAPIKeyError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 - shown as a fixed message, never the error's text
        logger.warning("turn_failed", extra={"type": type(exc).__name__})
        st.error("Something went wrong while calling the model service. Please try again.")
        return
    _store_result(result, question, settings.model)
    st.rerun()


def render_chat(settings: Settings) -> None:
    """Draw the conversation, the approval panel when the agent waits, and the input box."""
    ss = _state()
    if not config.get_api_key():
        st.info(
            f"Add `{config.API_KEY_NAME}` to `.streamlit/secrets.toml` to use the chat agent. "
            "The Browse tab works without it."
        )
        return

    if not ss.history and not ss.pending:
        st.markdown("Ask about outings for your child. Try one of these:")
        examples = TRIP_EXAMPLES + EXAMPLES[:2] if settings.trip else EXAMPLES
        cols = st.columns(len(examples))
        for col, example in zip(cols, examples, strict=True):
            if col.button(example, use_container_width=True):
                ss.queued_question = example
                st.rerun()

    for i, message in enumerate(ss.history):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                # Answers passed the grounding check; the parent's own text is shown as plain text.
                st.markdown(message["content"])
            else:
                st.text(message["content"])
            if message["role"] == "assistant":
                _render_details(message)
                _render_feedback(i, message, settings)

    if ss.pending:
        _render_approval(settings)

    if ss.get("shared_feedback") and st.button("🗑️ Delete the questions and answers I shared"):
        deleted = delete_shared_feedback(ss.feedback_session)
        ss.shared_feedback = False
        st.toast(f"Deleted {deleted} shared record(s).")

    _watch_retention()
    typed = st.chat_input("Ask about events and places for kids…", disabled=bool(ss.pending))
    question = typed or ss.pop("queued_question", None)
    if question and not ss.pending:
        ss.history.append({"role": "user", "content": question})
        _run(
            lambda graph: start_turn(
                graph,
                ss.thread_id,
                question,
                country=settings.country,
                city=settings.city,
                children=settings.children,
                trip=settings.trip,
                auto_approve=settings.auto_approve,
            ),
            question,
            settings,
        )
