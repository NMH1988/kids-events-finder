"""Privacy check on free text before it leaves the app (LEGAL_COMPLIANCE 1.2-1.4, 2.6).

The app never handles a child's health, name or exact age, or a family's contact details. Text the
parent types (chat messages, budget notes, a reason for rejecting a step, edited values) is checked
here first; when something is found, nothing is sent and the parent is asked to remove that part.

Matching runs on normalised copies of the text (the original is sent unchanged): compatibility
forms folded (fullwidth letters, digits and "@"), invisible characters removed, Cyrillic and Greek
look-alikes mapped to Latin, letters written one by one ("a.d.h.d") joined, and a copy without
accents, so decomposed or accent-free Vietnamese ("benh", "tu ky") is caught too.

The lists err on the side of asking: a false alarm costs the parent one edit, a miss would send
health data to the AI model. They are a basic safeguard, not proof (to be re-checked with a
Datenschutzberater). Place names that tools send to outside services use `check_place_name`.
"""

import re
import unicodedata
from dataclasses import dataclass

# Health, illness, disability, diagnosis and therapy words in English, German and Vietnamese.
# "word" matches the whole word; "stem*" also longer words (diagnos* -> diagnosis, Diagnose);
# "~stem*" also inside words, for German compounds (~therap* -> Physiotherapie, Ergotherapie).
HEALTH_TERMS: tuple[str, ...] = (
    # English
    "adhd",
    "autis*",
    "asperger*",
    "diagnos*",
    "disabilit*",
    "disabled",
    "handicap*",
    "is ill",
    "are ill",
    "fell ill",
    "illness*",
    "is sick",
    "are sick",
    "sickness",
    "disease*",
    "therap*",
    "medic*",
    "allerg*",
    "asthma*",
    "epilep*",
    "diabet*",
    "dyslex*",
    "down syndrome",
    "cerebral palsy",
    "wheelchair*",
    "speech delay*",
    "developmental delay*",
    "hyperactiv*",
    "anxiety",
    "depress*",
    "special needs",
    "hospital",
    "hospitals",
    "hospitalised",
    "hospitalized",
    "pregnan*",
    "seizure*",
    "mental health",
    "blind",
    "deaf",
    "cancer",
    "psychiatr*",
    "psycholog*",
    "eczema",
    "hearing aid*",
    # German (compounds: matched inside words)
    "adhs",
    "~therap*",
    "~krank*",
    "~behinder*",
    "~logopäd*",
    "~frühförder*",
    "förderbedarf",
    "~medikament*",
    "~allergi*",
    "~legasthen*",
    "~rollstuhl*",
    "~entwicklungsverzög*",
    "~schwanger*",
    "~angststörung*",
    "~arzt",
    "~ärzt*",
    "~klinik*",
    "~syndrom*",
    "~hörgerät*",
    "~gehörlos*",
    "~neurodermitis",
    "~diagnose*",
    "~psychiat*",
    "~epilepsie",
    "taub",
    # Vietnamese (also matched without accents, except the words in `_ACCENT_ONLY`)
    "bệnh",
    "hen suyễn",
    "tự kỷ",
    "tăng động",
    "khuyết tật",
    "chẩn đoán",
    "trị liệu",
    "dị ứng",
    "động kinh",
    "tiểu đường",
    "chậm phát triển",
    "chậm nói",
    "xe lăn",
    "trầm cảm",
    "uống thuốc",
    "mang thai",
    "ốm",
    "khiếm thính",
    "khiếm thị",
)
# Without accents these are other common words ("ôm" hug), so they match only with accents.
_ACCENT_ONLY = frozenset({"ốm"})

# Cyrillic and Greek letters that look like Latin ones.
_LOOKALIKES = str.maketrans(
    "АВЕКМНОРСТХаеорсухіІјѕԁΑΒΕΖΗΙΚΜΝΟΡΤΥΧαοιν",
    "ABEKMHOPCTXaeopcyxiIjsdABEZHIKMNOPTYXaoiv",
)
_SPACED_LETTERS = re.compile(r"(?<!\w)(?:[^\W\d_][ .]){2,}[^\W\d_](?!\w)")


def _soft(text: str) -> str:
    """Return the text with compatibility forms folded, invisibles removed, look-alikes mapped."""
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return unicodedata.normalize("NFC", text.translate(_LOOKALIKES))


