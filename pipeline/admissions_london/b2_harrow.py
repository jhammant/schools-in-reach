"""Harrow (LA 310): parse the council's "How places were allocated at Harrow
Secondary/Primary Schools" tables (one PDF per year and phase, 2022-2026).

Each row gives places available (PAN), applications received, offers per
admission criterion (EHC plan, looked after, medical/social, sibling, staff,
feeder, random allocation, Hindu faith places, distance) and the "furthest
distance offered in miles" (straight line, home to the centre point of the
school). Primary tables add offers "as the nearest school with a vacancy"
(non-preference offers) and total offered.

The column headers wrap over several lines (and in the 2022 editions are
rotated 90 degrees), so columns are recovered from the header words' horizontal
extents with pdfplumber and each value is assigned to the column above it.
The two Catholic secondaries and the voluntary-aided faith primaries are their
own admission authorities: the council prints only PAN, applications and
totals for them and refers parents to the school.
"""

from __future__ import annotations

import re

import b2_common as bc
import pdftools

LA_CODE = "310"
LA_NAME = "Harrow"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    # The table prints the short name; the open URN is "The Sacred Heart Language College" (HA3 7AY).
    bc.alias_key("Sacred Heart"): ("146245", "table prints the short name 'Sacred Heart'"),
    # Accented "Jérôme" does not tokenise like GIAS's "Saint Jerome Church of England Bilingual School".
    bc.alias_key("St Jérôme Church of England Bilingual School"):
        ("142904", "GIAS spells it Saint Jerome Church of England Bilingual School"),
}

BASE = "https://www.harrow.gov.uk/downloads/file/"
SECONDARY_DOCS = {
    2022: {"cache": "wb-secondary-2022.pdf",
           "url": "https://web.archive.org/web/20230325193317id_/" + BASE +
                  "29994/Secondary_school_place_allocations_2022_23.pdf",
           "title": "Harrow Council: How places were allocated at Harrow Secondary Schools for September 2022 "
                    "(Internet Archive copy; no longer on harrow.gov.uk)"},
    2023: {"cache": "secondary-2023.pdf", "url": BASE + "31344/How_places_were_allocated_22_23__website_ns.pdf",
           "title": "Harrow Council: How places were allocated at Harrow Secondary Schools for September 2023"},
    2024: {"cache": "secondary-2024.pdf", "url": BASE + "32426/How_places_were_allocated_2024_25_secondary.pdf",
           "title": "Harrow Council: How places were allocated at Harrow Secondary Schools for September 2024"},
    2025: {"cache": "secondary-2025.pdf", "url": BASE + "32972/How_places_were_allocated_25_26.pdf",
           "title": "Harrow Council: How places were allocated at Harrow Secondary Schools for September 2025"},
    2026: {"cache": "secondary-2026.pdf", "url": BASE + "33603/how-places-were-allocated-in-2026-27",
           "title": "Harrow Council: How places were allocated at Harrow Secondary Schools for September 2026"},
}
PRIMARY_DOCS = {
    2022: {"cache": "wb-primary-2022.pdf",
           "url": "https://web.archive.org/web/20231004112045id_/" + BASE +
                  "30858/R5___How_places_were_allocated_table_22_23.pdf",
           "title": "Harrow Council: How places were allocated at Harrow Primary Schools for September 2022 "
                    "(Internet Archive copy; no longer on harrow.gov.uk)"},
    2023: {"cache": "primary-2023.pdf", "url": BASE + "31543/R5___How_places_were_allocated_table_23_24_Landscape.pdf",
           "title": "Harrow Council: How places were allocated at Harrow Primary Schools for September 2023"},
    2024: {"cache": "primary-2024.pdf",
           "url": BASE + "32427/R5___How_places_were_allocated_table_24_25_Landscape__002_.pdf",
           "title": "Harrow Council: How places were allocated at Harrow Primary Schools for September 2024"},
    2025: {"cache": "primary-2025.pdf",
           "url": BASE + "33045/Reception_2025___How_places_were_allocated_at_Harrow_Schools.pdf",
           "title": "Harrow Council: How places were allocated at Harrow Primary Schools for September 2025"},
    2026: {"cache": "primary-2026.pdf", "url": BASE + "33701/primary-school-allocations-2026-27",
           "title": "Harrow Council: How places were allocated at Harrow Primary Schools for September 2026"},
}
DISTANCE_METHOD = "straight_line"
DISTANCE_NOTES = ('"Distance is measured in a straight line from the home address to the centre point of the school" '
                  "(footnote to every Harrow allocation table). Distances are published in miles.")

VALUE_RE = re.compile(r"^(N/A|\*|\d+(?:\.\d+)?\*{0,2}|\d*\s*\(\d+\*\))$")


