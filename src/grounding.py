"""Grounding check: every link in an answer must come from a tool result.

The model could invent a website, or injected text could make it write a tracking link or image.
Parents might then travel to a place that does not exist, or their browser would load a third-party
URL. Matching every Markdown form with patterns is never complete, so the answer is made safe by
construction instead (deny by default):

1. The answer is read the way a renderer would read it: control characters (also the placeholder
   markers) are removed, complete HTML entities are decoded, and the backslash escapes the URL
   passes need are resolved (other escapes are kept exactly as written).
2. Simple inline links `[text](url)` whose URL a tool returned are kept (rebuilt, without a title;
   address-like text becomes the link's host); images are never kept. Autolinks and bare URLs a
   tool returned are kept.
3. Every other URL-like run of text (`http(s):`, `//host`, `www.`, up to the next space, as the
   renderer's autolink rule reads it) is removed; e-mail addresses are written as "name (at) host".
4. In everything that is left, every character that could build a link, image, reference
   definition, HTML, entity, code block (e.g. a Mermaid diagram), directive or math
   (`\\ [ ] < > $ ` ~ @ &`) is backslash-escaped, so nothing else can form, whatever the syntax.

URLs are taken only from the known URL fields of tool results (`URL_FIELDS`) and only when strictly
formed (`_SAFE_URL`), so text a tool merely echoes (a budget note, a city name, an error message)
or a hostile value from a data source (a malformed OpenStreetMap `website` tag) can never make a
link count as verified or carry Markdown into the answer.
"""

