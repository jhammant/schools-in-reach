"""Southwark (LA 210): Reception from the council's community-primary-school
"Allocation of community school places by criteria" tables (September 2022,
2025, 2026 editions -- 2023/2024 editions could not be found); Year 7 from the
"Starting Secondary School in Southwark 2026/27" admission-arrangements guide
and the September 2026 secondary PAN table.

Southwark's secondary schools are ALL their own admissions authority (16
academies, 2 voluntary-aided, 2 free schools) -- the council only coordinates
applications between them and does not centrally publish Year 7 applications,
banding-test or distance-of-last-offer outcomes for any of them (checked:
southwark.gov.uk / services.southwark.gov.uk admissions pages, moderngov.
southwark.gov.uk committee papers, a WhatDoTheyKnow FOI-request index, and
web.archive.org). Only each school's September 2026 published admission number
and its 2026/27 admission arrangements (criteria order, distance method,
banding, nodal points -- read by hand from the guide) are modelled, all dated
2026; there is no outcomes data (applications/max_distance) to report.

Only Southwark's ~30 "community" primary schools publish allocation-by-
criteria tables; voluntary-aided and academy primary schools set their own
arrangements and are not covered by council-published tables either.
"""

from __future__ import annotations

import re

import common

LA_CODE = "210"
LA_NAME = "Southwark"
# The shared tokeniser's `'s` normalisation only strips an apostrophe-then-s (e.g. Camden's "St Josephs"/"St
# Joseph's" case); it doesn't bridge these two Southwark cases where GIAS and the source disagree the other way
# round, or where the source drops a word GIAS's own name doesn't share a token with:
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "john ruskin unit": ("100798", "GIAS spells it 'John Ruskin Primary School and Language Classes'; the source "
                          "table's short form 'John Ruskin & Unit' shares no token with 'Language Classes', so "
                          "the shared tokeniser's subset-match doesn't bridge it either."),
    "pilgrim way": ("100818", "GIAS spells it \"Pilgrims' Way Primary School\" (apostrophe after the s); the "
                     "source table prints \"Pilgrim's Way\" (apostrophe before the s) -- the reverse of the case "
                     "the shared tokeniser's 's normalisation handles."),
}

PRIMARY_DOCS = {
    2022: {"cache": "primary-allocation-2022.xlsx", "kind": "xlsx",
           "url": "https://web.archive.org/web/20240610140753if_/https://www.southwark.gov.uk/assets/attach/"
                  "127374/Sept-2022-Allocation-of-community-school-places-by-criteria.xlsx",
           "title": "Southwark Council: Allocation of community school places by criteria, September 2022 "
                    "(archived copy -- the live asset at this same URL has since been overwritten by later "
                    "years' editions)"},
    2025: {"cache": "primary-allocation-2025.pdf", "kind": "pdf",
           "url": "https://services.southwark.gov.uk/assets/attach/127374/"
                  "Allocation-of-community-school-places-by-criteria-Sept-2025.pdf",
           "title": "Southwark Council: Allocation of community school places by criteria, September 2025"},
    2026: {"cache": "primary-allocation-2026.pdf", "kind": "pdf",
           "url": "https://www.southwark.gov.uk/sites/default/files/2026-08/"
                  "Sept-2026-Allocation-of-community-school-places-by-criteria.pdf",
           "title": "Southwark Council: Allocation of community school places by criteria, September 2026"},
}

SECONDARY_GUIDE = {"cache": "secondary-brochure-2026.pdf", "kind": "pdf",
                   "url": "https://services.southwark.gov.uk/assets/attach/410313/"
                          "Starting-Secondary-School-in-Southwark-Brochure-2026-2027.pdf",
                   "title": "Southwark Council: Starting Secondary School in Southwark 2026/27 (admission "
                            "arrangements guide, admissions criteria from p21)"}
SECONDARY_PAN = {"cache": "secondary-pan-2026.pdf", "kind": "pdf",
                 "url": "https://services.southwark.gov.uk/assets/attach/426797/"
                        "Southwark-secondary-schools-PAN-September-2026-intake.pdf",
                 "title": "Southwark Council: Southwark secondary schools published admission number, "
                          "September 2026 intake"}
COMMUNITY_ARRANGEMENTS = {"cache": "community-primary-arrangements-2026.pdf", "kind": "pdf",
                          "url": "https://services.southwark.gov.uk/assets/attach/426791/"
                                 "Southwark-community-school-admission-arrangements-2026-to-2027.pdf",
                          "title": "Southwark community primary schools: Admission arrangements for September "
                                   "2026 intake (source of the distance-measurement wording in DISTANCE_NOTES; "
                                   "not machine-parsed for records)"}

