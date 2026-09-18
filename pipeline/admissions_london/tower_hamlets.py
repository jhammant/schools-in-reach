"""Tower Hamlets (LA 211): parse the "Starting Primary School" and "Ready for
Secondary School in Tower Hamlets" prospectuses (PDF).

Primary: a single consolidated table, "Summary of last year's application and
offers", lists every *oversubscribed* community school with its PAN,
applications, admission-criteria counts, and the "Tie-break cut off distance"
in metres for applicants outside the catchment area (Tower Hamlets primary
admissions are catchment-then-distance: catchment-area applicants are
prioritised over the borough-wide distance criterion). Community schools not
listed had every on-time applicant offered a place (stated in the booklet's
own text); voluntary-aided/academy primary schools are not covered by this
table at all.

Secondary: each school gets a profile page with a small "Previous year's
applications" box giving PAN ("Places available"), applications received,
and "Last offer on distance in meters" by test band (Band A-D, borough-wide
cognitive-ability-test banding, applied before distance), plus appeals -- the
Appeals count is not part of the output schema and is not recorded. Extracted
with pdfplumber word positions since pdftotext -layout misaligns this table's
wrapped school names.
"""

from __future__ import annotations

import re

import pdfplumber

import common
import pdftools

LA_CODE = "211"
LA_NAME = "Tower Hamlets"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    # The source table just says "Blue Gate Fields"; GIAS has separate infant and junior URNs on the same
    # site. Reception admissions are to the infants' school.
    "blue fields gate": ("100915", "Reception admissions at this site are to Blue Gate Fields Infants' School"),
    # GIAS's current name for this school omits "Science" and uses "Mathematics" in full.
    "college computing green maths mulberry science stepney":
        ("144700", "current GIAS name is 'Mulberry Stepney Green Mathematics and Computing College'"),
}

PRIMARY_DOCS = {
    2024: {"cache": "primary-prospectus-2025.pdf",
          "url": "https://stebon.org.uk/wp-content/uploads/2025/01/Primary-School-prospectus.pdf",
          "title": "Tower Hamlets Council: Starting Primary School in Tower Hamlets 2025 "
                   "(as republished by Stebon Primary School)"},
    2025: {"cache": "primary-prospectus-2026.pdf",
          "url": "https://www.towerhamlets.gov.uk/Documents/Education-and-skills/Admissions-and-exclusions/"
                 "Admissions/Primary-School-prospectus.pdf",
          "title": "Tower Hamlets Council: Starting Primary School in Tower Hamlets 2026"},
}
SECONDARY_DOCS = {
    2024: {"cache": "secondary-prospectus-2025.pdf",
          "url": "https://bluegatefields-jun.towerhamlets.sch.uk/wp-content/uploads/2024/09/"
                 "Secondary-School-prospectus-2025.pdf",
          "title": "Tower Hamlets Council: Ready for Secondary School in Tower Hamlets 2025 "
                   "(as republished by Bluegate Fields Junior School)"},
    2025: {"cache": "secondary-prospectus-2026.pdf",
          "url": "https://www.towerhamlets.gov.uk/Documents/Education-and-skills/Admissions-and-exclusions/"
                 "SecondarySchoolprospectus.pdf",
          "title": "Tower Hamlets Council: Ready for Secondary School in Tower Hamlets 2026"},
}
DISTANCE_METHOD = "mixed"
DISTANCE_NOTES = ('Primary: "Home to school distances will be measured using the shortest walking route" (note '
                  '6); catchment-area applicants are prioritised ahead of the borough-wide distance criterion, '
                  'so the published distance only applies to the (few) places offered to applicants outside '
                  'their catchment area, and is published in metres (converted to miles here). Secondary: places '
                  'are allocated mostly by a borough-wide banding test (four bands, by cognitive ability), with '
                  'distance as the tie-break within each band; the method of measuring that distance is not '
                  'stated in the prospectus (the table header says "last offer on distance in meters"; converted '
                  'to miles here).')

# --------------------------------------------------------------------------- primary

