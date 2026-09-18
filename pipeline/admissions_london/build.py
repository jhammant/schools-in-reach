"""Build site/data/la/<la_code>/admissions.json for eight London boroughs
(Islington, Haringey, Tower Hamlets, Waltham Forest, Newham, Camden, City of
London, Enfield) from each council's published Year 7 / Reception admissions
data, modelled on the working Hackney pipeline (pipeline/admissions/build.py).

Run from the project root:
    uv run --with pdfplumber --with openpyxl --with pandas --with beautifulsoup4 \
        python pipeline/admissions_london/build.py

Downloads are cached in pipeline/.cache/admissions_london/<la_code>/. A few
sources sit behind a council WAF that blocks plain HTTP fetches even with
browser headers (noted per-source below); those were fetched once through an
interactive browser tool and the cache is the durable record -- re-running
this script with an empty cache will fail loudly on those specific files
rather than silently produce incomplete data.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import camden
import common
import enfield
import gias
import haringey
import islington
import newham
import tower_hamlets
import waltham_forest as wf

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "site" / "data" / "la"
OGL = "Open Government Licence v3.0"


def dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def make_matcher(module) -> gias.Gias:
    return gias.Gias(common.gias_csv(), module.LA_CODE, module.MANUAL_ALIASES)


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


# --------------------------------------------------------------------------- Islington

def build_islington() -> dict:
    la = islington
    path = common.fetch(la.LA_CODE, la.PAGE)
    secondary, primary = la.parse(path)
    sources = [{"title": la.PAGE["title"], "url": la.PAGE["url"], "licence": la.PAGE["licence"]}]
    return build_json(la.LA_CODE, la.LA_NAME, sources, la.DISTANCE_METHOD, la.DISTANCE_NOTES,
                      secondary, primary, make_matcher(la),
                      "No PAN, applications or admission-criteria breakdown is published, only the cut-off "
                      "distance, and only for the three most recent years (2024-25 to 2026-27).")


# --------------------------------------------------------------------------- Haringey

def build_haringey() -> dict:
    la = haringey
    sec_path = common.fetch(la.LA_CODE, la.SECONDARY_PAGE)
    pri_path = common.fetch(la.LA_CODE, la.PRIMARY_PAGE)
    secondary, primary = la.parse(sec_path, pri_path)
    sources = [{"title": s["title"], "url": s["url"], "licence": s["licence"]}
              for s in (la.SECONDARY_PAGE, la.PRIMARY_PAGE)]
    return build_json(la.LA_CODE, la.LA_NAME, sources, la.DISTANCE_METHOD, la.DISTANCE_NOTES,
                      secondary, primary, make_matcher(la),
                      "No PAN, applications or admission-criteria breakdown is published, only the cut-off "
                      "distance.")


# --------------------------------------------------------------------------- Tower Hamlets

def build_tower_hamlets() -> dict:
    la = tower_hamlets
    sec_paths = {y: common.fetch(la.LA_CODE, {**d, "cache": d["cache"]}) for y, d in la.SECONDARY_DOCS.items()}
    pri_paths = {y: common.fetch(la.LA_CODE, {**d, "cache": d["cache"]}) for y, d in la.PRIMARY_DOCS.items()}
    skipped: list[str] = []
    secondary = la.parse_secondary(sec_paths, skipped)
    primary = la.parse_primary(pri_paths)
    for s in skipped:
        print(f"  tower_hamlets secondary skipped: {s}")
    sources = [{"title": d["title"], "url": d["url"], "licence": OGL}
              for d in list(la.SECONDARY_DOCS.values()) + list(la.PRIMARY_DOCS.values())]
    return build_json(la.LA_CODE, la.LA_NAME, sources, la.DISTANCE_METHOD, la.DISTANCE_NOTES,
                      secondary, primary, make_matcher(la),
                      f"Secondary: {len(skipped)} school/year profile pages could not be parsed (footnote text "
                      "interleaved with the data row in the source PDF) and are omitted rather than guessed; "
                      "see build log. Primary: only oversubscribed community schools are published; voluntary-"
                      "aided and academy primary schools are not covered by this table at all, and undersubscribed "
                      "community schools are not listed individually (see notes).")


# --------------------------------------------------------------------------- Waltham Forest

def build_waltham_forest() -> dict:
    la = wf
    sec_paths = {y: common.fetch(la.LA_CODE, d) for y, d in la.SECONDARY_DOCS.items()}
    pri_paths = {y: common.fetch(la.LA_CODE, d) for y, d in la.PRIMARY_DOCS.items()}
    secondary = la.parse("secondary", sec_paths)
    primary = la.parse("primary", pri_paths)
    sources = [{"title": f"Waltham Forest Council: How School Places Were Offered, secondary {y}", "url": d["url"],
               "licence": OGL} for y, d in la.SECONDARY_DOCS.items()] + \
             [{"title": f"Waltham Forest Council: How School Places Were Offered, reception {y}", "url": d["url"],
               "licence": OGL} for y, d in la.PRIMARY_DOCS.items()]
    return build_json(la.LA_CODE, la.LA_NAME, sources, la.DISTANCE_METHOD, la.DISTANCE_NOTES,
                      secondary, primary, make_matcher(la),
                      "Secondary is published for 2026 only; reception is published for 2022, 2025 and 2026 "
                      "(other years' editions could not be located online).")


# --------------------------------------------------------------------------- Newham

def build_newham() -> dict:
    la = newham
    sec_paths = {y: common.fetch(la.LA_CODE, {"cache": d["cache"], "url": d["url"]})
                for y, d in la.SECONDARY_DOCS.items()}
    pri_paths = {y: common.fetch(la.LA_CODE, {"cache": d["cache"], "url": d["url"]})
                for y, d in la.PRIMARY_DOCS.items()}
    skipped: list[str] = []
    secondary = la.parse("secondary", sec_paths, skipped)
    primary = la.parse("primary", pri_paths, skipped)
    print(f"  newham: {len(skipped)} duplicate/malformed outcome rows skipped (see build log for detail)")
    sources = [{"title": f"Newham Council: Primary to Secondary Transition {y}, Application & Offer Statistics",
               "url": d["url"], "licence": OGL} for y, d in la.SECONDARY_DOCS.items()] + \
             [{"title": f"Newham Council: Reception {y}, Application & Offer Statistics", "url": d["url"],
               "licence": OGL} for y, d in la.PRIMARY_DOCS.items()]
    return build_json(la.LA_CODE, la.LA_NAME, sources, la.DISTANCE_METHOD, la.DISTANCE_NOTES,
                      secondary, primary, make_matcher(la),
                      "PAN, applications and detailed admission-criteria counts are published but not parsed "
                      "here (the column layout is not consistent across years); only the distance and criterion "
                      "of the final offer, and the tie-break method, are recorded. Secondary 2026 does not yet "
                      "publish the outcomes-with-distance table (marked \"coming soon\" by the council at the "
                      "time of writing), so only 2023-2025 are covered for secondary.")


# --------------------------------------------------------------------------- Camden

def build_camden() -> dict:
    la = camden
    sec_paths = [common.fetch(la.LA_CODE, d) for d in la.SECONDARY_GUIDES]
    pri_paths = [common.fetch(la.LA_CODE, d) for d in la.PRIMARY_GUIDES]
    secondary = la.parse(sec_paths, "secondary")
    primary = la.parse(pri_paths, "primary")
    sources = [{"title": d["title"], "url": d["url"], "licence": d["licence"]}
              for d in la.SECONDARY_GUIDES + la.PRIMARY_GUIDES]
    return build_json(la.LA_CODE, la.LA_NAME, sources, la.DISTANCE_METHOD, la.DISTANCE_NOTES,
                      secondary, primary, make_matcher(la),
                      "Only community/comprehensive secondary schools and community primary schools publish "
                      "cut-off distances and criteria counts in these guides; voluntary-aided/faith schools are "
                      "marked \"n/a\" (vacant places) or direct enquiries to the school. Primary covers 2021, "
                      "2022, 2024 and 2025 (2023 not covered by either retrieved guide edition).")


# --------------------------------------------------------------------------- City of London

def build_city_of_london() -> dict:
    return {
        "generated": dt.date.today().isoformat(), "la_code": "201", "la_name": "City of London",
        "sources": [{
            "title": "City of London Corporation: The Aldgate School admissions policy",
            "url": "https://www.cityoflondon.gov.uk/assets/Services-DCCS/admissions-policy-aldgate-2023-24.pdf",
            "licence": OGL,
        }, {
            "title": "DfE Get Information about Schools (GIAS) establishment data, used to identify the City "
                     "of London's maintained schools",
            "url": "https://get-information-schools.service.gov.uk/Downloads", "licence": OGL,
        }],
        "distance_method": "straight_line",
        "distance_notes": "The Aldgate School (the City's only maintained/state-funded school) \"will use the "
                          "City of London's Geographical Information System (GIS) to measure straight line "
                          "distance\" from the Local Land and Property Gazetteer address point of the home to "
                          "that of the school. No published cut-off distance or admissions-outcome statistics "
                          "for The Aldgate School could be found (its own admissions page and the council's FIS "
                          "site publish policy and priority-area maps only, not results).",
        "secondary": {}, "primary": {}, "unmatched": [],
        "coverage": {"secondary_years": [], "primary_years": [],
                    "missing": "The City of London has no maintained secondary schools (GIAS: 0 open state-"
                               "funded secondary schools under LA code 201); its residents apply to secondary "
                               "schools in neighbouring boroughs (Hackney, Islington, Tower Hamlets, Southwark "
                               "etc.) through the pan-London coordinated admissions scheme, and any 'last "
                               "distance offered' figures for those schools belong to and are published by the "
                               "borough that runs them, not the City of London. Its only maintained school is "
                               "The Aldgate School (Reception-Year 6, URN 100000, Voluntary Aided). Searched: "
                               "cityoflondon.gov.uk and fis.cityoflondon.gov.uk admissions pages, the school's "
                               "own admissions page, and web searches for \"Aldgate School\" + \"distance "
                               "offered\" / \"cut-off\" / \"last child\"; none publish a distance-offered figure "
                               "for any year. No admissions.json data could therefore be produced for this "
                               "borough beyond this structure."},
    }


# --------------------------------------------------------------------------- Enfield

def build_enfield() -> dict:
    la = enfield
    paths = [common.fetch(la.LA_CODE, d) for d in la.GUIDES]
    skipped: list[str] = []
    secondary = la.parse(paths)
    sources = [{"title": d["title"], "url": d["url"], "licence": d["licence"]} for d in la.GUIDES]
    return build_json(la.LA_CODE, la.LA_NAME, sources, la.DISTANCE_METHOD, la.DISTANCE_NOTES,
                      secondary, [], make_matcher(la),
                      "Secondary covers 2020-2025 (2020 from the 2022 guide edition, 2021-2023 from a "
                      "standalone breakdown document, 2024-2025 from the 2026 guide edition). No primary/"
                      "Reception data: Enfield's own \"Reception allocation breakdown\" PDFs are on "
                      "enfield.gov.uk, which returned HTTP 403 to every fetch attempt (browser-header curl and "
                      "an interactive browser fetch tool both blocked), and no third-party mirror of that "
                      "specific document could be found (unlike several of Enfield's secondary documents, which "
                      "are mirrored by individual schools).")


BUILDERS = [build_islington, build_haringey, build_tower_hamlets, build_waltham_forest, build_newham,
           build_camden, build_city_of_london, build_enfield]


# --------------------------------------------------------------------------- verification
#
# Hand-checked values below were read directly from the cached source documents (HTML tables or
# pdftotext -layout output), independently of this script's own parsers, per borough:
#   islington: pipeline/.cache/admissions_london/206/cutoff-distances.html
#   haringey:  pipeline/.cache/admissions_london/309/{secondary,primary}-cutoff.html
#   tower_hamlets: .../211/{primary,secondary}-prospectus-2026.txt (pdftotext -layout of the PDF)
#   waltham_forest: .../320/{secondary,reception}-offered-2026.txt
#   newham:    .../316/reception-2026.txt
#   camden:    .../202/{secondary,primary}-guide-2026.txt
#   enfield:   .../308/{secondary-guide-2026,secondary-breakdown-mirror}.txt

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

    # islington (206): from the "Cut off distances for schools in Islington" HTML table
    c.eq("islington Central Foundation Boys' School Band 4 2026/2025/2024 max_distance",
        [year("206", "secondary", 100458, y).get("max_distance", {}).get("Band 4") for y in (2026, 2025, 2024)],
        [1.312, 2.19, 3.911])
    c.eq("islington Ambler Primary School 2026/2025/2024 max_distance",
        [year("206", "primary", 100397, y).get("max_distance") for y in (2026, 2025, 2024)],
        [0.338, 0.271, 0.29])

    # haringey (309): from the two "distance from school of last child offered" HTML tables
    c.eq("haringey Alexandra Park School 2026/2022 max_distance",
        [year("309", "secondary", 137531, y).get("max_distance", {}).get("All") for y in (2026, 2022)],
        [0.477, 0.458])
    c.eq("haringey Belmont Infant School 2026/2025/2022 max_distance",
        [year("309", "primary", 102079, y).get("max_distance") for y in (2026, 2025, 2022)],
        [0.216, 0.1808, 0.3202])

    # tower_hamlets (211): from the primary "Summary of last year's application and offers" table and the
    # secondary per-school "Previous year's applications" box (both read from pdftotext -layout output)
    e = year("211", "primary", 100939, 2025)  # Bigland Green
    c.eq("tower_hamlets Bigland Green 2025 applications/pan", (e.get("applications"), e.get("pan")), (178, 60))
    c.close("tower_hamlets Bigland Green 2025 max_distance (471m)", e.get("max_distance"), 471 / 1609.344)
    e = year("211", "secondary", 150606, 2025)  # Bishop Challoner Catholic School
    c.eq("tower_hamlets Bishop Challoner 2025 pan/applications", (e.get("pan"), e.get("applications")), (210, 216))
    e = year("211", "secondary", 150606, 2024)  # Bishop Challoner Catholic School, prior year
    c.eq("tower_hamlets Bishop Challoner 2024 places/applications", (e.get("pan"), e.get("applications")),
        (270, 278))
    c.eq("tower_hamlets Bishop Challoner 2024 Band A all_offered", "Band A" in e.get("all_offered", []), True)

    # waltham_forest (320): from "How School Places Were Offered" pdftotext -layout output
    c.eq("waltham_forest Frederick Bremer School 2026 max_distance",
        year("320", "secondary", 103094, 2026).get("max_distance", {}).get("All"), 0.718)
    c.eq("waltham_forest Ainslie Wood Primary School 2026 max_distance",
        year("320", "primary", 130343, 2026).get("max_distance"), 0.464)
    e = year("320", "secondary", 140957, 2026)  # Eden Girls' School, Waltham Forest (two admission sites)
    c.eq("waltham_forest Eden Girls' School 2026 max_distance (School site/Station site)",
        (e.get("max_distance", {}).get("School site"), e.get("max_distance", {}).get("Station site")),
        (1.654, 1.399))

    # newham (316): from the Reception 2026 and Year 7 2025 "Outcomes for On-Time Applicants" tables
    c.eq("newham Woodgrange Infant School 2026 max_distance",
        year("316", "primary", 102722, 2026).get("max_distance"), 0.759)
    c.eq("newham Elmhurst Primary School 2026 max_distance",
        year("316", "primary", 145362, 2026).get("max_distance"), 0.332)
    c.eq("newham Harris Academy Chobham 2025 (secondary) max_distance",
        year("316", "secondary", 139703, 2025).get("max_distance", {}).get("All"), 0.585)

    # camden (202): from the "Allocation of places" cut-off distance table
    c.eq("camden Acland Burghley School 2025/2024 max_distance",
        [year("202", "secondary", 100053, y).get("max_distance", {}).get("All") for y in (2025, 2024)],
        [0.85, 0.93])
    e = year("202", "secondary", 100054, 2025)  # The Camden School for Girls
    c.eq("camden School for Girls Band A/D 2025 max_distance",
        (e.get("max_distance", {}).get("Band A"), e.get("max_distance", {}).get("Band D")), (0.98, 0.42))

    # enfield (308): from the secondary "Breakdown of allocations" table in the 2026 guide edition
    wren_urn = next(int(u) for u, s in all_data["308"]["secondary"].items() if "Wren Academy" in s["name"])
    ignatius_urn = next(int(u) for u, s in all_data["308"]["secondary"].items() if "Ignatius" in s["name"])
    e = year("308", "secondary", wren_urn, 2024)
    c.eq("enfield Wren Academy Enfield 2024 max_distance (Community/CofE/Other Christian)",
        (e.get("max_distance", {}).get("Community"), e.get("max_distance", {}).get("Church of England"),
         e.get("max_distance", {}).get("Other Christian")), (0.649, 1.903, 1.516))
    e = year("308", "secondary", ignatius_urn, 2024)
    c.eq("enfield St Ignatius College 2024 pan/max_distance", (e.get("pan"), e.get("max_distance", {}).get("All")),
        (150, 1.476))

    return c


def main() -> None:
    exit_code = 0
    all_data: dict[str, dict] = {}
    for builder in BUILDERS:
        name = builder.__name__.replace("build_", "")
        print(f"\n=== {name} ===")
        try:
            data = builder()
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
