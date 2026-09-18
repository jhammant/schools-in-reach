"""Ealing (LA 307): parse Ealing Council's "High school allocations for
September <year>" and "Applications and offers for each primary school on
National Offer Day" PDFs (pdftotext -layout).

Each school either reads "All applicants offered" or has a small table of
admission criteria with the number of applicants, offered and refused, and the
"straight line distance of last place offered (tie-breaker)" for the criterion
where places ran out ("N/A - all offered" / "N/A - all refused" elsewhere).
Community primary schools share one table with a single row each. There is no
PAN column: total offers are the EHCP placements plus the offers per criterion.

Where a school prints a distance for more than one criterion (Twyford CE's
foundation and world-faith bands, Ark Soane's two measuring points "town hall"
and "school"), each becomes a group. Drayton Manor High School's 2021 table
measures the "shortest walking distance"; every other table is straight line.

Editions: secondary 2021, 2022, 2024, 2025, 2026 and primary 2020, 2022, 2024,
2025, 2026. The ealing.gov.uk download ids are reused for the next year's file,
so the 2021, 2022, 2024 (and primary 2020, 2022, 2024) editions are Internet
Archive snapshots; their offer-day dates were checked inside each PDF. No 2023
edition (either phase) or 2021 primary edition survives in the archive.
"""

from __future__ import annotations

import re

import b2_common as bc

LA_CODE = "307"
LA_NAME = "Ealing"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    # GIAS still records URN 101943 at Eastcote Lane, Northolt UB5 4HP under its former name, Islip Manor High School;
    # the only state secondary at that postcode is Northolt High School.
    bc.alias_key("Northolt High School"): ("101943", "GIAS name for this URN (UB5 4HP) is Islip Manor High School"),
}

DL = "https://www.ealing.gov.uk/download/downloads/id/"
WB = "https://web.archive.org/web/{ts}id_/" + DL
SECONDARY_DOCS = {
    2021: {"cache": "wb-high-2021.pdf", "url": WB.format(ts="20210927031857") +
           "15982/high_school_on_time_offers_2021.pdf"},
    2022: {"cache": "wb-high-2022.pdf", "url": WB.format(ts="20221004141557") +
           "15982/high_school_on_time_offers_2022.pdf"},
    2024: {"cache": "wb-high-2024.pdf", "url": WB.format(ts="20240530194452") +
           "18711/high_school_on_time_offers_2024.pdf"},
    2025: {"cache": "high-offers-2025.pdf", "url": DL + "18711/high_school_on_time_offers_2025.pdf"},
    2026: {"cache": "high-offers-2026.pdf", "url": DL + "21309/high_school_on_time_offers_2026.pdf"},
}
PRIMARY_DOCS = {
    2020: {"cache": "wb-primary-2020.pdf", "url": WB.format(ts="20210924063346") +
           "14153/priamary_school_on_time_offers_2020.pdf"},
    2022: {"cache": "wb-primary-2022.pdf", "url": WB.format(ts="20230207172631") +
           "17681/primary_school_on-time_offers_2022.pdf"},
    2024: {"cache": "wb-primary-2024.pdf", "url": WB.format(ts="20240710224301") +
           "18843/primary_school_on-time_offers_2024.pdf"},
    2025: {"cache": "primary-offers-2025.pdf", "url": DL + "18843/primary_school_on-time_offers_2024.pdf",
           "note": "file name says 2024 but the PDF is dated National Offer Day 16 April 2025"},
    2026: {"cache": "primary-offers-2026.pdf", "url": DL + "21522/primary_school_on-time_offers_2026.pdf"},
}
DISTANCE_METHOD = "mixed"
DISTANCE_NOTES = ("Ealing's tables give the \"straight line distance of last place offered (tie-breaker)\" in miles "
                  "(\"of a mile\" below one mile). Drayton Manor High School's 2021 table instead gives the "
                  "\"shortest walking distance of last place offered\".")

