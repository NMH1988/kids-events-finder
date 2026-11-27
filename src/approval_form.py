"""The approval panel's form: labelled fields for the live tools' arguments and their checks.

The form shows exactly the arguments the model wrote (no hidden argument, none filled in by
code) and turns the parent's field values back into tool arguments. It never decides what runs:
`decision_problem` and the tool's own schema still check every value on the server.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Literal, get_args

from pydantic import BaseModel, ValidationError

from src import config, privacy_check
from src.tools import registry

FieldKind = Literal["town", "country", "category", "date", "time"]

COUNTRIES: tuple[str, ...] = get_args(registry.Country)
CATEGORIES: tuple[str, ...] = get_args(registry.Category)
# The longest value of a `PlaceName` field in the tool schema; the text field has the same
# limit. `check_place_name` refuses shorter names too (40 characters), with its own message.
PLACE_MAX_CHARS = 60
# The only date and time spellings the form shows; the form sends HH:MM, so ":00" seconds are
# the only seconds it can show unchanged.
_DATE_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIME_TEXT = re.compile(r"\d{2}:\d{2}(?::00)?")
# The train tool's own default departure, used when the model and the parent leave it empty.
DEFAULT_DEPART_AFTER: time = registry.TrainArgs.model_fields["depart_after"].default


@dataclass(frozen=True)
class FormField:
    """One labelled field of the approval form, tied to one tool argument."""

    name: str
    label: str
    kind: FieldKind
    # An optional field left empty sends nothing, so the tool uses its own default.
    optional: bool = False


@dataclass(frozen=True)
class ToolForm:
    """The fields of one tool's form, its argument schema and how far ahead its dates may be."""

    fields: tuple[FormField, ...]
    schema: type[BaseModel]
    max_days_ahead: int | None = None

    def field_names(self) -> set[str]:
        """Return the argument names this form shows."""
        return {f.name for f in self.fields}


_TOWN = FormField("city", "Town or city", "town")
_COUNTRY = FormField("country", "Country", "country")
_FIRST_DAY = FormField("start_date", "First day", "date")
_LAST_DAY = FormField("end_date", "Last day", "date")

FORMS: dict[str, ToolForm] = {
    "find_nearby_places": ToolForm(
        (_TOWN, _COUNTRY, FormField("category", "Type of place", "category")),
        registry.PlacesArgs,
    ),
    "search_family_events": ToolForm(
        (_TOWN, _COUNTRY, _FIRST_DAY, _LAST_DAY),
        registry.EventsArgs,
        config.EVENTS_MAX_DAYS_AHEAD,
    ),
    "get_weather_forecast": ToolForm(
        (_TOWN, _COUNTRY, _FIRST_DAY, _LAST_DAY),
        registry.WeatherArgs,
        config.WEATHER_MAX_DAYS_AHEAD,
    ),
    "find_train_connection": ToolForm(
        (
            FormField("from_city", "From (town)", "town"),
            FormField("to_town", "To (town)", "town"),
            FormField("travel_date", "Travel date", "date"),
            FormField("depart_after", "Leave after", "time", optional=True),
        ),
        registry.TrainArgs,
        config.TRAIN_MAX_DAYS_AHEAD,
    ),
}


def _is_hidden(ch: str) -> bool:
    """Return True for a character that is invisible, moves text or cannot be shown."""
    # C*: control, format (bidi overrides, zero-width), surrogate, private-use and unassigned;
    # Z* other than the plain space: line and paragraph separators, unusual spaces.
    category = unicodedata.category(ch)
    return category[0] == "C" or (category[0] == "Z" and ch != " ")


def visible_text(text: str, keep: str = "") -> str:
    """Return text with control, format, private-use, unassigned and odd spaces escaped."""
    # Blank-looking letters outside these categories (e.g. U+3164) stay as they are; in a town
    # field, `check_place_name` refuses them before anything is sent.
    # json.dumps writes a character above U+FFFF as a surrogate pair, and a lone surrogate as
    # its own escape, so json.loads reads the escape back as the same character.
    return "".join(json.dumps(ch)[1:-1] if _is_hidden(ch) and ch not in keep else ch for ch in text)


def shown_json(args: object) -> str:
    """Return arguments as indented JSON whose hidden characters are escaped."""
    # json.dumps escapes control characters inside strings, but not format characters (bidi
    # overrides, zero-width spaces) or lone surrogates, which could reorder or hide text on the
    # page or break it. The layout's own newlines stay.
    return visible_text(json.dumps(args, indent=2, ensure_ascii=False, default=str), keep="\n")


