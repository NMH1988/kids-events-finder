"""Calls to external services: OpenStreetMap (Overpass), Ticketmaster Discovery and Open-Meteo.

Only a city, a country code, dates and a category are sent; nothing about the user or the child.
Every function returns plain dicts that the agent's tools turn into JSON.
"""

import math
from datetime import date, timedelta

import requests

from src import config, geo

ATTRIBUTION_OSM = "Data © OpenStreetMap contributors, ODbL (openstreetmap.org/copyright)"
ATTRIBUTION_TICKETMASTER = "Event data from Ticketmaster Discovery API"
ATTRIBUTION_WEATHER = "Weather data by Open-Meteo.com (CC BY 4.0)"

# OpenStreetMap tag filters for each category the agent may ask for.
_OSM_FILTERS: dict[str, tuple[str, ...]] = {
    "playground": ('["leisure"="playground"]',),
    "park": ('["leisure"="park"]',),
    "zoo": ('["tourism"="zoo"]',),
    "aquarium": ('["tourism"="aquarium"]',),
    "theme_park": ('["tourism"="theme_park"]',),
    "museum": ('["tourism"="museum"]',),
    "science_centre": (
        '["tourism"="museum"]["museum"~"science|technology|children"]',
        '["amenity"="science_centre"]',
    ),
}

# WMO weather codes used by Open-Meteo, grouped into plain words.
_WEATHER_CODES: dict[range, str] = {
    range(0, 1): "clear sky",
    range(1, 4): "partly cloudy",
    range(45, 49): "fog",
    range(51, 58): "drizzle",
    range(61, 68): "rain",
    range(71, 78): "snow",
    range(80, 83): "rain showers",
    range(85, 87): "snow showers",
    range(95, 100): "thunderstorm",
}


class ToolInputError(ValueError):
    """A tool argument is outside what the tool accepts."""


def _get_json(url: str, params: dict) -> dict:
    """GET a URL with the app's user agent and timeout and return the JSON body."""
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": config.HTTP_USER_AGENT},
        timeout=config.HTTP_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    return response.json()


def _locate(city: str, country: str) -> geo.Location:
    """Geocode a city or raise ToolInputError when it is not found in that country."""
    location = geo.geocode_city(city, country)
    if location is None:
        raise ToolInputError(f"City '{city}' was not found in {config.COUNTRIES[country]}.")
    return location


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two points in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def describe_weather(code: int | None) -> str:
    """Return plain words for a WMO weather code."""
    if code is None:
        return "unknown"
    return next((text for codes, text in _WEATHER_CODES.items() if code in codes), "unknown")


def build_overpass_query(category: str, lat: float, lon: float, radius: int) -> str:
    """Return the Overpass QL query for named places of a category around a point."""
    if category not in _OSM_FILTERS:
        raise ToolInputError(f"Unknown category: {category}")
    parts = "".join(
        f'nwr{f}["name"](around:{radius},{lat:.5f},{lon:.5f});' for f in _OSM_FILTERS[category]
    )
    return f"[out:json][timeout:25];({parts});out center tags 60;"


def find_nearby_places(city: str, country: str, category: str) -> dict:
    """Find named places of a category around a city's centre in OpenStreetMap."""
    location = _locate(city, country)
    query = build_overpass_query(
        category, location.latitude, location.longitude, config.PLACES_RADIUS_METERS
    )
    response = requests.post(
        config.OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": config.HTTP_USER_AGENT},
        timeout=config.HTTP_TIMEOUT_SECONDS + 15,
        allow_redirects=False,
    )
    response.raise_for_status()
    places = []
    seen: set[str] = set()
    for element in response.json().get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name")
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lon = element.get("lon") or element.get("center", {}).get("lon")
        if not name or lat is None or lon is None or name in seen:
            continue
        seen.add(name)
        website = tags.get("website") or tags.get("contact:website")
        if website and not website.startswith(("http://", "https://")):
            website = "https://" + website
        details = [category.replace("_", " ")]
        if tags.get("fee") in ("no", "yes"):
            details.append("free entry" if tags["fee"] == "no" else "entry fee")
        if tags.get("opening_hours"):
            details.append(f"opening hours (OSM): {tags['opening_hours']}")
        if tags.get("wheelchair") == "yes":
            details.append("wheelchair accessible")
        places.append(
            {
                "name": name,
                "category": category,
                "city": location.name,
                "distance_km": round(
                    _distance_km(location.latitude, location.longitude, lat, lon), 1
                ),
                "details": "; ".join(details),
                "website": website,
                "maps_url": geo.directions_url(lat=lat, lon=lon),
            }
        )
    # Places with a website first (more useful to parents), then the nearest.
    places.sort(key=lambda p: (p["website"] is None, p["distance_km"]))
    return {
        "source": ATTRIBUTION_OSM,
        "city": location.name,
        "country": country,
        "results": places[: config.PLACES_MAX_RESULTS],
    }


