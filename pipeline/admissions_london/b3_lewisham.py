"""Lewisham (LA 209): parse the council's two rolling "last year's number of
applications and appeals" web pages (secondary and primary/reception).

Secondary: https://lewisham.gov.uk/.../applying-to-start-secondary-school/
last-year-s-number-of-applications-and-appeals-for-secondary-school-places
Only reports schools whose academy trust submits data to the council that
year -- the set of schools listed genuinely varies year to year (as few as 3,
as many as 10); voluntary-aided/faith schools not covered say "contact the
school direct". The live page only ever shows the most recently published
year, so prior years are read from Wayback Machine snapshots taken shortly
after each year's National Offer Day.

Primary: the same page instead links a downloadable "GRID for reception
<year>" PDF -- a much fuller table (30+ community primary schools). Only two
editions could be found (2021 and 2026); the intervening years' PDFs 404 both
live and on Wayback Machine.

Both sources give distance in **metres**, converted to miles via common.miles().
"""

from __future__ import annotations

import re

import common

LA_CODE = "209"
LA_NAME = "Lewisham"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "infants stillness": ("100705", "GIAS spells it singular: Stillness Infant School"),
    "lucas vale": ("100695", "renamed Oak Gardens Primary School (same URN, same Thornville Street SE8 4QB "
                   "site, Phoenix Federation) after the 2021 grid was published"),
    "coopers lane": ("100676", "GIAS spells it with an apostrophe: Cooper's Lane Primary School, which the "
                     "shared tokeniser's 's-stripping rule turns into a different token set than the "
                     "apostrophe-less source spelling"),
    "drake francis sir": ("100712", "renamed Twin Oaks Primary School in 2023 (dropped the Sir Francis Drake "
                          "name over its slave-trade links; same URN, same site)"),
}

DISTANCE_METHOD = "straight_line"
DISTANCE_NOTES = ('"We measured all distances in metres using a straight line from a point in the applicant\'s '
                  'home to a point in the school premises using the ordinance survey [sic; Ordnance Survey]." '
                  '(published footnote, both secondary and primary pages). The 2021 primary edition additionally '
                  'describes this school-end point as "a nodal point within the school premises" -- i.e. a fixed '
                  'reference point inside the school grounds used for GIS measurement, not a nodal point away '
                  'from the school of the kind some other councils use for certain faith schools.')

OGL = "Open Government Licence v3.0"

SECONDARY_PAGE_URL = ("https://lewisham.gov.uk/myservices/education/schools/school-admission/"
                      "applying-to-start-secondary-school/last-year-s-number-of-applications-and-appeals-"
                      "for-secondary-school-places")
PRIMARY_PAGE_URL = ("https://lewisham.gov.uk/myservices/education/schools/school-admission/"
                    "applying-to-start-primary-school/last-year-s-number-of-application-and-appeals-for-"
                    "primary-school-places")

# {year: cache filename}; each year's secondary page was fetched from the live URL (2026) or a specific
# Wayback Machine snapshot taken shortly after that year's National Offer Day (2022-2025).
SECONDARY_DOCS = {
    2022: "secondary-lastyear-2022.html",
    2023: "secondary-lastyear-2023.html",
    2024: "secondary-lastyear-2024.html",
    2025: "secondary-lastyear-2025.html",
    2026: "secondary-lastyear-2026.html",
}
SECONDARY_SNAPSHOT_URL = {
    2022: "https://web.archive.org/web/20220523142246/" + SECONDARY_PAGE_URL,
    2023: "https://web.archive.org/web/20230604202318/" + SECONDARY_PAGE_URL,
    2024: "https://web.archive.org/web/20240420223546/" + SECONDARY_PAGE_URL,
    2025: "https://web.archive.org/web/20250503102228/" + SECONDARY_PAGE_URL,
    2026: SECONDARY_PAGE_URL,
}
# primary: each year's downloadable "GRID for reception" PDF (direct council URLs; the 2022-2025 editions
# could not be located either live or via Wayback Machine -- see MISSING_NOTE)
PRIMARY_DOCS = {
    2021: "grid-reception-2021.pdf",
    2026: "grid-reception-2026.pdf",
}
PRIMARY_DOC_URL = {
    2021: "https://lewisham.gov.uk/-/media/files/imported/reception-application-and-offers-2021-22-intake.ashx",
    2026: "https://lewisham.gov.uk/-/media/services/education/schools/admissions/grid-for-reception-2026.pdf",
}

SOURCES = [
    {"title": f"Lewisham Council: last year's number of applications and appeals for secondary school "
              f"places (data for {y})",
     "url": SECONDARY_SNAPSHOT_URL[y], "licence": OGL}
    for y in SECONDARY_DOCS
] + [
    {"title": f"Lewisham Council: GRID for reception {y} (application and appeal rates for community "
              f"primary schools)",
     "url": PRIMARY_DOC_URL[y], "licence": OGL}
    for y in PRIMARY_DOCS
]

