"""Haringey (LA 309): parse the council's two "distance from school of last
child offered a place on national offer day" pages (HTML tables, 2022-2026).
Like Islington, only the cut-off distance is published -- no PAN, applications
or criteria breakdown -- but Haringey's page states explicitly what "N/A"
means ("these schools offered all applicants a place on national offer day"),
so all_offered can be set from it without guessing. "Banded" schools test
rather than measure distance; "Contact school" means the figure was withheld.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

LA_CODE = "309"
LA_NAME = "Haringey"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {}

SECONDARY_PAGE = {
    "title": "Haringey Council: Secondary schools - distance from school of last child offered place "
             "on national offer day",
    "url": "https://haringey.gov.uk/schools-learning/schools/school-admissions/how-school-place-offers-were-made/"
           "cutoff-distance-school-last-child-offered-place/"
           "secondary-schools-distance-school-last-child-offered-place-national-offer-day",
    "licence": "Open Government Licence v3.0",
    "cache": "secondary-cutoff.html",
    "kind": "html",
}
PRIMARY_PAGE = {
    "title": "Haringey Council: Primary schools - distance from school of last child offered place "
             "on national offer day",
    "url": "https://haringey.gov.uk/schools-learning/schools/school-admissions/how-school-place-offers-were-made/"
           "cutoff-distance-school-last-child-offered-place/"
           "primary-schools-distance-school-last-child-offered-place-national-offer-day",
    "licence": "Open Government Licence v3.0",
    "cache": "primary-cutoff.html",
    "kind": "html",
}
DISTANCE_NOTES = ('"Distance from school in miles of last child offered a place under the distance criterion." '
                  '"N/A means these schools offered all applicants a place on national offer day." Banded schools '
                  '("Harris Academy Tottenham") offer places based on a test, not distance. The method of measuring '
                  'distance (straight line vs. walking route) is not stated on these pages.')
DISTANCE_METHOD = "unknown"

SPARSE_NOTE = ("Only the cut-off (last-offered) distance is published for Haringey schools on this page; "
              "applications, PAN and admission-criteria breakdowns are not published here.")


def _parse_table(html: str) -> tuple[list[str], dict[str, dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if len(tables) != 1:
        raise SystemExit(f"haringey: expected exactly 1 table, found {len(tables)}")
    rows = tables[0].find_all("tr")
    header = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    years = header[1:]
    for y in years:
        if not re.fullmatch(r"20\d\d", y):
            raise SystemExit(f"haringey: unexpected year header {y!r}")
    schools: dict[str, dict[str, str]] = {}
    for r in rows[1:]:
        cells = [c.get_text(strip=True) for c in r.find_all(["th", "td"])]
        if not cells:
            continue
        name = re.sub(r"\s+", " ", cells[0].replace("\xa0", " ")).strip()
        schools[name] = dict(zip(years, cells[1:]))
    return years, schools


def _records(years: list[str], schools: dict[str, dict[str, str]]) -> list[dict]:
    out = []
    for name, by_year in schools.items():
        for year, raw in by_year.items():
            max_distance, all_offered, allocation, notes = None, [], "distance", [SPARSE_NOTE]
            if raw == "N/A":
                all_offered = ["All"]
                notes.append("N/A: the school offered all applicants a place on national offer day.")
            elif raw == "Banded":
                allocation = "mixed"
                notes.append("This school allocates by a banding test, not primarily by distance.")
            elif raw == "Contact school":
                notes.append("Distance not published; the council directs enquiries to the school "
                             "(a faith or banded school).")
            else:
                max_distance = float(raw)
            out.append({
                "name": name, "year": int(year), "pan": None, "applications": None, "groups": ["All"],
                "criteria": [], "max_distance": {"All": max_distance}, "all_offered": all_offered,
                "non_preference_offers": None, "total_offers": None, "allocation": allocation, "notes": notes,
            })
    return out


def _primary_records(years: list[str], schools: dict[str, dict[str, str]]) -> list[dict]:
    out = []
    for name, by_year in schools.items():
        for year, raw in by_year.items():
            max_distance, all_offered, allocation, notes = None, False, "distance", [SPARSE_NOTE]
            if raw == "N/A":
                all_offered = True
                notes.append("N/A: the school offered all applicants a place on national offer day.")
            elif raw == "Banded":
                allocation = "mixed"
                notes.append("This school allocates by a banding test, not primarily by distance.")
            elif raw == "Contact school":
                notes.append("Distance not published; the council directs enquiries to the school "
                             "(a faith or banded school).")
            else:
                max_distance = float(raw)
            out.append({
                "name": name, "year": int(year), "pan": None, "applications": None, "total_offers": None,
                "criteria": [], "max_distance": max_distance, "all_offered": all_offered,
                "non_preference_offers": None, "allocation": allocation, "notes": notes,
            })
    return out


def parse(secondary_path, primary_path) -> tuple[list[dict], list[dict]]:
    sec_years, sec_schools = _parse_table(secondary_path.read_text(encoding="utf-8"))
    pri_years, pri_schools = _parse_table(primary_path.read_text(encoding="utf-8"))
    return _records(sec_years, sec_schools), _primary_records(pri_years, pri_schools)
