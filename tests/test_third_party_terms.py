"""Checks that docs/THIRD_PARTY_TERMS.md covers outside services and the owner's rules (T1.9)."""

import ast
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TERMS = ROOT / "docs" / "THIRD_PARTY_TERMS.md"
CODE = [
    *sorted((ROOT / "src").rglob("*.py")),
    *sorted((ROOT / "scripts").glob("*.py")),
    *sorted((ROOT / "views").rglob("*.py")),
    ROOT / "app.py",
]
HOST = re.compile(r"https?://([A-Za-z0-9.-]+)")


def terms() -> str:
    """Return the text of the third-party terms file."""
    return TERMS.read_text(encoding="utf-8")


def code_hosts() -> set[str]:
    """Return every host named in a string literal of the app's and the scripts' code."""
    hosts = set()
    for path in CODE:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                hosts.update(HOST.findall(node.value))
    return hosts


def entries() -> dict[str, str]:
    """Return each service entry of the file by its heading."""
    parts = re.split(r"^### ", terms().split("## Services", 1)[1], flags=re.MULTILINE)
    return {part.splitlines()[0]: part for part in parts[1:]}


def test_the_code_names_the_known_outside_hosts():
    """A control: the scan finds the services the app calls, so an empty scan cannot pass."""
    assert {"openrouter.ai", "overpass-api.de", "api.open-meteo.com"} <= code_hosts()


def named_host(host: str, text: str) -> bool:
    """Return True when the exact host is in the text, not only as a subdomain's tail."""
    return re.search(rf"(?<![\w.-]){re.escape(host)}(?![\w-])", text) is not None


@pytest.mark.parametrize("host", sorted(code_hosts()))
def test_every_outside_host_in_the_code_has_an_entry(host):
    """Each exact host the code calls or links appears in the services part of the terms file."""
    services = terms().split("## Services", 1)[1]
    assert named_host(host, services), f"{host}: add it to an entry in docs/THIRD_PARTY_TERMS.md"


@pytest.mark.parametrize("host", ["nominatim.openstreetmap.org", "api.github.com"])
def test_a_new_subdomain_is_not_covered_by_its_parent_domain(host):
    """A control: a host the file does not name fails, even when its domain is named."""
    assert not named_host(host, terms())


@pytest.mark.parametrize(
    "path",
    sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in CODE
        if re.search(r"\brequests\.(get|post|request|head)\(", p.read_text(encoding="utf-8"))
    ),
)
def test_every_module_that_makes_requests_is_covered(path):
    """A module sending HTTP requests is named in the file, or its calls are named by config."""
    text = terms()
    module_named = f"`{path}`" in text
    config_named = path in {"src/tools/external.py", "src/geo.py"} and "`config." in text
    assert module_named or config_named, f"{path}: name it in docs/THIRD_PARTY_TERMS.md"


def test_the_key_rule_names_how_each_provider_takes_its_key():
    """Rule 2 says how OpenRouter and Ticketmaster take their keys and what is never logged."""
    rules = terms().split("## The owner's rules (2026-11-24, mandatory)", 1)[1].split("\n## ", 1)[0]
    assert "the OpenRouter key only in the authorisation header" in rules
    assert "the Ticketmaster key in the `apikey` query parameter" in rules
    assert "`response.url` and the text of a request error are never logged" in rules
    for place in ("`~/.streamlit/`", "`printenv`", "`gh auth token`", "`config.get_api_key()`"):
        assert place in rules


def test_the_checklist_limits_fetching_the_terms_again():
    """Re-reading terms fetches only the listed URLs with web-fetch; wikis go to the owner."""
    checklist = terms().split("## Checklist before any live or paid run", 1)[1].split("\n## ", 1)[0]
    for phrase in ("Fetch only the URLs the entry lists", "never `curl`", "as data", "by hand"):
        assert phrase in checklist


def test_the_file_starts_with_the_owners_two_rules():
    """The two rules of 2026-11-24 come first and say what they forbid."""
    text = terms()
    rules = text.split("## The owner's rules (2026-11-24, mandatory)", 1)[1].split("\n## ", 1)[0]
    assert text.index("## The owner's rules") < text.index("## Services")
    assert "**Never violate the terms, policies or usage rules of any service" in rules
    assert "**Never expose the OpenRouter key, or any other key, in any form.**" in rules
    for phrase in ("red-teaming", "rate or volume limits", "masked or encoded", "rotated"):
        assert phrase in rules


def test_the_checklist_covers_red_teaming_limits_and_stale_entries():
    """The live-run checklist names the 30-day re-check, red-teaming, limits and the owner."""
    checklist = terms().split("## Checklist before any live or paid run", 1)[1].split("\n## ", 1)[0]
    for phrase in ("**30 days**", "**No adversarial or red-team prompts**", "HTTP 429", "owner"):
        assert phrase in checklist


@pytest.mark.parametrize(
    "service",
    [
        "OpenRouter",
        "OpenAI",
        "Qwen",
        "Open-Meteo",
        "Overpass",
        "Ticketmaster",
        "Transitous",
        "Google Maps",
        "GitHub",
        "PyPI",
        "bahn.de",
    ],
)
def test_every_service_has_its_entry(service):
    """Each service named in the ticket has a heading of its own."""
    assert any(service in heading for heading in entries()), service


@pytest.mark.parametrize("heading", sorted(entries()))
def test_every_entry_says_what_we_use_and_where_its_terms_are(heading):
    """Each entry states what we use and its terms or rules, with dates where they were read."""
    entry = entries()[heading]
    assert "- **What we use:**" in entry
    assert "- **Terms:**" in entry
    for found in re.findall(r"checked (\d{4}-\d{2}-\d{2})", entry):
        assert date.fromisoformat(found) <= date.today()


def test_the_red_team_incident_is_recorded():
    """The live red-team run of 2026-11-24 and its open decision are on record."""
    incidents = terms().split("## Incidents and decisions", 1)[1].split("\n## ", 1)[0]
    assert "2026-11-24, red-team run on OpenRouter (T1.8)" in incidents
    assert "**Open decision" in incidents
