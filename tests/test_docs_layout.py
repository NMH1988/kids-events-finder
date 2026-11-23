"""The plan index, the ticket files and the progress log agree, and doc links resolve (T1.4)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

PLAN_BACK = re.compile(
    r"^\[Implementation plan\]\(\.\./IMPLEMENTATION_PLAN\.md\) · (Epic \d+: .+)$"
)
PROGRESS_BACK = "[Progress log](../PROGRESS.md)"
TICKET_HEADING = re.compile(r"^### (T\d+\.\d+[a-z]?) (.+?) · status: (.+?) · issue .+$")
ENTRY_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) · (T\d+\.\d+[a-z]?) ")
EPIC_HEADING = re.compile(r"^## (Epic \d+: .+)$")
LIST_LINE = re.compile(r"^- \[(.*)\]\((tickets|progress)/([^)]+)\)$")
TABLE_ROW = re.compile(r"^\| (?:\[(T[^\]]+)\]\(tickets/([^)]+)\)|(T\d+\.\d+[a-z]?)) \|")
LINK = re.compile(r"!?\[[^\]]*\]\(<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\)")
CODE_SPAN = re.compile(r"(`+).*?\1")
STATUSES = {"todo", "in progress", "in review", "done", "dropped"}
NEEDS_ENTRY = {"in progress", "in review", "done"}


def index_lines(index: str, folder: str) -> list[tuple[str, str]]:
    """Return (link text, file name) for each list line of an index linking into the folder."""
    return [
        (m[1], m[3])
        for line in index.splitlines()
        if (m := LIST_LINE.match(line)) and m[2] == folder
    ]


def listed_epics(plan: str) -> dict[str, str]:
    """Return ticket file name -> the epic whose list holds it."""
    epics, epic = {}, ""
    for line in plan.splitlines():
        if m := EPIC_HEADING.match(line):
            epic = m[1]
        elif (m := LIST_LINE.match(line)) and m[2] == "tickets":
            epics[m[3]] = epic
    return epics


def status_word(status: str) -> str:
    """Return a status's keyword: the text before any comma or bracket ("dropped (why)")."""
    return re.split(r"[,(]", status)[0].strip()


def legend_statuses(plan: str) -> set[str]:
    """Return the backticked status words of the plan's status legend."""
    lines = plan.splitlines()
    start = lines.index("## Status legend")
    legend = next(line for line in lines[start + 1 :] if line.strip())
    return set(re.findall(r"`([^`]+)`", legend))


def order_rows(plan: str, problems: list[str]) -> dict[str, list[str]]:
    """Return ticket file name -> cells of its order-table row, noting malformed rows."""
    rows: dict[str, list[str]] = {}
    for line in plan.splitlines():
        m = TABLE_ROW.match(line)
        if not m:
            continue
        if m[3]:
            problems.append(f"{m[3]}: order-table row without a link to its file")
            continue
        if m[2] != f"{m[1]}.md":
            problems.append(f"{m[1]}: order-table row links {m[2]}")
        if m[2] in rows:
            problems.append(f"{m[2]}: more than one row in the order table")
        rows[m[2]] = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return rows