def _strip_accents(text: str) -> str:
    """Return the text without accents (Vietnamese đ becomes d)."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _join_spaced(text: str) -> str:
    """Join letters written one by one ("a d h d", "A.D.H.D") into one word."""
    return _SPACED_LETTERS.sub(lambda m: re.sub(r"[ .]", "", m.group(0)), text)


def _term_pattern(term: str) -> str:
    """Return a regex for one term (see `HEALTH_TERMS` for the markers)."""
    inside = term.startswith("~")
    stem = term.removeprefix("~").removesuffix("*")
    body = r"\s*".join(re.escape(part) for part in stem.split())
    start = "" if inside else r"(?<!\w)"
    end = "" if term.endswith("*") else r"(?!\w)"
    return start + body + end


_HEALTH = re.compile("|".join(_term_pattern(t) for t in HEALTH_TERMS))
_HEALTH_PLAIN = re.compile(
    "|".join(
        _term_pattern(_strip_accents(t))
        for t in HEALTH_TERMS
        if t.removeprefix("~").removesuffix("*") not in _ACCENT_ONLY
    )
)
_EMAIL = re.compile(r"[\w.+-]+\s*(?:@|\(at\)|\[at\])\s*[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
# International (+49 ..., 0049 ...) or national (030 1234567, 030 123 45 67) phone numbers; a
# candidate counts only with 7-15 digits, so dates and times do not.
_PHONE = re.compile(
    r"(?<![\w+])(?:\+|00)[1-9][\d \t/().-]{5,20}\d(?!\w)"
    r"|(?<![\w.:-])0\d{2,5}(?:[ /-]?\d{2,10}){1,4}(?![\w:-])"
)
_WEEKDAYS_MONTHS = (
    "monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|january|february|march|"
    "april|may|june|july|august|september|october|november|december|montag|dienstag|mittwoch|"
    "donnerstag|freitag|samstag|sonntag|wochenende|januar|februar|märz|juni|juli|oktober|dezember"
)
_CAPITAL_WORD = rf"(?!(?i:{_WEEKDAYS_MONTHS})(?!\w))[A-ZÀ-ÖØ-ÞĐ][^\W\d_]+"
# A person's name: "my daughter is called Mia", "unser Sohn heißt Max", "con tên là Na",
# "my son Max", "meine Tochter Lena mag ...", "bé Na", "my son's name is max", "Mia (5)".
# "A place called Legoland" or "my kid Saturday" is not a name of a person.
_CHILD_WORDS = r"son|daughter|child|kid|boy|girl|baby|sohn|tochter|kind|junge|mädchen|con|bé|cháu"
_GERMAN_VERB_AFTER_NAME = r"(?=\s*(?:,|\(|$|\s+(?:mag|will|kann|ist|hat|wird|darf|möchte|\w+t)\b))"
_NAME = re.compile(
    rf"(?<!\w)(?:(?i:{_CHILD_WORDS})\s+(?:(?i:is|ist)\s+)?"
    r"(?i:named|called|heißt|heisst|namens|tên là|tên)\s+[^\W\d_]+"
    rf"|(?i:{_CHILD_WORDS})'s\s+(?i:name)\s+(?i:is)\s+[^\W\d_]+"
    rf"|(?i:my|our)\s+(?i:son|daughter|child|kid|boy|girl|baby)\s+{_CAPITAL_WORD}"
    rf"|(?i:mein|meine|meinen|unser|unsere|unseren)\s+(?i:sohn|tochter|kind|junge|kleine[rn]?)\s+"
    rf"{_CAPITAL_WORD}{_GERMAN_VERB_AFTER_NAME}"
    r"|(?i:my name is|ich heiße|ich heisse|tôi tên là|tôi tên)\s+[^\W\d_]+"
    rf"|(?i:bé|cháu|con tôi)\s+{_CAPITAL_WORD}"
    rf"|{_CAPITAL_WORD}\s*\(\s*\d{{1,2}}\s*\))"
)
_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    "sixteen|seventeen"
)
_NOT_A_RANGE = r"(?<!\d[-–])(?<!\d [-–] )(?<!\d[-–] )(?<!\d [-–])"
_NO_RANGE_AFTER = r"(?!\s*[-–]\s*\d)"
_UNITS = r"(?!\s*(?:km|m|h|min|minutes?|hours?|stunden|std|uhr|euro|eur|€|%|miles?|[.:,]\d))"
# An exact age: "7 years old", "aged 7", "7-jährig", "7 Jahre alt", "7 tuổi", "18 months old",
# "seven years old", "7yo", "turns 7", "Lena is 7", "Leon, 6,". Age groups ("6-9", "3-5 tuổi")
# and time spans ("in 2 Monaten") are not exact ages.
_AGE = re.compile(
    rf"{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:years?|yrs?|months?)[\s-]*old(?!\w)"
    rf"|(?<!\w)(?:{_NUMBER_WORDS})[\s-]*(?:years?|months?)[\s-]*old(?!\w)"
    rf"|(?<!\w)aged?\s+\d{{1,2}}{_NO_RANGE_AFTER}(?!\w)"
    rf"|(?<!\w)\d{{1,2}}\s*(?:yo|y/o)(?!\w)"
    rf"|(?<!\w)turns?\s+\d{{1,2}}{_UNITS}(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:jahre|monate)\s+alt(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:jährig\w*|monatig\w*)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*(?:tháng\s+)?tuổi(?!\w)"
    rf"|(?:(?:{_CHILD_WORDS})|(?-i:{_CAPITAL_WORD}))\s+(?:is|ist|wird|turns|lên)\s+\d{{1,2}}"
    rf"{_NO_RANGE_AFTER}{_UNITS}(?!\w)"
    rf"|(?-i:{_CAPITAL_WORD}),\s*\d{{1,2}}\s*,",
    re.IGNORECASE,
)
# A street address: "Musterstraße 12", "Lindenweg 3a"; "Rückweg 2 Stunden" is a time.
_ADDRESS = re.compile(
    r"(?<!\w)[^\W\d_]+(?:straße|strasse|str\.|weg|allee|gasse|street|road|avenue)\s+\d{1,4}[a-z]?"
    rf"(?!\w){_UNITS}",
    re.IGNORECASE,
)

_DESCRIPTIONS = {
    "health": "health or medical information",
    "email": "an e-mail address",
    "phone": "a phone number",
    "name": "a name",
    "exact_age": "an exact age (choose the age group in the sidebar instead)",
    "address": "a street address",
}


@dataclass(frozen=True)
class Finding:
    """One piece of sensitive text: its kind and the text found (never shown or stored)."""

    kind: str
    text: str

    @property
    def description(self) -> str:
        """Return what kind of data this is, in words for the parent."""
        return _DESCRIPTIONS[self.kind]


def _phones(text: str) -> list[str]:
    """Return phone-number candidates that have a phone number's count of digits."""
    found = []
    for match in _PHONE.finditer(text):
        digits = sum(ch.isdigit() for ch in match.group(0))
        if 7 <= digits <= 15:
            found.append(match.group(0).strip())
    return found


