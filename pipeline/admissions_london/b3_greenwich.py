"""Greenwich (LA 203): parse the Royal Borough of Greenwich's annual "Secondary
Schools in Royal Greenwich" and "Primary Schools in Royal Greenwich" admission
booklets (PDF, via pdftotext -layout for secondary and pdfplumber word
positions for primary).

Each booklet edition is published a year ahead of the entry it advertises and
illustrates each school's page with the previous year's actual outcome
figures as a guide (e.g. the "2024/2025" edition, whose closing date is 31
October 2023, shows "for entry 2023" figures). Three secondary editions were
found (giving entry years 2022, 2023, 2025) and two primary editions (entry
years 2022, 2023); the intervening editions could not be located either live
on royalgreenwich.gov.uk or via the Wayback Machine.

Secondary layout: each school gets one two-column magazine page (prose on the
left, a data sidebar on the right); pdftotext -layout interleaves both
columns onto the same visual rows, so school names/years are recovered by
zipping the document's "for entry <year>" markers (one per school, in the
same order as the booklet's own contents list) against a hand-transcribed
per-edition name list, then searching the text between consecutive markers
for the "Band" / "Places available" / "Applications received" / distance
label rows -- these particular rows do reconstruct correctly across the full
page width even though surrounding prose does not.

Primary layout: four schools per landscape PDF page, in a strict 4-column
grid; pdfplumber word x-positions are split into page-width quarters (this
matches the observed column boundaries closely enough that no content
crosses a boundary) and each quarter's words are reassembled into clean,
single-school text via pipeline.admissions_london.pdftools helpers.

Secondary distances are published in **km**; primary distances in **metres**.
Both are converted to miles via common.miles().
"""

from __future__ import annotations

import re
from collections import defaultdict

import common
import pdftools

LA_CODE = "203"
LA_NAME = "Greenwich"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "crown stationers woods": ("141309", "renamed Leigh Stationers' Academy (same URN) after joining Leigh "
                               "Academies Trust; the 2022/2023-entry booklet editions used the old name "
                               "Stationers' Crown Woods Academy"),
    "manor rockcliffe": ("143593", "GIAS spells it Rockliffe Manor Primary School (one 'c'); the source "
                         "booklets consistently spell it Rockcliffe Manor School (two 'c's)"),
    # Greenwich has two distinct "Christ Church CE" primary schools; the shared tokeniser's subset-match rule
    # (a shorter GIAS name matching any longer source string containing the same words) makes both source
    # postcodes ambiguously match the shorter-named school unless pinned explicitly:
    "ce christ church se10": ("100165", "Christ Church Church of England Primary School, SE10 0DZ"),
    "ce christ church se18": ("100166", "Christ Church Church of England Primary School, Shooters Hill, "
                              "SE18 3RS -- the source table identifies it by postcode district (SE18) rather "
                              "than GIAS's own 'Shooters Hill' suffix, which shares no token with it"),
}

OGL = "Open Government Licence v3.0"

DISTANCE_METHOD = "mixed"
DISTANCE_NOTES = ('Distance criteria rank applicants by home-to-school distance measured to the school\'s main '
                  'entrance, with one nodal-point exception (James Wolfe School, below); the booklets give the last '
                  'offer in km (secondary) and m (primary). Where a school admits to split sites (Heronsgate, Invicta, Plumcroft '
                  'primary schools), distance is measured to whichever site is nearer the applicant\'s home. '
                  'James Wolfe School measures "using the main entrance to the former Greenwich Town Hall, '
                  'Meridian House, Royal Hill (SE10)" rather than either of its two school sites -- a genuine '
                  'nodal point (Royal Greenwich Determined Admission Arrangements 2025/26, section 2.5.3). Four '
                  'secondary academies (Harris Academy Greenwich, Leigh Academy Blackheath, Leigh Halley Academy '
                  '(formerly The Halley Academy), Leigh Stationers\' Academy (formerly Stationers\' Crown Woods '
                  'Academy)) use ability banding from a Year 6 test, with distance used only to rank within each '
                  'band. St Thomas More Catholic Comprehensive School and St Ursula\'s Convent School "do not '
                  'offer places based on home to school distance" at all (Royal Greenwich secondary school offers '
                  'map page) -- their published booklet profiles show no applications/distance figures.')

# ---------------------------------------------------------------------- secondary

