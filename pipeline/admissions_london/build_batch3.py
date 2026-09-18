"""Build site/data/la/<la_code>/admissions.json for eight more London boroughs
(Southwark, Lambeth, Lewisham, Greenwich, Wandsworth, Merton, Kingston upon
Thames, Richmond upon Thames) from each council's published Year 7 / Reception
admissions data, modelled on the working Hackney pipeline (pipeline/admissions/
build.py) and batch 1 (pipeline/admissions_london/build.py).

Run from the project root:
    uv run --with pdfplumber --with openpyxl --with pandas --with beautifulsoup4 \
        python pipeline/admissions_london/build_batch3.py

Downloads are cached in pipeline/.cache/admissions_london/<la_code>/. This
file is this batch's entry point; it does not import or modify build.py or
build_batch2.py (other agents' entry points), only the shared common.py/
gias.py/pdftools.py helpers and this batch's own b3_<borough>.py modules.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from types import ModuleType

import b3_greenwich
import b3_kingston
import b3_lambeth
import b3_lewisham
import b3_merton
import b3_richmond
import b3_southwark
import b3_wandsworth
import common
import gias

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "site" / "data" / "la"


def dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def make_matcher(module: ModuleType) -> gias.Gias:
    return gias.Gias(common.gias_csv(), module.LA_CODE, getattr(module, "MANUAL_ALIASES", {}))


def build_json(la_code: str, la_name: str, sources: list[dict], distance_method: str, distance_notes: str,
               secondary_records: list[dict], primary_records: list[dict], matcher: gias.Gias,
               missing_note: str) -> dict:
    unmatched: list[dict] = []
    log: list[str] = []
    secondary = common.assemble(secondary_records, matcher, "secondary", unmatched, log)
    primary = common.assemble(primary_records, matcher, "primary", unmatched, log)
    for line in dedupe(log):
        print("  " + line)
    sec_years = sorted({y for s in secondary.values() for y in s["years"]})
    pri_years = sorted({y for s in primary.values() for y in s["years"]})
    return {
        "generated": dt.date.today().isoformat(),
        "la_code": la_code, "la_name": la_name,
        "sources": sources,
        "distance_method": distance_method,
        "distance_notes": distance_notes,
        "secondary": secondary, "primary": primary,
        "unmatched": sorted(unmatched, key=lambda u: (u["phase"], u["name_in_source"], u["year"])),
        "coverage": {"secondary_years": sec_years, "primary_years": pri_years, "missing": missing_note},
    }


def write(la_code: str, data: dict) -> None:
    out = OUT_DIR / la_code / "admissions.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for phase in ("secondary", "primary"):
        schools = data[phase]
        years = sum(len(s["years"]) for s in schools.values())
        span = sorted({y for s in schools.values() for y in s["years"]})
        span_txt = f"{span[0]}-{span[-1]}" if span else "none"
        print(f"  {phase}: {len(schools)} schools, {years} school-years ({span_txt})")
    print(f"  unmatched: {len(data['unmatched'])}")
    print(f"  wrote {out.relative_to(ROOT)} ({out.stat().st_size:,} bytes)")


def build_borough(module: ModuleType) -> dict:
    secondary, primary = module.build()
    return build_json(module.LA_CODE, module.LA_NAME, module.SOURCES, module.DISTANCE_METHOD,
                      module.DISTANCE_NOTES, secondary, primary, make_matcher(module), module.MISSING_NOTE)


MODULES = [b3_southwark, b3_lambeth, b3_lewisham, b3_greenwich, b3_wandsworth, b3_merton, b3_kingston, b3_richmond]


# --------------------------------------------------------------------------- verification
#
# Hand-checked values below were read directly from the cached source documents (HTML tables or
# pdftotext -layout output), independently of each borough module's own parser.

class Checker:
    def __init__(self):
        self.failures: list[str] = []
        self.passed = 0

    def eq(self, label: str, actual, expected) -> None:
        if actual == expected:
            self.passed += 1
        else:
            self.failures.append(f"{label}: expected {expected!r}, got {actual!r}")

    def close(self, label: str, actual, expected: float, tol: float = 0.001) -> None:
        if actual is not None and abs(actual - expected) <= tol:
            self.passed += 1
        else:
            self.failures.append(f"{label}: expected ~{expected!r}, got {actual!r}")


def verify(all_data: dict[str, dict]) -> Checker:
    c = Checker()

    def year(la: str, phase: str, urn: int, yr: int) -> dict:
        try:
            return all_data[la][phase][str(urn)]["years"][str(yr)]
        except KeyError:
            c.failures.append(f"{la} {phase} URN {urn} {yr}: missing")
            return {}

    # lewisham (209): from the council's "last year's number of applications and appeals" secondary page and
    # the "GRID for reception" primary PDF (both read directly, independently of the module's own parser)
    c.close("lewisham Deptford Green School 2026 max_distance",
           year("209", "secondary", 100740, 2026).get("max_distance", {}).get("All"), 1.945)
    c.close("lewisham Forest Hill School 2026 max_distance",
           year("209", "secondary", 100745, 2026).get("max_distance", {}).get("All"), 1.073)
    c.close("lewisham Adamsrill Primary School 2021 max_distance",
           year("209", "primary", 100671, 2021).get("max_distance"), 2.705)
    c.close("lewisham Ashmead Primary School 2026 max_distance",
           year("209", "primary", 100716, 2026).get("max_distance"), 0.411)

    # southwark (210): from "Allocation of community school places by criteria" (primary) and the secondary
    # PAN table (no outcome data is published for Southwark secondaries -- see module docstring)
    e = year("210", "primary", 130918, 2026)  # Bessemer Grange
    c.eq("southwark Bessemer Grange 2026 applications/pan", (e.get("applications"), e.get("pan")), (217, 60))
    c.close("southwark Bessemer Grange 2026 max_distance", e.get("max_distance"), 0.629)
    e = year("210", "primary", 100793, 2025)  # Heber
    c.close("southwark Heber 2025 max_distance", e.get("max_distance"), 0.229)
    c.eq("southwark Kingsdale Foundation School 2026 pan",
        year("210", "secondary", 136309, 2026).get("pan"), 420)
    c.eq("southwark City of London Academy (Southwark) 2026 pan",
        year("210", "secondary", 134222, 2026).get("pan"), 240)

    # greenwich (203): from the "Secondary/Primary Schools in Royal Greenwich" admission booklets (distances
    # published in km for secondary, metres for primary; both read directly and converted independently here)
    c.close("greenwich Ark Greenwich Free School 2023 max_distance",
           year("203", "secondary", 138245, 2023).get("max_distance", {}).get("All"), 0.913)
    c.close("greenwich Harris Academy Greenwich 2025 Band 3 max_distance",
           year("203", "secondary", 138449, 2025).get("max_distance", {}).get("Band 3"), 4.418)
    c.close("greenwich James Wolfe Primary School and Centre for the Deaf 2023 max_distance (nodal point)",
           year("203", "primary", 131246, 2023).get("max_distance"), 5.272)
    c.close("greenwich Rockliffe Manor Primary School 2022 max_distance",
           year("203", "primary", 143593, 2022).get("max_distance"), 0.933)

    # wandsworth (212): from "How school places were offered for secondary schools 2026", "Previous years'
    # admissions at Wandsworth secondary schools" (2022-2025) and "How places were allocated for primary
    # schools <year>" (distances published in metres)
    c.close("wandsworth Ashcroft Technology Academy 2026 Band A max_distance (2659m)",
           year("212", "secondary", 135316, 2026).get("max_distance", {}).get("Band A"), 1.652)
    c.close("wandsworth Burntwood School 2025 Selective max_distance (3220m)",
           year("212", "secondary", 139842, 2025).get("max_distance", {}).get("Selective"), 2.001)
    c.close("wandsworth Graveney School 2022 Selective max_distance (693m)",
           year("212", "secondary", 137005, 2022).get("max_distance", {}).get("Selective"), 0.431)
    c.close("wandsworth Beatrix Potter Primary School 2025 max_distance (789m)",
           year("212", "primary", 100997, 2025).get("max_distance"), 0.49)
    c.close("wandsworth Gatton (VA) Primary School 2023 max_distance (2424m)",
           year("212", "primary", 134041, 2023).get("max_distance"), 1.506)

    # merton (315): from "School admissions and appeals data for recent years" (Sept 2026 edition), the
    # National Offer Day ("first round") furthest-distance figure for each school/year
    c.close("merton Ricards Lodge High School 2026 max_distance",
           year("315", "secondary", 102673, 2026).get("max_distance", {}).get("All"), 1.979)
    c.close("merton Rutlish School 2026 max_distance",
           year("315", "secondary", 102679, 2026).get("max_distance", {}).get("All"), 1.782)
    c.close("merton Dundonald Primary School 2026 max_distance (outside APA)",
           year("315", "primary", 102628, 2026).get("max_distance"), 0.237)
    c.close("merton Wimbledon Chase Primary School 2021 max_distance",
           year("315", "primary", 102662, 2021).get("max_distance"), 0.35)

    # lambeth (208): per-school "Secondary Transfer <year> National Offer Day details of offers" PDFs and the
    # primary "How offers were made" tables (metres)
    e = year("208", "secondary", 100638, 2026)  # Bishop Thomas Grant Catholic Secondary School
    c.eq("lambeth Bishop Thomas Grant 2026 applications/pan", (e.get("applications"), e.get("pan")), (772, 180))
    c.close("lambeth Bishop Thomas Grant 2026 max_distance (3123.010m)", e.get("max_distance", {}).get("All"), 1.941)
    c.close("lambeth Dunraven School 2026 Band 1.1 max_distance (1128.19m)",
           year("208", "secondary", 137093, 2026).get("max_distance", {}).get("Band 1.1"), 0.701)
    c.close("lambeth The Elms Academy 2026 max_distance (1515.09m)",
           year("208", "secondary", 134815, 2026).get("max_distance", {}).get("All"), 0.941)
    c.close("lambeth Ashmole Primary School 2026 max_distance (654.28m)",
           year("208", "primary", 100556, 2026).get("max_distance"), 0.407)
    c.close("lambeth Reay Primary School 2024 max_distance (1030.53m)",
           year("208", "primary", 100634, 2024).get("max_distance"), 0.640)

    # kingston (314): AfC "How places were allocated at Kingston borough secondary schools for the last three
    # years" (km) and "How places have been allocated at community infant and primary schools" (km)
    c.close("kingston Coombe Boys' School 2025 max_distance (2.624 km)",
           year("314", "secondary", 137859, 2025).get("max_distance", {}).get("All"), 1.630)
    c.eq("kingston Coombe Boys' School 2025 pan", year("314", "secondary", 137859, 2025).get("pan"), 180)
    c.close("kingston Tolworth Girls' School 2024 max_distance (3.937 km)",
           year("314", "secondary", 137060, 2024).get("max_distance", {}).get("All"), 2.446)
    c.eq("kingston Tiffin School 2025 allocation", year("314", "secondary", 136910, 2025).get("allocation"),
         "selective")
    c.close("kingston Alexandra Primary School 2023 max_distance (0.657 km)",
           year("314", "primary", 102578, 2023).get("max_distance"), 0.408)
    c.close("kingston Malden Manor Primary and Nursery School 2022 max_distance (2.495 km)",
           year("314", "primary", 102581, 2022).get("max_distance"), 1.550)

    # richmond (318): AfC/council "National Offer Day distance offers" (secondary, km) and the 2022-2024
    # community infant and primary allocation table (km)
    c.close("richmond Grey Court School 2025 max_distance (2.706 km)",
           year("318", "secondary", 138825, 2025).get("max_distance", {}).get("All"), 1.681)
    c.close("richmond Teddington School 2021 max_distance (4.120 km)",
           year("318", "secondary", 138460, 2021).get("max_distance", {}).get("All"), 2.560)
    c.close("richmond Waldegrave School 2024 priority area B max_distance (5.543 km)",
           year("318", "secondary", 138461, 2024).get("max_distance", {}).get("Priority area B (15%)"), 3.444)
    c.eq("richmond Turing House School 2024 allocation", year("318", "secondary", 141963, 2024).get("allocation"),
         "nodal_point")
    c.close("richmond Barnes Primary School 2023 max_distance (0.293 km)",
           year("318", "primary", 102902, 2023).get("max_distance"), 0.182)

    return c


def main() -> None:
    exit_code = 0
    all_data: dict[str, dict] = {}
    for module in MODULES:
        name = module.LA_NAME
        print(f"\n=== {name} ===")
        try:
            data = build_borough(module)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        write(data["la_code"], data)
        all_data[data["la_code"]] = data

    print("\n=== verification ===")
    checker = verify(all_data)
    if checker.failures:
        print(f"VERIFICATION FAILED ({len(checker.failures)} of {len(checker.failures) + checker.passed}):",
              file=sys.stderr)
        for failure in checker.failures:
            print("  " + failure, file=sys.stderr)
        exit_code = 1
    else:
        print(f"verification: {checker.passed} checks passed")
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
