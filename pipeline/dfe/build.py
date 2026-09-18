"""Build school register + DfE performance/pupil/finance/workforce data for every English local authority.

Usage (from the project root):
    uv run --with pyproj --with pandas python pipeline/dfe/build.py [--refresh] [--la 204]

Outputs (out/site/data/):
    la/<la_code>/schools.json          register of open establishments (GIAS)
    la/<la_code>/schools/<urn>.json    per-school DfE sections
    la/<la_code>/league_tables.json    compact sortable headline measures
    england/las.json                   national LA index
    england/benchmarks.json            per-LA and England comparators
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch  # noqa: E402
from finance import build_finance  # noqa: E402
from performance import (  # noqa: E402
    build_absence, build_census, build_destinations, build_ks2, build_ks4, build_ks5,
)
from register import load_register_england, school_record  # noqa: E402
from workforce import build_workforce  # noqa: E402

ROOT = fetch.ROOT
GIAS_FILE = ROOT / "pipeline" / ".cache" / "shared" / "gias_edubasealldata_20260916.csv"
GIAS_DATE = "2026-09-16"
OUT = ROOT / "out" / "site" / "data"
CSCP_AREA = "england"  # file prefix inside the all-England CSCP zips

# Performance-table years, newest first (CSCP download-data 'downloadYear').
YEARS = ["2024-2025", "2023-2024", "2022-2023"]

WORKFORCE_PUB = "b318967f-2931-472a-93f2-fbed1e181e6a"  # School workforce in England
ABSENCE_PUB = "cbbd299f-8297-44bc-92ac-558bcf51f8ad"  # Pupil absence in schools in England
EES_FILES = {
    "size_sch": (WORKFORCE_PUB, "Workforce_2010_2025_fte_hc_sch.csv", None),
    "ptr_sch": (WORKFORCE_PUB, "workforce_ptrs_2010_2025_sch.csv", None),
    "pay_sch": (WORKFORCE_PUB, "teacher_pay_school_swc_tps_merged.csv", None),
    "turnover_sch": (WORKFORCE_PUB, "teacher_turnover_2010_2025_sch.csv", None),
    "sickness_sch": (WORKFORCE_PUB, "sickness_absence_teachers_2010_2025_sch.csv", None),
    "ptr_nat": (WORKFORCE_PUB, "workforce_ptrs_2010_2025_nat_reg_la.csv", None),
    "size_nat": (WORKFORCE_PUB, "workforce_2010_2025_fte_hc_nat_reg_la.csv", None),
    "pay_nat": (WORKFORCE_PUB, "workforce_teacher_pay_2010_2025_nat_reg_la.csv", None),
    "sickness_nat": (WORKFORCE_PUB, "sickness_absence_teachers_2010_2025_nat_reg_la.csv", None),
    "absence_nat": (ABSENCE_PUB, "1_Absence_3term_nat_reg_la.csv", "Academic year 2024/25"),
}
CFR_FILE = "CFR_2024-25_Full_Data_Workbook.xlsx"
AAR_FILE = "AAR_2024-25_download.xlsx"

OGL = "Open Government Licence v3.0"
SRC_GIAS = {"title": "Get Information about Schools - establishment data (DfE)", "url": "https://get-information-schools.service.gov.uk/Downloads", "licence": OGL}
SRC_CSCP = {"title": "Compare school and college performance in England - download data (DfE)", "url": "https://www.compare-school-performance.service.gov.uk/download-data", "licence": OGL}
SRC_FBIT = {"title": "Financial Benchmarking and Insights Tool - CFR 2024-25 and AAR 2024/25 data (DfE)", "url": "https://financial-benchmarking-and-insights-tool.education.gov.uk/data-sources", "licence": OGL}
SRC_SWF = {"title": "School workforce in England, reporting year 2025 (DfE, Explore Education Statistics)", "url": "https://explore-education-statistics.service.gov.uk/find-statistics/school-workforce-in-england", "licence": OGL}
SRC_ABS = {"title": "Pupil absence in schools in England, 2024/25 (DfE, Explore Education Statistics)", "url": "https://explore-education-statistics.service.gov.uk/find-statistics/pupil-absence-in-schools-in-england", "licence": OGL}

# GIAS establishment type groups that are not state-funded schools.
NON_STATE_TYPE_GROUPS = {"Independent schools", "Colleges", "Universities", "Online provider", "Welsh schools"}


def slug(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


def write_json(path: Path, data) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(payload, encoding="utf-8")
    return len(payload.encode("utf-8"))


def drop_empty(value):
    """Remove empty trend lists / dicts so files stay small (nulls are kept)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            v = drop_empty(v)
            if isinstance(v, (list, dict)) and not v and k not in ("_suppressed",):
                continue
            out[k] = v
        return out
    if isinstance(value, list):
        # inside lists (trend points) nulls carry no information: drop them
        return [
            {k: v for k, v in drop_empty(item).items() if v is not None} if isinstance(item, dict) else drop_empty(item)
            for item in value
        ]
    return value


