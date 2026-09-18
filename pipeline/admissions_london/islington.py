"""Islington (LA 206): parse the council's "Cut-off distances for schools in
Islington" page (an HTML table, not a downloadable file). It publishes, for
each primary and secondary school, the home-to-school distance in miles of
the last child admitted under the distance criterion for the three most
recent admission years. No PAN, applications or admission-criteria breakdown
is published on this page, and "Not applicable" is not explained precisely
enough to safely infer all_offered (the page notes VA/faith schools' cut-off
"does not apply" to applicants admitted on faith grounds before distance is
reached, so "Not applicable" can mean undersubscribed OR simply "never
reached distance" for a faith school) -- so all_offered is left unset and the
ambiguity is recorded in a note instead of guessed.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

LA_CODE = "206"
LA_NAME = "Islington"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    # Source spells it "Myddlelton"; GIAS spells the open URN "Myddelton" (one fewer 'l').
    "hugh myddlelton": ("131842", "spelling variant in source: Hugh Myddelton Primary School"),
}

PAGE = {
    "title": "Islington Council: Cut off distances for schools in Islington",
    "url": "https://www.islington.gov.uk/children-and-families/schools/apply-for-a-school-place/"
           "school-admissions-information/cut-off-distance-maps",
    "licence": "Open Government Licence v3.0",
    "cache": "cutoff-distances.html",
    "kind": "html",
}

DISTANCE_NOTES = ('"The cut-off distance is the home-to-school distance for the child who gets the last place at '
                  'the school." For voluntary-aided schools with a religious character, the published cut-off "is '
                  'only for applicants who were considered for a place using only home-to-school distance as a '
                  'reason. It does not apply to other applicants considered under reasons of faith or church."')
DISTANCE_METHOD = "unknown"  # method of measurement is not stated on this page

YEAR_RE = re.compile(r"Distance \(miles\) in (\d{4})-\d{2}")
FAITH_RE = re.compile(r"Catholic|Church of England", re.I)


def _split_group(name: str) -> tuple[str, str]:
    m = re.match(r"^(.*) Band (\d+)$", name)
    if m:
        return m.group(1).strip(), f"Band {m.group(2)}"
    m = re.match(r"^(.*)\s+\(([^)]+)\)$", name)
    if m:
        return m.group(1).strip(), m.group(2)
    return name, "All"


def _parse_table(table, notes_not_applicable: list[str]) -> dict[str, dict]:
    rows = table.find_all("tr")
    header = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    year_cols = [(m.group(1), i) for i, h in enumerate(header) if (m := YEAR_RE.match(h))]
    schools: dict[str, dict] = {}
    for r in rows[1:]:
        cells = [c.get_text(strip=True) for c in r.find_all(["th", "td"])]
        if len(cells) < 2:
            continue
        base, group = _split_group(cells[0])
        entry = schools.setdefault(base, {"type": cells[1], "bands": {}})
        vals = {}
        for year, idx in year_cols:
            raw = cells[idx] if idx < len(cells) else "Not applicable"
            if raw in ("Not applicable", ""):
                vals[year] = None
                notes_not_applicable.append(f"{cells[0]} {year}")
            else:
                vals[year] = float(raw)
        entry["bands"][group] = vals
    return schools


def _allocation(school_type: str) -> str:
    return "faith_then_distance" if FAITH_RE.search(school_type) else "distance"


SPARSE_NOTE = ("Only the cut-off (last-offered) distance is published for Islington schools on this page; "
              "applications, PAN and admission-criteria breakdowns are not published here. \"Not applicable\" "
              "is left as an unknown cut-off (not assumed to mean every applicant was offered a place), because "
              "for voluntary-aided/faith schools it can instead mean every place was filled by an applicant "
              "admitted under a faith criterion before distance was reached.")


def _secondary_records(schools: dict[str, dict]) -> list[dict]:
    out = []
    for name, info in schools.items():
        groups = sorted(info["bands"])
        years = sorted({y for b in info["bands"].values() for y in b})
        for year in years:
            max_distance = {g: info["bands"][g].get(year) for g in groups}
            out.append({
                "name": name, "year": int(year), "pan": None, "applications": None, "groups": groups,
                "criteria": [], "max_distance": max_distance, "all_offered": [], "non_preference_offers": None,
                "total_offers": None, "allocation": _allocation(info["type"]), "notes": [SPARSE_NOTE],
            })
    return out


def _primary_records(schools: dict[str, dict]) -> list[dict]:
    out = []
    for name, info in schools.items():
        bands = info["bands"]
        assert list(bands) == ["All"], f"islington primary: unexpected bands for {name}: {list(bands)}"
        years = sorted(bands["All"])
        for year in years:
            out.append({
                "name": name, "year": int(year), "pan": None, "applications": None, "total_offers": None,
                "criteria": [], "max_distance": bands["All"][year], "all_offered": False,
                "non_preference_offers": None, "allocation": _allocation(info["type"]), "notes": [SPARSE_NOTE],
            })
    return out


def parse(path) -> tuple[list[dict], list[dict]]:
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if len(tables) != 2:
        raise SystemExit(f"islington: expected 2 tables (primary, secondary), found {len(tables)}")
    na_notes: list[str] = []
    primary_schools = _parse_table(tables[0], na_notes)
    secondary_schools = _parse_table(tables[1], na_notes)
    return _secondary_records(secondary_schools), _primary_records(primary_schools)
