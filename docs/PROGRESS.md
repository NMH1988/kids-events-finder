# Progress log

What each PR did and why, newest first. This file is the index: one line per entry; each entry is a file of its own in `docs/progress/`. **Read this before starting a ticket**: this index, the open PRs (`gh pr list --state open`), and the entries of the tickets the new one builds on, changes or names as a follow-up, so earlier decisions and loose ends are not lost.

**Adding an entry:** every PR (Dependabot exempt) adds, in the same PR, so the log reaches `main` together with the work:
1. a file `docs/progress/<YYYY-MM-DD>-<ticket ID>.md` (e.g. `2026-11-23-T1.4.md`; `-2` added for a second entry of the same ticket on the same day), whose first line is the link back to this index (`[Progress log](../PROGRESS.md)`), then an empty line, then the entry in the format below;
2. one line at the top of the list below: `- [<the entry's heading without "## ">](progress/<file name>)`.

Keep the entry short and record what the code does not say: decisions, gotchas, what was not checked, follow-ups. `tests/test_docs_layout.py` checks that every entry file has its line here, with the same text as its heading, and every line its file. Parallel PRs all add a line at the top, so they conflict here: keep both lines (`.gitattributes` sets `merge=union` for this file, which handles local merges; GitHub's web conflict editor ignores it).

**Entry format**

```
## <YYYY-MM-DD> · <ticket ID> <ticket title> · PR #<n> (closes #<issue>)
- **Serves:** <Capstone requirement and legal sections, as in the ticket>
- **What:** <the changes, file by file where it helps>
- **Why:** <the reasons a reader of the code would not see>
- **Reviews:** <code-reviewer, legal-reviewer, security-reviewer: last round and verdict>
- **Decisions & gotchas:** <owner decisions, surprises, what was not checked>
- **Follow-ups:** <tickets or open points, or "none">
```

**Numbers with `#`:** `#<n>` is an issue or PR in https://github.com/NMH1988/kids-events-finder.

## Entries

- [2026-11-26 · T5.12 UI design from the mockups into the Epic 5 tickets · PR #43 (closes #39)](progress/2026-11-26-T5.12.md)
- [2026-11-25 · T1.10 ui-designer agent: research and propose a legally safe UI design · PR #37 (closes #36)](progress/2026-11-25-T1.10.md)
- [2026-11-24 · T1.9 Third-party terms file and the owner's rules on outside services and keys · PR #29 (closes #28)](progress/2026-11-24-T1.9.md)
- [2026-11-24 · T5.1 Live progress while the agent works · PR #26 (closes #20)](progress/2026-11-24-T5.1.md)
- [2026-11-24 · T1.6 QRSPI workflow skill and stronger code and legal reviewers · PR #17 (closes #16)](progress/2026-11-24-T1.6.md)
- [2026-11-23 · T1.5 Owner review O1-O3: knowledge base, fares, prompt and evaluation questions · PR #15 (closes #14)](progress/2026-11-23-T1.5.md)
- [2026-11-23 · T1.4 Docs: ticket files, plan index and progress log · PR #13 (closes #12)](progress/2026-11-23-T1.4.md)
- [2026-11-20 · T2.1 Legal hardening group 1: privacy check, AI disclosure, money from code · PR #11 (closes #3)](progress/2026-11-20-T2.1.md)
- [2026-11-20 · T1.3 Budget day trips, age groups and legal compliance rules · PR #2](progress/2026-11-20-T1.3.md)
- [2026-11-19 · T1.2 CI: GitHub Actions for ruff and pytest · PR #1](progress/2026-11-19-T1.2.md)
- [2026-11-19 · T1.1 Initial scaffold: kids outing agent with HITL and advanced RAG · commit fd9b36a](progress/2026-11-19-T1.1.md)
