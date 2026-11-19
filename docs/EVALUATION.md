# Evaluation

Three levels, from cheapest to most realistic. Record each run's numbers in the tables below (date, model) so the presentation can show progress.

## 1. Offline tests (no key)

`python -m pytest -q` runs 105 tests with fake models and mocked HTTP. They cover the knowledge base schema, metadata filters, BM25, hybrid search, RRF, multi-query and reranking, the seven tools (validation, parsing, error handling), the ticket comparison rules (children's free rides, Deutschlandticket holders, the 9:00 weekday start, cross-state trips) and the budget check, the human-in-the-loop flows (approve, edit, reject, auto-approve), the grounding check, the index, feedback storage and an AppTest smoke test of the page.

## 2. Retrieval comparison (key + index)

`python -m scripts.evaluate_retrieval` runs the 25 questions in `data/eval_questions.json` (DE, GB, US; English, German and Vietnamese) through five variants and reports:
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

## 4. Human feedback and user testing

- In-app 👍/👎 ratings are stored in `data/feedback/feedback.jsonl` (local, gitignored) with the tools used and the grounding result. Report the share of 👍 answers.
- User test plan: ask 3-5 parents to complete 3 tasks (rainy-day idea, free activity, event this weekend). Measure task success, number of HITL rejections or edits and their reasons, and collect comments.

| Tester | Tasks done | 👍 / 👎 | HITL edits / rejects | Main comment |
|---|---|---|---|---|
| P1 | | | | |
