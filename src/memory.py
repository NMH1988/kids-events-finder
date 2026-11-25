"""Long-term memory: the family's activity preferences, kept across conversations (T5.11).

The memory is a LangGraph store (`InMemoryStore`) that is saved to a local JSON file, so it
survives a restart of the app. It holds fixed choices only: a place category or indoor/outdoor,
and whether the family likes or avoids it. No free text, place names, age groups, budget or family
size, and no visited or liked places (LEGAL_COMPLIANCE 1.5-1.7). The parent switches it on in the
sidebar; each preference is deleted `config.LONG_TERM_MEMORY_RETENTION_DAYS` after it was last
saved, and "Forget everything" deletes all of them at once (LEGAL_COMPLIANCE 2.7, 2.8, 2.11).
"""

import json
import logging
import re
import threading
import unicodedata
from collections.abc import Iterable
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langgraph.store.base import BaseStore, Op, PutOp, Result
from langgraph.store.memory import InMemoryStore

from src import config
from src.errors import AppInputError

logger = logging.getLogger(__name__)

MEMORY_OFF = "off (the parent has not switched on long-term memory)"


class FileBackedStore(InMemoryStore):
    """An in-memory LangGraph store that saves its preferences to a local file after each change."""

    def __init__(self, path: Path, now: datetime | None = None) -> None:
        """Load the saved preferences, dropping broken and expired ones."""
        super().__init__()
        self.path = path
        # Held for every change and for read-then-delete sequences (the cleaner runs in a thread).
        self.lock = threading.RLock()
        self._loading = True
        entries = _read(path, now)
        try:
            for key, value in (entries or {}).items():
                self.put(config.MEMORY_NAMESPACE, key, value)
        finally:
            self._loading = False
        if entries is None:
            # The file exists but could not be opened (e.g. another program holds it): keep it
            # untouched rather than delete the family's preferences; the next save rewrites it.
            return
        try:
            purge_expired(self, now)
            # Rewrite the file from what loaded (or delete it when nothing did), so a broken,
            # future-dated or disallowed entry, or a copy left by a crash, never outlives the
            # retention period unseen (code and legal review round 3).
            with self.lock:
                self._save()
        except OSError as exc:
            # The file is rewritten later; the page must still load.
            logger.warning("memory_save_failed", extra={"type": type(exc).__name__})

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        """Run the operations; a change is kept only when the file could be written too."""
        ops = list(ops)
        with self.lock:
            changes = not self._loading and any(isinstance(op, PutOp) for op in ops)
            before = _snapshot(self) if changes else {}
            results = super().batch(ops)
            if changes:
                try:
                    self._save()
                except OSError as exc:
                    self._restore(before)
                    logger.warning("memory_save_failed", extra={"type": type(exc).__name__})
                    raise
        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        """Run the operations like `batch` (the app has no async callers)."""
        return self.batch(ops)

    def _restore(self, before: dict[str, dict]) -> None:
        """Put the store back to the snapshot taken before a change whose file write failed."""
        now = _snapshot(self)
        ops = [PutOp(config.MEMORY_NAMESPACE, key, None) for key in now if key not in before]
        ops += [PutOp(config.MEMORY_NAMESPACE, key, value) for key, value in before.items()]
        super().batch(ops)

    def _save(self) -> None:
        """Write every preference to the file, or delete the file when none is left."""
        data = _snapshot(self)
        tmp = self.path.with_suffix(".tmp")
        if not data:
            self.delete_files()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            # Never leave a copy of the preferences behind in the temporary file.
            tmp.unlink(missing_ok=True)
            raise

    def delete_files(self) -> None:
        """Delete the memory file and any temporary copy, also ones this store did not load."""
        self.path.with_suffix(".tmp").unlink(missing_ok=True)
        self.path.unlink(missing_ok=True)


def _lock(store: BaseStore):
    """Return the store's lock, or a no-op lock for a plain store (tests, evaluation scripts)."""
    return getattr(store, "lock", None) or nullcontext()


def _snapshot(store: BaseStore) -> dict[str, dict]:
    """Return every stored entry by key."""
    return {item.key: item.value for item in _items(store)}


def _saved_at(value: dict) -> datetime:
    """Return when a valid entry was saved."""
    return datetime.fromisoformat(value["saved_at"])


def _valid(key: object, value: object, now: datetime | None = None) -> bool:
    """Return True when an entry is one of the allowed choices with a sensible save date."""
    if key not in config.MEMORY_TOPICS or not isinstance(value, dict):
        return False
    if set(value) != {"feeling", "saved_at"} or value["feeling"] not in config.MEMORY_FEELINGS:
        return False
    try:
        saved = _saved_at(value)
    except TypeError, ValueError:
        return False
    latest = (now or datetime.now(UTC)) + timedelta(seconds=config.MEMORY_CLOCK_SKEW_SECONDS)
    return saved.tzinfo is not None and saved <= latest


def _read(path: Path, now: datetime | None = None) -> dict[str, dict] | None:
    """Return the file's allowed entries: {} if broken or too large, None if it can't be opened."""
    try:
        if not path.exists():
            return {}
        if path.stat().st_size > config.MAX_MEMORY_FILE_BYTES:
            logger.warning("memory_file_unreadable", extra={"type": "TooLarge"})
            return {}
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("memory_file_unreadable", extra={"type": "UnicodeDecodeError"})
        return {}
    except OSError as exc:
        logger.warning("memory_file_unreadable", extra={"type": type(exc).__name__})
        return None
    try:
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - e.g. RecursionError from a tampered file
        logger.warning("memory_file_unreadable", extra={"type": type(exc).__name__})
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if _valid(k, v, now)}