MISSING_NOTE = ("Secondary: only whichever schools' admission authority submitted data to the council that "
               "year are published on this page (3-10 schools per year out of Lewisham's ~19 secondary "
               "schools); most voluntary-aided/faith/academy schools say \"contact the school direct\" and "
               "are not covered at all. Years 2022-2025 were only found via Wayback Machine snapshots of the "
               "page (the live page only ever shows the current year). Primary: the fuller \"GRID for "
               "reception\" table covers Lewisham's ~36 community primary schools, but only the 2021 and 2026 "
               "editions could be located; the 2022-2025 PDFs 404 both live and on the Wayback Machine, and "
               "voluntary-aided/academy primary schools are excluded from this table entirely (\"contact the "
               "school directly\").")

FAITH_RE = re.compile(r"Catholic|Church of England|CofE|C of E|Jewish", re.I)
DIST_NUM_RE = re.compile(r"(\d[\d,]*\.?\d*)")


def _skip_head(name: str) -> bool:
    low = name.strip().lower()
    return low in {"primary navigation", "breadcrumbs and page reading tool", "contact",
                   "secondary school admissions and appeals", "primary school admissions and appeals",
                   "in this section navigation and print", "in this section", "follow us on:",
                   "find out more about us", "utility navigation", "feedback widget",
                   "how helpful did you find this page?", "share page"}


def _extract_school_tables(html: str) -> list[tuple[str, dict[str, str] | None]]:
    """Associate each H2/H3 school-name heading with the <table> (if any) that follows it,
    in document order, skipping page-chrome headings."""
    tokens: list[tuple[str, int, str]] = []
    for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>", html, re.S):
        tokens.append(("H", m.start(), re.sub(r"<[^>]+>", "", m.group(1)).strip()))
    for m in re.finditer(r"<table.*?</table>", html, re.S):
        tokens.append(("T", m.start(), m.group(0)))
    tokens.sort(key=lambda t: t[1])
    out: list[tuple[str, dict[str, str] | None]] = []
    i = 0
    while i < len(tokens):
        kind, _, val = tokens[i]
        if kind == "H" and not _skip_head(val):
            name = val.strip()
            j = i + 1
            table_html = None
            while j < len(tokens) and tokens[j][0] != "H":
                if tokens[j][0] == "T" and table_html is None:
                    table_html = tokens[j][2]
                j += 1
            kv = None
            if table_html:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", table_html, re.S)
                cells = [re.sub(r"<[^>]+>", "", c.replace("&nbsp;", " ")).strip() for c in cells]
                kv = {cells[k]: cells[k + 1] for k in range(0, len(cells) - 1, 2)}
            out.append((name, kv))
            i = j
        else:
            i += 1
    return out


def _crit_label(key: str) -> str | None:
    k = key.lower()
    if "looked after" in k or "public care" in k or "looked child" in k:
        return "Looked after children"
    if "medical" in k or "social" in k:
        return "Exceptional medical or social need"
    if "sibling" in k:
        return "Siblings"
    if "ehcp" in k or ("education" in k and "health" in k and "care" in k):
        return "Education, Health and Care Plan (EHCP)"
    if "staff" in k:
        return "Children of staff"
    return None


def _distance_value(raw: str) -> tuple[float | None, bool, list[str]]:
    """Returns (max_distance_miles, all_offered, notes)."""
    text = raw.strip()
    if not text or text.lower() == "n/a":
        return None, False, []
    if "all places offered" in text.lower() or "all applicants offered" in text.lower():
        return None, True, []
    if text.lower() in ("contact school", "contact the school", "contact the school directly"):
        return None, False, ["Distance of last place offered not published by the council for this school "
                             "this year; the source says to contact the school directly."]
    m = DIST_NUM_RE.search(text)
    if not m:
        raise SystemExit(f"lewisham: unreadable distance value {raw!r}")
    metres = float(m.group(1).replace(",", ""))
    return common.miles(metres, from_unit="metres"), False, []


