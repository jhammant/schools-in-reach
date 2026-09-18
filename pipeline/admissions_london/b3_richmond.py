"""Richmond upon Thames (LA 318): parse the allocation tables published by
Achieving for Children (AfC, which runs Richmond's school admissions), in
the same formats as Kingston's (shared parsers in b3_afc.py):

* Secondary "National Offer Day (NOD) distance offers and final distance
  offers at the end of national coordination" -- the current edition
  (September 2023-2025, AfC CDN) and the previous council edition
  (2021-2023, richmond.gov.uk), used for its 2021 and 2022 columns.
* Primary "How places have been allocated at community infant and primary
  schools over the last three years (2022-2024)" -- a Wayback Machine copy;
  the current 2023-2025 edition linked from kr.afcinfo.org.uk returns HTTP
  404 from the CDN (a dead link, not bot protection) and no archived copy
  could be retrieved, so Reception 2025 is not covered.

Several secondary schools are published as sub-quota rows and are modelled as
groups of one school:
* Christ's School: "Christ's Foundation" (Christian foundation places, ranked
  by the school's numbered criteria -- the cut-off cell names the criterion
  reached, e.g. "Crit 18 - 3.858 kms") and "Christ's Open" (open places).
* Turing House School: "20%" measured to the school's 'Sun Stairs' door (OS
  grid TQ 13480 73643) and "80%" measured to a nodal admissions point in
  Somerset Gardens, Teddington (OS grid TQ 15356 71392), both by shortest
  route by road/footpath.
* Waldegrave School: priority area A (85% of catchment places) and priority
  area B (15%).
Distances are published in km.
"""

from __future__ import annotations

import b3_afc as afc
import common

LA_CODE = "318"
LA_NAME = "Richmond upon Thames"
OGL = "Open Government Licence v3.0"
CDN = "https://5f2fe3253cd1dfa0d089-bf8b2cdb6a1dc2999fecbc372702016c.ssl.cf3.rackcdn.com/uploads/ckeditor/attachments"

MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "orimary orleans": ("102895", "source misprints \"Orleans Orimary School\"; GIAS: Orleans Primary School"),
    "park richmond": ("136208", "source's \"Richmond Park Academy\" was renamed Lift Richmond Park (same URN)"),
    # the source's plural "Infants" never token-matches GIAS's singular "Infant":
    "carlisle infants": ("102883", "GIAS: Carlisle Infant School"),
    "hampton infants": ("102888", "GIAS: Hampton Infant School and Nursery"),
    "hampton infants wick": ("102889", "GIAS: Hampton Wick Infant and Nursery School"),
    "heathfield infants": ("102891", "GIAS: Heathfield Infant School"),
    "infants trafalgar": ("102901", "GIAS: Trafalgar Infant School"),
}

SEC_DOCS = [
    {"cache": "secondary-furthest-last3.pdf", "kind": "pdf", "years": [2025, 2024, 2023],
     "anchors": [30, 52, 75, 97, 120, 142],
     "url": f"{CDN}/18403/National_Offer_Day__NOD__distance_offers_and_final_distance_offers_for_last_three_years.pdf",
     "title": "Achieving for Children / London Borough of Richmond upon Thames: National Offer Day distance offers "
              "and final distance offers for the last three years (secondary, 2023-2025)"},
    {"cache": "secondary-furthest-2021-2023.pdf", "kind": "pdf", "years": [2023, 2022, 2021],
     "anchors": [35, 57, 79, 99, 123, 149], "use_years": {2022, 2021},
     "url": "https://www.richmond.gov.uk/media/utmdtytx/lbr_tss_furthest_distance_offers.pdf",
     "title": "London Borough of Richmond upon Thames: Distance offers 2021-23 (secondary; used for 2021 and 2022)"},
]
PRIMARY_DOC = {
    "cache": "primary-furthest-2022-2024.pdf", "kind": "pdf",
    "url": f"https://web.archive.org/web/20250727145957id_/{CDN}/16664/"
           "Richmond_Prim_%2B_Jun_How_Places_were_offered_2022_-2024__-_published_table.pdf",
    "title": "Achieving for Children / London Borough of Richmond upon Thames: How places have been allocated at "
             "community infant and primary schools over the last three years (2022-2024) -- Wayback Machine copy"}
BROCHURE = {"title": "London Borough of Richmond upon Thames: Richmond's infant, junior, primary and secondary "
                     "schools brochure 2027/28 (admission criteria: distance measurement, Turing House nodal point, "
                     "Waldegrave priority areas, Christ's School foundation/open places)",
            "url": f"{CDN}/19817/Richmond_s_infant__junior__primary_and_secondary_schools_brochure_2027__Aug26_.pdf"}

SOURCES = [{"title": d["title"], "url": d["url"], "licence": OGL} for d in [*SEC_DOCS, PRIMARY_DOC, BROCHURE]]

DISTANCE_METHOD = "mixed"
DISTANCE_NOTES = ("Each school sets its own measure. Community schools and most others use a straight line from "
                  "the Ordnance Survey address point of the home to the school gate, measured with the council's "
                  "geographical information system. Some schools instead use \"the shortest route by road and/or "
                  "maintained footpath\": Turing House School (to its 'Sun Stairs' door for 20% of places and to a "
                  "nodal admissions point in Somerset Gardens, Teddington for 80%) and Waldegrave School (to the "
                  "nearest pedestrian gate, within priority areas A and B). Two figures are published per school "
                  "per year: the National Offer Day cut-off (used for max_distance) and the furthest distance "
                  "offered by the end of national coordination on 31 August (in notes).")

