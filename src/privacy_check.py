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

from src import config

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
    "~depressiv*",
    "~psycholog*",
    "~orthopäd*",
    "~notaufnahme",
    "~schmerzen",
    "unwell",
    "been ill",
    "throws up",
    "throwing up",
    "threw up",
    "insulin",
    "inhaler*",
    "~inhalator*",
    "ritalin",
    "epipen*",
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
_HEALTH_EXTRA = (
    r"(?:(?<!\w)(?:is|are|got|feels?|feeling|was|has\s+been|gets?|getting|being)|'s)\s+sick"
    r"(?!\w)(?!\s+of\b)",
    r"(?<!\w)(?:carsick|car\s+sick|travel\s+sick|seasick)(?!\w)",
    # Any doctor, also in compounds (Ohrenarzt, Frauenärztin), but not "Schwarztee".
    r"(?<!schw)(?:arzt|ärzt|aerzt)",
)

# Cyrillic, Greek and other letters that look like Latin ones, and small capitals.
_LOOKALIKES = str.maketrans(
    "АВЕКМНОРСТХаеорсухіІјѕԁһΑΒΕΖΗΙΚΜΝΟΡΤΥΧαοινρıɑᴀᴄᴅᴇʜɪᴍɴᴏᴘʀꜱᴛᴜᴡʏ",
    "ABEKMHOPCTXaeopcyxiIjsdhABEZHIKMNOPTYXaoivpiaacdehimnoprstuwy",
)
# Hangul fillers look like nothing at all.
_INVISIBLE = frozenset("ㅤᅟᅠﾠ")
# Letters written one by one: "a d h d", "A. D. H. D.", "a-d-h-d", "a_d_h_d", "a/d/h/s".
_SPACED_LETTERS = re.compile(r"(?<!\w)(?:[^\W\d_](?:[ .\-_/·]+\s*|\t)){2,}[^\W\d_](?!\w)")
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _soft(text: str) -> str:
    """Return the text with compatibility forms folded, invisibles removed, look-alikes mapped."""
    text = unicodedata.normalize("NFKC", text or "").replace("’", "'").replace("‘", "'")
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


def _plain_pattern(term: str) -> str:
    """Return a regex where each word of a term may be typed with or without its accents."""
    inside = term.startswith("~")
    stem = term.removeprefix("~").removesuffix("*")
    words = [
        f"(?:{re.escape(w)}|{re.escape(_strip_accents(w))})"
        if _strip_accents(w) != w
        else re.escape(w)
        for w in stem.split()
    ]
    start = "" if inside else r"(?<!\w)"
    end = "" if term.endswith("*") else r"(?!\w)"
    return start + r"\s*".join(words) + end


