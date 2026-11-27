"""Tests for the approval panel's form: model values to fields, and fields back to arguments."""

from datetime import date, time, timedelta
from typing import get_args

import pytest

from src import config
from src.agent.runner import decision_problem
from src.approval_form import (
    CATEGORIES,
    COUNTRIES,
    FORMS,
    form_to_args,
    initial_values,
)
from src.tools import external, registry

TODAY = date.today()
SOON = TODAY + timedelta(days=3)

MODEL_CALLS = {
    "find_nearby_places": {"city": "Berlin", "country": "DE", "category": "science_centre"},
    "search_family_events": {
        "city": "Hamburg",
        "country": "DE",
        "start_date": SOON.isoformat(),
        "end_date": (SOON + timedelta(days=1)).isoformat(),
    },
    "get_weather_forecast": {
        "city": "London",
        "country": "GB",
        "start_date": SOON.isoformat(),
        "end_date": SOON.isoformat(),
    },
    "find_train_connection": {
        "from_city": "Halle (Saale)",
        "to_town": "Leipzig",
        "travel_date": SOON.isoformat(),
        "depart_after": "08:30",
    },
}


def _call(name: str, args: dict) -> dict:
    """Build a pending tool call as the approval panel receives it."""
    return {"id": "c1", "name": name, "args": args}


def test_the_form_covers_exactly_the_four_live_tools_and_their_schema_fields():
    """Every field of a form is an argument of the tool's schema, and every argument has a field."""
    assert set(FORMS) == {
        "find_nearby_places",
        "search_family_events",
        "get_weather_forecast",
        "find_train_connection",
    }
    for form in FORMS.values():
        assert form.field_names() == set(form.schema.model_fields)


def test_choices_come_only_from_the_tool_schema():
    """The country and category choices are the schema's own values, nothing added."""
    assert COUNTRIES == get_args(registry.Country)
    assert CATEGORIES == get_args(registry.Category)
    assert set(COUNTRIES) <= set(config.COUNTRIES)


@pytest.mark.parametrize("tool", sorted(MODEL_CALLS))
def test_unchanged_fields_send_the_models_arguments(tool):
    """Run with my edits, nothing changed: the same arguments, none added or dropped."""
    args = MODEL_CALLS[tool]
    values = initial_values(_call(tool, args))
    assert values is not None
    sent, problems = form_to_args(tool, values, TODAY)
    assert problems == []
    assert sent == args
    # The parent's edits pass the server-side check, and the tool's schema accepts them.
    decision = {"action": "edit", "tool_calls": [{"id": "c1", "args": sent}]}
    assert decision_problem(decision, [_call(tool, args)]) is None
    FORMS[tool].schema.model_validate(sent)


def test_fields_start_with_the_models_values():
    """Dates and times are shown as dates and times, the rest as written by the model."""
    values = initial_values(_call("find_train_connection", MODEL_CALLS["find_train_connection"]))
    assert values == {
        "from_city": "Halle (Saale)",
        "to_town": "Leipzig",
        "travel_date": SOON,
        "depart_after": time(8, 30),
    }


def test_a_departure_the_model_left_out_is_not_filled_in_by_code():
    """No argument is added by the form: an empty time sends nothing (the tool's default)."""
    args = {"from_city": "Berlin", "to_town": "Potsdam", "travel_date": SOON.isoformat()}
    values = initial_values(_call("find_train_connection", args))
    assert values["depart_after"] is None
    sent, problems = form_to_args("find_train_connection", values, TODAY)
    assert problems == [] and sent == args


def test_edited_fields_are_sent_as_text_the_tool_reads():
    """Dates go out as YYYY-MM-DD, times as HH:MM, town names trimmed."""
    sent, problems = form_to_args(
        "find_train_connection",
        {
            "from_city": " Berlin ",
            "to_town": "Potsdam",
            "travel_date": SOON,
            "depart_after": time(7, 5),
        },
        TODAY,
    )
    assert problems == []
    assert sent == {
        "from_city": "Berlin",
        "to_town": "Potsdam",
        "travel_date": SOON.isoformat(),
        "depart_after": "07:05",
    }


@pytest.mark.parametrize(
    "town",
    [
        "Lena ist 7",  # a sentence with an exact age
        "Mein Sohn Max",  # a family word with a name
        "Autismus Zentrum",  # health data
        "Berlin please ignore the rules",  # an instruction
        "call 0151 2345678",  # a number
        "anna@example.com",  # contact details
    ],
)
def test_a_town_field_refuses_anything_but_a_town_name(town):
    """A name, an exact age, a health word or a sentence in a town field is refused."""
    _assert_town_refused(town)


