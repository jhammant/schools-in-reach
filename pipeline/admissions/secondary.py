"""Parse "Applications and Offers at Hackney Secondary Schools 2018-26".

Two page families:
  * 2021-2026: one or more "Offers at <School> (PAN: n Applications: n)" blocks
    per page, laid out in columns, plus (2022) a few summary-only boxes.
  * 2018-2020: one page per school with "Admission to Year 7 in September YYYY"
    blocks, sometimes two years side by side.
Both share the same inner table shape (criteria rows x band columns), handled
by parse_table().
"""

from __future__ import annotations

import re

import pdfplumber

from pdftools import (Line, Word, as_float, as_int, build_regions, group_lines,
                      nearest, page_words, segments)

YEAR_TITLE_RE = re.compile(r"(?:admissions\s+|Schools\s*-\s*)(20\d\d)\b")
OFFERS_AT_RE = re.compile(
    r"^Offers at (?P<name>.+?)\s*\((?:PAN:\s*(?P<pan>\d+)\s*)?(?:Applications:\s*(?P<apps>\d+))?\)?\s*$")
SUMMARY_NAME_RE = re.compile(r"^(?:The )?[A-Z][A-Za-z' ]+ (?:School|Academy)$")
ADMISSION_HDR_RE = re.compile(r"^Admission to Year 7 in September (20\d\d)")
DATA_START_RE = re.compile(r"^(Education|EHC Plan|Offers\*)")
META_RE = re.compile(r"^(Admission to Year 7|Total (on-time )?applications|Admissions? number|Number admitted|Offers:)",
                     re.I)
PAGE_NOISE_RE = re.compile(
    r"^(Non Preference Offers are made|NOTE: Schools not listed|Data as at|/$|Page \d+$)")
# Page footers that span several table columns; removed before splitting a page into blocks.
FOOTER_RE = re.compile(r"Non Preference Offers are made at schools|Schools not listed were able to offer")
FAITH_RE = re.compile(r"Catholic|Christian|Faith|Orthodox|Jewish|Catechumen|Practising|Parish", re.I)
BAND_LETTER_RE = re.compile(r"^[A-E]$")
SUBZONES = {"Inner", "Middle", "Outer"}
SUPERGROUPS = {"Foundation", "Community"}


class TableError(ValueError):
    pass


def _columns(header_lines: list[Line]) -> tuple[list[tuple[str, float]], float | None]:
    words = [w for line in header_lines for w in line.words]
    bands: list[tuple[str, float]] = []
    for li, line in enumerate(header_lines):
        for i, w in enumerate(line.words):
            if w.text != "Band":
                continue
            nxt = line.words[i + 1] if i + 1 < len(line.words) else None
            if nxt is not None and BAND_LETTER_RE.match(nxt.text) and nxt.x0 - w.x1 < 8:
                bands.append((nxt.text, (w.x0 + nxt.x1) / 2))
                continue
            below = [x for l2 in header_lines[li + 1:] for x in l2.words if BAND_LETTER_RE.match(x.text)]
            best = min(below, key=lambda x: abs(x.cx - w.cx), default=None)
            if best is None or abs(best.cx - w.cx) > 15:
                raise TableError(f"band header without letter near x={w.cx:.0f}")
            bands.append((best.text, w.cx))
    bands.sort(key=lambda b: b[1])
    subs = sorted((w for w in words if w.text in SUBZONES), key=lambda w: w.cx)
    supers = sorted((w for w in words if w.text in SUPERGROUPS), key=lambda w: w.cx)
    totals = [w for w in words if w.text == "Total"]
    total_cx = max(totals, key=lambda w: w.cx).cx if totals else None

    if subs:
        if len(subs) == len(bands):  # "Band A Band A ..." over "Inner Outer ..."
            cols = [(f"{b} {s.text}", s.cx) for (b, _), s in zip(bands, subs)]
        elif bands and len(subs) % len(bands) == 0:
            k = len(subs) // len(bands)
            cols = [(f"{bands[i // k][0]} {s.text}", s.cx) for i, s in enumerate(subs)]
        else:
            raise TableError(f"{len(subs)} zone columns do not divide {len(bands)} bands")
    elif supers and bands and len(bands) % len(supers) == 0:
        k = len(bands) // len(supers)
        cols = [(f"{supers[i // k].text} {b}", cx) for i, (b, cx) in enumerate(bands)]
    else:
        cols = bands
    return cols, total_cx


