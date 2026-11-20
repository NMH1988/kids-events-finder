"""Tests for the children's age groups (no names, no exact ages)."""

import pytest

from src.family import band_for_age, check_bands, describe_children, overlaps


def test_age_groups_describe_children_by_position_only():
    """Children appear as Child 1, Child 2 with their age group."""
    assert describe_children(["0-2", "6-9"]) == "Child 1: 0-2 years; Child 2: 6-9 years"
    assert describe_children([]) == "not given"


def test_age_groups_match_place_age_ranges():
    """A place fits an age group when the ranges overlap."""
    assert overlaps("3-5", 4, 12) and overlaps("10-14", 0, 10)
    assert not overlaps("0-2", 6, 14)


def test_unknown_or_too_many_groups_are_rejected():
    """Only the defined groups and at most six children are accepted."""
    with pytest.raises(ValueError):
        check_bands(["4"])
    with pytest.raises(ValueError):
        check_bands(["3-5"] * 7)
    assert band_for_age(4) == "3-5" and band_for_age(15) == "15-17"
