"""The About tab: how the app works, its limits, privacy and data sources."""

import streamlit as st

from src import config
from src.tools.external import (
    ATTRIBUTION_OSM,
    ATTRIBUTION_TICKETMASTER,
    ATTRIBUTION_TRANSITOUS,
    ATTRIBUTION_WEATHER,
)


def render_about() -> None:
    """Explain the pipeline, the human-in-the-loop step, privacy and attributions."""
    st.markdown(
        f"""
### How it works
1. **Agent (LangGraph):** the model decides which tools to call for your question.
2. **Advanced RAG:** the curated knowledge base is searched with multi-query rewriting,
   hybrid search (vector + BM25), metadata filters (country, city, age, indoor),
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
- No account, no tracking. The chat lives only in this browser session.
- Only the city or town, country, dates and place category are sent to outside services
  (never the budget, ages or family size, which stay in the app); your
  question goes to the AI model through OpenRouter. Don't type names or other personal details.
- Feedback (rating, question, answer) is saved locally on the machine running the app.

### Data sources
- Curated knowledge base: the project's own short descriptions, with links to official websites.
- {ATTRIBUTION_OSM}
- {ATTRIBUTION_TICKETMASTER}
- {ATTRIBUTION_WEATHER}
- {ATTRIBUTION_TRANSITOUS}
- Ticket prices: copied by hand from bahn.de with the date they were checked. Always check
  the current price and area before you buy.
- Directions open in Google Maps.
"""
    )
