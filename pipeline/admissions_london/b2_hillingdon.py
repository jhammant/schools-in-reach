"""Hillingdon (LA 312): parse the council's "Secondary allocation data" (Year 7,
2021-2025) and "September <year> allocation data" (Reception, 2021-2025) PDFs.

Secondary: one row per school with the number of offers that could be made
(PAN including any bulge places), SEN placements (2023 on), places still
available after national offer day and the "furthest distance offered" in
metres. Codes: N/A (U) = undersubscribed, everyone who applied was offered;
N/A (F) = faith school, no distance published; N/A (B) = Swakeleys, which
admits by ability banding (NVRT). The 2024 and 2025 editions are image-only
PDFs (a spreadsheet screenshot with no text layer); their 18 rows were
transcribed by hand from the rendered page below and are checked against the
printed column totals.

Reception: PAN, on-time offers, places available, the furthest distance offered
(metres, excluding sibling offers) for the current and the previous year, and a
numeric code for the criterion the last child was offered under ("Contact
School" for own-admission-authority schools). Each edition's previous-year
column is used only for 2020, which has no edition of its own online; for other
years the edition for that year is used and the overlap is cross-checked.
"""

from __future__ import annotations

import re

import b2_common as bc
import pdftools

LA_CODE = "312"
LA_NAME = "Hillingdon"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {}

BASE = "https://www.hillingdon.gov.uk/media/"
SECONDARY_DOCS = {
    2021: {"cache": "secondary-2021.pdf", "url": BASE + "7409/Secondary-allocation-data-2021/pdf/"
                                                        "15Secondary_Allocation_Data_2021.pdf"},
    2022: {"cache": "secondary-2022.pdf", "url": BASE + "8518/Secondary-allocation-data-2022/pdf/"
                                                        "93Secondary_allocation_data_2022.pdf"},
    2023: {"cache": "secondary-2023.pdf", "url": BASE + "11188/Secondary-allocation-data-2023/pdf/"
                                                        "emSecondary_allocation_data_2023_1.pdf"},
    2024: {"cache": "secondary-2024.pdf", "url": BASE + "13608/Secondary-allocation-data-2024/pdf/"
                                                        "mjSecondary-allocation-data-2024.pdf"},
    2025: {"cache": "secondary-2025.pdf", "url": BASE + "15908/Secondary-allocation-data-2025/pdf/"
                                                        "g0Secondary_allocations_2025.pdf"},
}
PRIMARY_DOCS = {
    2021: {"cache": "reception-2021.pdf", "url": BASE + "8186/September-2021-allocation-data/pdf/"
                                                        "n8Reception_Allocation_Data_2021_1.pdf"},
    2022: {"cache": "reception-2022.pdf", "url": BASE + "9407/September-2022-allocation-data/pdf/"
                                                        "oeReception_Allocation_Data_2022.pdf"},
    2023: {"cache": "reception-2023.pdf", "url": BASE + "11486/September-2023-allocation-data/pdf/"
                                                        "3gSeptember_2023_allocation_data.pdf"},
    2024: {"cache": "reception-2024.pdf", "url": BASE + "13876/September-2024-allocation-data/pdf/"
                                                        "edUpdated-NOD-reception-allocation-data-V2.pdf"},
    2025: {"cache": "reception-2025.pdf", "url": BASE + "16165/September-2025-allocation-data/pdf/"
                                                        "b4September_2025_allocation_data_1.pdf"},
}
DISTANCE_METHOD = "unknown"
DISTANCE_NOTES = ("Hillingdon publishes the \"furthest distance offered\" in metres (converted to miles here); the "
                  "Reception tables exclude offers made under the sibling criterion. The measurement method is not "
                  "stated in these tables. N/A (U) marks an undersubscribed school (everyone who applied was "
                  "offered), N/A (F) a faith school for which no distance is published, and N/A (B) Swakeleys, "
                  "which allocates by NVRT ability banding.")

