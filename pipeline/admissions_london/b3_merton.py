"""Merton (LA 315): parse the council's "School admissions and appeals data
for recent years" PDF (via pdftotext -layout), which tabulates PAN,
applications and the furthest distance offered for both Year 7 (secondary,
"Transfer to secondary school") and Reception ("Reception allocations") for
six consecutive years in one document (September 2021-2026, the September
2026 edition -- "updated 1 September 2026").

Each school's row gives three "furthest distance" figures per year: the
National Offer Day figure, a "second round" figure, and a later (1 September)
figure after in-year movement; only the first (National Offer Day) figure is
used for max_distance, with the other two recorded in notes.

Only "community"/council-coordinated schools publish applications/criteria/
distance figures; voluntary-aided and academy schools' rows say "Please
contact school for further information" (PAN and on-time applications only).

Two Merton schools (secondary: none; primary: Dundonald, Wimbledon Chase)
operate an Admissions Priority Area (APA): all applicants living inside the
APA are offered a place, and a distance figure is published only for
applicants offered from outside the APA. Wimbledon Park has an APA too but,
in every year seen here, its own distance table is populated directly
(annotated "(in APA)") rather than using the "All APA offered" wording --
modelled as an ordinary single-group distance record with a note.

Distances are published in metres, converted to miles via common.miles().
"""

from __future__ import annotations

import re

import common

LA_CODE = "315"
LA_NAME = "Merton"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "harris prim": ("141143", "source abbreviates 'Harris Prim. Academy'; GIAS: Harris Primary Academy Merton"),
    "bury c st thomas": ("133774", "source abbreviates \"St Thomas of C'bury\"; GIAS: St Thomas of Canterbury "
                         "Catholic Primary School"),
    "paul peter ss": ("102667", "source abbreviates 'SS Peter & Paul'; GIAS: St Peter and Paul Catholic "
                      "Primary School"),
}

OGL = "Open Government Licence v3.0"
SOURCE_URL = ("https://www.merton.gov.uk/sites/default/files/2026-09/"
             "Admissions%20and%20appeals%20data%20for%20recent%20years%20-%20table%20Sept%2026.pdf")
SOURCES = [{"title": "London Borough of Merton: School admissions and appeals data for recent years "
                     "(updated 1 September 2026; secondary Year 7 outcomes 2021-2026, Reception outcomes "
                     "2021-2026)",
           "url": SOURCE_URL, "licence": OGL}]

DISTANCE_METHOD = "straight_line"
DISTANCE_NOTES = ('"Straight line distance between the child\'s home address and the main school" (Merton '
                  'Council secondary admissions criteria); the primary criteria page uses the same wording. '
                  '"Where more than one applicant has the same straight line distance measurement and distance '
                  'is the determining factor, rank order will be determined by random allocation." Three '
                  'distance figures are published per school per year -- the National Offer Day figure, a '
                  '"second round" figure, and a later (1 September) figure reflecting in-year movement -- of '
                  'which only the first (National Offer Day) is used for max_distance here; the other two are '
                  'recorded in notes. Two primary schools (Dundonald, Wimbledon Chase) operate an Admissions '
                  'Priority Area (APA): every applicant living inside the APA is offered a place, and only '
                  'applicants offered from outside the APA are ranked, and reported, by distance.')

MISSING_NOTE = ("Only \"community\"/council-coordinated schools publish applications, admission-criteria "
               "counts or distance-of-last-offer figures; voluntary-aided and academy schools' rows give only "
               "the published admission number and on-time applications received (\"contact the school "
               "directly\" for anything else) -- this covers 3 of 9 Merton secondary schools and roughly "
               "two-thirds of primary schools. Some criteria counts are published by the council only as "
               "\"<5\" (suppressed for data protection) rather than an exact number; those totals are null, "
               "with the label saying \"fewer than 5\", rather than guessed at.")

