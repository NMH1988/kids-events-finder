"""Loads and validates the curated knowledge base and turns entries into LangChain documents."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from langchain_core.documents import Document
from pydantic import BaseModel, Field, HttpUrl, model_validator

from src import config, family, geo


class Place(BaseModel):
    """One curated family-friendly place."""

    id: str
    name: str
    country: Literal["DE", "GB", "US"]
    city: str
    day_trip_from: list[str] = Field(default_factory=list)
    category: Literal[config.CATEGORIES]  # type: ignore[valid-type]
    age_min: int = Field(ge=0, le=17)
    age_max: int = Field(ge=0, le=17)
    setting: Literal["indoor", "outdoor", "mixed"]
    price: Literal["free", "paid", "mixed"]
    website: HttpUrl
    tags: list[str]
    description: str = Field(min_length=40, max_length=400)

    @model_validator(mode="after")
    def _ages_in_order(self) -> Place:
        """Reject an entry whose minimum age is above its maximum age."""
        if self.age_min > self.age_max:
            raise ValueError(f"{self.id}: age_min is above age_max")
        return self

    @property
    def maps_url(self) -> str:
        """Return the Google Maps directions link for this place."""
        return geo.directions_url(name=self.name, city=self.city, country=self.country)

    def serves_city(self, city: str) -> bool:
        """Return True when the place is in the city or is a day trip from it."""
        return city.lower() in {self.city.lower(), *(c.lower() for c in self.day_trip_from)}

    def suits_children(self, bands: tuple[str, ...] | list[str] = ()) -> bool:
        """Return True when the place's age range overlaps every child's age group."""
        return all(family.overlaps(b, self.age_min, self.age_max) for b in bands)

    def to_text(self) -> str:
        """Return the text that is embedded and searched for this place."""
        trip = f" Day trip from {', '.join(self.day_trip_from)}." if self.day_trip_from else ""
        return (
            f"{self.name} ({self.category.replace('_', ' ')}) in {self.city}, "
            f"{config.COUNTRIES[self.country]}.{trip} Ages {self.age_min}-{self.age_max}. "
            f"Setting: {self.setting}. Price: {self.price}. Tags: {', '.join(self.tags)}. "
            f"{self.description}"
        )

    def to_document(self) -> Document:
        """Return a LangChain document with the place's text and filterable metadata."""
        return Document(
            id=self.id,
            page_content=self.to_text(),
            metadata={
                "id": self.id,
                "name": self.name,
                "country": self.country,
                "city": self.city,
                # Chroma metadata holds only scalars, so the day-trip cities become one string.
                "day_trip_from": "|".join(self.day_trip_from),
                "category": self.category,
                "age_min": self.age_min,
                "age_max": self.age_max,
                "setting": self.setting,
                "price": self.price,
                "website": str(self.website),
            },
        )


@lru_cache(maxsize=4)
def load_places(path: Path = config.KNOWLEDGE_BASE_FILE) -> tuple[Place, ...]:
    """Load and validate every place in the knowledge base file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    places = tuple(Place.model_validate(item) for item in raw["places"])
    ids = [p.id for p in places]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate place ids in the knowledge base.")
    return places


def get_place(place_id: str) -> Place | None:
    """Return the place with this id, or None."""
    return next((p for p in load_places() if p.id == place_id), None)


def filter_places(
    country: str,
    city: str | None = None,
    category: str | None = None,
    bands: tuple[str, ...] | list[str] = (),
    setting: str | None = None,
) -> list[Place]:
    """Return the places matching the dropdown filters, used by the Browse tab."""
    result = []
    for place in load_places():
        if place.country != country:
            continue
        if city and not place.serves_city(city):
            continue
        if category and place.category != category:
            continue
        if setting == "indoor" and place.setting == "outdoor":
            continue
        if setting == "outdoor" and place.setting == "indoor":
            continue
        if not place.suits_children(bands):
            continue
        result.append(place)
    return result
