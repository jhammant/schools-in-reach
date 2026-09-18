"""Wandsworth (LA 212): Year 7 from the council's "Previous years' admissions
at Wandsworth secondary schools" report (2022-2025) plus the current "How
school places were offered for secondary schools 2026" report; Reception from
five separate year-by-year "How places were allocated for primary schools
<year>" reports (2022-2026 -- the equivalent primary "previous years" combined
report exists too but its wrapped, multi-column grid table renders inconsistent
column alignment via pdftotext for several schools, e.g. duplicated year/PAN
tokens and swapped distance figures for long-header schools such as Anglo
Portuguese School of London; the five single-year reports are unambiguous
one-row-per-school tables and are used instead).

Wandsworth secondary schools fall into five admission shapes, all read from
the source text (not assumed):
  - "coordinated" (5 schools -- Ark Putney, Ernest Bevin, Harris Academy
    Battersea, St John Bosco, Southfields): almost always "All applicants
    offered a place or a higher preference under co-ordinated admission
    arrangements" i.e. never undersubscribed enough to need the distance
    criterion that year. Harris Academy Battersea is the exception: in 2022 it
    did publish siblings/staff counts and a real cut-off distance.
  - banding (Ashcroft Technology Academy, Chestnut Grove Academy): remaining
    non-specialist places split into 5 ability bands (A-E, based on the
    Wandsworth Year 6 Test) with a separate cut-off distance per band. The
    "previous years" report only gives flat (non-banded) totals for the
    other criteria plus a distance-only band table (national-offer-day and
    by-31-August columns); only the single 2026 report gives a fully banded
    breakdown (each criterion split by band, plus an offered-count for the
    distance criterion per band). Both are modelled; the counts differ by
    what the source document year actually published.
  - selective (Burntwood School, Graveney School): a fixed number of places
    offered by Wandsworth Year 6 Test score (with distance as the score's own
    tie-break for the lowest qualifying score band), and separately
    non-selective "open" places allocated as coordinated/distance.
  - feeder (Bolingbroke Academy): after EHCP/LAC/staff, remaining places go
    to five named partner ("feeder") primary schools by distance within each
    feeder, ahead of any non-feeder applicant.
  - foundation/faith (Saint Cecilia's CofE School): Foundation places split by
    church-attendance category (with distance only as the last Foundation
    sub-category's tie-break), then Open places (siblings/staff/distance).

Distances are published in metres and converted to miles via common.miles().
Both the secondary and primary reports publish two cut-off figures per
criterion each year: the distance reached on national offer day, and a larger
figure reached "by 31 August" (after waiting-list movement/appeals). Only the
national-offer-day figure is used for max_distance here, for consistency with
the single current-year reports (which only ever publish that first figure);
the by-31-August figure is not modelled but is quoted in a school's own notes
where the source states it plainly, for context.

None of the secondary or primary reports state each school's overall Published
Admission Number (PAN) -- only per-criterion sub-totals (e.g. "Selective
(Ability) Places Offered: 70"), which are captured as criteria/notes, not as
`pan`. Wandsworth's "Choose a Wandsworth Secondary School" guide does publish a
PAN table, but only for the *next* admissions round (September 2027 at the
time of writing) -- since Burntwood School's own selective quota alone moved
between 60 and 83 across 2022-2025, that later table's numbers cannot safely
be backdated to 2022-2026 records, so `pan` is left None throughout.
"""

from __future__ import annotations

import re

import common

LA_CODE = "212"
LA_NAME = "Wandsworth"
# Filled in from the self-test (see module docstring / build notes for reasoning per entry).
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "gatton muslim": ("134041", "GIAS spells it 'Gatton (VA) Primary School'; the admissions reports call it "
                      "'Gatton School (Muslim)' (its actual faith character), sharing no distinctive token with "
                      "GIAS's own spelling."),
    "ce christchurch": ("101035", "GIAS spells it as two words, 'Christ Church CofE Primary School'; the 2023 "
                        "source PDF concatenates it to 'Christchurch' (one word), which the tokeniser reads as a "
                        "single distinct token rather than 'christ'+'church'. Closed (2014); no open successor "
                        "found under LA 212."),
    "goldfinch": ("101004", "GIAS has two closed 'Goldfinch Primary School' records with an identical name -- "
                  "the original LA-maintained school (closed 2018, reason 'For Academy') and the academy that "
                  "replaced it at the same postcode (closed in turn in 2025, reason 'Closure') -- so the shared "
                  "tokeniser's exact-name match is ambiguous between the two. Aliasing to the earlier (LA-"
                  "maintained) URN lets the matcher's own succession-chain logic follow it on to the final, "
                  "2025-closed academy URN."),
    "ce mary putney st": ("101046", "GIAS spells it 'St Mary's CE Nursery and Primary School'; the admissions "
                          "reports call it 'St Mary's CE Primary School (Putney)' -- neither 'nursery' nor "
                          "'putney' is a token the other spelling shares."),
}

