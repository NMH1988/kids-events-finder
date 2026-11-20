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
    "kränk*",
    # Common illnesses, symptoms and treatments
    "husten",
    "grippe",
    "~windpocken",
    "masern",
    "scharlach",
    "~durchfall",
    "erbrech*",
    "~migräne",
    "~bauchweh",
    "~kopfweh",
    "~entzündung*",
    "heuschnupfen",
    "~impfung*",
    "~impftermin*",
    "läuse",
    "physio*",
    "cough*",
    "caught a cold",
    "got a cold",
    "chickenpox",
    "headache*",
    "stomach ache*",
    "stomachache*",
    "earache*",
    "toothache*",
    "sore throat",
    "has covid",
    "had covid",
    "hat corona",
    "hatte corona",
    "~schnupfen",
    "~halsweh",
    "~ohrenweh",
    "~zahnweh",
    "mumps",
    "röteln",
    "bronchitis",
    "~ausschlag",
    "rash",
    "nause*",
    "übelkeit",
    "ist übel",
    "verletzung",
    "bein gebrochen",
    "has a temperature",
    "running a temperature",
    "sprain*",
    "broken wrist",
    "broken ankle",
    "~verstaucht",
    "sich übergeben",
    "schlecht im auto",
    "his jabs",
    "her jabs",
    "his shots",
    "her shots",
    "under the weather",
    "got hurt",
    "is hurt",
    "was hurt",
    "been hurt",
    "are hurt",
    "hurt himself",
    "hurt herself",
    "is hurting",
    "rolli",
    "rollis",
    "rollifahrer*",
    "~rollifreundlich*",
    "~rollator*",
    "~gehhilfe*",
    "walking frame",
    "~rehabuggy*",
    "reha-buggy",
    "~rehakinderwagen*",
    "adaptive stroller",
    "can't climb stairs",
    "can't walk far",
    "in plaster",
    "in gips",
    "einen gips",
    "been sick",
    "~reiseübelkeit",
    "his operation",
    "her operation",
    "nach der op",
    "stitches",
    "concussion",
    "~gehirnerschütterung",
    "aufgeschlagen",
    "wehgetan",
    "tummy ache",
    "sniffles",
    "runny nose",
    "booster shot*",
    "booster jab*",
    "booster vacc*",
    "~auffrischimpfung*",
    "mmr",
    "bị thương",
    # Giftedness is a development statement too (owner decision 2026-11-20); the verb ("we were
    # gifted tickets") is not, see `_HEALTH_EXTRA`.
    "~hochbegabt*",
    "late bloomer",
    "advanced for his age",
    "advanced for her age",
    "đau bụng",
    "sổ mũi",
    "bị nôn",
    "lên cơn sốt",
    "arm gebrochen",
    "erbroch*",
    "nosebleed*",
    "throw up",
    "influenza",
    "ear infection",
    "strep throat",
    "stomach bug",
    # Accessibility needs (owner decision 2026-11-20: handled like health data); words that also
    # fit a pram ("barrierefrei", "step-free") are in `_ACCESS` below.
    "~behindertengerecht*",
    "~rollstuhlgerecht*",
    "accessibility needs",
    "disabled access",
    "blue badge",
    # Development statements (owner decision 2026-11-20: blocked, not only left to the prompt)
    "developmental*",
    "his development",
    "her development",
    "their development",
    "my child's development",
    "child's development",
    "child development",
    "for development",
    "helps development",
    "developing slowly",
    "late talker",
    "late walker",
    "slow learner",
    "slow to talk",
    "learning difficult*",
    "delayed in speech",
    "behind her peers",
    "behind his peers",
    "behind their peers",
    "behind other kids",
    "behind for his age",
    "behind for her age",
    "behind in development",
    "behind in school",
    "behind in speech",
    "behind his class",
    "behind her class",
    "entwicklung meines*",
    "entwicklung meiner*",
    "entwicklung unseres*",
    "entwicklung unserer*",
    "entwicklung des kindes",
    "für die entwicklung",
    "~entwicklungsstand*",
    "~entwicklungsverzög*",
    "~entwicklungsstörung*",
    "~sprachentwickl*",
    "~kindesentwickl*",
    "con phát triển",
    "bé phát triển",
    "trẻ phát triển",
    "zurückgeblieben",
    "~lernschwäch*",
    "~sprachstörung*",
    "~förderschul*",
    "measles",
    "diarrh*",
    "vomit*",
    "migraine*",
    "lice",
    "bị sốt",
    "bị ho",
    "bị cảm",
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
_ACCENT_ONLY = frozenset(
    {"ốm", "bị sốt", "bị ho", "bị cảm", "bị nôn", "bị thương"}
    | {"con phát triển", "bé phát triển", "trẻ phát triển"}
)
# Step-free access: a child's accessibility need, unless the message is about a pram or buggy
# and names no wheelchair or disability ("Ist das Museum mit Kinderwagen barrierefrei?").
_ACCESS = re.compile(
    r"barrierefrei\w*|barrier\W*free|step\W*free|stufenlos(?!\s+verstellbar)|ohne\s+stufen|"
    r"accessible\s+toilets?|(?<!\w)a\s+ramp(?!\w)|(?<!\w)ramps\s+for|"
    # Generic accessibility questions (owner decision 2026-11-20), not getting there by transport.
    r"accessibility(?!\s+(?:by|via|from)\s)|"
    r"(?<!\w)(?:is|are)\s+(?:it|the|they)\s+(?:\w+\s+){0,3}accessible"
    # Not getting there ("by train", "on foot"), a season, or whether small children can manage
    # it ("accessible for toddlers?"), which is about age, not health; only when the clause ends
    # there, so "accessible for kids with a walker" stays blocked.
    r"(?!\s+(?:by|via|from|with\s+public)\s)(?!\s+on\s+foot)"
    r"(?!\s+in\s+(?:winter|summer|spring|autumn|fall)\b)"
    # (owner decision 2026-11-20: "accessible for toddlers?" passes only if the message ends there)
    r"(?!\s+(?:for|to)\s+(?:(?:my|our|the|young|small|little|older|younger)\s+)?(?:kids|children|"
    r"toddlers|families|little\s+ones|babies|young\s+kids|small\s+children)\s*[?.!]?\s*$)"
)
_ACCESSIBLE_ANY = re.compile(r"(?<!\w)accessib\w*")
# Equipment, not the child: a step-free or barrier-free question about a pram, a bike, a
# scooter or luggage is no health data ("Ist das Museum mit Kinderwagen barrierefrei?").
_PRAM = re.compile(
    r"(?<!\w)(?:\w*kinderwagen\w*|buggy|buggies|prams?|pushchairs?|strollers?|xe đẩy|skate\w*|"
    r"scooters?|bmx|bikes?|fahrrad|fahrräder|luggage|gepäck|suitcases?|koffer)(?!\w)"
)
# A wheelchair, a disability or a mobility aid in the same message keeps the block.
_DISABILITY = re.compile(
    r"wheelchair|rollstuhl|rolli(?!ng)|behindert|disab|xe lăn|handicap|reha|adaptive|rollator|"
    r"walker|gehhilfe|nicht\s+laufen|can(?:'?t|\s*not)\s+walk|weak\s+legs|crutch|krücke"
)
# Phrases a regex states better than a word list ("is sick", but not "sick of the rain").
_HEALTH_EXTRA = (
    r"(?:(?<!\w)(?:is|are|got|feels?|feeling|was|has\s+been|gets?|getting|being)|'s)\s+sick"
    r"(?!\w)(?!\s+of\b)",
    r"(?<!\w)(?:carsick|car\s+sick|travel\s+sick|seasick)(?!\w)",
    # Any doctor, also in compounds (Ohrenarzt, Frauenärztin); not "Schwarztee", the Harz
    # ("Harztour"), "Märztage" or the vet ("Tierarzt werden", a common child's wish).
    r"(?<!schw)(?<!tier)(?<!\bh)(?<!\bm)(?<!\bqu)(?:arzt|ärzt|aerzt)",
    r"(?<!\w)(?:doctor(?!\s+who\s+(?:exhibition|experience|ausstellung|museum|show|tour|shop|"
    r"event|themed)\b)(?!\s+dolittle)|(?:zahn|augen|kinder|haus|frauen|ohren)?doktor(?!fisch)|"
    r"hno|pa?ediatrician|dentist|zahnklinik)\w*",
    # Injuries and a cold are blocked by default; the exceptions are questions about safety or
    # animals ("damit sich keiner verletzt", "can kids get injured?", "risk of injury",
    # "verletzte Tiere", "so they don't hurt their feet", "a cold plunge").
    r"(?<!keiner )(?<!niemand )(?<!jemand )(?<!\w)verletzt(?!e[nr]?\s+(?:tiere|igel|vögel|"
    r"wildtiere|tieren))\w*",
    r"(?<!get )(?<!gets )(?<!getting )(?<!be )(?<!\w)injured(?!\s+(?:birds?|animals?|wildlife))"
    r"(?!\w)",
    # An injury of someone ("his injury", "a knee injury", "my son's injury", "got an injury"),
    # not "injuries at trampoline parks", "in case of an injury", "a minor injury unit" or "an
    # injury risk".
    # Possessive: "his injury", "my son's bad left knee injury", "Max's injury" (not "What's the
    # injury risk").
    r"(?:(?<!\w)(?:his|her|their|my)|(?<!\bwhat)(?<!\bthat)(?<!\bit)(?<!\bthere)(?<!\bwhere)"
    r"(?<!\bhere)(?<!\bwho)(?<!\bhow)'s|(?<=\ws)')\s+"
    r"(?!an?\s)(?:\w+\s+){0,3}?injur(?:y|ies)"
    r"(?!\s+(?:risk|clinic|unit|centre|center|prevention|insurance))(?!\w)",
    # "a/an … injury" is generic in a safety question ("in case of a minor injury", "a typical
    # injury", "a minor injury unit"), so only without such a qualifier or context.
    r"(?<!\w)(?<!case of )(?<!event of )(?<!if there is )(?<!if there's )(?<!if )an?\s+"
    r"(?!(?:typical|minor|common|possible)\s)(?:\w+\s+)?injur(?:y|ies)"
    r"(?!\s+(?:risk|clinic|unit|centre|center|prevention|insurance))(?!\w)",
    # Statements with a verb keep any qualifier ("has a minor injury", "suffered a serious head
    # injury", "has knee injury", "sustained injuries"); not "Have there been injuries at this
    # park?", "Which parks have the fewest injuries?" or "injury insurance".
    r"(?<!\w)(?:has|have|had|got|gets|suffered|sustained|picked\s+up)\s+(?!there\b)"
    r"(?!(?<=have\s)the\s+(?:fewest|least)\b)(?:\w+\s+){0,4}?"
    r"injur(?:y|ies)(?!\s+(?:risk|clinic|unit|centre|center|insurance)\b)",
    r"(?<!\w)(?:he|she|they|son|daughter|kid|kids|child|children|twins|boys|girls|baby|toddler|"
    r"both)\s+(?:has|have|had|got|suffered)\s+(?:\w+\s+){0,2}?injuries",
    r"'s\s+hurt(?!\w)",
    # "hurt/broke his …" is checked in `_hurt_findings`, which skips questions with a modal or a
    # negation earlier in the clause ("Will my son hurt his hands on the climbing wall?").
    # Fever in Vietnamese, not "sốt ruột" (impatient), "sốt sắng" (eager) or "sốt vé" (sold out).
    r"(?:con\s+đang\s+sốt|bé\s+đang\s+sốt|hơi\s+sốt|sốt\s+cao|sốt\s+nhẹ)(?!\s*(?:ruột|sắng|vé))",
    r"(?:(?<!\w)(?:is|are|feels?|feeling|was|were|been|still|seems?|looks?|got|became)|'s)\s+"
    # "running poorly", "written poorly" describe things, not a child.
    r"(?:\w+\s+){0,2}?(?<!running )(?<!working )(?<!written )(?<!loading )"
    r"(?<!organised )(?<!organized )poorly"
    r"(?!\s+(?:\w+ed|lit|kept|run|made|designed|paid|built|written)\b)",
    r"(?<!\w)(?:my|our|his|her)\s+poorly(?!\s+(?:\w+ed|lit|kept|run|made|designed)\b)",
    r"(?<!\w)poorly\s+since",
    # Giftedness of a child; not the verb: passive with an object ("we were gifted tickets", "we
    # got gifted a zoo membership") or active with a person ("my mum gifted us a voucher").
    r"(?<!\w)(?<!were )(?<!was )(?<!been )(?<!got )(?<!get )gifted(?!\s+(?:us|them|me)\b)(?!\w)",
    # "is gifted" is the child, whatever follows ("My son is gifted us teachers say").
    r"(?<!\w)(?:is|are|'s)\s+(?:so\s+|very\s+|really\s+|highly\s+)?gifted(?!\w)",
    # Passive with a thing as object; not "was gifted the teacher thinks".
    r"(?<!\w)(?:were|was|been|got|get)\s+gifted(?!\s+(?:tickets?|vouchers?|a|an|two|three|"
    r"some|our|my|\d+)\b)(?!\w)",
    r"spricht\s+noch\s+nicht(?!\s+(?:so\s+)?(?:gut\s+|viel\s+)?(?:englisch|deutsch|französisch|"
    r"spanisch|italienisch|niederländisch))",
    # Statements about a child's development (owner decision 2026-11-20).
    r"(?:son|daughter|kid|child|toddler|baby|boy|girl)'s\s+(?:\w+\s+)?development",
    r"(?:speech|language|motor|cognitive|social|emotional)\s+development",
    r"(?:seine|ihre|deren)\s+entwicklung|in\s+(?:der|ihrer|seiner)\s+entwicklung",
    r"(?:motorische|sprachliche|kognitive|soziale|emotionale)\s+entwicklung",
    r"entwicklung\w*\s+(?:\w+\s+){0,3}?(?:verzögert|zurück)",
    r"phát\s+triển\s+của\s+(?:con|bé|cháu|trẻ)|phát\s+triển\s+chậm",
    # A cold needs "a" ("has a cold") or the plural ("have colds"); "have cold drinks" is food.
    r"(?<!\w)(?:has|have|had)\s+(?:got\s+)?(?:a\s+(?:bad\s+|heavy\s+|nasty\s+)?cold(?!\s+(?:plunge|"
    r"drink|drinks|shower|showers|pool|water|temperature|room|buffet|food|snacks?|weather|dessert|"
    r"desserts|sandwich|sandwiches|milk)\b)|(?:bad\s+|heavy\s+)?colds)(?!\w)",
    # Booster vaccine ("after his booster", "had the booster"), not a booster seat ("a booster in
    # the taxi").
    r"(?<!bring )(?<!pack )(?<!\w)(?:his|her|their)\s+booster(?!\s+(?:seats?|cushions?)\b)"
    r"(?!\w)",
    r"(?<!\w)(?:had|got|gets|getting|needs?|needed|after|before)\s+(?:the|a)\s+booster"
    r"(?!\s+(?:seats?|rides?|cushions?|in|for)\b)(?!\w)",
    r"(?<!\w)(?:the\s+)?flu(?!\s+(?:season|outbreak|wave|shot\s+clinic)\b)"
    r"(?<!because of the flu)(?!\w)",
    r"(?<!\w)corona(?!\s+park)(?!\w)(?!\s+(?:rules|regeln|restrictions))",
    r"(?<!\w)covid(?:-19)?(?!\s+(?:rules|regeln|restrictions|test\s+centre))(?!\w)",
    # Vaccination of the child, not the rules ("Impfpass", "vaccine passport", "Impfpflicht").
    r"(?<!\w)(?:impf(?!pass|pflicht|nachweis)\w*|vaccin(?!e\s+passport)\w*)",
)

