"""Google Maps direction links and city geocoding (Open-Meteo, no key needed)."""

from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from src import config

_MAPS_DIR = "https://www.google.com/maps/dir/"


@dataclass(frozen=True)
class Location:
    """A geocoded city: its name, country code, coordinates and state (admin1)."""

    name: str
    country_code: str
    latitude: float
    longitude: float
    state: str | None = None


def directions_url(
    name: str | None = None,
    city: str | None = None,
    country: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> str:
    """Return a Google Maps directions link to a place, from the user's current location.

    Coordinates are used when known (exact); otherwise the place name, city and country are sent
    as a search text that Google Maps resolves. Uses the documented Maps URLs scheme, which needs
    no API key.
    """
    if lat is not None and lon is not None:
        destination = f"{lat:.6f},{lon:.6f}"
    else:
        parts = [p for p in (name, city, config.COUNTRIES.get(country or "", country)) if p]
        if not parts:
            raise ValueError("A destination needs a name or coordinates.")
        destination = ", ".join(parts)
    return _MAPS_DIR + "?" + urlencode({"api": "1", "destination": destination})


def transit_directions_url(origin: str, destination: str) -> str:
    """Return a Google Maps public-transport directions link between two named places."""
    query = {"api": "1", "origin": origin, "destination": destination, "travelmode": "transit"}
    return _MAPS_DIR + "?" + urlencode(query)


def geocode_city(city: str, country_code: str) -> Location | None:
    """Return the coordinates of a city in a country, or None when it cannot be found."""
    response = requests.get(
        config.GEOCODING_URL,
        params={"name": city, "count": 5, "language": "en", "countryCode": country_code},
        headers={"User-Agent": config.HTTP_USER_AGENT},
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    # Open-Meteo filters by countryCode, but checking again guards against a changed API.
    matches = [r for r in results if r.get("country_code", "").upper() == country_code.upper()]
    if not matches:
        return None
    best = max(matches, key=lambda r: r.get("population") or 0)
    return Location(
        name=best["name"],
        country_code=country_code.upper(),
        latitude=float(best["latitude"]),
        longitude=float(best["longitude"]),
        state=best.get("admin1"),
    )