def classify(label: str) -> str | None:
    parts = label.split(" | ")
    fwd = re.sub(r"[^A-Z]", "", label.upper())
    rev = "".join(re.sub(r"[^A-Z]", "", p.upper())[::-1] for p in parts)
    for s in (fwd, rev):
        rules = [
            (("FURTHEST", "BREAKER", "INMILES"), "cutoff"),
            (("VACANCY", "NEARESTSCHOOL"), "nearest"),
            (("TOTALOFFERED",), "total"),
            (("APPLICATION", "APPS"), "applications"),
            (("PLACEAVAILABLE", "PLACESAVAILABLE"), "pan"),
            (("EHC", "SPECIALEDUCATIONAL"), "EHC plan"),
            (("LOOKEDAFTER",), "Looked after children"),
            (("MEDICALSOCIAL",), "Medical/social need"),
            (("MEDICALPARENT",), "Medical need of parent"),
            (("SIBLING",), "Sibling"),
            (("STAFF",), "Children of staff"),
            (("FEEDER",), "Feeder school"),
            (("RANDOM",), "Random allocation"),
            (("NONISKCON",), "Hindu faith (non-ISKCON)"),
            (("ISKCON", "ISKON", "MANORTEMPLE"), "Hindu faith (ISKCON Bhaktivedanta Manor)"),
            (("HINDUPARENT",), "Hindu faith (non-ISKCON)"),
            (("DISTANCECRITERI",), "Distance"),
        ]
        for keys, kind in rules:
            if any(k in s for k in keys):
                return kind
    if fwd == "NES" or rev == "SEN":
        return "EHC plan"
    if fwd in ("E", "S", "SCHOOL", "NAME", "NAM", "CHOOL", "SCHOOLNAME"):
        return "name"
    return None


def _columns(words: list[pdftools.Word], top: float, bottom: float) -> list[tuple[str, float, float]]:
    cols = bc.header_columns(words, top, bottom, 0)
    # the 2022 editions print headers rotated, one narrow column per wrapped header line: merge those
    merged: list[list] = []
    for c in cols:
        if merged:
            prev = merged[-1]
            if (c.x1 - c.x0) < 20 and (prev[2] - prev[1]) < 45 and c.x0 - prev[2] < 5:
                prev[0] += " | " + c.label
                prev[2] = c.x1
                continue
        merged.append([c.label, c.x0, c.x1])
    out = []
    for label, x0, x1 in merged:
        kind = classify(label)
        if kind is None:
            raise SystemExit(f"harrow: unrecognised column header {label!r}")
        out.append((kind, x0, x1))
    return out


def _rows(path) -> list[dict]:
    rows = []
    with bc.open_pdf(path) as pdf:
        cols = None
        for page in pdf.pages:
            words = pdftools.page_words(page)
            lines = pdftools.group_lines(words)
            data = [l for l in lines if sum(bool(VALUE_RE.match(w.text)) for w in l.words) >= 3
                    and not l.text.lower().startswith(("how places", "* distance"))]
            if not data:
                continue
            hdr = next((l for l in lines if re.search(r"sibling|gnilbis|G N I L B I S", l.text, re.I)), None)
            if (hdr is not None and hdr.top < data[0].top) or (cols is None and data[0].top > 80):
                title = next((l for l in lines if "allocated" in l.text.lower()), None)
                top = max(w.bottom for w in title.words) + 2 if title is not None and title.top < data[0].top else 0
                cols = _columns(words, top, data[0].top - 1)
            if cols is None:
                raise SystemExit(f"harrow: no header found before data in {path.name}")
            value_x0 = min(x0 for kind, x0, _ in cols if kind in ("pan", "applications")) - 10
            first_top = data[0].top
            data = [l for l in lines if l.top >= first_top - 2
                    and sum(bool(VALUE_RE.match(w.text)) for w in l.words if w.x0 >= value_x0) >= 2
                    and not l.text.lower().startswith(("how places", "* distance", "*"))]
            value_cols = [bc.Column(kind, x0, x1) for kind, x0, x1 in cols if kind != "name"]
            name_words = [w for l in lines for w in l.words
                          if w.x1 <= value_x0 and not l.text.lower().startswith(("how places", "* distance", "*"))
                          and l.top > first_top - 30]
            per_line: dict[int, list[str]] = {i: [] for i in range(len(data))}
            for w in sorted(name_words, key=lambda w: (w.top, w.x0)):
                i = min(range(len(data)), key=lambda k: abs(data[k].cy - w.cy))
                if abs(data[i].cy - w.cy) <= 16:
                    per_line[i].append(w.text)
            for i, line in enumerate(data):
                vals = [w for w in line.words if w.x0 >= value_x0 and VALUE_RE.match(w.text)]
                cells = bc.assign(vals, value_cols, max_gap=25)
                named = {}
                for idx, texts in cells.items():
                    kind = value_cols[idx].label
                    if kind in named:
                        raise SystemExit(f"harrow {path.name}: two columns classified {kind!r}")
                    if len(texts) > 1 and all(re.fullmatch(r"\(\d+\*\)", t) for t in texts[1:]):
                        texts = [" ".join(texts)]
                    if len(texts) > 1:
                        raise SystemExit(f"harrow {path.name} {' '.join(per_line[i])}: several values {texts} "
                                         f"in column {kind!r}")
                    named[kind] = texts[0]
                rows.append({"name": " ".join(per_line[i]).strip(), "cells": named})
    return rows