YEAR_RE = re.compile(r"(?:ALLOCATIONS FOR SEPTEMBER|National Offer Day \(\d+\w* \w+)\s+(20\d\d)", re.I)
SCHOOLISH = re.compile(r"(School|Academy|College|High|Primary|Infant|Junior|Girls)\b")
HEADERISH = re.compile(r"^(Criteria|Number|Places|Straight line|Shortest walking|place offered|last|School$|School\s+applicants|"
                       r"COMMUNITY SCHOOLS|Community Schools|Academies|ACADEMIES|HIGH SCHOOL ALLOCATIONS|"
                       r"Applications and offers|Please see|Ealing Borough|\*|All applicants offered)", re.I)
CRIT_RE = re.compile(r"^\s*(?:\d{1,2}\s+(?!points))?(?P<label>\S.*?)\s{2,}(?P<a>\d+)\s+(?P<o>\d+)\s+(?P<r>\d+)\s+(?P<dist>\S.*?)\s*$")
COMMUNITY_RE = re.compile(r"^(?P<name>\S.*?)\s{2,}(?:(?P<a>\d+|N/A)\s+(?P<o>\d+|N/A)\s+(?P<r>\d+|N/A)|"
                          r"All applicants offered)\s+(?P<dist>\S.*?)\s*$")
DIST_RE = re.compile(r"(\d+\.\d+)\s+(?:miles?|of a mile)(?:\s+\(([^)]+)\))?")
EXTRA_DIST_RE = re.compile(r"^\s{30,}(\d+\.\d+)\s+(?:miles?|of a mile)\s+\(([^)]+)\)\s*$")
BAND_RE = re.compile(r"^\s*([A-Z][A-Za-z ]* Band)\s*$")
FAITH_RE = re.compile(r"\bCE\b|Church of England|Catholic|\bR[Cc]\b|Khalsa|Twyford|William Perkin|Ada Lovelace|"
                      r"Christ the Saviour|\bSt\.? [A-Z]")


def _blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    community = False
    cur: dict | None = None
    band = None

    def new(name: str) -> dict:
        nonlocal band
        band = None
        blk = {"name": name.strip(), "rows": [], "ehcp": None, "all": False, "walking": False, "community": False}
        blocks.append(blk)
        return blk

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^(COMMUNITY SCHOOLS|Community Schools)$", s):
            community = True
            continue
        if re.match(r"^(Academies|ACADEMIES)", s):
            community = False
            continue
        m = re.match(r"^(?P<name>[A-Z][^:]*?)\s*:\s*(?P<all>All applicants offered)?\s*$", s)
        if m and SCHOOLISH.search(m["name"]) and not s.startswith("Places allocated"):
            community = False
            cur = new(m["name"])
            cur["all"] = bool(m["all"])
            continue
        if community:
            m = COMMUNITY_RE.match(s)
            if m and SCHOOLISH.search(m["name"]):
                blk = new(m["name"])
                blk["community"] = True
                blk["all"] = m["a"] is None  # "All applicants offered" in place of the counts
                blk["rows"].append({"label": "All applicants", "band": None, "a": m["a"], "o": m["o"],
                                    "r": m["r"], "dist": m["dist"]})
                cur = None
                continue
            if not (line.startswith(" " * 10) and SCHOOLISH.search(s) and not re.search(r"\d", s)
                    and not HEADERISH.match(s)):
                continue
            community = False  # 2020/2022: the academies' blocks follow without a section heading
        if s.startswith("Places allocated to children with an Education Health"):
            if cur is not None:
                cur["ehcp"] = int(re.search(r"(\d+)\s*$", s).group(1))
            continue
        if "Shortest walking distance" in s and cur is not None:
            cur["walking"] = True
            continue
        if s == "All applicants offered" and cur is not None:
            cur["all"] = True
            continue
        mb = BAND_RE.match(line)
        if mb and cur is not None:
            band = mb.group(1)
            continue
        me = EXTRA_DIST_RE.match(line)
        if me and cur is not None and cur["rows"]:
            cur["rows"][-1]["dist"] += f" {me.group(1)} miles ({me.group(2)})"
            continue
        mc = CRIT_RE.match(line)
        if mc and cur is not None:
            cur["rows"].append({"label": mc["label"], "band": band, "a": mc["a"], "o": mc["o"], "r": mc["r"],
                                "dist": mc["dist"]})
            continue
        if not re.search(r"\d", s) and SCHOOLISH.search(s) and not HEADERISH.match(s) and len(s) < 70:
            cur = new(s)  # school name on its own line (centred in 2020-2022, left-aligned for 2025-26 primaries)
    return blocks