DISTANCE_METHOD = "straight_line"
DISTANCE_NOTES = ('Secondary: "Distances measured by straight line from home to school." (footnote to every '
                  'school\'s entry in "Previous years\' admissions at Wandsworth secondary schools" and the '
                  'current "How school places were offered" report). '
                  'Primary: "The distance used to prioritise applications for admission to schools in Wandsworth '
                  'will be measured in a straight line between your home and the centre of the school site. All '
                  'measurements will be calculated by Wandsworth Council\'s Geographical Information System. No '
                  'other measurements will be taken into account." (\"Choose a Wandsworth Primary School\" guide, '
                  'FAQ 9); the primary "previous years" report\'s own footnote adds: "Distances measured by a '
                  'straight line in metres from the child\'s address to centre of the school site."')

OGL = "Open Government Licence v3.0"

SEC_PREVIOUS_YEARS = {"cache": "sec-previous-years.pdf", "kind": "pdf",
                      "url": "https://www.wandsworth.gov.uk/media/yi1hafdr/"
                             "previous_years_admissions_for_wandsworth_secondary_schools.pdf",
                      "title": "Wandsworth Council: Previous years' admissions at Wandsworth secondary schools "
                               "(2022-2025)"}
SEC_OFFERED_2026 = {"cache": "sec-offered-2026.pdf", "kind": "pdf",
                    "url": "https://www.wandsworth.gov.uk/media/ln4kgbvg/"
                           "how_school_places_were_offered_for_secondary_schools_2026.pdf",
                    "title": "Wandsworth Council: How school places were offered for secondary schools 2026"}

PRI_OFFERED_URLS = {
    2022: "https://www.wandsworth.gov.uk/media/5813/how_places_were_allocated_for_primary_schools.pdf",
    2023: "https://www.wandsworth.gov.uk/media/13407/how_places_were_allocated_for_primary_schools_2023.pdf",
    2024: "https://www.wandsworth.gov.uk/media/mrenk3gj/how_places_were_allocated_for_primary_schools_2024.pdf",
    2025: "https://wandsworth.gov.uk/media/xonfunuu/how_places_were_allocated_for_primary_schools_2025.pdf",
    2026: "https://www.wandsworth.gov.uk/media/4q2f3jqt/how_places_were_allocated_for_primary_schools_2026.pdf",
}
PRI_OFFERED_DOCS = {
    year: {"cache": f"pri-offered-{year}.pdf", "kind": "pdf", "url": url,
          "title": f"Wandsworth Council: How places were allocated for primary schools {year}"}
    for year, url in PRI_OFFERED_URLS.items()
}

SOURCES = [{"title": d["title"], "url": d["url"], "licence": OGL}
          for d in [SEC_PREVIOUS_YEARS, SEC_OFFERED_2026, *PRI_OFFERED_DOCS.values()]]

MISSING_NOTE = (
    "Secondary: covers all 11 Wandsworth state secondary schools for 2022-2026 (2022-2025 from the council's "
    "\"Previous years' admissions\" report, 2026 from the current \"How school places were offered\" report). "
    "Neither report states each school's overall Published Admission Number; only per-criterion sub-totals "
    "(selective/specialist/banding places, feeder-school places etc) are published, so `pan` is left None "
    "throughout -- see module docstring. The Wandsworth Year 6 Test score thresholds behind the banding and "
    "selective schools' cut-offs are published separately (\"Information about previous years' Year 6 test "
    "scores\", not machine-parsed here) and are noted in the relevant records' `notes` where a distance was also "
    "quoted alongside a score threshold. "
    "Primary: covers Wandsworth's community, faith, free and academy primary/infant schools for 2022-2026 from "
    "five single-year \"How places were allocated\" reports (one row per school per year); a combined \"previous "
    "years\" report also exists but its multi-column grid renders inconsistently for several schools once "
    "converted from PDF (see module docstring) and was not used. For schools whose published table has a faith, "
    "foundation-place or priority-area criteria structure that varies from year to year in column count/order "
    "(mostly Catholic, Church of England and the one Muslim primary school, plus Beatrix Potter, Franciscan and "
    "Penwortham's priority-area tables), the admission number and furthest distance offered are still recorded "
    "but the individual criteria counts are not machine-labelled -- see each such year's notes for the raw "
    "published breakdown instead."
)

# --------------------------------------------------------------------------- shared helpers

NUM_RE = re.compile(r"(\d[\d,]*)")
# matches both the bare-"m" form used in tables ("2659m") and the spelled-out form used in prose
# ("2659 metres from the school")
METRES_RE = re.compile(r"(\d[\d,]*)\s*(?:m\b|metres\b)")


def _int(raw: str) -> int | None:
    raw = raw.strip()
    if raw in ("<5",):
        return None  # suppressed small count; not modelled as a number
    m = NUM_RE.match(raw)
    return int(m.group(1).replace(",", "")) if m else None


def _metres_to_miles(raw: str) -> float | None:
    m = METRES_RE.search(raw)
    return common.miles(float(m.group(1).replace(",", "")), from_unit="metres") if m else None


# tolerates the odd hyphenation/spacing pdftotext sometimes introduces around "co-ordinated"
ALL_OFFERED_RE = re.compile(r"All applicants offered a place or a higher preference under co-?\s*ordinated"
                            r"\s+admission\s+arrangements", re.I)


