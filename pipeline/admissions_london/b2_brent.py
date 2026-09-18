"""Brent (LA 304): parse "How places were allocated at Brent secondary schools"
(September 2024-2026) and "How places were offered - Reception" (2024-2026).

Each school block lists its published admission number, the offers made under
each admission criterion (EHCP, looked after, sibling, feeder, faith
categories, distance, "nearest school with a vacancy") and, per criterion, the
furthest distance offered in metres; from 2025 (Reception) and 2026 (secondary)
the block also says whether the school was over- or undersubscribed and how
many applications it had.

Brent does not print a single cut-off. For an oversubscribed school the
furthest distance of the last criterion that received offers (the lowest
priority criterion reached) is recorded as the cut-off. For undersubscribed
schools, or where places went to children allocated the school as the nearest
with a vacancy, every applicant was offered a place. Criteria in the Reception
2024 edition are listed alphabetically, not in priority order, so the cut-off
for that year is taken only from a school's general "any other applicant" /
"distance" category, and left empty for faith schools with several categories.
"""

from __future__ import annotations

import re

import b2_common as bc

LA_CODE = "304"
LA_NAME = "Brent"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {}

BASE = "https://www.brent.gov.uk/-/media/files/resident-documents/education-documents/"
SECONDARY_DOCS = {
    2024: {"cache": "secondary-2024.pdf", "url": BASE + "how-secondary-school-places-were-allocated-2024.pdf"},
    2025: {"cache": "secondary-2025.pdf", "url": BASE + "how-places-were-offered---secondary-2025.pdf"},
    2026: {"cache": "secondary-2026.pdf",
           "url": BASE + "how-secondary-school-places-were-allocated---2026---publish-v2.pdf"},
}
PRIMARY_DOCS = {
    2024: {"cache": "reception-2024.pdf", "url": BASE + "how-places-were-offered-reception-2024.pdf"},
    2025: {"cache": "reception-2025.pdf", "url": BASE + "how-places-were-offered-reception-2025.pdf"},
    2026: {"cache": "reception-2026.pdf", "url": BASE + "how-places-were-offered-reception-2026.pdf"},
}
DISTANCE_METHOD = "unknown"
DISTANCE_NOTES = ("Brent publishes, for each admission criterion, the furthest distance offered in metres "
                  "(converted to miles here); the measurement method is not stated in these tables. Furthest "
                  "distance is not shown for looked-after, social/medical, pupil premium and staff children.")

STATUS_RE = r"(?P<status>Oversubscribed|Undersubscribed|Fully subscribed)"
CRIT_RE = re.compile(r"^(?P<label>\S.*?)\s{2,}(?P<n>\d+)\*?(?:\s+(?P<dist>\d+(?:\.\d+)?)(?!\s*applications))?"
                     rf"(?:\s+{STATUS_RE})?(?:\s+(?P<apps>\d+) applications)?\s*$")
NSWV = "Nearest school with a vacancy"
FAITH_RE = re.compile(r"Catholic|Cath\b|C R P|CRP|Orthodox|Jew|Christian|Church|Parish|Faith|Hindu|Muslim|Sikh|"
                      r"Baptised|Bapt\b|Religious|Anglican|Synagogue|Mosque|Islamic", re.I)
GENERAL_RE = re.compile(r"^(Any Other Applicants?|All Other Applicants?|Distance|Other Applicants)$", re.I)
SENTINEL = 999999.0
# criteria whose furthest distance is not a distance cut-off (places given on need, aptitude or reservation)
NOT_CUTOFF_RE = re.compile(r"^EHCP$|Aptitude|Reserved|Looked After|L A C|Social|Medical|Staff|Pupil Premium|Eypp", re.I)


