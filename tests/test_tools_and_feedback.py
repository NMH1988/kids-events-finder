"""Tests for the tool registry (validation, errors, JSON results), the index and feedback."""

import json

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from pydantic import ValidationError

from src.feedback import load_feedback, save_feedback
from src.knowledge import load_places
from src.rag.index import build_index, open_index
from src.rag.retriever import AdvancedRetriever
from src.tools.registry import RagSettings, build_tools


@pytest.fixture
def tools():
    """The four tools on a BM25-only retriever, keyed by name."""
    built = build_tools(AdvancedRetriever(None), RagSettings(multi_query=False))
    return {t.name: t for t in built}


def test_four_tools_are_registered(tools):
    """The agent gets exactly the four documented tools."""
    assert set(tools) == {
        "search_knowledge_base",
        "find_nearby_places",
        "search_family_events",
        "get_weather_forecast",
    }


def test_knowledge_base_tool_returns_links_and_directions(tools):
    """Results carry the official website and a Google Maps directions link."""
    out = json.loads(
        tools["search_knowledge_base"].invoke(
            {"query": "chocolate", "country": "DE", "city": "Cologne", "child_age": 8}
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