def _is_all_offered(text: str) -> bool:
    return bool(ALL_OFFERED_RE.search(text))


def _classify_all_offered(text: str) -> tuple[bool, str | None]:
    """Distinguishes 'All applicants offered...' stated as the national-offer-day outcome (what max_distance
    is otherwise based on throughout this module) from the same sentence used to describe a LATER, by-31-
    August outcome after a real offer-day cut-off distance was already published (seen in some selective
    schools' non-selective route, e.g. Burntwood School 2023). Returns (all_offered_on_national_offer_day,
    a note to record when it was instead a by-31-August-only outcome)."""
    m = ALL_OFFERED_RE.search(text)
    if not m:
        return False, None
    preceding = text[max(0, m.start() - 40):m.start()].lower()
    if "31 august" in preceding or "by 31" in preceding:
        return False, ("By 31 August, all applicants had been offered a place or a higher preference under "
                       "coordinated admission arrangements (a real, lower cut-off distance applied on national "
                       "offer day itself -- see max_distance/notes).")
    return True, None


# --------------------------------------------------------------------------- secondary

SEC_SCHOOL_NAMES = [
    "ARK PUTNEY ACADEMY", "ASHCROFT TECHNOLOGY ACADEMY", "BOLINGBROKE ACADEMY", "BURNTWOOD SCHOOL",
    "CHESTNUT GROVE ACADEMY", "ERNEST BEVIN ACADEMY", "GRAVENEY SCHOOL", "HARRIS ACADEMY BATTERSEA",
    "SAINT CECILIA’S CHURCH OF ENGLAND SCHOOL", "ST JOHN BOSCO COLLEGE", "SOUTHFIELDS ACADEMY",
]
FAITH_SEC = {"SAINT CECILIA’S CHURCH OF ENGLAND SCHOOL", "ST JOHN BOSCO COLLEGE"}


SEC_DISPLAY = {
    "ARK PUTNEY ACADEMY": "Ark Putney Academy",
    "ASHCROFT TECHNOLOGY ACADEMY": "Ashcroft Technology Academy",
    "BOLINGBROKE ACADEMY": "Bolingbroke Academy",
    "BURNTWOOD SCHOOL": "Burntwood School",
    "CHESTNUT GROVE ACADEMY": "Chestnut Grove Academy",
    "ERNEST BEVIN ACADEMY": "Ernest Bevin Academy",
    "GRAVENEY SCHOOL": "Graveney School",
    "HARRIS ACADEMY BATTERSEA": "Harris Academy Battersea",
    "SAINT CECILIA’S CHURCH OF ENGLAND SCHOOL": "Saint Cecilia’s Church of England School",
    "ST JOHN BOSCO COLLEGE": "St John Bosco College",
    "SOUTHFIELDS ACADEMY": "Southfields Academy",
}


def _split_school_blocks(text: str, names: list[str]) -> dict[str, str]:
    positions = []
    for name in names:
        pat = re.compile(r"^[ \t]*" + re.escape(name) + r"\b.*$", re.M)
        matches = list(pat.finditer(text))
        if not matches:
            raise SystemExit(f"wandsworth: heading not found: {name!r}")
        # the Contents page (if any) lists names in Title Case, not ALL CAPS, so it never matches this
        # case-sensitive pattern; a school's real section is its first (and possibly only) ALL-CAPS match.
        # Saint Cecilia's has a second "... (CONTINUED)" heading later (its Appeals table); that's fine to
        # leave inside the block since _split_year_blocks() cuts everything from "Appeals Heard" onward.
        positions.append((matches[0].start(), name))
    positions.sort()
    blocks: dict[str, str] = {}
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        blocks[name] = text[start:end]
    return blocks


def _split_year_blocks(text: str) -> dict[int, str]:
    # cut at a genuine "Appeals Heard" section header (indented like any other section header); some pages'
    # side-by-side PDF layout also bleeds an "Appeals Heard" mini-table into the *right-hand* margin of an
    # unrelated band-distance table (e.g. Chestnut Grove Academy 2022) -- that copy is indented much further
    # right and must NOT be treated as a cutoff, or the real data to its left would be discarded.
    m = re.search(r"(?m)^\s{0,20}Appeals Heard", text)
    if m:
        text = text[:m.start()]
    matches = list(re.finditer(r"(?m)^\s*(20\d\d)\s*$", text))
    out: dict[int, str] = {}
    for i, m in enumerate(matches):
        year = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[year] = text[start:end]
    return out


def _sec_simple_all_offered(name: str, year: int, allocation: str, notes: list[str] | None = None) -> dict:
    return {"name": name, "year": year, "pan": None, "applications": None, "groups": ["All"], "criteria": [],
            "max_distance": {"All": None}, "all_offered": ["All"], "non_preference_offers": None,
            "total_offers": None, "allocation": allocation, "notes": notes or []}