DISTANCE_METHOD = "mixed"
DISTANCE_NOTES = ('Community primary schools: "The LA uses the eastings and northings linked to an applicant\'s '
                  'address to calculate a straight-line distance measurement to all of our community schools in '
                  'Southwark, which is generated by our Capita pupil database" (council\'s "Admission arrangements '
                  'for September 2026 intake" for community primary schools, section 1.1 note (e)). The same '
                  'document adds that Ivydale Primary School (which has two sites) is measured to each site\'s '
                  'main gate, the shorter distance used; and that flats sharing a communal entrance are measured '
                  'to the block, with lower door numbers prioritised in a tie. '
                  'Secondary schools set their own arrangements as their own admissions authorities: most measure '
                  'a straight-line distance from the home address to the school\'s main entrance/gate (a few '
                  'instead to a stated "admission nodal point" some distance from the school, e.g. a road '
                  'junction) -- but The City of London Academy (Southwark) measures "the shortest safe walking '
                  'distance" to its nodal point, not a straight line.')

# Read by hand from "Starting Secondary School in Southwark 2026/27", p21 onwards (one section per school).
# Dict keys are the school names exactly as printed in the PAN table (see _parse_secondary_pan).
SEC_ALLOCATION: dict[str, str] = {
    "Ark All Saints": "distance",
    "Ark Globe": "distance",
    "Ark Walworth Academy": "distance",
    "Bacon’s College": "catchment_then_distance",
    "Haberdashers’ Aske’s Borough Academy": "distance",
    "Harris Academy Bermondsey": "distance",
    "Harris Academy Peckham": "distance",
    "Harris Boys’ Academy East Dulwich": "distance",
    "Harris Girls’ Academy East Dulwich": "nodal_point",
    "Kingsdale Foundation School": "mixed",
    "Notre Dame RC Girls’ School": "faith_then_distance",
    "Sacred Heart Catholic School": "faith_then_distance",
    "South Bank University Academy": "mixed",
    "St Michael’s Catholic College": "faith_then_distance",
    "St Saviour’s & St Olave’s School": "faith_then_distance",
    "St Thomas the Apostle College": "faith_then_distance",
    "The Charter School Bermondsey": "distance",
    "The Charter School East Dulwich": "nodal_point",
    "The Charter School North Dulwich": "mixed",
    "The City of London Academy": "nodal_point",
}
SEC_GROUPS: dict[str, list[str]] = {
    "Kingsdale Foundation School": ["Band 1", "Band 2", "Band 3"],
}
SEC_NOTES: dict[str, list[str]] = {
    "Bacon’s College": ["Priority is given to children living south of the Thames with an SE or SW postcode "
                            "(closest first), ahead of children in any other postal area (also ranked by "
                            "proximity): modelled here as catchment_then_distance."],
    "Harris Girls’ Academy East Dulwich": ["Nodal point: \"the corner of the junction between Homestall Road "
                                               "and Peckham Rye\" -- straight-line distance is measured from the "
                                               "child's home to this point, not to the school itself."],
    "Kingsdale Foundation School": ["No distance criterion at all: places go by 3 ability bands (test scores), "
                                    "then within each band by looked-after-children / music-or-sport-scholarship / "
                                    "sibling / staff-child / exceptional-need priority, then up to 55 places to "
                                    "designated feeder primary schools, then random allocation."],
    "South Bank University Academy": ["Pupil-premium eligibility is prioritised ahead of the distance criterion "
                                      "(criterion 2 of 6); modelled here as mixed rather than pure distance."],
    "The Charter School East Dulwich": ["Nodal point: \"the nodal point at the Jarvis Road entrance\", measured "
                                        "from an Ordnance Survey centroid of the home address using a GIS."],
    "The Charter School North Dulwich": ["Up to 12 places are reserved for pupil-premium-eligible children "
                                         "(criterion 6, ranked after distance at criterion 5); modelled here as "
                                         "mixed."],
    "The City of London Academy": ["Nodal point: \"the corner of Lynton Road and St James's Road by the main "
                                   "academy building\", measured by the shortest SAFE WALKING distance (not a "
                                   "straight line) from the child's home -- the only Southwark secondary school "
                                   "known to use a walking-route measure."],
}
# Two schools' PAN cells in the source PDF have a footnote-reference digit fused onto the number with no space
# (pdftotext artefact): "1401" = PAN 140 + footnote marker "1"; "1952" = PAN 195 + footnote marker "2".
PAN_OVERRIDES: dict[str, tuple[int, str]] = {
    "Ark Globe": (140, "Published admission number is 140 for external applicants; up to 60 further places are "
                       "reserved for the academy's own year 6 pupils transferring internally (capacity 200 if "
                       "fewer than 60 transfer internally)."),
    "Bacon’s College": (195, "Published admission number is increased by 15 (from 180 to 195) for the "
                                 "September 2026 intake only."),
}
NO_RESULTS_NOTE = ("No applications, banding-test or distance-of-last-offer outcome data is centrally published "
                   "for this school; only the published admission number and admission arrangements are recorded "
                   "(see module docstring).")

