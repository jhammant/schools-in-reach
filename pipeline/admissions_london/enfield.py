"""Enfield (LA 308): parse the "Breakdown of allocations" tables published in
Enfield's secondary admissions guides and in a standalone "allocation
breakdown" document (mirrored on a school site; enfield.gov.uk blocks
automated downloads even with browser headers). Together these give six years
(2020-2025) of PAN, EHCP/LAC/medical, siblings, parent-employed-at-school and
distance-criterion counts, plus the maximum distance offered, per school.

No equivalent primary/Reception breakdown could be retrieved: the council's
own primary allocation-breakdown PDFs (e.g. "Reception-previous-allocation-
breakdown-Education.pdf") are on enfield.gov.uk and returned 403 Forbidden to
every fetch attempt (browser headers via curl, and Claude's own fetch tool),
and no third-party mirror of that specific document could be found.
"""

from __future__ import annotations

import re

import common

LA_CODE = "308"
LA_NAME = "Enfield"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    # Renamed Laurel Park School (same site, N14); GIAS in this extract carries only the current name, with
    # no separate closed URN for "Broomfield School" to follow via the usual succession logic.
    "broomfield": ("102056", "renamed Laurel Park School"),
}

GUIDES = [
    {"title": "Enfield Council: Your Guide to Secondary Schools in Enfield, September 2022 "
              "(breakdown of allocations for September 2020)",
     "cache": "secondary-guide-2022.pdf",
     "url": "https://traded.enfield.gov.uk/public-assets/attach/5226/"
            "ECSL2052-Your-Guide-to-Secondary-Schools-in-Enfield_Sept22.pdf",
     "licence": "Open Government Licence v3.0", "kind": "pdf"},
    {"title": "Enfield Council: breakdown of secondary allocations for September 2021-2023 "
              "(mirrored by St Mary's Church of England High School)",
     "cache": "secondary-breakdown-mirror.pdf",
     "url": "https://www.stmarysenfield.co.uk/ckfinder/userfiles/files/ADMISSIONS/AUTUMN%202023/"
            "Secondary-transfer-allocation-breakdown-Education.pdf",
     "licence": "Open Government Licence v3.0", "kind": "pdf",
     "note": "as republished by St Mary's CE High School (enfield.gov.uk blocks automated downloads)"},
    {"title": "Enfield Council: Your Guide to Secondary Schools in Enfield, September 2026 "
              "(breakdown of allocations for September 2024 and 2025)",
     "cache": "secondary-guide-2026.pdf",
     "url": "https://traded.enfield.gov.uk/public-assets/attach/9165/"
            "ECSL2052-Your-Guide-to-Secondary-Schools-in-Enfield_Sept26.pdf",
     "licence": "Open Government Licence v3.0", "kind": "pdf"},
]
DISTANCE_METHOD = "unknown"
DISTANCE_NOTES = ("Enfield's secondary guide states GOV.UK distances are \"only a guide as Enfield uses its own "
                  "specialist systems to measure distances when allocating places\"; the precise method (straight "
                  "line vs. walking route) is not stated in these documents.")

TYPE_RE = r"(Academy|Community|Voluntary Aided|Foundation)"
HEADER_RE = re.compile(r"Type of school\s+PAN\s+LAC")
DASH = "–‒‐-"