def ticket_problems(plan: str, tickets: dict[str, str]) -> list[str]:
    """Return how the plan index and the ticket files (name -> text) disagree."""
    problems: list[str] = []
    listed = index_lines(plan, "tickets")
    names = [name for _, name in listed]
    problems += [
        f"{n}: listed {names.count(n)} times" for n in sorted(set(names)) if names.count(n) > 1
    ]
    rows = order_rows(plan, problems)
    problems += [f"{n}: in an epic list, but no such file" for n in names if n not in tickets]
    problems += [f"{n}: in the order table, but no such file" for n in rows if n not in tickets]
    epics = listed_epics(plan)
    for name, text in sorted(tickets.items()):
        lines = text.splitlines()
        back = PLAN_BACK.match(lines[0]) if lines else None
        if not back or len(lines) < 3 or lines[1]:
            problems.append(f"{name}: does not start with the link back to the plan")
            continue
        if name in epics and epics[name] != back[1]:
            problems.append(f"{name}: its back link names {back[1]!r}, listed in {epics[name]!r}")
        heading = TICKET_HEADING.match(lines[2])
        if not heading:
            problems.append(f"{name}: no ticket heading on its third line")
            continue
        if name != f"{heading[1]}.md":
            problems.append(f"{name}: the heading names {heading[1]}")
        if status_word(heading[3]) not in STATUSES:
            problems.append(f"{name}: status {heading[3]!r} is not in the legend")
        title = lines[2][4:].split(" · status:")[0]
        if (title, name) not in listed:
            problems.append(f"{name}: no epic list line reading {title!r}")
        if name not in rows:
            problems.append(f"{name}: no row in the order table")
            continue
        cells = rows[name]
        if len(cells) != 5:
            problems.append(f"{name}: its order-table row has {len(cells)} cells, not 5")
            continue
        if f"{cells[1]} ({cells[2]})" != heading[2]:
            problems.append(f"{name}: title and size {heading[2]!r} differ in the table")
        if status_word(cells[4]) != status_word(heading[3]):
            problems.append(f"{name}: status {heading[3]!r} in its file, {cells[4]!r} in the table")
    return problems


def progress_problems(index: str, entries: dict[str, str]) -> list[str]:
    """Return how the progress index and the entry files (name -> text) disagree."""
    problems: list[str] = []
    listed = index_lines(index, "progress")
    names = [name for _, name in listed]
    problems += [
        f"{n}: listed {names.count(n)} times" for n in sorted(set(names)) if names.count(n) > 1
    ]
    problems += [f"{n}: in the index, but no such file" for n in names if n not in entries]
    for name, text in sorted(entries.items()):
        lines = text.splitlines()
        if len(lines) < 3 or lines[0] != PROGRESS_BACK or lines[1]:
            problems.append(f"{name}: does not start with the link back to the log")
            continue
        heading = ENTRY_HEADING.match(lines[2])
        if not heading:
            problems.append(f"{name}: no entry heading on its third line")
            continue
        if not re.fullmatch(rf"{heading[1]}-{re.escape(heading[2])}(?:-\d+)?\.md", name):
            problems.append(f"{name}: its name does not follow its heading")
        if (lines[2][3:], name) not in listed:
            problems.append(f"{name}: no index line reading {lines[2][3:]!r}")
    return problems


def cross_problems(tickets: dict[str, str], entries: dict[str, str]) -> list[str]:
    """Return progress entries naming no ticket file, and started tickets with no entry."""
    problems = []
    logged = set()
    for name, text in sorted(entries.items()):
        lines = text.splitlines()
        heading = ENTRY_HEADING.match(lines[2]) if len(lines) > 2 else None
        if not heading:
            continue
        logged.add(heading[2])
        if f"{heading[2]}.md" not in tickets:
            problems.append(f"{name}: names {heading[2]}, but there is no such ticket file")
    for name, text in sorted(tickets.items()):
        lines = text.splitlines()
        heading = TICKET_HEADING.match(lines[2]) if len(lines) > 2 else None
        if heading and status_word(heading[3]) in NEEDS_ENTRY and heading[1] not in logged:
            problems.append(f"{name}: status {heading[3]!r} but no progress entry")
    return problems


def broken_links(path: Path, text: str) -> list[str]:
    """Return the relative link targets in a Markdown file that point to no file."""
    broken, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence:
            continue
        for target in LINK.findall(CODE_SPAN.sub("", line)):
            if re.match(r"^(?:[a-z][a-z0-9+.-]*:|#)", target, re.I):
                continue
            file_part = re.split(r"[#?]", target)[0]
            if file_part and not (path.parent / file_part.replace("%20", " ")).exists():
                broken.append(target)
    return broken


def read_folder(folder: Path) -> dict[str, str]:
    """Return every Markdown file in a folder as name -> text."""
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.md"))}