# Image-only editions, transcribed by hand from the rendered PDF page:
# (school, offers that could be made, SEN, places available, furthest distance in metres or code)
SECONDARY_IMAGE_ROWS = {
    2024: [("Barnhill", 240, 6, 0, "1804"), ("Bishop Ramsey", 186, 5, 0, "N/A (F)"),
           ("Bishopshalt", 186, 6, 0, "1543.48"), ("Guru Nanak", 150, 7, 0, "N/A (F)"),
           ("Harefield School", 90, 2, 30, "N/A (U)"), ("Harlington", 240, 10, 0, "2732.77"),
           ("Haydon", 300, 4, 109, "N/A (U)"), ("Hewens", 120, 1, 41, "N/A (U)"),
           ("Northwood", 180, 11, 0, "1323.08"), ("Oak Wood", 240, 6, 25, "N/A (U)"),
           ("Park Academy West London", 180, 9, 0, "N/A (U)"), ("Queensmead", 240, 5, 0, "1191.79"),
           ("Rosedale", 200, 6, 0, "N/A (U)"), ("Ruislip High", 210, 8, 0, "1509.45"),
           ("Swakeleys", 240, 1, 0, "N/A (B)"), ("The Douay Martyrs", 240, 3, 0, "N/A (F)"),
           ("Uxbridge High", 240, 9, 0, "3055.46"), ("Vyners", 240, 6, 0, "1715.74")],
    2025: [("Barnhill", 240, 6, 0, "1047.65"), ("Bishop Ramsey", 186, 2, 0, "N/A (F)"),
           ("Bishopshalt", 186, 11, 0, "1349.33"), ("Guru Nanak", 120, 9, 0, "N/A (F)"),
           ("Harefield School", 90, 2, 24, "N/A (U)"), ("Harlington", 240, 17, 0, "2455.85"),
           ("Haydon", 300, 5, 72, "N/A (U)"), ("Hewens", 120, 3, 6, "N/A (U)"),
           ("Northwood", 180, 8, 0, "1131.36"), ("Oak Wood", 240, 5, 0, "6041.74"),
           ("Park Academy West London", 180, 12, 14, "N/A (U)"), ("Queensmead", 240, 2, 0, "1611.51"),
           ("Rosedale", 180, 12, 0, "N/A (U)"), ("Ruislip High", 210, 14, 0, "1148.79"),
           ("Swakeleys", 240, 6, 0, "N/A (B)"), ("The Douay Martyrs", 240, 4, 0, "N/A (F)"),
           ("Uxbridge High", 230, 14, 0, "3225.99"), ("Vyners", 240, 9, 0, "1673.49")],
}
SECONDARY_IMAGE_TOTALS = {2024: (3722, 105, 205), 2025: (3662, 141, 116)}  # printed "Totals" row

SEC_ROW = re.compile(r"^(?P<name>[A-Z][A-Za-z' ]+?)\s{2,}(?P<pan>\d+)\s+(?:(?P<sen>\d+)\s+)?(?P<avail>\d+)\s+"
                     r"(?P<dist>[\d,]+(?:\.\d+)?|N/A \([UFB]\))\**\s*$")


def _secondary_record(year: int, name: str, pan: int, sen: int | None, avail: int, dist: str) -> dict:
    notes = [f"\"Number of offers that could be made\" ({pan}) is recorded as the PAN; it includes any bulge "
             "places added that year."]
    criteria = [{"label": "SEN placements", "total": sen}] if sen is not None else []
    allocation, all_offered, max_distance = "distance", [], None
    if dist == "N/A (U)" or avail > 0:
        all_offered = ["All"]
        notes.append(f"Undersubscribed ({avail} place(s) still available after national offer day): everyone "
                     "who applied received an offer.")
    if dist == "N/A (F)":
        allocation = "faith_then_distance"
        notes.append("Faith school: Hillingdon does not publish a furthest distance for it.")
    elif dist == "N/A (B)":
        allocation = "mixed"
        notes.append("Banding school: offers depend on non-verbal reasoning test (NVRT) bands, so no single "
                     "furthest distance is published.")
    elif not dist.startswith("N/A"):
        metres = float(dist.replace(",", ""))
        max_distance = bc.miles_from_metres(metres)
        notes.append(f"Published as {dist} metres; converted to miles.")
    return bc.secondary_record(name, year, pan=pan, criteria=criteria, max_distance={"All": max_distance},
                               all_offered=all_offered, allocation=allocation, notes=notes)


def parse_secondary(paths: dict) -> list[dict]:
    out = []
    for year, path in sorted(paths.items()):
        if year in SECONDARY_IMAGE_ROWS:
            rows = SECONDARY_IMAGE_ROWS[year]
            totals = (sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows))
            if totals != SECONDARY_IMAGE_TOTALS[year]:
                raise SystemExit(f"hillingdon secondary {year}: transcription totals {totals} do not match the "
                                 f"printed totals {SECONDARY_IMAGE_TOTALS[year]}")
            for name, pan, sen, avail, dist in rows:
                rec = _secondary_record(year, name, pan, sen, avail, dist)
                rec["notes"].append("Transcribed by hand from an image-only PDF (no text layer); checked against "
                                    "the printed column totals.")
                out.append(rec)
            continue
        rows = [m for line in bc.text_of(path).splitlines() if (m := SEC_ROW.match(line.strip()))]
        if len(rows) < 17:
            raise SystemExit(f"hillingdon secondary {year}: only {len(rows)} rows matched")
        for m in rows:
            if m["name"].strip().lower().startswith("total"):
                continue
            sen = int(m["sen"]) if m["sen"] else None
            out.append(_secondary_record(year, m["name"].strip(), int(m["pan"]), sen, int(m["avail"]), m["dist"]))
    return out