PRIMARY_ROW_RE = re.compile(r"^\s*([A-Za-z][A-Za-z'&,.\- ]+?)\s{2,}" + r"(\d+)\s+" * 11 + r"(\d+)\s*$", re.M)
PRIMARY_CRITERIA = ["SEN / EHCP", "Looked After Children", "Medical or Social", "Sibling", "Children of Staff"]


def _parse_primary(text: str, year: int) -> list[dict]:
    starts = [m.start() for m in re.finditer(r"Summary of last year", text)]
    if not starts:
        raise SystemExit(f"tower_hamlets primary {year}: 'Summary of last year' section not found")
    start = starts[-1]
    end = text.index("Apply online", start)
    seg = text[start:end]
    records = []
    for m in PRIMARY_ROW_RE.finditer(seg):
        name = m.group(1).strip()
        apps, pan, sen, lac, medsoc, sibling, staff, nearest_in_catch, catch, outside_catch, tiebreak_m, total = \
            (int(g) for g in m.groups()[1:])
        criteria = []
        for label, n in zip(PRIMARY_CRITERIA, (sen, lac, medsoc, sibling, staff)):
            if n:
                criteria.append({"label": label, "total": n})
        # "Nearest school in catchment area" and "Catchment area" offers are catchment-priority offers (not
        # a distance criterion); "outside catchment area" offers are the ones the tie-break distance applies to.
        criteria.append({"label": "Catchment area (nearest school)", "total": nearest_in_catch})
        criteria.append({"label": "Catchment area", "total": catch})
        if outside_catch:
            criteria.append({"label": "Distance (outside catchment area)", "total": outside_catch})
        records.append({
            "name": name, "year": year, "pan": pan, "applications": apps, "total_offers": total,
            "criteria": criteria, "max_distance": common.miles(tiebreak_m, from_unit="metres"),
            "all_offered": False, "non_preference_offers": None, "allocation": "catchment_then_distance",
            "notes": ["Catchment-area applicants are prioritised ahead of the borough-wide distance criterion "
                     f"(only {outside_catch} of {total} offers this year went to applicants living outside the "
                     "school's catchment area); the published \"tie-break cut off distance\" is this school's "
                     "distance figure for the year, as printed, without further detail on which priority group "
                     "it was reached under.",
                     f"Published distance {tiebreak_m} metres, converted to miles here."],
        })
    return records


PRIMARY_ALL_OFFERED_NOTE = ("Tower Hamlets publishes this table only for community schools that received more "
                            "applications than places available; a community school not listed here was able "
                            "to offer a place to every on-time applicant (stated in the prospectus). Voluntary-"
                            "aided and academy primary schools are not covered by this table at all.")

# --------------------------------------------------------------------------- secondary

BAND_KEYS = ["Band A", "Band B", "Band C", "Band D"]


class TableError(ValueError):
    pass


def _page_school_name(lines: list) -> str | None:
    top_lines = sorted((l for l in lines if l.top < 100), key=lambda l: l.top)
    parts = [l.text.strip() for l in top_lines if not re.fullmatch(r"\d+", l.text.strip())]
    name = " ".join(parts).strip()
    name = re.sub(r"\s+\d+$", "", name)  # trailing page-within-section number glued onto the name line
    return name or None