def _flat_criteria(block: str) -> tuple[list[dict], list[str]]:
    """Pulls out simple '<Label>: <N>' lines that appear before any Band/Feeder/Selective table, for the
    flat (non-banded) criteria common to several school shapes (EHCP, LAC, siblings, staff, specialist/
    aptitude places). Returns (criteria, notes-for-suppressed-<5-values)."""
    label_map = [
        (re.compile(r"Education\s+Health\s+Care\s+Plan|EHC\s*Plan|Special\s+Education(al)?\s+Needs", re.I),
         "Education, Health and Care Plan (EHCP)"),
        (re.compile(r"Looked\s+After\s+Children", re.I), "Looked after children"),
        (re.compile(r"Children\s+of\s+[Ss]taff", re.I), "Children of staff"),
        (re.compile(r"Children\s+with\s+siblings\s+at\s+the\s+school", re.I), "Siblings"),
        (re.compile(r"Specialist\s+Aptitude\s+Places\s+in\s+Art", re.I), "Specialist aptitude places (Art & Design)"),
        (re.compile(r"Specialist\s+Aptitude\s+Places\s+in\s+Modern\s+Foreign\s+Languages", re.I),
         "Specialist aptitude places (Modern Foreign Languages)"),
        (re.compile(r"Specialist\s+Aptitude\s+Places", re.I), "Specialist aptitude places"),
    ]
    criteria: list[dict] = []
    notes: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        label_txt, _, rest = line.partition(":")
        rest = rest.strip()
        if not rest or "Band" in label_txt or "Furthest" in label_txt or "Feeder" in label_txt:
            continue
        for rx, label in label_map:
            if rx.search(label_txt):
                val = _int(rest)
                if val is None and rest.startswith("<5"):
                    notes.append(f"{label}: {rest.split()[0]} (suppressed small number, not counted).")
                elif val is not None:
                    criteria.append({"label": label, "total": val})
                break
    return criteria, notes


def _parse_sec_band_full(name: str, year: int, block: str) -> dict:
    """2026-style: 'Remaining places allocated within bands as follows:' with every criterion (including
    distance) split A-E, distance given as 'N (Dm)' (N = places offered by distance that band, D = metres)."""
    criteria, sup_notes = _flat_criteria(block.split("Remaining places")[0])
    table_text = block.split("Remaining places allocated within bands as follows:")[-1]
    rows = []
    for raw_line in table_text.splitlines():
        line = raw_line.strip()
        m = re.match(r"^([A-E])\s{2,}(.+)$", line)
        if not m:
            continue
        cells = re.split(r"\s{2,}", m.group(2).strip())
        rows.append((m.group(1), cells))
    if not rows:
        raise SystemExit(f"wandsworth: no band rows parsed for {name} {year}")
    n_mid = len(rows[0][1]) - 1
    if n_mid == 3:
        labels = ["Looked after children", "Siblings", "Children of staff"]
    elif n_mid == 4:
        labels = ["Looked after children", "Exceptional medical/social need", "Siblings", "Children of staff"]
    else:
        raise SystemExit(f"wandsworth: unexpected band column count for {name} {year}: {n_mid}")
    groups = [f"Band {b}" for b, _ in rows]
    counts_by_label = {lbl: {} for lbl in labels}
    dist_counts: dict[str, int] = {}
    max_distance: dict[str, float | None] = {}
    for band, cells in rows:
        g = f"Band {band}"
        for lbl, cell in zip(labels, cells[:-1]):
            v = _int(cell)
            if v is not None:
                counts_by_label[lbl][g] = v
        dm = re.match(r"^(\d+)\s*\((\d[\d,]*)m\)$", cells[-1])
        if dm:
            dist_counts[g] = int(dm.group(1))
            max_distance[g] = common.miles(float(dm.group(2).replace(",", "")), from_unit="metres")
        else:
            max_distance[g] = None
    for lbl in labels:
        c = counts_by_label[lbl]
        if c:
            criteria.append({"label": lbl, "counts": c, "total": sum(c.values())})
    if dist_counts:
        criteria.append({"label": "Distance", "counts": dist_counts, "total": sum(dist_counts.values())})
    return {"name": name, "year": year, "pan": None, "applications": None, "groups": groups, "criteria": criteria,
            "max_distance": max_distance, "all_offered": [], "non_preference_offers": None, "total_offers": None,
            "allocation": "mixed", "notes": sup_notes}


def _parse_sec_band_distance_only(name: str, year: int, block: str) -> dict:
    """2022-2025 ("previous years") style: flat non-banded criteria totals, then a band table giving only
    two distance columns (national-offer-day, by-31-August) per band, no per-band criteria breakdown."""
    head, _, table_text = block.partition("Furthest Distance Offered within each band")
    criteria, sup_notes = _flat_criteria(head)
    max_distance: dict[str, float | None] = {}
    aug_notes = []
    for raw_line in table_text.splitlines():
        line = raw_line.strip()
        m = re.match(r"^([A-E])\s{1,}(\S+)\s+(\S+)\s*$", line)
        if not m:
            continue
        band, on_day, by_aug = m.groups()
        g = f"Band {band}"
        max_distance[g] = _metres_to_miles(on_day)
        aug_v = _metres_to_miles(by_aug)
        if aug_v is not None and max_distance[g] is not None and abs(aug_v - max_distance[g]) > 0.001:
            aug_notes.append(f"{g}: by 31 August this had extended to {by_aug.strip()}.")
    if not max_distance:
        raise SystemExit(f"wandsworth: no band-distance rows parsed for {name} {year}")
    groups = sorted(max_distance)
    return {"name": name, "year": year, "pan": None, "applications": None, "groups": groups, "criteria": criteria,
            "max_distance": max_distance, "all_offered": [], "non_preference_offers": None, "total_offers": None,
            "allocation": "mixed", "notes": sup_notes + aug_notes}