MISSING_NOTE = ("Secondary: September 2021-2025 (the 2026 table is due by 1 October 2026); no PAN or applications "
               "counts are published in these tables. Primary: community infant/primary schools only, September "
               "2022-2024; the 2023-2025 edition's CDN link is dead (HTTP 404) and no archived copy could be "
               "retrieved, so Reception 2025 is missing; voluntary-aided and academy primaries are not in the "
               "council table; no applications counts.")

SUBQUOTAS = {
    "Christ's Foundation": ("Christ's School", "Foundation"),
    "Christ's Open": ("Christ's School", "Open"),
    "Turing House 20%": ("Turing House School", "20% (Sun Stairs door)"),
    "Turing House 80%": ("Turing House School", "80% (nodal point)"),
    "Waldegrave Area A 85%": ("Waldegrave School", "Priority area A (85%)"),
    "Waldegrave Area B 15%": ("Waldegrave School", "Priority area B (15%)"),
}
ALLOCATION = {"Christ's School": "mixed", "Turing House School": "nodal_point",
              "Waldegrave School": "catchment_then_distance", "St Richard Reynolds": "faith_then_distance"}
SCHOOL_NOTES = {
    "Christ's School": ["Christ's School (Church of England) offers up to 60 Christian foundation places, ranked by "
                        "worship/deanery criteria then siblings/staff/distance, and 90 open places ranked by "
                        "siblings, staff and distance; each group has its own cut-off."],
    "Turing House School": ["Nodal point: 80% of distance places go to applicants closest to the school's nodal "
                            "admissions point in Somerset Gardens, Teddington (OS grid reference TQ 15356 71392); "
                            "20% go to those closest to the school's 'Sun Stairs' door (TQ 13480 73643). Both are "
                            "measured by shortest route by road and/or maintained footpath."],
    "Waldegrave School": ["Girls' school with a rectangular catchment split into priority area A (85% of catchment "
                          "places) and priority area B (15%); within each area places go by distance (shortest "
                          "route by road/footpath to the nearest pedestrian gate)."],
    "St Richard Reynolds": ["Catholic school ranking applicants in faith-based oversubscription bands; the "
                            "published cut-off names the band reached (e.g. \"Band 8 - 3.758 kms\")."],
}
PRI_CRITERIA = ["Education, Health and Care Plan", "Looked after / previously looked after children",
                "Exceptional family, social or medical need", "Sibling at the school or paired school",
                "Children of staff", "Distance"]


def _cell_note(group: str, label: str, cell: str | None) -> str | None:
    if not cell:
        return None
    prefix = "" if group == "All" else f"{group}: "
    if cell.startswith("All pref"):
        return f"{prefix}{label}: all preferences met."
    if cell.startswith("Random alloc"):
        return f"{prefix}{label}: places were allocated at random within bands 2 and 3 (no distance cut-off)."
    if cell.startswith("Crit "):
        return f"{prefix}{label}: cut-off reached under oversubscription criterion {cell.split()[1]} at " \
               f"{afc.cell_miles(cell)} miles."
    if cell.startswith("Band "):
        return f"{prefix}{label}: cut-off reached within oversubscription band {cell.split()[1]} at " \
               f"{afc.cell_miles(cell)} miles."
    return f"{prefix}{label}: {afc.describe_nc(cell)}." if label != "National Offer Day" else None


def _secondary() -> list[dict]:
    by_key: dict[tuple[str, int], dict] = {}
    order: list[tuple[str, int]] = []
    for doc in SEC_DOCS:
        rows = afc.parse_secondary_table(common.pdftotext(common.fetch(LA_CODE, doc)), doc["anchors"])
        if len(rows) != 14:
            raise SystemExit(f"richmond: expected 14 secondary rows in {doc['cache']}, parsed {len(rows)}")
        for row in rows:
            school, group = SUBQUOTAS.get(row.name, (row.name, "All"))
            for k, year in enumerate(doc["years"]):
                if year not in doc.get("use_years", set(doc["years"])):
                    continue
                key = (school, year)
                if key not in by_key:
                    order.append(key)
                    by_key[key] = {
                        "name": school, "year": year, "pan": None, "applications": None, "groups": [],
                        "criteria": [], "max_distance": {}, "all_offered": [], "non_preference_offers": None,
                        "total_offers": None, "allocation": ALLOCATION.get(school, "distance"),
                        "notes": list(SCHOOL_NOTES.get(school, [])),
                    }
                rec = by_key[key]
                nod, nc = row.cells.get(2 * k), row.cells.get(2 * k + 1)
                rec["groups"].append(group)
                rec["max_distance"][group] = afc.cell_miles(nod)
                if afc.cell_all_offered(nod):
                    rec["all_offered"].append(group)
                for label, cell in (("National Offer Day", nod), ("End of national coordination", nc)):
                    note = _cell_note(group, label, cell)
                    if note:
                        rec["notes"].append(note)
    return [by_key[k] for k in order]


def build() -> tuple[list[dict], list[dict]]:
    secondary = _secondary()
    parsed = afc.parse_primary_table(common.pdftotext(common.fetch(LA_CODE, PRIMARY_DOC)))
    primary = afc.primary_records(parsed, PRI_CRITERIA)
    return secondary, primary