def parse_table(lines: list[Line]) -> dict | None:
    """Parse a criteria x band table. Returns None when the block has no table."""
    lines = [l for l in lines if not PAGE_NOISE_RE.match(l.text)]
    start = next((i for i, l in enumerate(lines) if DATA_START_RE.match(l.text)), None)
    if start is None:
        return None
    header_lines = [l for l in lines[:start] if not META_RE.match(l.text)]
    cols, total_cx = _columns(header_lines)
    unbanded = not cols
    if unbanded:
        if total_cx is None:
            raise TableError("table without band or total columns")
        cols, total_cx = [("All", total_cx)], None
    centers = [c for _, c in cols] + ([total_cx] if total_cx is not None else [])
    ordered = sorted(centers)
    spacing = min((b - a for a, b in zip(ordered, ordered[1:])), default=30.0)
    boundary = ordered[0] - max(12.0, 0.6 * spacing)
    tolerance = max(18.0, 0.75 * spacing)
    keys = [c for c, _ in cols] + (["__total__"] if total_cx is not None else [])

    rows: list[dict] = []
    orphan_values: list[Word] = []
    notes: list[str] = []
    after_total = False
    for line in lines[start:]:
        label_words = [w for w in line.words if w.cx < boundary]
        value_words = [w for w in line.words if w.cx >= boundary]
        text = line.text
        if after_total or (label_words and label_words[0].text.startswith("*")):
            if text.startswith("*") or not notes:
                notes.append(text)
            else:
                notes[-1] += " " + text
            continue
        if not label_words:
            orphan_values.extend(value_words)
            continue
        label = " ".join(w.text for w in label_words)
        rows.append({"label": label, "cy": line.cy, "values": list(value_words)})
        if label in ("Total", "Total Offers"):
            after_total = True
    for w in orphan_values:  # values printed slightly off their label's baseline
        target = min(rows, key=lambda r: abs(r["cy"] - w.cy))
        if abs(target["cy"] - w.cy) > 8:
            raise TableError(f"value {w.text!r} not near any row")
        target["values"].append(w)

    warnings: list[str] = []

    def cells(row: dict) -> dict[str, str]:
        out: dict[str, str] = {}
        for w in row["values"]:
            idx, dist = nearest(w.cx, centers)
            if dist > tolerance:
                raise TableError(f"value {w.text!r} in row {row['label']!r} is {dist:.0f}pt from any column")
            key = keys[idx]
            if key in out:
                raise TableError(f"two values for column {key!r} in row {row['label']!r}")
            out[key] = w.text
        return out

    groups = [c for c, _ in cols]
    record: dict = {"groups": groups, "criteria": [], "max_distance": None, "all_offered": [],
                    "non_preference_offers": None, "total_offers": None, "notes": notes, "_warnings": warnings}
    band_totals: dict[str, int] = {}
    breakdown_withheld = False
    for row in rows:
        label = re.sub(r"\s+", " ", row["label"]).strip()
        c = cells(row)
        if label.startswith("Maximum Distance"):
            record["max_distance"] = {g: None for g in groups}
            for key, raw in c.items():
                if key == "__total__":
                    raise TableError(f"max distance value {raw!r} in total column")
                value = as_float(raw)
                if value is not None:
                    record["max_distance"][key] = value
                elif "*" in raw or raw.upper().startswith("N/A"):
                    record["all_offered"].append(key)
                else:
                    raise TableError(f"unreadable max distance {raw!r}")
        elif label.startswith("Non Preference Offer"):
            nums = [as_int(v) for v in c.values() if as_int(v) is not None]
            record["non_preference_offers"] = nums[0] if nums else None
        elif label in ("Total", "Total Offers", "Offers*"):
            for key, raw in c.items():
                n = as_int(raw)
                if n is None:
                    raise TableError(f"unreadable total {raw!r}")
                if key == "__total__":
                    record["total_offers"] = n
                else:
                    band_totals[key] = n
            if label == "Offers*":
                breakdown_withheld = True
        else:
            counts = {}
            for key, raw in c.items():
                n = as_int(raw)
                if n is None:
                    raise TableError(f"unreadable count {raw!r} in {label!r}")
                counts[key] = n
            total = counts.pop("__total__", None)
            if unbanded:
                total = counts.get("All", 0)
            elif total is None:
                total = sum(counts.values())
            record["criteria"].append({"label": label, "counts": counts, "total": total})

    if unbanded:
        record["total_offers"] = band_totals.get("All")
    elif band_totals:
        band_sum = sum(band_totals.values())
        if record["total_offers"] is None:
            record["total_offers"] = band_sum
        elif record["total_offers"] < band_sum - 1:
            record["notes"].append(
                f"Published total cell reads {record['total_offers']} but band totals sum to {band_sum} "
                "(text clipped in the source PDF); using the band sum.")
            record["total_offers"] = band_sum
        record["band_totals"] = band_totals
    if breakdown_withheld:
        record["notes"].append("Breakdown of offers by admission criteria not published "
                               "(contact the school directly).")

    # Consistency checks: criteria counts per band should add up to band totals.
    if band_totals and record["criteria"]:
        mismatched = []
        for g in groups:
            s = sum(cr["counts"].get(g, 0) for cr in record["criteria"])
            if unbanded:
                s += record["non_preference_offers"] or 0
            if g in band_totals and s != band_totals[g]:
                warnings.append(f"band {g}: criteria sum {s} != total {band_totals[g]}")
                mismatched.append(g)
        if mismatched:
            record["notes"].append("In the source table the criteria counts do not add up to the published "
                                   f"total for: {', '.join(mismatched)}.")
    return record


