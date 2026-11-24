# Capstone requirements checklist

Deadline: **2026-12-16**. Case 2 (AI agent for task automation) with an advanced RAG part (Case 1).

## Required by the brief

| Requirement | Where | Status |
|---|---|---|
| README with goal, problem and how it works | `README.md` (first section) | Done |
| Showcase link near the top of the README (optional, a small part of the score); the entry must reflect the current state of the project | `README.md` line 3 | **Owner: upload after Epic 5, before booking the review, and add the link; update the entry after any later change** |
| Effective use of LangChain / LLM APIs | LangGraph agent, LangChain tools, OpenRouter | Done |
| Vector database (ChromaDB) | `src/rag/index.py` | Done |
| RAG (here advanced: multi-query, hybrid, RRF, filters, rerank) | `src/rag/retriever.py` | Done |
| Function calling / tool integration with external APIs | `src/tools/` (7 tools, 4 external APIs: OSM, Ticketmaster, Open-Meteo, Transitous) | Done |
| Multi-step reasoning, memory | LangGraph loop with checkpointer (conversation memory per thread) | Done |
| Interactive prototype ("Streamlit or another interface" for Case 2) | `app.py`, `views/` (Streamlit) | Done |
| User interface and interaction quality (evaluation criterion "Outcome quality") | `views/`; Epic 5 in `docs/IMPLEMENTATION_PLAN.md` (T5.1-T5.5) | Works; improvements planned in Epic 5 |
| Prompt engineering best practices | `src/prompts/agent_system.md` (role, process, rules, format, injection rule) | Done (reviewed for O2, T1.5) |
| Evaluation: accuracy and responsiveness, user testing | `scripts/evaluate_*.py`, `docs/EVALUATION.md`; offline red-team tests (T5.6) | Scripts done; **owner runs and fills the tables** |
| Ethical considerations documented | `docs/ETHICS.md` | Done |
| Presentation using SCR or SMART; 10 minutes + 5 for questions, six points: problem, solution, data, evaluation, challenges, what's next (the talk itself is optional but recommended) | README SCR section, `docs/PRESENTATION.md` | Outline done (six points) |

## Owner's to-do before the review
1. Done 2026-11-23 (O1): add `OPENROUTER_API_KEY` (and optionally `TICKETMASTER_API_KEY`) to `.streamlit/secrets.toml`, then run `python -m scripts.build_index`.
2. Done 2026-11-23 (O2, T1.5): review and edit the drafts: the system prompt and `data/eval_questions.json`.
3. Done 2026-11-23 (O3, T1.5): check the curated entries in `data/knowledge_base.json`; run `python -m scripts.check_links`. Re-check the ticket prices in `data/fares.json` on bahn.de.
4. Run both evaluation scripts and fill the tables in `docs/EVALUATION.md`.
5. Do 3-5 user tests with made-up questions and adult testers who agreed beforehand, and write down the results (no screen or voice recordings, no testers' names with their feedback; `docs/LEGAL_COMPLIANCE.md` 8).
6. After Epic 5 and before booking the review, upload the project to showcase.turingcollege.com and add the link near the top of the README (the GitHub repository exists); update the entry after any later change. Use screenshots or a recorded demo with made-up questions: a publicly reachable copy of the app would be a public deployment (`docs/LEGAL_COMPLIANCE.md` 8).
7. Record a short demo and prepare the 10-minute talk (`docs/PRESENTATION.md`).

## SMART goal for the project
Specific: a Streamlit agent that suggests grounded outings for children in DE, GB and US. Measurable: 100% grounded answers, hit@5 ≥ 0.8 for the best retrieval variant, average answer under 30 seconds. Achievable: built on tools from the course. Relevant: real parent need, showcases agents, HITL and advanced RAG. Time-bound: submitted by 2026-12-16.
