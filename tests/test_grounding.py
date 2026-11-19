"""Tests for the grounding check that removes links and images no tool returned."""

import json

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from markdown_it import MarkdownIt

from src.grounding import allowed_urls, enforce_grounding

MAPS = "https://www.google.com/maps/dir/?api=1&destination=Zoo%2C+Berlin"
ALLOWED = {"https://a.org", MAPS}
# CommonMark plus GFM-style tables and strikethrough, close to what Streamlit renders.
_PARSER = MarkdownIt("commonmark").enable(["table", "strikethrough"])


def _tool(payload: dict) -> ToolMessage:
    """Build a tool message holding a JSON payload."""
    return ToolMessage(content=json.dumps(payload), tool_call_id="1", name="t")


def _rendered_targets(markdown: str) -> list[tuple[str, str]]:
    """Return (kind, target) for every link, image and HTML a renderer would produce."""
    targets = []

    def walk(tokens):
        """Collect link and image targets from tokens and their children."""
        for token in tokens:
            if token.type == "link_open":
                targets.append(("link", token.attrGet("href") or ""))
            elif token.type == "image":
                targets.append(("image", token.attrGet("src") or ""))
            elif token.type in ("html_inline", "html_block"):
                targets.append(("html", token.content))
            if token.children:
                walk(token.children)

    walk(_PARSER.parse(markdown))
    return targets


def test_allowed_urls_come_only_from_url_fields_of_tool_results():
    """Links come from tool URL fields, never from the user's message or echoed text fields."""
    messages = [
        HumanMessage("see https://evil.example"),
        _tool({"results": [{"website": "https://a.org", "maps_url": "https://maps/x?y=1"}]}),
        _tool({"items": [{"label": "Zoo", "note": "https://evil.example/p.png"}]}),
        _tool({"city": "https://evil.example", "source_urls": ["https://bahn.de/x"]}),
    ]
    assert allowed_urls(messages) == {"https://a.org", "https://maps/x?y=1", "https://bahn.de/x"}


def test_tool_error_text_cannot_make_a_link_verified():
    """A non-JSON tool result (an error echoing the model's arguments) gives no allowed URLs."""
    error = ToolMessage(
        content="Error invoking tool with kwargs {'country': 'https://evil.example/p.png '}",
        tool_call_id="1",
        name="search_knowledge_base",
    )
    assert allowed_urls([error]) == set()


def test_verified_links_stay_and_invented_ones_are_removed():
    """A link from a tool stays; an invented one becomes plain text and is reported."""
    answer = "[Website](https://a.org/) and [Fake](https://invented.example/page) see https://b.org"
    cleaned, report = enforce_grounding(answer, {"https://a.org"})
    assert _rendered_targets(cleaned) == [("link", "https://a.org/")]
    assert "invented.example" not in cleaned and "b.org" not in cleaned
    assert report.removed == ["https://invented.example/page", "https://b.org"]