# For text typed without (some) accents: each word of a term as typed or without accents, so
# "con tôi bị tăng dong" matches "tăng động" while "kể từ kỳ" never becomes "tự kỷ".
_HEALTH_PLAIN = re.compile(
    "|".join(
        _plain_pattern(t)
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
    r"easter|christmas|halloween|xmas|ostern|weihnacht\w*|pfingst\w*|silvester|karneval|fasching|"
    r"next|last|this|year|nächste\w*|letzte\w*|münchen|köln|nürnberg|düsseldorf|"
    + "|".join(re.escape(c.casefold()) for cities in config.CITIES.values() for c in cities)
)
# Words with a count in brackets that are no person: "Adults (2)", "Tickets (2)", "Pizza (3)".
_GROUP_WORDS = (
    r"adults?|children|kids?|kinder|kindern|erwachsene|erwachsenen|tickets?|snacks?|eintritt|"
    r"persons?|personen|people|babies|teens?|rides?|items?|seats?|plätze|drinks?|getränke|"
    r"meals?|essen|pizzas?|kaffee|coffee|tea|tee|eis|ice|zug|train|bus|parken|parking|"
    r"familienkarte|souvenirs?|bratwurst|würstchen|pommes|wasser|water|brezeln?|kuchen|cake"
)
# German prepositions and conjunctions: after them "meinen Sohn Kurse" or "wenn mein Kind Tiere
# mag" is a noun, not a name (fixed-width lookbehinds, both cases).
_NOT_AFTER = "".join(
    rf"(?<!\b{w} )(?<!\b{w.capitalize()} )"
    for w in (
        "für mit von bei zu wenn weil ob da dass wo falls obwohl damit als ohne über gegen um"
    ).split()
)
# A capitalised word that could be a name: not a day or holiday, not written in capitals.
_CAPITAL_WORD = rf"(?!(?i:{_NOT_NAMES})(?!\w))[A-ZÀ-ÖØ-ÞĐ][a-zß-öø-ÿđā-ɏạ-ỹ]+"
# A person's name: "my daughter is called Mia", "unser Sohn heißt Max", "con tên là Na",
# "my son Max", "meine Tochter Lena mag ...", "bé Na", "my son's name is max", "Mia (5) loves".
# "A place called Legoland", "my kid Saturday" or "für meine Tochter Ausflüge" is not a name.
_CHILD_WORDS = r"son|daughter|child|kid|boy|girl|baby|sohn|tochter|kind|junge|mädchen|con|bé|cháu"
# German: "unser Sohn Max besucht die Schule" or "unser Sohn Max, der ..." is a name; in "wenn
# mein Kind Tiere mag?" the verb ends the clause, so "Tiere" is a noun. A name needs a verb that
# more words follow (or a relative clause); prepositions and adverbs ending in -t are no verbs.
_NOT_VERBS = r"mit|nicht|jetzt|seit|oft|gut|sonst|erst|fast|meist|bist|samt|recht|direkt"
_PERSON_VERB = (
    rf"(?=[ \t]+(?!(?:{_NOT_VERBS})\b)(?:mag|will|kann|möchte|darf|\w+t)"
    r"[ \t]+(?!(?:und|oder|aber|sondern|denn)\b)\w"
    r"|[ \t]*,[ \t]*(?:der|die|das|who)\b)"
)
_NAME = re.compile(
    rf"(?<!\w)(?:(?i:{_CHILD_WORDS})[ \t]+(?:(?i:is|ist)[ \t]+)?"
    r"(?i:named|called|heißt|heisst|namens|tên là|tên)[ \t]+[^\W\d_]+"
    rf"|(?i:{_CHILD_WORDS})'s[ \t]+(?i:name)[ \t]+(?i:is)[ \t]+[^\W\d_]+"
    rf"|(?i:my|our)[ \t]+(?i:son|daughter|child|kid|boy|girl|baby)[ \t]+{_CAPITAL_WORD}"
    rf"|{_NOT_AFTER}(?i:mein|meine|meinen|meinem|unser|unsere|unseren|unserem)[ \t]+"
    rf"(?i:sohn|tochter|kind|junge|kleine[rnm]?)[ \t]+{_CAPITAL_WORD}{_PERSON_VERB}"
    r"|(?i:my name is|ich heiße|ich heisse|tôi tên là|tôi tên)[ \t]+[^\W\d_]+"
    rf"|(?i:bé|cháu|con tôi)[ \t]+{_CAPITAL_WORD}"
    rf"|(?!(?i:{_GROUP_WORDS})\b){_CAPITAL_WORD}[ \t]*\([ \t]*\d{{1,2}}[ \t]*\))"
)
_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    "sixteen|seventeen|eins|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf"
)
# Not the second number of a range ("6-9", "6 to 9", "6 bis 9") and not a threshold ("under 6").
_NOT_A_RANGE = (
    r"(?<!\d[-–])(?<!\d [-–] )(?<!\d[-–] )(?<!\d [-–])(?<!to )(?<!and )(?<!bis )(?<!đến )"
    r"(?<!under )(?<!over )(?<!unter )(?<!über )(?<!ab )(?<!dưới )(?<!trên )(?<!from )(?<!von )"
    r"(?<!từ )(?<!up to )(?<!below )(?<!above )(?<!than )(?<!least )(?<!mindestens )"
    r"(?<!höchstens )(?<!minimum )(?<!maximum )"
    # "zwischen 6 und 9" is a range; "Kinder 5 und 8 Jahre alt" are two ages.
    r"(?<!zwischen \d und )(?<!zwischen \d\d und )(?<!between \d and )(?<!between \d\d and )"
)
_NO_RANGE_AFTER = (
    r"(?!\s*(?:[-–]|to|and|bis|đến|or|oder)\s*\d)(?!\s*\+)"
    r"(?!\s*(?:and|or|und|oder)\s+(?:up|over|older|above|under|younger|älter|jünger|mehr))"
)
_UNITS = (
    r"(?!\s*(?:km|m|h|hrs?|min|mins?|minutes?|hours?|stunden?|std|uhr|tage?|days?|wochen?|weeks?|"
    r"meter|metres?|meters?|kilometer|\w*minuten|stops?|stations?|stationen|haltestellen?|"
    r"euros?|eur|€|%|miles?|pounds?|£|dollars?|\$|gbp|usd|grad|degrees?|°|stars?|sterne|"
    r"per|pro|each|je)(?!\w))(?!\s*[.:,]\d)"
)
# Words before "is 7" that are not a child's name.
_NOT_A_CHILD = (
    r"entry|admission|ticket|tickets|budget|price|total|it|this|that|there|today|tomorrow|"
    r"weather|temperature|parking|eintritt|preis|wetter|es|das|der|die|zug|bus|start|lunch|"
    r"limit"
)
# "Lena is 7 (now, in May, but ...)": a child's age (0-17) that ends the phrase or is followed by
# a word that fits an age; "Die Fahrt ist 12" (an article before the word) is no age.
_CHILD_AGE = (
    r"(?:1[0-7]|[0-9]|" + r"|".join(r"(?:" + w + r")" for w in _NUMBER_WORDS.split("|")) + ")"
)
_PHRASE_END = (
    r"(?=\s*(?:$|[.,;!?)(\-–]|(?:and|und|và|now|jetzt|schon|already|years?|jahre|geworden|im|in|"
    r"next|nächste\w*|but|aber|so|soon|bald)\b))"
)
_NO_ARTICLE = "".join(
    rf"(?<!\b{w} )" for w in "der die das den dem the a an für for ein eine".split()
)
# An exact age: "7 years old", "aged 7", "7-jährig", "7 Jahre alt", "7 tuổi", "18 months old",
# "seven years old", "7yo", "turns 7", "Lena is 7", "he is 8", "Leon, 6, likes". Age groups
# ("6-9", "6 to 9", "3-5 tuổi"), thresholds ("under 6") and time spans are not exact ages.
_AGE = re.compile(
    rf"{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:years?|yrs?|months?)[\s-]*old(?!\w)"
    rf"|(?<!\w)(?:{_NUMBER_WORDS})[\s-]*(?:years?|months?)[\s-]*old(?!\w)"
    r"|(?<!from )(?<!minimum )(?<!min\. )(?<!under )(?<!over )(?<!ab )(?<!least )"
    rf"(?<!\w)aged?\s+\d{{1,2}}{_NO_RANGE_AFTER}(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}\s*(?:yo|y/o)(?!\w)"
    rf"|(?<!\w)turns?\s+\d{{1,2}}{_UNITS}(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:jahre|monate)\s+alt(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*-?\s*(?:jährig\w*|monatig\w*)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*(?:tháng\s+)?tuổi(?!\w)(?!\s+trở)"
    rf"|(?<!\w)(?:{_CHILD_WORDS}|he|she|er|sie)"
    rf"\s+(?:is|ist|wird|turns|lên)\s+(?:\d{{1,2}}|{_NUMBER_WORDS}){_NO_RANGE_AFTER}{_UNITS}(?!\w)"
    rf"|{_NO_ARTICLE}(?<!\w)(?!(?:{_NOT_A_CHILD})\b)(?-i:{_CAPITAL_WORD})"
    rf"\s+(?:is|ist|wird|turns)\s+{_CHILD_AGE}(?!\d){_NO_RANGE_AFTER}{_UNITS}{_PHRASE_END}"
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
    if not findings:
        # Accents typed away, often only on some words: each word of a term may match with or
        # without its accents, but a word with other accents ("từ" is not "tự") never matches.
        findings = [Finding("health", m.group(0)) for m in _HEALTH_PLAIN.finditer(folded)]
    findings += [Finding("email", m.group(0)) for m in _EMAIL.finditer(soft)]
    findings += [Finding("phone", p) for p in _phones(soft)]
    findings += [Finding("name", m.group(0)) for m in _NAME.finditer(soft)]
    findings += [Finding("exact_age", m.group(0)) for m in _AGE.finditer(soft)]
    findings += [Finding("address", m.group(0)) for m in _ADDRESS.finditer(soft)]
    return findings


def explain(findings: list[Finding]) -> str:
    """Return a message naming what kind of data to remove (the text itself is not repeated)."""
    kinds = ", ".join(dict.fromkeys(f.description for f in findings))
    hint = (
        ' A word with a number in brackets, e.g. "(3)", can look like a child\'s name and age; '
        'write "3x" before the word instead.'
        if any(f.kind == "name" and "(" in f.text for f in findings)
        else ""
    )
    return (
        f"For your family's privacy this was not sent. It seems to contain {kinds}, which the app "
        "does not handle. Please remove that part and try again. Children are described only by "
        f"their age group in the sidebar.{hint}"
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
        "super",
        "under",
        "by",
    }
)
_PLACE_MAX_WORDS = 5
# Words about a family, numbers or instructions: never part of a town's name in these countries.
# First names cannot be told from town names offline (accepted residual, LEGAL_COMPLIANCE 2.6).
_NOT_PLACE_WORDS = frozenset(
    (
        "familie family kind kinder kinders kids children child sohn tochter son daughter baby "
        "babies toddler teen teens teenager twins zwillinge eltern parents mama papa mum dad oma "
        "opa grandma grandpa granny grandad adults adult erwachsene kita krippe hort nursery "
        "kindergarten schule school grundschule schulkind boy girl junge mädchen maedchen "
        "budget euro eur jahre jahr years year ignore disregard forget override reveal key rules "
        "regeln instructions policy previous earlier above orders system prompt"
    ).split()
)
# Number words: allowed only before another capitalised word ("Drei Gleichen", "Seven Sisters",
# "Three Rivers"), never alone or before another number ("Berlin Sechs Neun").
_NUMBER_WORD = re.compile(
    r"(?:eins|zwei|drei|vier|fünf|fuenf|sechs|sieben|acht|neun|zehn|elf|zwölf|zwoelf|hundert|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|hundred|"
    r"(?:thir|four|fif|six|seven|eigh|nine)teen|(?:twen|thir|for|fif|six|seven|eigh|nine)ty|"
    r"(?:drei|vier|fünf|fuenf|sech|sieb|acht|neun)zehn|"
    r"(?:zwan|vier|fünf|fuenf|sech|sieb|acht|neun)zig|drei(?:ß|ss)ig)",
    re.IGNORECASE,
)
_APOSTROPHE_WORD = re.compile(r"[^\W\d_]+['’]s|[dDlLoO]['’][A-ZÀ-Þ][^\W\d_]*")
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
    bares = [w.strip("().") for w in words]
    for i, bare in enumerate(bares):
        if _NUMBER_WORD.fullmatch(bare):
            following = bares[i + 1] if i + 1 < len(bares) else ""
            if not following[:1].isupper() or _NUMBER_WORD.fullmatch(following):
                raise error
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
