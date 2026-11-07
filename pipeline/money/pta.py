"""Match parents' association charities to English schools, high confidence only.

Reads the Charity Commission register extract (large JSON arrays, streamed) and the
site's school register, and writes pta.json: for each matched school the charities that
raise money for it, newest first, with their annual return history.

Pass 1 anchors a charity to a school through its contact postcode or website. Pass 2
works on what pass 1 left: exact postcode either way round, web or email domain, GIAS
predecessor names, a name unique within the charity's council area, the school named in
the charitable objects, and the address town. Every pass-2 rule runs through the same
guards (independent schools block but are never targets, removed-before-opened, activity
words, risk flags that need a postcode or domain to agree, rule conflicts). Wider supporters'
names ('Friends of X', P.T.A., Parent/Teacher, Families & Staff, Supporters of) and the broad
tier (a school fund or society whose activities say parents raise money for the school) are
placed only by an exact postcode or a shared domain. A PTA serving an infant and a junior
school goes to both, with shared_with. Charities that still fit several schools go to
pta_ambiguous.jsonl for pta_adjudicate.py, whose accepted answers merge back with method
"llm" only once a person's spot check of 50 found none wrong; a school-website crawl merges
with method "website-crawl", or adds 'website' to the evidence of a match it confirms.
Every record carries history_status, last_income_year and removed_year.

A wrong match attributes a charity's money to the wrong school in public, so every rule
here errs towards missing a real PTA rather than inventing one.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

MAIN = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
CHARITY_DIR = MAIN / "pipeline/.cache/charity"
SITE_DATA = MAIN / "site/data"
LINKS = MAIN / "pipeline/.cache/dfe/gias/links.csv"
MONEY_DIR = MAIN / "pipeline/.cache/money"
OUT = MONEY_DIR / "pta.json"
AMBIGUOUS = MONEY_DIR / "pta_ambiguous.jsonl"
LLM = MONEY_DIR / "pta_llm.json"
CRAWL = MONEY_DIR / "pta_crawl.json"
REPORT = Path(__file__).resolve().parent / "REPORT_pta.md"
LICENCE = "Open Government Licence v3.0 (Charity Commission register)"
SOURCE = "Charity Commission register of charities, full extract"

# ----------------------------------------------------------------- names

# Phrases removed before tokenising, so 'C of E' and 'Church of England' cannot leak tokens.
PHRASES = [
    r"church\s+of\s+england", r"\bc\s*\.?\s*of\s*\.?\s*e\b", r"roman\s+catholic",
    r"voluntary\s+(aided|controlled)", r"parent[s']*[\s-]*(teacher|staff)[s']*",
    r"home[\s-]*school", r"pre[\s-]*school", r"all[\s-]*through",
]
GENERIC = {
    "the", "of", "and", "a", "an", "in", "at", "for", "to", "with", "on",
    "school", "schools", "primary", "infant", "infants", "junior", "juniors", "academy",
    "academies", "ce", "cofe", "coe", "rc", "catholic", "voluntary", "aided", "controlled",
    "community", "nursery", "foundation", "federation", "trust", "pta", "ptfa", "pfa", "psa",
    "hsa", "fos", "ptsa", "fsa", "pa", "parent", "parents", "teacher", "teachers", "friend",
    "friends", "association", "assoc", "assn", "staff", "home", "fund", "funds", "st", "saint",
    "college", "high", "secondary", "middle", "first", "lower", "upper", "prep", "preparatory",
    "preschool", "church", "england", "roman", "limited", "ltd", "cio", "charity", "charitable",
    "va", "vc", "jmi", "jm", "ci", "county", "council", "combined", "endowed", "free", "grammar",
    "specialist", "special", "sports", "arts", "science", "technology", "language", "music",
    "learning", "centre", "center", "campus", "group", "society", "committee", "club", "support",
    "supporters", "supporter", "familie", "parentteacher", "pre", "day", "independent", "international", "national",
}
SCHOOL_WORDS = re.compile(
    r"\b(school|schools|primary|infant|infants|junior|juniors|academy|academies|nursery|college|"
    r"pre[\s-]*school|preschool|kindergarten|prep|preparatory|sch)\b", re.I)
# Explicit parents' association markers: enough on their own.
PARENT_MARKERS = re.compile(
    r"\b(pta|ptfa|pfa|psa|hsa|fos|ptsa)\b|parent[s']*[\s-]*(teacher|staff|and\s+friends|&\s+friends|"
    r"teachers|friends|association|assoc)|parents'?\s+association|home[\s-]*school\s+association|"
    r"parent[\s-]*teacher", re.I)
# Weaker markers: only a candidate when the name also mentions a school.
WEAK_MARKERS = re.compile(r"\bfriends\s+of\b|\bschool\s+association\b|\bparents?\b", re.I)
# A charity whose name adds one of these words beside the school's is something else parents run.
EXCLUDED = {"toddler", "playgroup", "play", "scout", "guide", "cub", "brownie", "chapel", "choir", "band", "orchestra",
            "swimming", "pool", "youth", "mosque", "prize", "bursary", "bursarie"}
# 'X School for Girls' is not 'X School' unless the register says X School is a girls' school.
GENDER = {"girl": "Girls", "boy": "Boys"}
# Words that say which part of the school system a name belongs to.
PHASE = {"infant", "junior", "nursery", "primary", "first", "middle", "high", "secondary", "grammar",
         "college", "sixth", "upper", "lower", "prep", "senior", "comprehensive"}
INFANT, JUNIOR = {"infant", "nursery"}, {"junior"}
PRIMARY = {"infant", "nursery", "junior", "primary", "first", "middle", "prep", "lower"}
SECONDARY = {"high", "secondary", "grammar", "college", "sixth", "upper", "senior", "comprehensive"}
# GIAS phase of education, as a phase word (G8).
GIAS_PHASE = {"Primary": {"primary"}, "Secondary": {"secondary"}, "Nursery": {"nursery"}}
GENERIC_HOSTS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "pta-events.co.uk", "ptaevents.co.uk",
    "pta-events.com", "classlist.com", "justgiving.com", "localgiving.org", "wix.com", "weebly.com",
    "wordpress.com", "google.com", "sites.google.com", "gov.uk", "charitycommission.gov.uk",
    "linktr.ee", "easyfundraising.org.uk", "parentkind.org.uk", "pta.co.uk", "ptasocial.com",
}
# Email providers whose domain says nothing about the school (pass-2 rule d).
WEBMAIL = re.compile(r"^(gmail|googlemail|hotmail|yahoo|ymail|btinternet|btopenworld|btconnect|outlook|live|icloud|me|mac|"
                     r"aol|sky|talktalk|talk21|virginmedia|virgin|ntlworld|tiscali|blueyonder|msn|mail|protonmail|proton|"
                     r"gmx|zoho|orange|waitrose|tesco|freeserve|lineone|fsnet|onetel|plus|supanet|uwclub|clara|nhs|"
                     r"fastmail|yandex)\.", re.I)


def _tokens(name) -> list[str]:
    """Every word of a name, lowercased, de-possessived, singular, St for Saint."""
    text = str(name or "").lower().replace("&", " and ")
    text = text.replace("’", "'").replace("'s", "").replace("'", "")
    for phrase in PHRASES:
        text = re.sub(phrase, " ", text)
    tokens = []
    for raw in re.findall(r"[a-z0-9]+", text):
        tok = "st" if raw == "saint" else "prep" if raw == "preparatory" else raw
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        tokens.append(tok)
    return tokens


def normalise(name) -> list[str]:
    """Distinctive tokens of a school or charity name, generic words removed."""
    tokens = []
    for tok in _tokens(name):
        if len(tok) < 2 or tok in GENERIC or tok in tokens:
            continue
        tokens.append(tok)
    return tokens


def phase_words(name) -> set[str]:
    """Phase words (infant, junior, high...) in a name."""
    return PHASE & set(_tokens(name))


def phases_conflict(school_phase, charity_phase) -> bool:
    """True when the two names clearly belong to different parts of the system."""
    if not school_phase or not charity_phase or school_phase & charity_phase:
        return False
    return bool((school_phase & INFANT and charity_phase & JUNIOR) or (school_phase & JUNIOR and charity_phase & INFANT)
                or (school_phase & PRIMARY and charity_phase & SECONDARY and not school_phase & SECONDARY)
                or (school_phase & SECONDARY and charity_phase & PRIMARY and not school_phase & PRIMARY))


def conflict(school_phase, charity_phase) -> bool:
    """Pass-1 phase conflict, plus 'High School' never meets 'Grammar School' (G7)."""
    if phases_conflict(school_phase, charity_phase):
        return True
    return bool(("high" in charity_phase and "grammar" in school_phase and "high" not in school_phase)
                or ("grammar" in charity_phase and "high" in school_phase and "grammar" not in school_phase))


# Charities that sound like a parents' association but run something else: a pre-school, a club, the school itself.
NOT_PTA = re.compile(r"\bpre[\s-]?schools?\b|\bplay\s?groups?\b|\btoddlers?\b|\bkindergartens?\b|\bafter[\s-]school\b|"
                     r"\bout\s+of\s+school\b|\bbreakfast\s+club\b|\bholiday\s+club\b|\balumni\b|\bold\s+(boys|girls)\b|"
                     r"\bformer\s+pupils\b", re.I)
# A parents' association this large is more likely a school-owning or endowment charity: shown only after a manual check.
REVIEW_INCOME = 500_000
# Activity words that make a charity a music, sport or minibus group rather than a PTA (G3). Tested only on the words
# left over after the school's own name and place, so 'Holmes Chapel' and 'Rugby High' survive.
OUT_OF_SCOPE = {t for w in """music band orchestra choir choral swimming sport drama theatre minibus bursary bursaries prize
scholarship alumni chapel scout guide playgroup toddler rowing boat cricket football rugby tennis hockey netball cadet
gymnastics gym dance athletics library museum heritage history""".split() for t in _tokens(w)}
# Saints and religious words: a match made only of these needs a postcode or domain to agree (G4 saint_only).
RELIGIOUS = {t for w in """mary john joseph peter paul george michael andrew james luke mark matthew thomas anne margaret
patrick bernadette teresa francis anthony augustine edmund edward stephen nicholas chad cuthbert bede alban benedict catherine
helen giles lawrence leonard martin oswald philip barnabas bartholomew clement gregory hilda jude laurence saviour saint all holy
trinity cross family spirit ghost name rosary lady sacred heart christ angel blessed immaculate conception redeemer jesus wilfrid
aidan hugh dunstan alphege swithun boniface elizabeth agnes winifred monica vincent dominic ignatius columba bridget brigid joan
more fisher oliver plunkett pius our saints apostle apostles mother god faith hope charity""".split() for t in _tokens(w)}
BIG_PLACE = 8  # a town with more schools than this cannot anchor a match on its own name
# Words that end a backwards walk from a school word in objects / area-of-benefit text (rule b).
SCHOOL_WORD_TOKENS = {"school", "primary", "academy", "infant", "junior", "college", "nursery", "high"}
WALK_SKIP = SCHOOL_WORD_TOKENS | {"ce", "rc", "cofe", "va", "vc", "jmi", "jm", "and", "c", "e"}
WALK_STOP = {"of", "at", "in", "the", "for", "by", "to", "practice", "defined", "area", "catchment", "pupil",
             "student", "children", "child", "parent", "staff", "attending", "benefit", "education", "advance",
             "friend", "association", "support", "within", "from", "who", "which", "whom", "said", "known", "as",
             "being", "attend", "former", "past", "present", "and", "or", "a", "an", "with", "on", "not", "its",
             "their", "his", "her"} | SCHOOL_WORD_TOKENS
# Address lines that are counties or countries, not towns (rule e, ambiguous export).
COUNTIES = {x.lower() for x in """Bedfordshire Berkshire Bristol Buckinghamshire Cambridgeshire Cheshire Cornwall Cumbria
Derbyshire Devon Dorset Durham Essex Gloucestershire Hampshire Herefordshire Hertfordshire Kent Lancashire Leicestershire
Lincolnshire Norfolk Northamptonshire Northumberland Nottinghamshire Oxfordshire Rutland Shropshire Somerset Staffordshire
Suffolk Surrey Warwickshire Wiltshire Worcestershire Middlesex Merseyside Yorkshire Herts Hants Beds Bucks Berks Glos Lancs
Leics Lincs Northants Notts Oxon Staffs Wilts Worcs Warks Cambs Derbys Mersey""".split()} | {
    "west sussex", "east sussex", "greater london", "greater manchester", "west midlands", "west yorkshire",
    "south yorkshire", "north yorkshire", "east yorkshire", "east riding of yorkshire", "tyne and wear", "isle of wight",
    "county durham", "co durham", "uk", "united kingdom", "england", "cleveland", "avon", "humberside", "n yorks",
    "w yorks", "s yorks", "w sussex", "e sussex", "west mids"}
# Charity Commission local-authority names that cover more than one current English council.
COUNCIL_SPLITS = {
    "cumbria": ["Cumberland", "Westmorland and Furness"],
    "northamptonshire": ["North Northamptonshire", "West Northamptonshire"],
    "bournemouth": ["Bournemouth, Christchurch and Poole"],
    "poole": ["Bournemouth, Christchurch and Poole"],
    "dorset": ["Dorset", "Bournemouth, Christchurch and Poole"],  # Christchurch moved to BCP in 2019
    "durham": ["County Durham"],
    "herefordshire": ["Herefordshire, County of"],
}
RULE_ORDER = ["f", "d", "c", "a", "b", "e"]
RULE_METHOD = {"f": "postcode-exact", "d": "domain", "c": "predecessor", "a": "council-unique", "b": "objects", "e": "address-town"}
NAME_RULES = set("abce")  # rules that rest on the name alone: a G4 flag on them needs d or f to agree
STATE_EXCLUDED_GROUPS = {"Independent schools", "Colleges", "Universities"}
# Crawl evidence that says a charity is a parents' association even when its name does not: whole PTA words only, so
# 'transparent' or 'parent' alone never counts.
CRAWL_WORDS = re.compile(r"\b(?:p\.?\s?t\.?\s?f?\.?\s?a|pfa|psa|hsa|fsa|ptsa|fos)\b|\bfriends\s+of\b|\bthe\s+friends\b|\bschool\s+association\b|"
                         r"\bparents?['’]?\s*(?:and|&)\s*friends\b|\bparent[s'’]*[\s/-]*(?:teacher|staff)s?\b|"
                         r"\bparents?['’]?\s+association\b|\bhome[\s-]+school\s+association\b|\bfamil(?:y|ies)\s*(?:and|&)\s*staff\b",
                         re.I)
# Wider name forms (crawl_spec.md section 5, web tier) that pass 1's filter misses: 'Friends of X' with no school word,
# dotted P.T.A., Parent/Teacher, Families & Staff, Supporters of. Loose by design, so pass 2 accepts them only through
# an anchor: the exact postcode (rule f) or a shared web or email domain (rule d), plus a shared distinctive word.
WIDE_NAME = re.compile(r"\bfriends\b|\bparents?\b|famil(?:y|ies)\s*(?:and|&)\s*staff|\bsupporters\b|"
                       r"\b(?:pta|ptfa|pfa|psa|hsa|fsa|ptsa|fos|fofs)\b|\bp\.\s?t\.\s?(?:f\.\s?)?a\b|"
                       r"\bschool\s+(?:association|society)\b", re.I)
# Without a school word, a supporters' name is as likely a church, park or hospital friends group.
WIDE_VETO = re.compile(r"\bchurch\b|chapel|parish|hospital|hospice|library|museum|cathedral|abbey|theatre|wildlife|"
                       r"nature|village\s+hall|community\s+cent|scouts?\b|guides?\b|\bpark\s+trust|railway|canal|"
                       r"\bearth\b|refugee|overseas|africa|india|kenya|uganda|gambia|nepal|romania|league\s+of\s+friends|"
                       r"society\s+of\s+friends|medical|health|graveyard|cemetery|monument|handicap|mental|\bschool\s+fund\b",
                       re.I)
# Health charities are never a school's PTA unless the name says school: 'Friends of King's College Hospital' carries
# a school word ('college') yet supports the hospital, and a hospital school shares the hospital's postcode.
WIDE_HEALTH = re.compile(r"hospital|hospice|infirmary|\bnhs\b|medical|\bhealth\b", re.I)
# Parents' groups that are not a school's PTA, whatever else the name says.
WIDE_NOT_PTA = re.compile(r"supplementary|\bcarers?\b|parent\s+and\s+(?:child|toddler)|foster|adopt|deaf|blind|disab|"
                          r"autis|bereave|\bmusic|\bband\b|orchestra|choir|sport|swim|minibus|bursar|scholarship|alumni|"
                          r"old\s+(?:boys|girls)", re.I)
# Wording that names a parent-teacher association outright, unlike 'Friends of' or 'Supporters of': dotted P.T.A.,
# Parent/Teacher, a PTA acronym, Families & Staff. A wider name carrying one may rest on a saint's name, as pass 1's do.
EXPLICIT_PTA = re.compile(r"\bp\.\s?t\.\s?(?:f\.\s?)?a\b|\bparents?\s*[/&+]\s*teachers?\b|\b(?:pta|ptfa|pfa|psa|hsa|fsa|ptsa)\b|"
                          r"famil(?:y|ies)\s*(?:and|&)\s*staff", re.I)
# Broad tier (crawl_spec.md section 5): a supporters' word in a school-ish name, and activities about parents raising
# money for a school or its pupils. Like the web tier, matched only through rule (f) or (d).
BROAD_NAME = re.compile(r"\b(?:friends|parents?|supporters|association|fund|society|committee)\b", re.I)
BROAD_VETO = re.compile(r"pre\s*-?\s*school|supplementary|carers?\b|parent\s+and\s+(?:child|toddler)|\bchurch\b|parish|"
                        r"sunday|\bmusic|\bband\b|orchestra|choir|sport|swim|minibus|bursar|scholarship|alumni|"
                        r"old\s+(?:boys|girls)|foster|adopt|deaf|blind|disab|autis|bereave", re.I)
ACTIVITY_PARENTS = re.compile(r"\bparents?\b|\bp\.?t\.?a\b|\bptfa\b|\bfriends\s+of\b", re.I)
ACTIVITY_MONEY = re.compile(r"fund|rais|event|social|donat|equipment|resources", re.I)
ACTIVITY_SCHOOL = re.compile(r"\bschool|\bpupil|\bacademy|\bchildren", re.I)


def excluded_leftover(r, ctok) -> bool:
    """True when the charity name adds a word that makes it something other than this school's PTA: an activity
    or group word, or a gender the register does not give the school."""
    left = ctok - set(r["tokens"])
    if left & EXCLUDED:
        return True
    return any(GENDER[w] != r.get("gender") for w in left & set(GENDER))


def is_parent_association(name) -> bool:
    """True when a charity name reads as a school parents' association."""
    text = str(name or "")
    if NOT_PTA.search(text):
        return False
    if PARENT_MARKERS.search(text):
        return True
    if WIDE_HEALTH.search(text) and not re.search(r"\bschool\b", text, re.I):
        return False  # 'Friends of King's College Hospital': 'college' is not a school here
    return bool(WEAK_MARKERS.search(text) and SCHOOL_WORDS.search(text))