FAITH_RE = re.compile(r"^(St |St\.|Ss |Holy |Sacred |Bishop |Our Lady)", re.I)
APA_GROUP_SCHOOLS = {"Dundonald", "Wimbledon Chase"}
# Two-line-wrapped names where the continuation word appears on a later physical line than my general
# trailing-fragment heuristic checks (it spans 3 physical lines because of the APA / "(in APA)" annotation
# rows); disambiguated by order of appearance (both recur every year in this fixed alphabetical order).
WIMBLEDON_ORDER = ["Wimbledon Chase", "Wimbledon Park"]

STOP_WORDS = {"information", "offered", "round", "outside", "apa", "school", "contact", "please", "sibs",
             "all", "on", "time", "applicants", "(in"}
NUM_RE = re.compile(r"(<?\d+)")
DIST_RE = re.compile(r"(\d+\.\d+)")


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def _num(tok: str):
    tok = tok.strip()
    return int(tok) if re.fullmatch(r"\d+", tok) else tok


def _split_blocks(section_text: str) -> list[str]:
    return [b.strip("\n") for b in re.split(r"\n\s*\n\s*\n+", section_text) if b.strip()]


def _is_data_block(b: str) -> bool:
    s = b.strip()
    if not s or re.fullmatch(r"\d+", s):
        return False
    if s.startswith("School") and "Places" in b:
        return False
    if "No." in b.split("\n", 1)[0] and "School" in b:
        return False
    return True


def _leading_cell(line: str) -> str:
    return re.split(r"\s{2,}", line.strip(), maxsplit=1)[0]


def _clean_word_cell(cand: str, max_words: int = 2, max_len: int = 16) -> bool:
    words = cand.split()
    return (1 <= len(words) <= max_words and not any(w.lower().strip(".,()") in STOP_WORDS for w in words)
            and not re.search(r"\d", cand) and len(cand) <= max_len)


def _extract_name_continuation(block: str) -> tuple[str, str]:
    """A wrapped school name's later words sometimes appear as the leading cell of each subsequent physical
    line (e.g. 'Harris\\nAcademy\\nMerton   <data...>', or 'Wimbledon\\nChase   <annotation text...>'), and
    sometimes as a single short standalone LAST line (e.g. 'Bishop\\nGilpin'). Consume as many leading
    continuation lines as look like clean name words, then fall back to the whole-last-line case."""
    lines = [l for l in block.split("\n") if l.strip()]
    if len(lines) < 2:
        return block, ""
    continuation: list[str] = []
    i = 1
    while i < len(lines):
        cand = _leading_cell(lines[i])
        if not _clean_word_cell(cand):
            break
        continuation.append(cand)
        rest_of_line = lines[i][len(cand):].lstrip()
        lines[i] = rest_of_line
        if rest_of_line:
            break  # this line also carries data content after the name word; stop consuming further lines
        i += 1
    if continuation:
        remaining = [lines[0]] + [l for l in lines[1:] if l.strip()]
        return "\n".join(remaining), " ".join(continuation)
    last = lines[-1].strip()
    if _clean_word_cell(last, max_words=3, max_len=24):
        return "\n".join(lines[:-1]), last
    return block, ""


def _parse_block(block: str) -> dict | None:
    body, trailing = _extract_name_continuation(block)
    m = re.match(r"^(.*?)\s+(\d+)\s+(\d+)\s+(.*)$", body, re.S)
    if not m:
        return None
    name = _clean(m.group(1))
    if trailing:
        name = _clean(f"{name} {trailing}")
    pan, applications, rest = int(m.group(2)), int(m.group(3)), m.group(4)
    result = {"name": name, "pan": pan, "applications": applications}
    if "Please contact school" in rest:
        result["mode"] = "contact_school"
        return result
    if "All APA offered" in rest:
        nums = NUM_RE.findall(rest.split("All APA offered")[0])
        result["criteria_raw"] = [_num(n) for n in nums[:5]]
        result["mode"] = "apa"
        result["distances"] = DIST_RE.findall(rest)
        return result
    if "All on time offered" in rest or "All applicants offered" in rest:
        head = re.split(r"All (?:on time|applicants) offered", rest)[0]
        result["criteria_raw"] = [_num(n) for n in NUM_RE.findall(head)]
        result["mode"] = "all_offered"
        return result
    result["criteria_raw"] = [_num(n) for n in NUM_RE.findall(rest)[:5]]
    result["distances"] = DIST_RE.findall(rest)
    result["in_apa"] = "(in APA)" in rest
    result["mode"] = "distances"
    return result


