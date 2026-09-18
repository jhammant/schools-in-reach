"""Waltham Forest (LA 320): parse the council's "How School Places Were
Offered on National Offer Day" PDFs (one page per year, Reception and Year 7
separately), using pdfplumber word positions (columns are not reliably
recoverable from pdftotext -layout alone because "n/a" and numbers have
different widths). Each row gives PAN and a breakdown of offers by admission
criterion (including a "Distance" criterion count), the number of places
still available (if undersubscribed), and the cut-off ("last offered")
distance in miles -- published as "n/a" whenever Places Available > 0, i.e.
the school never reached a distance cut-off that year.
"""

from __future__ import annotations

import pdfplumber

import pdftools

LA_CODE = "320"
LA_NAME = "Waltham Forest"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {}

SECONDARY_DOCS = {
    2026: {"cache": "secondary-offered-2026.pdf",
          "url": "https://www.walthamforest.gov.uk/sites/default/files/2026-03/"
                 "How%20School%20Places%20Were%20Offered%20secondary%202026(1).pdf",
          "note": "walthamforest.gov.uk returns an AWS WAF browser challenge to plain HTTP fetches; this copy "
                  "was retrieved once via an interactive browser fetch and is cached, not re-downloadable by "
                  "this script's plain urllib fetch."},
}
PRIMARY_DOCS = {
    2022: {"cache": "reception-offered-2022.pdf",
          "url": "https://www.walthamforest.gov.uk/sites/default/files/2022-04/"
                 "How%20school%20Places%20Were%20Offered%20for%20reception%202022.pdf",
          "note": "see secondary 2026 note on walthamforest.gov.uk's bot challenge"},
    2025: {"cache": "reception-offered-2025.pdf",
          "url": "https://www.walthamforest.gov.uk/sites/default/files/2025-04/"
                 "How%20school%20places%20were%20offered%20reception%202025.pdf",
          "note": "see secondary 2026 note on walthamforest.gov.uk's bot challenge"},
    2026: {"cache": "reception-offered-2026.pdf",
          "url": "https://www.walthamforest.gov.uk/sites/default/files/2026-04/"
                 "How%20school%20places%20were%20offered%20reception_2026.pdf",
          "note": "see secondary 2026 note on walthamforest.gov.uk's bot challenge"},
}
DISTANCE_METHOD = "unknown"
DISTANCE_NOTES = ("The published tables give the \"Cut off Distance\" (miles) with no stated measurement method. "
                  "\"n/a\" is published whenever the school still had places available after all other criteria "
                  "were applied (i.e. it did not need to use the distance criterion to refuse anyone that year).")

PRIMARY_KEYS = ["pan", "sen_ehc", "lac", "medical", "social", "sibling", "staff", "religious", "distance",
                "la_alt", "places_avail", "cutoff"]
SECONDARY_KEYS = ["pan", "sen_ehc", "lac", "medical", "social", "feeder", "sibling", "staff", "religious",
                  "catchment", "distance", "la_alt", "places_avail", "cutoff"]
LABELS = {
    "sen_ehc": "SEN/EHC Plan", "lac": "LAC", "medical": "Medical", "social": "Social", "feeder": "Feeder Link",
    "sibling": "Sibling", "staff": "Staff Child", "religious": "Religious Criteria", "catchment": "Catchment",
    "distance": "Distance", "la_alt": "LA Alternative Offer",
}


class TableError(ValueError):
    pass


def _header_columns(row1_words: list[pdftools.Word], keys: list[str]) -> dict[str, float]:
    words = [w for w in row1_words if w.text not in ("BASE", "NAME")]
    centers: dict[str, float] = {}
    i = 0
    for key in keys:
        if i >= len(words):
            raise TableError(f"ran out of header words locating column {key!r}")
        if key == "cutoff":  # two words: "Cut" "off"
            centers[key] = (words[i].x0 + words[i + 1].x1) / 2
            i += 2
        else:
            centers[key] = words[i].x0
            i += 1
    return centers


def _body_lines(page, header_line) -> list:
    words = pdftools.page_words(page)
    lines = pdftools.group_lines(words)
    if header_line is not None:
        lines = [l for l in lines if l.top > header_line.top + 30]
    return [l for l in lines if not l.text.startswith(("Total", "How Places", "Below is a table"))]