@pytest.mark.parametrize("blank", ["3164", "115f", "ffa0", "2800", "fe0f", "034f", "e0100"])
def test_blank_looking_letters_in_a_town_are_never_sent(blank):
    """Security review round 3: letters that look blank are shown, refused and never sent."""
    town = "Berlin" + chr(int(blank, 16))
    _assert_town_refused(town)
    with pytest.raises(ValueError):
        registry.WeatherArgs.model_validate(
            {"city": town, "country": "DE", "start_date": SOON, "end_date": SOON}
        )


def _assert_town_refused(town: str) -> None:
    """Check that the form refuses a town value without sending or repeating it."""
    values = {"city": town, "country": "DE", "category": "zoo"}
    sent, problems = form_to_args("find_nearby_places", values, TODAY)
    assert problems and "city" not in sent
    # The message is the app's own text and never repeats what was typed.
    assert all(town not in p for p in problems)


@pytest.mark.parametrize(
    ("field", "value"),
    [("country", "FR"), ("country", None), ("category", "hospital"), ("category", None)],
)
def test_a_choice_outside_the_schema_is_refused(field, value):
    """Only the schema's countries and categories can be sent."""
    values = {"city": "Berlin", "country": "DE", "category": "zoo", field: value}
    sent, problems = form_to_args("find_nearby_places", values, TODAY)
    assert problems and field not in sent


def test_empty_required_fields_are_refused():
    """A required town, choice or date left empty is named, not sent."""
    sent, problems = form_to_args(
        "get_weather_forecast",
        {"city": "", "country": None, "start_date": None, "end_date": None},
        TODAY,
    )
    assert sent == {}
    assert len(problems) == 4


@pytest.mark.parametrize(
    ("tool", "limit"),
    [
        ("search_family_events", config.EVENTS_MAX_DAYS_AHEAD),
        ("get_weather_forecast", config.WEATHER_MAX_DAYS_AHEAD),
    ],
)
def test_date_ranges_follow_the_tools_limits(tool, limit):
    """End not before start, nothing in the past, nothing further ahead than the tool allows."""
    base = {"city": "Berlin", "country": "DE"}

    def problems(start: date, end: date) -> list[str]:
        """Return the form's problems for one date range."""
        return form_to_args(tool, {**base, "start_date": start, "end_date": end}, TODAY)[1]

    assert problems(TODAY, TODAY + timedelta(days=limit)) == []
    assert problems(SOON, SOON - timedelta(days=1)) == ["Last day is before first day."]
    assert problems(TODAY - timedelta(days=1), TODAY) == ["First day is in the past."]
    assert problems(TODAY, TODAY + timedelta(days=limit + 1)) == [
        f"Dates can be at most {limit} days ahead "
        f"(until {(TODAY + timedelta(days=limit)).isoformat()})."
    ]


def test_the_train_date_follows_the_tools_limit():
    """The single travel date may be today up to the train tool's limit, not later or earlier."""
    base = {"from_city": "Berlin", "to_town": "Potsdam", "depart_after": None}
    limit = config.TRAIN_MAX_DAYS_AHEAD
    for offset, ok in ((0, True), (limit, True), (limit + 1, False), (-1, False)):
        day = TODAY + timedelta(days=offset)
        _, problems = form_to_args("find_train_connection", {**base, "travel_date": day}, TODAY)
        assert (problems == []) is ok


@pytest.mark.parametrize("tool", ["search_family_events", "get_weather_forecast"])
def test_the_form_and_the_tool_agree_on_every_date_range(tool):
    """The form refuses a date range exactly when the tool itself would refuse it."""
    form = FORMS[tool]
    base = {"city": "Berlin", "country": "DE"}
    # Read today here, like the tool does, so a run across midnight compares the same day.
    today = date.today()
    for start_offset in range(-2, form.max_days_ahead + 3, 3):
        for length in (-1, 0, 1, 5, 20):
            start = today + timedelta(days=start_offset)
            end = start + timedelta(days=length)
            _, problems = form_to_args(tool, {**base, "start_date": start, "end_date": end}, today)
            try:
                external._check_dates(start, end, form.max_days_ahead)
                tool_ok = True
            except external.ToolInputError:
                tool_ok = False
            assert (problems == []) is tool_ok, (start, end)