def _parse_secondary_page(page, year: int) -> dict | None:
    words = pdftools.page_words(page)
    if "Previous" not in {w.text for w in words} or "Band" not in {w.text for w in words}:
        return None
    lines = pdftools.group_lines(words)
    name = _page_school_name(lines)
    if not name:
        raise TableError(f"tower_hamlets secondary {year}: could not read school name from page header")
    sub_header = next((l for l in lines if "available" in l.text and "received" in l.text), None)
    if sub_header is None:
        raise TableError(f"tower_hamlets secondary {year} {name}: no 'available/received' header row")
    centers: dict[str, float] = {}
    band_words = [w for w in sub_header.words if w.text == "Band"]
    letters = [w for w in sub_header.words if w.text in ("A", "B", "C", "D")]
    for bw in band_words:
        letter = min(letters, key=lambda l: abs(l.x0 - bw.x1))
        centers[f"Band {letter.text}"] = bw.x0
    for w in sub_header.words:
        if w.text == "available":
            centers["places"] = w.x0
        elif w.text == "received":
            centers["applications"] = w.x0
    # Appeals is not part of the output schema (and its cell can hold free text like "0 upheld from 2 lodged"),
    # so its column is located only to exclude it from the data row before column-matching, not captured.
    appeals_word = next((w for l in lines for w in l.words if w.text == "Appeals"), None)
    appeals_x = appeals_word.x0 - 15 if appeals_word is not None else None
    label_line = next((l for l in lines if l.text.strip() == "applications" and l.top > sub_header.top), None)
    if label_line is None:
        raise TableError(f"tower_hamlets secondary {year} {name}: no data row found")
    data_words = [w for w in words if abs(w.top - label_line.top) <= 12 and w.x0 > sub_header.words[0].x0 + 20
                 and (appeals_x is None or w.x0 < appeals_x)]
    keys = list(centers)
    xs = [centers[k] for k in keys]
    # A band can read "No one was refused a place" instead of a number/n/a/*, spanning several words that would
    # otherwise misalign onto neighbouring columns; consume each such phrase as one unit.
    forced_all_offered: set[str] = set()
    ordered = sorted(data_words, key=lambda w: w.x0)
    phrase = ["No", "one", "was", "refused", "a", "place"]
    consumed_ids: set[int] = set()
    for i in range(len(ordered) - len(phrase) + 1):
        if [w.text for w in ordered[i:i + len(phrase)]] == phrase:
            idx, dist = pdftools.nearest(ordered[i].cx, xs)
            if dist <= 40:
                forced_all_offered.add(keys[idx])
                consumed_ids.update(id(w) for w in ordered[i:i + len(phrase)])
    data_words = [w for w in data_words if id(w) not in consumed_ids]
    cells: dict[str, str] = {}
    for w in data_words:
        idx, dist = pdftools.nearest(w.cx, xs)
        if dist > 30:
            raise TableError(f"tower_hamlets secondary {year} {name}: value {w.text!r} {dist:.0f}pt from column")
        key = keys[idx]
        if key in cells:
            raise TableError(f"tower_hamlets secondary {year} {name}: two values for {key!r}")
        cells[key] = w.text
    pan = pdftools.as_int(cells.get("places", ""))
    applications = pdftools.as_int(cells.get("applications", ""))
    max_distance = {}
    all_offered = []
    for band in BAND_KEYS:
        raw = cells.get(band)
        if band in forced_all_offered:
            max_distance[band] = None
            all_offered.append(band)
        elif raw is None:
            max_distance[band] = None
        elif raw.lower().startswith("n/a") or "*" in raw:
            max_distance[band] = None
            all_offered.append(band)
        else:
            metres = pdftools.as_float(raw)
            max_distance[band] = common.miles(metres, from_unit="metres") if metres is not None else None
    groups = [b for b in BAND_KEYS if b in max_distance]
    return {
        "name": name, "year": year, "pan": pan, "applications": applications, "groups": groups, "criteria": [],
        "max_distance": {g: max_distance[g] for g in groups}, "all_offered": all_offered,
        "non_preference_offers": None, "total_offers": None, "allocation": "mixed",
        "notes": ["Places are allocated mostly by a borough-wide banding test (Band A-D, by cognitive ability), "
                 "with distance the tie-break within each band; \"n/a\" published for a band means every "
                 "applicant in that band was offered a place.",
                 "Published as \"last offer on distance in meters\"; converted to miles here."],
    }


def parse_secondary(paths: dict, skipped: list[str] | None = None) -> list[dict]:
    if skipped is None:
        skipped = []
    out = []
    for year, path in paths.items():
        with pdfplumber.open(path) as pdf:
            for pno, page in enumerate(pdf.pages):
                try:
                    rec = _parse_secondary_page(page, year)
                except TableError as exc:
                    skipped.append(f"{year} page {pno + 1}: {exc}")
                    continue
                if rec is not None:
                    out.append(rec)
    return out


def parse_primary(paths: dict) -> list[dict]:
    out = []
    for year, path in paths.items():
        out.extend(_parse_primary(common.pdftotext(path), year))
    return out