def _blocks_secondary(text: str) -> list[dict]:
    lines = text.splitlines()
    hdr = next(l for l in lines if "Criteria/Band" in l)
    split = hdr.index("Criteria/Band") - 2
    blocks: list[dict] = []
    for line in lines:
        if not line.strip() or "How places were" in line or "Data as at" in line or "EHCP =" in line:
            continue
        if line.startswith(("School Name", "(Published")):
            continue
        cut = split
        while cut < len(line) and line[cut - 1] != " " and line[cut] != " ":
            cut += 1  # a long school name running past the criteria column
        left, right = line[:cut].strip(), line[cut:].strip()
        if left and not left.startswith("("):
            m = re.match(r"^(?P<name>.*?)\s*(?:\((?P<pan>\d+)\))?$", left)
            blocks.append({"name": m["name"], "pan": int(m["pan"]) if m["pan"] else None, "criteria": [],
                           "status": None, "apps": None, "total": None})
        elif left.startswith("("):
            blocks[-1]["pan"] = int(re.match(r"\((\d+)\)", left).group(1))
        if not right:
            continue
        if right.startswith("Total"):
            blocks[-1]["total"] = int(right.split()[-1])
            continue
        m = CRIT_RE.match(right)
        if not m:
            raise SystemExit(f"brent secondary: unreadable criterion line {right!r}")
        _add(blocks[-1], m)
    return blocks


def _add(block: dict, m: re.Match) -> None:
    label = re.sub(r"^\d+\s+", "", m["label"]).strip()
    block["criteria"].append({"label": label, "n": int(m["n"]),
                              "dist": float(m["dist"]) if m["dist"] else None})
    if m["status"]:
        block["status"] = m["status"]
    if m["apps"]:
        block["apps"] = int(m["apps"])


SCHOOL_RE = re.compile(rf"^(?P<name>\S.*?)(?:\s*\((?P<pan>\d+)\))?\s{{2,}}(?:(?P<apps>\d+)\s+)?(?P<offers>\d+)\*?"
                       rf"\s+{STATUS_RE}\s*$")


def _blocks_primary(text: str) -> list[dict]:
    blocks: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            m = SCHOOL_RE.match(line)
            if m:
                blocks.append({"name": m["name"].strip(), "pan": int(m["pan"]) if m["pan"] else None,
                               "apps": int(m["apps"]) if m["apps"] else None, "offers": int(m["offers"]),
                               "status": m["status"], "criteria": [], "total": int(m["offers"])})
            continue
        if not blocks or not line.startswith("  ") or line.startswith("   " * 10):
            continue
        m = CRIT_RE.match(line.strip())
        if m and not line.strip().startswith(("School /", "Furthest", "Number of")):
            _add(blocks[-1], m)
    return blocks


def _cutoff(block: dict, ordered: bool) -> tuple[float | None, str | None]:
    preference = [c for c in block["criteria"] if c["label"] != NSWV and not NOT_CUTOFF_RE.search(c["label"])]
    with_dist = [c for c in preference if c["dist"] is not None]
    if not with_dist:
        return None, None
    if ordered:
        last = with_dist[-1]
    else:
        general = [c for c in with_dist if GENERAL_RE.match(c["label"])]
        if len(general) != 1:
            return None, None
        last = general[0]
    return last["dist"], last["label"]