ATTACKS = [
    "![](https://evil.example/p.png?b=100)",
    "![pic](https://evil.example/p.png)",
    "[](https://evil.example/x)",
    '[Zoo](https://evil.example/x "Zoo")',
    "![z](https://evil.example/p.png 'z')",
    "www.evil.example/page",
    "(https://evil.example/x)",
    "![z](HTTPS://evil.example/p.png)",
    "![z](//evil.example/p.png)",
    "![z](https&#58;//evil.example/p.png)",
    "![z](https\\://evil.example/p.png)",
    "[x][r]\n\n[r]: https&#58;//evil.example/p.png",
    "<https://evil.example/x>",
    "![z](<https://evil.example/p.png>)",
    "[js](javascript:alert(1))",
    "[a [b] c](javascript:alert(1))",
    "![a [b] c](http:evil.example/p.png?ages=3-5)",
    "![a\\]b](https:evil.example/p.png?b=100)",
    "![x](<https:evil.example/p b.png?b=100>)",
    '![x](https:evil.example/p.png "a\\"b")',
    "![x][r]\n\n> [r]: https:evil.example/p.png",
    "![x][r]\n\n- [r]: https:evil.example/p.png",
    "![x][r]\n\n[r]:\nhttps:evil.example/p.png",
    ":red[![a [b]](https:evil.example/p.png)]",
    '<img src="https:evil.example/p.png">',
    '<a href="https:evil.example">x</a>',
    "[![img](https://evil.example/p.png)](https://a.org)",
    "[x](data:image/png;base64,AAAA)",
    "$\\href{https://evil.example}{x}$",
    r"\[click\](https\\:\\/\\/evil.example/a(b)?ages=3-5)",
    r"\[click\](https&amp;#58;//evil.example/a)",
    "\\\\[x\\\\](https://evil.example/a)",
    "!\x000\x00 [Zoo](https://a.org)",
    "_https://evil.example/p.png?b=1_",
    "_www.evil.example/p_",
    'https://a.org"@evil.example/?ages=3-5',
    "https://a.org'@evil.example/?ages=3-5",
    "kids@evil.example",
    "[mail](mailto:kids@evil.example)",
    "```mermaid\nflowchart LR\n  A@{ img: '\\\\evil.example/p.png', label: 'Zoo' }\n```",
    "~~~mermaid\nflowchart LR\n  A@{ img: 'https://evil.example/p.png' }\n~~~",
]


@pytest.mark.parametrize("attack", ATTACKS)
def test_no_unverified_link_image_or_html_can_render(attack):
    """Whatever the syntax, a renderer finds no image, no HTML and only verified links."""
    cleaned, _ = enforce_grounding(f"Ideas: {attack} done", ALLOWED)
    for kind, target in _rendered_targets(cleaned):
        assert kind == "link" and target in ALLOWED, (kind, target, cleaned)
    # No code block (e.g. a Mermaid diagram) and no unescaped e-mail autolink can form.
    tokens = _PARSER.parse(cleaned)
    assert not any(t.type in ("fence", "code_block") for t in tokens), cleaned
    assert "@evil" not in cleaned.replace("\\@", "")


def test_images_are_dropped_even_from_a_verified_host():
    """An image would load without a click, so even a tool URL is never shown as an image."""
    for answer in ("![zoo](https://a.org)", "[![zoo](https://a.org)](https://a.org)"):
        cleaned, _ = enforce_grounding(answer, ALLOWED)
        assert all(kind != "image" for kind, _ in _rendered_targets(cleaned)), cleaned


@pytest.mark.parametrize("text", ["https://evil.example/login", "paypal.com/login", "www.x.de"])
def test_verified_link_text_cannot_show_another_address(text):
    """Link text that looks like an address is replaced, so it cannot hide where it goes."""
    cleaned, _ = enforce_grounding(f"[{text}](https://a.org)", ALLOWED)
    assert cleaned == "[a.org](https://a.org)"


def test_verified_url_with_entity_like_query_is_kept_intact():
    """Query parts like &region= or &sect= are not decoded into symbols."""
    url = "https://example.org/zoo?a=1&region=1&sect=A"
    cleaned, report = enforce_grounding(f"[Zoo]({url})", {url})
    assert _rendered_targets(cleaned) == [("link", url)] and report.grounded


def test_prices_and_escapes_render_the_same_on_every_turn():
    """Dollar prices stay plain text, and cleaning an already cleaned answer changes nothing."""
    answer = "Tickets $15 for adults, $10 for kids; ages <6 free [optional]."
    once, _ = enforce_grounding(answer, ALLOWED)
    twice, _ = enforce_grounding(once, ALLOWED)
    assert once == twice
    assert _rendered_targets(once) == []
    html = _PARSER.render(once)
    assert "$15" in html and "[optional]" in html


def test_bare_verified_url_keeps_surrounding_punctuation():
    """A verified URL in brackets or at the end of a sentence stays a link."""
    cleaned, report = enforce_grounding("(see https://a.org).", ALLOWED)
    assert report.grounded and report.verified == ["https://a.org"]