# --------------------------------------------------------------------------- reception

def _classify(label: str) -> str | None:
    s = label.lower()
    if "furthest" in s:
        m = re.search(r"(20\d\d)", s)
        return f"dist:{m.group(1)}" if m else None
    if "criteria" in s:
        return "crit"
    if "admission" in s or "published" in s:
        return "pan"
    if "offers" in s or "on-time" in s:
        return "offers"
    if "available" in s:
        return "avail"
    if s.startswith("school"):
        return "name"
    return None


def _keyword_columns(hdr_words: list[pdftools.Word], doc: str) -> list[tuple[str, float, float]]:
    """Column centres from one distinctive header word per column (headers are centred over wrapped text, so
    grouping every header word is unreliable); each column spans half-way to its neighbours."""
    centres: list[tuple[str, float]] = []
    def first(text: str) -> pdftools.Word:
        found = [w for w in hdr_words if w.text == text]
        if not found:
            raise SystemExit(f"hillingdon {doc}: header word {text!r} not found")
        return found[0]
    centres.append(("name", first("Schools").cx))
    centres.append(("pan", first("Published").cx))
    centres.append(("offers", first("On-time").cx))
    centres.append(("avail", first("Places").cx))
    years = [w for w in hdr_words if re.fullmatch(r"20\d\d", w.text)]
    for fw in sorted((w for w in hdr_words if w.text == "Furthest"), key=lambda w: w.x0):
        dw = min((w for w in hdr_words if w.text == "distance" and abs(w.top - fw.top) < 3 and w.x0 > fw.x0),
                 key=lambda w: w.x0)
        cx = (fw.x0 + dw.x1) / 2
        yw = min(years, key=lambda w: abs(w.cx - cx))
        centres.append((f"dist:{yw.text}", cx))
    if any(w.text == "Criteria" for w in hdr_words):  # not in the 2022 edition
        centres.append(("crit", first("Criteria").cx + 25))
    centres.sort(key=lambda c: c[1])
    cols = []
    for i, (kind, cx) in enumerate(centres):
        lo = (centres[i - 1][1] + cx) / 2 if i else 0
        hi = (centres[i + 1][1] + cx) / 2 if i + 1 < len(centres) else 2000
        cols.append((kind, lo + 1, hi - 1))
    return cols


VALUE_OK = re.compile(r"^([\d,]+(?:\.\d+)?\*?|N/A \([UF]\)|Contact [Ss]chool|[\w.]+)$")


def _reception_rows(path) -> list[dict]:
    rows = []
    with bc.open_pdf(path) as pdf:
        cols = None
        for page in pdf.pages:
            words = pdftools.page_words(page)
            lines = pdftools.group_lines(words)
            hdr = next((l for l in lines if l.text.startswith("Schools")), None)
            if hdr is not None:
                top = min(l.top for l in lines) - 1
                cols = _keyword_columns([w for w in words if top <= w.cy < hdr.top + 12], path.name)
                body_top = hdr.top + 12
            else:
                body_top = 0
            if cols is None:
                raise SystemExit(f"hillingdon {path.name}: no header on first page")
            foot = next((l for l in lines if l.text.startswith(("Please be aware", "*"))), None)
            bottom = foot.top - 1 if foot is not None else page.height
            pan_lo, pan_hi = next((x0, x1) for kind, x0, x1 in cols if kind == "pan")
            pan_words = [w for w in words if body_top <= w.cy < bottom and pan_lo <= w.cx <= pan_hi
                         and re.fullmatch(r"\d+", w.text)]
            if not pan_words:
                continue
            name_x1 = min(w.x0 for w in pan_words) - 3
            for row in bc.ruled_rows(page, words, cols, name_x1, body_top, bottom):
                if re.fullmatch(r"\d+", row["cells"].get("pan", "")):
                    rows.append(row)
    return rows


