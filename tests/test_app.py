"""Smoke tests of the Streamlit page with AppTest (no API key, no network)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_runs_without_key_and_browse_shows_places():
    """Without a key the page renders, the chat explains what is missing, Browse has cards."""
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("OPENROUTER_API_KEY" in i.value for i in at.info)
    assert any("places · opening times" in c.value for c in at.caption)


def test_changing_country_changes_city_list():
    """Choosing the United States offers US cities in the city dropdown."""
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.selectbox(key="country").set_value("US").run()
    city_box = at.sidebar.selectbox(key="city_US")
    assert "Chicago" in city_box.options
