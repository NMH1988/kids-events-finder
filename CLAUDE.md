# CLAUDE.md

Kids Outing Finder: Turing College AI Engineering capstone (deadline 2026-12-16). A Streamlit app with a LangGraph agent (human-in-the-loop approval of outside tool calls), advanced RAG over a curated knowledge base (Chroma + BM25, multi-query, RRF, rerank) and a grounding check on links. Requirements map: `docs/CAPSTONE_CHECKLIST.md`.

The owner writes in Vietnamese: reply in Vietnamese. Everything in the repo is in English.

## Conventions
- Every function, method and class gets a one-line docstring.
- Business logic in `src/`; UI in `views/`; `app.py` only composes the page.
- Settings and limits live in `src/config.py`. Build model clients only with `src/llm.py`; never pass `model`, `max_tokens` or `base_url` at call time.
- The OpenRouter and Ticketmaster keys are read only through `config.get_secret()`; never log, print or show them.
- Chroma runs embedded only, with embeddings from OpenRouter (never Chroma's built-in embedding functions).
- Outside services receive only city, country, dates and category; never the question or the child's age.
- The system prompt and the evaluation questions are drafts for the owner to review.
- Tests mock every LLM and network call (`tests/conftest.py` blocks `requests`).

## Commands (from this folder, Python 3.14 venv)
- Install: `.venv/Scripts/python.exe -m pip install -e ".[dev]"`
- Run: `.venv/Scripts/streamlit.exe run app.py`
- Build index (needs key): `.venv/Scripts/python.exe -m scripts.build_index`
- Test / lint: `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/ruff.exe check .`
- CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check` and pytest on every push to `main` and every PR.
- Evaluation (needs key + index): `python -m scripts.evaluate_retrieval`, `python -m scripts.evaluate_agent --judge`; link check: `python -m scripts.check_links`
