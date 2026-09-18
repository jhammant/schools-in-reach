"""Kingston upon Thames (LA 314): parse the allocation tables published by
Achieving for Children (AfC, which runs Kingston's school admissions) on
kr.afcinfo.org.uk (files hosted on AfC's Rackspace CDN):

* "How places were allocated at Kingston borough secondary schools for the
  last three years" -- NOD cut-off distance and end-of-national-coordination
  distance for September 2023, 2024 and 2025 entry, plus each school's 2025
  PAN (see b3_afc.parse_secondary_table).
* "How places have been allocated at community infant and primary schools
  over the last three years" -- the current edition (2023-2025) plus the
  previous edition (2022-2024, retrieved from the Wayback Machine because the
  CDN copy has been replaced), used only for its 2022 rows.

The September 2026 editions are "available by 1 October 2026" per AfC, so
2026 is not covered. Secondary distances are in km; primary in km.

Selective schools: The Tiffin School and The Tiffin Girls' School admit by
rank order of their own two-stage entrance test; neither publishes a
distance cut-off ("CONTACT THE SCHOOL FOR ALLOCATION INFORMATION").
"""

from __future__ import annotations

import b3_afc as afc
import common

LA_CODE = "314"
LA_NAME = "Kingston upon Thames"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "coombe hill infants": ("102567", "source prints \"Coombe Hill Infants'\"; GIAS: Coombe Hill Infant School"),
}
OGL = "Open Government Licence v3.0"
CDN = "https://5f2fe3253cd1dfa0d089-bf8b2cdb6a1dc2999fecbc372702016c.ssl.cf3.rackcdn.com/uploads/ckeditor/attachments"

SECONDARY_DOC = {
    "cache": "secondary-furthest-2023-2025.pdf", "kind": "pdf",
    "url": f"{CDN}/18413/RBK_TSS_furthest_distance_offers_Last_3_Years__2023-2025___published_.pdf",
    "title": "Achieving for Children / Royal Borough of Kingston: How places were allocated at Kingston borough "
             "secondary schools for the last three years (2023-2025)"}
PRIMARY_DOCS = [
    {"cache": "primary-furthest-2023-2025.pdf", "kind": "pdf", "years": {2023, 2024, 2025},
     "url": f"{CDN}/18451/Kingston_Prim___Jun_Offers_2025-2023__for_publication_.pdf",
     "title": "Achieving for Children / Royal Borough of Kingston: How places have been allocated at community "
              "infant and primary schools over the last three years (2023-2025)"},
    {"cache": "primary-furthest-2022-2024.pdf", "kind": "pdf", "years": {2022},
     "url": f"https://web.archive.org/web/20241208111523id_/{CDN}/16708/"
            "Kingston_Prim___Jun_Offers_2024-2022_for_publication_.pdf",
     "title": "Achieving for Children / Royal Borough of Kingston: How places have been allocated at community "
              "infant and primary schools over the last three years (2022-2024) -- Wayback Machine copy, used "
              "for 2022 only"},
]
BROCHURE = {"title": "Royal Borough of Kingston: Kingston's infant, junior, primary and secondary schools "
                     "brochure 2027/28 (admission criteria wording for distance measurement and the Tiffin schools)",
            "url": f"{CDN}/19837/Kingston_s_infant__junior__primary_and_secondary_schools_brochure_2027__Sep_26_.pdf"}

SOURCES = [{"title": d["title"], "url": d["url"], "licence": OGL} for d in [SECONDARY_DOC, *PRIMARY_DOCS, BROCHURE]]

DISTANCE_METHOD = "straight_line"
DISTANCE_NOTES = ("Kingston's admission criteria measure distance \"by a straight line in metres to the nearest "
                  "school gate\" (community schools) using the School Admissions computerised geographical "
                  "information system, from the Ordnance Survey address point of the home; the Tiffin School "
                  "likewise measures straight-line distance to the nearest Tiffin pedestrian gate, but only to "
                  "break a tie on test score. Two figures are published per school per year: the cut-off at "
                  "National Offer Day (used for max_distance) and the furthest distance offered by the end of "
                  "national coordination (in notes). \"All preferences met\" means every applicant who named the "
                  "school was offered; \"Overseas\" means the last place went to an applicant living overseas, "
                  "i.e. every UK-resident applicant ranked by distance was offered.")