def _blocks(text: str) -> list[tuple[int, str]]:
    # A guide edition's "breakdown of allocations" can hold one or two per-year tables, each ended either by a
    # "BREAKDOWN OF ALLOCATIONS END" marker or (for the last table before the following "Criteria for
    # admission" section) by that section's heading; the standalone mirrored breakdown document has neither and
    # simply runs one year's table into the next. Only accept "Type of school ... PAN ... LAC" matches that are
    # genuine table headers (preceded shortly by the "Enfield Schools" row label), to skip unrelated matches
    # elsewhere in the document (e.g. a per-school profile page).
    positions = [m.start() for m in HEADER_RE.finditer(text) if "Enfield Schools" in text[max(0, m.start() - 200):m.start()]]
    out = []
    for i, pos in enumerate(positions):
        year_m = re.search(r"\n\s*(20\d\d)\b", text[pos:pos + 400])
        if not year_m:
            raise SystemExit("enfield: could not find year near a 'Type of school' header")
        year = int(year_m.group(1))
        data_start = text.index("(miles)", pos) + len("(miles)")
        data_end = positions[i + 1] if i + 1 < len(positions) else len(text)
        for marker in ("BREAKDOWN OF ALLOCATIONS END", "CRITERIA FOR"):
            m = text.find(marker, data_start, data_end)
            if m != -1:
                data_end = min(data_end, m)
        out.append((year, text[data_start:data_end]))
    return out


NUM_OR_DASH = rf"(\d+(?:\.\d+)?|[{DASH}])"
ROW_RE = re.compile(
    rf"^\s*([A-Za-z][A-Za-z'’.,&\- ]*?)\d{{0,2}}\s+{TYPE_RE}\s+(\d+)\s+{NUM_OR_DASH}\s+{NUM_OR_DASH}\s+"
    rf"{NUM_OR_DASH}\s+{NUM_OR_DASH}\s+{NUM_OR_DASH}\s+\d+\s*$")
ALLOFF_RE = re.compile(
    rf"^\s*([A-Za-z][A-Za-z'’.,&\- ]*?)\d{{0,2}}\s+{TYPE_RE}\s+(\d+)\s+Places have been offered to all "
    r"applicants\.\s*$")


def _merge_wrapped(block: str) -> list[str]:
    lines = block.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        is_complete = bool(ROW_RE.match(line) or ALLOFF_RE.match(line))
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if stripped and not is_complete and re.match(TYPE_RE, nxt):
            out.append(line.rstrip() + " " + nxt)
            i += 2
            continue
        out.append(line)
        i += 1
    return out
SPECIAL_NAMES = ("St. Anne", "St. Ignatius", "Enfield County School for", "The Latymer School", "Wren Academy")


def _num(raw: str) -> float | None:
    return None if raw in ("–", "‒", "‐", "-") else float(raw)


def _generic_rows(block: str, year: int) -> list[dict]:
    out = []
    for line in _merge_wrapped(block):
        if any(line.strip().startswith(n) for n in SPECIAL_NAMES):
            continue
        m = ALLOFF_RE.match(line)
        if m:
            name, _type, pan = m.groups()
            out.append({
                "name": name.strip(), "year": year, "pan": int(pan), "applications": None, "groups": ["All"],
                "criteria": [], "max_distance": {"All": None}, "all_offered": ["All"], "non_preference_offers": None,
                "total_offers": None, "allocation": "distance",
                "notes": ["Places have been offered to all applicants (as published)."],
            })
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        name, _type, pan, ehcp, sib, parent, dist, maxd = m.groups()
        criteria = []
        for label, raw in (("Education, Health and Care Plan / Looked after / Medical", ehcp),
                           ("Siblings", sib), ("Parent employed at the school", parent),
                           ("Distance", dist)):
            v = _num(raw)
            if v is not None:
                criteria.append({"label": label, "total": int(v)})
        out.append({
            "name": name.strip(), "year": year, "pan": int(pan), "applications": None, "groups": ["All"],
            "criteria": criteria, "max_distance": {"All": _num(maxd)}, "all_offered": [],
            "non_preference_offers": None, "total_offers": None, "allocation": "distance", "notes": [],
        })
    return out


ST_NAME_RE = re.compile(r"St\.?\s*Anne’?s?'?\s*Catholic High|St\.?\s*Ignatius College")
ST_PAN_RE = re.compile(r"Voluntary Aided\s+(\d+)")