def la_benchmark(bench: dict, la_code: str) -> dict:
    """The per-LA slice of a national benchmark dict ({} if the LA has none)."""
    return (bench.get("la") or {}).get(la_code) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="re-download everything instead of using the cache")
    parser.add_argument("--la", action="append", default=None,
                        help="build only this LA code (repeatable); default builds all of England")
    args = parser.parse_args()
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # ------------------------------------------------------------------ fetch
    fetch.log("Fetching sources (cached in pipeline/.cache/dfe)")
    dirs = {y: fetch.cscp_england_zip(y, args.refresh) for y in YEARS}
    fetch.cscp_meta_zip(YEARS[0], args.refresh)
    cfr_path = fetch.fbit_file(CFR_FILE, args.refresh)
    aar_path = fetch.fbit_file(AAR_FILE, args.refresh)
    ees = {key: fetch.ees_filtered(pub, name, rel, args.refresh, la_code=None) for key, (pub, name, rel) in EES_FILES.items()}

    # --------------------------------------------------------------- register
    rows_by_la, la_info, skipped_las = load_register_england(GIAS_FILE)
    la_codes = sorted(rows_by_la, key=int)
    if args.la:
        wanted = {c.strip() for c in args.la}
        unknown = sorted(wanted - set(la_codes))
        if unknown:
            parser.error(f"LA code(s) not in the register: {', '.join(unknown)}")
        la_codes = [c for c in la_codes if c in wanted]
    fetch.log(f"{len(la_codes)} local authorities to build")

    all_records = {code: [school_record(r, code) for r in rows_by_la[code]] for code in la_codes}
    for schools in all_records.values():
        schools.sort(key=lambda s: s["name"])
    urns = {str(s["urn"]) for schools in all_records.values() for s in schools}
    gias_fsm = {
        str(s["urn"]): (s.get("fsm_pct"), s.get("census_date"))
        for schools in all_records.values() for s in schools
    }

    # --------------------------------------------------------------- datasets
    fetch.log("Building sections")
    ks2, ks2_b = build_ks2(YEARS, dirs, CSCP_AREA)
    ks4, ks4_b = build_ks4(YEARS, dirs, CSCP_AREA)
    ks5, ks5_b = build_ks5(YEARS, dirs, CSCP_AREA)
    census, census_b = build_census(YEARS, dirs, gias_fsm, CSCP_AREA)
    with open(ees["absence_nat"][0], encoding="utf-8", newline="") as fh:
        absence_rows = list(csv.DictReader(fh))
    absence, absence_b = build_absence(YEARS, dirs, absence_rows, CSCP_AREA)
    destinations, dest_b = build_destinations(YEARS, dirs, CSCP_AREA)
    finance, finance_b, finance_stats = build_finance(cfr_path, aar_path, urns)
    workforce, workforce_b = build_workforce(ees)

    sections = {
        "ks2": ks2, "ks4": ks4, "ks5": ks5, "census": census, "absence": absence,
        "finance": finance, "workforce": workforce, "destinations": destinations,
    }
    section_sources = {
        "ks2": SRC_CSCP, "ks4": SRC_CSCP, "ks5": SRC_CSCP, "census": SRC_CSCP, "absence": SRC_CSCP,
        "destinations": SRC_CSCP, "finance": SRC_FBIT, "workforce": SRC_SWF,
    }

    # --------------------------------------------------------- per-LA outputs
    grand_counts = {k: 0 for k in sections}
    la_summaries = []
    league_sizes = {}
    for code in la_codes:
        name = la_info[code]["name"]
        schools = all_records[code]
        out_dir = OUT / "la" / code
        counts = {k: 0 for k in sections}
        sizes = {}
        for school in schools:
            urn = str(school["urn"])
            doc = {"generated": generated, "sources": [SRC_GIAS], "urn": school["urn"], "name": school["name"], "phase": school.get("phase")}
            available = []
            for key, table in sections.items():
                if urn in table:
                    doc[key] = drop_empty(table[urn])
                    available.append(key)
                    counts[key] += 1
                    grand_counts[key] += 1
                    if section_sources[key] not in doc["sources"]:
                        doc["sources"].append(section_sources[key])
            school["data"] = available
            school["detail"] = f"schools/{urn}.json"
            sizes[urn] = write_json(out_dir / "schools" / f"{urn}.json", doc)

        schools_doc = {
            "generated": generated,
            "sources": [SRC_GIAS],
            "la": {"code": int(code), "name": name},
            "count": len(schools),
            "notes": [
                f"Open establishments in LA {code} from the GIAS establishment extract dated {GIAS_DATE}.",
                "lat/lon are WGS84 converted from GIAS British National Grid easting/northing (EPSG:27700).",
                "pupils, boys, girls and fsm_pct are GIAS figures from the census_date shown.",
                "Ofsted ratings are not part of the GIAS extract and are not included here.",
            ],
            "schools": schools,
        }
        write_json(out_dir / "schools.json", schools_doc)

        # ------------------------------------------------------ league tables
        rows = []
        for school in schools:
            urn = str(school["urn"])
            row = {"urn": school["urn"], "name": school["name"], "phase": school.get("phase"), "type": school.get("type")}
            k2, k4, k5 = ks2.get(urn), ks4.get(urn), ks5.get(urn)
            if k2 and (k2.get("rwm_expected_pct") is not None or k2.get("rwm_higher_pct") is not None):
                row["ks2_year"] = k2["year"]
                row["ks2_rwm_exp"] = k2.get("rwm_expected_pct")
                row["ks2_rwm_high"] = k2.get("rwm_higher_pct")
                row["ks2_cohort"] = k2.get("cohort")
            if k4 and (k4.get("attainment8") is not None or (k4.get("latest_progress8") or {}).get("score") is not None
                       or k4.get("eng_maths_5plus_pct") is not None):
                p8 = k4.get("latest_progress8") or {}
                row["ks4_year"] = k4["year"]
                row["ks4_p8"] = k4.get("progress8") if k4.get("progress8") is not None else p8.get("score")
                row["ks4_p8_year"] = k4["year"] if k4.get("progress8") is not None else p8.get("year")
                row["ks4_a8"] = k4.get("attainment8")
                row["ks4_em5"] = k4.get("eng_maths_5plus_pct")
                row["ks4_cohort"] = k4.get("cohort")
            if k5 and k5.get("alevel_aps") is not None:
                row["ks5_year"] = k5["year"]
                row["ks5_alevel_aps"] = k5.get("alevel_aps")
                row["ks5_alevel_grade"] = k5.get("alevel_grade")
                row["ks5_alevel_cohort"] = k5.get("alevel_cohort")
            if len(row) > 4:
                rows.append({k: v for k, v in row.items() if v is not None})

        def bench_row(area: str) -> dict:
            la_ks4 = ks4_b.get(area, {}) if area == "england" else la_benchmark(ks4_b, area)
            la_ks2 = ks2_b.get(area, {}) if area == "england" else la_benchmark(ks2_b, area)
            la_ks5 = ks5_b.get(area, {}) if area == "england" else la_benchmark(ks5_b, area)
            p8 = la_ks4.get("latest_progress8") or {}
            out = {
                "ks2_rwm_exp": la_ks2.get("rwm_expected_pct"),
                "ks2_rwm_high": la_ks2.get("rwm_higher_pct"),
                "ks4_p8": la_ks4.get("progress8") if la_ks4.get("progress8") is not None else p8.get("score"),
                "ks4_a8": la_ks4.get("attainment8"),
                "ks4_em5": la_ks4.get("eng_maths_5plus_pct"),
                "ks5_alevel_aps": la_ks5.get("alevel_aps"),
                "ks5_alevel_grade": la_ks5.get("alevel_grade"),
            }
            return {k: v for k, v in out.items() if v is not None}

        league = {
            "generated": generated,
            "sources": [SRC_CSCP],
            "years": {
                "ks2": ks2_b["year"], "ks4": ks4_b["year"], "ks5": ks5_b["year"],
                "ks4_p8": (la_benchmark(ks4_b, code).get("latest_progress8") or {}).get("year", ks4_b["year"]),
            },
            "columns": {
                "ks2_rwm_exp": "KS2 % meeting expected standard in reading, writing & maths",
                "ks2_rwm_high": "KS2 % achieving higher standard in reading, writing & maths",
                "ks2_cohort": "KS2 pupils",
                "ks4_p8": "Progress 8 (latest published year, see ks4_p8_year)",
                "ks4_a8": "Attainment 8",
                "ks4_em5": "% grade 5+ in English & maths",
                "ks4_cohort": "KS4 pupils",
                "ks5_alevel_aps": "A level average point score per entry",
                "ks5_alevel_grade": "A level average grade per entry",
                "ks5_alevel_cohort": "A level students",
            },
            "notes": [
                "Progress 8 is not published for 2024/25, so ks4_p8 holds the 2023/24 score.",
                "Small cohorts make results volatile; check the cohort columns before comparing.",
            ],
            "benchmarks": {slug(name): bench_row(code), "england": bench_row("england")},
            "rows": rows,
        }
        league_sizes[code] = write_json(out_dir / "league_tables.json", league)
        la_summaries.append((code, name, len(schools), len(sizes), counts))

    # ------------------------------------------------------------- england/*
    las_entries = []
    for code in la_codes:
        info = la_info[code]
        schools = all_records[code]
        register_rows = rows_by_la[code]
        lad_codes = sorted({(r.get("DistrictAdministrative (code)") or "").strip() for r in register_rows} - {""})
        coords = [(s["lat"], s["lon"]) for s in schools if s.get("lat") is not None and s.get("lon") is not None]
        bbox = centroid = None
        if coords:
            lats = [c[0] for c in coords]
            lons = [c[1] for c in coords]
            bbox = [round(min(lons) - 0.01, 5), round(min(lats) - 0.01, 5),
                    round(max(lons) + 0.01, 5), round(max(lats) + 0.01, 5)]
            centroid = [round(sum(lats) / len(lats), 5), round(sum(lons) / len(lons), 5)]
        state_count = sum(
            1 for r in register_rows
            if (r.get("EstablishmentTypeGroup (name)") or "").strip() not in NON_STATE_TYPE_GROUPS
        )
        las_entries.append({
            "la_code": code,
            "name": info["name"],
            "region": info["region"],
            "lad_codes": lad_codes,
            "school_count": len(schools),
            "state_school_count": state_count,
            "bbox": bbox,
            "centroid": centroid,
        })
    las_doc = {
        "generated": generated,
        "sources": [SRC_GIAS],
        "notes": [
            f"English local authorities with open establishments in the GIAS extract dated {GIAS_DATE}.",
            "state_school_count excludes independent schools, colleges, universities and online providers.",
            "bbox is [west, south, east, north] padded by 0.01 degrees; centroid is the mean of school coordinates.",
        ],
        "las": las_entries,
    }
    las_size = write_json(OUT / "england" / "las.json", las_doc)

    benchmarks = drop_empty({
        "generated": generated,
        "sources": [SRC_CSCP, SRC_FBIT, SRC_SWF, SRC_ABS],
        "notes": [
            "la = per-local-authority averages keyed by DfE LA code; england = state-funded schools in England unless stated.",
            "Finance averages are computed by this pipeline from school-level returns (see finance.method).",
            "Teacher turnover averages are computed by this pipeline from school-level FTE counts.",
        ],
        "ks2": ks2_b, "ks4": ks4_b, "ks5": ks5_b, "census": census_b, "absence": absence_b,
        "destinations": dest_b, "finance": finance_b, "workforce": workforce_b,
    })
    bench_size = write_json(OUT / "england" / "benchmarks.json", benchmarks)

    # ---------------------------------------------------------------- summary
    total_schools = sum(len(s) for s in all_records.values())
    print("\nOutputs")
    print(f"  la/                    {len(la_codes)} local authorities, {total_schools} establishments")
    print(f"  england/las.json       {las_size/1024:7.1f} KB")
    print(f"  england/benchmarks.json {bench_size/1024:7.1f} KB")
    print("\nSchools with each section (of %d)" % total_schools)
    for key, n in grand_counts.items():
        print(f"  {key:13s} {n}")
    print("\nSkipped non-English LA codes:")
    for s in skipped_las:
        print(f"  {s['code']:>4} {s['name']} ({s['reason']})")
    print("\nFive largest league_tables.json:")
    for code, size in sorted(league_sizes.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {code:>4} {la_info[code]['name']:<30} {size/1024:6.1f} KB")
    print("\nFinance rows read:", finance_stats)
    not_in_register = {k: sorted(set(v) - urns) for k, v in sections.items() if set(v) - urns}
    if not_in_register:
        print("Rows for URNs outside the open register (ignored):", {k: len(v) for k, v in not_in_register.items()})


if __name__ == "__main__":
    main()
