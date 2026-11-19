"""Grounding check: every link in an answer must come from a tool result.

The model could invent a website or an event. Parents might then travel to a place that does not
exist, so links that no tool returned are removed from the answer and reported, in code rather
than only in the prompt.
"""

import json
import re
from dataclasses import dataclass, field

from langchain_core.messages import BaseMessage, ToolMessage

_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BARE_URL = re.compile(r"(?<!\()https?://[^\s)\]>]+")


@dataclass
class GroundingReport:
    """Which links in an answer were verified against tool results and which were removed."""

    verified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        """Return True when no link had to be removed."""
        return not self.removed


def _collect_urls(value: object, into: set[str]) -> None:
    """Collect every http(s) string found anywhere in a JSON value."""
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            into.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_urls(v, into)
    elif isinstance(value, list):
        for v in value:
            _collect_urls(v, into)


def allowed_urls(messages: list[BaseMessage]) -> set[str]:
    """Return every URL that appears in the tool results of a conversation."""
    urls: set[str] = set()
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                _collect_urls(json.loads(message.content), urls)
            except json.JSONDecodeError, TypeError:
                urls.update(_BARE_URL.findall(str(message.content)))
    return urls


def _normalise(url: str) -> str:
    """Return a URL without a trailing slash or punctuation, so equal links compare equal."""
    return url.rstrip(".,;:!?").rstrip("/")


def enforce_grounding(answer: str, allowed: set[str]) -> tuple[str, GroundingReport]:
    """Remove links not found in tool results and return the cleaned answer and a report."""
    allowed_norm = {_normalise(u) for u in allowed}
    report = GroundingReport()

    def replace_link(match: re.Match) -> str:
        """Keep a verified Markdown link; turn an unverified one into plain text."""
        text, url = match.group(1), match.group(2)
        if _normalise(url) in allowed_norm:
            report.verified.append(url)
            return match.group(0)
        report.removed.append(url)
        return f"{text} (link removed: not verified)"

    cleaned = _MD_LINK.sub(replace_link, answer)

    def replace_bare(match: re.Match) -> str:
        """Keep a verified bare URL; drop an unverified one."""
        url = match.group(0)
        if _normalise(url) in allowed_norm:
            report.verified.append(url)
            return url
        report.removed.append(url)
        return "(link removed: not verified)"

    # Bare URLs left after the Markdown links were handled (a verified link's URL sits inside
    # "(...)", which the lookbehind skips).
    cleaned = _BARE_URL.sub(replace_bare, cleaned)
    return cleaned, report