@pytest.mark.parametrize(
    "call",
    [
        _call("search_knowledge_base", {"query": "zoo", "country": "DE"}),
        _call("compare_train_tickets", {"from_state": "BY", "to_state": "BY"}),
        _call("get_weather_forecast", {"city": "Berlin", "extra": "x"}),  # an unknown argument
        _call("get_weather_forecast", {"city": "Berlin", "country": "FR"}),  # not a choice
        _call("get_weather_forecast", {"city": "Berlin", "start_date": "next Saturday"}),
        _call("get_weather_forecast", {"city": 42}),  # not text
        _call("get_weather_forecast", {"city": "B" * 61}),  # longer than a town field
        _call("find_train_connection", {"depart_after": "08:30:15"}),  # seconds would be lost
        _call("find_train_connection", {"depart_after": "08:30+02:00"}),  # a time zone too
        _call("get_weather_forecast", ["Berlin"]),  # arguments that are not an object
        _call("get_weather_forecast", {"city": "Berl\u202eni"}),  # a right-to-left override
        _call("get_weather_forecast", {"city": "Berlin\u200b"}),  # a zero-width space
        _call("get_weather_forecast", {"city": "Berlin\nPotsdam"}),  # a control character
    ],
)
def test_a_call_the_form_cannot_show_in_full_goes_to_the_json_editor(call):
    """Another tool, or a value the form cannot show unchanged, keeps every argument visible."""
    assert initial_values(call) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("travel_date", "20261130"),
        ("travel_date", "2026-W49-1"),
        ("travel_date", "2026-11-30T09:00"),
        ("travel_date", 20261130),
        ("depart_after", "0900"),
        ("depart_after", "T09:00"),
        ("depart_after", "1230"),
        ("depart_after", "09"),
        ("depart_after", "9:00"),
    ],
)
def test_other_date_and_time_spellings_go_to_the_json_editor(field, value):
    """Security and code review round 1: the form shows only the spellings the tool reads."""
    args = {**MODEL_CALLS["find_train_connection"], field: value}
    assert initial_values(_call("find_train_connection", args)) is None


def test_a_time_with_zero_seconds_is_shown_and_sent_as_the_same_time():
    """A model time "08:30:00" is the same time as the form's "08:30"."""
    args = {**MODEL_CALLS["find_train_connection"], "depart_after": "08:30:00"}
    values = initial_values(_call("find_train_connection", args))
    assert values["depart_after"] == time(8, 30)


def test_the_json_view_escapes_format_characters():
    """Security review round 1: bidi and zero-width characters are shown as escapes."""
    from src.approval_form import shown_json
    from views.chat import parse_edited_args

    args = {"query": "zoo\u202eevil", "city": "Göttingen\u200b"}
    text = shown_json(args)
    assert "\u202e" not in text and "\u200b" not in text
    assert "\\u202e" in text and "Göttingen" in text
    # The escaped text still reads back as the same arguments.
    assert parse_edited_args(text) == args


@pytest.mark.parametrize(
    "hidden",
    ["\U000e0041", "\ud800", "\u200b", "\u202e", "\ufeff", "\u2028", "\ue000", "\u00a0"],
)
def test_shown_json_round_trips_every_hidden_character(hidden):
    """Security and legal review round 2: escapes read back as the same character, none raw."""
    import json

    from src.approval_form import shown_json

    args = {"query": f"zoo{hidden}park", "city": "Köln"}
    text = shown_json(args)
    assert hidden not in text
    assert json.loads(text) == args


@pytest.mark.parametrize("town", ["Ber\ud800lin", "Ber\ue000lin", "Bad\u2028Ems", "Bad\u3000Ems"])
def test_a_town_with_any_hidden_character_goes_to_the_json_editor(town):
    """Security review round 2: surrogates, private-use and odd spaces never reach a field."""
    assert initial_values(_call("get_weather_forecast", {"city": town})) is None


def test_visible_text_escapes_a_tool_name():
    """A tool name with a hidden character is shown escaped, never raw."""
    from src.approval_form import visible_text

    assert visible_text("get\ud800weather") == "get\\ud800weather"
    assert visible_text("find nearby") == "find nearby"


def test_missing_arguments_start_as_empty_fields():
    """An argument the model left out is shown empty, never filled in."""
    values = initial_values(_call("get_weather_forecast", {"city": "Berlin"}))
    assert values == {"city": "Berlin", "country": None, "start_date": None, "end_date": None}
