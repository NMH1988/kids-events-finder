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
    "sickness",
    "fever",
    "broken leg",
    "broken arm",
    "broke his*",
    "broke her*",
    "crutches",
    "lactose intoleran*",
    "gluten intoleran*",
    "coeliac",
    "celiac",
    "cystic fibrosis",
    "asd",
    "ocd",
    "ptsd",
    "tourette*",
    "on the spectrum",
    "stutter*",
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
    "depression*",
    "depressed",
    "depressive",
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
    "taubstumm",
    "~fieber*",
    "~erkält*",
    "~krücke*",
    "gipsbein",
    "gipsarm",
    "~mukoviszidose",
    "~zöliakie",
    "~intoleranz",
    "~zwangsstörung*",
    "stotter*",
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
# Phrases a regex states better than a word list ("is sick", but not "sick of the rain").
_HEALTH_EXTRA = (r"(?<!\w)(?:is|are|got|feels?|was)\s+sick(?!\w)(?!\s+of\b)",)

# Cyrillic, Greek and other letters that look like Latin ones, and small capitals.
_LOOKALIKES = str.maketrans(
    "АВЕКМНОРСТХаеорсухіІјѕԁһΑΒΕΖΗΙΚΜΝΟΡΤΥΧαοινρıɑᴀᴄᴅᴇʜɪᴍɴᴏᴘʀꜱᴛᴜᴡʏ",
    "ABEKMHOPCTXaeopcyxiIjsdhABEZHIKMNOPTYXaoivpiaacdehimnoprstuwy",
)
# Hangul fillers look like nothing at all.
_INVISIBLE = frozenset("ㅤᅟᅠﾠ")
# Letters written one by one: "a d h d", "A. D. H. D.", "a-d-h-d", "a_d_h_d", "a/d/h/s".
_SPACED_LETTERS = re.compile(r"(?<!\w)(?:[^\W\d_](?:[ .\-_/·]+\s*|\t)){2,}[^\W\d_](?!\w)")
# Letters only Vietnamese uses; text with them is matched with its accents, not without.
_VIETNAMESE = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯẠ-ỹ]")
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _soft(text: str) -> str:
    """Return the text with compatibility forms folded, invisibles removed, look-alikes mapped."""
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(
        ch
        for ch in text
        if unicodedata.category(ch) not in ("Cf", "Me", "Mc") and ch not in _INVISIBLE
    )
    return unicodedata.normalize("NFC", text.translate(_LOOKALIKES))


