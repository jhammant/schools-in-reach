"""Build site/data/hackney/admissions.json from Hackney Education's published
applications-and-offers PDFs (secondary Year 7 and primary Reception, 2018-2026).

Run from the project root:
    uv run --with pdfplumber python pipeline/admissions/build.py

Downloads are cached in pipeline/.cache/admissions/. The build fails loudly if
any hand-verified value is not reproduced.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import gias
import primary
import secondary

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "pipeline" / ".cache" / "admissions"
GIAS_CSV_GLOB = "gias_edubasealldata_*.csv"
OUT = ROOT / "site" / "data" / "hackney" / "admissions.json"

OGL = "Open Government Licence v3.0"
SECONDARY_PDF = {
    "title": "Hackney Education: Applications and Offers at Hackney Secondary Schools 2018-26",
    "url": "https://education.hackney.gov.uk/sites/default/files/document/"
           "Applications%20and%20Offers%20at%20Hackney%20Secondary%20Schools%202018-26.pdf",
    "licence": OGL,
    "cache": "sec_2018_26.pdf",
}
PRIMARY_PDF = {
    "title": "Hackney Education: Applications and Offers at Hackney Primary Schools 2018-26",
    "url": "https://education.hackney.gov.uk/sites/default/files/document/"
           "Applications%20and%20Offers%20at%20Hackney%20Primary%20Schools%202018-26.pdf",
    "licence": OGL,
    "cache": "pri_2018_26.pdf",
}
GIAS_SOURCE = {
    "title": "DfE Get Information about Schools (GIAS) establishment data, used to map school names to URNs",
    "url": "https://get-information-schools.service.gov.uk/Downloads",
    "licence": OGL,
}
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36",
    "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
IMPLAUSIBLE_MILES = 100.0

TOP_NOTES = [
    "Figures are as published by Hackney Education at national offer day; later offers and appeals are not included.",
    "Secondary 'groups' are the published column labels (ability bands A-E, Mossbourne Community Academy "
    "band x Inner/Middle/Outer zone, The Petchey Academy 2018-2022 band x Inner/Outer, The Urswick School "
    "Foundation/Community x band). Tables without bands use the single group 'All'.",
    "Secondary 'max_distance' is the home-to-school distance in miles of the last child offered a place by distance "
    "in each group; null when blank. Groups printed with '*' or 'N/A*' (all children in the band were offered) are "
    "listed in 'all_offered'. all_offered ['All'] means every on-time applicant was offered a place.",
    "Blank criteria cells in the source mean no offers under that criterion and are omitted from 'counts'.",
    "Values above 100 miles are kept as published; they mean the group was effectively undersubscribed.",
    "Primary 'all_offered' is as published for 2018-2022 (no 'last distance' shown / 'Yes' in the source). For "
    "2023-2026 the source gives no such flag, so it is derived: true when total offers were below the places "
    "available.",
    "Schools not listed for a year were able to offer all applicants who did not get a higher preference school a "
    "place (note in the 2021-2022 secondary pages).",
]


def fetch(spec: dict) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / spec["cache"]
    if not path.exists():
        req = urllib.request.Request(spec["url"], headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        if not data.startswith(b"%PDF"):
            raise SystemExit(f"download of {spec['url']} did not return a PDF")
        path.write_bytes(data)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    print(f"source {path.name}: {path.stat().st_size:,} bytes sha256:{digest}")
    return path


def gias_csv() -> Path:
    found = sorted((ROOT / "pipeline" / ".cache" / "shared").glob(GIAS_CSV_GLOB))
    if not found:
        raise SystemExit("GIAS extract not found in pipeline/.cache/shared/")
    return found[-1]


def _huge_distance_notes(max_distance: dict | float | None) -> list[str]:
    if isinstance(max_distance, dict):
        items = [(g, v) for g, v in max_distance.items() if v is not None and v > IMPLAUSIBLE_MILES]
        return [f"{'Band ' + g if len(g) == 1 else g}: published maximum distance {v} miles is not a real "
                "home-to-school distance; the group was effectively undersubscribed." for g, v in items]
    if max_distance is not None and max_distance > IMPLAUSIBLE_MILES:
        return [f"Published maximum distance {max_distance} miles is not a real home-to-school distance; "
                "the school was effectively undersubscribed."]
    return []


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def build_secondary(records: list[dict], matcher: gias.Gias, unmatched: list[dict], log: list[str]) -> dict:
    schools: dict[str, dict] = {}
    for rec in records:
        m = matcher.match(rec["name"], "secondary")
        if m is None:
            unmatched.append({"name_in_pdf": rec["name"], "year": rec["year"], "phase": "secondary"})
            continue
        if m.via != "name":
            log.append(f"secondary: {rec['name']!r} -> {m.urn} {m.name} via {m.via}")
        school = schools.setdefault(m.urn, {"urn": int(m.urn), "name": m.name, "status": m.status,
                                            "former_names": [], "former_urns": [], "years": {}})
        school["former_names"] = _dedupe(school["former_names"] + m.former_names)
        school["former_urns"] = sorted(set(school["former_urns"]) | {int(u) for u in m.former_urns})
        year = str(rec["year"])
        if year in school["years"]:
            raise SystemExit(f"duplicate secondary entry for {m.name} {year}")
        for w in rec.get("_warnings", []):
            log.append(f"secondary {rec['name']} {year} (p{rec['page']}): {w}")
        entry = {
            "pan": rec["pan"], "applications": rec["applications"], "groups": rec["groups"],
            "criteria": rec["criteria"], "max_distance": rec["max_distance"], "all_offered": rec["all_offered"],
            "non_preference_offers": rec["non_preference_offers"], "total_offers": rec["total_offers"],
            "band_totals": rec.get("band_totals", {}), "allocation": rec["allocation"],
            "notes": _dedupe(rec["notes"] + _huge_distance_notes(rec["max_distance"])),
        }
        if rec["name"] != m.name:
            entry["name_in_source"] = rec["name"]
        school["years"][year] = entry
    for school in schools.values():
        known = Counter(y["allocation"] for y in school["years"].values() if y["allocation"])
        for y in school["years"].values():
            if y["allocation"] is None and known:
                y["allocation"] = known.most_common(1)[0][0]
        _finish_school(school)
    return dict(sorted(schools.items(), key=lambda kv: kv[1]["name"]))


PRIMARY_PRIORITY = ["community_new", "aa_new", "community_mid", "aa_breakdown", "community_old", "aa_old",
                    "aa_summary", "all_old"]


def build_primary(records: list[dict], matcher: gias.Gias, unmatched: list[dict], log: list[str]) -> dict:
    grouped: dict[tuple[str, int], list[tuple[dict, gias.Match]]] = {}
    for rec in records:
        m = matcher.match(rec["name"], "primary")
        if m is None:
            unmatched.append({"name_in_pdf": rec["name"], "year": rec["year"], "phase": "primary"})
            continue
        if m.via != "name":
            log.append(f"primary: {rec['name']!r} -> {m.urn} {m.name} via {m.via}")
        grouped.setdefault((m.urn, rec["year"]), []).append((rec, m))

    schools: dict[str, dict] = {}
    for (urn, year), items in grouped.items():
        items.sort(key=lambda it: PRIMARY_PRIORITY.index(it[0]["kind"]))
        kinds = [it[0]["kind"] for it in items]
        if len(kinds) != len(set(kinds)):
            raise SystemExit(f"duplicate primary entries for URN {urn} {year}: {kinds}")
        m = items[0][1]
        school = schools.setdefault(urn, {"urn": int(urn), "name": m.name, "status": m.status, "type": None,
                                          "former_names": [], "former_urns": [], "years": {}})
        entry = {"pan": None, "applications": None, "total_offers": None, "criteria": [], "max_distance": None,
                 "all_offered": None, "non_preference_offers": None, "allocations": None, "notes": []}
        names = []
        for rec, match in items:
            school["former_names"] = _dedupe(school["former_names"] + match.former_names)
            school["former_urns"] = sorted(set(school["former_urns"]) | {int(u) for u in match.former_urns})
            names.append(rec["name"])
            for key in entry:
                if key == "notes":
                    entry["notes"] = _dedupe(entry["notes"] + rec["notes"])
                elif entry[key] in (None, []) and rec.get(key) not in (None, []):
                    entry[key] = rec[key]
            if rec["type"] and (school["type"] is None or year >= school.get("_type_year", 0)):
                school["type"], school["_type_year"] = rec["type"], year
        if entry["all_offered"] is None and entry["pan"] is not None and entry["total_offers"] is not None:
            entry["all_offered"] = entry["total_offers"] < entry["pan"]
        entry["notes"] = _dedupe(entry["notes"] + _huge_distance_notes(entry["max_distance"]))
        if names[0] != m.name:
            entry["name_in_source"] = names[0]
        school["years"][str(year)] = entry
    for school in schools.values():
        school.pop("_type_year", None)
        _finish_school(school)
    return dict(sorted(schools.items(), key=lambda kv: kv[1]["name"]))


def _finish_school(school: dict) -> None:
    school["years"] = dict(sorted(school["years"].items(), reverse=True))
    for key in ("former_names", "former_urns"):
        if not school[key]:
            del school[key]


# --------------------------------------------------------------------------- verification

CLAPTON = {  # URN 137442, bands A-E: (max distances, applications)
    2026: ([0.614, 0.746, 0.747, 0.885, 0.758], 580), 2025: ([0.995, 0.766, 0.747, 0.865, 0.954], 523),
    2024: ([0.985, 0.878, 0.607, 0.898, 0.875], 570), 2023: ([0.911, 1.125, 0.844, 0.857, 0.794], 587),
    2022: ([1.012, 0.998, 0.696, 0.686, 0.841], 568), 2021: ([0.915, 0.73, 0.838, 0.818, 0.799], 653),
    2020: ([1.156, 0.927, 0.764, 0.973, 0.856], 622), 2019: ([1.009, 0.834, 0.747, 0.707, 0.671], 671),
    2018: ([1.088, 0.745, 0.809, 0.779, 0.699], 635),
}
STOKE_NEWINGTON = {  # URN 100279, bands A-D
    2026: [7.21, 0.877, 0.754, 0.8], 2025: [1.766, 1.085, 0.897, 1.385], 2024: [0.673, 0.636, 0.589, 0.797],
    2023: [0.579, 0.911, 0.511, 0.88], 2022: [0.504, 0.532, 0.687, 0.9], 2021: [0.52, 0.603, 0.49, 0.522],
    2020: [0.481, 0.557, 0.747, 0.73], 2019: [0.655, 0.65, 0.672, 0.733],
}


class Checker:
    def __init__(self, data: dict):
        self.data = data
        self.failures: list[str] = []
        self.passed = 0

    def year(self, phase: str, urn: int, year: int) -> dict:
        try:
            return self.data[phase][str(urn)]["years"][str(year)]
        except KeyError:
            self.failures.append(f"{phase} URN {urn} {year}: missing")
            return {}

    def eq(self, label: str, actual, expected) -> None:
        if actual == expected:
            self.passed += 1
        else:
            self.failures.append(f"{label}: expected {expected!r}, got {actual!r}")

    @staticmethod
    def crit(entry: dict, label: str) -> dict:
        return next((c for c in entry.get("criteria", []) if c["label"] == label), {})


def verify(data: dict) -> Checker:
    c = Checker(data)
    # Hand-verified values supplied with the task.
    for year, (distances, apps) in CLAPTON.items():
        e = c.year("secondary", 137442, year)
        c.eq(f"Clapton {year} max_distance", [e.get("max_distance", {}).get(b) for b in "ABCDE"], distances)
        c.eq(f"Clapton {year} applications", e.get("applications"), apps)
    e = c.year("secondary", 137442, 2026)
    c.eq("Clapton 2026 PAN", e.get("pan"), 180)
    c.eq("Clapton 2026 Sibling total", c.crit(e, "Sibling").get("total"), 53)
    c.eq("Clapton 2026 Distance total", c.crit(e, "Distance").get("total"), 115)
    for year, distances in STOKE_NEWINGTON.items():
        e = c.year("secondary", 100279, year)
        c.eq(f"Stoke Newington {year} max_distance", [e.get("max_distance", {}).get(b) for b in "ABCD"], distances)
    e = c.year("secondary", 143756, 2026)
    c.eq("CoLA Shoreditch Park 2026 max_distance", e.get("max_distance"),
         {"A": 1.657, "B": 0.619, "C": 0.358, "D": 0.448})
    c.eq("CoLA Shoreditch Park 2026 applications", e.get("applications"), 735)
    c.eq("CoLA Shoreditch Park 2026 PAN", e.get("pan"), 180)

    # Spot checks read directly from the PDF text (pdftotext -layout plus word coordinates).
    zones = [f"{b} {z}" for b in "ABCD" for z in ("Inner", "Middle", "Outer")]
    e = c.year("secondary", 134693, 2024)  # Mossbourne Community Academy, secondary PDF p7
    c.eq("MCA 2024 applications/PAN", (e.get("applications"), e.get("pan")), (1282, 216))
    c.eq("MCA 2024 Random", ([c.crit(e, "Random").get("counts", {}).get(z) for z in zones],
                             c.crit(e, "Random").get("total")), ([17, 12, 8, 4, 5, 4, 12, 8, 9, 7, 6, 5], 97))
    c.eq("MCA 2024 Sibling", [c.crit(e, "Sibling").get("counts", {}).get(z) for z in zones],
         [11, 3, 3, 8, 10, 5, 10, 3, 1, 8, 3, 4])
    c.eq("MCA 2024 allocation/total", (e.get("allocation"), e.get("total_offers")), ("random_by_zone", 218))
    e = c.year("secondary", 100284, 2025)  # The Urswick CE School, secondary PDF p6
    c.eq("Urswick 2025 max_distance", e.get("max_distance"), {
        "Foundation A": 3.643, "Foundation B": 2.99, "Foundation C": 1.886, "Foundation D": 1.27,
        "Community A": None, "Community B": 1.63, "Community C": 1.653, "Community D": 351.708})
    c.eq("Urswick 2025 apps/PAN/NPO/total", (e.get("applications"), e.get("pan"), e.get("non_preference_offers"),
                                             e.get("total_offers")), (260, 150, 4, 87))
    c.eq("Urswick 2025 Sibling/Distance totals",
         (c.crit(e, "Sibling").get("total"), c.crit(e, "Distance").get("total")), (28, 45))
    e = c.year("secondary", 131609, 2019)  # The Bridge Academy, 2018-2020 page (PDF p30)
    c.eq("Bridge 2019 max_distance", e.get("max_distance"), {"A": None, "B": None, "C": 0.66, "D": 0.579, "E": 0.317})
    c.eq("Bridge 2019 all_offered", e.get("all_offered"), ["A", "B"])
    c.eq("Bridge 2019 Sibling", c.crit(e, "Sibling").get("counts"), {"A": 9, "B": 10, "C": 19, "D": 16, "E": 20})
    c.eq("Bridge 2019 apps/total", (e.get("applications"), e.get("total_offers")), (747, 189))
    e = c.year("secondary", 131062, 2022)  # The Petchey Academy (now Excelsior), PDF p14
    c.eq("Petchey 2022 Random A Inner / total / apps",
         (c.crit(e, "Random").get("counts", {}).get("A Inner"), e.get("total_offers"), e.get("applications")),
         (19, 189, 544))
    e = c.year("primary", 131706, 2019)  # Betty Layward, primary PDF p20
    c.eq("Betty Layward 2019", (e.get("pan"), e.get("applications"), e.get("max_distance"), e.get("all_offered")),
         (61, 277, 0.305, False))
    c.eq("Betty Layward 2019 siblings/distance",
         (c.crit(e, "Children with siblings at the school").get("total"), c.crit(e, "Distance").get("total")), (28, 33))
    e = c.year("primary", 142112, 2019)  # Hackney New Primary School, primary PDF p24
    c.eq("Hackney New Primary 2019", (e.get("applications"), e.get("total_offers"), e.get("max_distance")),
         (267, 50, 0.3))
    c.eq("Hackney New Primary 2019 criteria",
         (c.crit(e, "Siblings of children at Hackney New Primary School").get("total"),
          c.crit(e, "Distance").get("total")), (16, 34))
    e = c.year("primary", 140426, 2022)  # Mossbourne Riverside Academy, primary PDF p11-12
    c.eq("Mossbourne Riverside 2022", (e.get("pan"), e.get("applications"), e.get("total_offers"),
                                       e.get("max_distance"), e.get("all_offered")), (90, 233, 90, 0.621, False))
    c.eq("Mossbourne Riverside 2022 criteria",
         (c.crit(e, "Sibling").get("total"), c.crit(e, "Distance").get("total")), (37, 51))
    e = c.year("primary", 130303, 2026)  # Gayhurst Community School, primary PDF p1
    c.eq("Gayhurst 2026", (e.get("pan"), e.get("applications"), e.get("total_offers"), e.get("max_distance"),
                           e.get("non_preference_offers")), (60, 247, 60, 0.344, 0))
    c.eq("Gayhurst 2026 criteria", [x["total"] for x in e.get("criteria", [])], [1, 0, 0, 0, 17, 1, 41])
    return c


def main() -> None:
    sec_pdf, pri_pdf = fetch(SECONDARY_PDF), fetch(PRIMARY_PDF)
    matcher = gias.Gias(gias_csv())
    unmatched: list[dict] = []
    log: list[str] = []
    data = {
        "generated": dt.date.today().isoformat(),
        "sources": [{k: s[k] for k in ("title", "url", "licence")} for s in (SECONDARY_PDF, PRIMARY_PDF, GIAS_SOURCE)],
        "notes": TOP_NOTES,
        "secondary": build_secondary(secondary.parse(sec_pdf), matcher, unmatched, log),
        "primary": build_primary(primary.parse(pri_pdf), matcher, unmatched, log),
        "unmatched": sorted(unmatched, key=lambda u: (u["phase"], u["name_in_pdf"], u["year"])),
    }
    for line in dict.fromkeys(log):
        print("  " + line)

    checker = verify(data)
    if checker.failures:
        print(f"\nVERIFICATION FAILED ({len(checker.failures)} of {len(checker.failures) + checker.passed}):",
              file=sys.stderr)
        for failure in checker.failures:
            print("  " + failure, file=sys.stderr)
        raise SystemExit(1)
    print(f"verification: {checker.passed} checks passed")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for phase in ("secondary", "primary"):
        schools = data[phase]
        years = sum(len(s["years"]) for s in schools.values())
        span = sorted({y for s in schools.values() for y in s["years"]})
        print(f"{phase}: {len(schools)} schools, {years} school-years ({span[0]}-{span[-1]})")
    print(f"unmatched: {len(data['unmatched'])}")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
