# Capstone requirements checklist

Deadline: **2026-12-16**. Case 2 (AI agent for task automation) with an advanced RAG part (Case 1).

## Required by the brief

| Requirement | Where | Status |
|---|---|---|
| README with goal, problem and how it works | `README.md` (first section) | Done |
| Showcase link near the top of the README | `README.md` line 3 | **Owner: upload and add the link** |
| Effective use of LangChain / LLM APIs | LangGraph agent, LangChain tools, OpenRouter | Done |
| Vector database (ChromaDB) | `src/rag/index.py` | Done |
| RAG (here advanced: multi-query, hybrid, RRF, filters, rerank) | `src/rag/retriever.py` | Done |
| Function calling / tool integration with external APIs | `src/tools/` (4 tools, 3 external APIs) | Done |
| Multi-step reasoning, memory | LangGraph loop with checkpointer (conversation memory per thread) | Done |
| Interactive prototype in Streamlit | `app.py`, `views/` | Done |
| Prompt engineering best practices | `src/prompts/agent_system.md` (role, process, rules, format, injection rule) | Draft: **owner reviews** |
| Evaluation: accuracy and responsiveness, user testing | `scripts/evaluate_*.py`, `docs/EVALUATION.md` | Scripts done; **owner runs and fills the tables** |
| Ethical considerations documented | `docs/ETHICS.md` | Done |
| Presentation using SCR or SMART | README SCR section, `docs/PRESENTATION.md` | Outline done |

## Owner's to-do before the review
1. Add `OPENROUTER_API_KEY` (and optionally `TICKETMASTER_API_KEY`) to `.streamlit/secrets.toml`, then run `python -m scripts.build_index`.
2. Review and edit the drafts: the system prompt and `data/eval_questions.json`.
3. Check the curated entries in `data/knowledge_base.json`; run `python -m scripts.check_links`.
4. Run both evaluation scripts and fill the tables in `docs/EVALUATION.md`.
5. Do 3-5 user tests and record them.
6. Put the project in a GitHub repository, upload it to showcase.turingcollege.com and add the link to the README.
7. Record a short demo and prepare the 10-minute talk (`docs/PRESENTATION.md`).

## SMART goal for the project
Specific: a Streamlit agent that suggests grounded outings for children in DE, GB and US. Measurable: 100% grounded answers, hit@5 ≥ 0.8 for the best retrieval variant, average answer under 30 seconds. Achievable: built on tools from the course. Relevant: real parent need, showcases agents, HITL and advanced RAG. Time-bound: submitted by 2026-12-16.