def _items(store: BaseStore) -> list:
    """Return the stored preference items."""
    return store.search(config.MEMORY_NAMESPACE, limit=len(config.MEMORY_TOPICS) + 1)


def _fold(text: str) -> str:
    """Return the text in one Unicode form and case, for matching topic words."""
    # Every kind of dash counts as "-", and invisible characters (zero-width space, soft hyphen)
    # are dropped, so "theme‐park" is still a theme park (security review T5.11 round 4).
    chars = (
        "-" if unicodedata.category(c) == "Pd" else c
        for c in unicodedata.normalize("NFC", text)
        if unicodedata.category(c) != "Cf"
    )
    return "".join(chars).casefold()


def _word_pattern(word: str) -> str:
    """Return a pattern for a whole word or phrase, with a plural ending allowed."""
    # The words of a phrase may be joined by any spaces, line breaks or punctuation ("theme-park",
    # "theme/park", "theme.park"; security review T5.11 round 5).
    body = r"[\W_]+".join(re.escape(_fold(part)) for part in word.split())
    return r"(?<![\w\-])" + body + config.MEMORY_WORD_ENDINGS + r"(?![\w\-])"


def named_by_parent(text: str, topic: str) -> bool:
    """Return True when the parent's own message names the topic (a word from its fixed list)."""
    folded = _fold(text or "")
    words = config.MEMORY_TOPIC_WORDS.get(topic, ())
    # Phrases of other topics that contain one of this topic's words ("theme park" for "park")
    # are removed first, longest first, so they do not count for this topic.
    others = [
        phrase
        for other, phrases in config.MEMORY_TOPIC_WORDS.items()
        if other != topic
        for phrase in phrases
        if any(re.search(_word_pattern(word), _fold(phrase)) for word in words)
    ]
    for phrase in sorted(others, key=len, reverse=True):
        folded = re.sub(_word_pattern(phrase), " ", folded)
    return any(re.search(_word_pattern(word), folded) for word in words)


def switched_on(run_config: dict | None) -> bool:
    """Return the sidebar switch as passed in this run's config (off when it is missing)."""
    return bool(((run_config or {}).get("configurable") or {}).get("memory_on", False))


def save_preference(
    store: BaseStore, topic: str, feeling: str, now: datetime | None = None
) -> dict:
    """Save one preference (a new one for the same topic replaces it) and return what was saved."""
    if topic not in config.MEMORY_TOPICS or feeling not in config.MEMORY_FEELINGS:
        raise AppInputError("Only the listed topics and 'likes' or 'avoids' can be remembered.")
    saved_at = (now or datetime.now(UTC)).isoformat()
    store.put(config.MEMORY_NAMESPACE, topic, {"feeling": feeling, "saved_at": saved_at})
    return {"topic": topic, "feeling": feeling}


def preferences(store: BaseStore, now: datetime | None = None) -> list[dict]:
    """Return the remembered, unexpired preferences as topic and feeling, in topic order."""
    now = now or datetime.now(UTC)
    limit = timedelta(days=config.LONG_TERM_MEMORY_RETENTION_DAYS)
    found = {
        key: value
        for key, value in _snapshot(store).items()
        if _valid(key, value, now) and now - _saved_at(value) <= limit
    }
    return [
        {"topic": topic, "feeling": found[topic]["feeling"]}
        for topic in config.MEMORY_TOPICS
        if topic in found
    ]


def forget_all(store: BaseStore) -> int:
    """Delete every remembered preference in one change; return how many were deleted."""
    with _lock(store):
        keys = list(_snapshot(store))
        if keys:
            store.batch([PutOp(config.MEMORY_NAMESPACE, key, None) for key in keys])
        # Also a file the store could not load (broken, future-dated) or a leftover copy.
        if isinstance(store, FileBackedStore):
            store.delete_files()
    return len(keys)


def purge_expired(store: BaseStore, now: datetime | None = None) -> int:
    """Delete preferences saved longer ago than the retention period (and broken ones)."""
    now = now or datetime.now(UTC)
    limit = timedelta(days=config.LONG_TERM_MEMORY_RETENTION_DAYS)
    # Read and delete under one lock, so a preference saved again meanwhile is not deleted.
    with _lock(store):
        expired = [
            key
            for key, value in _snapshot(store).items()
            if not _valid(key, value, now) or now - _saved_at(value) > limit
        ]
        if expired:
            store.batch([PutOp(config.MEMORY_NAMESPACE, key, None) for key in expired])
    return len(expired)


def label(preference: dict) -> str:
    """Return the app's own wording of one preference, e.g. "likes museums"."""
    topic = config.MEMORY_TOPIC_LABELS.get(preference["topic"], preference["topic"])
    return f"{preference['feeling']} {topic}"


def describe(store: BaseStore | None, on: bool) -> str:
    """Describe the remembered preferences for the system prompt, built by code from fixed words."""
    if not on or store is None:
        return MEMORY_OFF
    found = preferences(store)
    if not found:
        return "on · nothing remembered yet"
    return "on · " + ", ".join(label(p) for p in found)
