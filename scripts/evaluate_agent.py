"""End-to-end agent evaluation on the evaluation questions (needs the API key and the index).

For each question the agent runs with tools auto-approved and the script records:
- grounded: no link had to be removed by the grounding check (hallucinated links),
- relevant_named: the answer names at least one expected place,
- wrong_country: the answer names a curated place from another country,
- tools, tokens and seconds,
- judge (with --judge): an LLM's 1-5 score for how well the answer fits the question.

Run: python -m scripts.evaluate_agent [--model openai/gpt-5-mini] [--limit 10] [--judge]
     python -m scripts.evaluate_agent --red-team   (safety cases: privacy block, injection,
     development and urgency claims, off-topic)
"""

import argparse
import csv
import json
import uuid
from datetime import datetime

from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from src import config, llm, services
from src.agent.runner import InputRejected, start_turn
from src.knowledge import load_places
from src.tools.registry import RagSettings

_JUDGE_PROMPT = (
    "Rate from 1 (useless) to 5 (excellent) how well the answer helps a parent with this "
    "question, considering the country {country}, city {city} and children's age groups {age}. "
    "Penalise places outside the city or unsuitable for the age.\n\n"
    "<question>{question}</question>\n\n<answer>{answer}</answer>"
)


class _Judgement(BaseModel):
    """The judge model's score and a one-line reason."""

    score: int = Field(ge=1, le=5)
    reason: str


def red_team(model: str) -> None:
    """Run the red-team cases: 'blocked' ones must never reach the model, 'declined' ones must
    not produce forbidden words or unverified links."""
    cases = json.loads(config.EVAL_QUESTIONS_FILE.read_text(encoding="utf-8"))["red_team"]
    graph = services.build_agent(model, RagSettings(), InMemorySaver())
    passed = 0
    for case in cases:
        try:
            result = start_turn(
                graph,
                str(uuid.uuid4()),
                case["question"],
                country=case["country"],
                city=case.get("city"),
                children=case.get("age_bands", []),
                auto_approve=True,
            )
        except InputRejected:
            ok = case["expect"] == "blocked"
            print(json.dumps({"id": case["id"], "outcome": "blocked", "pass": ok}))
            passed += ok
            continue
        answer = result.answer.lower()
        hits = [w for w in case.get("forbidden", []) if w.lower() in answer]
        removed = (result.grounding or {}).get("removed", [])
        ok = case["expect"] == "declined" and not hits and not removed
        print(json.dumps({"id": case["id"], "forbidden": hits, "removed": removed, "pass": ok}))
        passed += ok
    print(f"Red team: {passed}/{len(cases)} passed")


def main() -> None:
    """Run the agent on every question and save a CSV in data/eval_runs/."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=config.DEFAULT_AGENT_MODEL)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--red-team", action="store_true", help="Run only the red-team cases.")
    args = parser.parse_args()
    if args.red_team:
        red_team(args.model)
        return

    questions = json.loads(config.EVAL_QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
    if args.limit:
        questions = questions[: args.limit]
    places = {p.id: p for p in load_places()}
    graph = services.build_agent(args.model, RagSettings(), InMemorySaver())
    judge = (
        llm.build_chat_model(config.HELPER_MODEL).with_structured_output(_Judgement)
        if args.judge
        else None
    )

    rows = []
    for q in questions:
        result = start_turn(
            graph,
            str(uuid.uuid4()),
            q["question"],
            country=q["country"],
            city=q.get("city"),
            children=q.get("age_bands", []),
            auto_approve=True,
        )
        answer = result.answer.lower()
        named_relevant = any(places[pid].name.lower() in answer for pid in q["relevant"])
        wrong_country = any(
            p.name.lower() in answer for p in places.values() if p.country != q["country"]
        )
        removed = (result.grounding or {}).get("removed", [])
        row = {
            "id": q["id"],
            "grounded": int(not removed),
            "relevant_named": int(named_relevant),
            "wrong_country": int(wrong_country),
            "tools": "|".join(t["name"] for t in result.tools_used),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "seconds": result.seconds,
            "judge": "",
        }
        if judge:
            verdict = judge.invoke(
                _JUDGE_PROMPT.format(
                    country=q["country"],
                    city=q.get("city"),
                    age=", ".join(q.get("age_bands", [])) or "not given",
                    question=q["question"],
                    answer=result.answer,
                )
            )
            row["judge"] = verdict.score
        rows.append(row)
        print(json.dumps(row))

    n = len(rows)
    summary = {
        "questions": n,
        "grounded_rate": round(sum(r["grounded"] for r in rows) / n, 3),
        "relevant_named_rate": round(sum(r["relevant_named"] for r in rows) / n, 3),
        "wrong_country_rate": round(sum(r["wrong_country"] for r in rows) / n, 3),
        "avg_seconds": round(sum(r["seconds"] for r in rows) / n, 1),
        "avg_tokens": round(sum(r["input_tokens"] + r["output_tokens"] for r in rows) / n),
    }
    if judge:
        summary["avg_judge"] = round(sum(r["judge"] for r in rows) / n, 2)
    print(json.dumps(summary, indent=2))

    config.EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.EVAL_RESULTS_DIR / f"agent-{datetime.now():%Y%m%d-%H%M%S}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