def _eden_girls_row(name: str, words: list[pdftools.Word], year: int) -> dict:
    """Eden Girls' School Waltham Forest publishes separate distance-offered figures for its two sites ("School"
    site and "Station" site), printed across two visual rows as "School 38, ... 0 0 School 1.654," (row 1) and
    "Station 62 ... Station 1.399" (row 2) instead of a single value in the Distance / Cut off Distance columns.
    Parse the two "<Site> <value>" pairs directly, and the plain leading numeric fields by x-position."""
    ordered = sorted(words, key=lambda w: (round(w.top / 5), w.x0))
    site_values: dict[str, list[str]] = {"School": [], "Station": []}
    consumed: set[int] = set()
    for i, w in enumerate(ordered):
        if w.text in ("School", "Station") and i + 1 < len(ordered):
            site_values[w.text].append(ordered[i + 1].text.rstrip(","))
            consumed.update({i, i + 1})
    lead = [w.text for i, w in enumerate(ordered) if i not in consumed]
    pan, sen, lac, medical, social, feeder, sibling, staff, religious, catchment, la_alt, places_avail = lead[:12]
    criteria = []
    for key, val in (("SEN/EHC Plan", sen), ("LAC", lac), ("Medical", medical), ("Social", social),
                     ("Feeder Link", feeder), ("Sibling", sibling), ("Staff Child", staff),
                     ("Religious Criteria", religious), ("Catchment", catchment)):
        n = pdftools.as_int(val)
        if n is not None:
            criteria.append({"label": key, "total": n})
    groups = ["School site", "Station site"]
    dist_counts = {"School site": pdftools.as_int(site_values["School"][0]),
                  "Station site": pdftools.as_int(site_values["Station"][0])}
    max_distance = {"School site": pdftools.as_float(site_values["School"][1]),
                    "Station site": pdftools.as_float(site_values["Station"][1])}
    criteria.append({"label": "Distance", "counts": dist_counts,
                     "total": sum(v for v in dist_counts.values() if v)})
    return {
        "name": name, "year": year, "pan": pdftools.as_int(pan), "applications": None, "groups": groups,
        "criteria": criteria, "max_distance": max_distance, "all_offered": [], "non_preference_offers":
        pdftools.as_int(la_alt), "total_offers": None, "allocation": "distance",
        "notes": ["This school has two sites (\"School\" and \"Station\"); the council publishes separate "
                 "offer counts and cut-off distances for applicants measured from each site, reproduced here "
                 "as two groups instead of the usual single 'All' group."],
    }


def _parse_records(lines: list, keys: list[str], centers: dict[str, float], phase: str, year: int) -> list[dict]:
    name_limit = centers["pan"] - 15
    xs = [centers[k] for k in keys]
    records = []
    for i, line in enumerate(lines):
        name_words = [w for w in line.words if w.x1 < name_limit]
        value_words = [w for w in line.words if w.x1 >= name_limit]
        if not name_words or not value_words or name_words[0].text.startswith(("*", "^", "Note")):
            continue  # footnote / explanatory text, not a table row
        name = " ".join(w.text for w in name_words).strip()
        if name.startswith("Eden Girls"):
            cont_words = [w for w in lines[i + 1].words if w.x1 >= name_limit] if i + 1 < len(lines) else []
            records.append(_eden_girls_row(name, value_words + cont_words, year))
            continue
        cells: dict[str, str] = {}
        for w in value_words:
            idx, dist = pdftools.nearest(w.cx, xs)
            if dist > 35:
                raise TableError(f"{phase} {year} {name}: value {w.text!r} is {dist:.0f}pt from any column")
            key = keys[idx]
            if key in cells:
                raise TableError(f"{phase} {year} {name}: two values for column {key!r} ({cells[key]!r}, "
                                 f"{w.text!r})")
            cells[key] = w.text
        pan = pdftools.as_int(cells.get("pan", ""))
        if pan is None:
            continue  # not a data row
        criteria = []
        for key in ("sen_ehc", "lac", "medical", "social", "feeder", "sibling", "staff", "religious", "catchment",
                   "distance"):
            if key not in keys:
                continue
            raw = cells.get(key)
            n = pdftools.as_int(raw) if raw else None
            if n is not None:
                criteria.append({"label": LABELS[key], "total": n})
        la_alt = pdftools.as_int(cells.get("la_alt", ""))
        places_avail = pdftools.as_int(cells.get("places_avail", ""))
        cutoff_raw = cells.get("cutoff", "n/a")
        max_distance = None if cutoff_raw in ("n/a", "") else pdftools.as_float(cutoff_raw)
        all_offered = cutoff_raw in ("n/a", "") and bool(places_avail)
        notes = []
        if cutoff_raw in ("n/a", "") and not places_avail:
            notes.append("Cut off distance published as \"n/a\": no offers were made under the distance "
                        "criterion (places filled by higher-priority criteria), but the school had no places "
                        "remaining either, so this is not recorded as all_offered.")
        elif all_offered:
            notes.append(f"{places_avail} place(s) remained unfilled after all criteria were applied: the "
                        "distance criterion was never needed.")
        if phase == "secondary":
            records.append({
                "name": name, "year": year, "pan": pan, "applications": None, "groups": ["All"],
                "criteria": criteria, "max_distance": {"All": max_distance},
                "all_offered": ["All"] if all_offered else [], "non_preference_offers": la_alt,
                "total_offers": None, "allocation": "distance", "notes": notes,
            })
        else:
            records.append({
                "name": name, "year": year, "pan": pan, "applications": None, "total_offers": None,
                "criteria": criteria, "max_distance": max_distance, "all_offered": all_offered,
                "non_preference_offers": la_alt, "allocation": "distance", "notes": notes,
            })
    return records


def parse(phase: str, paths: dict) -> list[dict]:
    docs = SECONDARY_DOCS if phase == "secondary" else PRIMARY_DOCS
    keys = SECONDARY_KEYS if phase == "secondary" else PRIMARY_KEYS
    out = []
    for year in docs:
        path = paths[year]
        with pdfplumber.open(path) as pdf:
            centers = None
            for page in pdf.pages:
                words = pdftools.page_words(page)
                lines = pdftools.group_lines(words)
                header_line = next((l for l in lines if l.text.startswith("BASE NAME")), None)
                if header_line is not None:
                    centers = _header_columns(header_line.words, keys)
                if centers is None:
                    raise TableError(f"{phase} {year}: no 'BASE NAME' header row found before data rows")
                out.extend(_parse_records(_body_lines(page, header_line), keys, centers, phase, year))
    return out