import json
import re
import unicodedata
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
# "www." after a letter or digit ("Awww.") is not an autolink for the renderer, so it is left alone.
_BARE = re.compile(
    r"(?:https?:|(?<![\w:/])//(?=[\w-]+\.)|(?<![^\W_])www\.)[^\s<]*",
    re.IGNORECASE,
)
# Trailing characters the renderer's autolink rule leaves out of a link.
_TRAILING = ".,:;!?*_~'\""
# A verified URL must be strictly formed: http(s), then only these characters - no brackets,
# quotes, backslash, "@" (no user-info trick), "!", spaces or control characters.
_SAFE_URL = re.compile(r"https?://[A-Za-z0-9\-._~:/?#$&*+,;=%]+", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_ENTITY = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
# An escaped . - _ + between two word characters (www\.host, some\_page) is part of a word or URL;
# it is always resolved, so the URL passes see the address the renderer will link.
_WORD_ESCAPE = re.compile(r"(?<=[\w@.+\-])\\([.\-_+])(?=[\w@.+\-\\])")
# Escapes resolved before the URL passes; every other escape (e.g. \| or \#) is kept as written.
_URL_ESCAPES = frozenset("\\[]<>$`~@&:/")
_SPECIAL = re.compile(r"([\\\[\]<>$`~@&])")
_EMAIL = re.compile(r"([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)")
# A domain-like word (paypal.com, zoo．de) or a scheme; abbreviations like "z.B." or "St. Pauli"
# are not addresses.
_ADDRESS = re.compile(
    r"[\w-]+[.．。｡﹒․‧·⸱]+[^\W\d_]{2,}|\d{1,3}(?:[.．。｡﹒․‧·⸱]\d{1,3}){3}|://", re.IGNORECASE
)
# Zero-width joiner stays (it builds emoji such as family emoji); every other invisible format
# character (zero-width space, soft hyphen, word joiner, BOM ...) is removed before matching.
_KEEP_FORMAT = frozenset("‍")
# Tag characters build subdivision flags (England, Scotland, Wales): the black flag U+1F3F4, 2-6
# tag letters or digits, then the cancel tag U+E007F. They are kept only in that exact form, so no
# invisible text can hide behind a flag.
_TAG_CHARS = range(0xE0020, 0xE0080)
_FLAG = re.compile(
    "\U0001f3f4(?:"
    + "|".join("".join(chr(0xE0000 + ord(c)) for c in code) for code in ("gbeng", "gbsct", "gbwls"))
    + ")\U000e007f"
)
# Link text keeps only these characters; anything else (letter-like dots from other scripts,
# odd punctuation) could disguise it, so the link's host is shown instead.
_LABEL_PUNCTUATION = frozenset(" .,-'&:;()?!/+’‘“”„–—· ")
# Emoji outside the main emoji blocks that link text may use.
_LABEL_SYMBOLS = frozenset("⭐⭕⬛⬜⬅⬆⬇®™©")
# A domain spelled out in link text ("paypal .com", "PayPal .COM/login", "paypal dot com",
# "paypal(.)com"): a common top-level domain after a dot, comma or the word "dot".
_SPACED_DOMAIN = re.compile(
    r"[a-z0-9-]\s*(?:[.,·:]|\s[–-]\s|\(\.\)|\bdot\b)\s*"
    r"(?:c\s*o\s*m|org|net|de|uk|co|io|eu|at|ch|us|biz)(?![a-z])",
    re.IGNORECASE,
)
# An e-mail-like "@" (a word character on both sides) once escapes are resolved.
_MAIL_AT = re.compile(r"[\w.+-]@[\w-]")
_PLACEHOLDER = "\x00{}\x00"
_KEPT_ESCAPE = "\x01{}\x01"


@dataclass
class GroundingReport:
    """Which links in an answer were verified against tool results and which were removed."""

    verified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        """Return True when no link had to be removed."""
        return not self.removed


def is_strict_url(value: object) -> bool:
    """Return True for a strictly formed absolute http(s) URL (see `_SAFE_URL`)."""
    return isinstance(value, str) and _SAFE_URL.fullmatch(value) is not None


def _collect_urls(value: object, into: set[str]) -> None:
    """Collect the http(s) URLs held in the known URL fields anywhere in a JSON value."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in URL_FIELDS:
                items = item if isinstance(item, list) else [item]
                into.update(u for u in items if is_strict_url(u))
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


def _strip_invisible(text: str) -> str:
    """Remove control characters and invisible format characters (except emoji building blocks)."""
    text = _CONTROL.sub("", text)
    out: list[str] = []
    last = 0
    for match in [*_FLAG.finditer(text), None]:
        segment = text[last : match.start() if match else len(text)]
        out.extend(
            ch
            for ch in segment
            if ch in _KEEP_FORMAT
            or (ord(ch) not in _TAG_CHARS and unicodedata.category(ch) != "Cf")
        )
        if match:
            out.append(match.group(0))
            last = match.end()
    return "".join(out)


def _label_char(ch: str) -> bool:
    """Return True for a character link text may show: Latin letters, digits, emoji, punctuation."""
    if ch.isascii():
        return ch.isalnum() or ch in _LABEL_PUNCTUATION
    if ch in _LABEL_PUNCTUATION or ch in _LABEL_SYMBOLS:
        return True
    code = ord(ch)
    latin = 0xC0 <= code <= 0x24F or 0x1E00 <= code <= 0x1EFF
    symbol = unicodedata.category(ch) == "So"
    emoji = symbol and (
        (0x1F300 <= code < 0x1FB00)
        or 0x1F1E6 <= code <= 0x1F1FF  # regional indicators: country flags such as 🇩🇪
        or 0x2600 <= code <= 0x26FF
        or 0x2700 <= code <= 0x27BF
    )
    return (latin and ch.isalpha()) or emoji


def _decode(text: str, kept_escapes: list[str] | None = None) -> str:
    """Read text as a renderer would: no control characters, entities decoded, escapes resolved."""
    # With `kept_escapes`, escapes the URL passes do not need (e.g. \| or \#) become tokens
    # collected there, so they come back exactly as the model wrote them.
    text = _strip_invisible(text)
    # Decode until nothing changes, so double-encoded entities (&amp;#119;) cannot hide a URL.
    for _ in range(5):
        decoded = _strip_invisible(_ENTITY.sub(lambda m: unescape(m.group(0)), text))
        if decoded == text:
            break
        text = decoded
    for _ in range(10):
        resolved = _WORD_ESCAPE.sub(r"\1", text)
        if resolved == text:
            break
        text = resolved

    def resolve(match: re.Match) -> str:
        """Resolve an escape the URL passes need; keep any other as a token."""
        if kept_escapes is None or match.group(1) in _URL_ESCAPES:
            return match.group(1)
        kept_escapes.append(match.group(0))
        return _KEPT_ESCAPE.format(len(kept_escapes) - 1)

    return _ESCAPED.sub(resolve, text)


def _escape(text: str) -> str:
    """Backslash-escape every character that could build a link, image, code, HTML or math."""
    return _SPECIAL.sub(r"\\\1", text)


def _label(text: str, url: str) -> str:
    """Return safe link text; text that looks like an address is replaced by the link's host."""
    text = _SPECIAL.sub("", _ESCAPED.sub(r"\1", _strip_invisible(text))).replace("!", "").strip()
    # Link text needs no joiners, tag characters or combining marks: they can only disguise it.
    text = "".join(
        ch
        for ch in text
        if ch not in _KEEP_FORMAT and ord(ch) not in _TAG_CHARS and unicodedata.category(ch) != "Mn"
    ).strip()
    if (
        not text
        or not all(_label_char(ch) for ch in text)
        or _SPACED_DOMAIN.search(text)
        or _BARE.search(text)
        or _ADDRESS.search(text)
    ):
        return urlsplit(url).netloc.lower().removeprefix("www.") or "link"
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
    allowed_norm = {_normalise(_decode(u)) for u in allowed if is_strict_url(u)}
    cleaned, report, leftover = _clean(answer, allowed_norm, strict=False)
    if leftover:
        # Fail closed: an escape the model wrote still hid an address. Clean again with every
        # escape resolved first, so the URL passes see exactly what the renderer will link.
        cleaned, report, _ = _clean(answer, allowed_norm, strict=True)
    return cleaned, report


def _leftover_address(text: str) -> bool:
    """Return True when text (verified links already hidden) still reads as an address."""
    plain = _strip_invisible(_ESCAPED.sub(r"\1", text))
    return bool(_BARE.search(plain) or _MAIL_AT.search(plain))


def _clean(
    answer: str, allowed_norm: set[str], *, strict: bool
) -> tuple[str, GroundingReport, bool]:
    """Clean an answer; return the text, the report and whether an address could remain."""
    # In strict mode every escape is resolved before the URL passes, so none is kept as written.
    report = GroundingReport()
    kept: list[str] = []

    def is_allowed(url: str) -> bool:
        """Return True for an absolute http(s) URL that a tool returned."""
        return is_strict_url(url) and _normalise(url) in allowed_norm

    def keep(markdown: str) -> str:
        """Hide a verified link from the later passes and return its placeholder."""
        kept.append(markdown)
        return _PLACEHOLDER.format(len(kept) - 1)

    def replace_inline(match: re.Match) -> str:
        """Keep a verified link without its title; drop every image; flatten the rest."""
        is_image, text, url = match.group(1) == "!", match.group(2), match.group(3)
        if not is_image and is_allowed(url):
            report.verified.append(url)
            return keep(f"[{_label(text, url)}]({url})")
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

    kept_escapes: list[str] = []
    cleaned = _decode(answer, None if strict else kept_escapes)
    cleaned = _INLINE.sub(replace_inline, cleaned)
    cleaned = _AUTOLINK.sub(replace_autolink, cleaned)
    cleaned = _BARE.sub(replace_bare, cleaned)
    # The renderer turns name@host into a mail link even when "@" is escaped, so it is reworded.
    # Repeated until stable: overlapping addresses (a@b.de@c.de) leave a new one after one pass.
    for _ in range(10):
        reworded = _EMAIL.sub(r"\1 (at) \2", cleaned)
        if reworded == cleaned:
            break
        cleaned = reworded
    cleaned = _escape(cleaned)
    for i, escape in enumerate(kept_escapes):
        cleaned = cleaned.replace(_KEPT_ESCAPE.format(i), escape)
    # Re-read the result as the renderer will, with verified links still hidden as placeholders.
    leftover = _leftover_address(cleaned)
    for i, markdown in enumerate(kept):
        cleaned = cleaned.replace(_PLACEHOLDER.format(i), markdown)
    return cleaned, report, leftover