def _st_crit_re(gender: str) -> re.Pattern:
    # The "Criterion N - places offered to ... who live a maximum of X miles" sentence can have the school's own
    # name/PAN row spliced into the middle of it (a side effect of how a tall table cell linearises), so allow
    # an unbounded, non-greedy gap between "Criterion N" and the rest of the sentence.
    return re.compile(
        rf"Criter(?:ion|ia) (\d+)\s*[–-]\s*.*?offered to (?:siblings and )?{gender} who\s*(?:\n\s*)?"
        rf"live a\s*(?:\n\s*)?maximum of\s*(?:\n\s*)?([\d.]+) miles from the (?:school|college)", re.S)
ST_ALL_RE = re.compile(r"able to offer places to all\s*(?:\n\s*)?(?:girls|boys) who were considered|"
                       r"Places have been offered to all applicants")
QUOTA_NAME_RE = re.compile(r"Enfield County School for")
QUOTA_NUMS_RE = re.compile(r"Community\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s")
LATYMER_NAME_RE = re.compile(r"The Latymer School")
LATYMER_PAN_RE = re.compile(r"Voluntary Aided\s+(\d+)")
LATYMER_RANK_RE = re.compile(r"up to number (\d+) in the first round of offers")
WREN_RE = re.compile(
    r"Wren Academy Enfield:\s*Community places:\s*(\d+)\s*[–-]\s*furthest distance:\s*([\d.]+) miles;\s*"
    r"Foundation:\s*(\d+) divided between the two\s*\n?\s*criterion:\s*1\.\s*Church of England:\s*(\d+)"
    r"(?:\s*[–-]\s*furthest distance:\s*([\d.]+) miles|\s+demand met)"
    r";\s*2\.\s*(?:Other christian(?:\s+\w+)?|Church other):\s*(\d+)"
    r"(?:\s*[–-]\s*furthest distance:\s*([\d.]+) miles|\s+demand met)", re.S)
WREN_PAN_RE = re.compile(rf"Wren Academy Enfield\s*\d{{0,2}}\s+{TYPE_RE}\s+(\d+)")


