"""Camden (LA 202): parse the "Secondary Schools in Camden" and "Starting
School in Camden" admissions guides (PDF, via pdftotext -layout). Each guide's
"Allocation of places" section carries two years of cut-off distances plus a
criteria table (applications, EHCP, siblings, social/medical) for the two most
recent years at publication time, so two guide editions together give up to
four years. Community secondary tables also cover Camden School for Girls'
four bands.

Only community/comprehensive secondary schools and community primary schools
appear in these tables; the guides state voluntary-aided/faith schools with
"n/a" or "*" had vacant places or must be asked directly.
"""

from __future__ import annotations

import re

import common

LA_CODE = "202"
LA_NAME = "Camden"
# GIAS records these two schools' names without an apostrophe, while the admissions guides print one; the
# shared tokeniser's `'s` normalisation only fires when an apostrophe is present, so it doesn't bridge this.
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "joseph st": ("100041", "GIAS spells it without an apostrophe: St Josephs Catholic Primary School"),
    "cross king": ("140686", "GIAS spells it without an apostrophe: Kings Cross Academy"),
}

SECONDARY_GUIDES = [
    {"title": "Camden Council: Secondary Schools in Camden 2025", "cache": "secondary-guide-2025.pdf",
     "url": "https://www.brecknock.camden.sch.uk/wp-content/uploads/2025/03/"
            "Secondary-schools-in-Camden-admissions-guide-2025-WEB.pdf",
     "licence": "Open Government Licence v3.0", "kind": "pdf",
     "note": "as republished by Brecknock Primary School (camden.gov.uk blocks automated downloads)"},
    {"title": "Camden Council: Secondary Schools in Camden 2026", "cache": "secondary-guide-2026.pdf",
     "url": "https://www.brecknock.camden.sch.uk/wp-content/uploads/2025/12/"
            "Secondary-Schools-in-Camden-2026-admissions-guide-1.pdf",
     "licence": "Open Government Licence v3.0", "kind": "pdf",
     "note": "as republished by Brecknock Primary School (camden.gov.uk blocks automated downloads)"},
]
PRIMARY_GUIDES = [
    {"title": "Camden Council: Starting School in Camden 2023", "cache": "primary-guide-2023.pdf",
     "url": "https://www.brecknock.camden.sch.uk/wp-content/uploads/2024/02/"
            "Starting-School-in-Camden-2023-admissions-guide.pdf",
     "licence": "Open Government Licence v3.0", "kind": "pdf",
     "note": "as republished by Brecknock Primary School (camden.gov.uk blocks automated downloads)"},
    {"title": "Camden Council: Starting School in Camden 2026", "cache": "primary-guide-2026.pdf",
     "url": "https://www.brecknock.camden.sch.uk/wp-content/uploads/2025/12/"
            "Starting-School-in-Camden-2026-admissions-guide-1.pdf",
     "licence": "Open Government Licence v3.0", "kind": "pdf",
     "note": "as republished by Brecknock Primary School (camden.gov.uk blocks automated downloads)"},
]
DISTANCE_METHOD = "straight_line"
DISTANCE_NOTES = ('"Applications are considered based on distance from the child\'s home to the school... measured '
                  'in a straight line from the home address to the school using a computerised mapping system." '
                  '(secondary guide, admissions criteria). The primary guide adds: distance is "measured in a '
                  'straight line between the home and school addresses" using address co-ordinates, "to the centre '
                  'of the school".')

YEARS_RE = re.compile(r"when the offers were published in March (20\d\d) and March (20\d\d)")
YEARS_RE_PRIMARY = re.compile(r"when the results were published\s*\n?\s*in April (20\d\d) and April (20\d\d)")
BAND_ROW = re.compile(r"^\s+Band ([A-D]):\s+(\S+)\s+(\S+)\s*$")
NAME_DIST_ROW = re.compile(r"^\s*(\S.*?)(?:\s+Band ([A-D]):)?\s{2,}(\S+)\s+(\S+)\s*$")
CRIT_ROW = re.compile(r"^\s*(\S.*?)\s{2,}(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")
FAITH_RE = re.compile(r"Catholic|Church of England|Jewish", re.I)


NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?")


def _num(raw: str) -> float | None:
    if raw in ("n/a", "-", "*", "–"):
        return None
    m = NUM_RE.match(raw)
    if not m:
        raise SystemExit(f"camden: unreadable numeric value {raw!r}")
    return float(m.group(0))


def _cutoff_table(lines: list[str]) -> dict[str, dict[str, tuple[float | None, float | None]]]:
    """Returns {school_name: {band_or_'All': (value_for_year_a, value_for_year_b)}}."""
    schools: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    last_name = None
    for line in lines:
        m = BAND_ROW.match(line)
        if m and last_name:
            band, va, vb = m.group(1), m.group(2), m.group(3)
            schools[last_name][f"Band {band}"] = (_num(va), _num(vb))
            continue
        m = NAME_DIST_ROW.match(line)
        if not m:
            continue
        name, band, va, vb = m.group(1).strip(), m.group(2), m.group(3), m.group(4)
        if name in ("School", "(distances)"):
            continue  # the "School <year> <year>" / "(distances) (distances)" header rows themselves
        schools.setdefault(name, {})
        schools[name][f"Band {band}" if band else "All"] = (_num(va), _num(vb))
        last_name = name
    return schools


def _crit_table(lines: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in lines:
        m = CRIT_ROW.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        out[name] = list(m.groups()[1:])
    return out


def _section(text: str, start_marker: str, end_marker: str) -> list[str]:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end].splitlines()


def _find(text: str, pattern: str, start: int = 0) -> int:
    m = re.search(pattern, text[start:], re.M)
    if not m:
        raise SystemExit(f"camden: pattern not found: {pattern!r}")
    return start + m.start()


