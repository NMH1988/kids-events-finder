"""Regional train ticket comparison for a family day trip in Germany.

Plain code, not the model, does the arithmetic: the rules (who rides free, how many people a
ticket covers, the 9:00 weekday start) come from `data/fares.json`, which the owner checks by hand.
"""

import json
import unicodedata
from dataclasses import dataclass, field
from datetime import date, time
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from src import config, family
from src.errors import AppInputError


class DayTicket(BaseModel):
    """One day ticket for regional trains, as listed in the fares file."""

    id: str
    name: str
    area: list[str]
    price_first: float = Field(ge=0)
    price_extra: float = Field(ge=0)
    max_persons: int = Field(ge=1, le=5)
    children_6_14_free_max: int = Field(ge=0)
    weekday_valid_from: str | None = None
    notes: str = ""
    source_url: str
    checked_on: date

    def covers(self, *states: str) -> bool:
        """Return True when every state is inside the ticket's area."""
        return "ALL" in self.area or all(s in self.area for s in states)

    def price_for(self, persons: int) -> float:
        """Return the price for a number of paying persons."""
        return round(self.price_first + self.price_extra * (persons - 1), 2)


class DeutschlandTicket(BaseModel):
    """The monthly Deutschlandticket: holders travel for no extra cost on a day trip."""

    name: str
    monthly_price: float
    notes: str
    source_url: str
    checked_on: date


class FareTable(BaseModel):
    """Everything in the fares file."""

    deutschlandticket: DeutschlandTicket
    day_tickets: list[DayTicket]


@dataclass(frozen=True)
class Party:
    """Who travels: adults, children's age groups and 15+ Deutschlandticket holders."""

    adults: int
    children_bands: tuple[str, ...] = ()
    deutschlandticket_holders: int = 0

    def __post_init__(self) -> None:
        """Reject a party the fare rules cannot describe."""
        low, high = config.TRIP_TRAVELLERS_RANGE
        if not low <= self.adults <= high:
            raise ValueError(f"adults must be between {low} and {high}.")
        family.check_bands(self.children_bands)
        if not 0 <= self.deutschlandticket_holders <= self.adult_fare_travellers:
            raise ValueError(
                "deutschlandticket_holders must be between 0 and the number of travellers aged 15+."
            )

    @property
    def adult_fare_travellers(self) -> int:
        """Return how many travellers pay the adult fare (adults plus children aged 15-17)."""
        return self.adults + sum(1 for b in self.children_bands if b in family.ADULT_FARE_BANDS)

    @property
    def school_age_children(self) -> int:
        """Return how many children are 6-14, the ages that some tickets charge for."""
        return sum(1 for b in self.children_bands if b in family.SCHOOL_AGE_BANDS)


@dataclass
class TicketOption:
    """One way for the whole party to travel, with its total cost."""

    label: str
    total_eur: float
    tickets: list[str]
    notes: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    checked_on: str = ""


@lru_cache(maxsize=2)
def load_fares(path: Path = config.FARES_FILE) -> FareTable:
    """Load and validate the fares file."""
    return FareTable.model_validate(json.loads(path.read_text(encoding="utf-8")))


# Official long forms the geocoder uses for some states, e.g. "State of Berlin" or "Free and
# Hanseatic City of Hamburg"; they are removed before matching.
_STATE_PREFIXES = (
    "free state of ",
    "state of ",
    "land ",
    "free and hanseatic city of ",
    "free hanseatic city of ",
    "freie und hansestadt ",
    "freie hansestadt ",
)
# German names of the states whose English names differ (the geocoder answers in English).
_GERMAN_NAMES = {
    "bayern": "BY",
    "hessen": "HE",
    "niedersachsen": "NI",
    "nordrhein-westfalen": "NW",
    "rheinland-pfalz": "RP",
    "sachsen": "SN",
    "sachsen-anhalt": "ST",
    "thuringen": "TH",
}