def _shown_value(kind: FieldKind, value: object) -> tuple[bool, object]:
    """Return whether a model value fits its field unchanged, and the value the field shows."""
    if value is None:
        return True, None
    if kind == "town":
        fits = (
            isinstance(value, str)
            and len(value) <= PLACE_MAX_CHARS
            and not any(_is_hidden(ch) for ch in value)
        )
        return fits, value
    if kind == "country":
        return value in COUNTRIES, value
    if kind == "category":
        return value in CATEGORIES, value
    # Only the plain forms the tool's schema reads are shown: other ISO spellings ("20261127",
    # "2026-W48-5", "0830") would be shown as a value the call does not send.
    if kind == "date":
        if not isinstance(value, str) or not _DATE_TEXT.fullmatch(value):
            return False, None
        try:
            return True, date.fromisoformat(value)
        except ValueError:
            return False, None
    if not isinstance(value, str) or not _TIME_TEXT.fullmatch(value):
        return False, None
    try:
        return True, time.fromisoformat(value)
    except ValueError:
        return False, None


def initial_values(call: dict) -> dict[str, object] | None:
    """Return the form's starting values from the model's arguments, or None for the JSON editor."""
    form = FORMS.get(call.get("name"))
    args = call.get("args")
    # A tool without a form, or an argument the form cannot show, falls back to the JSON editor:
    # every argument the call sends must stay visible.
    if form is None or not isinstance(args, dict) or not set(args) <= form.field_names():
        return None
    values: dict[str, object] = {}
    for field in form.fields:
        fits, shown = _shown_value(field.kind, args.get(field.name))
        if not fits:
            return None
        values[field.name] = shown
    return values


def _date_problems(form: ToolForm, values: dict, today: date) -> list[str]:
    """Return the date limits a tool would refuse, with the same rules as the tool itself."""
    dated = [f for f in form.fields if f.kind == "date"]
    if not dated or any(values.get(f.name) is None for f in dated):
        return []
    first, last = dated[0], dated[-1]
    start, end = values[first.name], values[last.name]
    problems = []
    if start < today:
        problems.append(f"{first.label} is in the past.")
    if end < start:
        problems.append(f"{last.label} is before {first.label.lower()}.")
    if form.max_days_ahead is not None:
        limit = today + timedelta(days=form.max_days_ahead)
        if end > limit:
            problems.append(
                f"Dates can be at most {form.max_days_ahead} days ahead "
                f"(until {limit.isoformat()})."
            )
    return problems


def form_to_args(
    tool: str, values: dict[str, object], today: date | None = None
) -> tuple[dict, list[str]]:
    """Turn the form's field values into tool arguments; return them with any problems found."""
    form = FORMS[tool]
    today = today or date.today()
    args: dict[str, object] = {}
    problems: list[str] = []
    for field in form.fields:
        value = values.get(field.name)
        if field.kind == "town":
            text = (value or "").strip() if isinstance(value, str) else ""
            if not text:
                problems.append(f"Fill in {field.label.lower()}.")
                continue
            try:
                args[field.name] = privacy_check.check_place_name(text)
            except ValueError as exc:
                # The message is the app's own fixed text; it never quotes the value.
                problems.append(f"{field.label}: {exc}")
        elif field.kind in ("country", "category"):
            options = COUNTRIES if field.kind == "country" else CATEGORIES
            if value not in options:
                problems.append(f"Choose {field.label.lower()}.")
            else:
                args[field.name] = value
        elif field.kind == "date":
            if not isinstance(value, date):
                problems.append(f"Pick {field.label.lower()}.")
            else:
                args[field.name] = value.isoformat()
        elif value is None and field.optional:
            continue  # nothing sent: the tool uses its own default
        elif not isinstance(value, time):
            problems.append(f"Pick {field.label.lower()}.")
        else:
            args[field.name] = value.strftime("%H:%M")
    dates = {f.name: values.get(f.name) for f in form.fields if f.kind == "date"}
    if all(isinstance(d, date) for d in dates.values()):
        problems += _date_problems(form, dates, today)
    if not problems:
        try:
            form.schema.model_validate(args)
        except ValidationError:
            problems.append("The tool would not accept these values. Please check them.")
    return args, problems
