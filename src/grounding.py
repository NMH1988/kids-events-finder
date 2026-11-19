"""Grounding check: every link in an answer must come from a tool result.

The model could invent a website, or injected text could make it write a tracking link or image.
Parents might then travel to a place that does not exist, or their browser would load a third-party
URL. Matching every Markdown form with patterns is never complete, so the answer is made safe by
construction instead (deny by default):

1. The answer is decoded the way a renderer would read it: complete HTML entities are decoded,
   Markdown backslash escapes are resolved, and NUL characters (used for placeholders) are removed.
2. Simple inline links `[text](url)` whose URL a tool returned are kept (rebuilt, without a title,
   with safe link text); images are never kept. Autolinks and bare URLs a tool returned are kept.
3. Every other URL-like run of text (`http(s):`, `//host`, `www.`, up to the next space, as the
   renderer's autolink rule reads it) is removed.
4. In everything that is left, every character that could build a link, image, reference
   definition, HTML, code block (e.g. a Mermaid diagram), directive, math or e-mail autolink
   (`\\ [ ] < > $ ` ~ @`) is backslash-escaped, so nothing else can form, whatever syntax was used.

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
URL_FIELDS = frozenset({"website", "maps_url", "source_url", "source_urls"})
# [text](href "title") and ![alt](href); the href may sit in <...>; the title is dropped.
_INLINE = re.compile(
    r"(!?)\[([^\[\]]*)\]\(\s*<?([^\s<>()]*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
_AUTOLINK = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.-]*:[^\s<>]*|www\.[^\s<>]*)>")
# A URL-like run up to the next space or "<": a scheme, a protocol-relative host or "www.".
_BARE = re.compile(
    r"(?:https?:|(?<![\w:/])//(?=[\w-]+\.)|www\.)[^\s<]*",
    re.IGNORECASE,
)
# Trailing characters the renderer's autolink rule leaves out of a link.
_TRAILING = ".,:;!?*_~'\""
_ENTITY = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
_SPECIAL = re.compile(r"([\\\[\]<>$`~@])")
_DOMAIN = re.compile(r"[\w-]+\.[a-z]{2,}", re.IGNORECASE)
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
    """Read text as a renderer would: no NULs, complete entities decoded, escapes resolved."""
    text = text.replace("\x00", "")
    text = _ENTITY.sub(lambda m: unescape(m.group(0)), text)
    return _ESCAPED.sub(r"\1", text)


def _escape(text: str) -> str:
    """Backslash-escape every character that could build a link, image, code, HTML or math."""
    return _SPECIAL.sub(r"\\\1", text)


def _label(text: str) -> str:
    """Return safe link text: no link syntax, and no address that could hide where it goes."""
    text = _SPECIAL.sub("", text).replace("!", "").strip()
    if not text or _BARE.search(text) or _DOMAIN.search(text):
        return "link"
    return text


def _split_tail(span: str) -> tuple[str, str]:
    """Split trailing punctuation and unbalanced ')' off a URL-like run, as autolinks do."""
    end = len(span)
    while end and (
        span[end - 1] in _TRAILING
        or (span[end - 1] == ")" and span[:end].count("(") < span[:end].count(")"))
    ):
        end -= 1
    return span[:end], span[end:]


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
        """Keep a verified URL-like run only when the whole run is that URL; drop any other."""
        url, tail = _split_tail(match.group(0))
        if is_allowed(url):
            report.verified.append(url)
            return keep(url) + tail
        report.removed.append(url)
        return REMOVED + tail

    cleaned = _decode(answer)
    cleaned = _INLINE.sub(replace_inline, cleaned)
    cleaned = _AUTOLINK.sub(replace_autolink, cleaned)
    cleaned = _BARE.sub(replace_bare, cleaned)
    cleaned = _escape(cleaned)
    for i, markdown in enumerate(kept):
        cleaned = cleaned.replace(_PLACEHOLDER.format(i), markdown)
    return cleaned, report
