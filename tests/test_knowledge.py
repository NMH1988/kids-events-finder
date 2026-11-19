"""Tests for the curated knowledge base and its filters."""

from urllib.parse import parse_qs, urlparse

from src import config
from src.knowledge import filter_places, get_place, load_places


def test_knowledge_base_loads_and_ids_are_unique():
    """Every entry validates and ids are unique."""
    places = load_places()
    assert len(places) >= 45
    assert len({p.id for p in places}) == len(places)


def test_every_dropdown_city_has_at_least_two_places():
    """Each city offered in the sidebar has curated places to show."""
    for country, cities in config.CITIES.items():
        for city in cities:
            assert len(filter_places(country, city)) >= 2, (country, city)


def test_websites_are_https_and_ids_start_with_country():
    """Links are secure and ids follow the country prefix convention."""
    for place in load_places():
        assert str(place.website).startswith("https://"), place.id
        assert place.id.startswith(place.country.lower() + "-"), place.id


def test_maps_url_targets_place_name_and_city():
    """The directions link sends the place name, city and country to Google Maps."""
    place = get_place("gb-nhm-london")
    query = parse_qs(urlparse(place.maps_url).query)
    assert query["api"] == ["1"]
    assert query["destination"] == ["Natural History Museum, London, United Kingdom"]


def test_filters_by_age_setting_and_day_trip():
    """Age, indoor/outdoor and day-trip cities filter as expected."""
    toddler = filter_places("DE", "Berlin", age=2)
    assert all(p.age_min <= 2 for p in toddler)
    assert "de-technikmuseum" not in {p.id for p in toddler}
    indoor = filter_places("GB", "London", setting="indoor")
    assert all(p.setting != "outdoor" for p in indoor)
    munich = {p.id for p in filter_places("DE", "Munich")}
    assert "de-legoland-deutschland" in munich
