"""Tests for the external service calls, with every HTTP request mocked."""

from datetime import date, timedelta

import pytest
import requests

from src import geo
from src.tools import external
from tests.conftest import FakeResponse

BERLIN = geo.Location("Berlin", "DE", 52.52, 13.405)
TODAY = date.today()


@pytest.fixture
def at_berlin(monkeypatch):
    """Make geocoding return Berlin without a request."""
    monkeypatch.setattr(geo, "geocode_city", lambda city, country: BERLIN)


def test_directions_url_prefers_coordinates():
    """Coordinates give an exact destination."""
    url = geo.directions_url(name="X", lat=52.5, lon=13.4)
    assert url == "https://www.google.com/maps/dir/?api=1&destination=52.500000%2C13.400000"


def test_geocode_checks_country(monkeypatch):
    """Geocoding keeps only results in the requested country, the largest first."""
    payload = {
        "results": [
            {
                "name": "Berlin",
                "country_code": "US",
                "latitude": 1,
                "longitude": 1,
                "population": 1,
            },
            {
                "name": "Berlin",
                "country_code": "DE",
                "latitude": 52.5,
                "longitude": 13.4,
                "population": 3_000_000,
            },
        ]
    }
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload))
    assert geo.geocode_city("Berlin", "DE").latitude == 52.5
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"results": []}))
    assert geo.geocode_city("Nowhere", "DE") is None


def test_overpass_query_uses_category_filter():
    """The Overpass query asks for named playgrounds around the point."""
    query = external.build_overpass_query("playground", 52.52, 13.405, 8000)
    assert '["leisure"="playground"]["name"](around:8000,52.52000,13.40500)' in query
    with pytest.raises(external.ToolInputError):
        external.build_overpass_query("casino", 0, 0, 1)


def test_find_nearby_places_parses_and_sorts(monkeypatch, at_berlin):
    """Named results come back with directions; places with a website come first."""
    elements = {
        "elements": [
            {"type": "node", "lat": 52.52, "lon": 13.40, "tags": {"name": "Near Park"}},
            {
                "type": "way",
                "center": {"lat": 52.60, "lon": 13.50},
                "tags": {"name": "Far Zoo", "website": "zoo.example", "fee": "no"},
            },
            {"type": "node", "lat": 52.0, "lon": 13.0, "tags": {}},
        ]
    }
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(elements))
    result = external.find_nearby_places("Berlin", "DE", "zoo")
    names = [p["name"] for p in result["results"]]
    assert names == ["Far Zoo", "Near Park"]
    assert result["results"][0]["website"] == "https://zoo.example"
    assert "free entry" in result["results"][0]["details"]
    assert result["results"][1]["maps_url"].startswith("https://www.google.com/maps/dir/")
    assert "OpenStreetMap" in result["source"]


def test_events_without_key_explain_instead_of_calling():
    """With no Ticketmaster key the tool explains and makes no request."""
    result = external.search_family_events("Berlin", "DE", TODAY, TODAY, api_key=None)
    assert result["results"] == [] and "not configured" in result["error"]


def test_events_parse_ticketmaster_response(monkeypatch):
    """Events keep name, date, venue, link and a directions link to the venue."""
    seen = {}

    def fake_get(url, params, **kwargs):
        """Return one event and record the request."""
        seen.update(params)
        return FakeResponse(
            {
                "_embedded": {
                    "events": [
                        {
                            "name": "Kids Show",
                            "url": "https://tm.example/e/1",
                            "dates": {"start": {"localDate": "2026-12-01", "localTime": "15:00"}},
                            "info": "Fun for all ages.",
                            "_embedded": {"venues": [{"name": "Hall", "city": {"name": "Berlin"}}]},
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)
    result = external.search_family_events(
        "Berlin", "DE", TODAY, TODAY + timedelta(days=7), api_key="k"
    )
    event = result["results"][0]
    assert event["website"] == "https://tm.example/e/1" and event["venue"] == "Hall"
    assert "Hall" in event["maps_url"].replace("+", " ")
    assert seen["classificationName"] == "family" and seen["countryCode"] == "DE"


def test_dates_are_checked():
    """Past, reversed and far-future dates are rejected before any request."""
    with pytest.raises(external.ToolInputError):
        external.get_weather_forecast("Berlin", "DE", TODAY - timedelta(days=1), TODAY)
    with pytest.raises(external.ToolInputError):
        external.get_weather_forecast("Berlin", "DE", TODAY, TODAY - timedelta(days=1))
    with pytest.raises(external.ToolInputError):
        external.get_weather_forecast("Berlin", "DE", TODAY, TODAY + timedelta(days=40))


def test_weather_suggests_indoor_when_rain_is_likely(monkeypatch, at_berlin):
    """A rainy day is described in words and flagged for indoor plans."""
    payload = {
        "daily": {
            "time": ["d1", "d2"],
            "weather_code": [61, 0],
            "temperature_2m_max": [10, 20],
            "temperature_2m_min": [5, 12],
            "precipitation_probability_max": [80, 0],
        }
    }
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload))
    days = external.get_weather_forecast("Berlin", "DE", TODAY, TODAY + timedelta(days=1))["days"]
    assert days[0]["summary"] == "rain" and days[0]["suggest_indoor"] is True
    assert days[1]["summary"] == "clear sky" and days[1]["suggest_indoor"] is False
