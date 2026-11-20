"""Settings, limits and the supported countries, kept in one place instead of magic numbers."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KNOWLEDGE_BASE_FILE = DATA_DIR / "knowledge_base.json"
FARES_FILE = DATA_DIR / "fares.json"
EVAL_QUESTIONS_FILE = DATA_DIR / "eval_questions.json"
FEEDBACK_FILE = DATA_DIR / "feedback" / "feedback.jsonl"
EVAL_RESULTS_DIR = DATA_DIR / "eval_runs"
CHROMA_DIR = ROOT / "chroma"
CHROMA_COLLECTION = "kid_places"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# --- Models (all calls go through OpenRouter's OpenAI-compatible API) ---
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
API_KEY_NAME = "OPENROUTER_API_KEY"
ALLOWED_MODELS: tuple[str, ...] = ("openai/gpt-5-mini", "openai/gpt-5-nano", "openai/gpt-5")
DEFAULT_AGENT_MODEL = "openai/gpt-5-mini"
# Query rewriting and reranking are simple tasks, so the cheapest model does them.
HELPER_MODEL = "openai/gpt-5-nano"
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
REASONING_EFFORT = "low"
# gpt-5 models spend reasoning tokens from this budget too, so it stays generous.
MAX_TOKENS = 4000
LLM_TIMEOUT_SECONDS = 60
LLM_MAX_RETRIES = 2

# --- Agent ---
# LangGraph counts every node visit; this bounds one turn's agent <-> tool loop.
AGENT_RECURSION_LIMIT = 16
# Tools that send data outside the app need the user's approval (human in the loop).
# `check_budget` stays inside the app but also pauses: the parent fills in the prices
# (entry fees, food) that no open data source provides. The knowledge base search and the
# ticket comparison run without asking.
TOOLS_REQUIRING_APPROVAL: frozenset[str] = frozenset(
    {
        "find_nearby_places",
        "search_family_events",
        "get_weather_forecast",
        "find_train_connection",
        "check_budget",
    }
)
# These pause even with auto-approve on: the parent's own amounts must replace anything the model
# wrote, so a guessed price can never become a real total (LEGAL_COMPLIANCE 7.3).
TOOLS_ALWAYS_REVIEWED: frozenset[str] = frozenset({"check_budget"})
MAX_USER_MESSAGE_CHARS = 1000
# Conversations are deleted from server memory after this much idle time (LEGAL_COMPLIANCE 2.7).
CONVERSATION_RETENTION_SECONDS = 2 * 60 * 60
# A background cleaner enforces both retention limits this often, even when nobody uses the app.
CLEANUP_INTERVAL_SECONDS = 5 * 60
# Feedback records are deleted after this many days; question text is kept only with consent.
FEEDBACK_RETENTION_DAYS = 90

# --- Advanced RAG ---
RETRIEVAL_TOP_K = 5
# Each retriever (dense and BM25) returns this many candidates per query before fusion.
RETRIEVAL_CANDIDATES = 12
# Reciprocal Rank Fusion constant; 60 is the value from the original RRF paper.
RRF_K = 60
MULTI_QUERY_COUNT = 3
RERANK_CANDIDATES = 8

# --- External services (no personal data is sent: only city, country, dates, categories) ---
HTTP_TIMEOUT_SECONDS = 15
HTTP_USER_AGENT = "kids-events-finder/0.1 (student project)"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
TICKETMASTER_KEY_NAME = "TICKETMASTER_API_KEY"
PLACES_RADIUS_METERS = 8000
PLACES_MAX_RESULTS = 8
EVENTS_MAX_RESULTS = 8
WEATHER_MAX_DAYS_AHEAD = 15
EVENTS_MAX_DAYS_AHEAD = 90

# --- Budget day trips by regional train (Germany only) ---
# Transitous: free journey planning (MOTIS) for open-source, non-commercial projects. Its usage
# policy asks for a User-Agent with the app name, version and a contact; the public repository
# is the contact.
TRANSITOUS_PLAN_URL = "https://api.transitous.org/api/v5/plan"
TRANSITOUS_USER_AGENT = "kids-events-finder/0.2 (+https://github.com/NMH1988/kids-events-finder)"
# Modes the Deutschlandticket and Länder-Tickets cover: no ICE, IC, night trains or coaches.
REGIONAL_TRANSIT_MODES = ("REGIONAL_RAIL", "SUBURBAN", "SUBWAY", "TRAM", "BUS", "FERRY")
TRAIN_MAX_RESULTS = 3
TRAIN_MAX_DAYS_AHEAD = 30
LOCAL_TIMEZONE = "Europe/Berlin"
TRIP_TRAVELLERS_RANGE = (1, 5)  # adults per trip; Länder-Tickets cover up to 5 people
BUDGET_RANGE_EUR = (0, 2000)
MAX_BUDGET_ITEMS = 12
# German states by ISO 3166-2 suffix, with the English names the geocoder returns.
GERMAN_STATES: dict[str, str] = {
    "BW": "Baden-Württemberg",
    "BY": "Bavaria",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hesse",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Lower Saxony",
    "NW": "North Rhine-Westphalia",
    "RP": "Rhineland-Palatinate",
    "SL": "Saarland",
    "SN": "Saxony",
    "ST": "Saxony-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thuringia",
}

# --- Countries and cities offered in the dropdowns ---
COUNTRIES: dict[str, str] = {"DE": "Germany", "GB": "United Kingdom", "US": "United States"}
CITIES: dict[str, tuple[str, ...]] = {
    "DE": ("Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"),
    "GB": ("London", "Manchester", "Edinburgh", "Bristol", "Birmingham"),
    "US": ("New York", "San Francisco", "Chicago", "Washington", "Los Angeles"),
}
CATEGORIES: tuple[str, ...] = (
    "museum",
    "science_centre",
    "zoo",
    "aquarium",
    "theme_park",
    "park",
    "playground",
)


def get_secret(name: str) -> str | None:
    """Return a secret from Streamlit secrets or the environment, or None when it is not set."""
    value: str | None = None
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # noqa: BLE001 - no secrets file, or not running inside Streamlit
        value = None
    value = value or os.environ.get(name)
    if not value or value.startswith("your-"):
        return None
    return value


def get_api_key() -> str | None:
    """Return the OpenRouter key, or None when it is not configured."""
    return get_secret(API_KEY_NAME)