def _record(parsed: dict, year: int, crit_labels: list[str], phase: str) -> dict:
    name = parsed["name"]
    criteria = []
    suppressed = False
    for label, val in zip(crit_labels, parsed.get("criteria_raw", [])):
        if isinstance(val, str):  # "<5": keep totals numeric-or-null, flag the suppression in the label
            suppressed = True
            criteria.append({"label": f"{label} (fewer than 5; exact count suppressed)", "total": None})
        else:
            criteria.append({"label": label, "total": val})
    notes: list[str] = []
    if suppressed:
        notes.append("One or more criteria counts are published by the council only as \"<5\" (suppressed "
                    "for data protection) rather than an exact figure.")
    allocation = "distance"
    if name in APA_GROUP_SCHOOLS:
        allocation = "catchment_then_distance"
    elif FAITH_RE.match(name):
        allocation = "faith_then_distance"
        notes.append("Classified as faith_then_distance from the school's name and voluntary-aided status; "
                    "this source does not publish each school's own admission-criteria order.")

    if phase == "secondary":
        groups, all_offered = ["All"], []
        max_distance = {"All": None}
        pan = parsed["pan"]
        applications = parsed["applications"]
    else:
        groups = None

    if parsed["mode"] == "contact_school":
        notes.append("No applications, admission-criteria breakdown or distance-of-last-offer figures "
                    "published for this school this year; contact the school directly (own admission "
                    "authority).")
        if phase == "secondary":
            return {"name": name, "year": year, "pan": parsed["pan"], "applications": parsed["applications"],
                    "groups": ["All"], "criteria": [], "max_distance": {"All": None}, "all_offered": [],
                    "non_preference_offers": None, "total_offers": None, "allocation": allocation,
                    "notes": notes}
        return {"name": name, "year": year, "pan": parsed["pan"], "applications": parsed["applications"],
                "total_offers": None, "criteria": [], "max_distance": None, "all_offered": False,
                "non_preference_offers": None, "allocation": allocation, "notes": notes}

    if parsed["mode"] == "all_offered":
        if phase == "secondary":
            return {"name": name, "year": year, "pan": parsed["pan"], "applications": parsed["applications"],
                    "groups": ["All"], "criteria": criteria, "max_distance": {"All": None},
                    "all_offered": ["All"], "non_preference_offers": None, "total_offers": None,
                    "allocation": allocation, "notes": notes}
        return {"name": name, "year": year, "pan": parsed["pan"], "applications": parsed["applications"],
                "total_offers": None, "criteria": criteria, "max_distance": None, "all_offered": True,
                "non_preference_offers": None, "allocation": allocation, "notes": notes}

    if parsed["mode"] == "apa":
        dists = parsed.get("distances", [])
        outside_mi = common.miles(float(dists[0]), from_unit="metres") if dists else None
        if dists and len(dists) > 1:
            notes.append(f"Later-round furthest distance offered outside the APA: "
                        f"{', '.join(common.miles(float(d), from_unit='metres').__str__() for d in dists[1:])} "
                        f"miles.")
        notes.append("Every applicant living inside the Admissions Priority Area (APA) was offered a place; "
                    "the distance figure applies only to applicants offered from outside the APA.")
        if phase == "secondary":
            return {"name": name, "year": year, "pan": parsed["pan"], "applications": parsed["applications"],
                    "groups": ["APA", "Outside APA"], "criteria": criteria,
                    "max_distance": {"APA": None, "Outside APA": outside_mi}, "all_offered": ["APA"],
                    "non_preference_offers": None, "total_offers": None, "allocation": allocation,
                    "notes": notes}
        return {"name": name, "year": year, "pan": parsed["pan"], "applications": parsed["applications"],
                "total_offers": None, "criteria": criteria, "max_distance": outside_mi, "all_offered": False,
                "non_preference_offers": None, "allocation": allocation, "notes": notes}

    # mode == "distances"
    dists = parsed.get("distances", [])
    mi = common.miles(float(dists[0]), from_unit="metres") if dists else None
    if dists and len(dists) > 1:
        later = [str(common.miles(float(d), from_unit="metres")) for d in dists[1:]]
        notes.append(f"Later 'second round' / 1 September furthest distance offered (miles): {', '.join(later)}.")
    if parsed.get("in_apa"):
        notes.append("These figures are annotated \"(in APA)\" in the source: this school has an Admissions "
                    "Priority Area, and distance is measured within it.")
    if phase == "secondary":
        return {"name": name, "year": year, "pan": parsed["pan"], "applications": parsed["applications"],
                "groups": ["All"], "criteria": criteria, "max_distance": {"All": mi}, "all_offered": [],
                "non_preference_offers": None, "total_offers": None, "allocation": allocation, "notes": notes}
    return {"name": name, "year": year, "pan": parsed["pan"], "applications": parsed["applications"],
            "total_offers": None, "criteria": criteria, "max_distance": mi, "all_offered": False,
            "non_preference_offers": None, "allocation": allocation, "notes": notes}


