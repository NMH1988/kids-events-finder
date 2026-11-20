# Evaluation

Three levels, from cheapest to most realistic. Record each run's numbers in the tables below (date, model) so the presentation can show progress.

## 1. Offline tests (no key)

`python -m pytest -q` runs 1249 tests with fake models and mocked HTTP. They cover the privacy check (health words, names, exact ages, contact details, place-name fields; every red-team case marked "blocked" is blocked and no normal question is), the knowledge base schema, metadata filters, BM25, hybrid search, RRF, multi-query and reranking, the seven tools (validation, parsing, error handling), the ticket comparison rules (children's free rides, Deutschlandticket holders, the 9:00 weekday start, cross-state trips) and the budget check, the human-in-the-loop flows (approve, edit, reject, auto-approve), the grounding check, the index, feedback storage and an AppTest smoke test of the page.

## 2. Retrieval comparison (key + index)

`python -m scripts.evaluate_retrieval` runs the 25 questions in `data/eval_questions.json` (DE, GB, US; English, German and Vietnamese; synthetic, with children as age groups like in the app) through five variants and reports:
- **hit rate@5**: share of questions where an expected place is in the top 5,
- **MRR**: mean reciprocal rank of the first expected place.

| Date | Variant | hit@5 | MRR | Seconds |
|---|---|---|---|---|
| _yyyy-mm-dd_ | bm25 | | | |
| | dense | | | |
| | hybrid | | | |
| | hybrid_mq | | | |
| | hybrid_mq_rr | | | |

Expected pattern to check: BM25 fails on the Vietnamese and German questions, multi-query fixes them; hybrid beats each single retriever.

## 3. End-to-end agent (key + index)

`python -m scripts.evaluate_agent --judge` runs every question through the agent with tools auto-approved and reports:
- **grounded rate**: answers where no link had to be removed (target: 100%),
- **relevant named rate**: answers that mention an expected place,
- **wrong country rate**: answers that mention a curated place from another country (target: 0%),
- **average latency and tokens** per answer,
- **LLM judge** (gpt-5-nano, 1-5): how well the answer fits the question, city and age.

| Date | Model | Grounded | Relevant named | Wrong country | Avg s | Avg tokens | Judge |
|---|---|---|---|---|---|---|---|
| _yyyy-mm-dd_ | openai/gpt-5-mini | | | | | | |
| | openai/gpt-5-nano | | | | | | |

### Red team
`python -m scripts.evaluate_agent --red-team` runs the 13 safety cases in `data/eval_questions.json` (`red_team`): health, names, exact ages, e-mails, statements about a child's development and accessibility needs must be blocked before any model call; a prompt injection asking for a tracking link, a request for fake urgency, a request for a development claim ("make my child smarter") and an off-topic request must be declined without forbidden words or unverified links. Target: 13/13.

| Date | Model | Passed | Failures |
|---|---|---|---|
| _yyyy-mm-dd_ | openai/gpt-5-mini | /13 | |

## 4. Human feedback and user testing

- In-app 👍/👎 ratings are stored in `data/feedback/feedback.jsonl` (local, gitignored) with the tools used and the grounding result. Report the share of 👍 answers.
- Testers follow `docs/LEGAL_COMPLIANCE.md` section 8: adults who agreed beforehand, made-up questions only, no recordings, no names stored with feedback.
- User test plan: ask 3-5 parents to complete 3 tasks (rainy-day idea, free activity, event this weekend). Measure task success, number of HITL rejections or edits and their reasons, and collect comments.

| Tester | Tasks done | 👍 / 👎 | HITL edits / rejects | Main comment |
|---|---|---|---|---|
| P1 | | | | |
