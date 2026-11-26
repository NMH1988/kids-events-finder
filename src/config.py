"""Settings, limits and the supported countries, kept in one place instead of magic numbers."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KNOWLEDGE_BASE_FILE = DATA_DIR / "knowledge_base.json"
FARES_FILE = DATA_DIR / "fares.json"
EVAL_QUESTIONS_FILE = DATA_DIR / "eval_questions.json"
FEEDBACK_FILE = DATA_DIR / "feedback" / "feedback.jsonl"
# Long-term memory (T5.11): the family's preferences, kept only on this computer (gitignored).
MEMORY_FILE = DATA_DIR / "memory" / "preferences.json"
EVAL_RESULTS_DIR = DATA_DIR / "eval_runs"
CHROMA_DIR = ROOT / "chroma"
CHROMA_COLLECTION = "kid_places"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# --- AI provider and models ---
# Any OpenAI-compatible provider works: switching (e.g. to an account with a DPA and zero data
# retention, LEGAL_COMPLIANCE "Before a public deployment") changes only these lines, the model
# names below and the About page text that names the provider. Today: the school's OpenRouter
# account, so synthetic data only (LEGAL_COMPLIANCE 8).
AI_PROVIDER_NAME = "OpenRouter"
AI_BASE_URL = "https://openrouter.ai/api/v1"
API_KEY_NAME = "OPENROUTER_API_KEY"
EMBEDDING_BASE_URL = AI_BASE_URL
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
# Environment switches that would send runs to LangSmith; `src/llm.py` sets them to "false".
TRACING_ENV_OFF: tuple[str, ...] = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_TRACING",
)
# Highest log detail allowed; logs never hold message content, ages, budgets or keys (2.7, 2.10).
# The libraries below log request bodies, and urllib3 logs each request's URL, which holds the
# Ticketmaster key, at DEBUG; `src/llm.py` caps them at LOG_LEVEL when it is imported.
LOG_LEVEL = "INFO"
QUIET_LOGGERS: tuple[str, ...] = (
    "openai",
    "httpx",
    "httpcore",
    "urllib3",
    "langchain",
    "langgraph",
)

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
# wrote, so a guessed price can never become a real total (LEGAL_COMPLIANCE 7.3); and the parent
# confirms every long-term memory save, so no tool text can plant a preference (owner decision
# 2026-11-25, T5.11, LEGAL_COMPLIANCE 2.11).
TOOLS_ALWAYS_REVIEWED: frozenset[str] = frozenset({"check_budget", "remember_preference"})
# Tools whose results are the app's own money calculations; the UI shows them from the tool
# results under the answer (never from the model's text).
CALCULATION_TOOLS: frozenset[str] = frozenset({"compare_train_tickets", "check_budget"})
# Progress steps shown while the agent works (T5.1). Fixed app text only: never the model's text,
# tool arguments or tool results, so nothing reaches the page before the grounding check.
PROGRESS_START = "Thinking about your question"
PROGRESS_NEXT_STEP = "Thinking about the next step"
PROGRESS_GROUNDING = "Checking the links in the answer"
PROGRESS_APPROVAL = "Waiting for your approval"
PROGRESS_UNKNOWN_TOOL = "Using a tool"
PROGRESS_TOOL_LABELS: dict[str, str] = {
    "search_knowledge_base": "Searching the curated places",
    "find_nearby_places": "Looking for places on OpenStreetMap",
    "search_family_events": "Looking for family events",
    "get_weather_forecast": "Checking the weather",
    "find_train_connection": "Looking for train connections",
    "compare_train_tickets": "Comparing train tickets",
    "check_budget": "Adding up the budget",
    "remember_preference": "Remembering your preference",
}
MAX_USER_MESSAGE_CHARS = 1000
# Limit for the parent's reason and edits in the approval panel (keeps every check fast).
MAX_DECISION_CHARS = 5000
# Longest reject reason; enforced on the server too, not only by the text box.
MAX_REJECT_REASON_CHARS = 300
# Longest single value in edited arguments (the longest tool field, the knowledge base query, is
# 300 characters).
MAX_EDIT_VALUE_CHARS = 400
# Deepest nesting of lists and dicts in edited arguments (tool arguments need at most 3).
MAX_EDIT_DEPTH = 6
# Conversations are deleted from server memory after this much idle time (LEGAL_COMPLIANCE 2.7).
CONVERSATION_RETENTION_SECONDS = 2 * 60 * 60
# A background cleaner enforces both retention limits this often, even when nobody uses the app.
CLEANUP_INTERVAL_SECONDS = 5 * 60
# Feedback records are deleted after this many days; question text is kept only with consent.
FEEDBACK_RETENTION_DAYS = 90
# A remembered preference is deleted this many days after it was last saved (T5.11).
LONG_TERM_MEMORY_RETENTION_DAYS = 30
# One local profile: without a login the memory belongs to this computer, not to a person, so it
# is for the local demo only (LEGAL_COMPLIANCE "Before a public deployment").
MEMORY_NAMESPACE: tuple[str, ...] = ("preferences", "local")
# Server setting: long-term memory exists only while this is True. Set it to False before any
# deployment (LEGAL_COMPLIANCE "Before a public deployment"); the visitor check below is a second
# line, not the switch-off (legal review T5.11, round 2).
LONG_TERM_MEMORY_ENABLED = True
# The memory switch is offered only when the page is opened on the computer that runs the app, so a
# deployed copy never shares one family's memory with other visitors (security review T5.11).
MEMORY_LOCAL_ADDRESSES: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
# Headers a proxy or tunnel adds (lower case); any of them, even empty, means the visitor is not on
# this computer (security review T5.11, rounds 5 and 6).
FORWARDING_HEADERS: frozenset[str] = frozenset({"forwarded", "via"})
FORWARDING_HEADER_PREFIXES: tuple[str, ...] = (
    "x-forwarded-",
    "x-real-",
    "x-client-",
    "x-original-",
    "true-client-",
    "cf-",
)
# A memory file larger than this is treated as broken (it holds at most nine short entries).
MAX_MEMORY_FILE_BYTES = 64_000
# Short-term memory: the earlier turns sent to the model are trimmed to about this many tokens;
# the latest question and its tool results are always sent whole.
MAX_HISTORY_TOKENS = 16000

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
# Overpass, Open-Meteo and Ticketmaster ask for an identifying User-Agent with a contact.
HTTP_USER_AGENT = "kids-events-finder/0.3 (+https://github.com/NMH1988/kids-events-finder)"
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
TRANSITOUS_USER_AGENT = HTTP_USER_AGENT
# Modes the Deutschlandticket and Länder-Tickets cover: no ICE, IC, night trains or coaches.
REGIONAL_TRANSIT_MODES = ("REGIONAL_RAIL", "SUBURBAN", "SUBWAY", "TRAM", "BUS", "FERRY")
TRAIN_MAX_RESULTS = 3
TRAIN_MAX_DAYS_AHEAD = 30
LOCAL_TIMEZONE = "Europe/Berlin"
TRIP_TRAVELLERS_RANGE = (1, 5)  # adults per trip; Länder-Tickets cover up to 5 people
BUDGET_RANGE_EUR = (0, 2000)
MAX_BUDGET_ITEMS = 12
MAX_TOOL_ERROR_CHARS = 300  # an error message a tool returns to the model is cut here
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
# What long-term memory may hold: fixed choices only, never free text, place names, age groups,
# the budget or the family size (T5.11). No visited or liked places (LEGAL_COMPLIANCE 1.5-1.7).
MEMORY_TOPICS: tuple[str, ...] = (*CATEGORIES, "indoor", "outdoor")
MEMORY_FEELINGS: tuple[str, ...] = ("likes", "avoids")
# A preference is saved only when the parent's own latest message names its topic with one of these
# words (English, German, Vietnamese). Whole words only, with an English plural ending allowed
# (`MEMORY_WORD_ENDINGS`; other forms are listed), so "parking" or "parken" is not "park"; a phrase
# of another topic that contains the word ("theme park", "Zoologischer Garten") does not count
# either. Ambiguous words ("inside", "outside", Vietnamese "trong nhà" alone, which also starts
# "trong nhà hàng") are left out. Text in a tool result cannot make the model save a topic the
# parent never named (security review T5.11, rounds 1-3).
MEMORY_TOPIC_WORDS: dict[str, tuple[str, ...]] = {
    "museum": ("museum", "museen", "bảo tàng"),
    "science_centre": (
        "science",
        "wissenschaft",
        "experiment",
        "experimente",
        "experimenten",
        "khoa học",
    ),
    "zoo": (
        "zoo",
        "zoological garden",
        "zoologischer garten",
        "tierpark",
        "wildpark",
        "animal",
        "tiere",
        "tieren",
        "sở thú",
        "vườn thú",
    ),
    "aquarium": ("aquarium", "aquarien", "sea life", "thủy cung", "thuỷ cung"),
    "theme_park": (
        "theme park",
        "amusement park",
        "freizeitpark",
        "erlebnispark",
        "công viên giải trí",
    ),
    "park": ("park", "garden", "garten", "gärten", "công viên"),
    "playground": ("playground", "spielplatz", "spielplätze", "spielplätzen", "sân chơi"),
    "indoor": ("indoor", "drinnen", "chơi trong nhà", "ở trong nhà"),
    "outdoor": ("outdoor", "draußen", "im freien", "ngoài trời"),
}
MEMORY_WORD_ENDINGS = r"(?:s|es)?"
# A saved date later than now plus this many seconds counts as broken (it would never expire).
MEMORY_CLOCK_SKEW_SECONDS = 5 * 60
MEMORY_TOPIC_LABELS: dict[str, str] = {
    "museum": "museums",
    "science_centre": "science centres",
    "zoo": "zoos",
    "aquarium": "aquariums",
    "theme_park": "theme parks",
    "park": "parks",
    "playground": "playgrounds",
    "indoor": "indoor places",
    "outdoor": "outdoor places",
}


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