# Each edition's school profiles appear in this exact order (matching the booklet's own "Contents" page); the
# name printed is the one used that edition (two academies were renamed, and reordered alphabetically under
# their new name, between the 2024/25 and 2026/27 editions).
SEC_NAMES_OLD = ["Ark Greenwich Free School", "Eltham Hill School", "The Halley Academy",
                "Harris Academy Greenwich", "The John Roan School", "Leigh Academy Blackheath",
                "Plumstead Manor School", "Royal Greenwich Trust School", "St Mary Magdalene CE School",
                "St Paul's Academy", "St Thomas More Catholic Comprehensive School",
                "St Ursula's Convent School", "Stationers' Crown Woods Academy", "Thomas Tallis School",
                "Woolwich Polytechnic School for Boys", "Woolwich Polytechnic School for Girls"]
SEC_NAMES_LEIGH = ["Ark Greenwich Free School", "Eltham Hill School", "Harris Academy Greenwich",
                   "Leigh Academy Blackheath", "Leigh Halley Academy", "Leigh Stationers' Academy",
                   "Plumstead Manor School", "Royal Greenwich Trust School", "St Mary Magdalene CE School",
                   "St Paul's Academy", "St Thomas More Catholic Comprehensive School",
                   "St Ursula's Convent School", "The John Roan School", "Thomas Tallis School",
                   "Woolwich Polytechnic School for Boys", "Woolwich Polytechnic School for Girls"]

SECONDARY_EDITIONS = [
    # (entry year, cache filename, url, ordered name list)
    (2022, "secondary-booklet-old.pdf",
     "https://www.royalgreenwich.gov.uk/download/downloads/id/5916/secondary_school_admissions_booklet.pdf",
     SEC_NAMES_OLD),
    (2023, "secondary-booklet-2026.pdf",
     "https://www.royalgreenwich.gov.uk/download/downloads/id/7546/secondary_school_admission_booklet.pdf",
     SEC_NAMES_OLD),
    (2025, "secondary-booklet-2627.pdf",
     "https://www.royalgreenwich.gov.uk/sites/default/files/2026-02/secondary%20school%20booklet%2026%2027.pdf",
     SEC_NAMES_LEIGH),
]

FAITH_RE = re.compile(r"Catholic|Convent|CE School|Church of England", re.I)
NODAL_SEC_RE = re.compile(r"James Wolfe", re.I)  # not actually a secondary school; kept for clarity/no-op

_STOP = r"(?=\s{2,}[A-Za-z]|\n)"
BAND_RE = re.compile(r"(?<![A-Za-z])Band\s+([0-9][0-9\s]*)" + _STOP)
PAN_RE = re.compile(r"Places available\s+([0-9][0-9,.\s*-]*)" + _STOP)
APP_RE = re.compile(r"Applications received\s+([0-9][0-9,.\s-]*)" + _STOP)
DIST_RE = re.compile(r"(?:Last offer on distance|Distance of last offer) \(km\)\s*([0-9N/A.\s-]*)" + _STOP)


def _num(tok: str) -> int | None:
    tok = tok.rstrip("*")
    return int(tok.replace(",", "")) if re.fullmatch(r"-?\d+", tok) else None


def _dist_mi(tok: str) -> float | None:
    if tok in ("-", "N/A", ""):
        return None
    return common.miles(float(tok), from_unit="km")