def _num(raw: str | None) -> int | None:
    return int(raw) if raw and raw.isdigit() else None


def _record(phase: str, year: int, blk: dict) -> dict:
    notes: list[str] = []
    rows = blk["rows"]
    cut = []
    for row in rows:
        for value, site in DIST_RE.findall(row["dist"]):
            label = row["label"] if not row["band"] else f"{row['band']}: {row['label']}"
            cut.append((f"{label} ({site})" if site else label, float(value), row))
    labels_text = " ".join(r["label"] for r in rows) + " " + blk["name"]
    all_offered = blk["all"] or any("all applicants offered" in r["dist"].lower() for r in rows)
    if blk["all"]:
        notes.append("Published as \"All applicants offered\".")
    for label, value, row in cut:
        notes.append(f"{label}: {row['a']} applicants, {row['o']} offered, {row['r']} refused; last place offered at "
                     f"{value} miles.")
    refused_all = [r["label"] for r in rows if "all refused" in r["dist"].lower()]
    if refused_all:
        notes.append("No places were left for: " + "; ".join(refused_all) + ".")
    if blk["walking"]:
        notes.append("This table gives the shortest walking distance, not the straight-line distance.")
    offered = [n for n in (_num(r["o"]) for r in rows) if n is not None]
    criteria = ([{"label": "Education, Health and Care Plan", "total": blk["ehcp"]}] if blk["ehcp"] is not None else [])
    criteria += [{"label": (f"{r['band']}: " if r["band"] else "") + r["label"], "total": _num(r["o"])}
                 for r in rows if _num(r["o"]) is not None and not blk["community"]]
    total = (blk["ehcp"] or 0) + sum(offered) if offered else None
    if phase == "primary":
        row = rows[0] if blk["community"] else None
        value = cut[-1][1] if cut else None
        if all_offered and value is not None:
            notes.append("A distance is printed although the school is published as having offered all applicants.")
        allocation = "faith_then_distance" if FAITH_RE.search(labels_text) else "distance"
        if row and row["a"] and row["a"].isdigit() and row["r"] and row["r"].isdigit() and all_offered \
                and int(row["r"]) > 0:
            notes.append(f"Published as all applicants offered although {row['r']} applicant(s) are counted as "
                         "refused (most likely offered a higher preference).")
        return bc.primary_record(blk["name"], year, applications=_num(row["a"]) if row else None,
                                 criteria=criteria, max_distance=None if all_offered and not cut else value,
                                 all_offered=all_offered and not cut, total_offers=_num(row["o"]) if row else total,
                                 allocation=allocation, notes=notes)
    groups = ["All"] if len(cut) <= 1 else [c[0] for c in cut]
    max_distance = {g: c[1] for g, c in zip(groups, cut)} if cut else {"All": None}
    if len(groups) > 1:
        allocation = "mixed"
        notes.append("Distances are printed for more than one criterion or measuring point; each is a group.")
    elif FAITH_RE.search(labels_text):
        allocation = "faith_then_distance"
    else:
        allocation = "distance"
    return bc.secondary_record(blk["name"], year, groups=groups, criteria=criteria, max_distance=max_distance,
                               all_offered=["All"] if all_offered and not cut else [], total_offers=total,
                               allocation=allocation, notes=notes)


def parse(phase: str, paths: dict) -> list[dict]:
    out = []
    for year, path in sorted(paths.items()):
        text = bc.text_of(path)
        printed = {int(y) for y in YEAR_RE.findall(text)}
        if printed != {year}:
            raise SystemExit(f"ealing {phase} {year}: document is dated {sorted(printed)}")
        blocks = _blocks(text)
        if len(blocks) < (12 if phase == "secondary" else 40):
            raise SystemExit(f"ealing {phase} {year}: only {len(blocks)} schools parsed")
        for blk in blocks:
            if not blk["rows"] and not blk["all"]:
                raise SystemExit(f"ealing {phase} {year} {blk['name']}: no rows parsed")
            out.append(_record(phase, year, blk))
    return out