SCORE_SENTENCE_RE = re.compile(
    r"scoring standardised test (?:core|score) of (\d+(?:\.\d+)?) or above,?\s*(?:and those scoring "
    r"(\d+(?:\.\d+)?) living up to a distance of (\d[\d,]*) metres from the school,?\s*)?offered a place",
    re.I)


def _parse_sec_selective(name: str, year: int, block: str) -> dict:
    flat_block = " ".join(block.split())  # collapse line-wraps for the multi-line prose sentences below
    sel_m = re.search(r"Selective \(Ability\) Places Offered:\s*(\d+)", flat_block)
    selective_places = int(sel_m.group(1)) if sel_m else None
    sel_sentence_m = SCORE_SENTENCE_RE.search(flat_block)
    notes = []
    sel_max_distance = None
    sel_all_offered = False
    if sel_sentence_m:
        score, tie_score, tie_dist = sel_sentence_m.groups()
        if tie_dist:
            sel_max_distance = common.miles(float(tie_dist.replace(",", "")), from_unit="metres")
            notes.append(f"Selective: offered to all scoring {score} or above outright, and those scoring "
                        f"{tie_score} living up to {tie_dist}m from the school (this is a Wandsworth Year 6 "
                        f"Test score threshold, not a pure distance criterion; recorded here as the tie-break "
                        f"distance for the lowest qualifying score).")
        else:
            notes.append(f"Selective: offered to all scoring {score} or above (no distance tie-break needed "
                        f"this year).")
    non_sel_text = block.split("Non-selective (Open) Places:")[-1] if "Non-selective (Open) Places:" in block \
        else block.split("Non-selective")[-1]
    non_sel_all_offered, non_sel_aug_note = _classify_all_offered(non_sel_text)
    if non_sel_aug_note:
        notes.append("Non-selective: " + non_sel_aug_note)
    criteria, sup_notes = _flat_criteria(non_sel_text)
    other_m = re.search(r"Other children living closest to the school:\s*(\d+)\s*\(up to a distance of "
                        r"(\d[\d,]*)\s*metres from the school\)", " ".join(non_sel_text.split()))
    non_sel_max_distance = None
    if other_m:
        criteria.append({"label": "Other children living closest to the school", "total": int(other_m.group(1))})
        non_sel_max_distance = common.miles(float(other_m.group(2).replace(",", "")), from_unit="metres")
    groups = ["Selective", "Non-selective"]
    max_distance = {"Selective": sel_max_distance, "Non-selective": non_sel_max_distance}
    all_offered = (["Selective"] if sel_all_offered else []) + (["Non-selective"] if non_sel_all_offered else [])
    if selective_places is not None:
        criteria.append({"label": "Selective (ability) places offered", "total": selective_places})
    return {"name": name, "year": year, "pan": None, "applications": None, "groups": groups,
            "criteria": criteria, "max_distance": max_distance, "all_offered": all_offered,
            "non_preference_offers": None, "total_offers": None, "allocation": "selective",
            "notes": notes + sup_notes}


FEEDER_NAMES = ["Ark John Archer", "Belleville Wix", "Belleville", "Falconbrook", "Honeywell"]


def _parse_sec_feeder(name: str, year: int, block: str) -> dict:
    head, _, table_text = block.partition("Feeder School")
    criteria, sup_notes = _flat_criteria(head)
    table_text = table_text.split("\n", 1)[-1]  # drop the rest of the header line itself
    table_text, _, tail = table_text.partition("Other applicants:")
    counts: dict[str, int] = {}
    max_distance: dict[str, float | None] = {}
    all_offered: list[str] = []
    for raw_line in table_text.splitlines():
        line = raw_line.strip()
        matched = None
        for fname in FEEDER_NAMES:
            if line.startswith(fname):
                matched = fname
                rest = line[len(fname):].strip()
                break
        if matched is None:
            continue
        m = re.match(r"^(<5|\d+)\s*\(([^)]*)\)", rest)
        if not m:
            continue
        count_raw, paren = m.groups()
        n = _int(count_raw)
        if n is not None:
            counts[matched] = n
        if "all offered" in paren.lower():
            all_offered.append(matched)
            max_distance[matched] = None
        else:
            max_distance[matched] = _metres_to_miles(paren)
    other_notes = []
    tail = tail.strip()
    if tail:
        other_notes.append("Other (non-feeder) applicants: " + " ".join(tail.split())[:300])
    groups = FEEDER_NAMES
    for g in groups:
        max_distance.setdefault(g, None)
    if counts:
        criteria.append({"label": "Feeder school places offered", "counts": counts, "total": sum(counts.values())})
    notes = sup_notes + other_notes + [
        "This school prioritises named partner (\"feeder\") primary schools ahead of any other applicant; "
        "'groups' here are those feeder schools, each with its own distance cut-off, rather than ability/test "
        "bands.",
    ]
    return {"name": name, "year": year, "pan": None, "applications": None, "groups": groups, "criteria": criteria,
            "max_distance": max_distance, "all_offered": all_offered, "non_preference_offers": None,
            "total_offers": None, "allocation": "mixed", "notes": notes}