def is_widened_name(name) -> bool:
    """True for the wider supporters' name forms (web tier) that is_parent_association misses. Such a charity is only
    ever matched through an exact postcode or a shared domain (pass-2 rules f and d)."""
    text = str(name or "")
    if is_parent_association(text) or NOT_PTA.search(text) or WIDE_NOT_PTA.search(text) or not WIDE_NAME.search(text):
        return False
    if WIDE_HEALTH.search(text) and not re.search(r"\bschool\b", text, re.I):
        return False
    return bool(SCHOOL_WORDS.search(text) or not WIDE_VETO.search(text))


def is_broad_candidate(charity) -> bool:
    """True for the broad tier (crawl_spec.md section 5) that neither is_parent_association nor is_widened_name takes:
    'Woodlea School Fund' whose charity_activities say parents raise money for the school or its pupils."""
    name = str(charity.get("charity_name") or "")
    if is_parent_association(name) or NOT_PTA.search(name) or BROAD_VETO.search(name):
        return False
    if WIDE_HEALTH.search(name) and not re.search(r"\bschool\b", name, re.I):
        return False
    if not (BROAD_NAME.search(name) and (SCHOOL_WORDS.search(name) or WEAK_MARKERS.search(name))):
        return False
    activities = str(charity.get("charity_activities") or "")
    return bool(ACTIVITY_PARENTS.search(activities) and ACTIVITY_MONEY.search(activities) and ACTIVITY_SCHOOL.search(activities))


