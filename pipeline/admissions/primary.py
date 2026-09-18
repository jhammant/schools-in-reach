"""Parse "Applications and Offers at Hackney Primary Schools 2018-26".

Page families (identified from the page title):
  community_new  2023-2026 community schools: one row per school, every cell filled
  aa_new         2023-2026 voluntary aided schools and academies (no distances)
  community_mid  2021-2022 community schools: blank cells, "43 (0.38)" distance cells
  aa_summary     2021-2022 admitting-authority (AA) schools summary with an "Oversubscribed?" column
  aa_breakdown   2021-2022 per-school criteria boxes for oversubscribed AA schools
  community_old  2018-2020 oversubscribed community schools, one page per year
  all_old        2018-2020 "Schools who normally offer all applicants a place" (3 years per row)
  aa_old         2018-2020 one page per AA school with 2020/2019/2018 columns
"""

from __future__ import annotations

import re

import pdfplumber

from pdftools import Line, Word, as_float, as_int, build_regions, group_lines, is_number, nearest, page_words, segments

PAREN_DIST_RE = re.compile(r"^\((\d+(?:\.\d+)?)\)$")
YEAR_RE = re.compile(r"^20\d\d$")

COMMUNITY_CRITERIA = [
    ("ehcp", "Education, Health and Care Plan"),
    ("lac", "Looked after & previously looked after children"),
    ("cpp", "Children with a Child Protection Plan"),
    ("medsoc", "Medical/Social reasons"),
    ("sibling", "Children with siblings at the school"),
    ("staff", "Children of staff at the school"),
    ("distance", "Distance"),
]
TEACHERS_LABEL = "Children of teachers at the school"


class PrimaryParseError(ValueError):
    pass


def _record(name: str, year: int, page: int, kind: str, school_type: str | None) -> dict:
    return {"name": name, "year": year, "page": page, "kind": kind, "type": school_type, "pan": None,
            "applications": None, "total_offers": None, "criteria": [], "max_distance": None,
            "non_preference_offers": None, "allocations": None, "all_offered": None, "notes": [], "_flags": set()}


def _clean_name(words: list[Word]) -> tuple[str, set[str]]:
    text = " ".join(w.text for w in words)
    flags = set(re.findall(r"[*~^]", text))
    return re.sub(r"\s*[*~^]+", "", text).strip(), flags


def _classify(title: str, prev: str | None) -> tuple[str | None, int | None]:
    patterns = [
        ("community_new", r"community primary schools\s+for Reception admissions (20\d\d)\b"),
        ("aa_new", r"voluntary aided primary schools and academies\s+for Reception admissions (20\d\d)\b"),
        ("community_mid", r"Hackney Primary Schools\s+for reception class admissions (20\d\d)\b"),
        ("community_mid", r"^Offers at Community Schools .*Reception (20\d\d)\b"),
        ("aa_summary", r"^Offer Summary at Admitting Authority .*Reception (20\d\d)\b"),
        ("aa_breakdown", r"^Offer breakdown at oversubscribed AA Schools .*Reception (20\d\d)\b"),
        ("community_old", r"Offers in (20\d\d) at Hackney Community Schools"),
    ]
    for kind, pattern in patterns:
        m = re.search(pattern, title, re.I)
        if m:
            return kind, int(m.group(1))
    if "Schools who normally offer all applicants a place" in title:
        return "all_old", None
    if prev == "all_old" and "Number of places available" in title:
        return "all_old", None
    if "Admission to Reception Class to start in" in title:
        return "aa_old", None
    return None, None


def _apply_footnotes(records: list[dict], footnotes: list[str]) -> None:
    """Attach footnotes ("* Admissions capped ...") to rows carrying the same marker."""
    for note in footnotes:
        m = re.match(r"^(?:Note:\s*)?([*~^]+)\s*(.+)$", note.strip())
        if not m or m.group(2).startswith("Non Preference Offers are made"):
            continue
        marker, text = m.group(1)[0], m.group(2).strip()
        for rec in records:
            if marker in rec["_flags"]:
                rec["notes"].append(text)