def _parse_sec_foundation(name: str, year: int, block: str) -> dict:
    foundation_text, _, open_text = block.partition("Open places:")
    foundation_text = foundation_text.split("Foundation Places:")[-1]

    def joined_lines(text: str) -> list[str]:
        lines: list[str] = []
        for raw in text.splitlines():
            s = raw.strip()
            if not s:
                continue
            if re.match(r"^[A-Z][a-zA-Z]", s) and ":" in s:
                lines.append(s)
            elif lines:
                lines[-1] += " " + s
        return lines

    def parse_section(text: str) -> tuple[list[dict], float | None, bool, list[str]]:
        criteria = []
        max_dist = None
        all_off = False
        notes = []
        for line in joined_lines(text):
            label, _, rest = line.partition(":")
            label, rest = label.strip(), rest.strip()
            if label.lower().startswith("furthest distance offered"):
                continue
            v = _int(rest)
            dist_m = METRES_RE.search(rest)
            if v is not None:
                criteria.append({"label": label, "total": v})
            if dist_m:
                if max_dist is None:
                    max_dist = _metres_to_miles(rest)
                notes.append(f"{label}: {rest}")
            elif "all offered" in rest.lower():
                all_off = True
                notes.append(f"{label}: {rest}")
        return criteria, max_dist, all_off, notes

    f_criteria, f_dist, f_all_offered, f_notes = parse_section(foundation_text)
    o_criteria, o_dist, o_all_offered, o_notes = parse_section(open_text)
    dist_m = re.search(r"Furthest distance offered \(in metres1?\) under proximity criterion:\s*(\d[\d,]*)m",
                       open_text)
    if dist_m:
        o_dist = common.miles(float(dist_m.group(1).replace(",", "")), from_unit="metres")
    groups = ["Foundation", "Open"]
    max_distance = {"Foundation": f_dist, "Open": o_dist}
    all_offered = (["Foundation"] if f_all_offered else []) + (["Open"] if o_all_offered else [])
    criteria = [{"label": f"Foundation: {c['label']}", "total": c["total"]} for c in f_criteria] + \
              [{"label": f"Open: {c['label']}", "total": c["total"]} for c in o_criteria]
    return {"name": name, "year": year, "pan": None, "applications": None, "groups": groups, "criteria": criteria,
            "max_distance": max_distance, "all_offered": all_offered, "non_preference_offers": None,
            "total_offers": None, "allocation": "faith_then_distance", "notes": f_notes + o_notes}


def _parse_sec_year(heading: str, year: int, block: str) -> dict:
    name = SEC_DISPLAY[heading]
    allocation = "faith_then_distance" if heading in FAITH_SEC else "distance"
    if "Selective (Ability)" in block:
        return _parse_sec_selective(name, year, block)
    if "Foundation Places" in block:
        return _parse_sec_foundation(name, year, block)
    if "Feeder School" in block:
        return _parse_sec_feeder(name, year, block)
    if "Remaining places allocated within bands as follows" in block:
        return _parse_sec_band_full(name, year, block)
    if "Furthest Distance Offered within each band" in block:
        return _parse_sec_band_distance_only(name, year, block)
    all_offered_flag, aug_note = _classify_all_offered(block)
    if all_offered_flag:
        return _sec_simple_all_offered(name, year, allocation)
    # a school with real (non-banded, non-selective, non-feeder) applications/criteria/distance data, e.g.
    # Harris Academy Battersea 2022
    criteria, sup_notes = _flat_criteria(block)
    dist_m = re.search(r"Furthest distance offered \(in metres1?\) under proximity criterion:\s*(\d[\d,]*)\s*m",
                       " ".join(block.split()))
    max_distance = common.miles(float(dist_m.group(1).replace(",", "")), from_unit="metres") if dist_m else None
    if aug_note:
        sup_notes = sup_notes + [aug_note]
    return {"name": name, "year": year, "pan": None, "applications": None, "groups": ["All"], "criteria": criteria,
            "max_distance": {"All": max_distance}, "all_offered": [], "non_preference_offers": None,
            "total_offers": None, "allocation": allocation, "notes": sup_notes}


def _parse_secondary() -> list[dict]:
    prev_path = common.fetch(LA_CODE, SEC_PREVIOUS_YEARS)
    prev_text = common.pdftotext(prev_path)
    prev_text = prev_text[prev_text.index("PAGE 2"):]
    prev_blocks = _split_school_blocks(prev_text, SEC_SCHOOL_NAMES)

    cur_path = common.fetch(LA_CODE, SEC_OFFERED_2026)
    cur_text = common.pdftotext(cur_path)
    cur_blocks = _split_school_blocks(cur_text, SEC_SCHOOL_NAMES)

    records: list[dict] = []
    for heading in SEC_SCHOOL_NAMES:
        school_text = prev_blocks[heading]
        for year, yblock in _split_year_blocks(school_text).items():
            records.append(_parse_sec_year(heading, year, yblock))
        cur_block = cur_blocks[heading].split("CONTINUED ON NEXT PAGE")[0]
        records.append(_parse_sec_year(heading, 2026, cur_block))
    return records