def test_trip_plan_fare_rules_link_is_kept():
    """The budget trip plan's fare rules link from the ticket comparison stays a link."""
    url = "https://www.bahn.de/faq/pk/angebot/regionale-angebote/laender-tickets"
    allowed = allowed_urls([_tool({"options": [{"source_urls": [url]}]})])
    cleaned, _ = enforce_grounding(f"- **Ticket:** 44 EUR · [Fare rules]({url})", allowed)
    assert _rendered_targets(cleaned) == [("link", url)]


def test_answer_card_keeps_its_links_and_plain_text():
    """The answer format's Website and Directions links survive; ordinary text stays readable."""
    answer = (
        "### 🦁 Zoo Berlin\nBerlin · zoo · ages 0-17 · outdoor · paid\n\n"
        "Great for weekends & rainy days; open 9//18 per day.\n\n"
        f'[🌐 Website](https://a.org) · [🗺️ Directions]({MAPS} "t")'
    )
    cleaned, report = enforce_grounding(answer, ALLOWED)
    assert _rendered_targets(cleaned) == [("link", "https://a.org"), ("link", MAPS)]
    assert "Great for weekends &amp; rainy days; open 9//18 per day." in _PARSER.render(cleaned)
    assert report.grounded


def test_answer_without_links_is_grounded():
    """An answer with no links passes unchanged."""
    cleaned, report = enforce_grounding("No links here.", set())
    assert cleaned == "No links here." and report.grounded


# Bare-URL attacks: the test parser does not autolink like Streamlit's renderer, so these are
# checked on the text itself - the attacker host must be gone.
BARE_ATTACKS = [
    "_https://evil.example/p.png?b=1_",
    "_www.evil.example/p_",
    'https://a.org"@evil.example/?ages=3-5',
    "https://a.org'@evil.example/?ages=3-5",
    "https://a.org\x85@evil.example/?ages=3-5",
    "&amp;#119;ww.evil.example/p?ages=3-5",
    "&amp;#104;ttps://evil.example/p",
    "www.evil.example/page",
    "Visit HTTP://EVIL.EXAMPLE/x now",
]


@pytest.mark.parametrize("attack", BARE_ATTACKS)
def test_bare_url_attacks_leave_no_attacker_host(attack):
    """Autolink-style attacks lose the attacker host entirely."""
    cleaned, report = enforce_grounding(f"Ideas: {attack} done", ALLOWED)
    assert "evil.example" not in cleaned.lower(), cleaned
    assert report.removed


@pytest.mark.parametrize(
    "hostile",
    [
        "https://zoo.example/a][![i](https://evil.example/p(1).png?c=Berlin)",
        "https://zoo.example/a <img src=x>",
        "https://user@evil.example/",
        'https://zoo.example/a"b',
        "https://zoo.example/a\\b",
        "javascript:alert(1)",
    ],
)
def test_malformed_url_from_a_data_source_is_never_verified(hostile):
    """A hostile website value (e.g. an OSM tag) is not accepted as a verified URL."""
    allowed = allowed_urls([_tool({"results": [{"website": hostile}]})])
    assert allowed == set()
    cleaned, _ = enforce_grounding(f"[🌐 Website]({hostile})", allowed)
    assert all(kind == "link" and "evil" not in t for kind, t in _rendered_targets(cleaned))
    assert "evil.example" not in cleaned.replace("\\", "")


def test_email_addresses_are_not_turned_into_mail_links():
    """An e-mail address is written as name (at) host, so no renderer makes a mail link."""
    cleaned, _ = enforce_grounding("Write to kids@evil.example for tickets.", ALLOWED)
    assert "kids (at) evil.example" in cleaned and "@" not in cleaned


def test_intentional_escapes_are_kept_as_written():
    """Escapes the model wrote on purpose (table pipes, #, -, numbers, stars) survive unchanged."""
    answer = (
        "| a | x \\| y | z |\n|---|---|---|\n\n"
        "\\# not a heading\n\\- not a list\n2026\\. ok \\*x\\*"
    )
    cleaned, _ = enforce_grounding(answer, ALLOWED)
    assert cleaned == answer
    html = _PARSER.render(cleaned)
    assert "<h1>" not in html and "<li>" not in html and "<em>" not in html