def is_widened(charity) -> bool:
    """A wider-name charity (web or broad tier): matched only by an exact postcode or a shared domain."""
    return is_widened_name(charity.get("charity_name")) or is_broad_candidate(charity)


def is_state_funded(school) -> bool:
    """State-funded schools are match targets; independents, colleges and universities only block."""
    return not (school.get("type_group") in STATE_EXCLUDED_GROUPS or "independent" in str(school.get("type") or "").lower())


# ------------------------------------------------------------- postcodes

def norm_postcode(raw) -> str | None:
    text = re.sub(r"\s+", "", str(raw or "")).upper()
    return text if re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}", text) else None


def postcode_parts(pc) -> tuple[str, str]:
    """(district, sector) of a normalised postcode."""
    return pc[:-3], pc[:-2]


def postcode_area(pc) -> str | None:
    """The letters of a normalised postcode (GU, N, PO)."""
    m = re.match(r"[A-Z]+", pc or "")
    return m.group(0) if m else None


def domain(url) -> str | None:
    """Registrable host of a website, ignoring www. and known generic hosts."""
    text = str(url or "").strip().lower()
    if not text:
        return None
    if "://" not in text:
        text = "http://" + text
    host = (urlsplit(text).hostname or "").strip(".")
    host = host[4:] if host.startswith("www.") else host
    if "." not in host or host in GENERIC_HOSTS or any(host.endswith("." + g) for g in GENERIC_HOSTS):
        return None
    return host