# --------------------------------------------------------------------------- primary

PRI_HEADING_RE = re.compile(r"^\s{0,8}([A-Z][A-Z’'.,()/ -]{2,70})\s*$", re.M)

PRI_HEADER_STOP_WORDS = ("Baptised", "Catholic", "Muslim", "Faith Places", "Foundation Places",
                         "Eastern Christian", "Anglican", "worship", "Islamic")

PRI_LABEL_MAP = [
    (re.compile(r"Looked\s+After", re.I), "Looked after children"),
    (re.compile(r"Exceptional", re.I), "Exceptional social/medical need"),
    (re.compile(r"Children\s+of\s+[Ss]taff|Children\s+of\s+staff", re.I), "Children of staff"),
    (re.compile(r"Priority\s+Area\s*1", re.I), "Priority Area 1"),
    (re.compile(r"Priority\s+Area\s*2", re.I), "Priority Area 2"),
    (re.compile(r"Siblings", re.I), "Siblings"),
    (re.compile(r"Priority\s+Area\b", re.I), "Priority Area"),
]


def _pri_split_blocks(text: str) -> list[tuple[str, str]]:
    heads = [m for m in PRI_HEADING_RE.finditer(text) if len(m.group(1).split()) >= 2]
    out = []
    for i, m in enumerate(heads):
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((m.group(1).strip(), text[start:end]))
    return out


def _pri_labels(header_text: str) -> list[str]:
    labels: list[tuple[int, str]] = []
    seen = set()
    for rx, label in PRI_LABEL_MAP:
        if label in seen:
            continue
        m = rx.search(header_text)
        if m:
            labels.append((m.start(), label))
            seen.add(label)
    labels.sort()
    return [l for _, l in labels]


def _parse_belleville_wix(name: str, year: int, block: str) -> dict:
    # Belleville Wix Academy publishes two data rows each year (Bilingual class, then English class); both
    # words also appear earlier in the table's own (wrapped) header ("Bilingual / English Class"), so the
    # DATA rows are found specifically: the Bilingual row is the one immediately preceded by the admission
    # number at the start of its line, and the English row starts a line with only whitespace before it.
    pan_line_m = re.search(r"(?m)^\s*(\d+)\s+Bilingual\s", block)
    eng_line_m = re.search(r"(?m)^[ \t]*English\s", block)
    if not pan_line_m or not eng_line_m:
        raise SystemExit(f"wandsworth: could not locate Belleville Wix Bilingual/English data rows for {year}")
    pan = int(pan_line_m.group(1))
    bi_text = block[pan_line_m.end(1):eng_line_m.start()]
    eng_text = block[eng_line_m.end():]
    def extract_row(raw_txt: str) -> tuple[int | None, float | None, bool, str]:
        """raw_txt is everything from just after the row's leading 'Bilingual'/'English' label to (roughly)
        the start of the next row. Some rows put an explanatory clause with its own embedded distance inside
        parentheses ahead of the row's real 'Furthest Distance Offered' value (e.g. '12 (up to a distance of
        710 metres from the school)   N/A'), so parenthetical text is stripped before looking for the row's
        real outcome marker (a bare distance, 'N/A', or 'all offered')."""
        if not raw_txt:
            return None, None, False, ""
        stripped = re.sub(r"\([^)]*\)", " ", raw_txt, flags=re.S)
        na_m = re.search(r"\bN/A\b", stripped)
        ao_m = re.search(r"\ball offered\b", stripped, re.I)
        dist_m = METRES_RE.search(stripped)
        markers = [x for x in (na_m, ao_m, dist_m) if x is not None]
        if not markers:
            pre, dist, all_off, note_end = stripped[:120], None, False, 120
        else:
            first = min(markers, key=lambda x: x.start())
            pre, note_end = stripped[:first.start()], first.end()
            if first is dist_m:
                dist, all_off = common.miles(float(dist_m.group(1).replace(",", "")), from_unit="metres"), False
            elif first is ao_m:
                dist, all_off = None, True
            else:
                dist, all_off = None, False
        nums = re.findall(r"\b(\d+)\b", pre)
        places = int(nums[-1]) if len(nums) >= 2 else None
        return places, dist, all_off, " ".join(stripped[:note_end].split())

    bi_places, bi_dist, bi_all, bi_raw = extract_row(bi_text)
    eng_places, eng_dist, eng_all, eng_raw = extract_row(eng_text)
    notes = [f"Belleville Wix Academy runs two parallel admission classes each year (Bilingual German-English "
            f"immersion, and English). Bilingual class: {bi_raw or 'not published'}. English class: "
            f"{eng_raw or 'not published'}. This record's max_distance is the larger (English-class) furthest "
            f"distance offered."]
    max_distance = eng_dist if eng_dist is not None else bi_dist
    all_offered = bi_all and eng_all
    criteria = []
    if bi_places is not None:
        criteria.append({"label": "Siblings (Bilingual class)", "total": bi_places})
    if eng_places is not None:
        criteria.append({"label": "Siblings (English class)", "total": eng_places})
    return {"name": name, "year": year, "pan": pan, "applications": None, "total_offers": None,
            "criteria": criteria, "max_distance": max_distance, "all_offered": all_offered,
            "non_preference_offers": None, "allocation": "distance", "notes": notes}


