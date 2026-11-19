# Ethical considerations

The users are parents and the subject is children, so mistakes have real-world consequences (a trip to a closed or non-existent place, an unsuitable activity). This document lists the risks and what the app does about each one.

| Risk | Why it matters | Mitigation in the app | Where |
|---|---|---|---|
| Hallucinated places, events or links | A family may travel to something that does not exist | Prompt allows only tool results; the grounding check removes every link no tool returned and shows a warning | `src/prompts/agent_system.md`, `src/grounding.py`, `src/agent/graph.py` (`grounding` node) |
| Outdated information (hours, prices, closures) | Places change; the knowledge base is a snapshot | No hours or prices in the curated data; the UI and every answer tell parents to check the official website; `scripts/check_links.py` finds dead links | `data/knowledge_base.json`, `views/about.py` |
| Agent acting without oversight | Outside calls send data to third parties and cost quota | Human-in-the-loop: outside tools pause for approve / edit / reject; auto-approve is off by default and must be switched on by the parent | `src/agent/graph.py` (`human_review`), `views/chat.py` |
| Children's personal data | Children's data needs special care (GDPR Art. 8, COPPA in the US) | Only an age (0-17) is used; the UI asks not to type names or details; outside services receive only city, country, dates and category; the prompt tells the model not to ask for personal details | `views/sidebar.py`, `src/tools/external.py`, system prompt |
| Data sent to the LLM provider | Questions go to OpenRouter and the model provider | Disclosed on the About tab; no account, no tracking; chat lives only in the session's memory | `views/about.py`, `src/agent/runner.py` |
| Stored feedback | Ratings store the question and answer | Stored locally in a gitignored file, never sent anywhere; disclosed on the About tab | `src/feedback.py`, `.gitignore` |
| Prompt injection (via the question or tool results) | Text from users or APIs could try to change the agent's rules | Retrieved text and questions are delimited and labelled as data; tool arguments are validated with Pydantic (country list, age range, category list, date range); the grounding check works in code, so injected links cannot reach the answer | `src/tools/registry.py`, `src/rag/retriever.py` prompts |
| Commercial bias | Event APIs favour paid, ticketed events | Curated knowledge base includes free museums, parks and playgrounds; `price` is shown on every card | `data/knowledge_base.json` |
| Geographic bias | Big cities are better covered | Known limit; only 15 cities are curated, other cities rely on OpenStreetMap | README "Limits" |
| Safety and supervision | The app cannot judge if a place is safe for a specific child | The About tab says parents remain responsible; age ranges are labelled as suggestions | `views/about.py` |
| Copyright and licences | Third-party content must be reusable | Descriptions are the project's own words; OSM (ODbL) and Ticketmaster data are queried live, shown with attribution and not stored; Open-Meteo is CC BY 4.0 with attribution | README "Data sources" |
| Wrong money figures (budget trips) | A model that adds up prices can be wrong, and an invented entry fee misleads a family on a budget | Ticket prices come from a hand-checked fare table with a source link and date; the totals are calculated in code (`check_budget`), not by the model; unknown costs stay empty until the parent fills them in at the approval step; every plan tells parents to check bahn.de | `data/fares.json`, `src/fares.py`, `src/budget.py`, `views/chat.py` |
| Family details sent to the journey planner | Budget, ages and family size are personal | Transitous receives only the two town names and the date; the budget and the party stay in the app | `src/tools/external.py` |
| Transitous terms | Free only for open-source, non-commercial use, with a contact in the User-Agent | The repository is public under the MIT licence; the User-Agent names the repository; any paid version needs another journey planner | `src/config.py`, `LICENSE` |
| Cost and abuse | A public app could spend the owner's key | Runs locally; message length limit; LangGraph recursion limit bounds the agent's loop; the model allowlist and max tokens are fixed when the client is built | `src/config.py`, `src/llm.py` |

## Before any public deployment
- Add a "bring your own key" option or authentication, so visitors cannot spend the owner's key.
- Review Ticketmaster's terms of use for public display of event data.
- Re-run `scripts/check_links.py` and re-verify the curated entries.
- Re-check every price in `data/fares.json` against bahn.de and update `checked_on`.
- Open-Meteo's free API and Transitous are for non-commercial use only; a version that earns money needs paid or other data sources.