def find_sensitive(text: str) -> list[Finding]:
    """Return the sensitive parts of a text (health, contact details, names, exact ages)."""
    soft = _join_spaced(_soft(text))
    folded = soft.casefold()
    plain = _strip_accents(folded)
    findings = [Finding("health", m.group(0)) for m in _HEALTH.finditer(folded)]
    if not findings:
        findings = [Finding("health", m.group(0)) for m in _HEALTH_PLAIN.finditer(plain)]
    findings += [Finding("email", m.group(0)) for m in _EMAIL.finditer(soft)]
    findings += [Finding("phone", p) for p in _phones(soft)]
    findings += [Finding("name", m.group(0)) for m in _NAME.finditer(soft)]
    findings += [Finding("exact_age", m.group(0)) for m in _AGE.finditer(soft)]
    findings += [Finding("address", m.group(0)) for m in _ADDRESS.finditer(soft)]
    return findings


def explain(findings: list[Finding]) -> str:
    """Return a message naming what kind of data to remove (the text itself is not repeated)."""
    kinds = ", ".join(dict.fromkeys(f.description for f in findings))
    return (
        f"For your family's privacy this was not sent. It seems to contain {kinds}, which the app "
        "does not handle. Please remove that part and try again. Children are described only by "
        "their age group in the sidebar."
    )


def string_values(value: object) -> list[str]:
    """Return every string inside a JSON-like value (dict values, list items)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in string_values(v)]
    if isinstance(value, list):
        return [s for v in value for s in string_values(v)]
    return []


# Small words that place names keep in lower case ("Frankfurt am Main", "Stratford-upon-Avon").
_PLACE_CONNECTORS = frozenset(
    {
        "am",
        "an",
        "der",
        "die",
        "das",
        "den",
        "dem",
        "im",
        "in",
        "ob",
        "vor",
        "bei",
        "upon",
        "on",
        "of",
        "the",
        "la",
        "le",
        "de",
        "sur",
        "en",
    }
)
_PLACE_MAX_WORDS = 5
_PLACE_MAX_CHARS = 40


def _latin_letter(ch: str) -> bool:
    """Return True for a Latin letter (ASCII, accented Latin, Vietnamese)."""
    return (
        ch.isalpha() and (ch.isascii() or "À" <= ch <= "ɏ" or "Ḁ" <= ch <= "ỿ") and ch not in "×÷"
    )


def check_place_name(value: str) -> str:
    """Return a town or city name unchanged, or raise ValueError for anything else."""
    value = value.strip()
    error = ValueError(
        "Use a town or city name only (up to 5 capitalised words, letters, . ' - and brackets)."
    )
    if value != unicodedata.normalize("NFKC", value) or len(value) > _PLACE_MAX_CHARS:
        raise error
    if not all(_latin_letter(ch) or ch in " .'’()-" for ch in value) or "  " in value:
        raise error
    words = value.split(" ")
    if not words or len(words) > _PLACE_MAX_WORDS or not _latin_letter(value[0]):
        raise error
    for word in words:
        bare = word.strip("()")
        if not bare or (not bare[0].isupper() and bare not in _PLACE_CONNECTORS):
            raise error
    # A dot followed by two letters (evil.example) is a domain; "St. Peter", "D.C." are not.
    if re.search(r"\.[^\W\d_]{2}", value) or find_sensitive(value):
        raise error
    return value