FAITH = re.compile(r"Catholic|Church of England|\bC of E\b|CE\b|Hujjat|Avanti|Salvatorian|Sacred Heart|"
                   r"St Jérôme|St Jerome|Jewish|Moriah|Mosaic|Menorah|Krishna", re.I)
COUNT_ORDER = ["EHC plan", "Looked after children", "Medical/social need", "Medical need of parent", "Sibling",
               "Children of staff", "Feeder school", "Random allocation", "Hindu faith (ISKCON Bhaktivedanta Manor)",
               "Hindu faith (non-ISKCON)", "Distance"]


def _record(phase: str, year: int, row: dict) -> dict:
    cells = row["cells"]
    name = re.sub(r"\s+", " ", row["name"]).strip()
    pan, apps = bc.to_int(cells.get("pan")), bc.to_int(cells.get("applications"))
    criteria = []
    for label in COUNT_ORDER:
        raw = cells.get(label)
        n = bc.to_int(raw) if raw not in (None, "N/A", "*") else None
        if n is not None:
            criteria.append({"label": label, "total": n})
    cutoff_raw = cells.get("cutoff")
    cutoff = bc.to_float(cutoff_raw) if cutoff_raw not in (None, "N/A", "*") else None
    nearest = bc.to_int(cells.get("nearest")) if cells.get("nearest") not in (None, "N/A") else None
    total = bc.to_int(cells.get("total")) if cells.get("total") not in (None, "N/A") else None
    offered = total if total is not None else (sum(c["total"] for c in criteria) if criteria else None)
    notes = []
    breakdown = any(c["label"] in ("Sibling", "Distance") for c in criteria)
    if not breakdown:
        notes.append("Harrow's table gives only places, applications and total offers for this school, which is "
                     "its own admission authority: \"contact the school directly\" for the breakdown.")
    all_offered = False
    if cutoff is None and nearest:
        all_offered = True
        notes.append(f"No furthest distance was published and {nearest} place(s) went to children allocated this "
                     "school as the nearest with a vacancy: every applicant who named it was offered a place.")
    elif cutoff is None and offered is not None and pan is not None and offered < pan and (breakdown or total):
        all_offered = True
        notes.append(f"No furthest distance was published and {offered} offers were made against {pan} places: "
                     "every applicant was offered a place.")
    elif cutoff is None and breakdown:
        notes.append("No furthest distance was published: places were filled before the distance criterion "
                     "was needed to refuse anyone, or no distance offers were made.")
    if nearest:
        notes.append(f"{nearest} place(s) were offered to children refused all their preferences, as the nearest "
                     "school with a vacancy.")
    labels = {c["label"] for c in criteria}
    if "Random allocation" in labels and any(c["total"] for c in criteria if c["label"] == "Random allocation"):
        allocation = "mixed"
        notes.append("Some places are allocated by random allocation and the rest by distance; the furthest "
                     "distance applies to the distance places only.")
    elif FAITH.search(name) or any(l.startswith("Hindu") for l in labels):
        allocation = "faith_then_distance"
    else:
        allocation = "distance"
    if phase == "secondary":
        return bc.secondary_record(name, year, pan=pan, applications=apps, criteria=criteria,
                                   max_distance={"All": cutoff}, all_offered=["All"] if all_offered else [],
                                   non_preference_offers=nearest, total_offers=total, allocation=allocation,
                                   notes=notes)
    return bc.primary_record(name, year, pan=pan, applications=apps, criteria=criteria, max_distance=cutoff,
                             all_offered=all_offered, non_preference_offers=nearest, total_offers=total,
                             allocation=allocation, notes=notes)


def parse(phase: str, paths: dict[int, "Path"]) -> list[dict]:  # noqa: F821
    out = []
    for year, path in sorted(paths.items()):
        rows = _rows(path)
        if len(rows) < 8:
            raise SystemExit(f"harrow {phase} {year}: only {len(rows)} rows parsed")
        for row in rows:
            if not row["name"]:
                raise SystemExit(f"harrow {phase} {year}: row without a school name: {row['cells']}")
            out.append(_record(phase, year, row))
    return out
