"""Stores the parent's thumbs up/down on answers, the human feedback used in the evaluation.

Only the rating, the question, the answer and technical facts (model, tools, grounding) are
stored, locally in a gitignored file. The UI warns not to type personal details.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from src import config


def save_feedback(
    rating: int,
    question: str,
    answer: str,
    *,
    model: str,
    country: str,
    tools_used: list[str],
    grounded: bool | None,
    comment: str = "",
    path: Path = config.FEEDBACK_FILE,
) -> None:
    """Append one feedback record (rating 1 = helpful, 0 = not helpful) as a JSON line."""
    if rating not in (0, 1):
        raise ValueError("rating must be 0 or 1")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "rating": rating,
        "question": question[: config.MAX_USER_MESSAGE_CHARS],
        "answer": answer,
        "comment": comment[:500],
        "model": model,
        "country": country,
        "tools_used": tools_used,
        "grounded": grounded,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_feedback(path: Path = config.FEEDBACK_FILE) -> list[dict]:
    """Return every stored feedback record, oldest first."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
