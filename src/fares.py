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

from src import config


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
    """Who travels: adults (15+), the children's ages (0-14) and Deutschlandticket holders."""

    adults: int
    children_ages: tuple[int, ...] = ()
    deutschlandticket_holders: int = 0

    def __post_init__(self) -> None:
        """Reject a party the fare rules cannot describe."""
        low, high = config.TRIP_TRAVELLERS_RANGE
        if not low <= self.adults <= high:
            raise ValueError(f"adults must be between {low} and {high}.")
        if not 0 <= self.deutschlandticket_holders <= self.adults:
            raise ValueError("deutschlandticket_holders must be between 0 and adults.")
        age_low, age_high = config.CHILD_TICKET_AGE_RANGE
        if any(not age_low <= a <= age_high for a in self.children_ages):
            raise ValueError(f"Children's ages must be {age_low}-{age_high}; 15+ count as adults.")
        if len(self.children_ages) > config.MAX_CHILDREN_PER_TRIP:
            raise ValueError(f"At most {config.MAX_CHILDREN_PER_TRIP} children per trip.")

    @property
    def school_age_children(self) -> int:
        """Return how many children are 6-14, the ages that some tickets charge for."""
        return sum(1 for a in self.children_ages if a >= 6)


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
    if wanted in _GERMAN_NAMES:
        return _GERMAN_NAMES[wanted]
    return next((c for c, n in config.GERMAN_STATES.items() if _plain(n) == wanted), None)


def _valid_at(ticket: DayTicket, travel_date: date, departure: time | None) -> bool:
    """Return False when the ticket does not yet run at a weekday departure time."""
    if not ticket.weekday_valid_from or departure is None or travel_date.weekday() >= 5:
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
        raise ValueError("Unknown German state; use a code such as BY, BE or NW.")
    kids = party.school_age_children
    holders = party.deutschlandticket_holders
    others = party.adults - holders
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
        whole = _group_cost(ticket, party.adults, kids)
        if whole:
            persons, price = whole
            options.append(
                TicketOption(
                    label=f"One {ticket.name} for the whole family",
                    total_eur=price,
                    tickets=[f"{ticket.name} for {persons} person(s)"],
                    notes=[ticket.notes] if ticket.notes else [],
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
        "warnings": [
            "Prices cover regional trains only (RE, RB, S-Bahn): no ICE or IC.",
            "Day tickets cover the return trip on the same day.",
            "Check on bahn.de that the whole route stays inside the ticket's area.",
        ],
    }


def parse_ages(text: str) -> tuple[int, ...]:
    """Parse children's ages typed as '4, 8' into a tuple, or raise ValueError."""
    parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    try:
        ages = tuple(int(p) for p in parts)
    except ValueError:
        raise ValueError("Type the ages as whole numbers, separated by commas.") from None
    low, high = config.CHILD_TICKET_AGE_RANGE
    if any(not low <= a <= high for a in ages):
        raise ValueError(f"Children's ages must be {low}-{high}; 15+ count as adults.")
    if len(ages) > config.MAX_CHILDREN_PER_TRIP:
        raise ValueError(f"At most {config.MAX_CHILDREN_PER_TRIP} children per trip.")
    return ages
