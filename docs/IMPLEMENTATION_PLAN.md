# Implementation plan

Epics, tickets, acceptance criteria, dependencies, order and status. This file and the progress log (`docs/PROGRESS.md`) are the record of the work that travels with the repo when it is copied to the course repository (GitHub issues and PRs do not), so keep each ticket's status current: every PR updates the status of its ticket.

**Where the tickets are:** this file is the index (owner tasks, the order table, and each epic's list of tickets); each ticket is a file of its own, `docs/tickets/T<x.y>.md`. A ticket's status is in two places, which change together: the heading in its file and its row in the order table. A new ticket gets:
1. its file, whose first line is the link back to this index and its epic (e.g. `[Implementation plan](../IMPLEMENTATION_PLAN.md) · Epic 1: Foundation`), then an empty line, then the ticket in the format below;
2. a row in the order table;
3. a line in its epic's list: `- [<the heading up to " · status:", without "### ">](tickets/T<x.y>.md)`.

`tests/test_docs_layout.py` checks that these agree.

**Status of this plan:** set up by T1.4 (issue #12) on 2026-11-23, following the layout of the owner's earlier project. T1.1-T1.3 and T2.1 were done before the plan existed; their tickets were written after the fact from their commits and PR descriptions. The open tickets come from the GitHub issues #4-#10 of 2026-11-20; their acceptance criteria were drafted by Claude: T3.1-T3.4's approved by the owner on 2026-11-23 (with the layout), T4.1-T4.3's still to be written. Epic 5 (T5.1-T5.6) was proposed by Claude at the owner's request on 2026-11-24; the owner approved the list and the acceptance criteria that day (T5.6 criteria 8-14, added in T1.8, have their scope approved and their wording confirmed when the ticket starts).

## Status legend

`todo` · `in progress` · `in review` · `done` · `dropped` (with the reason)

## Ticket format

```
### T<epic>.<n> <title> (S/M/L) · status: todo · issue #<n>
**Serves:** Capstone (`docs/CAPSTONE_CHECKLIST.md`): <requirement> or none | beyond the brief (owner's request); Legal (`docs/LEGAL_COMPLIANCE.md`): <sections> or none
**Depends on:** T<x.y>, O<n>, ... or none
**Acceptance criteria**
- [ ] <testable criterion> - verified by <test or check>
**Notes:** files, risks, follow-ups
```

Sizes: S = up to half a day, M = about a day, L = more than a day. A ticket without a GitHub issue writes `issue none` (with its PR, if any); only the work from before this plan has none, every new ticket gets an issue. **Every ticket has testable acceptance criteria**, approved by the owner before it starts; a planned ticket far ahead (Epic 4) may list only its scope until then. Statuses come from the legend (checked by `tests/test_docs_layout.py`).

## Owner tasks

The owner does these (from `docs/CAPSTONE_CHECKLIST.md`, "Owner's to-do before the review"); Claude reviews where asked. Synthetic data only (`docs/LEGAL_COMPLIANCE.md` 8).

| ID | Task | Needed by | Status |
|---|---|---|---|
| O1 | Add `OPENROUTER_API_KEY` (optionally `TICKETMASTER_API_KEY`) to `.streamlit/secrets.toml`, then `python -m scripts.build_index` | O4, live checks | done (2026-11-23: index built, 49 places; no Ticketmaster key) |
| O2 | Review and edit the drafts: the system prompt (`src/prompts/agent_system.md`) and `data/eval_questions.json`; the owner writes, Claude reviews | O4 | done (2026-11-23, T1.5: written by Claude at the owner's request, approved by the owner) |
| O3 | Check the curated entries in `data/knowledge_base.json`, run `python -m scripts.check_links`, re-check the prices in `data/fares.json` on bahn.de | O4 | done (2026-11-23, T1.5: 11 entries fixed, prices unchanged) |
| O4 | Run both evaluation scripts and fill the tables in `docs/EVALUATION.md` | Capstone review | done (2026-11-24, T1.8: run by Claude at the owner's request) |
| O5 | 3-5 user tests with made-up questions, adult testers who agreed beforehand; results written down, no screen or voice recordings, no testers' names with their feedback (`docs/LEGAL_COMPLIANCE.md` 8) | Capstone review | todo |
| O6 | Upload to showcase.turingcollege.com after Epic 5 and before booking the review, and add the link near the top of the README (the GitHub repository exists); update the entry after any later change. Screenshots or a recorded demo only: a publicly reachable copy of the app is a public deployment (`docs/LEGAL_COMPLIANCE.md` 8) | Capstone review | todo |
| O7 | Record a short demo and prepare the 10-minute talk (`docs/PRESENTATION.md`) | Capstone review (2026-12-16) | todo |

## Overview and order

Deadline: **2026-12-16** (Capstone review). The owner tasks O1-O7 come first for the Capstone. Epic 3 is needed only before a public deployment; Epic 4 is beyond the Capstone. The order below is a proposal; the owner sets it.

| Ticket | Title | Size | Depends on | Status |
|---|---|---|---|---|
| [T1.1](tickets/T1.1.md) | Initial scaffold: kids outing agent with HITL and advanced RAG | L | none | done |
| [T1.2](tickets/T1.2.md) | CI: GitHub Actions for ruff and pytest | S | T1.1 | done |
| [T1.3](tickets/T1.3.md) | Budget day trips, age groups and legal compliance rules | L | T1.2 | done |
| [T2.1](tickets/T2.1.md) | Legal hardening group 1: privacy check, AI disclosure, money from code | L | T1.3 | done |
| [T1.4](tickets/T1.4.md) | Docs: ticket files, plan index and progress log | M | none | done |
| [T1.5](tickets/T1.5.md) | Owner review O1-O3: knowledge base, fares, prompt and evaluation questions | M | O1 | done |
| [T1.6](tickets/T1.6.md) | QRSPI workflow skill and stronger code and legal reviewers | S | none | done |
| [T1.7](tickets/T1.7.md) | Enforce the reviewers' never-open and allowlist rules with deny rules and hooks | S | T1.6 | todo |
| [T1.8](tickets/T1.8.md) | Owner task O4: run the evaluations and fill docs/EVALUATION.md | S | T1.5 | done |
| [T1.9](tickets/T1.9.md) | Third-party terms file and the owner's rules on outside services and keys | S | none | done |
| [T5.1](tickets/T5.1.md) | Live progress while the agent works | M | none | done |
| [T5.2](tickets/T5.2.md) | Parent-friendly approval form instead of raw JSON | M | T5.1 | todo |
| [T5.6](tickets/T5.6.md) | Offline red-team tests: injection checks, answer checks and the approval gate | L | none | todo |
| [T5.4](tickets/T5.4.md) | Clear messages when the agent stops | S | T5.1 | todo |
| [T5.3](tickets/T5.3.md) | Trip plan box from the tool results | M | none | todo |
| [T5.5](tickets/T5.5.md) | Source credits for data from earlier turns | S | none | todo |
| [T3.1](tickets/T3.1.md) | Before a public deployment: AI provider with a DPA | M | none | todo |
| [T3.2](tickets/T3.2.md) | Datenschutzerklärung and Impressum | M | T3.1 | todo |
| [T3.3](tickets/T3.3.md) | Invite codes and rate limits | M | none | todo |
| [T3.4](tickets/T3.4.md) | Replace Transitous, then decide on a private repository | L | none | todo |
| [T4.1](tickets/T4.1.md) | Switch the front end to a PWA | L | none | todo |
| [T4.2](tickets/T4.2.md) | Activity variety suggestions | L | T4.1 | todo |
| [T4.3](tickets/T4.3.md) | Live train data and Web Push notifications | L | T3.4, T4.1 | todo |

## Epic 1: Foundation

The app, CI and the project's working rules.

- [T1.1 Initial scaffold: kids outing agent with HITL and advanced RAG (L)](tickets/T1.1.md)
- [T1.2 CI: GitHub Actions for ruff and pytest (S)](tickets/T1.2.md)
- [T1.3 Budget day trips, age groups and legal compliance rules (L)](tickets/T1.3.md)
- [T1.4 Docs: ticket files, plan index and progress log (M)](tickets/T1.4.md)
- [T1.5 Owner review O1-O3: knowledge base, fares, prompt and evaluation questions (M)](tickets/T1.5.md)
- [T1.6 QRSPI workflow skill and stronger code and legal reviewers (S)](tickets/T1.6.md)
- [T1.7 Enforce the reviewers' never-open and allowlist rules with deny rules and hooks (S)](tickets/T1.7.md)
- [T1.8 Owner task O4: run the evaluations and fill docs/EVALUATION.md (S)](tickets/T1.8.md)
- [T1.9 Third-party terms file and the owner's rules on outside services and keys (S)](tickets/T1.9.md)

## Epic 2: Legal hardening

Bringing the app in line with `docs/LEGAL_COMPLIANCE.md` for the Capstone demo with synthetic data.

- [T2.1 Legal hardening group 1: privacy check, AI disclosure, money from code (L)](tickets/T2.1.md)

## Epic 3: Before a public deployment

Needed before real users, hosting or income (`docs/LEGAL_COMPLIANCE.md`, "Before a public deployment"); none of it blocks the local Capstone demo. These tickets cover only part of that checklist: the rest (hosting DPA with servers in Germany, Overpass instance and caching, the Transitous request counter, coordinates from OpenStreetMap, re-checking fares and the knowledge base) is tracked there until it gets a ticket.

- [T3.1 Before a public deployment: AI provider with a DPA (M)](tickets/T3.1.md)
- [T3.2 Datenschutzerklärung and Impressum (M)](tickets/T3.2.md)
- [T3.3 Invite codes and rate limits (M)](tickets/T3.3.md)
- [T3.4 Replace Transitous, then decide on a private repository (L)](tickets/T3.4.md)

## Epic 4: Beyond the Capstone

The owner's plans for the app after the Capstone (owner's request).

- [T4.1 Switch the front end to a PWA (L)](tickets/T4.1.md)
- [T4.2 Activity variety suggestions (L)](tickets/T4.2.md)
- [T4.3 Live train data and Web Push notifications (L)](tickets/T4.3.md)

## Epic 5: Capstone demo: UI and agent

Interface and agent improvements before the Capstone review (2026-12-16), for the evaluation criteria "user interface and interaction quality" and "accuracy and responsiveness" (`docs/CAPSTONE_CHECKLIST.md`). Order: T5.1 and T5.2 first, so the user tests (O5) and the showcase entry (O6) see the new interface; O4 can run in parallel.

- [T5.1 Live progress while the agent works (M)](tickets/T5.1.md)
- [T5.2 Parent-friendly approval form instead of raw JSON (M)](tickets/T5.2.md)
- [T5.3 Trip plan box from the tool results (M)](tickets/T5.3.md)
- [T5.4 Clear messages when the agent stops (S)](tickets/T5.4.md)
- [T5.5 Source credits for data from earlier turns (S)](tickets/T5.5.md)
- [T5.6 Offline red-team tests: injection checks, answer checks and the approval gate (L)](tickets/T5.6.md)