# ---------------------------------------------------------------- 2023-2026

def _community_new(lines: list[Line], year: int, page: int) -> list[dict]:
    out, footnotes = [], []
    for line in lines:
        if line.text.startswith("*"):
            footnotes.append(line.text)
            continue
        nums = [w for w in line.words if is_number(w.text)]
        if len(nums) != 12:
            continue
        name, flags = _clean_name([w for w in line.words if w.x1 <= nums[0].x0])
        values = [as_float(w.text) for w in nums]
        rec = _record(name, year, page, "community_new", "Community")
        rec["_flags"] = flags
        rec["pan"], rec["applications"], rec["total_offers"] = (int(v) for v in values[:3])
        rec["criteria"] = [{"label": label, "total": int(v)} for (_, label), v in zip(COMMUNITY_CRITERIA, values[3:10])]
        rec["max_distance"] = values[10] if rec["total_offers"] else None
        rec["non_preference_offers"] = int(values[11])
        out.append(rec)
    return out, footnotes


def _aa_new(lines: list[Line], words: list[Word], year: int, page: int) -> list[dict]:
    type_hdr = next((w for w in words if w.text == "Type"), None)
    if type_hdr is None:
        raise PrimaryParseError(f"page {page}: no Type column")
    out, footnotes = [], []
    for line in lines:
        if line.text.startswith("*"):
            footnotes.append(line.text)
            continue
        nums = [w for w in line.words if is_number(w.text)]
        if len(nums) != 5:
            continue
        name, flags = _clean_name([w for w in line.words if w.x1 < type_hdr.x0 - 5])
        school_type = " ".join(w.text for w in line.words if w.x0 >= type_hdr.x0 - 5 and w.x1 <= nums[0].x0)
        values = [as_int(w.text) for w in nums]
        rec = _record(name, year, page, "aa_new", school_type or None)
        rec["_flags"] = flags
        rec["pan"], rec["applications"], rec["total_offers"] = values[:3]
        rec["criteria"] = [{"label": "Education, Health and Care Plan", "total": values[3]}]
        rec["non_preference_offers"] = values[4]
        out.append(rec)
    return out, footnotes


# ------------------------------------------------------- keyword-column tables

def _resolve_headers(words: list[Word], spec: list[tuple[str, str]], max_top: float) -> dict[str, float]:
    """Find the x-centre of each column header word. When a header word occurs
    more than once (e.g. "Offers"), take the occurrence lying between its
    neighbours in the spec order."""
    # Skip the page title band (top < 50pt): titles repeat words such as "Applications" and "Offers".
    candidates = {key: [w for w in words if w.text == text and 50 < w.top < max_top] for key, text in spec}
    centers: dict[str, float] = {}
    for key, _ in spec:
        if len(candidates[key]) == 1:
            centers[key] = candidates[key][0].cx
    keys = [k for k, _ in spec]
    for i, key in enumerate(keys):
        if key in centers:
            continue
        lo = max((centers[k] for k in keys[:i] if k in centers), default=float("-inf"))
        hi = min((centers[k] for k in keys[i + 1:] if k in centers), default=float("inf"))
        between = [w for w in candidates[key] if lo < w.cx < hi]
        if len(between) != 1:
            raise PrimaryParseError(f"cannot locate column header {dict(spec)[key]!r}")
        centers[key] = between[0].cx
    return centers


