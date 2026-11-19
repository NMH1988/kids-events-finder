# Presentation outline (10 minutes + 5 minutes questions)

1. **The problem (1.5 min)**: SCR from the README. Who: parents in DE, GB, US. Why it matters: scattered information, and chatbots that invent places and links.
2. **The solution (3 min)**: live demo. Pick a country and city, ask a rainy-day question in Vietnamese, show the approval panel (edit the city, then approve), the answer cards with Website and Directions, the "How this answer was made" panel and the 👍. Then the architecture diagram from the README: agent, tools, human review, grounding.
3. **The data (1 min)**: curated knowledge base (50 places, own descriptions, official links), live OSM, Ticketmaster and Open-Meteo data, how documents are built with metadata for filtering.
4. **Evaluation (2 min)**: retrieval table (BM25 vs dense vs hybrid vs multi-query vs rerank), agent table (grounded rate, wrong-country rate, judge score, latency, cost), user test results.
5. **Challenges (1.5 min)**: keeping the agent from inventing links (solved in code, not only in the prompt); pausing and resuming a LangGraph run from Streamlit (interrupt + checkpointer + thread id); cross-language retrieval (multi-query rewriting).
6. **What's next (1 min)**: more cities and countries, user location for distances, saving favourite places, opening-hours data, deployment with bring-your-own-key.