def doc_files() -> list[Path]:
    """Return the Markdown files whose links are checked: docs/ (all levels), README, CLAUDE."""
    return [*sorted(DOCS.rglob("*.md")), ROOT / "README.md", ROOT / "CLAUDE.md"]


def test_plan_index_agrees_with_the_ticket_files():
    """Every ticket file has its epic list line and order-table row, with the same status."""
    plan = (DOCS / "IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    tickets = read_folder(DOCS / "tickets")
    assert tickets, "docs/tickets/ holds no ticket"
    assert ticket_problems(plan, tickets) == []


def test_progress_index_agrees_with_the_entry_files():
    """Every entry file has exactly one index line reading as its heading, and back."""
    index = (DOCS / "PROGRESS.md").read_text(encoding="utf-8")
    entries = read_folder(DOCS / "progress")
    assert entries, "docs/progress/ holds no entry"
    assert progress_problems(index, entries) == []


def test_every_entry_names_a_ticket_and_every_started_ticket_has_an_entry():
    """Progress entries and ticket files point at each other."""
    tickets = read_folder(DOCS / "tickets")
    entries = read_folder(DOCS / "progress")
    assert cross_problems(tickets, entries) == []


GOOD_PLAN = (
    "## Epic 1: Foundation\n"
    "| [T1.1](tickets/T1.1.md) | Title | S | none | done |\n"
    "- [T1.1 Title (S)](tickets/T1.1.md)\n"
)
GOOD_TICKET = (
    "[Implementation plan](../IMPLEMENTATION_PLAN.md) · Epic 1: Foundation\n\n"
    "### T1.1 Title (S) · status: done · issue #1\n"
)
GOOD_ENTRY = "[Progress log](../PROGRESS.md)\n\n## 2026-11-23 · T1.1 Title · PR #2\n"
GOOD_INDEX = "- [2026-11-23 · T1.1 Title · PR #2](progress/2026-11-23-T1.1.md)\n"


def test_the_status_words_match_the_plan_legend():
    """The statuses the test accepts are exactly those of the plan's legend."""
    plan = (DOCS / "IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert legend_statuses(plan) == STATUSES


def test_a_dropped_status_with_its_reason_is_accepted():
    """The legend's "dropped (reason)" form passes the status check."""
    plan = GOOD_PLAN.replace("| done |", "| dropped (superseded by T1.2) |")
    ticket = GOOD_TICKET.replace("status: done", "status: dropped (superseded by T1.2)")
    assert ticket_problems(plan, {"T1.1.md": ticket}) == []


def test_the_checkers_accept_a_consistent_layout():
    """A plan, ticket, index and entry that agree give no problem."""
    tickets, entries = {"T1.1.md": GOOD_TICKET}, {"2026-11-23-T1.1.md": GOOD_ENTRY}
    assert ticket_problems(GOOD_PLAN, tickets) == []
    assert progress_problems(GOOD_INDEX, entries) == []
    assert cross_problems(tickets, entries) == []


@pytest.mark.parametrize(
    ("plan", "name", "ticket", "expected"),
    [
        (GOOD_PLAN.replace("| done |", "| todo |"), "T1.1.md", GOOD_TICKET, "in its file"),
        (
            GOOD_PLAN.replace("| done |", "| doen |"),
            "T1.1.md",
            GOOD_TICKET.replace("status: done", "status: doen"),
            "not in the legend",
        ),
        (GOOD_PLAN, "T1.1.md", GOOD_TICKET.replace("Epic 1: Foundation", "Epic 2: X"), "listed in"),
        (
            GOOD_PLAN.splitlines()[0] + "\n" + GOOD_PLAN.splitlines()[2],
            "T1.1.md",
            GOOD_TICKET,
            "no row",
        ),
        (GOOD_PLAN + GOOD_PLAN.splitlines()[2], "T1.1.md", GOOD_TICKET, "listed 2 times"),
        (GOOD_PLAN, "T1.2.md", GOOD_TICKET, "the heading names T1.1"),
        (GOOD_PLAN, "T1.1.md", GOOD_TICKET.replace("Title (S)", "Other (S)"), "no epic list line"),
        (GOOD_PLAN.replace("| Title |", "| Old |"), "T1.1.md", GOOD_TICKET, "differ in the table"),
        (GOOD_PLAN.replace("| S |", "| M |"), "T1.1.md", GOOD_TICKET, "differ in the table"),
        (
            GOOD_PLAN.replace("[T1.1](tickets/T1.1.md)", "T1.1"),
            "T1.1.md",
            GOOD_TICKET,
            "without a link",
        ),
        (
            GOOD_PLAN.replace("(tickets/T1.1.md) |", "(tickets/T1.9.md) |"),
            "T1.1.md",
            GOOD_TICKET,
            "row links",
        ),
        (GOOD_PLAN + GOOD_PLAN.splitlines()[1], "T1.1.md", GOOD_TICKET, "more than one row"),
        (GOOD_PLAN.replace("| none |", ""), "T1.1.md", GOOD_TICKET, "not 5"),
        (GOOD_PLAN, "T1.2.md", "x", "in an epic list, but no such file"),
        (GOOD_PLAN, "T1.2.md", "x", "in the order table, but no such file"),
        (GOOD_PLAN, "T1.1.md", GOOD_TICKET.replace("[Implementation", "[Plan"), "link back"),
        (GOOD_PLAN, "T1.1.md", GOOD_TICKET.replace("### T1.1", "## T1.1"), "no ticket heading"),
    ],
)
def test_ticket_problems_catches_each_disagreement(plan, name, ticket, expected):
    """Each way the plan and a ticket file can disagree is reported."""
    assert any(expected in problem for problem in ticket_problems(plan, {name: ticket}))


@pytest.mark.parametrize(
    ("index", "name", "entry", "expected"),
    [
        ("", "2026-11-23-T1.1.md", GOOD_ENTRY, "no index line"),
        (GOOD_INDEX, "2026-11-24-T1.1.md", GOOD_ENTRY, "in the index, but no such file"),
        (GOOD_INDEX * 2, "2026-11-23-T1.1.md", GOOD_ENTRY, "listed 2 times"),
        (GOOD_INDEX, "2026-11-23-T1.1.md", GOOD_ENTRY.replace("[Progress", "[Log"), "link back"),
        (
            GOOD_INDEX,
            "2026-11-23-T1.1.md",
            GOOD_ENTRY.replace("## 2026", "## Nov 2026"),
            "no entry",
        ),
        (GOOD_INDEX, "2026-11-23-T1.2.md", GOOD_ENTRY, "does not follow its heading"),
    ],
)
def test_progress_problems_catches_each_disagreement(index, name, entry, expected):
    """Each way the progress index and an entry file can disagree is reported."""
    assert any(expected in problem for problem in progress_problems(index, {name: entry}))


def test_cross_problems_catches_a_missing_ticket_and_a_missing_entry():
    """An entry for an unknown ticket, and a done ticket with no entry, are reported."""
    problems = cross_problems(
        {"T1.1.md": GOOD_TICKET}, {"2026-11-23-T9.9.md": GOOD_ENTRY.replace("T1.1", "T9.9")}
    )
    assert any("T9.9" in problem and "no such ticket" in problem for problem in problems)
    assert any("T1.1.md" in problem and "no progress entry" in problem for problem in problems)


def test_broken_links_finds_a_missing_target(tmp_path):
    """A relative link to a missing file is reported; web links, anchors and code are not."""
    (tmp_path / "here.md").write_text("x", encoding="utf-8")
    text = "[a](missing.md) [b](here.md) [c](https://example.org) [d](#top) `[e](gone.md)`"
    assert broken_links(tmp_path / "doc.md", text) == ["missing.md"]


@pytest.mark.parametrize("path", doc_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_point_to_files(path):
    """Every relative Markdown link in the docs, the README and CLAUDE.md finds its file."""
    assert broken_links(path, path.read_text(encoding="utf-8")) == []