def _dist(raw: str | None) -> tuple[float | None, str | None]:
    if raw is None or raw == "":
        return None, None
    raw = raw.replace("*", "").strip()
    if raw.startswith("N/A"):
        return None, raw
    return float(raw.replace(",", "")), None


FAITH = re.compile(r"Catholic|CofE|C of E|\bCE\b|Church|Guru Nanak|Nanaksar|Sikh|Khalsa|Jewish|Islamic", re.I)


def parse_primary(paths: dict) -> tuple[list[dict], list[str]]:
    by_year: dict[int, dict[str, dict]] = {}
    previous: dict[int, dict[str, tuple[float | None, str | None]]] = {}
    for year, path in sorted(paths.items()):
        rows = _reception_rows(path)
        if len(rows) < 50:
            raise SystemExit(f"hillingdon reception {year}: only {len(rows)} rows")
        by_year[year] = {}
        for row in rows:
            cells, name = row["cells"], re.sub(r"\*+$", "", row["name"]).strip()
            pan, offers = bc.to_int(cells.get("pan")), bc.to_int(cells.get("offers"))
            avail = bc.to_int(cells.get("avail"))
            this_raw, prev_raw = cells.get(f"dist:{year}"), cells.get(f"dist:{year - 1}")
            if f"dist:{year}" not in {k for k in cells} and this_raw is None:
                this_raw = None
            dist, code = _dist(this_raw)
            previous.setdefault(year - 1, {})[name] = _dist(prev_raw)
            crit = (cells.get("crit") or "").strip()
            notes = [f"{offers} on-time offers against a published admission number of {pan}."]
            all_offered = code == "N/A (U)" or (avail or 0) > 0
            allocation = "faith_then_distance" if (code == "N/A (F)" or FAITH.search(name)) else "distance"
            if code == "N/A (U)":
                notes.append("Published as N/A (U): undersubscribed, everyone who applied was offered.")
            elif code == "N/A (F)":
                notes.append("Published as N/A (F): faith school, no furthest distance published.")
            if dist is not None:
                notes.append(f"Furthest distance offered (excluding sibling offers) published as {this_raw} "
                             "metres; converted to miles.")
                if all_offered:
                    notes.append("A furthest distance is published although places remained: it is the furthest "
                                 "child offered, not a cut-off.")
            if crit:
                notes.append(f"Criterion the last child was offered under, as published: \"{crit}\" (Hillingdon "
                             "notes this does not mean everyone in that criterion was offered).")
            rec = bc.primary_record(name, year, pan=pan, max_distance=None if all_offered else
                                    bc.miles_from_metres(dist), all_offered=all_offered, total_offers=offers,
                                    allocation=allocation, notes=notes)
            if all_offered and dist is not None:
                rec["notes"].append(f"Furthest child offered: {bc.miles_from_metres(dist)} miles.")
            by_year[year][name] = rec
    log: list[str] = []
    out = [rec for year in by_year.values() for rec in year.values()]
    for year, schools in previous.items():
        if year in by_year:
            for name, (dist, code) in schools.items():
                rec = by_year[year].get(name)
                if rec is None or dist is None:
                    continue
                mine = rec["max_distance"]
                if mine is not None and abs(mine - bc.miles_from_metres(dist)) > 0.002:
                    rec["notes"].append(f"The {year + 1} edition's previous-year column gives a different furthest "
                                        f"distance for {year} ({dist:g} metres, {bc.miles_from_metres(dist)} miles); "
                                        f"the {year} edition's own figure is used here.")
                    log.append(f"hillingdon reception {year} {name}: {year} edition gives {mine} mi, {year + 1} "
                               f"edition's previous-year column gives {bc.miles_from_metres(dist)} mi (kept {year} "
                               "edition)")
            continue
        for name, (dist, code) in schools.items():
            if dist is None and code is None:
                continue
            notes = ["Only the furthest distance is available for this year, from the previous-year column of the "
                     f"{year + 1} edition."]
            if code == "N/A (U)":
                notes.append("Published as N/A (U): undersubscribed, everyone who applied was offered.")
            elif code == "N/A (F)":
                notes.append("Published as N/A (F): faith school, no furthest distance published.")
            else:
                notes.append("Furthest distance offered (excluding sibling offers), converted from metres.")
            out.append(bc.primary_record(name, year, max_distance=bc.miles_from_metres(dist),
                                         all_offered=code == "N/A (U)",
                                         allocation="faith_then_distance" if (code == "N/A (F)" or
                                                                              FAITH.search(name)) else "distance",
                                         notes=notes))
    return out, log