def _strip_accents(text: str) -> str:
    """Return the text without accents (Vietnamese đ becomes d)."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _join_spaced(text: str) -> str:
    """Join letters written one by one ("a d h d", "A. D. H. D.") into one word."""
    return _SPACED_LETTERS.sub(lambda m: re.sub(r"[^\w]|_", "", m.group(0)), text)


def _term_pattern(term: str) -> str:
    """Return a regex for one term (see `HEALTH_TERMS` for the markers)."""
    inside = term.startswith("~")
    stem = term.removeprefix("~").removesuffix("*")
    body = r"\s*".join(re.escape(part) for part in stem.split())
    start = "" if inside else r"(?<!\w)"
    end = "" if term.endswith("*") else r"(?!\w)"
    return start + body + end


def _variants(term: str) -> set[str]:
    """Return the term and its spelling without umlauts (Logopädie -> Logopaedie)."""
    return {term, term.translate(_UMLAUTS)}


_HEALTH = re.compile(
    "|".join([*(_term_pattern(v) for t in HEALTH_TERMS for v in _variants(t)), *_HEALTH_EXTRA])
)
_HEALTH_PLAIN = re.compile(
    "|".join(
        _term_pattern(_strip_accents(t))
        for t in HEALTH_TERMS
        if t.removeprefix("~").removesuffix("*") not in _ACCENT_ONLY
    )
)
# name@host.tld, also "name (at) host.tld"; "Zoo @ 10.30" is not an address.
_EMAIL = re.compile(
    r"[\w.+-]+(?:@|\s*\(at\)\s*|\s*\[at\]\s*)[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}(?!\w)",
    re.IGNORECASE,
)
# International (+49 ..., 0049 ...) or national (030 1234567, 030 123 45 67) phone numbers; a
# candidate counts only with 7-15 digits, so dates and times do not.
_PHONE = re.compile(
    r"(?<![\w+])(?:\+|00)[1-9][\d \t/().-]{5,20}\d(?!\w)"
    r"|(?<![\w.:-])0\d{2,5}(?:[ /-]?\d{2,10}){1,4}(?![\w:-])"
)
# Words that are capitalised but no name: days, months, holidays, "Today".
_NOT_NAMES = (
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)day\w*|weekend\w*|today|tomorrow|tonight|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"(?:mon|diens|donners|frei|sams|sonn)tag\w*|mittwoch\w*|wochenende\w*|heute|morgen\w*|"
    r"januar|februar|märz|mai|juni|juli|oktober|dezember|"
    r"easter|christmas|halloween|xmas|ostern|weihnacht\w*|pfingst\w*|silvester|karneval|fasching"
)
# A capitalised word that could be a name: not a day or holiday, not written in capitals.
_CAPITAL_WORD = rf"(?!(?i:{_NOT_NAMES})(?!\w))[A-ZÀ-ÖØ-ÞĐ][a-zß-öø-ÿđā-ɏạ-ỹ]+"
# A person's name: "my daughter is called Mia", "unser Sohn heißt Max", "con tên là Na",
# "my son Max", "meine Tochter Lena mag ...", "bé Na", "my son's name is max", "Mia (5) loves".
# "A place called Legoland", "my kid Saturday" or "für meine Tochter Ausflüge" is not a name.
_CHILD_WORDS = r"son|daughter|child|kid|boy|girl|baby|sohn|tochter|kind|junge|mädchen|con|bé|cháu"
_PERSON_VERB = r"(?=\s+(?:mag|liebt|ist|hat|will|wird|möchte|spielt|geht\s+gern)\b)"
_NAME = re.compile(
    rf"(?<!\w)(?:(?i:{_CHILD_WORDS})\s+(?:(?i:is|ist)\s+)?"
    r"(?i:named|called|heißt|heisst|namens|tên là|tên)\s+[^\W\d_]+"
    rf"|(?i:{_CHILD_WORDS})'s\s+(?i:name)\s+(?i:is)\s+[^\W\d_]+"
    rf"|(?i:my|our)\s+(?i:son|daughter|child|kid|boy|girl|baby)\s+{_CAPITAL_WORD}"
    rf"|(?i:mein|meine|meinen|unser|unsere|unseren)\s+(?i:sohn|tochter|kind|junge|kleine[rn]?)\s+"
    rf"{_CAPITAL_WORD}{_PERSON_VERB}"
    r"|(?i:my name is|ich heiße|ich heisse|tôi tên là|tôi tên)\s+[^\W\d_]+"
    rf"|(?i:bé|cháu|con tôi)\s+{_CAPITAL_WORD}"
    rf"|{_CAPITAL_WORD}\s*\(\s*\d{{1,2}}\s*\)(?=\s+(?!(?:and|und|or|oder|và)\b)[a-z]))"
)
_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    "sixteen|seventeen|eins|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf"
)
# Not the second number of a range ("6-9", "6 to 9", "6 bis 9") and not a threshold ("under 6").
_NOT_A_RANGE = (
    r"(?<!\d[-–])(?<!\d [-–] )(?<!\d[-–] )(?<!\d [-–])(?<!to )(?<!and )(?<!bis )(?<!đến )"
    r"(?<!under )(?<!over )(?<!unter )(?<!über )(?<!ab )(?<!dưới )(?<!trên )(?<!from )(?<!von )"
    r"(?<!từ )(?<!up to )(?<!below )(?<!above )"
)
_NO_RANGE_AFTER = r"(?!\s*(?:[-–]|to|and|bis|đến|or|oder)\s*\d)(?!\s*\+)"
_UNITS = (
    r"(?!\s*(?:km|m|h|min|minutes?|hours?|stunden|std|uhr|euros?|eur|€|%|miles?|pounds?|£|"
    r"dollars?|\$|gbp|usd|grad|degrees?|°|stars?|sterne)(?!\w))(?!\s*[.:,]\d)"
)
# Words before "is 7" that are not a child's name.
_NOT_A_CHILD = (
    r"entry|admission|ticket|tickets|budget|price|total|it|this|that|there|today|tomorrow|"
    r"weather|temperature|parking|eintritt|preis|wetter|es|das|der|die|zug|bus|start"
)
# An exact age: "7 years old", "aged 7", "7-jährig", "7 Jahre alt", "7 tuổi", "18 months old",
# "seven years old", "7yo", "turns 7", "Lena is 7", "he is 8", "Leon, 6, likes". Age groups
# ("6-9", "6 to 9", "3-5 tuổi"), thresholds ("under 6") and time spans are not exact ages.
_AGE = re.compile(
    rf"{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:years?|yrs?|months?)[\s-]*old(?!\w)"
    rf"|(?<!\w)(?:{_NUMBER_WORDS})[\s-]*(?:years?|months?)[\s-]*old(?!\w)"
    rf"|(?<!\w)aged?\s+\d{{1,2}}{_NO_RANGE_AFTER}(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}\s*(?:yo|y/o)(?!\w)"
    rf"|(?<!\w)turns?\s+\d{{1,2}}{_UNITS}(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:jahre|monate)\s+alt(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:jährig\w*|monatig\w*)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*(?:tháng\s+)?tuổi(?!\w)"
    rf"|(?<!\w)(?:(?:{_CHILD_WORDS}|he|she|er|sie)|(?!(?:{_NOT_A_CHILD})\b)(?-i:{_CAPITAL_WORD}))"
    rf"\s+(?:is|ist|wird|turns|lên)\s+(?:\d{{1,2}}|{_NUMBER_WORDS}){_NO_RANGE_AFTER}{_UNITS}(?!\w)"
    rf"|(?-i:{_CAPITAL_WORD}),\s*\d{{1,2}}\s*,\s*(?-i:[a-z])",
    re.IGNORECASE,
)
# A street address: "Musterstraße 12", "Lindenweg 3a"; "Rückweg 2 Stunden" is a time and
# "Fußweg 15 bis zum Zoo" a distance.
_ADDRESS = re.compile(
    r"(?<!\w)[^\W\d_]+(?:straße|strasse|str\.|weg|allee|gasse|street|road|avenue)\s+\d{1,4}[a-z]?"
    rf"(?!\w){_UNITS}(?!\s+(?:bis|to)\b)",
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
    findings = [Finding("health", m.group(0)) for m in _HEALTH.finditer(folded)]
    if not findings and not _VIETNAMESE.search(folded):
        # Accents typed away (or decomposed): match the accent-free copy. Text with Vietnamese
        # letters is not stripped, so ordinary words ("kể từ kỳ") do not turn into health terms.
        plain = _strip_accents(folded)
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
    """Return every text inside a JSON-like value: dict keys and values, list items, numbers."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in [str(k), *string_values(v)]]
    if isinstance(value, list):
        return [s for v in value for s in string_values(v)]
    return [] if value is None or isinstance(value, bool) else [str(value)]


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
_NOT_PLACE_WORDS = frozenset(
    "familie family kind kinder kids children child sohn tochter son daughter baby eltern "
    "parents mama papa mum dad budget euro eur jahre jahr years year alt old ignore rules "
    "regeln instructions previous system prompt".split()
)
_APOSTROPHE_WORD = re.compile(r"[^\W\d_]+['’]s|[dDlL]['’][A-ZÀ-Þ][^\W\d_]*")
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
    if not all(_latin_letter(ch) or ch in " .'’()-/" for ch in value) or "  " in value:
        raise error
    # Words are split on spaces, hyphens and slashes, so "Berlin-Kind-sieben-Jahre" counts as
    # four words; every part is capitalised or a small connecting word.
    words = re.split(r"[ \-/]", value)
    if len(words) > _PLACE_MAX_WORDS or not _latin_letter(value[0]):
        raise error
    for word in words:
        bare = word.strip("().")
        # An apostrophe only in "King's" or before a capital ("d'Alene", "L'Isle").
        apostrophe = "'" in bare or "’" in bare
        if apostrophe and not _APOSTROPHE_WORD.fullmatch(bare):
            raise error
        if not bare or not (bare[0].isupper() or bare in _PLACE_CONNECTORS or apostrophe):
            raise error
        # Words about a family or instructions are never part of a town's name.
        if bare.casefold() in _NOT_PLACE_WORDS:
            raise error
    # A dot followed by two letters (evil.example) is a domain; "St. Peter", "D.C." are not.
    if re.search(r"\.[^\W\d_]{2}", value) or find_sensitive(value):
        raise error
    return value
