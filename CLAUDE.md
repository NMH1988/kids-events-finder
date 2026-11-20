# CLAUDE.md

Kids Outing Finder: Turing College AI Engineering capstone (deadline 2026-12-16). A Streamlit app with a LangGraph agent (human-in-the-loop approval of outside tool calls), budget day trips by regional train in Germany (Transitous journeys, ticket comparison, budget check), advanced RAG over a curated knowledge base (Chroma + BM25, multi-query, RRF, rerank) and a grounding check on links. Requirements map: `docs/CAPSTONE_CHECKLIST.md`.

The owner writes in Vietnamese: reply in Vietnamese. Everything in the repo is in English.

## Legal compliance comes first (mandatory)
- **Before starting any ticket, read `docs/LEGAL_COMPLIANCE.md` in full** and check the planned change against every section it touches (children's data, no health data, GDPR, no trackers, AI Act, advertising/ranking, licences).
- If a change would break a rule, or it is unclear, **stop and ask the owner before writing code**. Never implement first and check later.
- **After finishing a ticket, before opening the PR, run the `legal-reviewer` subagent** (`.claude/agents/legal-reviewer.md`) on the branch's changes. Fix every BLOCK and CHANGE finding (or get the owner's decision on it), re-run until the verdict is PASS, and paste the verdict and any open questions into the PR's Legal check. Run it again on a PR after later commits change what data leaves the app.
- Every PR fills in the **Legal check** section of `.github/pull_request_template.md`. A PR without it is not merged.
- A new data source, service, data flow or legally relevant feature updates `docs/LEGAL_COMPLIANCE.md` (rules and registers) in the same PR.
- These rules are not legal advice; tell the owner when something needs a lawyer or Datenschutzberater.
- **Synthetic data only for now:** the project uses the school's OpenRouter account (no DPA, no zero data retention). Whenever deployment, hosting, real users or income come up, remind the owner of the "Before a public deployment" checklist in `docs/LEGAL_COMPLIANCE.md` first.

## Reviews after every ticket (mandatory)
Run these subagents (`.claude/agents/`) on the branch before opening or merging its PR:
1. **`code-reviewer`** - bugs, security basics, conventions, Capstone fit, acceptance criteria. Every round's report goes on the PR as a comment (the agent posts it when it reviews the PR's head; otherwise post it yourself right after opening the PR, in round order). Fix Must fix findings and run it again.
2. **`legal-reviewer`** - see above; its verdict goes into the PR's Legal check.
3. **`security-reviewer`** - also when the change touches prompts, tools, the graph, retrieval, output rendering, scripts or secrets. Ask it to post on the PR.
After each review check with `gh pr view <n> --json comments` that the report is on the PR, and give the owner the link. Reports are public: repo-relative paths only, no keys, no personal data, no payload of an open High or Critical finding.

## Conventions
- Every function, method and class gets a one-line docstring.
- Business logic in `src/`; UI in `views/`; `app.py` only composes the page.
- Settings and limits live in `src/config.py`. Build model clients only with `src/llm.py`; never pass `model`, `max_tokens` or `base_url` at call time.
- The OpenRouter and Ticketmaster keys are read only through `config.get_secret()`; never log, print or show them.
- Chroma runs embedded only, with embeddings from OpenRouter (never Chroma's built-in embedding functions).
- Map, event, weather and transit services receive only town or city names (or their coordinates), country, dates, times and category; never the question, the children's age groups, the budget or the family size. The AI model via OpenRouter receives the question, the age groups and the trip settings, as disclosed on the About page.
- Children are only "Child 1", "Child 2" with an age group (`src/family.py`); never names or exact ages.
- Money is calculated in code, never by the model: ticket rules in `data/fares.json` + `src/fares.py`, totals in `src/budget.py`. Every fare entry keeps its bahn.de `source_url` and `checked_on` date. Unknown prices stay `null` for the parent to fill in.
- Transitous (train journeys) is free only for open-source, non-commercial use; keep `TRANSITOUS_USER_AGENT` with the repository as the contact.
- The system prompt and the evaluation questions are drafts for the owner to review.
- Tests mock every LLM and network call (`tests/conftest.py` blocks `requests`).

## Commands (from this folder, Python 3.14 venv)
- Install: `.venv/Scripts/python.exe -m pip install -e ".[dev]"`
- Run: `.venv/Scripts/streamlit.exe run app.py`
- Build index (needs key): `.venv/Scripts/python.exe -m scripts.build_index`
- Test / lint: `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/ruff.exe check .`
- CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check` and pytest on every push to `main` and every PR.
- Evaluation (needs key + index): `python -m scripts.evaluate_retrieval`, `python -m scripts.evaluate_agent --judge`; link check: `python -m scripts.check_links`
