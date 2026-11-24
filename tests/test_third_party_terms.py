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


@pytest.mark.parametrize("host", sorted(code_hosts()))
def test_every_outside_host_in_the_code_has_an_entry(host):
    """Each host the code calls or links appears in the terms file."""
    registrable = ".".join(host.split(".")[-2:])
    assert registrable in terms(), f"{host}: add an entry to docs/THIRD_PARTY_TERMS.md"


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
    assert "- **Terms:**" in entry or "- **Rules we keep:**" in entry or "Open questions" in entry
    for found in re.findall(r"checked (\d{4}-\d{2}-\d{2})", entry):
        assert date.fromisoformat(found) <= date.today()


def test_the_red_team_incident_is_recorded():
    """The live red-team run of 2026-11-24 and its open decision are on record."""
    incidents = terms().split("## Incidents and decisions", 1)[1].split("\n## ", 1)[0]
    assert "2026-11-24, red-team run on OpenRouter (T1.8)" in incidents
    assert "**Open decision" in incidents
