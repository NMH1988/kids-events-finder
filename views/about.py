"""The About tab: how the app works, its limits, privacy and data sources."""

import streamlit as st

from src import config
from src.tools.external import (
    ATTRIBUTION_OSM,
    ATTRIBUTION_TICKETMASTER,
    ATTRIBUTION_WEATHER,
)


def render_about() -> None:
    """Explain the pipeline, the human-in-the-loop step, privacy and attributions."""
    st.markdown(
        f"""
### How it works
1. **Agent (LangGraph):** the model decides which tools to call for your question.
2. **Advanced RAG:** the curated knowledge base is searched with multi-query rewriting,
   hybrid search (vector + BM25), metadata filters (country, city, age groups, indoor),
   Reciprocal Rank Fusion and optional LLM reranking.
3. **Live tools:** OpenStreetMap for nearby places, Ticketmaster for family events,
   Open-Meteo for the weather.
4. **Human in the loop:** before any call to an outside service, you see what will be sent
   and can approve, edit or reject it.
5. **Grounding check:** every link in an answer must come from a tool result; any other link
   is removed before you see it.
6. **Feedback:** your 👍/👎 is stored locally to evaluate and improve the answers.
7. **Budget day trips (Germany):** regional train journeys from Transitous, a ticket
   comparison (Deutschlandticket, Länder-Tickets, Quer-durchs-Land-Ticket) calculated by
   the app from its fare table, the weather, and a budget check where you fill in the
   prices the app cannot know. The app does the arithmetic, never the AI model.

### Limits
- Suggestions can be wrong or out of date. Check opening times, prices, age limits and
  accessibility on the official website before you go.
- Only {", ".join(config.COUNTRIES.values())} are supported.
- The app does not judge safety; parents stay responsible for supervising their children.

### Privacy
- No account, no tracking, no cookies for advertising or analytics.
- Children are described only as "Child 1", "Child 2" with an age group; the app never asks for
  names, exact ages or health information. Please don't type them in the chat.
- **AI model (OpenRouter, model providers possibly in the US):** receives your question, the
  country and city, the children's age groups and, when trip planning is on, the budget, the
  number of adults, Deutschlandticket holders and the budget items, so it can plan the trip.
- **Map, event, weather and train services** receive only town or city names (or their
  coordinates), the country, dates, times and place categories; never the age groups, budget or
  family size.
- Conversations are deleted from the server when you start a new one. After 2 hours without use
  the agent's copy is deleted automatically (checked every 5 minutes); the copy shown on your open
  page is removed within a few minutes, or when you close it.
- Feedback: only the 👍/👎 and technical facts are saved on this app's server, and deleted after
  90 days. Your question and the answer are saved only if you tick the box to share them; you can
  delete them again while the page is open. After you close the page they can no longer be matched
  to you and are deleted after 90 days.

### Data sources
- Curated knowledge base: the project's own short descriptions, with links to official websites.
- {ATTRIBUTION_OSM}
- {ATTRIBUTION_TICKETMASTER}
- {ATTRIBUTION_WEATHER}
- Journeys by [Transitous](https://transitous.org/sources/) (see its data sources); German
  timetables by DELFI e.V. and others; street data © OpenStreetMap contributors.
- Ticket prices: copied by hand from bahn.de with the date they were checked. Always check
  the current price and area before you buy.
- Directions open in Google Maps.
"""
    )