# Cyrillic, Greek and other letters that look like Latin ones, and small capitals.
_LOOKALIKES = str.maketrans(
    "АВЕКМНОРСТХаеорсухіІјѕԁһΑΒΕΖΗΙΚΜΝΟΡΤΥΧαοινρıɑᴀᴄᴅᴇʜɪᴍɴᴏᴘʀꜱᴛᴜᴡʏ",
    "ABEKMHOPCTXaeopcyxiIjsdhABEZHIKMNOPTYXaoivpiaacdehimnoprstuwy",
)
# Hangul fillers look like nothing at all.
_INVISIBLE = frozenset("ㅤᅟᅠﾠ")
# Letters written one by one: "a d h d", "A. D. H. D.", "a-d-h-d", "a_d_h_d", "a/d/h/s".
# Possessive quantifiers (*+, ++) keep matching linear on long input.
_SPACED_LETTERS = re.compile(r"(?<!\w)(?:[^\W\d_](?:[ .\-_/·]++\s*+|\t)){2,}[^\W\d_](?!\w)")
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
# Characters typed as an apostrophe: right and left quote, acute accent, backtick, modifier
# letter apostrophe, prime.
_APOSTROPHES = str.maketrans(dict.fromkeys("’‘´`ʼ′", "'"))


def _soft(text: str) -> str:
    """Return the text with compatibility forms folded, invisibles removed, look-alikes mapped."""
    # Apostrophe look-alikes before NFKC, which turns "´" into a space and a combining accent.
    text = (text or "").translate(_APOSTROPHES)
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES)
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
    # The lookbehind anchors the start, so a long run of letters is not re-scanned (no slow-down).
    r"(?<![\w.+-])[\w.+-]+(?:@|\s*\(at\)\s*|\s*\[at\]\s*)[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}(?!\w)",
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
    r"thanksgiving|memorial|labou?r|bank|boxing|spring|summer|winter|autumn|fall|half|"
    r"mother'?s|mothers|father'?s|fathers|independence|presidents?|valentine\w*|new|trick|"
    r"veterans|easter\w*|fourth|good|columbus|martin(?=\s+luther)|st|saint|patrick'?s|bonfire|"
    r"guy(?=\s+fawkes)|juneteenth|hanukk?ah|chanukah|diwali|eid|ramadan|day|mlk|lego|legoland|"
    r"playmobil|disneyland|ideas?|what|which|where|how|any|help|black|lunar|mardi|pokemon|"
    r"pokémon|zoo|"
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
# Main clause: the verb after the name is followed by more words ("Max spielt und malt gern").
_PERSON_VERB = rf"(?=[ \t]+(?!(?:{_NOT_VERBS})\b)(?:mag|will|kann|möchte|darf|\w+t)[ \t]+\w)"
# A relative clause after the name: in a main clause any name ("Mein Sohn Ben, der gern malt").
_RELATIVE_CLAUSE = r"(?=[ \t]*,[ \t]*(?:der|die|das|who)\b)"
_POSSESSIVE = r"(?i:mein|meine|meinen|meinem|meiner|unser|unsere|unseren|unserem|unserer)"
# Endings of activity and other common nouns that are no names (Fußball, Ski, Kanu, Kajak, Kunst,
# Musik, Sport, Golf, Yoga, Judo, Tanz, Theater, Vögel, Bilder).
# Whole words (with a word start), so first names like Franz, Wolf or Rudolf still count as names.
# Compound endings no first name has (Kampfsport, Brettspiel, Kindertheater, Skateboard).
_ACTIVITY_ENDINGS = (
    # "golf" only after three letters (Minigolf, Discgolf), so the name Ingolf still counts.
    r"(?<!ball)(?<!sport)(?<!spiel)(?<!theater)(?<!yoga)(?<![^\W\d_]{3}golf)(?<!board)"
    + "".join(
        rf"(?<!\b{w})"
        for w in (
            "Ski",
            "Kanu",
            "Kajak",
            "Kunst",
            "Musik",
            "Sport",
            "Golf",
            "Minigolf",
            "Yoga",
            "Judo",
            "Tanz",
            "Theater",
            "Vögel",
            "Bilder",
            "Ballett",
            "Karate",
            "Snowboard",
            "Spiel",
        )
    )
)
_CHILD_NOUN = r"(?i:sohn|tochter|kind|junge|kleine[rnm]?)"
# After a preposition the pronoun must fit the child ("für meinen Sohn Max, der", "mit meiner
# Tochter Lena, die"), and for a daughter the word must not look plural ("Events, die", "Kurse,
# die"), so "für mein Kind Tipps, die" or "für meinen Sohn Workshops, die" pass.
# Nouns ending like these are no names ("Ferienbetreuung, die", "Schwimmunterricht, der").
_NOUN_ENDINGS_F = (
    "".join(
        f"(?<!{e})"
        for e in ("e", "es", "er", "s", "n", "ung", "heit", "keit", "schaft", "ion", "tät")
    )
    + "(?<!ik)(?<!ur)"
)
# Boys' names often end in -s (Lukas, Jonas, Elias), and plurals take "die", so -s stays allowed.
_NOUN_ENDINGS_M = "(?<!richt)(?<!sport)(?<!kurs)"
_PREPOSITION_RELATIVE = (
    rf"{_POSSESSIVE}[ \t]+(?:(?i:sohn|junge|jungen|kleiner|kleinen|kleinem)[ \t]+{_CAPITAL_WORD}"
    rf"{_NOUN_ENDINGS_M}(?=[ \t]*,[ \t]*der\b)"
    rf"|(?i:tochter|kleine)[ \t]+{_CAPITAL_WORD}{_NOUN_ENDINGS_F}(?=[ \t]*,[ \t]*die\b)"
    # "mit meinem Kind Paul, der …" / "für mein Kind Lena, die …"; ", das" is left out because
    # neuter nouns look the same ("für mein Kind Spielzeug, das …").
    rf"|(?i:kind)[ \t]+{_CAPITAL_WORD}{_NOUN_ENDINGS_M}(?=[ \t]*,[ \t]*der\b)"
    rf"|(?i:kind)[ \t]+{_CAPITAL_WORD}{_NOUN_ENDINGS_F}(?=[ \t]*,[ \t]*die\b))"
)
_NAME = re.compile(
    rf"(?<!\w)(?:(?i:{_CHILD_WORDS})[ \t]+(?:(?i:is|ist)[ \t]+)?"
    r"(?i:named|called|heißt|heisst|namens|tên là|tên)[ \t]+[^\W\d_]+"
    rf"|(?i:{_CHILD_WORDS})'s[ \t]+(?i:name)[ \t]+(?i:is)[ \t]+[^\W\d_]+"
    rf"|(?i:my|our)[ \t]+(?i:son|daughter|child|kid|boy|girl|baby|little\s+one)[ \t]+"
    rf"{_CAPITAL_WORD}"
    # "my kids Max and Lena", "my two kids Max …", "my boys Max and Tom", "Kids: Max and Lena";
    # with a comma the name needs a second comma or "and" after it ("my son, Max, loves"), so
    # "For my son, Lego or Playmobil?" passes. Possessive quantifiers keep this linear.
    rf"|(?i:my|our)[ \t]++(?:(?i:two|three|four|2|3|4)[ \t]++)?"
    r"(?i:kids|children|sons|daughters|twins|boys|girls)[ \t]*+:?[ \t]*+"
    rf"(?:(?i:are|are\s+called)[ \t]++)?{_CAPITAL_WORD}"
    r"|(?i:my|our)[ \t]++(?i:children's|kids')[ \t]++(?i:names?)[ \t]++(?i:are|is)[ \t]++"
    rf"{_CAPITAL_WORD}"
    r"|(?i:the)[ \t]++(?i:kids|children)[ \t]++(?i:are)[ \t]++"
    rf"{_CAPITAL_WORD}(?=[ \t]++(?i:and)[ \t]++)"
    rf"|{_CAPITAL_WORD}[ \t]++(?i:and|und)[ \t]++{_CAPITAL_WORD}[ \t]++(?i:are|sind)[ \t]++"
    r"(?i:my|our|meine|unsere)[ \t]++(?i:kids|children|sons|daughters|kinder)"
    # "Kids: Max and Lena", "Ideas for kids: Mia, Leo and Ben", "Kids: Mia, and Leo"; a second
    # capitalised word must follow, so "Activities for kids: Swimming, climbing" passes.
    r"|(?i:kids|children|kinder)[ \t]*+:[ \t]*+"
    rf"{_CAPITAL_WORD}(?=[ \t]*+(?:,[ \t]*+(?:and[ \t]++)?|and\b[ \t]*+|und\b[ \t]*+|&[ \t]*+)"
    r"[A-ZÀ-ÖØ-ÞĐ])"
    r"|(?i:my|our)[ \t]++(?i:son|daughter|boy|girl|kids|children|youngest|eldest|oldest|"
    r"little\s+one)[ \t]*+,[ \t]*+"
    rf"{_CAPITAL_WORD}(?=[ \t]*+(?:,|and\b|und\b))"
    rf"|{_POSSESSIVE}[ \t]++(?:(?i:zwei|drei|beiden)[ \t]++)?(?i:kinder|zwillinge|söhne|töchter)"
    rf"[ \t]*+:?[ \t]*+(?:(?i:heißen|heissen|sind)[ \t]++)?\(?{_CAPITAL_WORD}(?:[ \t]*+,[ \t]*+"
    rf"{_CAPITAL_WORD})*+[ \t]++(?:und|&|and)[ \t]++{_CAPITAL_WORD}(?!\w)"
    # "wo meine Kinder Tiere und Pflanzen sehen?": plural nouns (ending in -e, -n, -s) before a
    # clause-final verb are no names; "Max und Lena tanzen." still counts.
    # Activity nouns ("Fußball und Basketball spielen?") count as plural-looking nouns too.
    rf"(?:(?<![ens]){_ACTIVITY_ENDINGS}|(?![ \t]+\w+(?:[ \t]+(?:können|kann|wollen|will|möchten|"
    r"dürfen|müssen))?[ \t]*(?:[.?!,;]|$)))"
    rf"|{_NOT_AFTER}{_POSSESSIVE}[ \t]+{_CHILD_NOUN}[ \t]+{_CAPITAL_WORD}"
    rf"(?:{_PERSON_VERB}|{_RELATIVE_CLAUSE})"
    rf"|{_PREPOSITION_RELATIVE}"
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
    # "für 4- und 5-Jährige": a shortened compound of two age groups.
    r"(?<!\d[-–] und )(?<!\d[-–] oder )(?<!\d[-–] and )(?<!\d[-–] or )"
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
    r"limit|bedtime|naptime|dinner|breakfast|kickoff|abfahrt|ankunft|treffpunkt|beginn|einlass|"
    r"mittagessen|abendessen|frühstück|gleis|platform|membership|mitgliedschaft|legoland|"
    r"sunset|sunrise|pickup|dropoff|checkout|checkin|showtime|storytime|opening|closing|feeding|"
    r"vorstellung|fütterung|öffnung|sonnenuntergang|abholung|rückfahrt|rückweg|heimfahrt|"
    r"return|departure|arrival"
)
# The verb before an age: "is", "ist", "wird", "turns", "is turning", "will be", "'s", "'ll be".
_AGE_VERB = r"(?:\s+(?:is\s+turning|will\s+be|is|ist|wird|turns|lên)|'s|'ll\s+be)\s+"
# Words before a number that still give an exact age: "Lena is only 7", "Lena ist erst 7".
_AGE_ADVERB = (
    r"(?:(?:only|just|almost|nearly|now|already|about|around|erst|fast|schon|gerade|bald|jetzt|"
    r"inzwischen|mittlerweile|ungefähr|etwa)\s+)?"
)
# Older siblings and the youngest, after an article: "Die Kleine ist 4", "Der Große ist 7",
# "the youngest is 3".
_SIBLING_WORDS = (
    r"kleine[rn]?|kleinste[rn]?|große[rn]?|grosse[rn]?|größte[rn]?|grösste[rn]?|jüngste[rn]?|"
    r"jüngere[rn]?|älteste[rn]?|ältere[rn]?|mittlere[rn]?|youngest|eldest|oldest"
)
# "Lena is 7 (now, in May, but ...)": a child's age (0-17) that ends the phrase or is followed by
# a word that fits an age; "Die Fahrt ist 12" (an article before the word) is no age.
_CHILD_AGE = (
    r"(?:1[0-7]|[0-9]|" + r"|".join(r"(?:" + w + r")" for w in _NUMBER_WORDS.split("|")) + ")"
)
_PHRASE_END = (
    r"(?!\s+and\s+a\s+half\s+(?:hours?|hrs?|minutes?|mins?|days?|weeks?|miles?|km)\b)"
    r"(?=\s*(?:$|[.,;!?)(\-–]|:(?!\d)|(?:and|und|và|now|jetzt|schon|already|years?|jahre|"
    r"geworden|im|in|next|nächste\w*|but|aber|so|soon|bald|"
    r"this\s+(?:year|summer|winter|spring|autumn|fall|month|week)|dieses\s+jahr|diesen\s+(?:sommer|winter|monat|herbst|frühling)|diese\s+woche|too|auch)\b))"
)
_NO_ARTICLE = "".join(
    rf"(?<!\b{w} )" for w in "der die das den dem the a an für for ein eine".split()
)
# An exact age: "7 years old", "aged 7", "7-jährig", "7 Jahre alt", "7 tuổi", "18 months old",
# "seven years old", "7yo", "turns 7", "Lena is 7", "he is 8", "Leon, 6, likes". Age groups
# ("6-9", "6 to 9", "3-5 tuổi"), thresholds ("under 6") and time spans are not exact ages.
_AGE = re.compile(
    rf"{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*+-?\s*+(?:years?|yrs?|months?)[\s-]*old(?!\w)"
    rf"|(?<!\w)(?:{_NUMBER_WORDS})[\s-]*(?:years?|months?)[\s-]*old(?!\w)"
    r"|(?<!from )(?<!minimum )(?<!min\. )(?<!under )(?<!over )(?<!ab )(?<!least )"
    rf"(?<!\w)aged?\s+\d{{1,2}}{_NO_RANGE_AFTER}(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}\s*(?:yo|y/o)(?!\w)"
    rf"|(?<!\w)turns?\s+\d{{1,2}}{_UNITS}(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*+-?\s*+(?:jahre|monate)\s+alt(?!\w)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*+-?\s*+(?:jährig\w*|monatig\w*)"
    rf"|{_NOT_A_RANGE}(?<!\w)\d{{1,2}}{_NO_RANGE_AFTER}\s*(?:tháng\s+)?tuổi(?!\w)(?!\s+trở)"
    rf"|(?<!\w)(?:{_CHILD_WORDS}|he|she|er|sie|{_SIBLING_WORDS})"
    rf"{_AGE_VERB}{_AGE_ADVERB}(?:\d{{1,2}}|{_NUMBER_WORDS})"
    rf"{_NO_RANGE_AFTER}{_UNITS}(?!\w)"
    rf"|{_NO_ARTICLE}(?<!\w)(?!(?:{_NOT_A_CHILD})\b)(?-i:{_CAPITAL_WORD})"
    rf"{_AGE_VERB}{_AGE_ADVERB}{_CHILD_AGE}(?!\d){_NO_RANGE_AFTER}{_UNITS}"
    rf"{_PHRASE_END}"
    # "my kids are 7 and 4", "meine Kinder sind 5 und 8"
    rf"|(?<!\w)(?:kids|children|kinder|boys|girls)\s+(?:are|sind)\s+{_CHILD_AGE}\s+(?:and|und|&)\s+"
    rf"{_CHILD_AGE}(?!\d){_UNITS}"
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


_HURT = re.compile(r"(?<!\w)(?:hurt|broke)\s+(?:his|her|my)\s+\w+", re.IGNORECASE)
# A modal right before the subject ("Will my son hurt …", "could my daughter hurt …") or a
# negation or "to" right before the verb ("so he doesn't hurt …", "to hurt") makes it a safety
# question. "May" is a modal only in lower case or at the start of the clause ("In May my son
# hurt his knee" is a statement).
_MODAL_BEFORE = re.compile(
    # "might have hurt" is a statement about a past injury, not a safety question.
    r"(?:^\s*(?i:will|would|could|can|might|may)|(?<!\w)(?:will|would|could|can|might|may))"
    r"\s+(?:\w+\s+){0,2}(?<!have )$"
    r"|(?<!\w)(?i:don't|doesn't|won't|didn't|can't|cannot|couldn't|wouldn't|shouldn't|not|to|"
    r"never)\s+$"
)


def _hurt_findings(soft: str) -> list[Finding]:
    """Return "hurt/broke his …" statements; "Will my son hurt his hands?" is a safety question."""
    found = []
    for match in _HURT.finditer(soft):
        # The clause before the verb ends at punctuation and at "and", "but", "because".
        before = soft[max(0, match.start() - 200) : match.start()]
        clause = re.split(r"[.?!;,]|\b(?:and|but|because|und|aber|weil)\b", before)
        if not _MODAL_BEFORE.search(clause[-1]):
            found.append(Finding("health", match.group(0)))
    return found


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
    findings += _hurt_findings(soft)
    # Step-free access is a child's need unless the message is only about a pram or buggy.
    disability = _DISABILITY.search(folded)
    if not (_PRAM.search(folded) and not disability):
        findings += [Finding("health", m.group(0)) for m in _ACCESS.finditer(folded)]
    # A mobility aid anywhere in the message keeps "accessible for kids?" blocked ("My son uses a
    # walker. Is the zoo accessible for kids?").
    if disability:
        findings += [Finding("health", m.group(0)) for m in _ACCESSIBLE_ANY.finditer(folded)]
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
    # Iterative, so deeply nested input cannot overflow the stack.
    found: list[str] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict):
            found.extend(str(k) for k in item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif item is not None and not isinstance(item, bool):
            found.append(str(item))
    return found


def json_depth(value: object) -> int:
    """Return how deeply a JSON-like value nests lists and dicts (iterative)."""
    deepest, stack = 0, [(value, 0)]
    while stack:
        item, depth = stack.pop()
        deepest = max(deepest, depth)
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
    return deepest


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
        "regeln instructions policy previous earlier above orders system prompt "
        "monate monaten months wochen weeks jahren kleinkind kleinkinder schulkinder "
        "grundschüler grundschueler zwilling enkel enkelin enkelkind enkelkinder kindern "
        "jährig jaehrig jährige jährigen jaehrige jaehrigen yrs yr yo mo sick ill accessible "
        "cold sprained hurt kid ramp jabs gips weather"
    ).split()
)
# "Seven Berlin" is an age before a city, not a town ("Seven Sisters").
_KNOWN_CITIES = frozenset(
    word.casefold() for cities in config.CITIES.values() for c in cities for word in c.split()
)
_AFTER_NUMBER_WORDS = frozenset(
    "bis to und and unter under ab over über monate monaten months wochen weeks jahre jahren "
    "years tage days".split()
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
# Only used with fullmatch on one word of a value capped at 40 characters; possessive anyway.
_APOSTROPHE_WORD = re.compile(r"[^\W\d_]++['’]s|[dDlLoO]['’][A-ZÀ-Þ][^\W\d_]*+")
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
    # An empty value (only spaces or tabs) is refused like any other bad value, never a crash.
    if not value or value != unicodedata.normalize("NFKC", value) or len(value) > _PLACE_MAX_CHARS:
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
            # Only as the first word, before a capitalised word that is no number, range word
            # or time unit ("Drei Gleichen", not "Sechs Bis Neun" or "Fünf Monate").
            following = bares[i + 1] if i + 1 < len(bares) else ""
            if (
                i != 0
                or not following[:1].isupper()
                or _NUMBER_WORD.fullmatch(following)
                or following.casefold() in _AFTER_NUMBER_WORDS
                or following.casefold() in _KNOWN_CITIES
            ):
                raise error
        # An apostrophe only in "King's" or before a capital ("d'Alene", "L'Isle").
        apostrophe = "'" in bare or "’" in bare
        if apostrophe and not _APOSTROPHE_WORD.fullmatch(bare):
            raise error
        if not bare or not (bare[0].isupper() or bare in _PLACE_CONNECTORS or apostrophe):
            raise error
        # Words about a family or instructions are never part of a town's name.
        if bare.casefold() in _NOT_PLACE_WORDS or re.search(r"j(?:ä|ae)hrig", bare.casefold()):
            raise error
    # A dot followed by two letters (evil.example) is a domain; "St. Peter", "D.C." are not.
    if re.search(r"\.[^\W\d_]{2}", value) or find_sensitive(value):
        raise error
    return value
