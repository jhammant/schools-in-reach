"""Build site/data/la/<la_code>/admissions.json for eight more London boroughs
(Barnet, Brent, Westminster, Kensington and Chelsea, Hammersmith and Fulham,
Ealing, Harrow, Hillingdon) from each council's published Year 7 / Reception
allocation data, in the same shape as the Hackney pipeline's output
(pipeline/admissions/build.py) and the batch-1 boroughs (build.py here).

Run from the project root:
    uv run --with pdfplumber --with openpyxl --with pandas --with beautifulsoup4 \
        python pipeline/admissions_london/build_batch2.py

Downloads are cached in pipeline/.cache/admissions_london/<la_code>/. Two
councils put their document stores behind bot protection (barnet.gov.uk,
rbkc.gov.uk); those documents are fetched from the Internet Archive's copy of
the council URL, or from the other council that publishes the same file. The
build fails loudly if any hand-checked value is not reproduced.

Reuses the batch-1 helpers (common.py: fetch, pdftotext cache, GIAS matching and
record assembly; gias.py; pdftools.py) without modifying them.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import b2_barnet
import b2_biborough
import b2_brent
import b2_brochures
import b2_ealing
import b2_harrow
import b2_hillingdon
import common
import gias

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "site" / "data" / "la"
OGL = "Open Government Licence v3.0"
GIAS_SOURCE = {"title": "DfE Get Information about Schools (GIAS) establishment data, used to map school names to "
                        "URNs and to identify selective (grammar) schools",
               "url": "https://get-information-schools.service.gov.uk/Downloads", "licence": OGL}


def fetch_all(la_code: str, docs) -> dict:
    items = docs.items() if isinstance(docs, dict) else ((d["cache"], d) for d in docs)
    return {key: common.fetch(la_code, {"cache": d["cache"], "url": d["url"], "kind": "pdf"}) for key, d in items}


def sources(docs, default_title: str) -> list[dict]:
    items = docs.items() if isinstance(docs, dict) else ((d.get("year"), d) for d in docs)
    return [{"title": d.get("title") or f"{default_title} {key}", "url": d["url"], "licence": OGL} for key, d in items]


def build_json(la_code: str, la_name: str, srcs: list[dict], method: str, notes: str, secondary: list[dict],
               primary: list[dict], aliases: dict, missing: str, log: list[str]) -> dict:
    matcher = gias.Gias(common.gias_csv(), la_code, aliases)
    unmatched: list[dict] = []
    sec = common.assemble(secondary, matcher, "secondary", unmatched, log)
    pri = common.assemble(primary, matcher, "primary", unmatched, log)
    return {
        "generated": dt.date.today().isoformat(), "la_code": la_code, "la_name": la_name,
        "sources": srcs + [GIAS_SOURCE], "distance_method": method, "distance_notes": notes,
        "secondary": sec, "primary": pri,
        "unmatched": sorted(unmatched, key=lambda u: (u["phase"], u["name_in_source"], u["year"])),
        "coverage": {"secondary_years": sorted({y for s in sec.values() for y in s["years"]}),
                     "primary_years": sorted({y for s in pri.values() for y in s["years"]}), "missing": missing},
    }


# --------------------------------------------------------------------------- boroughs

def build_harrow(log: list[str]) -> dict:
    m = b2_harrow
    sec = m.parse("secondary", fetch_all(m.LA_CODE, m.SECONDARY_DOCS))
    pri = m.parse("primary", fetch_all(m.LA_CODE, m.PRIMARY_DOCS))
    return build_json(m.LA_CODE, m.LA_NAME, sources(m.SECONDARY_DOCS, "") + sources(m.PRIMARY_DOCS, ""),
                      m.DISTANCE_METHOD, m.DISTANCE_NOTES, sec, pri, m.MANUAL_ALIASES,
                      "Harrow has no grammar schools. The two Catholic secondaries (Salvatorian College, Sacred Heart "
                      "Language College) and the voluntary-aided faith primaries are their own admission authorities: "
                      "Harrow publishes only their places, applications and total offers, not a distance. Editions "
                      "for 2022 are Internet Archive copies (removed from harrow.gov.uk).", log)


def build_hillingdon(log: list[str]) -> dict:
    m = b2_hillingdon
    sec = m.parse_secondary(fetch_all(m.LA_CODE, m.SECONDARY_DOCS))
    pri, plog = m.parse_primary(fetch_all(m.LA_CODE, m.PRIMARY_DOCS))
    log.extend(plog)
    srcs = [{"title": f"Hillingdon Council: Secondary allocation data {y}", "url": d["url"], "licence": OGL}
            for y, d in m.SECONDARY_DOCS.items()] + \
           [{"title": f"Hillingdon Council: September {y} (Reception) allocation data", "url": d["url"], "licence": OGL}
            for y, d in m.PRIMARY_DOCS.items()]
    return build_json(m.LA_CODE, m.LA_NAME, srcs, m.DISTANCE_METHOD, m.DISTANCE_NOTES, sec, pri, m.MANUAL_ALIASES,
                      "Secondary: no applications or criteria breakdown, only places, SEN placements, places left and "
                      "the furthest distance; faith schools and Swakeleys (banding) have no published distance. The 2024 "
                      "and 2025 secondary tables are image-only PDFs, transcribed by hand and checked against their "
                      "printed totals. Reception 2020 comes only from the previous-year column of the 2021 edition "
                      "(distance only). No 2026 edition of either table was online at the time of the build.", log)


def build_brent(log: list[str]) -> dict:
    m = b2_brent
    sec = m.parse("secondary", fetch_all(m.LA_CODE, m.SECONDARY_DOCS))
    pri = m.parse("primary", fetch_all(m.LA_CODE, m.PRIMARY_DOCS))
    srcs = [{"title": f"Brent Council: How places were allocated at Brent secondary schools, September {y}",
             "url": d["url"], "licence": OGL} for y, d in m.SECONDARY_DOCS.items()] + \
           [{"title": f"Brent Council: How places were offered, Reception {y}", "url": d["url"], "licence": OGL}
            for y, d in m.PRIMARY_DOCS.items()]
    return build_json(m.LA_CODE, m.LA_NAME, srcs, m.DISTANCE_METHOD, m.DISTANCE_NOTES, sec, pri, m.MANUAL_ALIASES,
                      "Only 2024-2026 are published (brent.gov.uk \"How school places were offered\"); earlier years "
                      "are not online. Brent prints a furthest distance per criterion rather than a single cut-off, "
                      "so the cut-off recorded is that of the last criterion reached. Applications are printed only "
                      "from Reception 2026 and secondary 2026; PAN is not printed in the Reception 2024 edition. Brent "
                      "also publishes junior-school (Year 3) tables, not included.", log)


def build_ealing(log: list[str]) -> dict:
    m = b2_ealing
    sec = m.parse("secondary", fetch_all(m.LA_CODE, m.SECONDARY_DOCS))
    pri = m.parse("primary", fetch_all(m.LA_CODE, m.PRIMARY_DOCS))
    srcs = [{"title": f"Ealing Council: High school allocations for September {y}", "url": d["url"], "licence": OGL}
            for y, d in m.SECONDARY_DOCS.items()] + \
           [{"title": f"Ealing Council: Applications and offers for each primary school on National Offer Day {y}",
             "url": d["url"], "licence": OGL} for y, d in m.PRIMARY_DOCS.items()]
    return build_json(m.LA_CODE, m.LA_NAME, srcs, m.DISTANCE_METHOD, m.DISTANCE_NOTES, sec, pri, m.MANUAL_ALIASES,
                      "No 2023 edition (either phase) or 2021 Reception edition could be found on ealing.gov.uk or in "
                      "the Internet Archive (the council reuses download ids, overwriting earlier years). Ealing does "
                      "not print PANs; applications are printed only per criterion (and for oversubscribed community "
                      "primaries).", log)


def build_barnet(log: list[str]) -> dict:
    m = b2_barnet
    sec = m.parse_secondary(fetch_all(m.LA_CODE, m.SECONDARY_DOCS), log)
    pri = m.parse_primary(fetch_all(m.LA_CODE, m.PRIMARY_DOCS), log)
    srcs = [{"title": d["title"] + " (Internet Archive copy; barnet.gov.uk blocks automated requests)",
             "url": d["url"], "licence": OGL} for d in m.SECONDARY_DOCS + m.PRIMARY_DOCS]
    return build_json(m.LA_CODE, m.LA_NAME, srcs, m.DISTANCE_METHOD, m.DISTANCE_NOTES, sec, pri, m.MANUAL_ALIASES,
                      "barnet.gov.uk is behind bot protection, so only editions captured by the Internet Archive are "
                      "used: secondary 2021-2025, primary 2021 and 2023-2025 (no 2022 primary or 2026 editions were "
                      "captured). Barnet does not publish applications for secondary schools. The Henrietta Barnett "
                      "School, Queen Elizabeth's School and St Michael's Catholic Grammar School are selective and "
                      "publish no distance. In 2024 Barnet only says demand was met at \"all other\" primary "
                      "schools without naming them, so those schools have no 2024 entry.", log)


def build_biborough(log: list[str]) -> dict[str, dict]:
    m = b2_biborough
    bi_paths = fetch_all("213", m.BIBOROUGH_DOCS)
    hf_paths = fetch_all("205", m.HF_DOCS)
    by_la = m.parse(m.BIBOROUGH_DOCS, bi_paths)
    hf = m.parse(m.HF_DOCS, hf_paths)
    bi_src = [{"title": f"Westminster City Council / RBKC: How places were offered for each school in the Bi-borough "
                        f"area, {y}", "url": d["url"], "licence": OGL} for y, d in m.BIBOROUGH_DOCS.items()]
    hf_src = [{"title": f"Hammersmith & Fulham Council: How places were offered for LBHF secondary schools, {y}",
               "url": d["url"], "licence": OGL} for y, d in m.HF_DOCS.items()]
    primaries, brochure_src = {}, {}
    for code in ("213", "207", "205"):
        paths = fetch_all(code, b2_brochures.BROCHURES[code])
        recs, skipped = b2_brochures.parse(code, paths)
        log.extend(skipped)
        primaries[code] = [r for r in recs if r["name"] not in b2_brochures.NOT_IN_GIAS]
        primaries[code + "_unmatched"] = [{"name_in_source": r["name"], "year": r["year"], "phase": "primary"}
                                          for r in recs if r["name"] in b2_brochures.NOT_IN_GIAS]
        brochure_src[code] = [{"title": d["title"], "url": d["url"], "licence": OGL}
                              for d in b2_brochures.BROCHURES[code]]
    primary_note = ("Reception: no allocation table is published; outcomes are read from the \"How places were "
                    "offered\" panel on each school's page of the council's primary admissions brochure (applications, "
                    "offers per criterion and the last distance offered, or \"all applicants were offered\"). ")
    extra = [r for la, rs in (by_la | hf).items() if la not in ("213", "207", "205") for r in rs]
    if extra:
        raise SystemExit(f"biborough: records outside the three boroughs: {[r['name'] for r in extra]}")
    out = {}
    for code, name, recs, srcs, missing in (
            ("213", "Westminster", by_la.get("213", []), bi_src,
             "Secondary 2022-2026 from the shared Bi-borough document (published on both councils' sites). "
             + primary_note + "Primary 2022-2025 from the 2023-2026 brochures; the 2026 panels are not yet "
             "published (next brochure)."),
            ("207", "Kensington and Chelsea", by_la.get("207", []), bi_src,
             "Secondary 2022-2026 from the shared Bi-borough document, fetched from westminster.gov.uk. " + primary_note
             + "Primary 2024-2025 only, from Internet Archive copies of the 2025 and 2026 brochures: rbkc.gov.uk blocks "
             "automated requests with a bot-protection challenge, and no earlier brochure was archived."),
            ("205", "Hammersmith and Fulham", hf.get("205", []), hf_src,
             "Secondary 2022-2025 from the standalone \"How places were offered\" PDFs (no 2026 edition is published "
             "separately; its outcomes appear only inside the \"Moving on up 2027\" brochure, not parsed). "
             + primary_note + "Primary 2025-2026 from the 2026 and 2027 brochures (earlier brochures were not "
             "archived).")):
        out[code] = build_json(code, name, srcs + brochure_src[code], "straight_line", m.DISTANCE_NOTES, recs,
                               primaries[code], m.MANUAL_ALIASES[code], missing, log)
        out[code]["unmatched"] = sorted(out[code]["unmatched"] + primaries[code + "_unmatched"],
                                        key=lambda u: (u["phase"], u["name_in_source"], u["year"]))
    return out


# --------------------------------------------------------------------------- verification

class Checker:
    def __init__(self, data: dict[str, dict]):
        self.data = data
        self.failures: list[str] = []
        self.passed: dict[str, int] = {}

    def year(self, la: str, phase: str, name: str, yr: int) -> dict:
        schools = [s for s in self.data[la][phase].values() if s["name"] == name]
        if len(schools) != 1:
            self.failures.append(f"{la} {phase} {name!r}: found {len(schools)} schools")
            return {}
        entry = schools[0]["years"].get(str(yr))
        if entry is None:
            self.failures.append(f"{la} {phase} {name!r} {yr}: missing year")
            return {}
        return entry

    def eq(self, la: str, label: str, actual, expected) -> None:
        if actual == expected:
            self.passed[la] = self.passed.get(la, 0) + 1
        else:
            self.failures.append(f"{la} {label}: expected {expected!r}, got {actual!r}")


def miles(metres: float) -> float:
    return round(metres / 1609.344, 3)


def verify(data: dict[str, dict]) -> Checker:
    """Values read by hand from the cached source documents (pdftotext -layout output, or for Hillingdon's
    image-only 2025 secondary table, the rendered page), independently of the parsers."""
    c = Checker(data)
    md = lambda e, g="All": (e.get("max_distance") or {}).get(g)  # noqa: E731

    # Harrow 310: secondary-2026.txt "Nower Hill 1425 324 ... 191 0.886"; secondary-2025.txt "Whitmore High 1368 270
    # ... 169 0.791"; primary-2026.txt "Krishna Avanti School 60 263 ... 25 0.683 N/A 60"; wb-primary-2022.txt
    # "Cannon Lane Primary School 120 348 ... 73 1.402 N/A 120"
    e = c.year("310", "secondary", "Nower Hill High School", 2026)
    c.eq("310", "Nower Hill 2026 (apps, pan, cut-off)", (e.get("applications"), e.get("pan"), md(e)), (1425, 324, 0.886))
    c.eq("310", "Whitmore High 2025 cut-off", md(c.year("310", "secondary", "Whitmore High School", 2025)), 0.791)
    e = c.year("310", "primary", "Krishna Avanti Primary School", 2026)
    c.eq("310", "Krishna Avanti 2026 (apps, cut-off, allocation)", (e.get("applications"), e.get("max_distance"),
                                                                      e.get("allocation")), (263, 0.683, "faith_then_distance"))
    e = c.year("310", "primary", "Cannon Lane Primary School", 2022)
    c.eq("310", "Cannon Lane 2022 (pan, cut-off, total)", (e.get("pan"), e.get("max_distance"), e.get("total_offers")),
         (120, 1.402, 120))

    # Hillingdon 312: secondary-2023.txt "Uxbridge High 240 6 0 3773.36"; secondary-2025 page image "Oak Wood 240 5 0
    # 6041.74" and "Haydon 300 5 72 N/A (U)*"; reception-2025.txt "Hillingdon Primary School 90 90 0 1369.9793
    # 1130.6215"; reception-2021.txt "Heathrow Primary School 60 60 0 3,023.79 2,068.64" (2021 then 2020 columns)
    c.eq("312", "Uxbridge High 2023 cut-off", md(c.year("312", "secondary", "Uxbridge High School", 2023)), miles(3773.36))
    c.eq("312", "Oak Wood 2025 cut-off", md(c.year("312", "secondary", "Oak Wood School", 2025)), miles(6041.74))
    c.eq("312", "Haydon 2025 all offered", c.year("312", "secondary", "Haydon School", 2025).get("all_offered"), ["All"])
    c.eq("312", "Hillingdon Primary 2025 cut-off",
         c.year("312", "primary", "Hillingdon Primary School", 2025).get("max_distance"), miles(1130.6215))
    c.eq("312", "Heathrow Primary 2021 / 2020 cut-offs",
         (c.year("312", "primary", "Heathrow Primary School", 2021).get("max_distance"),
          c.year("312", "primary", "Heathrow Primary School", 2020).get("max_distance")), (miles(3023.79), miles(2068.64)))

    # Brent 304: secondary-2026.txt "Alperton Community School (324) ... Distance 76 1584.73", "694 applications";
    # reception-2026.txt "Ark Academy (60) 314 60 Oversubscribed ... Distance 24 490.03"; secondary-2024.txt
    # "Claremont High School (270) ... Distance 14 569.23"
    e = c.year("304", "secondary", "Alperton Community School", 2026)
    c.eq("304", "Alperton 2026 (pan, apps, cut-off)", (e.get("pan"), e.get("applications"), md(e)), (324, 694, miles(1584.73)))
    e = c.year("304", "primary", "Ark Academy", 2026)
    c.eq("304", "Ark Academy Reception 2026 (apps, cut-off)", (e.get("applications"), e.get("max_distance")),
         (314, miles(490.03)))
    c.eq("304", "Claremont 2024 cut-off", md(c.year("304", "secondary", "Claremont High School", 2024)), miles(569.23))

    # Barnet 302: wb-secondary-2023-2025.txt (2025 table) "Ashmole Academy 261 ... Geographical Distance 102 0.618",
    # "Queen Elizabeth's Girls' 210 ... Geographical Distance 171 5.386", "Queen Elizabeth's Boys' 192 Academic
    # Ability 192"; wb-primary-2023.txt "Barnfield Primary 60 222 26 0.589 None"; wb-primary-2025.txt
    # "Barnfield Primary 60 162 18 All 0.951"
    e = c.year("302", "secondary", "Ashmole Academy", 2025)
    c.eq("302", "Ashmole 2025 (pan, cut-off)", (e.get("pan"), md(e)), (261, 0.618))
    c.eq("302", "QE Girls 2025 cut-off", md(c.year("302", "secondary", "Queen Elizabeth's Girls' School", 2025)), 5.386)
    e = c.year("302", "secondary", "Queen Elizabeth's School, Barnet", 2025)
    c.eq("302", "QE Boys 2025 selective", (e.get("pan"), e.get("allocation")), (192, "selective"))
    e = c.year("302", "primary", "Barnfield Primary School", 2023)
    c.eq("302", "Barnfield 2023 (apps, in-area cut-off)", (e.get("applications"), e.get("max_distance")), (222, 0.589))
    c.eq("302", "Barnfield 2025 outside-area cut-off",
         c.year("302", "primary", "Barnfield Primary School", 2025).get("max_distance"), 0.951)

    # Ealing 307: high-offers-2026.txt "Drayton Manor ... 4 Distance 153 58 95 1.647 miles", Twyford "21 points
    # living outside a named deanery 30 23 7 3.657 miles"; primary-offers-2026.txt "Fielding Primary School 217 120 97
    # 0.365 of a mile"; wb-primary-2020.txt "Grange Primary School 127 120 7 1.614 miles"
    c.eq("307", "Drayton Manor 2026 cut-off", md(c.year("307", "secondary", "Drayton Manor High School", 2026)), 1.647)
    e = c.year("307", "secondary", "Twyford Church of England High School", 2026)
    c.eq("307", "Twyford 2026 foundation band cut-off",
         md(e, "Foundation Band: 21 points living outside a named deanery"), 3.657)
    e = c.year("307", "primary", "Fielding Primary School", 2026)
    c.eq("307", "Fielding 2026 (apps, cut-off)", (e.get("applications"), e.get("max_distance")), (217, 0.365))
    c.eq("307", "Grange Primary 2020 cut-off", c.year("307", "primary", "Grange Primary School", 2020).get("max_distance"),
         1.614)

    # Westminster 213: sec_2026.txt "Paddington Academy Places available = 180 (Applications received = 721) ...
    # Distance 87 offers up to 0.519 of a mile"; "St George's Catholic School ... up to a distance of 2.298 miles";
    # Grey Coat "Open Places 6 offers (1 LAC, all siblings offered, and offered up to 0.254 of a mile ..."
    e = c.year("213", "secondary", "Paddington Academy", 2026)
    c.eq("213", "Paddington 2026 (pan, apps, cut-off)", (e.get("pan"), e.get("applications"), md(e)), (180, 721, 0.519))
    c.eq("213", "St George's 2026 cut-off", md(c.year("213", "secondary", "St George's Catholic School", 2026)), 2.298)
    c.eq("213", "Grey Coat 2026 open band 1", md(c.year("213", "secondary", "The Grey Coat Hospital", 2026),
                                                "Open Places (Band 1)"), 0.254)

    # Kensington and Chelsea 207: sec_2026.txt "All Saints Catholic College Places available = 180 (Applications
    # received = 781) ... Remaining places offered up to a distance of 1.841 miles"; "Chelsea Academy ... Community
    # places 94 offers up to a distance of 2.083 miles"; Holland Park "Band D 36 offers total ... up to 0.761 of a
    # mile"; sec_2024.txt Kensington Aldridge "Living outside priority area 19 offers up to a distance of 0.926"
    e = c.year("207", "secondary", "All Saints Catholic College", 2026)
    c.eq("207", "All Saints 2026 (apps, cut-off)", (e.get("applications"), md(e)), (781, 1.841))
    c.eq("207", "Chelsea Academy 2026 cut-off", md(c.year("207", "secondary", "Chelsea Academy", 2026)), 2.083)
    c.eq("207", "Holland Park 2026 band D", md(c.year("207", "secondary", "Holland Park School", 2026), "Band D"), 0.761)
    c.eq("207", "KAA 2024 cut-off", md(c.year("207", "secondary", "Kensington Aldridge Academy", 2024)), 0.926)

    # Hammersmith and Fulham 205: secondary-offered-2024.txt "The Hurlingham Academy ... Distance 126 offers, last
    # offer up to 1.952 miles"; Lady Margaret "Open Band 3 ... 9 offers ..., last offer up to 0.103 miles";
    # secondary-offered-2025.txt Hammersmith Academy "Band E 28 offers (including 9 EHCP), last offer up to 0.393"
    c.eq("205", "Hurlingham 2024 cut-off", md(c.year("205", "secondary", "The Hurlingham Academy", 2024)), 1.952)
    c.eq("205", "Lady Margaret 2024 open band 3", md(c.year("205", "secondary", "Lady Margaret School", 2024),
                                                     "Open Band 3"), 0.103)
    c.eq("205", "Hammersmith Academy 2025 band E", md(c.year("205", "secondary", "Hammersmith Academy", 2025), "Band E"),
         0.393)
    # Reception from the brochures. Westminster primary-brochure-2025.pdf page 18 (rendered): "ARK ATWOOD PRIMARY
    # ACADEMY ... Admission number 60 ... HOW PLACES WERE OFFERED IN 2024 Total number of on-time applications
    # submitted: 184 ... Distance from home to school: 23 offered up to 0.463 of a mile"; H&F primary-brochure-2027.txt
    # "Addison Primary School ... 110 How places were offered in 2026 Siblings: 7 Distance: 13 (last distance offered
    # was 1.243 of a mile)"; RBKC wb-primary-brochure-2026.txt "Bousfield ... Total number of on-time applications
    # submitted 231 ... Distance: 37 (up to a distance of 0.340 of a mile straight-line)"; H&F
    # secondary-offered-2023.txt "The Hurlingham Academy Places available = 135 (Applications received = 493) ...
    # last offer up to 5.056 miles"
    e = c.year("213", "primary", "Ark Atwood Primary Academy", 2024)
    c.eq("213", "Ark Atwood Reception 2024 (pan, apps, cut-off)", (e.get("pan"), e.get("applications"),
                                                                  e.get("max_distance")), (60, 184, 0.463))
    e = c.year("205", "primary", "Addison Primary School", 2026)
    c.eq("205", "Addison Reception 2026 (apps, cut-off)", (e.get("applications"), e.get("max_distance")), (110, 1.243))
    e = c.year("205", "secondary", "The Hurlingham Academy", 2023)
    c.eq("205", "Hurlingham 2023 (apps, cut-off)", (e.get("applications"), md(e)), (493, 5.056))
    e = c.year("207", "primary", "Bousfield Primary School", 2025)
    c.eq("207", "Bousfield Reception 2025 (apps, cut-off)", (e.get("applications"), e.get("max_distance")), (231, 0.34))
    return c


BUILDERS = [build_barnet, build_brent, build_ealing, build_harrow, build_hillingdon]


def main() -> None:
    all_data: dict[str, dict] = {}
    log: list[str] = []
    for builder in BUILDERS:
        print(f"=== {builder.__name__.replace('build_', '')} ===")
        data = builder(log)
        all_data[data["la_code"]] = data
    print("=== biborough (Westminster, Kensington and Chelsea, Hammersmith and Fulham) ===")
    all_data.update(build_biborough(log))
    for line in dict.fromkeys(log):
        print("  " + line)

    checker = verify(all_data)
    if checker.failures:
        print(f"\nVERIFICATION FAILED ({len(checker.failures)}):", file=sys.stderr)
        for failure in checker.failures:
            print("  " + failure, file=sys.stderr)
        raise SystemExit(1)
    short = [la for la in all_data if checker.passed.get(la, 0) < 3]
    if short:
        raise SystemExit(f"fewer than 3 hand-checked values for: {short}")
    print("verification: " + ", ".join(f"{la} {n}" for la, n in sorted(checker.passed.items())) + " checks passed")

    print()
    for la, data in sorted(all_data.items(), key=lambda kv: kv[1]["la_name"]):
        out = OUT_DIR / la / "admissions.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        cov = data["coverage"]
        span = lambda ys: f"{ys[0]}-{ys[-1]} ({len(ys)} yrs)" if ys else "none"  # noqa: E731
        print(f"{data['la_name']} ({la}): secondary {len(data['secondary'])} schools {span(cov['secondary_years'])}; "
              f"primary {len(data['primary'])} schools {span(cov['primary_years'])}; "
              f"unmatched {len(data['unmatched'])}; {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
