"""Privacy check on free text before it leaves the app (LEGAL_COMPLIANCE 1.2-1.4, 2.6).

The app never handles a child's health, name or exact age, or a family's contact details. Text the
parent types (chat messages, budget notes, a reason for rejecting a step) is checked here first;
when something is found, nothing is sent and the parent is asked to remove that part.

The lists are deliberately simple and err on the side of asking: a false alarm costs the parent one
edit, a miss would send health data to the AI model. Place names that tools send to outside services
are checked with `check_place_name`.
"""

import re
from dataclasses import dataclass

# Health, illness, disability, diagnosis and therapy words in English, German and Vietnamese.
# A term ending in "*" also matches longer words (diagnos* -> diagnosis, Diagnose, diagnosed).
HEALTH_TERMS: tuple[str, ...] = (
    # English
    "adhd",
    "autis*",
    "asperger*",
    "diagnos*",
    "disabilit*",
    "disabled",
    "handicap*",
    "illness*",
    "sick*",
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
    "hospital*",
    "pregnan*",
    "seizure*",
    "mental health",
    # German
    "adhs",
    "krank*",
    "behinder*",
    "logopäd*",
    "ergotherap*",
    "frühförder*",
    "förderbedarf",
    "medikament*",
    "allergi*",
    "legasthen*",
    "rollstuhl*",
    "entwicklungsverzög*",
    "schwanger*",
    "angststörung*",
    "arzt",
    "ärzt*",
    "kinderarzt*",
    "klinik*",
    # Vietnamese
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
)


def _term_pattern(term: str) -> str:
    """Return a regex for one term: whole word, or a word start when it ends in '*'."""
    stem = term.removesuffix("*")
    body = r"\s+".join(re.escape(part) for part in stem.split())
    return rf"(?<!\w){body}" + ("" if term.endswith("*") else r"(?!\w)")


_HEALTH = re.compile("|".join(_term_pattern(t) for t in HEALTH_TERMS), re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+\s*(?:@|\(at\)|\[at\])\s*[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
# International (+49 ..., 0049 ...) or national (030 1234567) phone numbers; dates and times have
# separators these patterns do not allow.
_PHONE = re.compile(
    r"(?<![\w+])(?:\+|00)[1-9][\d \t/().-]{6,18}\d(?!\w)"
    r"|(?<![\w.:-])0\d{2,5}[ /-]?\d{4,10}(?![\w:-])"
)
# A person's name: "my daughter is called Mia", "unser Sohn heißt Max", "con tên là Na",
# "my son Max", "bé Na", "my name is ...". "A place called Legoland" is not a name of a person.
_CHILD_WORDS = r"son|daughter|child|kid|boy|girl|baby|sohn|tochter|kind|junge|mädchen|con|bé|cháu"
_NAME = re.compile(
    rf"(?<!\w)(?:(?i:{_CHILD_WORDS})\s+(?:(?i:is|ist)\s+)?"
    r"(?i:named|called|heißt|heisst|namens|tên là|tên)\s+"
    r"|(?i:my|our)\s+(?i:son|daughter|child|kid|boy|girl|baby)\s+"
    r"|(?i:my name is|ich heiße|ich heisse|tôi tên là|tôi tên)\s+"
    r"|(?i:bé|cháu)\s+)"
    r"[A-ZÀ-ÖØ-ÞĐ][^\W\d_]+"
)
# An exact age: "7 years old", "aged 7", "7-jährig", "7 Jahre", "7 tuổi", "18 months old".
_AGE = re.compile(
    r"(?<!\w)\d{1,2}\s*-?\s*(?:years?|yrs?|months?)[\s-]*old(?!\w)"
    r"|(?<!\w)aged?\s+\d{1,2}(?!\w)"
    r"|(?<!\w)\d{1,2}\s*-?\s*(?:jahre|jahren|jährig\w*|monate\w*)(?!\w)"
    r"|(?<!\w)\d{1,2}\s*(?:tháng\s+)?tuổi(?!\w)",
    re.IGNORECASE,
)
# A street address: "Musterstraße 12", "Lindenweg 3a".
_ADDRESS = re.compile(
    r"(?<!\w)[^\W\d_]+(?:straße|strasse|str\.|weg|allee|gasse|street|road|avenue)\s+\d{1,4}[a-z]?(?!\w)",
    re.IGNORECASE,
)

_KINDS: tuple[tuple[str, re.Pattern, str], ...] = (
    ("health", _HEALTH, "health or medical information"),
    ("email", _EMAIL, "an e-mail address"),
    ("phone", _PHONE, "a phone number"),
    ("name", _NAME, "a name"),
    ("exact_age", _AGE, "an exact age (choose the age group in the sidebar instead)"),
    ("address", _ADDRESS, "a street address"),
)

# A town or city name: letters, spaces and . ' ’ - ( ), e.g. "Frankfurt (Oder)", "St. Peter-Ording".
_PLACE_NAME = re.compile(r"[^\W\d_](?:[^\W\d_]|[ .'’()\-])*")


@dataclass(frozen=True)
class Finding:
    """One piece of sensitive text: its kind, a description for the parent and the text found."""

    kind: str
    description: str
    text: str


def find_sensitive(text: str) -> list[Finding]:
    """Return the sensitive parts of a text (health, contact details, names, exact ages)."""
    findings: list[Finding] = []
    for kind, pattern, description in _KINDS:
        for match in pattern.finditer(text or ""):
            findings.append(Finding(kind, description, match.group(0).strip()))
    return findings


def explain(findings: list[Finding]) -> str:
    """Return a message asking the parent to remove the sensitive parts before sending."""
    parts = []
    for description in dict.fromkeys(f.description for f in findings):
        found = ", ".join(
            dict.fromkeys(f'"{f.text}"' for f in findings if f.description == description)
        )
        parts.append(f"{description} ({found})")
    return (
        "For your family's privacy this was not sent. The app does not handle "
        + "; ".join(parts)
        + ". Please remove that part and try again. Children are described only by their age "
        "group in the sidebar."
    )


def check_place_name(value: str) -> str:
    """Return a town or city name unchanged, or raise ValueError for anything else."""
    value = value.strip()
    # A dot directly followed by a letter (evil.example) is a domain, not "St. Peter".
    if not _PLACE_NAME.fullmatch(value) or "  " in value or re.search(r"\.[^\W\d_]", value):
        raise ValueError("Use a town or city name only (letters, spaces, . ' - and brackets).")
    if find_sensitive(value):
        raise ValueError("Use a town or city name only.")
    return value
