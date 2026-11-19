"""Grounding check: every link in an answer must come from a tool result.

The model could invent a website, or injected text could make it write a tracking link or image.
Parents might then travel to a place that does not exist, or their browser would load a third-party
URL. Matching every Markdown form with patterns is never complete, so the answer is made safe by
construction instead (deny by default):

1. Simple inline links `[text](url)` whose URL a tool returned are kept (rebuilt, without a title);
   images are never kept. Autolinks and bare URLs a tool returned are kept too.
2. Every other URL-like text (`http(s):`, `//host`, `www.`) is removed.
3. In everything that is left, the characters that build links, images, reference definitions,
   HTML, directives and math (`[`, `]`, `<`, `>`, `$`) are backslash-escaped, so no other link or
   image can form, whatever syntax was used.

URLs are taken only from the known URL fields of tool results (`URL_FIELDS`), so text a tool merely
echoes (a budget note, a city name, an error message) can never make a link count as verified.
"""

import json
import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urlsplit, urlunsplit

from langchain_core.messages import BaseMessage, ToolMessage

REMOVED = "(link removed: not verified)"
# The tool result fields that hold links the app itself built or got from a data source.
URL_FIELDS = frozenset({"website", "maps_url", "url", "source_url", "source_urls"})
# [text](href "title") and ![alt](href); the href may sit in <...>; the title is dropped.
_INLINE = re.compile(
    r"(!?)\[([^\[\]]*)\]\(\s*<?([^\s<>()]*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
_AUTOLINK = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.-]*:[^\s<>]*|www\.[^\s<>]*)>")
# Scheme with or without "//", a protocol-relative host, or "www.".
_BARE = re.compile(
    r"\bhttps?:[^\s<>\"'\]\)]+|(?<![\w:])//[\w-]+\.[^\s<>\"'\]\)]*|\bwww\.[^\s<>\"'\]\)]+",
    re.IGNORECASE,
)
_ENTITY = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")
_SPECIAL = re.compile(r"([\[\]<>$])")
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


def _is_http(value: object) -> bool:
    """Return True for a string that is an absolute http(s) URL."""
    return isinstance(value, str) and value.lower().startswith(("http://", "https://"))


def _collect_urls(value: object, into: set[str]) -> None:
    """Collect the http(s) URLs held in the known URL fields anywhere in a JSON value."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in URL_FIELDS:
                items = item if isinstance(item, list) else [item]
                into.update(u for u in items if _is_http(u))
            else:
                _collect_urls(item, into)
    elif isinstance(value, list):
        for item in value:
            _collect_urls(item, into)


def allowed_urls(messages: list[BaseMessage]) -> set[str]:
    """Return every URL in the URL fields of the JSON tool results of a conversation."""
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


def _decode(text: str) -> str:
    """Decode complete HTML entities and drop backslashes before ':' or '/', as a renderer would."""
    decoded = _ENTITY.sub(lambda m: unescape(m.group(0)), text)
    return re.sub(r"\\([:/])", r"\1", decoded)


def _escape(text: str) -> str:
    """Backslash-escape the characters that could build a link, image, HTML or math."""
    return _SPECIAL.sub(r"\\\1", text)


def _label(text: str) -> str:
    """Return safe link text: no link syntax, and no URL that could hide where the link goes."""
    text = re.sub(r"[!\[\]<>$]", "", text).strip()
    return "link" if not text or _BARE.search(text) else text


def enforce_grounding(answer: str, allowed: set[str]) -> tuple[str, GroundingReport]:
    """Return the answer with only verified links left as links, and a report."""
    # The answer is decoded before matching, so the allowed URLs are decoded the same way.
    allowed_norm = {_normalise(_decode(u)) for u in allowed if _is_http(u)}
    report = GroundingReport()
    kept: list[str] = []

    def is_allowed(url: str) -> bool:
        """Return True for an absolute http(s) URL that a tool returned."""
        return _is_http(url) and _normalise(url) in allowed_norm

    def keep(markdown: str) -> str:
        """Hide a verified link from the later passes and return its placeholder."""
        kept.append(markdown)
        return _PLACEHOLDER.format(len(kept) - 1)

    def replace_inline(match: re.Match) -> str:
        """Keep a verified link without its title; drop every image; flatten the rest."""
        is_image, text, url = match.group(1) == "!", match.group(2), match.group(3)
        if not is_image and is_allowed(url):
            report.verified.append(url)
            return keep(f"[{_label(text)}]({url})")
        report.removed.append(url)
        return f"{text} {REMOVED}" if text.strip() else REMOVED

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
    cleaned = _INLINE.sub(replace_inline, cleaned)
    cleaned = _AUTOLINK.sub(replace_autolink, cleaned)
    cleaned = _BARE.sub(replace_bare, cleaned)
    cleaned = _escape(cleaned)
    for i, markdown in enumerate(kept):
        cleaned = cleaned.replace(_PLACEHOLDER.format(i), markdown)
    return cleaned, report
