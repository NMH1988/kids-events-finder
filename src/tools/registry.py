"""The agent's tools: argument schemas (validated before a tool runs) and JSON results."""

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Literal

import requests
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from src.rag.retriever import AdvancedRetriever
from src.tools import external

logger = logging.getLogger(__name__)

Country = Literal["DE", "GB", "US"]
Category = Literal[
    "museum", "science_centre", "zoo", "aquarium", "theme_park", "park", "playground"
]


@dataclass
class RagSettings:
    """Switches for the advanced RAG pipeline, set from the sidebar."""

    multi_query: bool = True
    rerank: bool = False


class KnowledgeBaseArgs(BaseModel):
    """Arguments of the knowledge base search."""

    query: str = Field(min_length=2, max_length=300, description="What the family is looking for.")
    country: Country = Field(description="ISO country code: DE, GB or US.")
    city: str | None = Field(default=None, max_length=60, description="City, or null for all.")
    child_age: int | None = Field(default=None, ge=0, le=17, description="Child's age in years.")
    indoor_only: bool = Field(default=False, description="True for rainy-day or indoor plans.")


class PlacesArgs(BaseModel):
    """Arguments of the OpenStreetMap nearby places search."""

    city: str = Field(min_length=2, max_length=60)
    country: Country
    category: Category


class EventsArgs(BaseModel):
    """Arguments of the Ticketmaster family events search."""

    city: str = Field(min_length=2, max_length=60)
    country: Country
    start_date: date = Field(description="First day, YYYY-MM-DD, today or later.")
    end_date: date = Field(description="Last day, YYYY-MM-DD.")


class WeatherArgs(BaseModel):
    """Arguments of the weather forecast."""

    city: str = Field(min_length=2, max_length=60)
    country: Country
    start_date: date
    end_date: date


def _safe(tool_name: str, func, **kwargs) -> str:
    """Run a tool function and return JSON; failures become an error message, not an exception."""
    try:
        return json.dumps(func(**kwargs), ensure_ascii=False, default=str)
    except external.ToolInputError as exc:
        return json.dumps({"error": str(exc), "results": []})
    except requests.RequestException as exc:
        logger.warning("tool_http_error", extra={"tool": tool_name, "type": type(exc).__name__})
        return json.dumps(
            {"error": "The external service did not answer. Try again later.", "results": []}
        )


def build_tools(
    retriever: AdvancedRetriever,
    rag_settings: RagSettings | None = None,
    ticketmaster_key: str | None = None,
) -> list[BaseTool]:
    """Return the four tools the agent can call."""
    settings = rag_settings or RagSettings()

    def search_knowledge_base(
        query: str,
        country: str,
        city: str | None = None,
        child_age: int | None = None,
        indoor_only: bool = False,
    ) -> str:
        """Search the curated knowledge base of family-friendly places (museums, zoos, etc.)."""

        def run() -> dict:
            """Run the advanced RAG search and shape its results."""
            found = retriever.search(
                query,
                country,
                city,
                child_age,
                indoor_only,
                multi_query=settings.multi_query,
                rerank=settings.rerank,
            )
            return {
                "source": "Curated knowledge base (official websites)",
                "results": [
                    {
                        "id": r.place.id,
                        "name": r.place.name,
                        "city": r.place.city,
                        "day_trip_from": r.place.day_trip_from,
                        "category": r.place.category,
                        "ages": f"{r.place.age_min}-{r.place.age_max}",
                        "setting": r.place.setting,
                        "price": r.place.price,
                        "description": r.place.description,
                        "website": str(r.place.website),
                        "maps_url": r.place.maps_url,
                    }
                    for r in found
                ],
            }

        return _safe("search_knowledge_base", run)

    def find_nearby_places(city: str, country: str, category: str) -> str:
        """Find more places of one category near a city centre in OpenStreetMap (live data)."""
        return _safe(
            "find_nearby_places",
            external.find_nearby_places,
            city=city,
            country=country,
            category=category,
        )

    def search_family_events(city: str, country: str, start_date: date, end_date: date) -> str:
        """Search live family events (shows, concerts, festivals) in a city between two dates."""
        return _safe(
            "search_family_events",
            external.search_family_events,
            city=city,
            country=country,
            start_date=start_date,
            end_date=end_date,
            api_key=ticketmaster_key,
        )

    def get_weather_forecast(city: str, country: str, start_date: date, end_date: date) -> str:
        """Get the daily forecast (up to 15 days ahead) to choose indoor or outdoor plans."""
        return _safe(
            "get_weather_forecast",
            external.get_weather_forecast,
            city=city,
            country=country,
            start_date=start_date,
            end_date=end_date,
        )

    return [
        StructuredTool.from_function(search_knowledge_base, args_schema=KnowledgeBaseArgs),
        StructuredTool.from_function(find_nearby_places, args_schema=PlacesArgs),
        StructuredTool.from_function(search_family_events, args_schema=EventsArgs),
        StructuredTool.from_function(get_weather_forecast, args_schema=WeatherArgs),
    ]
