"""Replaces lone surrogates in model output and the parent's decision with U+FFFD.

A lone surrogate (U+D800-U+DFFF on its own) cannot be written as UTF-8: a model request that
holds one fails, and the checkpointer silently turns it into "?" when it saves. Every AI message
the agent node returns, the parent's decision and every tool result pass through here first.
"""

import hashlib
import json
import re
from typing import Any

from langchain_core.messages import AIMessage

REPLACEMENT = "�"
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
# Length of the hash added to an id that held a lone surrogate.
_ID_HASH_CHARS = 12


def clean_text(value: Any) -> Any:
    """Return the value with every lone surrogate in its strings (also string keys) replaced."""
    if isinstance(value, str):
        return _LONE_SURROGATE.sub(REPLACEMENT, value)
    if isinstance(value, dict):
        # Only string keys are cleaned; any other key is kept as it is, so a key the depth
        # check does not look at is never walked (security round 4 of PR #48).
        return {
            (_LONE_SURROGATE.sub(REPLACEMENT, k) if isinstance(k, str) else k): clean_text(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [clean_text(v) for v in value]
    if isinstance(value, tuple):
        return tuple(clean_text(v) for v in value)
    return value


def short_hash(text: str) -> str:
    """Return a short, plain hash of any text, also one holding a lone surrogate."""
    # json.dumps escapes every character outside ASCII (a lone surrogate too), so encoding
    # never fails and the hash is taken from the original text.
    return hashlib.sha256(json.dumps(text).encode("ascii")).hexdigest()[:_ID_HASH_CHARS]


def clean_id(value: Any) -> Any:
    """Return an id without lone surrogates; distinct ids stay distinct, equal ones equal."""
    if not isinstance(value, str) or not _LONE_SURROGATE.search(value):
        return value
    # Replacing alone could make "a\ud800" equal to "a\udc00" or to a real "a�", and the
    # approval panel and the tool results tell calls (and the history its messages) apart by id.
    return f"{clean_text(value)}-{short_hash(value)}"


def _clean_call(call: dict) -> dict:
    """Return a tool call (valid or invalid) with its name, arguments and id cleaned."""
    cleaned = {k: clean_text(v) for k, v in call.items() if k != "id"}
    if "id" in call:
        cleaned["id"] = clean_id(call["id"])
    return cleaned


def clean_ai_message(message: AIMessage) -> AIMessage:
    """Return the model's message with every lone surrogate replaced, ids kept apart."""
    return message.model_copy(
        update={
            "content": clean_text(message.content),
            "additional_kwargs": clean_text(message.additional_kwargs),
            "response_metadata": clean_text(message.response_metadata),
            "name": clean_text(message.name),
            # Two message ids that became equal would make the history replace one step by the
            # other (security round 1).
            "id": clean_id(message.id),
            "tool_calls": [_clean_call(tc) for tc in message.tool_calls],
            "invalid_tool_calls": [_clean_call(tc) for tc in message.invalid_tool_calls],
        }
    )


def clean_decision(decision: dict) -> dict:
    """Return the parent's decision (edited arguments, reject reason) without lone surrogates."""
    cleaned = {k: clean_text(v) for k, v in decision.items() if k != "tool_calls"}
    if "tool_calls" in decision:
        calls = decision["tool_calls"]
        cleaned["tool_calls"] = (
            [_clean_call(c) if isinstance(c, dict) else clean_text(c) for c in calls]
            if isinstance(calls, list)
            else clean_text(calls)
        )
    return cleaned