MISSING_NOTE = ("Secondary: September 2023-2025 only (the 2026 table is due by 1 October 2026; earlier editions "
               "could not be retrieved); PAN is published for 2025 only; no applications counts. Four schools "
               "publish nothing (\"contact the school\"): The Tiffin School and The Tiffin Girls' School "
               "(selective) and The Holy Cross School and Richard Challoner School (Catholic). Primary: community "
               "infant/primary schools only, September 2022-2025 (voluntary-aided and academy primaries are not "
               "in the council table); no applications counts.")

SEC_YEARS = [2025, 2024, 2023]
SELECTIVE = {"Tiffin School": "The Tiffin School admits boys by rank order of the combined score in its own "
                              "two-stage entrance test (after EHCP, then looked-after/pupil-premium boys at or "
                              "above the 450th score); boys living within 10 km (the priority area) are ranked "
                              "before those outside; straight-line distance only breaks a tie for the 180th "
                              "place. No distance cut-off is published.",
             "The Tiffin Girls' School": "The Tiffin Girls' School admits girls by rank order of the combined mark "
                                         "in its own two-stage entrance test, with up to 60 places for girls in "
                                         "its inner area scoring at or above the 350th mark and the rest by mark "
                                         "(designated area first); distance only breaks ties. No distance "
                                         "cut-off is published."}
FAITH = {"The Holy Cross School", "Richard Challoner"}
PRI_CRITERIA = ["Education, Health and Care Plan", "Looked after / previously looked after children",
                "Sibling at the school or paired school", "Exceptional family, social or medical need",
                "Children of staff", "Distance"]


def _secondary(text: str) -> list[dict]:
    rows = afc.parse_secondary_table(text, [47, 69, 86, 101, 118, 148], has_pan=True)
    if len(rows) != 11:
        raise SystemExit(f"kingston: expected 11 secondary schools, parsed {len(rows)}")
    records = []
    for row in rows:
        for k, year in enumerate(SEC_YEARS):
            nod, nc = row.cells.get(2 * k), row.cells.get(2 * k + 1)
            notes: list[str] = []
            allocation = "selective" if row.name in SELECTIVE else \
                "faith_then_distance" if row.name in FAITH else "distance"
            if row.name in SELECTIVE:
                notes.append(SELECTIVE[row.name])
            max_mi, all_offered = None, []
            if nod and nod.startswith("CONTACT"):
                notes.append("The council publishes no allocation figures for this school (\"contact the school "
                             "for allocation information\").")
            else:
                max_mi = afc.cell_miles(nod)
                if afc.cell_all_offered(nod):
                    all_offered = ["All"]
                    notes.append("All preferences met at National Offer Day." if nod.startswith("All") else
                                 "National Offer Day cut-off \"Overseas\": the last place went to an applicant "
                                 "living overseas, so every UK-resident applicant ranked by distance was offered.")
                if nc:
                    notes.append(f"End of national coordination: {afc.describe_nc(nc)}.")
            records.append({
                "name": row.name, "year": year, "pan": row.pan if year == 2025 else None, "applications": None,
                "groups": ["All"], "criteria": [], "max_distance": {"All": max_mi}, "all_offered": all_offered,
                "non_preference_offers": None, "total_offers": None, "allocation": allocation, "notes": notes,
            })
    return records


def build() -> tuple[list[dict], list[dict]]:
    sec_path = common.fetch(LA_CODE, SECONDARY_DOC)
    secondary = _secondary(common.pdftotext(sec_path))
    primary: list[dict] = []
    for doc in PRIMARY_DOCS:
        parsed = afc.parse_primary_table(common.pdftotext(common.fetch(LA_CODE, doc)))
        primary.extend(afc.primary_records([p for p in parsed if p["year"] in doc["years"]], PRI_CRITERIA))
    return secondary, primary
