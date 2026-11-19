"""Tests for the external service calls, with every HTTP request mocked."""

from datetime import date, time, timedelta

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


def test_train_result_links_to_transitous_sources(monkeypatch, at_berlin):
    """The journey result carries the Transitous sources link as its own field."""
    empty = FakeResponse({"itineraries": []})
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: empty)
    result = external.find_train_connection("Berlin", "Potsdam", TODAY, time(9, 0))
    assert result["source_url"] == "https://transitous.org/sources/"


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


def test_train_connection_uses_regional_modes_and_local_times(monkeypatch):
    """Journeys come back in local time with live delays; only regional modes are requested."""
    places = {
        "Munich": geo.Location("Munich", "DE", 48.14, 11.56, "Bavaria"),
        "Augsburg": geo.Location("Augsburg", "DE", 48.37, 10.90, "Bavaria"),
    }
    monkeypatch.setattr(geo, "geocode_city", lambda city, country: places[city])
    seen = {}

    def fake_get(url, params, headers, **kwargs):
        """Return one journey with a 5-minute delay and record the request."""
        seen.update(params, ua=headers["User-Agent"])
        ride = {
            "mode": "REGIONAL_RAIL",
            "displayName": "RE89",
            "from": {"name": "München Hbf"},
            "to": {"name": "Augsburg Hbf"},
            "startTime": "2026-11-21T08:40:00Z",
            "scheduledStartTime": "2026-11-21T08:35:00Z",
            "realTime": True,
        }
        walk = {"mode": "WALK", "from": {"name": "START"}, "to": {"name": "München Hbf"}}
        itinerary = {
            "startTime": "2026-11-21T08:33:00Z",
            "endTime": "2026-11-21T09:20:00Z",
            "duration": 2820,
            "transfers": 0,
            "legs": [walk, ride],
        }
        return FakeResponse({"itineraries": [itinerary]})

    monkeypatch.setattr(requests, "get", fake_get)
    day = TODAY + timedelta(days=2)
    result = external.find_train_connection("Munich", "Augsburg", day, time(9, 30))
    journey = result["results"][0]
    assert journey["depart"] == "09:33" and journey["arrive"] == "10:20"  # CET is UTC+1
    assert journey["rides"] == ["RE89 München Hbf → Augsburg Hbf"]
    assert journey["delay_min"] == 5 and journey["live_data"] is True
    assert result["from_state"] == "BY" and result["to_state"] == "BY"
    assert "HIGHSPEED_RAIL" not in seen["transitModes"] and "REGIONAL_RAIL" in seen["transitModes"]
    assert "github.com" in seen["ua"]
    assert "travelmode=transit" in result["maps_url"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.tierpark-göttingen.de", "https://www.xn--tierpark-gttingen-8zb.de"),
        ("zoo.example/Öffnungszeiten ", "https://zoo.example/%C3%96ffnungszeiten"),
        ("HTTPS://Zoo.Example/a", "https://zoo.example/a"),
        ("https://zoo.example/a b", "https://zoo.example/a%20b"),
        ("https://user@evil.example/", None),
        ("zoo.example:99999", None),
        ("zoo.example:8080/a", None),
        ("Tel: 030 123", None),
        ("javascript:alert(1)", None),
        ("ftp://zoo.de", None),
        ("http://localhost/x", None),
        ("http://10.0.0.1/x", None),
        ("zoo.example%2eevil.example", None),
        ("https://zoo.example:443/a", "https://zoo.example/a"),
        ("", None),
        (None, None),
    ],
)
def test_osm_website_values_are_cleaned_into_strict_urls(raw, expected):
    """Crowd-sourced website tags become encoded http(s) URLs, or None when unusable."""
    assert external.clean_website(raw) == expected