def _parse_section(section_text: str, year: int, crit_labels: list[str], phase: str) -> list[dict]:
    records = []
    wimbledon_seen = 0
    for block in _split_blocks(section_text):
        if not _is_data_block(block):
            continue
        parsed = _parse_block(block)
        if parsed is None:
            continue
        if parsed["name"] == "Wimbledon" and phase == "primary":
            parsed["name"] = WIMBLEDON_ORDER[wimbledon_seen] if wimbledon_seen < len(WIMBLEDON_ORDER) \
                else "Wimbledon"
            wimbledon_seen += 1
        records.append(_record(parsed, year, crit_labels, phase))
    if not records:
        raise SystemExit(f"merton: no {phase} records parsed for {year}")
    return records


SEC_CRIT_LABELS = ["Education, Health and Care Plan (EHCP)", "Looked after / previously looked after children",
                   "Medical or social need", "Siblings", "Children of staff"]
PRI_CRIT_LABELS = ["Education, Health and Care Plan (EHCP)", "Looked after / previously looked after children",
                   "Medical or social need", "Children of staff", "Siblings"]


def build() -> tuple[list[dict], list[dict]]:
    path = common.fetch(LA_CODE, {"cache": "recent-years-sept26.pdf", "url": SOURCE_URL, "kind": "pdf"})
    text = common.pdftotext(path)
    marks = list(re.finditer(r"How places were allocated for September (\d{4})", text))
    if len(marks) != 12:
        raise SystemExit(f"merton: expected 12 year-section markers (6 secondary + 6 reception), found "
                         f"{len(marks)}")
    sec_marks, pri_marks = marks[:6], marks[6:]

    secondary: list[dict] = []
    for i, m in enumerate(sec_marks):
        year = int(m.group(1))
        start, end = m.end(), (sec_marks[i + 1].start() if i + 1 < len(sec_marks) else pri_marks[0].start())
        secondary.extend(_parse_section(text[start:end], year, SEC_CRIT_LABELS, "secondary"))

    appeals_start = text.index("Appeals\nWe receive")
    primary: list[dict] = []
    for i, m in enumerate(pri_marks):
        year = int(m.group(1))
        end_default = pri_marks[i + 1].start() if i + 1 < len(pri_marks) else appeals_start
        start, end = m.end(), min(end_default, appeals_start)
        primary.extend(_parse_section(text[start:end], year, PRI_CRIT_LABELS, "primary"))

    return secondary, primary