def _parse_guide(text: str, phase: str) -> list[dict]:
    if phase == "secondary":
        m = YEARS_RE.search(text)
        year_a, year_b = sorted((int(m.group(1)), int(m.group(2))), reverse=True)  # table lists most-recent-first
        start = _find(text, r"^School\s+" + str(year_a))
        end = _find(text, r"^n/a - These schools had vacant places", start)
        cutoff_lines = text[start:end].splitlines()
        start = _find(text, r"^Acland Burghley School", end)
        end = _find(text, r"^\s*Other local authority", start)
        crit_lines = text[start:end].splitlines()
    else:
        m = re.search(r"in April (20\d\d) and April (20\d\d)", text)
        year_a, year_b = sorted((int(m.group(1)), int(m.group(2))), reverse=True)
        idx = text.index("Furthest child")
        crit_start = _find(text, r"^\s*Abacus\b", idx)
        crit_end = _find(text, r"^\s*\*\s*-\s*Check with the school", crit_start)
        crit_lines = text[crit_start:crit_end].splitlines()

    records: list[dict] = []
    if phase == "secondary":
        cutoffs = _cutoff_table(cutoff_lines)
        crit = _crit_table(crit_lines)
        names = sorted(set(cutoffs) | set(crit))
        for name in names:
            bands = cutoffs.get(name, {"All": (None, None)})
            groups = sorted(bands)
            crow = crit.get(name)
            allocation = "mixed" if len(groups) > 1 else ("faith_then_distance" if FAITH_RE.search(name) else "distance")
            for i, year in enumerate((year_a, year_b)):
                max_distance = {g: bands[g][i] for g in groups}
                pan = applications = ehcp = siblings = socmed = None
                criteria = []
                notes = []
                if crow:
                    (places, apps_a, apps_b, la_a, la_b, ehcp_a, ehcp_b, sib_a, sib_b, soc_a, soc_b) = crow
                    apps, la, ehcp_v, sib, soc = (apps_a, la_a, ehcp_a, sib_a, soc_a) if i == 0 else \
                                                 (apps_b, la_b, ehcp_b, sib_b, soc_b)
                    pan = int(places) if i == 0 and places not in ("*", "-") else None
                    applications = int(apps) if apps not in ("*", "-") else None
                    for label, raw in (("Looked after children", la), ("Education, Health and Care Plan", ehcp_v),
                                       ("Siblings", sib), ("Social/medical", soc)):
                        if raw in ("*", "-"):
                            if raw == "*":
                                notes.append(f"{label}: not published for {name} {year} "
                                            "(\"contact the school directly\").")
                            continue
                        criteria.append({"label": label, "total": int(raw)})
                all_offered = []
                if all(v is None for v in max_distance.values()) and crow:
                    all_offered = list(groups)
                    notes.append("n/a: the school had vacant places when the offers were published, so the "
                                 "distance criterion was not reached.")
                records.append({
                    "name": name, "year": year, "pan": pan, "applications": applications, "groups": groups,
                    "criteria": criteria, "max_distance": max_distance, "all_offered": all_offered,
                    "non_preference_offers": None, "total_offers": None, "allocation": allocation, "notes": notes,
                })
    else:
        for line in crit_lines:
            m = CRIT_ROW.match(line)
            if not m:
                continue
            name = m.group(1).strip()
            (adm, apps_a, apps_b, ehcp_a, ehcp_b, sib_a, sib_b, soc_a, soc_b, dist_a, dist_b) = m.groups()[1:]
            for i, year in enumerate((year_a, year_b)):
                apps, ehcp_v, sib, soc, dist = (apps_a, ehcp_a, sib_a, soc_a, dist_a) if i == 0 else \
                                               (apps_b, ehcp_b, sib_b, soc_b, dist_b)
                pan = int(adm) if i == 0 and adm not in ("*", "-") else None
                applications = int(apps) if apps not in ("*", "-") else None
                criteria, notes = [], []
                for label, raw in (("Education, Health and Care Plan", ehcp_v), ("Siblings", sib),
                                   ("Social/medical", soc)):
                    if raw in ("*", "-"):
                        if raw == "*":
                            notes.append(f"{label}: not published for {name} {year} "
                                        "(\"contact the school directly\").")
                        continue
                    criteria.append({"label": label, "total": int(raw)})
                max_distance = _num(dist)
                all_offered = False
                if dist == "n/a":
                    all_offered = True
                    notes.append("n/a: the school had vacant places after the offer date.")
                records.append({
                    "name": name, "year": year, "pan": pan, "applications": applications, "total_offers": None,
                    "criteria": criteria, "max_distance": max_distance, "all_offered": all_offered,
                    "non_preference_offers": None, "allocation": "distance", "notes": notes,
                })
    return records


def _merge(records: list[dict]) -> list[dict]:
    """Guide editions overlap by one year; merge same (name, year) records,
    preferring non-null values and cross-checking where both sources agree."""
    by_key: dict[tuple[str, int], dict] = {}
    for rec in records:
        key = (rec["name"], rec["year"])
        if key not in by_key:
            by_key[key] = rec
            continue
        prev = by_key[key]
        for field in ("pan", "applications", "max_distance"):
            a, b = prev.get(field), rec.get(field)
            if a is not None and b is not None and a != b:
                raise SystemExit(f"camden: conflicting {field} for {key}: {a!r} vs {b!r}")
            if a is None and b is not None:
                prev[field] = b
        if not prev.get("criteria") and rec.get("criteria"):
            prev["criteria"] = rec["criteria"]
    return list(by_key.values())


def parse(paths: list, phase: str) -> list[dict]:
    out = []
    for path in paths:
        text = common.pdftotext(path)
        out.extend(_parse_guide(text, phase))
    return _merge(out)
