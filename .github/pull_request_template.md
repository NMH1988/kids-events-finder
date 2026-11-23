Closes #<!-- issue number -->

## Ticket
- **T<!-- x.y -->** <!-- title --> (`docs/tickets/T<x.y>.md`)
- Serves: <!-- Capstone requirement (docs/CAPSTONE_CHECKLIST.md) and legal sections, or "beyond the brief (owner's request)" -->

## Summary
<!-- What changes and why. -->

## Acceptance criteria
<!-- Each criterion from the ticket, with the test or check that proves it. -->
- [ ] <!-- criterion --> - <!-- test or check -->

## Tests
<!-- What was run (pytest, ruff, browser check) and what was not checked. -->

## Docs
- [ ] Progress entry added: `docs/progress/<date>-T<x.y>.md` and its line at the top of `docs/PROGRESS.md`.
- [ ] Ticket status updated in `docs/tickets/T<x.y>.md` and in the order table of `docs/IMPLEMENTATION_PLAN.md`; the last commit before merge sets it to `done`, ticks the met criteria and puts this PR's number in the progress heading and index line.

## Reviews
- `code-reviewer`: <!-- last round number and verdict, link to its PR comment -->
- `security-reviewer`: <!-- verdict and link, or "not needed: <reason>" -->

## Legal check (required, see docs/LEGAL_COMPLIANCE.md)
- [ ] I read `docs/LEGAL_COMPLIANCE.md` before starting.
- `legal-reviewer` verdict: <!-- PASS / NEEDS CHANGES / BLOCK, with the date of the run -->
- Findings fixed or decided by the owner: <!-- list, or "none" -->
- Sections this change touches: <!-- e.g. 1 Children's data, 2.3 Privacy policy, 6.3 Licences, or "none" -->
- [ ] No child names, no health data, no development assessment (1.2, 1.4, 1.5).
- [ ] No new data sent to outside services beyond what the registers list, or the registers are updated (2, registers).
- [ ] No trackers, analytics or advertising scripts (3.1).
- [ ] AI disclosure and grounding still work (4.1, 4.3).
- [ ] No commercial links, or they are labelled and do not affect ranking (5).
- [ ] New data sources or dependencies have a checked licence that allows our use (6.3, 6.4).
- Open legal questions for the owner: <!-- "none", or list them -->
