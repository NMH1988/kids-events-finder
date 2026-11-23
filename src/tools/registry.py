"""The agent's tools: argument schemas (validated before a tool runs) and JSON results."""

import json
import logging
from dataclasses import dataclass
from datetime import date, time
from typing import Annotated, Literal

import requests
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt import InjectedState
from pydantic import AfterValidator, BaseModel, Field, ValidationError

from src import budget, config, family, fares, privacy_check
from src.errors import AppInputError
from src.family import AgeBand
from src.rag.retriever import AdvancedRetriever
from src.tools import external

logger = logging.getLogger(__name__)

Country = Literal["DE", "GB", "US"]
Category = Literal[
    "museum", "science_centre", "zoo", "aquarium", "theme_park", "park", "playground"
]
# A town or city name only: no free text reaches the geocoder or other outside services.
PlaceName = Annotated[
    str, Field(min_length=2, max_length=60), AfterValidator(privacy_check.check_place_name)
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
    city: PlaceName | None = Field(default=None, description="City, or null for all.")
    age_bands: list[AgeBand] = Field(
        default_factory=list,
        max_length=family.MAX_CHILDREN,
        description="Children's age groups from the context; every place must suit all of them.",
    )
    indoor_only: bool = Field(default=False, description="True for rainy-day or indoor plans.")


class PlacesArgs(BaseModel):
    """Arguments of the OpenStreetMap nearby places search."""

    city: PlaceName
    country: Country
    category: Category


class EventsArgs(BaseModel):
    """Arguments of the Ticketmaster family events search."""

    city: PlaceName
    country: Country
    start_date: date = Field(description="First day, YYYY-MM-DD, today or later.")
    end_date: date = Field(description="Last day, YYYY-MM-DD.")


class WeatherArgs(BaseModel):
    """Arguments of the weather forecast."""

    city: PlaceName
    country: Country
    start_date: date
    end_date: date


class TrainArgs(BaseModel):
    """Arguments of the regional train journey search (Germany only)."""

    from_city: PlaceName = Field(description="Where the family starts.")
    to_town: PlaceName = Field(description="Town of the destination.")
    travel_date: date = Field(description="Day of the trip, YYYY-MM-DD.")
    depart_after: time = Field(default=time(9, 0), description="Earliest departure, HH:MM.")


class TicketArgs(BaseModel):
    """Arguments of the ticket comparison; the party comes from the app's trip settings."""

    from_state: str = Field(min_length=2, max_length=40, description="State code, e.g. BY.")
    to_state: str = Field(min_length=2, max_length=40, description="State code, e.g. BY.")
    travel_date: date
    departure: time | None = Field(default=None, description="Departure time, HH:MM.")
    # Injected by the graph from the sidebar settings, never written by the model, so a cheaper
    # party cannot be made up (security review R1-4). They are not in the model's tool schema.
    trip: Annotated[dict | None, InjectedState("trip")] = None
    children: Annotated[list[str] | None, InjectedState("children")] = None


class BudgetArgs(BaseModel):
    """Arguments of the budget check; the parent fills in unknown amounts before it runs."""

    budget_eur: float = Field(ge=0, le=config.BUDGET_RANGE_EUR[1])
    items: list[budget.BudgetItem] = Field(min_length=1, max_length=config.MAX_BUDGET_ITEMS)


def _safe(tool_name: str, func, **kwargs) -> str:
    """Run a tool function and return JSON; failures become an error message, not an exception."""
    try:
        return json.dumps(func(**kwargs), ensure_ascii=False, default=str)
    except AppInputError as exc:
        # The app wrote this message, so the model may see it.
        return json.dumps({"error": str(exc), "results": []})
    except ValidationError as exc:
        # Pass the messages on only when the app's own validators wrote all of them; a validator
        # message may quote its input, which could be a service's text.
        errors = exc.errors()
        if errors and all(isinstance(e.get("ctx", {}).get("error"), AppInputError) for e in errors):
            messages = "; ".join(e["msg"].removeprefix("Value error, ") for e in errors)
            return json.dumps({"error": messages[: config.MAX_TOOL_ERROR_CHARS], "results": []})
        logger.warning("tool_bad_value", extra={"tool": tool_name, "type": type(exc).__name__})
        return json.dumps(
            {"error": "The tool got data it could not read. Try again later.", "results": []}
        )
    except ValueError as exc:
        # Usually a service value that could not be parsed: never echo the service's text.
        logger.warning("tool_bad_value", extra={"tool": tool_name, "type": type(exc).__name__})
        return json.dumps(
            {"error": "The tool got data it could not read. Try again later.", "results": []}
        )
    except requests.RequestException as exc:
        logger.warning("tool_http_error", extra={"tool": tool_name, "type": type(exc).__name__})
        return json.dumps(
            {"error": "The external service did not answer. Try again later.", "results": []}
        )
    except (LookupError, TypeError, AttributeError, ArithmeticError, RecursionError) as exc:
        # A malformed answer from an outside service must not end the whole turn.
        logger.warning("tool_bad_data", extra={"tool": tool_name, "type": type(exc).__name__})
        return json.dumps(
            {"error": "The tool got data it could not read. Try again later.", "results": []}
        )


def build_tools(
    retriever: AdvancedRetriever,
    rag_settings: RagSettings | None = None,
    ticketmaster_key: str | None = None,
) -> list[BaseTool]:
    """Return the tools the agent can call."""
    settings = rag_settings or RagSettings()

    def search_knowledge_base(
        query: str,
        country: str,
        city: str | None = None,
        age_bands: list[str] | None = None,
        indoor_only: bool = False,
    ) -> str:
        """Search the curated knowledge base of family-friendly places (museums, zoos, etc.)."""

        def run() -> dict:
            """Run the advanced RAG search and shape its results."""
            found = retriever.search(
                query,
                country,
                city,
                tuple(age_bands or ()),
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

    def find_train_connection(
        from_city: str, to_town: str, travel_date: date, depart_after: time = time(9, 0)
    ) -> str:
        """Find regional-train journeys (Deutschlandticket area, no ICE/IC) in Germany."""
        return _safe(
            "find_train_connection",
            external.find_train_connection,
            from_city=from_city,
            to_town=to_town,
            travel_date=travel_date,
            depart_after=depart_after,
        )

    def compare_train_tickets(
        from_state: str,
        to_state: str,
        travel_date: date,
        departure: time | None = None,
        trip: dict | None = None,
        children: list[str] | None = None,
    ) -> str:
        """Compare regional day tickets for the family set in the app's trip settings."""

        def run() -> dict:
            """Build the party from the trip settings and compare the tickets."""
            if not trip:
                raise AppInputError(
                    "Ask the parent to switch on budget day trip planning in the sidebar; the "
                    "ticket comparison uses the number of adults and Deutschlandticket holders set "
                    "there."
                )
            party = fares.Party(
                adults=int(trip["adults"]),
                children_bands=tuple(children or ()),
                deutschlandticket_holders=int(trip["deutschlandticket_holders"]),
            )
            return fares.compare_tickets(party, from_state, to_state, travel_date, departure)

        return _safe("compare_train_tickets", run)

    def check_budget(budget_eur: float, items: list[budget.BudgetItem]) -> str:
        """Add up the trip's costs against the budget; the parent fills in unknown amounts."""
        parsed = [budget.BudgetItem.model_validate(i) for i in items]
        return _safe("check_budget", budget.check_budget, budget_eur=budget_eur, items=parsed)

    return [
        StructuredTool.from_function(search_knowledge_base, args_schema=KnowledgeBaseArgs),
        StructuredTool.from_function(find_nearby_places, args_schema=PlacesArgs),
        StructuredTool.from_function(search_family_events, args_schema=EventsArgs),
        StructuredTool.from_function(get_weather_forecast, args_schema=WeatherArgs),
        StructuredTool.from_function(find_train_connection, args_schema=TrainArgs),
        StructuredTool.from_function(compare_train_tickets, args_schema=TicketArgs),
        StructuredTool.from_function(check_budget, args_schema=BudgetArgs),
    ]
