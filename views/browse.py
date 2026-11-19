"""The Browse tab: curated places for the chosen country as cards, no model call needed."""

import streamlit as st

from src import config
from src.knowledge import Place, filter_places
from views.sidebar import Settings

_ICONS = {
    "museum": "🏛️",
    "science_centre": "🔬",
    "zoo": "🦁",
    "aquarium": "🐠",
    "theme_park": "🎢",
    "park": "🌳",
    "playground": "🛝",
}


def _label(category: str) -> str:
    """Return a category's icon and readable name."""
    return f"{_ICONS.get(category, '📍')} {category.replace('_', ' ').capitalize()}"


def render_place_card(place: Place) -> None:
    """Draw one place as a card with Website and Directions buttons."""
    with st.container(border=True):
        st.markdown(f"#### {_ICONS.get(place.category, '📍')} {place.name}")
        trip = f" · day trip from {', '.join(place.day_trip_from)}" if place.day_trip_from else ""
        st.caption(
            f"{place.city}{trip} · ages {place.age_min}-{place.age_max} · {place.setting} · "
            f"{place.price}"
        )
        st.write(place.description)
        left, right = st.columns(2)
        left.link_button("🌐 Website", str(place.website), use_container_width=True)
        right.link_button("🗺️ Directions", place.maps_url, use_container_width=True)


def render_browse(settings: Settings) -> None:
    """Draw the filters and the matching place cards."""
    st.subheader(f"Places for families in {config.COUNTRIES[settings.country]}")
    left, right = st.columns(2)
    category = left.selectbox(
        "Type of place",
        [None, *config.CATEGORIES],
        format_func=lambda c: "All" if c is None else _label(c),
    )
    setting = right.selectbox(
        "Indoor or outdoor", [None, "indoor", "outdoor"], format_func=lambda s: s or "Both"
    )
    places = filter_places(settings.country, settings.city, category, settings.children, setting)
    st.caption(f"{len(places)} places · opening times and prices change, check the website first.")
    if not places:
        st.info("No curated places match these filters. Try the chat for live results.")
        return
    columns = st.columns(2)
    for i, place in enumerate(places):
        with columns[i % 2]:
            render_place_card(place)