def _keyword_rows(words: list[Word], lines: list[Line], spec: list[tuple[str, str]], year: int, page: int,
                  kind: str, school_type: str | None, name_gap: float = 20.0) -> tuple[list[dict], list[str]]:
    first_row = next(l for l in lines if sum(is_number(w.text) and not YEAR_RE.match(w.text) for w in l.words) >= 2)
    centers = _resolve_headers(words, spec, first_row.top)
    keys = list(centers)
    xs = [centers[k] for k in keys]
    name_limit = min(xs) - name_gap
    records, footnotes = [], []
    in_notes = False
    for line in lines:
        if line.top < first_row.top - 2:
            continue
        if in_notes or line.text.startswith(("Notes", "Note:", "Data as at")):
            in_notes = True
            footnotes.append(line.text)
            continue
        if re.match(r"^[*~^]\s", line.text):
            footnotes.append(line.text)
            continue
        name_words = [w for w in line.words if w.x1 < name_limit]
        value_words = [w for w in line.words if w.x1 >= name_limit]
        if not name_words or not value_words:
            continue
        name, flags = _clean_name(name_words)
        rec = _record(name, year, page, kind, school_type)
        rec["_flags"] = flags
        cells: dict[str, str] = {}
        for w in value_words:
            m = PAREN_DIST_RE.match(w.text)
            if m:
                rec["max_distance"] = float(m.group(1))
                continue
            idx, dist = nearest(w.cx, xs)
            if dist > 25:
                raise PrimaryParseError(f"page {page} {name}: value {w.text!r} is {dist:.0f}pt from any column")
            if keys[idx] in cells:
                raise PrimaryParseError(f"page {page} {name}: two values in column {keys[idx]}")
            cells[keys[idx]] = w.text
            rec["_flags"] |= set(re.findall(r"[*~^]", w.text))
        rec["_cells"] = cells
        records.append(rec)
    return records, footnotes


def _fill_counts(rec: dict, staff_label: str, with_offers: bool) -> None:
    cells = rec.pop("_cells")
    rec["pan"] = as_int(cells["places"]) if "places" in cells else None
    rec["applications"] = as_int(cells["applications"]) if "applications" in cells else None
    if with_offers and "offers" in cells:
        rec["total_offers"] = as_int(cells["offers"])
    if "allocations" in cells:
        rec["allocations"] = as_int(cells["allocations"])
    rec["criteria"] = [{"label": staff_label if key == "staff" else label, "total": as_int(cells.get(key, "0"))}
                       for key, label in COMMUNITY_CRITERIA]


COMMUNITY_SPEC_MID = [("places", "available"), ("applications", "Applications"), ("offers", "Offers"),
                      ("ehcp", "Education,"), ("lac", "previously"), ("cpp", "Protection"), ("medsoc", "Medical/"),
                      ("sibling", "siblings"), ("staff", "teachers"), ("distance", "(distance"),
                      ("allocations", "Allocations^")]
COMMUNITY_SPEC_OLD = [("places", "available"), ("applications", "Applications"), ("ehcp", "Education,"),
                      ("lac", "previously"), ("cpp", "Protection"), ("medsoc", "Medical/"), ("sibling", "siblings"),
                      ("staff", "teachers"), ("distance", "(distance")]
AA_SUMMARY_SPEC = [("places", "available"), ("applications", "Applications"), ("offers", "Offers"),
                   ("ehcp", "Education,"), ("oversubscribed", "Oversubscribed?"), ("allocations", "Allocations^")]


def _community_mid(words, lines, year, page) -> list[dict]:
    records, footnotes = _keyword_rows(words, lines, COMMUNITY_SPEC_MID, year, page, "community_mid", "Community")
    for rec in records:
        _fill_counts(rec, TEACHERS_LABEL, with_offers=True)
        # Only oversubscribed schools show "(distance of last child offered)".
        rec["all_offered"] = rec["max_distance"] is None
    return records, footnotes


def _community_old(words, lines, year, page) -> list[dict]:
    records, footnotes = _keyword_rows(words, lines, COMMUNITY_SPEC_OLD, year, page, "community_old", "Community")
    for rec in records:
        _fill_counts(rec, TEACHERS_LABEL, with_offers=False)
        rec["all_offered"] = False  # these pages list only schools that could not offer every applicant
    return records, footnotes


def _aa_summary(words, lines, year, page) -> list[dict]:
    records, footnotes = _keyword_rows(words, lines, AA_SUMMARY_SPEC, year, page, "aa_summary", None, name_gap=25)
    for rec in records:
        cells = rec.pop("_cells")
        rec["pan"] = as_int(cells.get("places", ""))
        rec["applications"] = as_int(cells.get("applications", ""))
        rec["total_offers"] = as_int(cells.get("offers", ""))
        rec["allocations"] = as_int(cells.get("allocations", ""))
        rec["criteria"] = [{"label": "Education, Health and Care Plan", "total": as_int(cells.get("ehcp", "0"))}]
        rec["all_offered"] = cells.get("oversubscribed", "").lower() != "yes"
    return records, footnotes


