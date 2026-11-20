"""Tests for the privacy check on the parent's free text (LEGAL_COMPLIANCE 1.2-1.4, 2.6)."""

import json

import pytest

from src import config
from src.agent.runner import InputRejected, check_input
from src.privacy_check import check_place_name, explain, find_sensitive


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("My child has ADHD, which places are calm?", "health"),
        ("Mein Sohn hat Autismus", "health"),
        ("Gibt es etwas nach der Ergotherapie?", "health"),
        ("Sie ist krank, etwas Ruhiges bitte", "health"),
        ("he was diagnosed last year", "health"),
        ("Places with wheelchair access", "health"),
        ("Con tôi bị hen suyễn", "health"),
        ("bé bị tự kỷ nhẹ", "health"),
        ("Bé đang ốm", "health"),
        ("write to mia.parent@example.com", "email"),
        ("mia.parent (at) example.com", "email"),
        ("call me on +49 30 1234567", "phone"),
        ("Tel. 030 1234567", "phone"),
        ("My daughter is called Mia", "name"),
        ("unser Sohn heißt Max", "name"),
        ("my son Max loves trains", "name"),
        ("con tên là Na", "name"),
        ("bé Na thích vẽ", "name"),
        ("Ideas for my 7 year old?", "exact_age"),
        ("a 7-year-old and a baby", "exact_age"),
        ("Kind, 7 Jahre alt", "exact_age"),
        ("für einen 4-jährigen", "exact_age"),
        ("bé 6 tuổi", "exact_age"),
        ("our baby is 18 months old", "exact_age"),
        ("aged 9", "exact_age"),
        ("we live at Lindenstraße 12", "address"),
    ],
)
def test_sensitive_text_is_found(text, kind):
    """Health, contact details, names, exact ages and addresses are found."""
    assert kind in {f.kind for f in find_sensitive(text)}


@pytest.mark.parametrize(
    "text",
    [
        "My son loves dinosaurs, where should we go?",
        "Wo kann mein Kind Tiere sehen, auch bei schlechtem Wetter?",
        "Cuối tuần trời mưa, bé thích thí nghiệm khoa học và máy móc",
        "Is there a place called Legoland near Munich?",
        "Day trip by regional train this Saturday, 2026-11-21 at 08:30?",
        "Free things to do with a toddler",
        "Medieval castle for kids",
        "Rainy-day ideas for this weekend?",
        "Somewhere free for a baby and a toddler on a wet day",
        "Trips under 100 EUR for 2 adults and 3 kids",
        "Chuyến đi trong ngày bằng tàu, không quá ngân sách",
        "Potsdamer Platz in Berlin",
    ],
)
def test_ordinary_questions_pass(text):
    """Normal questions about outings are not blocked."""
    assert find_sensitive(text) == []


def test_check_input_blocks_before_any_model_call():
    """The runner's input check rejects sensitive text with a message saying what to remove."""
    with pytest.raises(InputRejected) as exc:
        check_input("My daughter is called Mia and has asthma")
    message = str(exc.value)
    assert "not sent" in message and "health" in message and "a name" in message


def test_explain_lists_each_kind_once():
    """The message names every kind of finding once, with the text found."""
    text = explain(find_sensitive("ADHD and autism, mia@example.com"))
    assert text.count("health or medical information") == 1
    assert '"ADHD"' in text and "e-mail" in text


@pytest.mark.parametrize("name", ["Berlin", "Frankfurt (Oder)", "St. Peter-Ording", "Köln"])
def test_place_names_pass(name):
    """Town names pass unchanged."""
    assert check_place_name(name) == name


@pytest.mark.parametrize(
    "name", ["Berlin; DROP", "Berlin  Mitte", "10115 Berlin", "www.evil.example", "Klinik Nord"]
)
def test_other_text_is_not_a_place_name(name):
    """Anything but a plain town name is rejected."""
    with pytest.raises(ValueError):
        check_place_name(name)


def test_red_team_cases_marked_blocked_are_blocked_and_questions_pass():
    """The evaluation set's 'blocked' red-team cases are stopped; its normal questions are not."""
    data = json.loads(config.EVAL_QUESTIONS_FILE.read_text(encoding="utf-8"))
    for case in data["red_team"]:
        if case["expect"] == "blocked":
            with pytest.raises(InputRejected):
                check_input(case["question"])
        else:
            assert check_input(case["question"])
    for question in data["questions"]:
        assert check_input(question["question"]), question["id"]
        assert "age" not in question and question["age_bands"]
