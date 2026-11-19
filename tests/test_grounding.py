"""Tests for the grounding check that removes links and images no tool returned."""

import json

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from src.grounding import allowed_urls, enforce_grounding

ALLOWED = {"https://a.org", "https://www.google.com/maps/dir/?api=1&destination=Zoo%2C+Berlin"}


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


def test_tool_error_text_cannot_make_a_link_verified():
    """A non-JSON tool result (an error echoing the model's arguments) gives no allowed URLs."""
    error = ToolMessage(
        content="Error invoking tool with kwargs {'country': 'https://evil.example/p.png '}",
        tool_call_id="1",
        name="search_knowledge_base",
    )
    assert allowed_urls([error]) == set()


def test_verified_links_stay_and_invented_ones_are_removed():
    """A link from a tool stays; an invented one becomes plain text and is reported."""
    answer = "[Website](https://a.org/) and [Fake](https://invented.example/page) see https://b.org"
    cleaned, report = enforce_grounding(answer, {"https://a.org"})
    assert "[Website](https://a.org/)" in cleaned
    assert "invented.example" not in cleaned and "b.org" not in cleaned
    assert report.removed == ["https://invented.example/page", "https://b.org"]
    assert not report.grounded


@pytest.mark.parametrize(
    "attack",
    [
        "![](https://evil.example/p.png?b=100)",
        "![pic](https://evil.example/p.png)",
        "[](https://evil.example/x)",
        '[Zoo](https://evil.example/x "Zoo")',
        "![z](https://evil.example/p.png 'z')",
        "www.evil.example/page",
        "(https://evil.example/x)",
        "![z](HTTPS://evil.example/p.png)",
        "![z](//evil.example/p.png)",
        "[z](//evil.example/x)",
        "![z](https&#58;//evil.example/p.png)",
        "![z](https\\://evil.example/p.png)",
        "[x][r]\n\n[r]: https&#58;//evil.example/p.png",
        "[x][r]\n\n[r]: https://evil.example/p.png",
        "<https://evil.example/x>",
        "![z](<https://evil.example/p.png>)",
        "[js](javascript:alert(1))",
        "Visit HTTP://EVIL.EXAMPLE/x now",
    ],
)
def test_no_unverified_host_survives_any_link_form(attack):
    """Every link and image form that points to an unverified host is removed."""
    cleaned, report = enforce_grounding(f"Ideas: {attack} done", ALLOWED)
    assert "evil.example" not in cleaned.lower() and "javascript:" not in cleaned
    assert report.removed


def test_images_are_dropped_even_from_a_verified_host():
    """An image would load without a click, so even a tool URL is not shown as an image."""
    cleaned, report = enforce_grounding("![zoo](https://a.org)", ALLOWED)
    assert "![" not in cleaned and "https://a.org" not in cleaned


def test_verified_maps_link_with_query_and_title_is_kept_without_its_title():
    """A tool's maps URL stays clickable; the title is dropped; its query cannot be extended."""
    url = "https://www.google.com/maps/dir/?api=1&destination=Zoo%2C+Berlin"
    cleaned, report = enforce_grounding(f'[🗺️ Directions]({url} "t") and {url}&x=1', ALLOWED)
    assert f"[🗺️ Directions]({url})" in cleaned and '"t"' not in cleaned
    assert report.verified == [url] and report.removed == [f"{url}&x=1"]


def test_answer_without_links_is_grounded():
    """An answer with no links passes unchanged."""
    cleaned, report = enforce_grounding("No links here.", set())
    assert cleaned == "No links here." and report.grounded