def _parse_secondary(paths: dict[int, "Path"]) -> list[dict]:  # noqa: F821
    records: list[dict] = []
    for year, path in paths.items():
        html = path.read_text(encoding="utf-8", errors="replace")
        for name, kv in _extract_school_tables(html):
            if not kv:
                continue  # "please contact the school direct" -- no data published this year
            pan = applications = None
            criteria: list[dict] = []
            dist_raw = None
            for key, val in kv.items():
                kl = key.lower()
                if "published admissions" in kl or "places available" in kl:
                    pan = int(val) if val.strip().isdigit() else pan
                elif "total number of applicants" in kl or "applicants who named" in kl:
                    applications = int(val) if val.strip().isdigit() else applications
                elif "distance of last place offered" in kl or "distance" in kl:
                    dist_raw = val
                elif "appeal" in kl:
                    continue
                else:
                    label = _crit_label(key)
                    if label and val.strip().lstrip("-").isdigit():
                        criteria.append({"label": label, "total": int(val)})
            max_distance, all_offered_flag, dist_notes = _distance_value(dist_raw or "")
            allocation = "faith_then_distance" if FAITH_RE.search(name) else "distance"
            records.append({
                "name": name, "year": year, "pan": pan, "applications": applications, "groups": ["All"],
                "criteria": criteria, "max_distance": {"All": max_distance},
                "all_offered": ["All"] if all_offered_flag else [],
                "non_preference_offers": None, "total_offers": None, "allocation": allocation,
                "notes": dist_notes,
            })
    return records


ROW_RE = re.compile(r"^\s*(\S.*?)\s{2,}(.+)$")


ORPHAN_NUM_RE = re.compile(r"^\s*([0-9][0-9,]*)\s*$")


def _parse_primary_text(text: str, year: int) -> list[dict]:
    raw_lines = text.splitlines()
    # locate the data rows: between "Name of school" header repeats and the closing distance-method paragraph
    records: list[dict] = []
    n = len(raw_lines)
    i = 0
    while i < n:
        raw_line = raw_lines[i]
        i += 1
        if not raw_line.strip():
            continue
        if raw_line.strip() in ("Name of school",) or "For 20" in raw_line or "If you want" in raw_line or \
           "For precise" in raw_line or "measured all distances" in raw_line:
            continue
        m = ROW_RE.match(raw_line)
        if not m:
            continue  # a wrapped header fragment or other non-data line
        name, rest = m.group(1).strip(), m.group(2)
        tokens = re.split(r"\s{2,}", rest.strip())
        if len(tokens) < 7 or not tokens[0].lstrip("-").isdigit():
            continue  # not a data row (a wrapped header fragment etc.)
        # pdftotext -layout occasionally wraps one overflowing column (usually "applicants") onto its own
        # line immediately below; if this row is short by exactly one token and the next physical line is a
        # lone number, splice it in as the second token (applicants) before parsing fields.
        if len(tokens) == 9 and i < n:
            om = ORPHAN_NUM_RE.match(raw_lines[i])
            if om:
                tokens.insert(1, om.group(1))
                i += 1
        pan = int(tokens[0])
        applications = int(tokens[1]) if tokens[1].replace(",", "").isdigit() else None
        # last two tokens are always "appeals heard" / "successful appeals"; the token just before those is
        # the trailing criterion column (bulge-class distance for 2021, EHCP for 2026); the distance-of-last-
        # place-offered token is whichever of the remaining middle tokens is a decimal number, "All places
        # offered" or "N/A".
        middle = tokens[2:-2]
        dist_idx = None
        for idx, tok in enumerate(middle):
            if tok.lower() in ("n/a", "all places offered") or re.match(r"^\d[\d,]*\.\d+$", tok):
                dist_idx = idx
                break
        criteria: list[dict] = []
        max_distance = None
        all_offered_flag = False
        if dist_idx is not None:
            max_distance, all_offered_flag, _ = _distance_value(middle[dist_idx])
            numeric_before = middle[:dist_idx]  # public care, medical/social, siblings[, staff]
            labels_before = ["Looked after children", "Exceptional medical or social need", "Siblings",
                             "Children of staff"]
            for label, val in zip(labels_before, numeric_before):
                if val.replace(",", "").isdigit():
                    criteria.append({"label": label, "total": int(val)})
        records.append({
            "name": name, "year": year, "pan": pan, "applications": applications, "total_offers": None,
            "criteria": criteria, "max_distance": max_distance, "all_offered": all_offered_flag,
            "non_preference_offers": None, "allocation": "distance", "notes": [],
        })
    return records


def build() -> tuple[list[dict], list[dict]]:
    sec_paths = {y: common.fetch(LA_CODE, {"cache": fn, "url": SECONDARY_SNAPSHOT_URL[y], "kind": "html"})
                for y, fn in SECONDARY_DOCS.items()}
    secondary = _parse_secondary(sec_paths)

    primary: list[dict] = []
    for year, fn in PRIMARY_DOCS.items():
        pdf_path = common.fetch(LA_CODE, {"cache": fn, "url": PRIMARY_DOC_URL[year], "kind": "pdf"})
        text = common.pdftotext(pdf_path)
        primary.extend(_parse_primary_text(text, year))
    return secondary, primary
