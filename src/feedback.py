"""Stores the parent's thumbs up/down on answers, the human feedback used in the evaluation.

By default only the rating and technical facts (model, country, tools, grounding) are stored. The
question and the answer are stored only when the parent ticks the box to share them, together with
a random id of the browser session, so the parent can delete what they shared while the page is
open (consent can be withdrawn, GDPR Art. 7(3)). Records are deleted after
`config.FEEDBACK_RETENTION_DAYS` (LEGAL_COMPLIANCE 2.7). The file is local and gitignored.
"""

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src import config

# One lock for every read-modify-write of the file (the cleaner runs in a background thread).
_LOCK = threading.Lock()


def _is_recent(record: dict, now: datetime) -> bool:
    """Return True when a record is younger than the retention period."""
    try:
        created = datetime.fromisoformat(record["time"])
    except KeyError, ValueError, TypeError:
        return False
    return now - created <= timedelta(days=config.FEEDBACK_RETENTION_DAYS)


def _read(path: Path) -> list[dict]:
    """Return every readable record in the file, oldest first; broken lines are skipped."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _write(path: Path, records: list[dict]) -> None:
    """Replace the file's content with these records."""
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )


def purge_old_feedback(path: Path = config.FEEDBACK_FILE, now: datetime | None = None) -> int:
    """Delete records older than the retention period (and broken lines); return how many."""
    now = now or datetime.now(UTC)
    with _LOCK:
        if not path.exists():
            return 0
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        kept = [r for r in _read(path) if _is_recent(r, now)]
        if len(kept) != len(lines):
            _write(path, kept)
        return len(lines) - len(kept)


def delete_shared_feedback(session_id: str, path: Path = config.FEEDBACK_FILE) -> int:
    """Delete every record this browser session shared text in; return how many were deleted."""
    if not session_id:
        return 0
    with _LOCK:
        records = _read(path)
        kept = [r for r in records if r.get("session_id") != session_id]
        if len(kept) != len(records):
            _write(path, kept)
        return len(records) - len(kept)


def save_feedback(
    rating: int,
    question: str,
    answer: str,
    *,
    model: str,
    country: str,
    tools_used: list[str],
    grounded: bool | None,
    share_text: bool = False,
    session_id: str = "",
    comment: str = "",
    path: Path = config.FEEDBACK_FILE,
) -> None:
    """Append a feedback record; question, answer and session id only when `share_text` is True."""
    if rating not in (0, 1):
        raise ValueError("rating must be 0 or 1")
    path.parent.mkdir(parents=True, exist_ok=True)
    purge_old_feedback(path)
    record = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "rating": rating,
        "model": model,
        "country": country,
        "tools_used": tools_used,
        "grounded": grounded,
        "text_shared": share_text,
    }
    if share_text:
        record["question"] = question[: config.MAX_USER_MESSAGE_CHARS]
        record["answer"] = answer
        record["comment"] = comment[:500]
        record["session_id"] = session_id
    with _LOCK, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_feedback(path: Path = config.FEEDBACK_FILE) -> list[dict]:
    """Return every stored feedback record younger than the retention period, oldest first."""
    now = datetime.now(UTC)
    with _LOCK:
        return [r for r in _read(path) if _is_recent(r, now)]