def _record(phase: str, year: int, block: dict) -> dict:
    ordered = not (phase == "primary" and year == 2024)
    nswv = sum(c["n"] for c in block["criteria"] if c["label"] == NSWV)
    criteria = [{"label": c["label"], "total": c["n"]} for c in block["criteria"]]
    labels = " ".join(c["label"] for c in block["criteria"])
    faith_name = re.search(r"CofE|C of E|\bRC\b|Catholic|Church|Jewish|Islamia|Torah|Hindu|Sikh|Muslim|JFS|"
                           r"Menorah|Mosaic|Avanti|Swaminarayan", block["name"])
    allocation = "faith_then_distance" if FAITH_RE.search(labels) or faith_name else "distance"
    if re.search(r"Zone [A-Z]|Random|Banding|Band [A-Z]", labels):
        allocation = "mixed"
    notes = []
    furthest = [f"{c['label']}: {bc.miles_from_metres(c['dist'])} mi" for c in block["criteria"]
                if c["dist"] is not None and c["dist"] < SENTINEL]
    if furthest:
        notes.append("Furthest distance offered by criterion (converted from metres): " + "; ".join(furthest) + ".")
    if any(c["dist"] == SENTINEL for c in block["criteria"]):
        notes.append("A furthest distance of 999999 is printed for one criterion; it is a placeholder, not a "
                     "distance, and is ignored.")
    undersubscribed = block["status"] == "Undersubscribed" or nswv > 0
    all_offered = False
    max_distance = None
    if undersubscribed:
        all_offered = True
        why = (f"{nswv} place(s) went to children allocated it as the nearest school with a vacancy"
               if nswv else "Brent marks it undersubscribed")
        notes.append(f"Every applicant was offered a place: {why}.")
    else:
        dist, label = _cutoff(block, ordered)
        if dist is not None and dist < SENTINEL:
            max_distance = bc.miles_from_metres(dist)
            notes.append(f"Cut-off taken as the furthest distance offered under the last criterion reached, "
                         f"\"{label}\" ({dist:g} metres).")
        elif not ordered:
            notes.append("This edition lists criteria alphabetically rather than in priority order, and the school "
                         "has no single general distance category, so no cut-off is recorded.")
    if block.get("sites"):
        notes.append("Brent prints this school's sites separately (" + "; ".join(
            f"{site} site: {status or 'status not given'}" for site, status in block["sites"]) +
            "); the figures are combined here and criteria are prefixed by site.")
        if block["status"] is None and not undersubscribed:
            max_distance = None
            notes.append("The sites differ in status, so no single cut-off is recorded.")
    if block.get("status"):
        notes.append(f"Brent status: {block['status']}.")
    if phase == "secondary":
        return bc.secondary_record(block["name"], year, pan=block["pan"], applications=block["apps"],
                                   criteria=criteria, max_distance={"All": max_distance},
                                   all_offered=["All"] if all_offered else [], non_preference_offers=nswv,
                                   total_offers=block["total"], allocation=allocation, notes=notes)
    return bc.primary_record(block["name"], year, pan=block["pan"], applications=block["apps"], criteria=criteria,
                             max_distance=max_distance, all_offered=all_offered, non_preference_offers=nswv,
                             total_offers=block["total"], allocation=allocation, notes=notes)


SITE_RE = re.compile(r"^(?P<base>.*?)\s+-\s+(?P<site>.+?) site$", re.I)


def _merge_sites(blocks: list[dict]) -> list[dict]:
    """A school admitting on two sites is printed as two blocks ("Leopold Primary School - Hawkshead Road site");
    GIAS has one URN, so combine them, keeping each site's criteria under a site prefix."""
    out: list[dict] = []
    by_base: dict[str, dict] = {}
    for blk in blocks:
        m = SITE_RE.match(blk["name"])
        if not m:
            out.append(blk)
            continue
        base, site = m["base"].strip(), m["site"].strip()
        crits = [dict(c, label=f"{site} site: {c['label']}" if c["label"] != NSWV else NSWV) for c in blk["criteria"]]
        if base not in by_base:
            merged = dict(blk, name=base, criteria=crits, sites=[(site, blk["status"])])
            by_base[base] = merged
            out.append(merged)
            continue
        merged = by_base[base]
        merged["criteria"] += crits
        merged["sites"].append((site, blk["status"]))
        for key in ("pan", "apps", "total", "offers"):
            if merged.get(key) is not None and blk.get(key) is not None:
                merged[key] += blk[key]
        if blk["status"] != merged["status"]:
            merged["status"] = None
    return out


def parse(phase: str, paths: dict) -> list[dict]:
    out = []
    for year, path in sorted(paths.items()):
        text = bc.text_of(path)
        blocks = _blocks_secondary(text) if phase == "secondary" else _blocks_primary(text)
        if len(blocks) < (12 if phase == "secondary" else 50):
            raise SystemExit(f"brent {phase} {year}: only {len(blocks)} schools parsed")
        blocks = _merge_sites(blocks)
        for block in blocks:
            if not block["criteria"]:
                raise SystemExit(f"brent {phase} {year} {block['name']}: no criteria parsed")
            out.append(_record(phase, year, block))
    return out
