"""Compare retrieval variants on the evaluation questions: hit rate@k and MRR.

Variants: BM25 only, dense only, hybrid (RRF), hybrid + multi-query, hybrid + multi-query +
rerank. Needs the API key and the built index for every variant except BM25.

Run: python -m scripts.evaluate_retrieval [--variants bm25,dense,hybrid,hybrid_mq,hybrid_mq_rr]
"""

import argparse
import csv
import json
import time
from datetime import datetime

from src import config
from src.rag.retriever import AdvancedRetriever

VARIANTS = {
    "bm25": {"mode": "bm25", "multi_query": False, "rerank": False},
    "dense": {"mode": "dense", "multi_query": False, "rerank": False},
    "hybrid": {"mode": "hybrid", "multi_query": False, "rerank": False},
    "hybrid_mq": {"mode": "hybrid", "multi_query": True, "rerank": False},
    "hybrid_mq_rr": {"mode": "hybrid", "multi_query": True, "rerank": True},
}


def load_questions() -> list[dict]:
    """Return the evaluation questions."""
    return json.loads(config.EVAL_QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]


def score(found_ids: list[str], relevant: list[str]) -> tuple[int, float]:
    """Return (hit, reciprocal rank of the first relevant id) for one question."""
    for rank, pid in enumerate(found_ids, start=1):
        if pid in relevant:
            return 1, 1.0 / rank
    return 0, 0.0


def evaluate(retriever: AdvancedRetriever, questions: list[dict], variant: dict) -> dict:
    """Run one variant over all questions and return its metrics and per-question rows."""
    rows, hits, rrs, started = [], 0, 0.0, time.perf_counter()
    for q in questions:
        found = retriever.search(
            q["question"],
            q["country"],
            q.get("city"),
            tuple(q.get("age_bands", ())),
            q.get("indoor_only", False),
            **variant,
        )
        ids = [r.place.id for r in found]
        hit, rr = score(ids, q["relevant"])
        hits, rrs = hits + hit, rrs + rr
        rows.append({"id": q["id"], "hit": hit, "rr": round(rr, 3), "found": "|".join(ids)})
    n = len(questions)
    return {
        "hit_rate": round(hits / n, 3),
        "mrr": round(rrs / n, 3),
        "seconds": round(time.perf_counter() - started, 1),
        "rows": rows,
    }


def main() -> None:
    """Evaluate the chosen variants, print a table and save a CSV in data/eval_runs/."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", default=",".join(VARIANTS))
    names = parser.parse_args().variants.split(",")
    questions = load_questions()

    needs_api = any(VARIANTS[n]["mode"] != "bm25" or VARIANTS[n]["multi_query"] for n in names)
    if needs_api:
        from src import services

        retriever = services.build_retriever()
        if retriever.vectorstore is None:
            raise SystemExit("Build the index first: python -m scripts.build_index")
    else:
        retriever = AdvancedRetriever(vectorstore=None)

    config.EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = config.EVAL_RESULTS_DIR / f"retrieval-{stamp}.csv"
    print(f"{'variant':<14}{'hit@5':>8}{'MRR':>8}{'sec':>8}")
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["variant", "question", "hit", "rr", "found"])
        for name in names:
            result = evaluate(retriever, questions, VARIANTS[name])
            print(f"{name:<14}{result['hit_rate']:>8}{result['mrr']:>8}{result['seconds']:>8}")
            for row in result["rows"]:
                writer.writerow([name, row["id"], row["hit"], row["rr"], row["found"]])
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
