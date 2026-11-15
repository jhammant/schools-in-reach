"""Publication gate and method counts for automatically read PTA accounts.

Only load() reads the optional input. It returns extracted records after the human
spot check passes; renderers receive that mapping, never the unchecked file.
No figures here feed the school's income, per-pupil or comparison calculations.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

SPOT_CHECK_MIN = 10
REGISTER_HOST = "register-of-charities.charitycommission.gov.uk"


def gate_reason(doc) -> str | None:
    """Why publication is blocked, or None for an integer sample >= 10 with no errors."""
    spot = doc.get("spot_check") if isinstance(doc, dict) else None
    if not isinstance(spot, dict):
        return "no spot check recorded"
    n, wrong = spot.get("n"), spot.get("wrong")
    if type(n) is not int or n < SPOT_CHECK_MIN:
        return f"spot check must cover at least {SPOT_CHECK_MIN} accounts"
    if type(wrong) is not int or wrong != 0:
        return "spot check must record zero wrong"
    return None


def register_source(url) -> bool:
    """Only an HTTPS link to the register can be used as the accounts source."""
    if not isinstance(url, str) or any(ord(c) < 32 for c in url):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname == REGISTER_HOST
                and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except ValueError:
        return False


def load(path, log=print) -> dict:
    """Fail closed for absent, unreadable or unchecked input; never write to the cache."""
    if path is None:
        log("PTA accounts hidden: no accounts file supplied")
        return {}
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        log("PTA accounts hidden: accounts file missing")
        return {}
    except (OSError, ValueError):
        log("PTA accounts hidden: accounts file could not be read")
        return {}
    reason = gate_reason(doc)
    if reason:
        log(f"PTA accounts hidden: {reason}")
        return {}
    records = {number: record for number, record in doc.items()
               if number.isdigit() and isinstance(record, dict) and record.get("extracted") is True
               and isinstance(record.get("facts"), dict) and register_source(record.get("source_url"))}
    log(f"PTA accounts: spot check passed; {len(records)} extracted records with a register source")
    return records


# Deliberately small: group clear wording variants, never guess an unfamiliar method.
# Multiple categories can be mentioned in one line (for example "fair and raffle").
METHOD_KEYWORDS = {
    "Fairs": r"fairs?|fetes?",
    "Discos": r"discos?",
    "Cake sales": r"cakes? (?:sales?|stalls?)|bake sales?",
    "Non-uniform days": r"non ?uniform|mufti|dress down|own clothes",
    "Uniform sales": r"uniform (?:sales?|shops?|stalls?)",
    "Raffles and lotteries": r"raffles?|lotter(?:y|ies)|(?:100|200) clubs?",
    "Quiz nights": r"quiz|quizzes",
    "Gift Aid": r"gift ?aid|gasds",
    "Match funding": r"match(?:ed)? (?:funding|funds|giving|donations?)",
    "Grants": r"grants?",
    "Sponsored events": r"sponsored",
    "Online shopping platforms": r"easy ?fundraising|amazon ?smile|the ?giving ?machine|give as you live|online shopping",
    "Donations": r"donations?",
}
METHOD_PATTERNS = {label: re.compile(r"\b(?:" + pattern + r")\b") for label, pattern in METHOD_KEYWORDS.items()}


def normalise_methods(text) -> set[str]:
    """Known method labels mentioned in text, ignoring case, punctuation and accents."""
    if not isinstance(text, str):
        return set()
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return {label for label, pattern in METHOD_PATTERNS.items() if pattern.search(text)}


def method_counts(records) -> Counter:
    """Count each method once per charity, including named shopping platforms and Gift Aid."""
    counts = Counter()
    for record in records.values():
        facts = record["facts"]
        methods = set()
        for entry in facts.get("how_raised") or []:
            if isinstance(entry, dict):
                methods.update(normalise_methods(entry.get("method")))
        for platform in facts.get("platforms") or []:
            methods.update(normalise_methods(platform))
        gift = facts.get("gift_aid")
        if type(gift) in (int, float) and gift > 0:
            methods.add("Gift Aid")
        counts.update(methods)
    return counts