def _parse_pri_year(name: str, year: int, block: str) -> dict:
    if name.startswith("Belleville Wix"):
        return _parse_belleville_wix(name, year, block)
    if _is_all_offered(block):
        return {"name": name, "year": year, "pan": None, "applications": None, "total_offers": None,
                "criteria": [], "max_distance": None, "all_offered": True, "non_preference_offers": None,
                "allocation": "distance", "notes": []}
    lines = [l for l in block.splitlines() if l.strip()]
    data_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*\d+\s", line):
            data_idx = i
            break
    if data_idx is None:
        # no PAN found at all -- nothing usable published this year for this school
        return {"name": name, "year": year, "pan": None, "applications": None, "total_offers": None,
                "criteria": [], "max_distance": None, "all_offered": False, "non_preference_offers": None,
                "allocation": "distance",
                "notes": ["Could not identify a published admission-number/criteria row for this school this "
                          "year; see the source PDF directly."]}
    header_text = " ".join(lines[:data_idx])
    # everything from the data row to the next heading (already isolated as `block`'s tail) may include a
    # continuation row (e.g. no cases seen for non-Belleville-Wix schools, but stay defensive: only take
    # lines up to the first blank-separated gap or the block end)
    data_text = "\n".join(lines[data_idx:])
    row_line = lines[data_idx].strip()
    cells = re.split(r"\s{2,}", row_line)
    pan = _int(cells[0])
    notes: list[str] = []
    # distance: search the whole data_text (handles values that wrap across lines) for the last metres value
    dist_matches = list(METRES_RE.finditer(data_text))
    all_offered_criterion = "all offered" in data_text.lower() and not dist_matches
    max_distance = None
    if dist_matches:
        max_distance = common.miles(float(dist_matches[-1].group(1).replace(",", "")), from_unit="metres")
    criteria: list[dict] = []
    is_complex = any(w.lower() in header_text.lower() for w in PRI_HEADER_STOP_WORDS)
    if not is_complex and len(cells) >= 2:
        # chop the last cell (the distance column) off before labelling
        middle_cells = cells[1:-1] if len(cells) > 2 else []
        clean_header = header_text.split("Furthest Distance")[0].split("Furthest distance")[0]
        labels = _pri_labels(clean_header)
        if labels and len(labels) == len(middle_cells):
            for label, cell in zip(labels, middle_cells):
                v = _int(cell)
                if v is not None:
                    criteria.append({"label": label, "total": v})
                elif cell.strip() == "<5":
                    notes.append(f"{label}: <5 (suppressed small number, not counted).")
        elif middle_cells:
            notes.append("Published criteria breakdown (not machine-labelled): " +
                        " | ".join(f"{c.strip()}" for c in middle_cells) + f" -- headed: " +
                        " ".join(clean_header.split())[:200])
    elif is_complex and len(cells) >= 2:
        notes.append("Published breakdown (not machine-labelled -- faith/foundation-place criteria vary by "
                    "school): " + " ".join(row_line.split()) + " -- headed: " + " ".join(header_text.split())[:250])
    if all_offered_criterion and not criteria and not is_complex:
        notes.append("By the close of this criterion, all remaining applicants were offered a place without "
                    "the distance criterion being reached (see raw text).")
    return {"name": name, "year": year, "pan": pan, "applications": None, "total_offers": None,
            "criteria": criteria, "max_distance": max_distance, "all_offered": False,
            "non_preference_offers": None, "allocation": "distance", "notes": notes}


def _parse_primary() -> list[dict]:
    records: list[dict] = []
    for year, spec in PRI_OFFERED_DOCS.items():
        path = common.fetch(LA_CODE, spec)
        text = common.pdftotext(path)
        text = text.split("HOW PLACES WERE OFFERED AT EACH WANDSWORTH SCHOOL")[-1]
        for name, block in _pri_split_blocks(text):
            records.append(_parse_pri_year(_titlecase(name), year, block))
    return records


def _titlecase(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    small = {"of", "the", "and", "in"}
    words = name.split(" ")
    out = []
    for i, w in enumerate(words):
        core = w.strip("().,/'’")
        if not core:
            out.append(w)
            continue
        lw = core.lower()
        if lw in small and i != 0:
            cased = lw
        elif lw == "ce":
            cased = "CE"
        else:
            cased = core[:1].upper() + core[1:].lower()
        out.append(w.replace(core, cased))
    return " ".join(out)


def build() -> tuple[list[dict], list[dict]]:
    return _parse_secondary(), _parse_primary()
