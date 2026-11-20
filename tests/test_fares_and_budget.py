"""Tests for the ticket comparison and the budget check (plain arithmetic, no model)."""

from datetime import date, time

import pytest

from src.budget import BudgetItem, check_budget
from src.fares import Party, compare_tickets, load_fares, state_code

SATURDAY = date(2026, 11, 21)
MONDAY = date(2026, 11, 23)


def _cheapest(result: dict) -> dict:
    """Return the cheapest option of a comparison."""
    return result["options"][0]


def test_fares_file_is_valid():
    """Every ticket in the fares file has a source and a check date."""
    fares = load_fares()
    assert fares.day_tickets and all(t.source_url.startswith("https://") for t in fares.day_tickets)


def test_state_names_map_to_codes():
    """English, German and code spellings all give the same state code."""
    assert state_code("Bavaria") == state_code("Bayern") == state_code("by") == "BY"
    assert state_code("Thüringen") == "TH" and state_code("North Rhine-Westphalia") == "NW"
    assert state_code("Atlantis") is None


def test_family_without_deutschlandticket_gets_the_state_ticket():
    """Two adults with children 4 and 8 in Bavaria: Bayern-Ticket for 2, the children ride free."""
    party = Party(adults=2, children_bands=("3-5", "6-9"))
    best = _cheapest(compare_tickets(party, "BY", "BY", SATURDAY))
    assert best["total_eur"] == 44.0 and "Bayern-Ticket" in best["tickets"][0]


def test_children_need_a_ticket_even_when_parents_hold_a_deutschlandticket():
    """Both parents hold a Deutschlandticket: one 1-person Bayern-Ticket takes the children."""
    party = Party(adults=2, children_bands=("6-9", "10-14"), deutschlandticket_holders=2)
    best = _cheapest(compare_tickets(party, "BY", "BY", SATURDAY))
    assert best["total_eur"] == 34.0
    assert best["tickets"][0] == "Deutschlandticket"


def test_everyone_with_a_deutschlandticket_travels_for_free():
    """Holders with only a toddler pay nothing extra."""
    party = Party(adults=2, children_bands=("3-5",), deutschlandticket_holders=2)
    assert _cheapest(compare_tickets(party, "BY", "BY", SATURDAY))["total_eur"] == 0.0


def test_weekday_start_before_nine_skips_tickets_that_start_later():
    """At 8:00 on a Monday the Bayern-Ticket and the Quer-durchs-Land-Ticket are not valid yet."""
    result = compare_tickets(Party(adults=1), "BY", "BY", MONDAY, time(8, 0))
    assert result["options"] == []
    assert any("Bayern-Ticket" in s for s in result["not_valid_at_this_time"])
    weekend = compare_tickets(Party(adults=1), "BY", "BY", SATURDAY, time(8, 0))
    assert _cheapest(weekend)["total_eur"] == 34.0


def test_hessenticket_counts_school_children_as_people():
    """The Hessenticket has one price for up to 5 people, school children included."""
    party = Party(adults=2, children_bands=("6-9", "6-9", "10-14"))
    best = _cheapest(compare_tickets(party, "HE", "HE", SATURDAY))
    assert best["total_eur"] == 43.5
    too_many = compare_tickets(
        Party(adults=3, children_bands=("6-9", "6-9", "10-14")), "HE", "HE", SATURDAY
    )
    assert all("Hessenticket" not in o["label"] for o in too_many["options"])


def test_trip_across_states_falls_back_to_quer_durchs_land():
    """Munich to Frankfurt has no shared state ticket, so only the nationwide one fits."""
    best = _cheapest(compare_tickets(Party(adults=2), "BY", "HE", SATURDAY))
    assert best["total_eur"] == 63.0 and "Quer-durchs-Land" in best["label"]


def test_party_and_ages_are_validated():
    """Impossible parties and unknown age groups are rejected."""
    with pytest.raises(ValueError):
        Party(adults=0)
    with pytest.raises(ValueError):
        Party(adults=1, deutschlandticket_holders=2)
    with pytest.raises(ValueError):
        Party(adults=1, children_bands=("16",))
    with pytest.raises(ValueError):
        Party(adults=1, children_bands=("3-5",) * 7)
    with pytest.raises(ValueError):
        compare_tickets(Party(adults=1), "Atlantis", "BY", SATURDAY)


def test_budget_reports_remaining_and_unknown_costs():
    """Known amounts are added up; missing amounts are listed, not guessed."""
    items = [
        BudgetItem(label="Train", amount_eur=44),
        BudgetItem(label="Zoo entry"),
        BudgetItem(label="Lunch", amount_eur=30.5),
    ]
    result = check_budget(100, items)
    assert result["known_total_eur"] == 74.5 and result["remaining_eur"] == 25.5
    assert result["unknown_items"] == ["Zoo entry"]
    assert result["status"] == "within_budget_so_far"
    assert check_budget(50, items)["status"] == "over_budget"
    with pytest.raises(ValueError):
        check_budget(-1, items)


def test_teenagers_pay_the_adult_fare_and_may_hold_a_deutschlandticket():
    """A 15-17 child counts as a paying traveller and can be one of the ticket holders."""
    party = Party(adults=1, children_bands=("15-17", "6-9"))
    assert party.adult_fare_travellers == 2 and party.school_age_children == 1
    assert _cheapest(compare_tickets(party, "BY", "BY", SATURDAY))["total_eur"] == 44.0
    both = Party(adults=1, children_bands=("15-17",), deutschlandticket_holders=2)
    assert _cheapest(compare_tickets(both, "BY", "BY", SATURDAY))["total_eur"] == 0.0


def test_geocoder_long_state_names_are_recognised():
    """The geocoder's long names for the city-states map to their codes."""
    assert state_code("State of Berlin") == "BE" and state_code("Land Berlin") == "BE"
    assert state_code("Free and Hanseatic City of Hamburg") == "HH"
    assert state_code("Free Hanseatic City of Bremen") == "HB"
    assert state_code("Baden-Wurttemberg") == "BW"


def test_weekday_without_departure_time_spells_out_the_nine_oclock_rule():
    """With no departure time on a weekday, late-starting tickets carry a clear note."""
    best = _cheapest(compare_tickets(Party(adults=1), "BY", "BY", MONDAY))
    assert any("09:00" in note for note in best["notes"])
    weekend = _cheapest(compare_tickets(Party(adults=1), "BY", "BY", SATURDAY))
    assert not any("09:00" in note for note in weekend["notes"])


def test_too_many_paying_travellers_get_a_reason_not_silence():
    """Six paying travellers fit no day ticket, and the result says why."""
    party = Party(adults=2, children_bands=("15-17",) * 4)
    result = compare_tickets(party, "BY", "BY", SATURDAY)
    assert result["options"] == []
    assert "No single day ticket" in result["warnings"][0]


def test_large_party_warning_also_appears_when_tickets_start_later():
    """The too-many-travellers note does not depend on the 9:00 weekday rule."""
    party = Party(adults=2, children_bands=("15-17",) * 4)
    result = compare_tickets(party, "BY", "BY", MONDAY, time(7, 45))
    assert result["options"] == [] and result["not_valid_at_this_time"]
    assert "at most 5 people" in result["warnings"][0]
    assert state_code("Free State of Bavaria") == "BY"