def _aa_breakdown(page, words, lines, year, pno) -> list[dict]:
    headers = [seg for line in lines for seg in segments(line) if seg.text.startswith("Offers at ")]
    out = []
    for header, region in zip(headers, build_regions(headers, page.width, page.height)):
        name = header.text[len("Offers at "):].strip()
        rec = _record(name, year, pno, "aa_breakdown", None)
        for line in group_lines(region.words(words)):
            if abs(line.cy - header.cy) < 3 or line.text.startswith(("Admission Criteria", "Page ")):
                continue
            last = line.words[-1]
            value = last.text if is_number(last.text) and len(line.words) > 1 else None
            label = " ".join(w.text for w in (line.words[:-1] if value is not None else line.words))
            if label.startswith("Maximum Distance"):
                rec["max_distance"] = as_float(value) if value else None
            elif label == "Total Offers":
                rec["total_offers"] = as_int(value) if value else None
            elif re.match(r"Total (On-time )?Applications", label):
                rec["applications"] = as_int(value) if value else None
            else:
                rec["criteria"].append({"label": label, "total": as_int(value) if value else 0})
        rec["all_offered"] = False
        out.append(rec)
    return out, []


# ---------------------------------------------------------------- 2018-2020

def _all_old(words: list[Word], lines: list[Line], page: int) -> list[dict]:
    year_words = sorted((w for w in words if YEAR_RE.match(w.text) and w.top < 140), key=lambda w: w.cx)
    if len(year_words) != 9:
        raise PrimaryParseError(f"page {page}: expected 9 year headers, found {len(year_words)}")
    groups = [year_words[0:3], year_words[3:6], year_words[6:9]]
    col_x = [w.cx for w in year_words]
    name_limit = col_x[0] - 25
    header_bottom = year_words[0].bottom
    body = [w for w in words if w.top > header_bottom + 2]
    anchors = [l for l in group_lines([w for w in body if w.x1 >= name_limit and as_int(w.text) is not None])]
    rows = [{"cy": a.cy, "name_words": [], "cells": {}} for a in anchors]
    if not rows:
        return []
    for w in body:
        row = min(rows, key=lambda r: abs(r["cy"] - w.cy))
        if w.x1 < name_limit:
            if abs(row["cy"] - w.cy) <= 9:
                row["name_words"].append(w)
            continue
        if as_int(w.text) is not None:
            idx, _ = nearest(w.cx, col_x)
            row["cells"].setdefault(idx, w.text)
        elif w.text in ("Yes", "No"):
            idx, dist = nearest(w.cx, col_x[6:])
            row["cells"].setdefault(6 + idx, w.text)
    out = []
    for row in rows:
        name, flags = _clean_name(sorted(row["name_words"], key=lambda w: (round(w.cy), w.x0)))
        for k in range(3):
            year = int(groups[0][k].text)
            if int(groups[1][k].text) != year or int(groups[2][k].text) != year:
                raise PrimaryParseError(f"page {page}: year columns not aligned")
            rec = _record(name, year, page, "all_old", None)
            rec["pan"] = as_int(row["cells"].get(k, ""))
            rec["applications"] = as_int(row["cells"].get(3 + k, ""))
            able = row["cells"].get(6 + k)
            if able is None:
                raise PrimaryParseError(f"page {page} {name} {year}: no Yes/No")
            rec["all_offered"] = able == "Yes"
            out.append(rec)
    return out, []