SEC_MISSING_NOTE = ("No Year 7 applications, banding-test outcomes or distance-of-last-offer figures are centrally "
                    "published by Southwark Council for any secondary school: all 20 Southwark secondary schools "
                    "are their own admissions authority. Only the September 2026 published admission number and "
                    "each school's 2026/27 admission arrangements (criteria order, distance method, banding, nodal "
                    "points) are recorded, all for 2026 only.")
PRIMARY_MISSING_NOTE = ("Only Southwark's ~30 \"community\" primary schools publish allocation-by-criteria tables; "
                        "voluntary-aided and academy primary schools set their own arrangements and are not "
                        "covered by any council-published table. Three editions were found -- September 2022 (an "
                        "archived xlsx; the live asset at that URL has since been overwritten), 2025 and 2026 -- "
                        "2023 and 2024 editions could not be located on the council site or in web.archive.org.")
MISSING_NOTE = SEC_MISSING_NOTE + " " + PRIMARY_MISSING_NOTE


def _norm(name: str) -> str:
    return name.replace("’", "'").strip()


def _parse_secondary_pan(text: str) -> list[dict]:
    start = text.index("1.1 Academies")
    end = text.index("\nNotes")
    body = text[start:end]
    records = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = re.match(r"^(.+\S)\s+(\d+)$", line)
        if not m:
            continue
        name, pan = m.group(1).strip(), int(m.group(2))
        if name in ("School",) or re.match(r"^\d+(\.\d+)?\s", name):
            continue
        note = None
        if name in PAN_OVERRIDES:
            pan, note = PAN_OVERRIDES[name]
        allocation = SEC_ALLOCATION.get(name, "distance")
        groups = SEC_GROUPS.get(name, ["All"])
        notes = list(SEC_NOTES.get(name, []))
        if note:
            notes.append(note)
        notes.append(NO_RESULTS_NOTE)
        records.append({
            "name": _norm(name), "year": 2026, "pan": pan, "applications": None, "groups": groups,
            "criteria": [], "max_distance": {g: None for g in groups}, "all_offered": [],
            "non_preference_offers": None, "total_offers": None, "allocation": allocation, "notes": notes,
        })
    if len(records) != 20:
        raise SystemExit(f"southwark: expected 20 secondary schools in the PAN table, parsed {len(records)}")
    return records


_ALL_OFFERED_NOTE = ("All applicants who were considered for a place at this school were offered one; the "
                     "distance criterion was not needed.")

# These six names appear as ordinary rows (PAN, applications, criteria breakdown) in the September 2022 edition
# of this table but not in the 2025 or 2026 editions, and don't cleanly correspond to a currently-open Southwark
# primary school. Checked individually: "Camelot" and "Cobourg" are the pre-amalgamation names of two schools
# that merged in 2023 to form Bird In Bush School (URN 100780, itself already a separate row in this same 2022
# table under its post-merger name -- see southwarknews.co.uk, "Cobourg Primary School set to merge with Camelot
# Primary School"); "Comber Grove", "Dog Kennel Hill" and "Townsend" are GIAS "Closed" with no open successor
# under LA 210; "Rotherhithe" did convert to an academy (GIAS URN 149605) and the shared matcher resolves it
# there automatically. Given as printed rather than guessed at or silently dropped, per the task brief, but
# flagged here since a couple of these may double-count a school already present under its current name.
LEGACY_2022_ONLY = {"Camelot", "Cobourg", "Comber Grove", "Dog Kennel Hill", "Rotherhithe", "Townsend"}
_LEGACY_NOTE = ("This school does not appear in the 2025 or 2026 editions of this table and may be a "
               "pre-amalgamation/pre-closure name rather than a school still taking Southwark community-school "
               "admissions in later years (see LEGACY_2022_ONLY in this module for what was checked).")