def _parse_secondary_edition(text: str, year: int, names: list[str]) -> list[dict]:
    matches = list(re.finditer(r"for entry \d{4}", text))
    if len(matches) != len(names):
        raise SystemExit(f"greenwich secondary {year}: expected {len(names)} school profiles, "
                         f"found {len(matches)} 'for entry' markers")
    records = []
    for idx, (name, m) in enumerate(zip(names, matches)):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        band_m, pan_m, app_m, dist_m = BAND_RE.search(block), PAN_RE.search(block), APP_RE.search(block), \
                                        DIST_RE.search(block)
        n_bands = len(band_m.group(1).split()) if band_m else 0
        pans = [t for t in (pan_m.group(1).split() if pan_m else [])]
        apps = [t for t in (app_m.group(1).split() if app_m else [])]
        dists = [t for t in (dist_m.group(1).split() if dist_m and dist_m.group(1).strip() else [])]
        notes: list[str] = []
        if n_bands:
            groups = [f"Band {b}" for b in band_m.group(1).split()]
            width = max(len(pans), len(apps), len(dists), n_bands)
            if width == n_bands + 2:
                groups.append("Untested")  # the final trailing column is always an aggregate "Total", dropped
            band_pans = [_num(p) for p in pans[:n_bands]]
            band_apps = [_num(a) for a in apps[:n_bands]]
            total_pan = _num(pans[-1]) if width > n_bands and len(pans) == width else \
                (sum(band_pans) if band_pans and None not in band_pans else None)
            total_apps = _num(apps[-1]) if width > n_bands and len(apps) == width else \
                (sum(band_apps) if band_apps and None not in band_apps else None)
            pans, apps, dists = pans[:len(groups)], apps[:len(groups)], dists[:len(groups)]
            allocation = "mixed"
            notes.append(f"{n_bands}-band ability-banding scheme (Year 6 test); distance ranks applicants "
                        f"within each band, not across the whole cohort.")
        else:
            groups = ["All"]
            allocation = "faith_then_distance" if FAITH_RE.search(name) else "distance"
            if not pans and not apps and not dists:
                notes.append("No applications, admission-number or distance-of-last-offer figures published "
                            "for this school this year (this school's booklet profile leaves these fields "
                            "blank; per the council's secondary-school offers map, St Thomas More Catholic "
                            "Comprehensive School and St Ursula's Convent School do not offer places based on "
                            "home to school distance at all).")
        pan = _num(pans[0]) if len(groups) == 1 and pans else (total_pan if n_bands else None)
        applications = _num(apps[0]) if len(groups) == 1 and apps else (total_apps if n_bands else None)
        max_distance = {g: (_dist_mi(dists[i]) if i < len(dists) else None) for i, g in enumerate(groups)} \
            if len(groups) > 1 else {"All": (_dist_mi(dists[0]) if dists else None)}
        criteria = []
        if len(groups) > 1:
            for i, g in enumerate(groups):
                criteria.append({"label": f"{g} places available", "total": _num(pans[i]) if i < len(pans) else None})
                criteria.append({"label": f"{g} applications", "total": _num(apps[i]) if i < len(apps) else None})
            criteria = [c for c in criteria if c["total"] is not None]
        records.append({
            "name": name, "year": year, "pan": pan, "applications": applications, "groups": groups,
            "criteria": criteria, "max_distance": max_distance, "all_offered": [],
            "non_preference_offers": None, "total_offers": None, "allocation": allocation, "notes": notes,
        })
    return records


def _build_secondary() -> list[dict]:
    records = []
    for year, cache, url, names in SECONDARY_EDITIONS:
        path = common.fetch(LA_CODE, {"cache": cache, "url": url, "kind": "pdf"})
        text = common.pdftotext(path)
        records.extend(_parse_secondary_edition(text, year, names))
    return records


# ---------------------------------------------------------------------- primary

PRIMARY_EDITIONS = [
    (2022, "primary-booklet-old.pdf",
     "https://www.royalgreenwich.gov.uk/download/downloads/id/5917/primary_school_admissions_booklet.pdf"),
    (2023, "primary-booklet-2425.pdf",
     "https://www.royalgreenwich.gov.uk/download/downloads/id/7547/primary_school_admission_booklet.pdf"),
]

PRIMARY_APP_RE = re.compile(r"Applications to\s+(.+?)\s+for\s+entry\s+(\d{4})", re.S)
PRIMARY_PAN_RE = re.compile(r"Places available\s+(\S+)")
PRIMARY_APPS_RE = re.compile(r"Applications received\s+(\S+)")
PRIMARY_DIST_RE = re.compile(r"Distance of last offer \(m\)\s+(\S+)")

NODAL_PRIMARY = {"James Wolfe School": ("nodal_point", ["Nodal point: distance is measured from the home "
    "address to \"the main entrance to the former Greenwich Town Hall, Meridian House, Royal Hill (SE10)\", not "
    "to either of the school's two sites (Randall Place for Reception-Y3, Royal Hill for Y4-6)."])}