def _plain(text: str) -> str:
    """Return lower-case text without accents, for matching state names."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return folded.lower().strip()


def state_code(name: str | None) -> str | None:
    """Return the two-letter code of a German state from its English or German name or code."""
    if not name:
        return None
    if name.upper() in config.GERMAN_STATES:
        return name.upper()
    wanted = _plain(name)
    for prefix in _STATE_PREFIXES:
        if wanted.startswith(prefix):
            wanted = wanted.removeprefix(prefix)
            break
    if wanted in _GERMAN_NAMES:
        return _GERMAN_NAMES[wanted]
    return next((c for c, n in config.GERMAN_STATES.items() if _plain(n) == wanted), None)


def _starts_late_on_weekdays(ticket: DayTicket, travel_date: date) -> bool:
    """Return True when the ticket starts later in the day on this (week)day."""
    return bool(ticket.weekday_valid_from) and travel_date.weekday() < 5


def _valid_at(ticket: DayTicket, travel_date: date, departure: time | None) -> bool:
    """Return False when the ticket does not yet run at a weekday departure time."""
    if not _starts_late_on_weekdays(ticket, travel_date) or departure is None:
        return True
    hours, minutes = (int(x) for x in ticket.weekday_valid_from.split(":"))
    return departure >= time(hours, minutes)


def _group_cost(ticket: DayTicket, adults: int, school_kids: int) -> tuple[int, float] | None:
    """Return (paying persons, price) for adults plus school-age children on one ticket."""
    paying = adults + max(0, school_kids - ticket.children_6_14_free_max)
    if paying == 0 or paying > ticket.max_persons:
        return None
    return paying, ticket.price_for(paying)


def compare_tickets(
    party: Party,
    from_state: str,
    to_state: str,
    travel_date: date,
    departure: time | None = None,
    fares: FareTable | None = None,
) -> dict:
    """Return the ways the party can make a return day trip, cheapest first."""
    fares = fares or load_fares()
    states = [state_code(from_state), state_code(to_state)]
    if None in states:
        raise AppInputError("Unknown German state; use a code such as BY, BE or NW.")
    kids = party.school_age_children
    holders = party.deutschlandticket_holders
    paying = party.adult_fare_travellers
    others = paying - holders
    d_ticket = fares.deutschlandticket
    options: list[TicketOption] = []
    skipped: list[str] = []

    if others == 0 and kids == 0:
        options.append(
            TicketOption(
                label="Everyone uses their Deutschlandticket",
                total_eur=0.0,
                tickets=[d_ticket.name],
                notes=["No extra cost. Children under 6 ride free."],
                source_urls=[d_ticket.source_url],
                checked_on=d_ticket.checked_on.isoformat(),
            )
        )

    for ticket in fares.day_tickets:
        if not ticket.covers(*states):
            continue
        if not _valid_at(ticket, travel_date, departure):
            skipped.append(f"{ticket.name}: valid from {ticket.weekday_valid_from} on weekdays")
            continue
        # Without a departure time the 9:00 weekday rule cannot be checked, so it is spelled out.
        time_note = (
            [f"Valid only from {ticket.weekday_valid_from} on this weekday: check the departure."]
            if departure is None and _starts_late_on_weekdays(ticket, travel_date)
            else []
        )
        whole = _group_cost(ticket, paying, kids)
        if whole:
            persons, price = whole
            options.append(
                TicketOption(
                    label=f"One {ticket.name} for the whole family",
                    total_eur=price,
                    tickets=[f"{ticket.name} for {persons} person(s)"],
                    notes=[*time_note, *([ticket.notes] if ticket.notes else [])],
                    source_urls=[ticket.source_url],
                    checked_on=ticket.checked_on.isoformat(),
                )
            )
        if holders and (others or kids):
            # Holders keep their Deutschlandticket; one day ticket covers everyone else. When only
            # children need a ticket, one holder buys a 1-person ticket and takes them along.
            mixed = _group_cost(ticket, others or 1, kids)
            if mixed and (not whole or mixed[1] < whole[1]):
                persons, price = mixed
                options.append(
                    TicketOption(
                        label=f"Deutschlandticket for holders + {ticket.name} for the rest",
                        total_eur=price,
                        tickets=[d_ticket.name, f"{ticket.name} for {persons} person(s)"],
                        notes=[
                            *time_note,
                            "Children who ride free must travel with the person named on the "
                            "day ticket.",
                            *([ticket.notes] if ticket.notes else []),
                        ],
                        source_urls=[d_ticket.source_url, ticket.source_url],
                        checked_on=ticket.checked_on.isoformat(),
                    )
                )

    options.sort(key=lambda o: o.total_eur)
    return {
        "source": "Fare rules copied from bahn.de; check the official page before buying.",
        "from_state": states[0],
        "to_state": states[1],
        "travel_date": travel_date.isoformat(),
        "options": [vars(o) for o in options],
        "not_valid_at_this_time": skipped,
        "warnings": _warnings(fares, states, party),
    }


def _group_fits(fares: FareTable, states: list[str], party: Party) -> bool:
    """Return True when the party fits one option at any time of day (group size only)."""
    holders, kids = party.deutschlandticket_holders, party.school_age_children
    others = party.adult_fare_travellers - holders
    if others == 0 and kids == 0:
        return True
    return any(
        _group_cost(t, party.adult_fare_travellers, kids)
        or (holders and _group_cost(t, others or 1, kids))
        for t in fares.day_tickets
        if t.covers(*states)
    )


def _warnings(fares: FareTable, states: list[str], party: Party) -> list[str]:
    """Return the fixed warnings, plus a note when the group is too large for any day ticket."""
    warnings = [
        "Prices cover regional trains only (RE, RB, S-Bahn): no ICE or IC.",
        "Day tickets cover the return trip on the same day.",
        "Check on bahn.de that the whole route stays inside the ticket's area.",
    ]
    if not _group_fits(fares, states, party):
        most = max(t.max_persons for t in fares.day_tickets)
        warnings.insert(
            0,
            "No single day ticket covers this many paying travellers (day tickets take at most "
            f"{most} people): split the group over two tickets or check bahn.de.",
        )
    return warnings
