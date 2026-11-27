# Capstone requirements checklist

Deadline: **2026-12-16**. Case 2 (AI agent for task automation) with an advanced RAG part (Case 1).

## Required by the brief

| Requirement | Where | Status |
|---|---|---|
| README with goal, problem and how it works | `README.md` (first section) | Done |
| Showcase link near the top of the README (optional, a small part of the score); the entry must reflect the current state of the project | `README.md` line 3 | **Owner: upload after Epic 5, before booking the review, and add the link; update the entry after any later change** |
| Effective use of LangChain / LLM APIs | LangGraph agent, LangChain tools, OpenRouter | Done |
| OpenAI API | OpenAI models (`openai/gpt-5-mini`, `-nano`, `gpt-5`) through OpenRouter's OpenAI-compatible Chat Completions API, called with the official `openai` SDK through `langchain_openai` (`src/llm.py`); calling OpenAI directly means changing the provider lines in `src/config.py` (`AI_BASE_URL`, `API_KEY_NAME`, `AI_PROVIDER_NAME`) and the model IDs, which carry OpenRouter's `openai/` prefix | Done |
| Vector database (ChromaDB) | `src/rag/index.py` | Done |
| RAG (here advanced: multi-query, hybrid, RRF, filters, rerank) | `src/rag/retriever.py` | Done |
| Function calling / tool integration with external APIs | `src/tools/` (8 tools, 4 external APIs: OSM, Ticketmaster, Open-Meteo, Transitous; the internal `remember_preference` writes the long-term memory, T5.11) | Done |
| Multi-step reasoning | LangGraph agent loop: model, tools, human-in-the-loop approval, grounding check (`src/agent/graph.py`) | Done |
| Short-term memory | LangGraph checkpointer: the conversation per thread (`views/chat.py`); the history sent to the model is trimmed to a token budget (`history_for_model` in `src/agent/graph.py`, T5.11) | Done |
| Long-term memory | LangGraph Store passed to the graph: the family's activity preferences across conversations, opt-in, saved on this computer, written by the `remember_preference` tool only after the parent approves each save (human in the loop) and read into the system prompt (`src/memory.py`, T5.11) | Done (T5.11) |
| Interactive prototype ("Streamlit or another interface" for Case 2) | `app.py`, `views/` (Streamlit) | Done |
| User interface and interaction quality (evaluation criterion "Outcome quality") | `views/`; Epic 5 in `docs/IMPLEMENTATION_PLAN.md` (T5.1-T5.5, T5.7, T5.13-T5.16); design in `docs/design/ui-design-spec.md` (T5.12) | Works; improvements planned in Epic 5 |
| Prompt engineering best practices | `src/prompts/agent_system.md` (role, process, rules, format, injection rule) | Done (reviewed for O2, T1.5) |
| Evaluation: accuracy and responsiveness, user testing | `scripts/evaluate_*.py`, `docs/EVALUATION.md`; offline red-team tests (T5.6) | Retrieval, agent and red-team runs done 2026-11-24 (O4, T1.8); red-team cases offline only from now on (owner decision 2026-11-24, T5.6 to do); **user tests (O5) to do** |
| Ethical considerations documented | `docs/ETHICS.md` | Done |
| Presentation using SCR or SMART; 10 minutes + 5 for questions, six points: problem, solution, data, evaluation, challenges, what's next (the talk itself is optional but recommended) | README SCR section, `docs/PRESENTATION.md` | Outline done (six points) |

## Owner's to-do before the review
1. Done 2026-11-23 (O1): add `OPENROUTER_API_KEY` (and optionally `TICKETMASTER_API_KEY`) to `.streamlit/secrets.toml`, then run `python -m scripts.build_index`.
2. Done 2026-11-23 (O2, T1.5): review and edit the drafts: the system prompt and `data/eval_questions.json`.
3. Done 2026-11-23 (O3, T1.5): check the curated entries in `data/knowledge_base.json`; run `python -m scripts.check_links`. Re-check the ticket prices in `data/fares.json` on bahn.de.
4. Done 2026-11-24 (O4, T1.8): run both evaluation scripts and fill the tables in `docs/EVALUATION.md`.
5. Do 3-5 user tests with made-up questions and adult testers who agreed beforehand, and write down the results (no screen or voice recordings, no testers' names with their feedback; `docs/LEGAL_COMPLIANCE.md` 8).
6. After Epic 5 and before booking the review, upload the project to showcase.turingcollege.com and add the link near the top of the README (the GitHub repository exists); update the entry after any later change. Use screenshots or a recorded demo with made-up questions: a publicly reachable copy of the app would be a public deployment (`docs/LEGAL_COMPLIANCE.md` 8).
7. Record a short demo and prepare the 10-minute talk (`docs/PRESENTATION.md`).

## SMART goal for the project
Specific: a Streamlit agent that suggests grounded outings for children in DE, GB and US. Measurable: 100% grounded answers, hit@5 ≥ 0.8 for the best retrieval variant, average answer under 30 seconds. Achievable: built on tools from the course. Relevant: real parent need, showcases agents, HITL and advanced RAG. Time-bound: submitted by 2026-12-16.
