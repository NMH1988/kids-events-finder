"""Children are described only as "Child 1", "Child 2" with an age group; no names, no exact ages.

The groups nest inside the rail fare groups (0-5 free, 6-14 child, 15+ adult), so ticket rules stay
exact, and they are fine enough to match places' age ranges (data minimisation, GDPR Art. 5).
"""

from typing import Literal, get_args

AgeBand = Literal["0-2", "3-5", "6-9", "10-14", "15-17"]
AGE_BANDS: tuple[str, ...] = get_args(AgeBand)
_RANGES: dict[str, tuple[int, int]] = {
    "0-2": (0, 2),
    "3-5": (3, 5),
    "6-9": (6, 9),
    "10-14": (10, 14),
    "15-17": (15, 17),
}
BAND_LABELS: dict[str, str] = {
    "0-2": "👶 0-2 years",
    "3-5": "🧒 3-5 years",
    "6-9": "🎒 6-9 years",
    "10-14": "🧑 10-14 years",
    "15-17": "🧑‍🎓 15-17 years (adult fare)",
}
MAX_CHILDREN = 6
# Rail fares: under 6 free, 6-14 child fare (often free on day tickets), 15+ pay as adults.
SCHOOL_AGE_BANDS = frozenset({"6-9", "10-14"})
ADULT_FARE_BANDS = frozenset({"15-17"})


def band_range(band: str) -> tuple[int, int]:
    """Return the youngest and oldest age of a band, or raise ValueError for an unknown band."""
    if band not in _RANGES:
        raise ValueError(f"Unknown age group '{band}'; use one of {', '.join(AGE_BANDS)}.")
    return _RANGES[band]


def check_bands(bands: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Validate a list of children's age groups and return it as a tuple."""
    if len(bands) > MAX_CHILDREN:
        raise ValueError(f"At most {MAX_CHILDREN} children.")
    for band in bands:
        band_range(band)
    return tuple(bands)


def band_for_age(age: int) -> str:
    """Return the age group for an age (used only to convert old evaluation data)."""
    return next(b for b, (lo, hi) in _RANGES.items() if lo <= age <= hi)


def overlaps(band: str, age_min: int, age_max: int) -> bool:
    """Return True when a place's age range overlaps the age group."""
    lo, hi = band_range(band)
    return age_min <= hi and lo <= age_max


def describe_children(bands: tuple[str, ...] | list[str]) -> str:
    """Return 'Child 1: 3-5 years; Child 2: 6-9 years' for the prompt, or 'not given'."""
    if not bands:
        return "not given"
    return "; ".join(f"Child {i}: {band} years" for i, band in enumerate(bands, start=1))