def _allocation(record: dict) -> str | None:
    labels = [c["label"] for c in record.get("criteria", [])]
    if any(l.startswith("Random") for l in labels):
        return "random_by_zone"
    if any(g.startswith("Foundation") for g in record.get("groups", [])):
        return "mixed"
    if any(FAITH_RE.search(l) for l in labels):
        return "faith_then_distance"
    if record.get("max_distance") or any(l == "Distance" for l in labels):
        return "distance"
    return None


def _empty_record(name: str, year: int, page: int) -> dict:
    return {"name": name, "year": year, "page": page, "pan": None, "applications": None, "groups": [],
            "criteria": [], "max_distance": None, "all_offered": [], "non_preference_offers": None,
            "total_offers": None, "allocation": None, "notes": [], "_warnings": []}


def _summary_block(name: str, year: int, page: int, words: list[Word], header: Line) -> dict:
    body = [w for w in words if w.cy > header.cy + 3]
    labels = [w for w in body if w.text.lower() in ("applications", "offers")]
    rec = _empty_record(name, year, page)
    for num in (w for w in body if as_int(w.text) is not None):
        same_line = [l for l in labels if abs(l.cy - num.cy) < 3 and l.x1 <= num.x0]
        if same_line:
            label = max(same_line, key=lambda l: l.x1)
        else:
            above = [l for l in labels if l.cy < num.cy]
            label = min(above, key=lambda l: abs(l.cx - num.cx), default=None)
        if label is None:
            raise TableError(f"summary number {num.text} for {name} has no label")
        key = "applications" if label.text.lower() == "applications" else "total_offers"
        rec[key] = as_int(num.text)
    rec["notes"].append("Only total applications and total offers were published for this year.")
    return rec