def _aa_old(words: list[Word], lines: list[Line], page: int) -> list[dict]:
    title = next(l for l in lines if l.top > 30)
    school = title.text.strip()
    hdr_line = next(l for l in lines if l.text.startswith("Admission Criteria"))
    year_words = [w for w in hdr_line.words if YEAR_RE.match(w.text)]
    years = [int(w.text) for w in year_words]
    col_x = [w.cx for w in year_words]
    name_limit = min(col_x) - 30
    body = [w for w in words if w.top > hdr_line.words[0].bottom + 1]
    label_lines = group_lines([w for w in body if w.x1 < name_limit])
    table_end = next((l.cy for l in label_lines if l.text.startswith("Total Applica")), None)
    if table_end is None:
        raise PrimaryParseError(f"page {page} {school}: no applications row")
    rows = [{"label": l.text, "cy": l.cy, "cells": {}} for l in label_lines if l.cy <= table_end + 2]
    notes = [l.text for l in group_lines([w for w in body if w.cy > table_end + 6])]
    text_columns: set[int] = set()
    numbers = []
    for w in body:
        if w.x1 < name_limit or w.cy > table_end + 6:
            continue
        idx, _ = nearest(w.cx, col_x)
        if is_number(w.text) or w.text == "N/A":
            numbers.append((idx, w))
        else:
            text_columns.add(idx)
    for idx, w in numbers:
        if idx in text_columns and YEAR_RE.match(w.text):
            continue  # "Sept 2019" inside the "All on-time applicants ... were offered" note
        row = min(rows, key=lambda r: abs(r["cy"] - w.cy))
        if abs(row["cy"] - w.cy) > 9:
            raise PrimaryParseError(f"page {page} {school}: value {w.text} not near a row")
        if idx in row["cells"]:
            raise PrimaryParseError(f"page {page} {school}: two values in {row['label']} {years[idx]}")
        row["cells"][idx] = w.text
    out = []
    for idx, year in enumerate(years):
        rec = _record(school, year, page, "aa_old", None)
        rec["all_offered"] = idx in text_columns
        for row in rows:
            label, raw = row["label"], row["cells"].get(idx)
            if label.startswith("Maximum Distance"):
                rec["max_distance"] = as_float(raw) if raw else None
            elif label == "Total Offers":
                rec["total_offers"] = as_int(raw) if raw else None
            elif label.startswith("Total Applica"):
                rec["applications"] = as_int(raw) if raw else None
            elif not rec["all_offered"] and raw != "N/A":  # N/A: criterion not used that year
                rec["criteria"].append({"label": label, "total": as_int(raw) if raw else 0})
        if rec["all_offered"]:
            rec["notes"].append(f"All on-time applicants seeking a place for September {year} were offered.")
        rec["notes"].extend(notes)
        out.append(rec)
    return out, []


def parse(pdf_path) -> list[dict]:
    records: list[dict] = []
    footnotes: dict[tuple[str, int | None], list[str]] = {}
    prev_kind = None
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            words = page_words(page)
            nav = {id(w) for line in group_lines(words) if re.fullmatch(r"(Back to index\s*)+", line.text)
                   for w in line.words}
            words = [w for w in words if id(w) not in nav]
            lines = group_lines(words)
            if not lines:
                continue
            title = " ".join(l.text for l in lines[:6] if l.top < 110)
            kind, year = _classify(title, prev_kind)
            handlers = {
                "community_new": lambda: _community_new(lines, year, pno),
                "aa_new": lambda: _aa_new(lines, words, year, pno),
                "community_mid": lambda: _community_mid(words, lines, year, pno),
                "aa_summary": lambda: _aa_summary(words, lines, year, pno),
                "aa_breakdown": lambda: _aa_breakdown(page, words, lines, year, pno),
                "community_old": lambda: _community_old(words, lines, year, pno),
                "all_old": lambda: _all_old(words, lines, pno),
                "aa_old": lambda: _aa_old(words, lines, pno),
            }
            if kind in handlers:
                page_records, page_notes = handlers[kind]()
                records += page_records
                footnotes.setdefault((kind, year), []).extend(page_notes)
            prev_kind = kind
    # Footnotes can sit on the second page of a two-page table, so apply them per (table, year).
    for (kind, year), notes in footnotes.items():
        _apply_footnotes([r for r in records if r["kind"] == kind and r["year"] == year], notes)
    for rec in records:
        rec.pop("_flags", None)
    return records
