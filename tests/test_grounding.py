"""Tests for the grounding check that removes links no tool returned."""

import json

from langchain_core.messages import HumanMessage, ToolMessage

from src.grounding import allowed_urls, enforce_grounding


def _tool(payload: dict) -> ToolMessage:
    """Build a tool message holding a JSON payload."""
    return ToolMessage(content=json.dumps(payload), tool_call_id="1", name="t")


def test_allowed_urls_collects_nested_links_from_tool_messages_only():
    """Links come from tool results, never from the user's message."""
    messages = [
        HumanMessage("see https://evil.example"),
        _tool({"results": [{"website": "https://a.org", "maps_url": "https://maps/x?y=1"}]}),
    ]
    assert allowed_urls(messages) == {"https://a.org", "https://maps/x?y=1"}


def test_verified_links_stay_and_invented_ones_are_removed():
    """A link from a tool stays; an invented one becomes plain text and is reported."""
    answer = "[Website](https://a.org/) and [Fake](https://invented.example/page) see https://b.org"
    cleaned, report = enforce_grounding(answer, {"https://a.org"})
    assert "[Website](https://a.org/)" in cleaned
    assert "invented.example" not in cleaned and "b.org" not in cleaned
    assert report.removed == ["https://invented.example/page", "https://b.org"]
    assert not report.grounded


def test_answer_without_links_is_grounded():
    """An answer with no links passes unchanged."""
    cleaned, report = enforce_grounding("No links here.", set())
    assert cleaned == "No links here." and report.grounded
