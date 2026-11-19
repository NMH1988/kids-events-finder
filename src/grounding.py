"""Grounding check: every link in an answer must come from a tool result.

The model could invent a website, or injected text could make it write a tracking link or image.
Parents might then travel to a place that does not exist, or their browser would load a third-party
URL. So the answer is cleaned in code, deny by default: images are always dropped (an image loads
without a click), link titles and reference definitions are dropped, and every URL-like text -
Markdown links, autolinks, bare `https://`, `//host` and `www.` forms, any case, after decoding
HTML entities and backslash escapes - is kept only when a tool returned that exact URL.
"""

import html
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from langchain_core.messages import BaseMessage, ToolMessage

REMOVED = "(link removed: not verified)"
# [text](href "title") and ![alt](href); the href may sit in <...>; the title is dropped.
_INLINE = re.compile(
    r"(!?)\[([^\]]*)\]\(\s*<?([^\s<>)]*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
# Reference definitions such as "[r]: https://host" (they would turn [x][r] into a link).
_REF_DEF = re.compile(r"^[ \t]{0,3}\[[^\]]+\]:[ \t]*(\S+).*$", re.MULTILINE)
_AUTOLINK = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.-]*:[^\s<>]*|www\.[^\s<>]*)>")
_BARE = re.compile(r"(?:https?:)?//[^\s<>\"'\]\)]+|\bwww\.[^\s<>\"'\]\)]+", re.IGNORECASE)
_PLACEHOLDER = "\x00{}\x00"


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
    """Return every URL in the JSON tool results of a conversation."""
    # Tool results that are not JSON (e.g. an error text that echoes the model's own arguments)
    # give no URLs, so the model cannot make its own link count as verified.
    urls: set[str] = set()
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                _collect_urls(json.loads(message.content), urls)
            except json.JSONDecodeError, TypeError:
                continue
    return urls


def _normalise(url: str) -> str:
    """Return a comparable form: trailing punctuation and slash removed, scheme and host lower."""
    url = url.rstrip(".,;:!?").rstrip("/")
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), *parts[2:]))


def _decode(answer: str) -> str:
    """Decode HTML entities and drop backslashes before ':' or '/', as a renderer would."""
    return re.sub(r"\\([:/])", r"\1", html.unescape(answer))


def enforce_grounding(answer: str, allowed: set[str]) -> tuple[str, GroundingReport]:
    """Remove links and images not found in tool results; return the cleaned answer and a report."""
    # The answer is decoded before matching, so the allowed URLs are decoded the same way.
    allowed_norm = {
        _normalise(_decode(u)) for u in allowed if u.lower().startswith(("http://", "https://"))
    }
    report = GroundingReport()
    kept: list[str] = []

    def is_allowed(url: str) -> bool:
        """Return True for an absolute http(s) URL that a tool returned."""
        return url.lower().startswith(("http://", "https://")) and _normalise(url) in allowed_norm

    def keep(markdown: str) -> str:
        """Hide a verified link from the later passes and return its placeholder."""
        kept.append(markdown)
        return _PLACEHOLDER.format(len(kept) - 1)

    def replace_definition(match: re.Match) -> str:
        """Drop a reference definition; its target is reported unless it was verified."""
        url = match.group(1).strip("<>")
        (report.verified if is_allowed(url) else report.removed).append(url)
        return ""

    def replace_inline(match: re.Match) -> str:
        """Drop every image; keep a verified link without its title; flatten the rest."""
        is_image, text, url = match.group(1) == "!", match.group(2).strip(), match.group(3)
        if not is_image and is_allowed(url):
            report.verified.append(url)
            return keep(f"[{text or 'link'}]({url})")
        report.removed.append(url)
        if is_image:
            return f"{text} {REMOVED}".strip() if text else REMOVED
        return f"{text} {REMOVED}" if text else REMOVED

    def replace_autolink(match: re.Match) -> str:
        """Keep a verified <url> autolink; drop any other."""
        url = match.group(1)
        if is_allowed(url):
            report.verified.append(url)
            return keep(f"<{url}>")
        report.removed.append(url)
        return REMOVED

    def replace_bare(match: re.Match) -> str:
        """Keep a verified bare URL; drop any other URL-like text."""
        url = match.group(0)
        if is_allowed(url):
            report.verified.append(url)
            return keep(url)
        report.removed.append(url)
        return REMOVED

    cleaned = _decode(answer)
    cleaned = _REF_DEF.sub(replace_definition, cleaned)
    cleaned = _INLINE.sub(replace_inline, cleaned)
    cleaned = _AUTOLINK.sub(replace_autolink, cleaned)
    cleaned = _BARE.sub(replace_bare, cleaned)
    for i, markdown in enumerate(kept):
        cleaned = cleaned.replace(_PLACEHOLDER.format(i), markdown)
    return cleaned, report