SPLIT_SITE_NOTE = {
    "Heronsgate School": "Split-site school (Royal Arsenal and Thamesmead sites); distance is measured to the "
                         "Thamesmead site's main entrance.",
    "Invicta School": "Split-site school (Benbow Street and Invicta Road sites); distance is measured to "
                      "whichever site is nearest the applicant's home.",
    "Plumcroft School": "Split-site school (Plumcroft Road and Vincent Road sites); distance is measured to "
                        "whichever site is nearest the applicant's home.",
}


def _column_text(page) -> list[str]:
    w = page.width
    bounds = [w / 4, w / 2, 3 * w / 4]
    words = pdftools.page_words(page)
    buckets: dict[int, list] = defaultdict(list)
    for word in words:
        buckets[sum(1 for b in bounds if word.x0 >= b)].append(word)
    out = []
    for k in sorted(buckets):
        lines = pdftools.group_lines(buckets[k])
        lines.sort(key=lambda l: l.top)
        out.append(" ".join(l.text for l in lines))
    return out


def _parse_primary_edition(pdf_path, year: int) -> list[dict]:
    import pdfplumber

    records = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "Applications to" not in text:
                continue
            for col_text in _column_text(page):
                m = PRIMARY_APP_RE.search(col_text)
                if not m:
                    continue
                name = re.sub(r"\s+", " ", m.group(1)).strip()
                if not name.endswith("School"):
                    name = f"{name} School"
                pan_m, apps_m, dist_m = PRIMARY_PAN_RE.search(col_text), PRIMARY_APPS_RE.search(col_text), \
                                        PRIMARY_DIST_RE.search(col_text)
                pan = _num(pan_m.group(1)) if pan_m else None
                applications = _num(apps_m.group(1)) if apps_m else None
                dist_raw = dist_m.group(1) if dist_m else None
                max_distance = common.miles(float(dist_raw), from_unit="metres") if dist_raw and \
                    re.fullmatch(r"\d+(\.\d+)?", dist_raw) else None
                notes = [SPLIT_SITE_NOTE[name]] if name in SPLIT_SITE_NOTE else []
                allocation = "distance"
                if name in NODAL_PRIMARY:
                    allocation, notes = NODAL_PRIMARY[name][0], list(NODAL_PRIMARY[name][1])
                records.append({
                    "name": name, "year": year, "pan": pan, "applications": applications, "total_offers": None,
                    "criteria": [], "max_distance": max_distance, "all_offered": False,
                    "non_preference_offers": None, "allocation": allocation, "notes": notes,
                })
    return records


def _build_primary() -> list[dict]:
    records = []
    for year, cache, url in PRIMARY_EDITIONS:
        path = common.fetch(LA_CODE, {"cache": cache, "url": url, "kind": "pdf"})
        records.extend(_parse_primary_edition(path, year))
    return records


SOURCES = [{"title": f"Royal Borough of Greenwich: Secondary Schools in Royal Greenwich admission booklet "
                     f"(entry {year} figures)", "url": url, "licence": OGL}
          for year, _, url, _ in SECONDARY_EDITIONS] + \
         [{"title": f"Royal Borough of Greenwich: Primary Schools in Royal Greenwich admission booklet "
                    f"(entry {year} figures)", "url": url, "licence": OGL}
          for year, _, url in PRIMARY_EDITIONS] + \
         [{"title": "Royal Borough of Greenwich: Determined Admission Arrangements 2025 to 2026 (source of the "
                    "James Wolfe/Heronsgate/Invicta/Plumcroft split-site and nodal-point wording)",
           "url": "https://www.royalgreenwich.gov.uk/sites/default/files/2025-01/"
                  "Royal-Greenwich-Determined-Admission-Arrangements-2025-to-2026-Revised.pdf", "licence": OGL}]

MISSING_NOTE = ("Secondary: three editions found giving entry years 2022, 2023 and 2025 (2024 and 2026 editions "
               "could not be located live or via the Wayback Machine); St Thomas More Catholic Comprehensive "
               "School and St Ursula's Convent School publish no applications/distance figures in any edition "
               "(they select entirely on faith criteria, per the council's own offers-map page). Primary: only "
               "two editions found (entry years 2022 and 2023); only community/voluntary-controlled primary "
               "schools that the council itself coordinates appear in this table -- voluntary-aided/academy "
               "primary schools are not covered. No banding is used for Reception; the four ability-banding "
               "secondary academies rank by test score first and by distance only within each band.")


def build() -> tuple[list[dict], list[dict]]:
    return _build_secondary(), _build_primary()