def _primary_record(name: str, year: int, pan: int, applications: int, sen, lac, sib, socmed, staff, dist_count,
                    dist_m, extra_notes: list[str] | None = None) -> dict:
    extra_notes = extra_notes or []
    all_offered = sen == "ALL OFFERED" if isinstance(sen, str) else False
    if all_offered:
        return {"name": _norm(name), "year": year, "pan": pan, "applications": applications, "total_offers": None,
                "criteria": [], "max_distance": None, "all_offered": True, "non_preference_offers": None,
                "allocation": "distance", "notes": [_ALL_OFFERED_NOTE] + extra_notes}
    criteria = [
        {"label": "SEN", "total": int(sen)},
        {"label": "LAC", "total": int(lac)},
        {"label": "Siblings", "total": int(sib)},
        {"label": "Social/Medical", "total": int(socmed)},
        {"label": "Children of staff at the school", "total": int(staff)},
        {"label": "Distance", "total": int(dist_count)},
    ]
    max_distance = common.miles(float(dist_m), from_unit="metres")
    return {"name": _norm(name), "year": year, "pan": pan, "applications": applications, "total_offers": None,
            "criteria": criteria, "max_distance": max_distance, "all_offered": False,
            "non_preference_offers": None, "allocation": "distance", "notes": extra_notes}


def _parse_primary_pdf(text: str, year: int) -> list[dict]:
    # Some editions of this document carry a leftover page 2 from a much older edition (a stray "Furthest
    # distance (metres) offered a school place" summary with no year label of its own, confirmed against the
    # 2022 xlsx to be September 2022 data republished verbatim); only the labelled 26/27-style table above the
    # first footnote is this year's data.
    text = text.split("*School has a designated ASD base")[0]
    records = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = re.split(r"\s{2,}", line)
        if len(parts) == 7 and parts[4] == "ALL APPLICANTS OFFERED A PLACE":
            name, pan_raw, apps_raw = parts[0], parts[1], parts[2]
            records.append(_primary_record(name, year, int(pan_raw.rstrip("*")), int(apps_raw),
                                           "ALL OFFERED", None, None, None, None, None, None))
        elif len(parts) == 13:
            name, pan_raw, apps_raw = parts[0], parts[1], parts[2]
            sen, lac, sib, socmed, staff, dist_count, dist_m = parts[4], parts[5], parts[6], parts[7], parts[8], \
                                                                parts[9], parts[10]
            records.append(_primary_record(name, year, int(pan_raw.rstrip("*")), int(apps_raw), sen, lac, sib,
                                           socmed, staff, dist_count, dist_m))
    if not records:
        raise SystemExit(f"southwark: no primary rows parsed for {year}")
    return records


def _parse_primary_xlsx(path, year: int) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Sheet1"]
    records = []
    rows = list(ws.iter_rows(values_only=True))
    for row in rows[1:]:
        name = row[0]
        if not name or not isinstance(name, str) or name.startswith("*"):
            continue
        try:
            pan = int(str(row[1]).rstrip("*"))
        except (ValueError, TypeError):
            continue
        applications = int(row[2])
        sen, lac, sib, socmed, staff, dist_count, dist_m = row[4], row[5], row[6], row[7], row[8], row[9], row[10]
        extra_notes = [_LEGACY_NOTE] if name.strip() in LEGACY_2022_ONLY else []
        records.append(_primary_record(name, year, pan, applications, sen, lac, sib, socmed, staff, dist_count,
                                       dist_m, extra_notes))
    if not records:
        raise SystemExit(f"southwark: no primary rows parsed for {year}")
    return records


def build() -> tuple[list[dict], list[dict]]:
    guide_path = common.fetch(LA_CODE, SECONDARY_GUIDE)
    del guide_path  # not machine-parsed: its criteria were read by hand into SEC_ALLOCATION/SEC_GROUPS/SEC_NOTES
    arrangements_path = common.fetch(LA_CODE, COMMUNITY_ARRANGEMENTS)
    del arrangements_path  # not machine-parsed: its distance-measurement wording was read by hand into DISTANCE_NOTES

    pan_path = common.fetch(LA_CODE, SECONDARY_PAN)
    secondary = _parse_secondary_pan(common.pdftotext(pan_path))

    primary: list[dict] = []
    for year, spec in PRIMARY_DOCS.items():
        path = common.fetch(LA_CODE, spec)
        if spec["kind"] == "xlsx":
            primary.extend(_parse_primary_xlsx(path, year))
        else:
            primary.extend(_parse_primary_pdf(common.pdftotext(path), year))
    return secondary, primary


SOURCES = [{"title": d["title"], "url": d["url"], "licence": "Open Government Licence v3.0"}
          for d in [SECONDARY_GUIDE, SECONDARY_PAN, COMMUNITY_ARRANGEMENTS, *PRIMARY_DOCS.values()]]