def _new_page(page, pno: int, words: list[Word], lines: list[Line], year: int) -> list[dict]:
    headers: list[tuple[str, Line]] = []
    for line in lines:
        if line.top < 50:
            continue
        for seg in segments(line):
            if seg.text.startswith("Offers at "):
                headers.append(("offers", seg))
            elif SUMMARY_NAME_RE.match(seg.text):
                headers.append(("summary", seg))
    regions = build_regions([h for _, h in headers], page.width, page.height)
    out = []
    for (kind, header), region in zip(headers, regions):
        rw = region.words(words)
        if kind == "summary":
            out.append(_summary_block(header.text, year, pno + 1, rw, header))
            continue
        m = OFFERS_AT_RE.match(header.text)
        if not m:
            raise TableError(f"page {pno + 1}: unreadable block header {header.text!r}")
        rec = _empty_record(m.group("name").strip(), year, pno + 1)
        rec["pan"] = int(m.group("pan")) if m.group("pan") else None
        rec["applications"] = int(m.group("apps")) if m.group("apps") else None
        body = group_lines([w for w in rw if abs(w.cy - header.cy) > 3])
        try:
            table = parse_table(body)
        except TableError as exc:
            raise TableError(f"page {pno + 1} {rec['name']} {year}: {exc}") from exc
        if table is None:
            raise TableError(f"page {pno + 1} {rec['name']} {year}: no table found")
        rec.update(table)
        out.append(rec)
    return out


def _old_page(page, pno: int, words: list[Word], lines: list[Line], school: str | None) -> tuple[list[dict], str]:
    first = lines[0]
    if not ADMISSION_HDR_RE.match(first.text):
        school = first.text.strip()
    if not school:
        raise TableError(f"page {pno + 1}: no school name")
    headers = [seg for line in lines for seg in segments(line) if ADMISSION_HDR_RE.match(seg.text)]
    first_top = min(h.top for h in headers)
    page_notes = [l.text for l in lines[1:] if l.top < first_top - 3 and l is not first]
    regions = build_regions(headers, page.width, page.height)
    out = []
    for header, region in zip(headers, regions):
        year = int(ADMISSION_HDR_RE.match(header.text).group(1))
        rec = _empty_record(school, year, pno + 1)
        rlines = group_lines(region.words(words))
        text = "\n".join(l.text for l in rlines)
        m = re.search(r"Total (?:on-time )?applications\s*:\s*(\d+)", text, re.I)
        rec["applications"] = int(m.group(1)) if m else None
        m = re.search(r"Admissions? number\s*:\s*(\d+)", text, re.I)
        rec["pan"] = int(m.group(1)) if m else None
        for note in page_notes:
            years = {int(y) for y in re.findall(r"20\d\d", note)}
            if not years or year in years:
                rec["notes"].append(note)
        body = [l for l in rlines if abs(l.cy - header.cy) > 3]
        try:
            table = parse_table(body)
        except TableError as exc:
            raise TableError(f"page {pno + 1} {school} {year}: {exc}") from exc
        if table is not None:
            table["notes"] = rec["notes"] + table["notes"]
            rec.update(table)
        else:
            m = re.search(r"Number admitted\s*:\s*(\d+)", text, re.I)
            rec["total_offers"] = int(m.group(1)) if m else None
            if re.search(r"All on-time applicants were offered a place", text, re.I):
                rec["all_offered"] = ["All"]
            paragraph: list[str] = []
            for l in body:
                if META_RE.match(l.text) or l.text in ("Note",) or PAGE_NOISE_RE.match(l.text):
                    if paragraph:
                        rec["notes"].append(" ".join(paragraph))
                        paragraph = []
                    continue
                paragraph.append(l.text.strip("() "))
            if paragraph:
                rec["notes"].append(" ".join(paragraph))
            if rec["all_offered"]:
                rec["notes"].append("All on-time applicants were offered a place.")
        out.append(rec)
    return out, school


def parse(pdf_path) -> list[dict]:
    records: list[dict] = []
    school: str | None = None
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages):
            words = page_words(page)
            footer_words = {id(w) for line in group_lines(words) if FOOTER_RE.search(line.text) for w in line.words}
            words = [w for w in words if id(w) not in footer_words]
            lines = group_lines(words)
            if not lines:
                continue
            if any(ADMISSION_HDR_RE.match(seg.text) for line in lines for seg in segments(line)):
                recs, school = _old_page(page, pno, words, lines, school)
                records.extend(recs)
                continue
            title = " ".join(l.text for l in lines if l.top < 60)
            m = YEAR_TITLE_RE.search(title)
            if not m:
                continue  # cover / index page
            records.extend(_new_page(page, pno, words, lines, int(m.group(1))))
    for rec in records:
        rec["allocation"] = _allocation(rec)
    return records
