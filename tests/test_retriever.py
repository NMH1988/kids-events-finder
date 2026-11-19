"""Tests for the advanced RAG retriever: filters, BM25, dense, RRF, multi-query and rerank."""

import pytest

from src.knowledge import load_places
from src.rag.retriever import AdvancedRetriever, _Queries, _Score, _Scores, reciprocal_rank_fusion
from tests.fakes import KeywordVectorStore, StubHelperLLM


@pytest.fixture
def store():
    """A keyword vector store over the real knowledge base."""
    return KeywordVectorStore([p.to_document() for p in load_places()])


def test_rrf_rewards_items_ranked_high_in_several_lists():
    """An item near the top of both lists beats one that tops only one list."""
    scores = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"], ["b"]], k=60)
    assert max(scores, key=scores.get) == "b"
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)


def test_metadata_filters_keep_country_city_age_and_indoor(store):
    """Candidates respect country, city, age and the indoor-only switch."""
    retriever = AdvancedRetriever(store)
    found = retriever.candidates("GB", "London", age=1, indoor_only=True)
    assert found
    for place in found:
        assert place.country == "GB" and place.serves_city("London")
        assert place.age_min <= 1 and place.setting != "outdoor"


def test_bm25_finds_keyword_match(store):
    """Keyword search ranks the dinosaur museum first for a dinosaur question."""
    retriever = AdvancedRetriever(None)
    found = retriever.search("dinosaurs", "DE", "Berlin", 6, mode="bm25", multi_query=False)
    assert found[0].place.id == "de-naturkunde-berlin"
    assert found[0].found_by == {"bm25"}


def test_hybrid_merges_dense_and_bm25_and_never_leaves_the_country(store):
    """Hybrid results come from both searches and stay in the chosen country and city."""
    retriever = AdvancedRetriever(store)
    found = retriever.search("submarine science museum", "US", "Chicago", 10, multi_query=False)
    assert found[0].place.id == "us-msi-chicago"
    assert found[0].found_by == {"dense", "bm25"}
    assert all(r.place.country == "US" and r.place.city == "Chicago" for r in found)


def test_multi_query_adds_rewritten_queries(store):
    """A foreign-language question is rewritten into English queries that find the place."""
    helper = StubHelperLLM({"_Queries": _Queries(queries=["dinosaur skeletons museum"])})
    retriever = AdvancedRetriever(store, helper_llm=helper)
    assert retriever.rewrite("Bé thích khủng long") == [
        "Bé thích khủng long",
        "dinosaur skeletons museum",
    ]
    found = retriever.search("Bé thích khủng long", "DE", "Frankfurt", 5)
    assert found[0].place.id == "de-senckenberg"
    assert "<question>Bé thích khủng long</question>" in helper.stubs["_Queries"].prompts[0]


def test_rerank_reorders_by_llm_score(store):
    """The reranker's scores decide the final order."""
    helper = StubHelperLLM(
        {
            "_Scores": _Scores(
                scores=[_Score(id="us-shedd", score=10), _Score(id="us-field-museum", score=2)]
            )
        }
    )
    retriever = AdvancedRetriever(store, helper_llm=helper)
    found = retriever.search("museum", "US", "Chicago", 6, multi_query=False, rerank=True, k=3)
    assert found[0].place.id == "us-shedd"
    assert found[0].rerank_score == 10


def test_no_candidates_returns_empty():
    """A filter combination with no places returns nothing without searching."""
    retriever = AdvancedRetriever(None)
    assert retriever.search("anything", "DE", "Atlantis") == []
