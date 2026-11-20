"""Tests for the tool registry (validation, errors, JSON results), the index and feedback."""

import json

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from pydantic import ValidationError

from src.feedback import delete_shared_feedback, load_feedback, save_feedback
from src.knowledge import load_places
from src.rag.index import build_index, open_index
from src.rag.retriever import AdvancedRetriever
from src.tools.registry import RagSettings, build_tools


@pytest.fixture
def tools():
    """The four tools on a BM25-only retriever, keyed by name."""
    built = build_tools(AdvancedRetriever(None), RagSettings(multi_query=False))
    return {t.name: t for t in built}


def test_all_tools_are_registered(tools):
    """The agent gets exactly the documented tools."""
    assert set(tools) == {
        "search_knowledge_base",
        "find_nearby_places",
        "search_family_events",
        "get_weather_forecast",
        "find_train_connection",
        "compare_train_tickets",
        "check_budget",
    }


def test_ticket_and_budget_tools_return_json(tools):
    """The ticket comparison and budget check run inside the app and return JSON."""
    tickets = json.loads(
        tools["compare_train_tickets"].invoke(
            {
                "from_state": "Bavaria",
                "to_state": "BY",
                "travel_date": "2026-11-21",
                "adults": 2,
                "children_age_bands": ["3-5", "6-9"],
            }
        )
    )
    assert tickets["options"][0]["total_eur"] == 44.0
    checked = json.loads(
        tools["check_budget"].invoke(
            {
                "budget_eur": 80,
                "items": [{"label": "Train", "amount_eur": 44}, {"label": "Zoo"}],
            }
        )
    )
    assert checked["remaining_eur"] == 36.0 and checked["unknown_items"] == ["Zoo"]
    bad = json.loads(
        tools["compare_train_tickets"].invoke(
            {"from_state": "Mars", "to_state": "BY", "travel_date": "2026-11-21", "adults": 1}
        )
    )
    assert "Unknown German state" in bad["error"]


def test_knowledge_base_tool_returns_links_and_directions(tools):
    """Results carry the official website and a Google Maps directions link."""
    out = json.loads(
        tools["search_knowledge_base"].invoke(
            {"query": "chocolate", "country": "DE", "city": "Cologne", "age_bands": ["6-9"]}
        )
    )
    first = out["results"][0]
    assert first["id"] == "de-schokoladenmuseum"
    assert first["website"].startswith("https://")
    assert first["maps_url"].startswith("https://www.google.com/maps/dir/?api=1")


def test_invalid_arguments_are_rejected_before_running(tools):
    """An unsupported country or an impossible age never reaches the tool."""
    with pytest.raises(ValidationError):
        tools["search_knowledge_base"].invoke({"query": "zoo", "country": "FR"})
    with pytest.raises(ValidationError):
        tools["find_nearby_places"].invoke({"city": "Berlin", "country": "DE", "category": "bar"})


def test_network_failure_becomes_a_friendly_error(tools):
    """A failed request (blocked in tests) returns an error message, not an exception."""
    out = json.loads(
        tools["find_nearby_places"].invoke({"city": "Berlin", "country": "DE", "category": "zoo"})
    )
    assert out["results"] == [] and "did not answer" in out["error"]


def test_index_builds_and_opens_with_fake_embeddings(tmp_path):
    """The Chroma index stores every place and can be searched with a country filter."""
    embeddings = DeterministicFakeEmbedding(size=32)
    assert open_index(embeddings, tmp_path / "none") is None
    count = build_index(embeddings, persist_dir=tmp_path / "chroma")
    assert count == len(load_places())
    store = open_index(embeddings, tmp_path / "chroma")
    docs = store.similarity_search("zoo", k=3, filter={"country": "US"})
    assert docs and all(d.metadata["country"] == "US" for d in docs)


def test_feedback_is_appended_and_read_back(tmp_path):
    """Ratings are stored as JSON lines; an invalid rating is refused."""
    path = tmp_path / "fb.jsonl"
    save_feedback(1, "q", "a", model="m", country="DE", tools_used=["x"], grounded=True, path=path)
    save_feedback(0, "q2", "a2", model="m", country="GB", tools_used=[], grounded=False, path=path)
    records = load_feedback(path)
    assert [r["rating"] for r in records] == [1, 0]
    with pytest.raises(ValueError):
        save_feedback(5, "q", "a", model="m", country="DE", tools_used=[], grounded=None, path=path)


def test_feedback_keeps_text_only_with_consent_and_expires(tmp_path):
    """Question and answer are stored only when shared; records older than 90 days are deleted."""
    from datetime import UTC, datetime, timedelta

    from src.feedback import purge_old_feedback

    path = tmp_path / "fb.jsonl"
    save_feedback(
        1,
        "my question",
        "the answer",
        model="m",
        country="DE",
        tools_used=[],
        grounded=True,
        path=path,
    )
    save_feedback(
        0,
        "shared q",
        "shared a",
        model="m",
        country="DE",
        tools_used=[],
        grounded=True,
        share_text=True,
        path=path,
    )
    first, second = load_feedback(path)
    assert "question" not in first and first["text_shared"] is False
    assert second["question"] == "shared q"
    later = datetime.now(UTC) + timedelta(days=91)
    assert purge_old_feedback(path, now=later) == 2
    assert load_feedback(path) == []


def test_shared_feedback_can_be_deleted_by_its_session(tmp_path):
    """Consent can be withdrawn: a session deletes only the text it shared."""
    path = tmp_path / "fb.jsonl"
    common = {"model": "m", "country": "DE", "tools_used": [], "grounded": True, "path": path}
    save_feedback(1, "q1", "a1", share_text=True, session_id="s1", **common)
    save_feedback(1, "q2", "a2", share_text=True, session_id="s2", **common)
    path.write_text(path.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    assert delete_shared_feedback("s1", path) == 1
    assert [r["question"] for r in load_feedback(path)] == ["q2"]
    assert delete_shared_feedback("", path) == 0


def test_malformed_outside_data_becomes_an_error_message(monkeypatch):
    """A broken payload from an outside service returns a JSON error instead of ending the turn."""
    from src.tools import external

    def broken(**kwargs):
        """Fail like code reading an unexpected payload."""
        raise AttributeError("'str' object has no attribute 'get'")

    monkeypatch.setattr(external, "search_family_events", broken)
    built = {t.name: t for t in build_tools(AdvancedRetriever(None), RagSettings(), "key")}
    out = json.loads(
        built["search_family_events"].invoke(
            {
                "city": "Berlin",
                "country": "DE",
                "start_date": "2099-01-01",
                "end_date": "2099-01-02",
            }
        )
    )
    assert "could not read" in out["error"]
