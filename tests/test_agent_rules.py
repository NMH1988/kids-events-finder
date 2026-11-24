"""Checks that the reviewer agents and the qrspi skill keep their safety rules (T1.6)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / ".claude" / "agents"
REVIEWERS = ["code-reviewer.md", "legal-reviewer.md", "security-reviewer.md"]
SKILL = ROOT / ".claude" / "skills" / "qrspi" / "SKILL.md"
STORED = [".streamlit/secrets.toml", ".env", "data/feedback/", "data/eval_runs/", "chroma/"]


def read(name: str) -> str:
    """Return the text of one reviewer agent file."""
    return (AGENTS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", REVIEWERS)
def test_reviewers_fetch_the_pr_by_number_not_by_branch_name(name):
    """A PR's branch name can hold shell syntax, so agents fetch pull/<n>/head instead."""
    text = read(name)
    assert "git fetch origin pull/<n>/head" in text
    assert "git fetch origin <headRefName>" not in text
    assert "git fetch origin <branch>" not in text


@pytest.mark.parametrize("name", REVIEWERS)
def test_reviewers_name_every_secret_and_stored_data_path(name):
    """Every reviewer is told never to open the key files or stored user data."""
    text = read(name)
    for path in STORED:
        assert path in text, path


def test_skill_names_every_secret_and_stored_data_path():
    """The qrspi skill bans the same paths in its Research phase."""
    text = SKILL.read_text(encoding="utf-8")
    for path in STORED:
        assert path in text, path


@pytest.mark.parametrize("name", ["code-reviewer.md", "legal-reviewer.md"])
def test_round_queries_count_only_the_owners_comments(name):
    """A stranger's comment cannot fake a review round."""
    queries = [line for line in read(name).splitlines() if "--jq" in line and "round" in line]
    assert queries
    for line in queries:
        assert 'select(.author.login == "NMH1988")' in line


@pytest.mark.parametrize("name", REVIEWERS)
def test_reviewers_use_no_fixed_heredoc_delimiter_or_shell_variable(name):
    """Posting uses an unguessable delimiter and plain calls, not $(...) or a reused variable."""
    text = read(name)
    assert not re.search(r"<<'(REVIEW|LEGAL|SECURITY|COMPLIANCE)_EOF'", text)
    assert "$(git branch" not in text
    assert '--head "$b"' not in text


@pytest.mark.parametrize("name", REVIEWERS)
def test_reviewers_run_no_code_from_someone_elses_pr(name):
    """Local checks run only on the owner's own, non-fork PR."""
    text = read(name)
    assert "isCrossRepository" in text
    assert "--disable-warnings" in text