def _check_dates(start: date, end: date, max_days_ahead: int) -> None:
    """Raise ToolInputError when a date range is in the past, reversed or too far ahead."""
    today = date.today()
    if start < today:
        raise ToolInputError("start_date is in the past.")
    if end < start:
        raise ToolInputError("end_date is before start_date.")
    if end > today + timedelta(days=max_days_ahead):
        raise ToolInputError(f"Dates can be at most {max_days_ahead} days ahead.")


def search_family_events(
    city: str, country: str, start_date: date, end_date: date, api_key: str | None
) -> dict:
    """Search Ticketmaster for family events in a city between two dates."""
    _check_dates(start_date, end_date, config.EVENTS_MAX_DAYS_AHEAD)
    if not api_key:
        return {
            "source": ATTRIBUTION_TICKETMASTER,
            "error": "Event search is not configured (no Ticketmaster key). "
            "Use the knowledge base and nearby places instead.",
            "results": [],
        }
    response = requests.get(
        config.TICKETMASTER_URL,
        params={
            "apikey": api_key,
            "countryCode": country,
            "city": city,
            "classificationName": "family",
            "startDateTime": f"{start_date.isoformat()}T00:00:00Z",
            "endDateTime": f"{end_date.isoformat()}T23:59:59Z",
            "size": config.EVENTS_MAX_RESULTS * 2,
            "sort": "date,asc",
            "locale": "*",
        },
        headers={"User-Agent": config.HTTP_USER_AGENT},
        timeout=config.HTTP_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    events = []
    seen: set[str] = set()
    for event in response.json().get("_embedded", {}).get("events", []):
        name = event.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        venue = (event.get("_embedded", {}).get("venues") or [{}])[0]
        location = venue.get("location") or {}
        start = event.get("dates", {}).get("start", {})
        text = event.get("info") or event.get("pleaseNote") or ""
        if venue.get("name"):
            maps_url = geo.directions_url(
                name=venue["name"],
                city=(venue.get("city") or {}).get("name", city),
                country=country,
            )
        elif location.get("latitude"):
            maps_url = geo.directions_url(
                lat=float(location["latitude"]), lon=float(location["longitude"])
            )
        else:
            maps_url = geo.directions_url(name=name, city=city, country=country)
        events.append(
            {
                "name": name,
                "date": start.get("localDate"),
                "time": start.get("localTime"),
                "venue": venue.get("name"),
                "city": (venue.get("city") or {}).get("name", city),
                "details": text[:300],
                "website": event.get("url"),
                "maps_url": maps_url,
            }
        )
    return {
        "source": ATTRIBUTION_TICKETMASTER,
        "city": city,
        "country": country,
        "results": events[: config.EVENTS_MAX_RESULTS],
    }


def get_weather_forecast(city: str, country: str, start_date: date, end_date: date) -> dict:
    """Return the daily forecast for a city, to choose between indoor and outdoor plans."""
    _check_dates(start_date, end_date, config.WEATHER_MAX_DAYS_AHEAD)
    location = _locate(city, country)
    data = _get_json(
        config.WEATHER_URL,
        {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max",
            "timezone": "auto",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    )
    daily = data.get("daily", {})
    days = []
    for i, day in enumerate(daily.get("time", [])):
        code = (daily.get("weather_code") or [None])[i]
        rain = (daily.get("precipitation_probability_max") or [None])[i]
        days.append(
            {
                "date": day,
                "summary": describe_weather(code),
                "temp_min_c": (daily.get("temperature_2m_min") or [None])[i],
                "temp_max_c": (daily.get("temperature_2m_max") or [None])[i],
                "rain_probability_pct": rain,
                "suggest_indoor": bool((rain or 0) >= 50 or (code or 0) >= 51),
            }
        )
    return {"source": ATTRIBUTION_WEATHER, "city": location.name, "days": days}