def _special_rows(block: str, year: int) -> list[dict]:
    out = []
    for name_m in ST_NAME_RE.finditer(block):
        forward = block[name_m.start():name_m.start() + 700]
        wide = block[max(0, name_m.start() - 300):name_m.start() + 700]
        is_anne = "Anne" in name_m.group(0)
        name = "St. Anne's Catholic High School for Girls" if is_anne else "St. Ignatius College"
        pan_m = ST_PAN_RE.search(forward)
        if not pan_m:
            raise SystemExit(f"enfield {year}: no PAN found for {name}")
        pan = int(pan_m.group(1))
        crit_m = _st_crit_re("girls" if is_anne else "boys").search(wide)
        if crit_m:
            criterion, dist = crit_m.groups()
            groups, max_distance, all_offered = ["All"], {"All": float(dist)}, []
            notes = [f"All places offered by criterion {criterion} (siblings / faith) were within {dist} miles; "
                    "distance is the tie-break for the school's final oversubscription criterion, not the "
                    "primary allocation basis."]
        elif ST_ALL_RE.search(forward):
            groups, max_distance, all_offered = ["All"], {"All": None}, ["All"]
            notes = ["Places have been offered to all applicants (as published)."]
        else:
            raise SystemExit(f"enfield {year}: could not parse allocation narrative for {name}")
        out.append({
            "name": name, "year": year, "pan": pan, "applications": None, "groups": groups, "criteria": [],
            "max_distance": max_distance, "all_offered": all_offered, "non_preference_offers": None,
            "total_offers": None, "allocation": "faith_then_distance", "notes": notes,
        })
    m = QUOTA_NAME_RE.search(block)
    if m:
        window = block[m.start():m.start() + 400]
        if "Quota system" in window:
            nums_m = QUOTA_NUMS_RE.search(window)
            if not nums_m:
                raise SystemExit(f"enfield {year}: could not parse Enfield County School for Girls row")
            pan, ehcp, sib, parent = nums_m.groups()
            out.append({
                "name": "Enfield County School for Girls", "year": year, "pan": int(pan), "applications": None,
                "groups": ["All"],
                "criteria": [{"label": l, "total": int(v)} for l, v in (
                    ("Education, Health and Care Plan / Looked after / Medical", ehcp), ("Siblings", sib),
                    ("Parent employed at the school", parent)) if int(v)],
                "max_distance": {"All": None}, "all_offered": [], "non_preference_offers": None,
                "total_offers": None, "allocation": "mixed",
                "notes": ["Published as \"Not applicable - Quota system\": places are allocated by a gender "
                         "quota, not by the distance criterion."],
            })
        elif "Places have been offered to all applicants" in window:
            pan_m = re.search(r"Community\s+(\d+)", window)
            out.append({
                "name": "Enfield County School for Girls", "year": year, "pan": int(pan_m.group(1)),
                "applications": None, "groups": ["All"], "criteria": [], "max_distance": {"All": None},
                "all_offered": ["All"], "non_preference_offers": None, "total_offers": None,
                "allocation": "mixed",
                "notes": ["Places have been offered to all applicants (as published). In other years this "
                         "school allocates its remaining places by a gender quota, not by distance."],
            })
        else:
            raise SystemExit(f"enfield {year}: could not parse Enfield County School for Girls row")
    m = LATYMER_NAME_RE.search(block)
    if m:
        window = block[m.start():m.start() + 400]
        pan_m = LATYMER_PAN_RE.search(window)
        rank_m = LATYMER_RANK_RE.search(window)
        if not pan_m or not rank_m:
            raise SystemExit(f"enfield {year}: could not parse The Latymer School row")
        pan, rank = pan_m.group(1), rank_m.group(1)
        out.append({
            "name": "The Latymer School", "year": year, "pan": int(pan), "applications": None, "groups": ["All"],
            "criteria": [], "max_distance": {"All": None}, "all_offered": [], "non_preference_offers": None,
            "total_offers": None, "allocation": "mixed",
            "notes": [f"The Latymer School (a grammar school) offered places to children ranked up to number "
                     f"{rank} in the first round of offers (by entrance test, not distance)."],
        })
    m = WREN_RE.search(block)
    pan_m = WREN_PAN_RE.search(block)
    if m and pan_m:
        comm_places, comm_dist, found_places, ce_places, ce_dist, other_places, other_dist = m.groups()
        groups = ["Community", "Church of England", "Other Christian"]
        max_distance = {"Community": float(comm_dist), "Church of England": float(ce_dist) if ce_dist else None,
                        "Other Christian": float(other_dist) if other_dist else None}
        all_offered = [g for g, v in (("Church of England", ce_dist), ("Other Christian", other_dist)) if not v]
        out.append({
            "name": "Wren Academy Enfield", "year": year, "pan": int(pan_m.group(2)), "applications": None,
            "groups": groups, "criteria": [
                {"label": "Community places", "total": int(comm_places)},
                {"label": "Foundation: Church of England", "total": int(ce_places)},
                {"label": "Foundation: Other Christian", "total": int(other_places)}],
            "max_distance": max_distance, "all_offered": all_offered, "non_preference_offers": None,
            "total_offers": None, "allocation": "mixed",
            "notes": ["Wren Academy Enfield admits under two separate schemes: community places (by distance) and "
                     "Foundation places (Church of England / other Christian, then distance); \"demand met\" "
                     "years had no distance cut-off because applications did not exceed places in that group."],
        })
    return out


def parse(paths: list) -> list[dict]:
    records: list[dict] = []
    seen_years: set[int] = set()
    for path in paths:
        text = common.pdftotext(path)
        for year, block in _blocks(text):
            if year in seen_years:
                continue  # cross-checked manually; skip duplicate coverage across overlapping guide editions
            seen_years.add(year)
            records.extend(_generic_rows(block, year))
            records.extend(_special_rows(block, year))
    return records
