"""Compact, lazy-loaded fundraising finder data. Figures follow areas.py's PTA rules.

Names, links, phase and money status come from search.json. Rows contain schools
with a registered association; the pupil-count map also covers other schools.
Null means unavailable, never zero.
"""
import json

from pipeline.money import areas, series

PHASES = ("other", "primary", "secondary", "special", "all_through", "nursery", "alternative_provision", "post16")
COLUMNS = ("id", "c", "b", "lat", "lon", "income", "pp", "year", "charities", "flags", "change")
DATA_BUDGET = 1_200_000


def phase_code(phase):
    phase = str(phase or "").lower().replace("-", "_").replace(" ", "_")
    phase = {"16_plus": "post16", "post_16": "post16"}.get(phase, phase)
    return PHASES.index(phase) if phase in PHASES else 0


def registered(charity):
    return (not charity.get("removed") and not charity.get("removed_year")
            and str(charity.get("status") or "registered").lower() == "registered"
            and not areas.held_back(charity))


def latest(item, *, latest_complete=None):
    charities = [c for c in item.get("pta") or [] if registered(c)]
    if not charities:
        return None
    rows = item.get("rows") or []
    entries = areas.school_years(rows, charities)
    record = areas.pta_record(item["school"], item["council"]["code"], item["council"], rows, entries, charities, None)
    year = max(record["years"], default=None)
    slot = record["years"].get(year) or {}
    income, pupils = slot.get("income"), slot.get("pupils")
    changes = series.pta_changes(charities, rows, series.pta_pupils(rows), record["years"], latest_complete=latest_complete)
    change = changes.get(year) or {"reason": 6}
    return {"income": round(income) if income is not None else None,
            "pp": round(income / pupils) if income is not None and pupils else None,
            "year": year,
            "charities": sorted({str(c["charity_number"]) for c in charities if c.get("charity_number")}),
            "flags": (1 if slot.get("confidence") == "medium" else 0)
                     | (2 if any(c.get("shared_with") for c in charities) else 0),
            "change": change["reason"] or [change["value"], change["pct"], change["pp"]]}


def school_size(item):
    """The latest full return's own-school roll; never substitute an older or federation count."""
    rows = item.get("rows") or []
    full = series.status.full_years(rows)
    if not full:
        return None
    count = series.pta_pupils(rows).get(series.year_label(full[-1]))
    return round(count, 1) if count is not None else None


def build_data(schools, area_doc):
    """Attach each school's figures for static nearby lists; return the compact browser document.

    Medians are the existing published figures in the latest well-covered year, not
    recomputed over whichever latest returns happen to be filed or filtered.
    """
    pta = (area_doc or {}).get("pta") or {}
    year = pta.get("year")
    councils, rows, pupils = {}, [], {}
    for item in schools:
        count = school_size(item)
        if count is not None:
            pupils[item["urn"]] = int(count) if count == int(count) else count
        item["fundraising"] = latest(item, latest_complete=year)
        if item["fundraising"] is None:
            continue
        council = item["council"]
        code = council["code"]
        stats = (((area_doc or {}).get("councils") or {}).get(code) or {}).get("by_year") or {}
        median = ((stats.get(year) or {}).get("all") or {}).get("pta_pp_median")
        councils[code] = [council["name"], council.get("region") or "", round(median) if median is not None else None]
        values = dict(item["fundraising"], id=item["urn"], c=code, b=(item.get("profile") or {}).get("band"),
                      lat=round(item["lat"], 5) if isinstance(item.get("lat"), (int, float)) else None,
                      lon=round(item["lon"], 5) if isinstance(item.get("lon"), (int, float)) else None)
        rows.append([values[key] for key in COLUMNS])
    median = ((pta.get("by_year") or {}).get(year) or {}).get("median_pp")
    return {"v": 2, "columns": COLUMNS, "councils": councils, "year": year,
            "england": round(median) if median is not None else None, "rows": rows, "pupils": pupils}


def encode(doc):
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    size = len(text.encode("utf-8"))
    if size > DATA_BUDGET:
        raise ValueError(f"Fundraising data too large: {size:,} bytes (budget {DATA_BUDGET:,})")
    return text