def email_domain(raw) -> str | None:
    """Host of a contact email, unless it is a webmail provider."""
    m = re.search(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", str(raw or ""))
    if not m:
        return None
    host = m.group(1).lower().strip(".")
    if WEBMAIL.match(host):
        return None
    return host[4:] if host.startswith("www.") else host


def norm_place(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def charity_town(address_lines) -> str | None:
    """Best guess at the post town of a charity's contact address: the last line that is not a county."""
    lines = [a for a in address_lines if a and norm_place(a)]
    for line in reversed(lines):
        if norm_place(line) not in COUNTIES and not re.search(r"\d", line):
            return line.strip().title()
    return lines[-1].strip().title() if lines else None


# -------------------------------------------------------------- councils

def la_key(name) -> str:
    text = str(name or "").lower().replace("&", "and").replace(".", "")
    text = re.sub(r",?\s*(city|county) of$", "", text)
    text = re.sub(r"^(city|county) of\s+", "", text)
    text = re.sub(r"\s+city$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def council_codes(description, councils) -> list[str]:
    """la_codes for a Charity Commission 'Local Authority' area description; [] for Welsh and unknown areas."""
    key = la_key(description)
    by_name = {name: code for code, name in councils.items()}
    if key in COUNCIL_SPLITS:
        return sorted(by_name[n] for n in COUNCIL_SPLITS[key] if n in by_name)
    by_key = {la_key(name): code for code, name in councils.items()}
    return [by_key[key]] if key in by_key else []


# ----------------------------------------------------------------- match

def _date(raw):
    return str(raw)[:10] if raw else None


def _school_record(school):
    pc = norm_postcode(school.get("postcode"))
    district, sector = postcode_parts(pc) if pc else (None, None)
    place = " ".join(str(school.get(k) or "") for k in ("town", "locality", "street", "council"))
    return {
        "urn": str(school["urn"]), "name": school.get("name") or "", "tokens": normalise(school.get("name")),
        "phase": phase_words(school.get("name")), "gphase": GIAS_PHASE.get(school.get("phase"), set()),
        "gphase_raw": str(school.get("phase") or ""),
        "place": set(normalise(place)), "town": str(school.get("town") or ""),
        "la": str(school.get("la_code") or ""), "la_name": str(school.get("council") or ""),
        "postcode": pc, "postcode_raw": school.get("postcode"), "district": district, "sector": sector,
        "domain": domain(school.get("website")), "open_date": _date(school.get("open_date")),
        "state": is_state_funded(school), "gender": school.get("gender"), "preds": [],
    }


def _charity_record(charity, method, evidence, confidence="high"):
    return {
        "charity_number": int(charity["registered_charity_number"]),
        "name": charity.get("charity_name") or "",
        "status": charity.get("charity_registration_status") or "",
        "registered": _date(charity.get("date_of_registration")),
        "removed": _date(charity.get("date_of_removal")),
        "latest_income": charity.get("latest_income"),
        **({"review": f"income over £{REVIEW_INCOME:,}: check it is a parents' association"}
           if (charity.get("latest_income") or 0) > REVIEW_INCOME else {}),
        "history": [],
        "match": {"method": method, "evidence": evidence, "confidence": confidence},
    }


def _closed(school) -> bool:
    return "closed" in str(school.get("status") or "").lower()


def match(schools, charities):
    """Pass 1, pure: (matches by urn, rejections). Schools and charities are raw dicts.

    Independent schools, colleges and universities take part as blockers (a PTA whose name fits one is
    never handed to a state namesake) but are never matched themselves (G1).
    """
    recs = [r for r in (_school_record(s) for s in schools if not _closed(s)) if r["tokens"]]
    by_postcode, by_sector, by_domain, by_district = (defaultdict(list) for _ in range(4))
    for r in recs:
        if r["postcode"]:
            by_postcode[r["postcode"]].append(r)
            by_sector[r["sector"]].append(r)
            by_district[r["district"]].append(r)
        if r["domain"]:
            by_domain[r["domain"]].append(r)

    matches = defaultdict(list)
    rejections = []
    seen = {}  # charity number -> urn, to catch one charity matching several schools

    def reject(charity, reason, names):
        rejections.append({"charity_number": int(charity["registered_charity_number"]),
                           "charity": charity.get("charity_name") or "", "reason": reason, "schools": names})

    for charity in charities:
        if charity.get("linked_charity_number", 0) not in (0, 1) or not is_parent_association(charity.get("charity_name")):
            continue
        ctokens = set(normalise(charity.get("charity_name")))
        if not ctokens:
            continue
        cphase = phase_words(charity.get("charity_name"))
        pc = norm_postcode(charity.get("charity_contact_postcode"))
        host = domain(charity.get("charity_contact_web"))

        def fits(r):
            return set(r["tokens"]) <= ctokens and not phases_conflict(r["phase"], cphase) and not excluded_leftover(r, ctokens)

        candidates, ambiguous = {}, []
        if pc:
            for r in by_postcode.get(pc, []):
                if fits(r):
                    candidates[r["urn"]] = (r, "postcode", f"tokens {','.join(r['tokens'])}; postcode {pc}")
            for r in by_sector.get(pc[:-2], []):
                if r["urn"] in candidates or not fits(r):
                    continue
                # A sector is a weaker signal: the charity must name only the school (plus its own place names),
                # and no other school in the district may carry the same distinctive name.
                if ctokens - set(r["tokens"]) - r["place"]:
                    continue
                shared = [o for o in by_district[r["district"]] if o is not r and set(o["tokens"]) == set(r["tokens"])]
                if shared:
                    ambiguous.append((r, shared))
                    continue
                candidates[r["urn"]] = (r, "sector", f"tokens {','.join(r['tokens'])}; sector {pc[:-2]}, unique in {r['district']}")
        if host:
            for r in by_domain.get(host, []):
                if r["urn"] not in candidates and fits(r):
                    candidates[r["urn"]] = (r, "website", f"tokens {','.join(r['tokens'])}; website {host}")
        if not candidates:
            if ambiguous:
                # The only lead was a sector match blocked by a namesake: record it so the report shows it.
                names = sorted({o["name"] for r, shared in ambiguous for o in [r, *shared]})
                reject(charity, "another school in the district shares the name", names)
            continue

        # The most specific candidates, plus any state school in their districts whose name also fits the
        # charity with at least as many distinctive words ('Park Primary' never blocks 'Whitelands Park Primary').
        best = max(len(c[0]["tokens"]) for c in candidates.values())
        candidates = {urn: c for urn, c in candidates.items() if len(c[0]["tokens"]) == best}
        if not any(c[0]["state"] for c in candidates.values()):
            reject(charity, "belongs to an independent school", [c[0]["name"] for c in candidates.values()])
            continue
        # An independent school counts here only when its name fits the charity more fully than any candidate's
        # ('Friends of Woodlea Park School' near Woodlea Primary on Park Road): an equal-length independent namesake
        # elsewhere in the district never vetoes an exact postcode, and the sector rule already checks those.
        tied = {urn: c[0] for urn, c in candidates.items()}
        for r, _, _ in candidates.values():
            for o in by_district.get(r["district"], []):
                if o["urn"] in tied or not set(o["tokens"]) <= ctokens or len(o["tokens"]) < best:
                    continue
                if o["state"] or (len(o["tokens"]) > best and not phases_conflict(o["phase"], cphase)):
                    tied[o["urn"]] = o
        longer = [o["name"] for o in tied.values() if not o["state"] and len(o["tokens"]) > best]
        if longer:
            reject(charity, "belongs to an independent school", longer)
            continue
        chosen = None
        if len(tied) == 1:
            chosen, = candidates
        elif cphase:
            # 'X Junior School PTA' settles an infant/junior tie only when every other tied school's own phase
            # words clearly conflict with the charity's. A school with no phase words cannot be ruled out.
            survivors = [urn for urn, o in tied.items() if not phases_conflict(o["phase"], cphase)]
            if len(survivors) == 1 and survivors[0] in candidates:
                chosen = survivors[0]
        if chosen is None:
            reason = "charity fits several schools" if len(candidates) > 1 else "another school in the district also fits"
            reject(charity, reason, [o["name"] for o in tied.values()])
            continue
        r, method, evidence = candidates[chosen]
        if not r["state"]:
            reject(charity, "belongs to an independent school", [r["name"]])
            continue
        if len(tied) > 1:
            evidence += f"; phase {','.join(sorted(cphase))} rules out {len(tied) - 1}"
        number = int(charity["registered_charity_number"])
        if number in seen and seen[number] != r["urn"]:
            reject(charity, "charity fits several schools", [seen[number], r["name"]])
            matches[seen[number]] = [c for c in matches[seen[number]] if c["charity_number"] != number]
            continue
        seen[number] = r["urn"]
        matches[r["urn"]].append(_charity_record(charity, method, evidence))
    for urn in list(matches):
        matches[urn].sort(key=lambda c: c["registered"] or "", reverse=True)
        if not matches[urn]:
            del matches[urn]
    return dict(matches), rejections


# ---------------------------------------------------------------- pass 2

def school_phase(r) -> set[str]:
    """Phase words of a school's name plus its GIAS phase (G8)."""
    return set(r["phase"]) | set(r["gphase"])


def _fits(r, tokens, phase, ctok, cphase) -> bool:
    return (bool(tokens) and set(tokens) <= ctok and not conflict(phase, cphase)
            and not excluded_leftover({"tokens": tokens, "gender": r.get("gender")}, ctok))


def fits_at_postcode(r, ctok, cphase) -> bool:
    """Rule (f)'s name test for a school at the charity's own postcode: the names fit either way round (the school's
    words all in the charity's, or the charity's all in the school's name and place), with no phase clash or activity
    word."""
    tokens = set(r["tokens"])
    return bool(tokens and not conflict(school_phase(r), cphase) and not excluded_leftover(r, ctok)
                and (tokens <= ctok or (ctok <= tokens | r["place"] and ctok & tokens)))


def pick(entries, ctok, cphase):
    """Pass-1 tie logic over (record, tokens, phase, label) entries: the most specific fit wins, the charity's
    phase may settle a tie (a school with no phase words cannot be ruled out). Returns (chosen, tied)."""
    ok = [e for e in entries if _fits(e[0], e[1], e[2], ctok, cphase)]
    if not ok:
        return None, []
    best = max(len(e[1]) for e in ok)
    tied = [e for e in ok if len(e[1]) >= best]
    urns = {e[0]["urn"] for e in tied}
    if len(urns) == 1:
        return tied[0], tied
    if cphase:
        survivors = {e[0]["urn"] for e in tied if not conflict(e[2], cphase)}
        if len(survivors) == 1:
            return next(e for e in tied if e[0]["urn"] in survivors), tied
    return None, tied


def name_phrases(text):
    """School names mentioned in objects / area-of-benefit text: (distinctive tokens, raw span, phase words)."""
    out = []
    for seg in re.split(r"[.,;:()\n\"]|\b\d+\)", str(text or "")):
        toks = _tokens(seg)
        for i, tok in enumerate(toks):
            if tok not in SCHOOL_WORD_TOKENS:
                continue
            j = i - 1
            while j >= 0 and toks[j] in WALK_SKIP:  # 'primary school', 'c of e school'
                j -= 1
            words = []
            while j >= 0 and toks[j] not in WALK_STOP and len(words) < 6:
                words.append(toks[j])
                j -= 1
            words.reverse()
            distinct = {w for w in words if w not in GENERIC and len(w) > 1}
            span = toks[j + 1:i + 1]
            if distinct:
                out.append((frozenset(distinct), " ".join(span), PHASE & set(span)))
    return out


def out_of_scope_words(charity_name, r) -> set[str]:
    """Activity words in the charity name that are not part of the school's own name or place (G3)."""
    left = set(_tokens(charity_name)) - set(_tokens(r["name"])) - r["place"] - set(_tokens(r["town"]))
    return left & OUT_OF_SCOPE


def _sibling(r, by_district):
    """The other half of an infant/junior pair: same distinctive name and district, the complementary phase word."""
    mine = r["phase"]
    if not (mine & INFANT or mine & JUNIOR) or not r["district"]:
        return None
    want = JUNIOR if mine & INFANT else INFANT
    sibs = [o for o in by_district.get(r["district"], []) if o is not r and o["state"] and o["tokens"]
            and set(o["tokens"]) == set(r["tokens"]) and o["phase"] & want and not o["phase"] & mine]
    return sibs[0] if len(sibs) == 1 else None


def load_predecessors(links_path, depth=3):
    """urn -> predecessor school names from GIAS links.csv (cp1252), following 'Predecessor' links up to `depth` hops."""
    links = defaultdict(list)
    with open(links_path, encoding="cp1252", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("LinkType") or "").startswith("Predecessor"):
                links[str(row["URN"]).strip()].append((str(row["LinkURN"]).strip(), (row.get("LinkName") or "").strip()))

    def walk(urn, left, seen):
        out = []
        for lurn, lname in links.get(urn, []):
            if lurn in seen:
                continue
            seen.add(lurn)
            if lname:
                out.append(lname)
            if left > 1:
                out += walk(lurn, left - 1, seen)
        return out

    return {urn: walk(urn, depth, {urn}) for urn in links}


def match_pass2(schools, charities, unmatched, areas_by_charity, objects_by_charity, predecessors, *,
                matched_urns=frozenset(), councils=None, widened=frozenset()):
    """Pass 2, pure: (new matches by urn, ambiguous rows).

    schools: raw register dicts (state and independent) with la_code/council set; charities: raw candidate dicts;
    unmatched: charity numbers pass 1 did not place; areas_by_charity: {number: [CC 'Local Authority' descriptions]};
    objects_by_charity: {number: (charitable_objects, area_of_benefit)}; predecessors: {urn: [former names]};
    matched_urns: schools already covered (for the ambiguous rows' already_matched flag); widened: numbers of
    wider-name charities (is_widened: web or broad tier), which only the anchor rules (f) and (d) may place and which are never
    exported as ambiguous.
    """
    councils = councils or {str(s.get("la_code")): s.get("council") for s in schools if s.get("la_code") and s.get("council")}
    recs = []
    for s in schools:
        if _closed(s):
            continue
        r = _school_record(s)
        r["preds"] = [n for n in predecessors.get(r["urn"], []) if n]
        recs.append(r)
    by_la, by_pc, by_sector, by_district, by_domain, by_town = (defaultdict(list) for _ in range(6))
    for r in recs:
        by_la[r["la"]].append(r)
        if r["postcode"]:
            by_pc[r["postcode"]].append(r)
            by_sector[r["sector"]].append(r)
            by_district[r["district"]].append(r)
        if r["domain"]:
            by_domain[r["domain"]].append(r)
        if norm_place(r["town"]):
            by_town[norm_place(r["town"])].append(r)
    rec_by_urn = {r["urn"]: r for r in recs}
    cands = {int(c["registered_charity_number"]): c for c in charities
             if c.get("linked_charity_number", 0) in (0, 1) and int(c["registered_charity_number"]) in unmatched}

    def entries_for(r, with_preds, cphase=frozenset()):
        """(record, tokens, phase, label) for a school's current name and, with_preds, its GIAS predecessor names.

        A predecessor name never masks the school's current GIAS phase (G8): when both the charity's phase and the
        predecessor's own phase clash with it, the predecessor is left out, so a Junior predecessor of a secondary
        academy does not let a junior PTA attach to it. 'Middle' (ages 9-13) overlaps both primary and secondary, so
        Isle of Wight middle schools' PTAs still follow them into their secondary successors, and a place word such as
        High Green in a predecessor that also says Primary is no clash."""
        out = [(r, r["tokens"], school_phase(r), "current")]
        if with_preds:
            gphase = set(r["gphase"])
            for pn in r["preds"]:
                pphase = phase_words(pn)
                if conflict(gphase, cphase - {"middle"}) and conflict(gphase, pphase - {"middle"}):
                    continue
                out.append((r, normalise(pn), pphase | gphase, "pred:" + pn))
        return out

    def one_side(cphase) -> bool:
        """The charity's name says infant or junior, but not both ('X Infant and Junior Schools PTA' is shared)."""
        return bool(cphase & INFANT) != bool(cphase & JUNIOR)

    def targets_for(r, tied, cphase):
        """Schools a charity attaches to: the chosen school with its infant/junior twin, or a twin pair that tied.

        A charity whose own name says only infant or only junior is never shared."""
        if r is not None:
            sib = None if one_side(cphase) else _sibling(r, by_district)
            return [r, sib] if sib else [r]
        urns = sorted({e[0]["urn"] for e in tied})
        if len(urns) == 2 and not one_side(cphase):
            a, b = rec_by_urn[urns[0]], rec_by_urn[urns[1]]
            if _sibling(a, by_district) is b:
                return [a, b]
        return []

    area_cache = {}

    def codes_for(number):
        out = set()
        for desc in areas_by_charity.get(number, []):
            if desc not in area_cache:
                area_cache[desc] = council_codes(desc, councils)
            out.update(area_cache[desc])
        return sorted(out)

    per_charity = defaultdict(dict)  # number -> rule -> (urns, evidence, flags)
    blocked = set()                   # a single fit that a leftover word or a rule conflict stopped

    for number, c in cands.items():
        name = c.get("charity_name") or ""
        ctok = set(normalise(name))
        cphase = phase_words(name)
        wide = number in widened
        codes = [] if wide else codes_for(number)
        pool = [r for code in codes for r in by_la.get(code, [])]
        pc = norm_postcode(c.get("charity_contact_postcode"))
        host = domain(c.get("charity_contact_web"))
        edom = email_domain(c.get("charity_contact_email"))
        objects, aob = objects_by_charity.get(number, ("", ""))
        addr = [c.get(f"charity_contact_address{i}") for i in range(1, 6)]
        removed = _date(c.get("date_of_removal"))
        council_toks = {t for code in codes for t in normalise(councils.get(code))}

        def leftover(r, toks=None):
            return ctok - set(r["tokens"] if toks is None else toks) - r["place"] - council_toks

        def predates(r):
            return bool(removed and r["open_date"] and removed < r["open_date"] and not r["preds"])

        def flags(r, toks=None):
            matched = set(r["tokens"] if toks is None else toks)
            out = []
            if matched and matched <= RELIGIOUS:
                out.append("saint_only")
            if any(o is not r and matched < set(o["tokens"]) and not conflict(school_phase(o), cphase) for o in by_la[r["la"]]):
                out.append("longer_namesake")
            if matched <= set(normalise(r["town"])) | set(normalise(r["la_name"])) and len(by_town.get(norm_place(r["town"]), [])) > BIG_PLACE:
                out.append("big_place")
            return out

        def add(rule, targets, evidence, toks=None):
            for r in targets:
                if not r["state"] or predates(r) or out_of_scope_words(name, r):  # G1, G2, G3
                    return
            per_charity[number][rule] = (tuple(sorted(r["urn"] for r in targets)), evidence, flags(targets[0], toks))

        def wide_ok(r):
            """A wider name with neither a school word nor explicit PTA wording ('Friends of Bousfield') must share a
            word with the school that is neither a saint's nor a place name, so a church or village friends group at
            the same postcode never fits. 'St Johns P.T.A.' names a parent-teacher association outright."""
            if SCHOOL_WORDS.search(name) or EXPLICIT_PTA.search(name):
                return True
            shared = ctok & set(r["tokens"])
            return bool(shared - RELIGIOUS - r["place"] - set(normalise(r["town"])))

        # (f) exact postcode: the school at the charity's address, name either way round; or an infant/junior pair on
        # one site, for a charity whose name is not one-sided
        if pc and ctok and pc in by_pc:
            here = [r for r in by_pc[pc] if fits_at_postcode(r, ctok, cphase)]
            targets = (targets_for(here[0], [], cphase) if len(here) == 1
                       else targets_for(None, [(r,) for r in here], cphase) if len(here) == 2 else [])
            if targets and (not wide or all(wide_ok(r) for r in here)):  # the anchored schools, not a twin riding along
                add("f", targets, f"postcode-exact {pc}")

        # (d) web or email domain shared with exactly one school; the names must not contradict
        for dom, kind in ((host, "website"), (edom, "email")):
            hit = by_domain.get(dom, []) if dom else []
            if len(hit) != 1:
                continue
            r = hit[0]
            shares = ctok & set(r["tokens"]) or any(ctok & set(normalise(pn)) for pn in r["preds"])
            compatible = shares if wide else (not ctok or shares)
            if compatible and not conflict(school_phase(r), cphase):
                add("d", targets_for(r, [], cphase), f"domain {dom} ({kind})")
                break

        if wide:
            continue  # the name rules below are for pass-1 names only

        # (c) predecessor names: the current name does not fit, a GIAS predecessor's does. The council pool first;
        # with nothing there, the charity's postcode sector.
        if ctok:
            scopes = [("council area", pool)]
            if pc:
                scopes.append((f"sector {pc[:-2]}", by_sector.get(pc[:-2], [])))
            for scope, local in scopes:
                chosen, tied = pick([e for r in local for e in entries_for(r, True, cphase)], ctok, cphase)
                if not chosen:
                    continue  # nothing settled here: try the next scope
                if chosen[3].startswith("pred:"):
                    r, toks = chosen[0], chosen[1]
                    if (not any(e[0] is r and e[3] == "current" for e in tied)
                            and not _fits(r, r["tokens"], school_phase(r), ctok, cphase)):
                        if not leftover(r, toks):
                            add("c", targets_for(r, [], cphase), f"predecessor '{chosen[3][5:]}' unique in {scope}", toks)
                        else:
                            blocked.add(number)
                break

        # (a) distinctive name unique within the charity's council area(s)
        if pool and ctok:
            chosen, tied = pick([e for r in pool for e in entries_for(r, False)], ctok, cphase)
            targets = targets_for(chosen and chosen[0], tied, cphase)
            if targets:
                if not leftover(targets[0]):
                    add("a", targets, f"council-unique in {', '.join(councils.get(x, x) for x in codes)}")
                else:
                    blocked.add(number)

        # (b) objects / area of benefit names a school inside the council area
        if pool:
            hits, multi = {}, False
            for ptoks, raw, pphase in name_phrases(objects) + name_phrases(aob):
                exact = [r for r in pool if set(r["tokens"]) == ptoks and not conflict(school_phase(r), pphase | cphase)]
                if len(exact) == 1:
                    hits[exact[0]["urn"]] = (exact[0], raw)
                elif len(exact) > 1:
                    multi = True
            if len(hits) == 1 and not multi:
                r, raw = next(iter(hits.values()))
                if ((not ctok or not leftover(r) or ctok & set(r["tokens"])) and not excluded_leftover(r, ctok)
                        and not conflict(school_phase(r), cphase)):
                    add("b", targets_for(r, [], cphase), f"objects name '{raw}'")

        # (e) a charity address line is a school's town; the name is unique in that town and in the school's council
        if ctok:
            for town in sorted({norm_place(a) for a in addr if a} & set(by_town)):
                local = by_town[town]
                if pc:  # same postcode area, so Newport (Wight) never meets Newport (Shropshire)
                    local = [r for r in local if r["postcode"] and postcode_area(r["postcode"]) == postcode_area(pc)]
                chosen, tied = pick([e for r in local for e in entries_for(r, False)], ctok, cphase)
                targets = targets_for(chosen and chosen[0], tied, cphase)
                if not targets:
                    continue
                r = targets[0]
                if leftover(r):
                    blocked.add(number)
                    continue
                again, again_tied = pick([e for o in by_la[r["la"]] for e in entries_for(o, False)], ctok, cphase)
                if {e[0]["urn"] for e in again_tied} == {t["urn"] for t in targets}:
                    add("e", targets, f"address-town '{r['town']}' unique in {r['la_name'] or 'council'}")
                break

    # ------------------------------------------------------------- resolve per charity (G4, G5)
    final, weak_only = {}, {}
    for number, rules in per_charity.items():
        if len({v[0] for v in rules.values()}) > 1:
            blocked.add(number)  # G5: the rules disagree
            continue
        urns = next(iter(rules.values()))[0]
        flagged = any(v[2] for rule, v in rules.items() if rule in NAME_RULES)
        if not flagged or "d" in rules or "f" in rules:
            final[number] = (urns, [(rule, rules[rule][1]) for rule in RULE_ORDER if rule in rules])
        else:
            weak_only[number] = urns

    matches = defaultdict(list)
    for number, (urns, agreed) in final.items():
        method = RULE_METHOD[agreed[0][0]]
        evidence = "; ".join(ev for _, ev in agreed) + ("; wider name" if number in widened else "")
        for urn in urns:
            rec = _charity_record(cands[number], method, evidence)
            if len(urns) > 1:
                rec["shared_with"] = [u for u in urns if u != urn]
            matches[urn].append(rec)
    for urn in matches:
        matches[urn].sort(key=lambda c: c["registered"] or "", reverse=True)

    # ------------------------------------------------------------- ambiguous export
    pass2_urns = {urn for urns, _ in final.values() for urn in urns}
    rows = []
    def split(urns):
        """(state urns, independent urns): only state schools are candidates; independents ride along as a warning."""
        return [u for u in urns if rec_by_urn[u]["state"]], [u for u in urns if not rec_by_urn[u]["state"]]

    for number, c in cands.items():
        if number in final or number in widened:
            continue
        name = c.get("charity_name") or ""
        ctok = set(normalise(name))
        if not ctok:
            continue
        cphase = phase_words(name)
        codes = sorted({code for desc in areas_by_charity.get(number, []) for code in council_codes(desc, councils)})
        pc = norm_postcode(c.get("charity_contact_postcode"))
        pool = [r for code in codes for r in by_la.get(code, [])] or (by_district.get(pc[:-3], []) if pc else [])
        if not pool:
            continue
        entries = [e for r in pool for e in entries_for(r, True, cphase)]
        ok = [e for e in entries if _fits(e[0], e[1], e[2], ctok, cphase)]
        kind, cand_urns, independent_urns = None, [], []
        if ok:
            best = max(len(e[1]) for e in ok)
            state, independent = split(list(dict.fromkeys(e[0]["urn"] for e in ok if len(e[1]) >= best)))
            # The 2-5 limit counts state candidates only; one state fit beside an independent namesake is still a choice.
            if 2 <= len(state) <= 5 or (len(state) == 1 and independent):
                kind, cand_urns, independent_urns = "several_fit", state, independent
            elif len(state) == 1 and number in blocked and number not in weak_only:
                kind, cand_urns = "single_fit_blocked", state
        if kind is None and number in weak_only:
            r = rec_by_urn[weak_only[number][0]]
            longer = [o["urn"] for o in by_la[r["la"]] if o is not r and set(r["tokens"]) < set(o["tokens"])
                      and not conflict(school_phase(o), cphase)]
            state, independent = split(list(dict.fromkeys(list(weak_only[number]) + longer)))
            kind, cand_urns, independent_urns = "flagged_single_fit", state[:5], independent
        if kind is None and not ok:
            part = []
            for r in pool:
                st = set(r["tokens"])
                inter = st & ctok
                if st and inter and len(inter) >= max(1, len(st) - 1) and len(inter) >= len(ctok) - 1:
                    part.append((len(inter), r["urn"]))
            state, independent = split(list(dict.fromkeys(u for _, u in sorted(part, key=lambda x: -x[0]))))
            if 1 <= len(state) <= 5:
                kind, cand_urns, independent_urns = "partial_name", state, independent
        if kind is None or not cand_urns:
            continue
        independents = [rec_by_urn[u]["name"] for u in independent_urns]
        objects, aob = objects_by_charity.get(number, ("", ""))
        addr = [a for a in (c.get(f"charity_contact_address{i}") for i in range(1, 6)) if a]
        rows.append({
            "charity_number": number, "charity_name": name, "kind": kind, "objects": objects, "area_of_benefit": aob,
            "area": [councils.get(x, x) for x in codes], "postcode": c.get("charity_contact_postcode"),
            "town": charity_town(addr), "address": addr, "status": c.get("charity_registration_status") or "",
            "removed": _date(c.get("date_of_removal")), "latest_income": c.get("latest_income"), "recent_returns": None,
            "also_fits_independent": independents,
            "candidates": [{"urn": u, "name": rec_by_urn[u]["name"], "postcode": rec_by_urn[u]["postcode_raw"],
                            "town": rec_by_urn[u]["town"], "phase": rec_by_urn[u]["gphase_raw"],
                            "predecessor_names": rec_by_urn[u]["preds"],
                            "already_matched": u in matched_urns or u in pass2_urns} for u in cand_urns],
        })
    return dict(matches), rows


# ---------------------------------------------------------------- merges

def _placed(matches):
    """charity number -> set of urns it is attached to."""
    placed = defaultdict(set)
    for urn, charities in matches.items():
        for c in charities:
            placed[c["charity_number"]].add(urn)
    return placed


SPOT_CHECK_MIN = 50  # accepted LLM picks a person must have judged, with none wrong, before any is merged


def llm_gate(llm) -> str | None:
    """Why pta_llm.json may not be merged yet, or None once its spot check passed: 'spot_check': {'n' >= 50, 'wrong': 0}."""
    spot = (llm or {}).get("spot_check")
    if not isinstance(spot, dict):
        return "no spot check recorded (pta_adjudicate.py sample, then spot-check)"
    n, wrong = spot.get("n"), spot.get("wrong")
    if not isinstance(n, int) or isinstance(n, bool) or n < SPOT_CHECK_MIN:
        return f"spot check covers {n!r} picks, fewer than {SPOT_CHECK_MIN}"
    if not isinstance(wrong, int) or isinstance(wrong, bool) or wrong != 0:
        return f"spot check found {wrong!r} wrong"
    return None


SHARED_URN = re.compile(r"(?<!\d)\d{5,7}(?!\d)")


def is_shared_answer(answer) -> bool:
    """True for an adjudicator answer whose reason starts 'shared:' (prompt v1 rule 6), whatever its urn says: it goes
    to the deterministic shared step, never to one school."""
    return str((answer or {}).get("reason") or "").strip().lower().startswith("shared:")


def school_index(schools_by_urn):
    """(records by urn, records by postcode district, records by council, records by postcode) of the open schools
    with a distinctive name, state and independent: what shared_targets checks blockers against."""
    recs = {urn: _school_record(s) for urn, s in schools_by_urn.items() if not _closed(s)}
    recs = {urn: r for urn, r in recs.items() if r["tokens"]}
    by_district, by_la, by_pc = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in recs.values():
        if r["district"]:
            by_district[r["district"]].append(r)
            by_pc[r["postcode"]].append(r)
        if r["la"]:
            by_la[r["la"]].append(r)
    return recs, by_district, by_la, by_pc


def shared_targets(answer, charity, schools_by_urn, state_urns, index=None):
    """The two schools a 'shared:' adjudicator answer names, when the deterministic check agrees, else [].

    Both must be state-funded, open and an infant/junior pair in one postcode district (pass 2's _sibling); the
    charity's name must fit each with no word left unexplained by the school's name or place; and no other school,
    independent ones included, may explain the name better: none in the district or council fits it with more
    distinctive words, and none at the charity's own postcode fits it unless it is one of the pair. An answer whose urn
    is set but is not one of the pair is self-contradictory and is dropped. index: school_index(schools_by_urn), built
    once by merge_llm."""
    reason = str(answer.get("reason") or "").strip()
    if not is_shared_answer(answer):
        return []
    urns = list(dict.fromkeys(SHARED_URN.findall(reason)))
    if len(urns) != 2 or any(u not in state_urns or u not in schools_by_urn for u in urns):
        return []
    if answer.get("urn") is not None and str(answer["urn"]).strip() not in urns:
        return []
    recs_by_urn, by_district, by_la, by_pc = index or school_index(schools_by_urn)
    if any(u not in recs_by_urn for u in urns):
        return []  # closed, or no distinctive name to check
    recs = [recs_by_urn[u] for u in urns]
    name = charity.get("charity_name") or ""
    ctok, cphase = set(normalise(name)), phase_words(name)
    if not recs[0]["district"] or _sibling(recs[0], by_district) is not recs[1]:
        return []
    if not all(_fits(r, r["tokens"], school_phase(r), ctok, cphase) and not out_of_scope_words(name, r)
               and not ctok - set(r["tokens"]) - r["place"] for r in recs):
        return []
    best = max(len(r["tokens"]) for r in recs)
    nearby = {o["urn"]: o for r in recs for o in by_district.get(r["district"], []) + by_la.get(r["la"], [])}
    if any(set(o["tokens"]) <= ctok and len(o["tokens"]) > best and not conflict(school_phase(o), cphase)
           for urn, o in nearby.items() if urn not in urns):
        return []  # 'Friends of Woodlea Park School' beside independent Woodlea Park School
    pc = norm_postcode(charity.get("charity_contact_postcode"))
    if pc and any(o["urn"] not in urns and fits_at_postcode(o, ctok, cphase) for o in by_pc.get(pc, [])):
        return []  # the charity's address is another school's, which its name fits (rule f's test)
    return urns


def merge_llm(matches, llm, charities_by_number, state_urns, schools_by_urn=None) -> int:
    """Add accepted adjudicator answers (pta_llm.json) as method 'llm', confidence 'medium'. Returns the count added.

    Nothing merges until llm_gate passes (a person judged 50 or more accepted picks and found none wrong). 'shared:'
    answers, whatever their urn, go only through shared_targets, given the raw register by urn, and attach to both
    schools with shared_with.
    """
    if llm_gate(llm):
        return 0
    placed = _placed(matches)
    added = 0
    index = None
    for key, answer in sorted((llm or {}).get("answers", {}).items()):
        if not isinstance(answer, dict) or not str(key).isdigit():
            continue
        number = int(key)
        charity = charities_by_number.get(number)
        if not charity or number in placed:
            continue
        urn = str(answer.get("urn") or "")
        if is_shared_answer(answer):
            if schools_by_urn is None:
                continue
            index = index or school_index(schools_by_urn)
            urns = shared_targets(answer, charity, schools_by_urn, state_urns, index)
        elif answer.get("accepted") and urn in state_urns:
            urns = [urn]
        else:
            urns = []
        for u in urns:
            evidence = answer.get("reason") or ""
            if len(urns) > 1:
                evidence = "shared: the name fits both schools; " + evidence
            rec = _charity_record(charity, "llm", evidence, confidence="medium")
            if len(urns) > 1:
                rec["shared_with"] = [o for o in urns if o != u]
            matches.setdefault(u, []).append(rec)
            matches[u].sort(key=lambda c: c["registered"] or "", reverse=True)
            placed[number].add(u)
        added += bool(urns)
    return added


def merge_crawl(matches, crawl, charities_by_number, state_urns, counts=None, school_names=None) -> int:
    """Add charity numbers found on school websites (pta_crawl.json) as method 'website-crawl'. Returns the count added.

    A hit counts only when the charity's name reads as a parents' association, or is a wider name (is_widened)
    sharing a distinctive word with the school's name (school_names: {urn: name}), or the page evidence uses real PTA
    wording; and the charity is not already attached to another school (it is never moved). A hit that confirms an
    existing match only adds 'website <url>' to that match's evidence. Unknown keys ('meta') are ignored; counts, when
    given, gets 'added' and 'confirmed'.
    """
    placed = _placed(matches)
    added = confirmed = 0
    schools = (crawl or {}).get("schools") if isinstance(crawl, dict) else None
    for urn, hits in (schools if isinstance(schools, dict) else {}).items():
        urn = str(urn)
        if urn not in state_urns or not isinstance(hits, list):
            continue
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            try:
                number = int(hit.get("charity_number"))
            except (TypeError, ValueError):
                continue
            url = str(hit.get("source_url") or "")
            if number in placed:
                if urn in placed[number]:
                    for c in matches.get(urn, []):
                        note = f"website {url}".strip()
                        if c["charity_number"] == number and note not in c["match"]["evidence"]:
                            c["match"]["evidence"] = "; ".join(x for x in (c["match"]["evidence"], note) if x)
                            confirmed += 1
                continue
            charity = charities_by_number.get(number)
            if not charity or charity.get("linked_charity_number", 0) not in (0, 1):
                continue
            name = charity.get("charity_name")
            wide_fits = bool(school_names and is_widened(charity)
                             and set(normalise(name)) & set(normalise(school_names.get(urn))))
            if not (is_parent_association(name) or wide_fits or CRAWL_WORDS.search(str(hit.get("evidence") or ""))):
                continue
            matches.setdefault(urn, []).append(_charity_record(charity, "website-crawl", url or str(hit.get("evidence") or "")))
            matches[urn].sort(key=lambda c: c["registered"] or "", reverse=True)
            placed[number].add(urn)
            added += 1
    if counts is not None:
        counts.update(added=added, confirmed=confirmed)
    return added


# --------------------------------------------------------------- streams

_SKIP = re.compile(r"[\s,]*")


def iter_json_array(path, chunk_size=1 << 20):
    """Yield each object of a JSON array file without loading the whole file."""
    decoder = json.JSONDecoder()
    with open(path, encoding="utf-8-sig") as f:
        buf, pos, started = f.read(chunk_size), 0, False
        while True:
            pos = _SKIP.match(buf, pos).end()
            if pos >= len(buf):
                more = f.read(chunk_size)
                if not more:
                    return
                buf, pos = buf[pos:] + more, 0
                continue
            if buf[pos] == "[" and not started:
                started, pos = True, pos + 1
                continue
            if buf[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except json.JSONDecodeError:
                more = f.read(chunk_size)
                if not more:
                    raise ValueError(f"truncated JSON array in {path}")
                buf, pos = buf[pos:] + more, 0
                continue
            pos = end
            yield obj


def load_councils(site_data) -> dict[str, str]:
    """la_code -> council name from the English manifest, {} when it is absent."""
    las = Path(site_data) / "england/las.json"
    if not las.exists():
        return {}
    return {str(la["la_code"]): la["name"] for la in json.loads(las.read_text(encoding="utf-8")).get("las", [])}


def load_schools(site_data, all_schools=False):
    """Open schools from every English council's register, each with la_code and council set.

    State-funded schools only by default: an independent school's "association" is usually the charity that runs
    it. all_schools=True keeps independents, colleges and universities so the matchers can use them as blockers.
    site/data/la also holds Scottish, Welsh and Northern Irish councils; only those listed in the English manifest
    (england/las.json) are read, and any register that names another nation is skipped.
    """
    site_data = Path(site_data)
    councils = load_councils(site_data)
    paths = ([site_data / "la" / code / "schools.json" for code in sorted(councils)] if councils
             else sorted(site_data.glob("la/*/schools.json")))
    schools = []
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        nation = (data.get("la") or {}).get("nation")
        if nation and nation != "England":
            continue
        for school in data.get("schools", []):
            if not all_schools and not is_state_funded(school):
                continue
            school.setdefault("la_code", path.parent.name)
            school.setdefault("council", councils.get(path.parent.name))
            schools.append(school)
    return schools


def iter_candidates(charity_path, extra_numbers=(), widened=False):
    """Main charities whose name reads as a parents' association, plus any numbers in extra_numbers and, with
    widened=True, the wider supporters' names and the activity-backed broad tier (is_widened)."""
    extra = set(extra_numbers)
    for obj in iter_json_array(charity_path):
        name = obj.get("charity_name")
        if obj.get("linked_charity_number", 0) in (0, 1) and (is_parent_association(name) or obj.get("registered_charity_number") in extra
                                                              or (widened and is_widened(obj))):
            yield obj


def load_areas(path, numbers) -> dict[int, list[str]]:
    """charity number -> Charity Commission 'Local Authority' area descriptions, for the given numbers."""
    out = defaultdict(list)
    for row in iter_json_array(path):
        number = row.get("registered_charity_number")
        if number in numbers and row.get("linked_charity_number", 0) in (0, 1) and row.get("geographic_area_type") == "Local Authority":
            out[number].append(row.get("geographic_area_description") or "")
    return dict(out)


def load_objects(path, numbers) -> dict[int, tuple[str, str]]:
    """charity number -> (charitable_objects, area_of_benefit), for the given numbers."""
    out = {}
    for row in iter_json_array(path):
        number = row.get("registered_charity_number")
        if number in numbers and row.get("linked_charity_number", 0) in (0, 1):
            out[number] = (row.get("charitable_objects") or "", row.get("area_of_benefit") or "")
    return out


CURRENT_FROM, RECENT_FROM = 2024, 2019  # history_status: income in a year ending this year or later


def history_fields(record) -> dict:
    """history_status, last_income_year and removed_year of a charity record, from its history and removal date.

    'current' = income for a year ending 2024 or later, 'recent' = income since 2019, else 'historical' (the site
    says 'Had a registered PTA until <year>'). Consumers derive the same from history when a record lacks them."""
    years = [int(h["period_end"][:4]) for h in record.get("history") or []
             if h.get("income") is not None and str(h.get("period_end") or "")[:4].isdigit()]
    last = max(years) if years else None
    status = "current" if last and last >= CURRENT_FROM else "recent" if last and last >= RECENT_FROM else "historical"
    removed = str(record.get("removed") or "")[:4]
    return {"history_status": status, "last_income_year": last, "removed_year": int(removed) if removed.isdigit() else None}


def attach_history(matches, returns, ambiguous=()):
    """Fill each matched charity's history from annual return rows (any iterable of dicts), and count the
    returns since 2019 with an income figure for each ambiguous row (recent_returns)."""
    wanted = defaultdict(list)
    for charities in matches.values():
        for c in charities:
            wanted[c["charity_number"]].append(c)
    recent = {row["charity_number"]: 0 for row in ambiguous}
    if not wanted and not recent:
        return
    rows = defaultdict(dict)
    for ret in returns:
        number = ret.get("registered_charity_number")
        if not ret.get("fin_period_end_date"):
            continue
        period = str(ret["fin_period_end_date"])[:7]
        suppressed = bool(ret.get("suppression_ind"))
        if number in recent and period >= "2019-01" and not suppressed and ret.get("total_gross_income") is not None:
            recent[number] += 1
        if number not in wanted:
            continue
        row = {"period_end": period,
               "income": None if suppressed else ret.get("total_gross_income"),
               "expenditure": None if suppressed else ret.get("total_gross_expenditure")}
        if period not in rows[number] or rows[number][period]["income"] is None:
            rows[number][period] = row
    for number, charities in wanted.items():
        history = sorted(rows[number].values(), key=lambda h: h["period_end"], reverse=True)
        for c in charities:
            c["history"] = history
            c.update(history_fields(c))
    for row in ambiguous:
        row["recent_returns"] = recent[row["charity_number"]]


def attach_parta(matches, rows) -> int:
    """Write charity['parta'] from the latest annual return Part A row (any iterable of dicts). Returns charities covered."""
    wanted = defaultdict(list)
    for charities in matches.values():
        for c in charities:
            wanted[c["charity_number"]].append(c)
    latest = {}
    for row in rows:
        number = row.get("registered_charity_number")
        end = _date(row.get("fin_period_end_date"))
        if number not in wanted or not end:
            continue
        if number not in latest or end > latest[number][0]:
            latest[number] = (end, row)
    for number, (end, row) in latest.items():
        for c in wanted[number]:
            c["parta"] = {"count_volunteers": row.get("count_volunteers"),
                          "raises_funds_from_public": row.get("charity_raises_funds_from_public"),
                          "trading_subsidiary": row.get("charity_has_trading_subsidiary"),
                          "ar_due_date": _date(row.get("ar_due_date")), "fin_period_end": end}
    return len(latest)


# ---------------------------------------------------------------- report

REGENERATE = """\
## Regenerating

Real inputs live in the main checkout (`M=/Users/jhammant/dev/personal/SchoolCatchmentArea`) and are never committed.
Back up the live output first (`-n`: the first, pre-Wave-B backup is never overwritten), then write through a temp
file so readers never see half a file (pta.py does the temp file and `os.replace` itself):

```bash
cp -n "$M/pipeline/.cache/money/pta.json" "$M/pipeline/.cache/money/pta.json.before-wave-b"
python3 -m pipeline.money.pta                      # ~30 s; writes pta.json, pta_ambiguous.jsonl and this report
```

Adjudicator answers (method `llm`) merge only after a spot check:

```bash
python3 -m pipeline.money.pta_adjudicate import-pilot   # the pilot's full Qwen run -> pta_llm.json (no recomputation)
python3 -m pipeline.money.pta_adjudicate sample         # 50 random accepted picks -> pta_llm_review.md
# judge every row in pta_llm_review.md (right / wrong / unsure), then:
python3 -m pipeline.money.pta_adjudicate spot-check     # records spot_check {n, wrong} in pta_llm.json
python3 -m pipeline.money.pta                           # merges the answers once n >= 50 and wrong == 0
```

`--ambiguous`, `--llm` and `--crawl` default to `--out`'s directory, so a run (or a test) writing elsewhere never
touches the live cache. Older checkouts lack this: their `tests/test_pta_review.py` empties the live
`pta_ambiguous.jsonl`; rerun pta.py to restore it. `pta_crawl_review.json` is never merged.
"""


def _is_wide(c) -> bool:
    return "wider name" in str(c["match"]["evidence"])


def report(matches, rejections, stats, schools_by_urn, seed, seconds):
    pairs = [(schools_by_urn.get(urn, urn), c) for urn, cs in matches.items() for c in cs]
    methods = Counter(c["match"]["method"] for _, c in pairs)
    agreeing = Counter(m for _, c in pairs if c["match"]["method"] in RULE_METHOD.values()
                       for m in RULE_METHOD.values() if re.search(r"(^|; )" + re.escape(m) + r"\b", c["match"]["evidence"]))
    shared = sum(1 for _, c in pairs if c.get("shared_with"))
    parta = sum(1 for _, c in pairs if c.get("parta"))
    wide = [(s, c) for s, c in pairs if _is_wide(c)]
    status = Counter((c.get("history_status") or history_fields(c)["history_status"]) for _, c in pairs)
    best = Counter()
    for cs in matches.values():
        got = {c.get("history_status") or history_fields(c)["history_status"] for c in cs}
        best[next(k for k in ("current", "recent", "historical") if k in got)] += 1
    rng = random.Random(seed)
    lines = [
        "# PTA matching report", "",
        f"Generated {date.today().isoformat()} by `pipeline/money/pta.py` (seed {seed}, {seconds:.0f}s).", "",
        f"- Candidate charities (main, parents' association by name): {stats.get('candidates', 0):,}",
        f"- Wider-name candidates (Friends of X, P.T.A., Parent/Teacher, Families & Staff, Supporters of; rules f and d "
        f"only): {stats.get('widened', 0):,}, of which {len(wide):,} matched to {len({s for s, _ in wide}):,} schools; "
        f"{stats.get('broad', 0):,} of the candidates are the activity-backed broad tier (a school fund or society)",
        f"- Schools matched: {len(matches):,}",
        f"- Charities matched: {len(pairs):,} ({shared:,} shared infant/junior attributions)",
        "- By method: " + ", ".join(f"{m} {n:,}" for m, n in sorted(methods.items())),
        "- Pass-2 rules agreeing (a charity can count under several): " + (", ".join(f"{m} {n:,}" for m, n in sorted(agreeing.items())) or "none"),
        f"- Pass-1 ambiguity rejections: {len(rejections):,}",
        f"- Ambiguous charities exported for adjudication: {stats.get('ambiguous', 0):,}"
        + (" (" + ", ".join(f"{k} {n:,}" for k, n in sorted(stats.get("ambiguous_kinds", {}).items())) + ")" if stats.get("ambiguous_kinds") else ""),
        f"- Merged from the adjudicator (llm): {stats.get('llm', 0):,}; from the website crawl: {stats.get('crawl', 0):,}",
        f"- Adjudicator answers in pta_llm.json: {stats.get('llm_answers', 0):,}, {stats.get('llm_accepted', 0):,} accepted, "
        f"{stats.get('llm_shared', 0):,} 'shared:'; gate: {stats.get('llm_gate') or 'open (spot check passed)'}",
        f"- Website crawl hits confirming an existing match (evidence gains 'website'): {stats.get('crawl_confirmed', 0):,}",
        f"- Annual return Part A attached: {parta:,} of {len(pairs):,} matched charities",
        "- history_status of matched charities: " + ", ".join(f"{k} {status.get(k, 0):,}" for k in ("current", "recent", "historical")),
        "- Schools by their most recent PTA: " + ", ".join(f"{k} {best.get(k, 0):,}" for k in ("current", "recent", "historical"))
        + " (current = income for a year ending 2024 or later, recent = since 2019)",
        "",
    ]
    for method in ["postcode", "sector", "website", *RULE_METHOD.values(), "llm", "website-crawl"]:
        rows = [(s, c) for s, c in pairs if c["match"]["method"] == method and not _is_wide(c)]
        if not rows:
            continue
        sample = rng.sample(rows, min(25, len(rows)))
        lines += [f"## {len(sample)} random `{method}` matches for review", "", "| school | charity | evidence |", "|---|---|---|"]
        lines += [f"| {s} | {c['name']} ({c['charity_number']}) | {c['match']['evidence']} |" for s, c in sample]
        lines.append("")
    for method in ("postcode-exact", "domain"):
        rows = [(s, c) for s, c in wide if c["match"]["method"] == method]
        if not rows:
            continue
        sample = rng.sample(rows, min(25, len(rows)))
        lines += [f"## {len(sample)} random wider-name `{method}` matches for review", "", "| school | charity | evidence |", "|---|---|---|"]
        lines += [f"| {s} | {c['name']} ({c['charity_number']}) | {c['match']['evidence']} |" for s, c in sample]
        lines.append("")
    lines += [f"## Pass-1 ambiguity rejections ({len(rejections):,})", ""]
    lines += [f"- {r['charity']} ({r['charity_number']}): {r['reason']}: {'; '.join(r['schools'])}" for r in rejections[:20]]
    lines += ["", REGENERATE]
    return "\n".join(lines) + "\n"


def _read_json(path):
    path = Path(path) if path else None
    return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else None


def write_atomic(path, text):
    """Write text through a temp file in the same directory and os.replace it in, so readers never see half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--charity-dir", type=Path, default=CHARITY_DIR)
    parser.add_argument("--site-data", type=Path, default=SITE_DATA)
    parser.add_argument("--links", type=Path, default=LINKS, help="GIAS links.csv for predecessor names")
    parser.add_argument("--out", type=Path, default=OUT)
    # The money-cache files default to --out's directory, so a run writing elsewhere never touches the live ones.
    parser.add_argument("--ambiguous", type=Path, help="default: pta_ambiguous.jsonl beside --out")
    parser.add_argument("--llm", type=Path, help="pta_llm.json from pta_adjudicate.py, merged when present and spot-checked "
                                                 "(default: beside --out)")
    parser.add_argument("--crawl", type=Path, help="pta_crawl.json from pta_crawl.py, merged when present (default: beside --out)")
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    args.ambiguous = args.ambiguous or args.out.parent / AMBIGUOUS.name
    args.llm = args.llm or args.out.parent / LLM.name
    args.crawl = args.crawl or args.out.parent / CRAWL.name
    if "review" in args.crawl.name:
        parser.error(f"{args.crawl.name} holds crawl hits for review; only pta_crawl.json is merged")
    start = time.time()

    def tick(msg):
        print(f"{msg} ({time.time() - start:.0f}s)", flush=True)

    schools = load_schools(args.site_data, all_schools=True)
    councils = load_councils(args.site_data)
    state_urns = {str(s["urn"]) for s in schools if is_state_funded(s)}
    schools_by_urn = {str(s["urn"]): s for s in schools}
    llm, crawl = _read_json(args.llm), _read_json(args.crawl)
    crawl_hits = (crawl or {}).get("schools") if isinstance(crawl, dict) else None
    crawl_numbers = {int(h["charity_number"]) for hits in (crawl_hits if isinstance(crawl_hits, dict) else {}).values()
                     if isinstance(hits, list) for h in hits if isinstance(h, dict) and str(h.get("charity_number", "")).isdigit()}
    candidates = list(iter_candidates(args.charity_dir / "publicextract.charity.json", crawl_numbers, widened=True))
    by_number = {int(c["registered_charity_number"]): c for c in candidates}
    widened = {n for n, c in by_number.items() if is_widened(c)}
    stats = {"candidates": sum(1 for c in candidates if is_parent_association(c.get("charity_name"))), "widened": len(widened),
             "broad": sum(1 for n in widened if not is_widened_name(by_number[n].get("charity_name")))}
    tick(f"{len(schools):,} schools ({len(state_urns):,} state-funded), {stats['candidates']:,} candidate charities, "
         f"{len(widened):,} wider names")

    matches, rejections = match(schools, candidates)
    tick(f"pass 1: {len(matches):,} schools matched, {len(rejections):,} rejected")

    placed = set(_placed(matches))
    unmatched = {n for n, c in by_number.items() if n not in placed and is_parent_association(c.get("charity_name"))}
    areas_path = args.charity_dir / "publicextract.charity_area_of_operation.json"
    objects_path = args.charity_dir / "publicextract.charity_governing_document.json"
    areas = load_areas(areas_path, unmatched) if areas_path.exists() else {}
    objects = load_objects(objects_path, unmatched) if objects_path.exists() else {}
    predecessors = load_predecessors(args.links) if args.links and args.links.exists() else {}
    new, ambiguous = match_pass2(schools, candidates, unmatched | (widened - placed), areas, objects, predecessors,
                                 matched_urns=set(matches), councils=councils, widened=widened)
    for urn, charities in new.items():
        matches.setdefault(urn, []).extend(charities)
        matches[urn].sort(key=lambda c: c["registered"] or "", reverse=True)
    stats["ambiguous"] = len(ambiguous)
    stats["ambiguous_kinds"] = dict(Counter(row["kind"] for row in ambiguous))
    tick(f"pass 2: {sum(len(v) for v in new.values()):,} charities on {len(new):,} schools, {len(ambiguous):,} ambiguous")

    stats["llm_gate"] = llm_gate(llm) if llm else "no pta_llm.json"
    answers = [a for a in (llm or {}).get("answers", {}).values() if isinstance(a, dict)]
    stats["llm_answers"], stats["llm_accepted"] = len(answers), sum(1 for a in answers if a.get("accepted"))
    stats["llm_shared"] = sum(1 for a in answers if str(a.get("reason") or "").lower().startswith("shared:"))
    stats["llm"] = merge_llm(matches, llm, by_number, state_urns, schools_by_urn)
    crawl_counts = {}
    stats["crawl"] = merge_crawl(matches, crawl, by_number, state_urns, crawl_counts,
                                 {urn: s.get("name") for urn, s in schools_by_urn.items()})
    stats["crawl_confirmed"] = crawl_counts.get("confirmed", 0)
    attach_history(matches, iter_json_array(args.charity_dir / "publicextract.charity_annual_return_history.json"), ambiguous)
    for charities in matches.values():
        for c in charities:
            c.update(history_fields(c))
    parta_path = args.charity_dir / "publicextract.charity_annual_return_parta.json"
    if parta_path.exists():
        attach_parta(matches, iter_json_array(parta_path))
    tick(f"history and Part A attached; llm {stats['llm']:,} ({stats['llm_gate'] or 'gate open'}), crawl {stats['crawl']:,}")

    write_atomic(args.out, json.dumps({"generated": date.today().isoformat(), "source": SOURCE, "licence": LICENCE,
                                       "schools": matches}, indent=1))
    write_atomic(args.ambiguous, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ambiguous))
    names = {str(s["urn"]): s.get("name") or str(s["urn"]) for s in schools}
    write_atomic(args.report, report(matches, rejections, stats, names, args.seed, time.time() - start))
    tick(f"wrote {args.out}, {args.ambiguous} and {args.report}")


if __name__ == "__main__":
    main()
