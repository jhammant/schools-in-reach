"""School Money map explorer (unit C1): the /map/ page and the data its map.js reads.

Writes, through write_pages(env):
  /map/                             the explorer: measure, year, geography, school filters, search,
                                    the Leaflet map, its key, an area/school card, and below the map
                                    a sortable table of every council (also the no-JavaScript view)
  /map/constituencies/              the same table for all 543 constituencies (too big for /map/)
  /data/map/councils.geojson        council boundaries, properties {id, code, name}, 4 dp
  /data/map/constituencies.geojson  constituency boundaries, simplified to fit 1.5 MB, 4 dp
  /data/map/measures.json           per-area values by measure and year (build_measures)
  /data/map/schools.json            one compact row per school with coordinates (build_schools)

Reads: site/data/england/la_boundaries_lite.geojson and pipeline/money/data/constituencies_2024.geojson
(repo-relative, falling back to the real repo like areas.py), data/ifs_context.json for the reasons
behind deficits, data/la_dsg.json for the high-needs override note, and env['items'] / env['areas'].
Stdlib only. Never imports build_money.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from pipeline.money import site
from pipeline.money import status as health

ROOT = Path(__file__).resolve().parents[2]
REAL_ROOT = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
DATA_DIR = Path(__file__).with_name("data")
COUNCILS_SRC = "site/data/england/la_boundaries_lite.geojson"
CONSTITUENCIES_SRC = "pipeline/money/data/constituencies_2024.geojson"

COUNCILS_BUDGET = 450_000
CONSTITUENCIES_BUDGET = 1_500_000
SCHOOLS_BUDGET = 1_600_000
FIRST_YEAR = "2018-19"
DP = 4

TILES_URL = "https://tiles.schoolsinreach.com/tiles/uk.pmtiles"
# Hashes checked on 2026-11-07 against the cdnjs API and jsDelivr's data API, and by hashing the files.
LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
LEAFLET_CSS_SRI = "sha512-h9FcoyWjHcOcmEVkxOfTLnmZFWIH0iZhZT1H2TbOq55xssQGEJHEaIm+PgoUaZbRvQTNTluNOEfb1ZRy6D3BOw=="
LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"
LEAFLET_JS_SRI = "sha512-puJW3E/qXDqYp9IfhAI54BJEaWIfloJ7JWs7OeD5i6ruC9JZL1gERT1wjtwXFlh7CjE7ZJ+/vcRZRkIYIb6p4g=="
PROTOMAPS_JS = "https://cdn.jsdelivr.net/npm/protomaps-leaflet@5.1.0/dist/protomaps-leaflet.js"
PROTOMAPS_JS_SRI = "sha256-Jq8BT3sa8wjsEgt5HP92ZXu5wzg2M7UgM+bt+eXkzbU="

SRC_FINANCE = "DfE CFR (council-run) and AAR (academy) returns"
LEVELS_ALL = ["england", "council", "constituency"]
LEVELS_LA = ["england", "council"]

# key, label, unit, signed, scale, source, levels, aliases (first found wins).
# An alias is (block, key): "all" is by_year[y]["all"], "dsg" is dsg[y], "area" is area[key][y].
MEASURES = [
    ("pct_in_deficit", "Share of schools in deficit", "pct", False, "sequential", SRC_FINANCE, LEVELS_ALL,
     [("all", "in_deficit_pct"), ("all", "pct_in_deficit")]),
    ("deficit_pp", "Deficit per pupil, schools in deficit", "gbp_pp", True, "diverging", SRC_FINANCE, LEVELS_ALL,
     [("all", "deficit_pp")]),
    ("reserve_median_pp", "Median reserve per pupil", "gbp_pp", True, "diverging", SRC_FINANCE, LEVELS_ALL,
     [("all", "reserve_median_pp"), ("all", "reserve_pp_median")]),
    ("gov_pp_median", "Median government funding per pupil", "gbp_pp", False, "sequential", SRC_FINANCE, LEVELS_ALL,
     [("all", "gov_pp_median"), ("all", "grant_pp_median")]),
    ("spend_pp_median", "Median spending per pupil", "gbp_pp", False, "sequential", SRC_FINANCE, LEVELS_ALL,
     [("all", "spend_pp_median"), ("all", "spend_median_pp")]),
    ("dsg_pp", "Council high-needs (DSG) balance per pupil", "gbp_pp", True, "diverging",
     "DfE section 251 outturn (Dedicated Schools Grant balance)", LEVELS_LA, [("dsg", "per_pupil")]),
    ("pta_median_pp", "Median parents' association income per pupil", "gbp_pp", False, "sequential",
     "Charity Commission register", LEVELS_ALL, [("all", "pta_median_pp"), ("all", "pta_pp_median")]),
    ("fsm_pct", "Pupils eligible for free school meals", "pct", False, "sequential", "DfE school census",
     LEVELS_ALL, [("all", "fsm_pct"), ("area", "fsm_pct_by_year")]),
    ("pupils", "Pupils in schools with a full-year return", "pupils", False, "sequential", SRC_FINANCE, LEVELS_ALL,
     [("area", "pupils_by_year")]),
]
MEASURE_KEYS = [m[0] for m in MEASURES]
DEFAULT_MEASURE = "pct_in_deficit"
DEFICIT_MEASURES = {"pct_in_deficit", "deficit_pp", "reserve_median_pp", "dsg_pp"}

PHASES = ["primary", "secondary", "special", "all_through", "nursery", "alternative_provision", "post16", "other"]
PHASE_LABELS = {"primary": "Primary", "secondary": "Secondary", "special": "Special", "all_through": "All-through",
                "nursery": "Nursery", "alternative_provision": "Alternative provision", "post16": "Sixth form and 16+",
                "other": "Other"}
GOVERNANCE = ["council-run", "academy", "free school", "independent"]
GOV_LABELS = {"council-run": "Council-run", "academy": "Academy", "free school": "Free school", "independent": "Independent"}
ICONS = {"in_deficit": "▼", "heading_for_deficit": "↘", "tight": "●", "healthy": "✓", "large_reserves": "▲"}

HELPS = ("What helps: a plan agreed with the council or trust to bring the budget back into balance over a few "
         "years, forecasts that governors see often, and early talks about pupil numbers and special needs "
         "funding. The guides list questions to ask.")
CASH_NOTE = "£ figures are cash for each year, not adjusted for inflation."
PTA_NOTE = ("Parents' association income comes from the Charity Commission register. Charities with income of "
            "£5,000 or less need not register, so a school with no registered parents' association found may "
            "still have one. It can overlap with donations in the school's own accounts, so the two are never added together.")
DSG_FALLBACK = ("Statutory override: council high-needs (DSG) deficits are held apart from council general funds "
                "until the end of 2027-28, and the High Needs Stability Grant pays most of them from autumn 2026.")


# ----------------------------------------------------------------- small helpers

def _dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return None


def resolve(rel):
    """A repo file relative to this checkout, else the real repo; None when neither has it."""
    for base in (ROOT, REAL_ROOT):
        path = base / rel
        if path.is_file():
            return path
    return None


def _number(value):
    """value as a finite int/float, or None (bools and strings are not numbers here)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (math.inf, -math.inf):
        return None
    return value


def _tidy(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _json_attr(obj) -> str:
    return site.esc(_dumps(obj))


def _json_script(obj) -> str:
    """JSON for a <script type="application/json"> block, with '<' and '&' escaped as site.page does."""
    return _dumps(obj).replace("<", "\\u003c").replace("&", "\\u0026")


# ----------------------------------------------------------------- geometry

def _seg_dist2(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        ex, ey = px - ax, py - ay
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        ex, ey = px - (ax + t * dx), py - (ay + t * dy)
    return ex * ex + ey * ey


def _closed(points):
    pts = [list(p) for p in points]
    if pts and pts[0][:2] != pts[-1][:2]:
        pts.append(list(pts[0]))
    return pts


def _significance(points, floor=0.0):
    """Douglas-Peucker split distance for each position of a closed ring, worked out iteratively
    (a stack, no recursion). A position survives tolerance t when its value is above t. The ring is
    split first at the vertex farthest from its start; both ends and that vertex never drop.
    Segments whose widest deviation is at or below floor are not split further."""
    n = len(points)
    sig = [0.0] * n
    if n < 4:
        return [math.inf] * n
    sig[0] = sig[-1] = math.inf
    x0, y0 = points[0][0], points[0][1]
    far = max(range(1, n - 1), key=lambda i: (points[i][0] - x0) ** 2 + (points[i][1] - y0) ** 2)
    sig[far] = math.inf
    stack = [(0, far, math.inf), (far, n - 1, math.inf)]
    while stack:
        s, e, cap = stack.pop()
        if e - s < 2:
            continue
        ax, ay, bx, by = points[s][0], points[s][1], points[e][0], points[e][1]
        best, idx = -1.0, s + 1
        for i in range(s + 1, e):
            d = _seg_dist2(points[i][0], points[i][1], ax, ay, bx, by)
            if d > best:
                best, idx = d, i
        d = min(math.sqrt(best), cap)
        if d <= floor:
            for i in range(s + 1, e):
                sig[i] = d
            continue
        sig[idx] = d
        stack.append((s, idx, d))
        stack.append((idx, e, d))
    return sig


def _pick(points, sig, tolerance):
    """(ring, collapsed): positions above tolerance, topped up to 4 by significance when DP leaves
    fewer (collapsed is then True)."""
    keep = [i for i, s in enumerate(sig) if s > tolerance]
    collapsed = len(keep) < 4
    if collapsed and len(points) >= 4:
        chosen = set(keep)
        spare = sorted((i for i in range(len(points)) if i not in chosen), key=lambda i: -sig[i])
        keep = sorted(chosen.union(spare[:4 - len(keep)]))
    return [points[i] for i in keep], collapsed


def simplify_ring(points, tolerance):
    """Douglas-Peucker for one closed ring (degrees). Keeps the first and last position, stays closed and
    never returns fewer than 4 positions."""
    pts = _closed(points)
    if len(pts) <= 4 or tolerance <= 0:
        return pts
    ring, _ = _pick(pts, _significance(pts, tolerance), tolerance)
    return ring


def _ring_area(ring):
    return abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))) / 2


def _polygons(geom):
    """[polygon, ...] where a polygon is [outer ring, hole, ...], for Polygon and MultiPolygon."""
    kind, coords = (geom or {}).get("type"), (geom or {}).get("coordinates") or []
    if kind == "Polygon":
        return [coords] if coords else []
    if kind == "MultiPolygon":
        return [p for p in coords if p]
    return []


def _geometry(polys):
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def _simplify_polys(polys, sigs, tolerance):
    """Simplified polygons. A part whose outer ring collapses is dropped, holes likewise; the
    largest part (by area) is always kept."""
    largest = max(range(len(polys)), key=lambda k: _ring_area(polys[k][0])) if polys else -1
    out = []
    for k, poly in enumerate(polys):
        outer, collapsed = _pick(poly[0], sigs[k][0], tolerance)
        if collapsed and k != largest:
            continue
        rings = [outer]
        for ring, sig in zip(poly[1:], sigs[k][1:]):
            hole, hole_collapsed = _pick(ring, sig, tolerance)
            if not hole_collapsed:
                rings.append(hole)
        out.append(rings)
    return out


def simplify_geometry(geom, tolerance):
    """A Polygon/MultiPolygon simplified ring by ring (see _simplify_polys)."""
    polys = [[_closed(r) for r in poly] for poly in _polygons(geom)]
    if not polys or tolerance <= 0:
        return _geometry(polys) if polys else geom
    sigs = [[_significance(r, tolerance) for r in poly] for poly in polys]
    return _geometry(_simplify_polys(polys, sigs, tolerance))


def _round_ring(ring, dp):
    out = []
    for p in ring:
        q = [round(p[0], dp), round(p[1], dp)]
        if not out or out[-1] != q:
            out.append(q)
    if out and out[0] != out[-1]:
        out.append(list(out[0]))
    return out


def _round_polys(polys, dp):
    largest = max(range(len(polys)), key=lambda k: _ring_area(polys[k][0])) if polys else -1
    out = []
    for k, poly in enumerate(polys):
        outer = _round_ring(poly[0], dp)
        if len(outer) < 4:
            if k != largest:
                continue
            outer = [[round(p[0], dp), round(p[1], dp)] for p in poly[0]]
        rings = [outer]
        for hole in poly[1:]:
            hole = _round_ring(hole, dp)
            if len(hole) >= 4:
                rings.append(hole)
        out.append(rings)
    return out


def round_geometry(geom, dp=DP):
    """Coordinates rounded to dp decimals with consecutive duplicates removed; rings that fall
    below 4 positions are dropped, except the largest part, which is always kept."""
    polys = _polygons(geom)
    return _geometry(_round_polys(polys, dp)) if polys else geom


def _feature_collection(features):
    return _dumps({"type": "FeatureCollection", "features": features})


def build_geojson(features, id_prefix, code_key, budget, simplify):
    """Compact GeoJSON text with properties {id: id_prefix + code, code, name}, rounded to 4 dp, at most
    budget bytes. With simplify, the Douglas-Peucker tolerance rises (doubling, then bisection) until it
    fits. Raises ValueError when it cannot fit."""
    prepared = []
    for f in features or []:
        props = f.get("properties") or {}
        code = str(props.get(code_key) if props.get(code_key) is not None else props.get("code", ""))
        polys = [[_closed(r) for r in poly] for poly in _polygons(f.get("geometry"))]
        if not code or not polys:
            continue
        prepared.append(({"id": f"{id_prefix}{code}", "code": code, "name": str(props.get("name") or code)}, polys))

    def encode(tolerance, sigs=None):
        out = []
        for k, (props, polys) in enumerate(prepared):
            if tolerance > 0:
                polys = _simplify_polys(polys, sigs[k], tolerance)
            out.append({"type": "Feature", "properties": props, "geometry": _geometry(_round_polys(polys, DP))})
        return _feature_collection(out)

    text = encode(0)
    if len(text.encode("utf-8")) <= budget:
        return text
    if not simplify:
        raise ValueError(f"{id_prefix}boundaries are {len(text.encode('utf-8')):,} bytes, over the {budget:,} byte budget")
    sigs = [[[_significance(r, 1e-6) for r in poly] for poly in polys] for _, polys in prepared]
    lo, hi, best = 0.0, 5e-5, None
    while hi <= 0.2:
        text = encode(hi, sigs)
        if len(text.encode("utf-8")) <= budget:
            best = text
            break
        lo, hi = hi, hi * 2
    if best is None:
        raise ValueError(f"{id_prefix}boundaries do not fit {budget:,} bytes even at tolerance {lo}")
    for _ in range(7):
        mid = (lo + hi) / 2
        text = encode(mid, sigs)
        if len(text.encode("utf-8")) <= budget:
            best, hi = text, mid
        else:
            lo = mid
    return best


# ----------------------------------------------------------------- measures

def _areas_block(areas_doc):
    doc = areas_doc or {}
    if isinstance(doc.get("areas"), dict):
        doc = doc["areas"]
    return doc


def _value(area, year, aliases):
    """The first alias with a numeric value for year, or None."""
    by_year = (area.get("by_year") or {}).get(year)
    split = by_year.get("all") if isinstance(by_year, dict) and isinstance(by_year.get("all"), dict) else {}
    for block, key in aliases:
        if block == "all":
            value = split.get(key)
        elif block == "dsg":
            entry = (area.get("dsg") or {}).get(year)
            value = entry.get(key) if isinstance(entry, dict) else None
        else:
            series = area.get(key)
            value = series.get(year) if isinstance(series, dict) else None
        if _number(value) is not None:
            return value
    return None


def _round_measure(value, unit):
    if unit == "gbp_pp":
        return int(round(value))
    return _tidy(round(value, 1))


def _area_years(area):
    years = set()
    for key in ("by_year", "pupils_by_year", "dsg", "fsm_pct_by_year", "schools_by_year"):
        block = area.get(key)
        if isinstance(block, dict):
            years.update(str(y) for y in block)
    return years


def _area_values(area, years, level):
    m = {}
    for key, _label, unit, _signed, _scale, _source, levels, aliases in MEASURES:
        if level not in levels:
            continue
        series = {}
        for year in years:
            value = _value(area, year, aliases)
            if value is not None:
                series[year] = _round_measure(value, unit)
        if series:
            m[key] = series
    return m


def measure_meta():
    """{key: {label, unit, signed, scale, source, levels}} in display order."""
    return {key: {"label": label, "unit": unit, "signed": signed, "scale": scale, "source": source, "levels": levels}
            for key, label, unit, signed, scale, source, levels, _aliases in MEASURES}


def _area_id(prefix, key):
    key = str(key)
    return key if key.startswith(prefix) else prefix + key


def build_measures(areas_doc):
    """measures.json from the areas document (build_areas output, bare or wrapped in {"areas": ...}).
    Missing or None values are omitted, never written as 0; an area with no values is still listed."""
    A = _areas_block(areas_doc)
    england = A.get("england") if isinstance(A.get("england"), dict) else {}
    councils = A.get("councils") if isinstance(A.get("councils"), dict) else {}
    constituencies = A.get("constituencies") if isinstance(A.get("constituencies"), dict) else {}
    candidates = set(_area_years(england))
    for block in (councils, constituencies):
        for area in block.values():
            if isinstance(area, dict):
                candidates |= _area_years(area)
    candidates = sorted(y for y in candidates if re.fullmatch(r"\d{4}-\d{2}", y) and y >= FIRST_YEAR)

    def listing(block, prefix, level):
        out = {}
        named = {k: (v if isinstance(v, dict) else {}) for k, v in block.items()}
        for key in sorted(named, key=lambda k: (str(named[k].get("name") or k).lower(), str(k))):
            area = named[key]
            ident = _area_id(prefix, key)
            name = str(area.get("name") or key)
            out[ident] = {"name": name, "p": site.page_path("area", ident, name), "m": _area_values(area, candidates, level)}
        return out

    doc = {
        "years": [],
        "measures": measure_meta(),
        "england": _area_values(england, candidates, "england"),
        "council": listing(councils, "council-", "council"),
        "constituency": listing(constituencies, "constituency-", "constituency"),
    }
    used = set()
    for series in doc["england"].values():
        used.update(series)
    for level in ("council", "constituency"):
        for entry in doc[level].values():
            for series in entry["m"].values():
                used.update(series)
    doc["years"] = sorted(used)
    return doc


def default_year(measures):
    """The latest year in the document. A measure missing for that year shows as not published, not as an older year."""
    years = measures.get("years") or []
    return years[-1] if years else None


# ----------------------------------------------------------------- schools

def read_item(item):
    """The one place this module reads a school item (Wave B is reshaping them)."""
    urn = str(item.get("urn"))
    name = str(item.get("name") or "")
    council = item.get("council") if isinstance(item.get("council"), dict) else {}
    la = item.get("la") or council.get("code")
    if isinstance(la, dict):
        la = la.get("code")
    raw = item.get("status")
    key = raw.get("status") if isinstance(raw, dict) else (raw if isinstance(raw, str) else None)
    tags = item.get("tags") or {}
    governance = tags.get("governance") or ("academy" if item.get("academy") else "council-run")
    pupils = item.get("pupils")
    if pupils is None:
        years = health.full_years(item.get("rows") or [])
        pupils = years[-1].get("pupils") if years else None
    school = item.get("school") if isinstance(item.get("school"), dict) else {}
    lat = item.get("lat") if item.get("lat") is not None else school.get("lat")
    lon = item.get("lon") if item.get("lon") is not None else school.get("lon")
    phase = re.sub(r"[\s-]+", "_", str(item.get("phase") or "other").strip().lower())
    return {
        "urn": urn, "name": name, "path": item.get("path") or site.page_path("school", urn, name),
        "la": str(la) if la not in (None, "") else None,
        "la_name": item.get("la_name") or council.get("name"),
        "phase": phase if phase in PHASES else "other",
        "status": key if key in health.ORDER else None,
        "governance": governance if governance in GOVERNANCE else "council-run",
        "pupils": pupils, "lat": _number(lat), "lon": _number(lon),
    }


def build_schools(items):
    """schools.json: a key and one row [urn, lat, lon, status, phase, governance, name] per school with
    coordinates; status -1 means no published status. Raises ValueError over 1.6 MB (never trims)."""
    rows = []
    for item in items or []:
        s = read_item(item)
        if s["lat"] is None or s["lon"] is None or not s["urn"].isdigit():
            continue
        rows.append([int(s["urn"]), round(s["lat"], DP), round(s["lon"], DP),
                     health.ORDER.index(s["status"]) if s["status"] else -1,
                     PHASES.index(s["phase"]), GOVERNANCE.index(s["governance"]), s["name"]])
    rows.sort(key=lambda r: r[0])
    doc = {"key": {"status": list(health.ORDER), "phase": list(PHASES), "governance": list(GOVERNANCE),
                   "fields": ["urn", "lat", "lon", "status", "phase", "governance", "name"]},
           "rows": rows}
    size = len(_dumps(doc).encode("utf-8"))
    if size > SCHOOLS_BUDGET:
        raise ValueError(f"schools.json would be {size:,} bytes, over the {SCHOOLS_BUDGET:,} byte budget; "
                         "shorten the rows rather than dropping schools")
    return doc


# ----------------------------------------------------------------- context for map.js

def map_context():
    """Static copy map.js shows beside deficits: the IFS reasons (with pages), what helps, the DSG note."""
    ifs = _load_json(DATA_DIR / "ifs_context.json") or {}
    framings = ifs.get("framings") or {}
    source = ifs.get("source") or {}

    def framing(key):
        f = framings.get(key) or {}
        return {"title": f.get("title") or "", "text": f.get("text") or "", "pages": f.get("pages") or []} if f else None

    dsg = _load_json(DATA_DIR / "la_dsg.json") or {}
    notes = (dsg.get("source") or {}).get("notes") or []
    dsg_note = next((n for n in notes if isinstance(n, str) and n.startswith("Statutory override")), DSG_FALLBACK)
    return {
        "why": framing("why_schools_go_into_deficit"),
        "send": framing("send_pressure"),
        "cite": source.get("short_cite") or site.IFS_CITE,
        "url": source.get("url") or site.IFS_URL,
        "helps": HELPS,
        "helps_link": "/guides/governors/",
        "dsg_note": dsg_note,
        "cash_note": CASH_NOTE,
        "pta_note": PTA_NOTE,
    }


def _pages(pages):
    """[62, 63] -> 'p.62–63'; [46, 58] -> 'pp.46, 58'; [7] -> 'p.7'."""
    pages = [p for p in pages or [] if isinstance(p, int)]
    if not pages:
        return ""
    if len(pages) == 1:
        return f"p.{pages[0]}"
    if len(pages) == 2 and pages[1] == pages[0] + 1:
        return f"p.{pages[0]}–{pages[1]}"
    return "pp." + ", ".join(str(p) for p in pages)


# ----------------------------------------------------------------- HTML

def fmt_value(value, unit, signed=False):
    """Display text for a measure value; None gives the 'not published' sentence, never £0."""
    if _number(value) is None:
        return "Not published for this year"
    if unit == "pct":
        return f"{value:.1f}%"
    if unit == "gbp_pp":
        sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
        return f"{sign}£{abs(round(value)):,} per pupil"
    text = f"{value:,.1f}".rstrip("0").rstrip(".")
    return f"{text} pupils"


def _sort_value(value):
    return site.esc(str(_tidy(value)))


def _why_html(ctx):
    why = ctx.get("why") or {}
    if not why.get("text"):
        return ""
    cite = f' <span class="small muted">({site.esc(ctx["cite"])}, {site.esc(_pages(why.get("pages")))})</span>'
    return (f'<aside class="mx-why" aria-labelledby="mx-why-h"><h2 id="mx-why-h">{site.esc(why.get("title") or "Why schools go into deficit")}</h2>'
            f'<p>{site.esc(why["text"])}{cite}</p>'
            f'<p>{site.esc(ctx["helps"])} <a href="{site.esc(ctx["helps_link"])}">Questions for governors</a> · '
            f'<a href="/guides/parents/">for parents</a>.</p></aside>')


def _table_rows(entries, measure, year, linked):
    """Table rows. Linked rows (the /map/ council table) carry the area id and page link; unlinked rows
    (543 constituencies) are kept bare so the page stays inside the 48,000-byte budget."""
    unit, signed = measure["unit"], measure["signed"]
    rows = []
    for ident, entry in entries.items():
        value = entry["m"].get(measure["key"], {}).get(year)
        name = site.esc(entry["name"])
        if value is None:
            td = "<td>Not published</td>"
        else:
            td = f'<td data-sort="{_sort_value(value)}">{site.esc(fmt_value(value, unit, signed))}</td>'
        if linked:
            rows.append(f'<tr data-id="{site.esc(ident)}"><th scope="row"><a href="{site.esc(entry["p"])}">{name}</a></th>{td}</tr>')
        else:
            rows.append(f"<tr><th>{name}</th>{td}</tr>")  # a first-column th is a row header (auto scope)
    return "".join(rows)


def _caption(measure, year, england_value, level_label):
    eng = fmt_value(england_value, measure["unit"], measure["signed"]) if england_value is not None else "not published"
    return (f'{site.esc(measure["label"])}, {site.esc(year or "no year yet")}, by {level_label}. '
            f'England: {site.esc(eng)}. Source: {site.esc(measure["source"])}.')


def _table(entries, measure, year, england_value, level, linked, table_id):
    head = "Council" if level == "council" else "Constituency"
    if not entries:
        return f'<p class="muted" id="{table_id}-empty">Figures for this year aren\'t published yet.</p>'
    return (f'<div class="mx-scroll"><table data-sortable id="{table_id}" data-level="{level}">'
            f'<caption>{_caption(measure, year, england_value, head.lower())}</caption>'
            f'<thead><tr><th scope="col">{head}</th><th scope="col">{site.esc(measure["label"])}</th></tr></thead>'
            f'<tbody>{_table_rows(entries, measure, year, linked)}</tbody></table></div>')


def _checks(name, options, labels, legend):
    boxes = "".join(
        f'<label class="mx-check"><input type="checkbox" name="{name}" value="{site.esc(v)}" checked> {labels[v]}</label>'
        for v in options)
    return f'<fieldset class="mx-group"><legend>{legend}</legend>{boxes}</fieldset>'


def _status_labels():
    labels = {k: f'<span class="badge small s-{k}"><span aria-hidden="true">{ICONS[k]}</span> {site.esc(health.LABELS[k])}</span>'
              for k in health.ORDER}
    labels["none"] = "No published status"
    return labels


def _controls(measures, years, year, measure_key):
    options = "".join(f'<option value="{site.esc(k)}"{" selected" if k == measure_key else ""}>{site.esc(m["label"])}</option>'
                      for k, m in measures.items())
    idx = years.index(year) if year in years else max(len(years) - 1, 0)
    disabled = "" if len(years) > 1 else " disabled"
    statuses = _checks("status", list(health.ORDER) + ["none"], _status_labels(), "Status")
    return (
        '<div class="mx-controls" id="mx-controls">'
        f'<div class="mx-field"><label for="mx-measure">Colour the map by</label><select id="mx-measure" name="m">{options}</select></div>'
        f'<div class="mx-field"><label for="mx-year">Year</label><div class="mx-range">'
        f'<input type="range" id="mx-year" name="y" min="0" max="{max(len(years) - 1, 0)}" step="1" value="{idx}" '
        f'aria-valuetext="{site.esc(year or "")}"{disabled}>'
        f'<output id="mx-year-out" for="mx-year">{site.esc(year or "No year yet")}</output></div></div>'
        '<fieldset class="mx-field mx-geo"><legend>Areas</legend>'
        '<label class="mx-check"><input type="radio" name="g" value="council" checked> Councils</label>'
        '<label class="mx-check"><input type="radio" name="g" value="constituency"> Constituencies</label></fieldset>'
        '<div class="mx-field mx-search"><label for="mx-q">Find a school or area on the map</label>'
        '<input id="mx-q" type="search" role="combobox" autocomplete="off" aria-autocomplete="list" aria-expanded="false" '
        'aria-controls="mx-q-list" placeholder="School, council or constituency">'
        '<ul id="mx-q-list" class="listbox" role="listbox" aria-label="Places on the map" hidden></ul></div>'
        '<details class="mx-filters"><summary>Filter school dots</summary>'
        f'{_checks("phase", PHASES, PHASE_LABELS, "Phase")}{_checks("gov", GOVERNANCE, GOV_LABELS, "Run by")}{statuses}'
        '<p class="small muted">School dots appear when you zoom in to town level.</p></details>'
        '</div>')


def _head(*, with_map=True):
    """Pinned libraries (each URL once, as a constant) plus this unit's CSS and JS."""
    parts = []
    if with_map:
        parts.append(f'<link rel="stylesheet" href="{LEAFLET_CSS}" integrity="{LEAFLET_CSS_SRI}" crossorigin="anonymous">')
    parts.append('<link rel="stylesheet" href="/assets/map.css">')
    if with_map:
        parts.append(f'<script src="{LEAFLET_JS}" integrity="{LEAFLET_JS_SRI}" crossorigin="anonymous" defer></script>')
        parts.append(f'<script src="{PROTOMAPS_JS}" integrity="{PROTOMAPS_JS_SRI}" crossorigin="anonymous" defer></script>')
        parts.append('<script src="/assets/map.js" defer></script>')
    return "".join(parts)


def map_body(measures, ctx, *, has_councils, has_constituencies):
    """The /map/ body: controls, map, key, card, the reasons behind deficits and the council table."""
    meta = {k: dict(v, key=k) for k, v in measures["measures"].items()}
    measure = meta[DEFAULT_MEASURE]
    years = measures["years"]
    year = default_year(measures)
    england_value = (measures.get("england") or {}).get(DEFAULT_MEASURE, {}).get(year)
    data = {"measures": "/data/map/measures.json", "schools": "/data/map/schools.json",
            "council": "/data/map/councils.geojson" if has_councils else None,
            "constituency": "/data/map/constituencies.geojson" if has_constituencies else None}
    page_ctx = dict(ctx, years=years, defaults={"m": DEFAULT_MEASURE, "y": year, "g": "council"},
                    measures=meta, data=data, fbit="https://financial-benchmarking-and-insights-tool.education.gov.uk/school/")
    missing = "" if has_councils else (
        '<p class="mx-note" role="status">Council boundaries aren\'t available just now, so the map can\'t colour '
        'councils. The table below still lists every council.</p>')
    noscript = ('<noscript><p class="mx-note">The map needs JavaScript. The table below lists every council, and every '
                'council has its own page: <a href="/council/">browse councils</a>.</p></noscript>')
    map_div = (f'<div id="money-map" class="mx-map" role="region" aria-label="Map of England coloured by the chosen measure" '
               f'data-tiles="{TILES_URL}" data-default-measure="{DEFAULT_MEASURE}" data-default-year="{site.esc(year or "")}" '
               f'data-years="{_json_attr(years)}">{noscript}</div>')
    card = ('<div id="mx-card" class="mx-card" role="dialog" aria-modal="false" aria-labelledby="mx-card-title" hidden>'
            '<button type="button" class="mx-close" aria-label="Close card"><span aria-hidden="true">×</span></button>'
            '<div class="mx-card-body"></div></div>')
    legend = ('<div id="mx-legend" class="mx-legend" role="region" aria-live="polite" aria-label="Map key">'
              f'<p class="small muted">{site.esc(CASH_NOTE)}</p></div>')
    table = _table(measures["council"], measure, year, england_value, "council", True, "mx-table")
    return (
        '<h1>School money map</h1>'
        '<p class="lead">See how school budgets compare across England, council by council or constituency by constituency. '
        'Pick a measure and a year, then tap an area or a school for its figures.</p>'
        f'{_controls(meta, years, year, DEFAULT_MEASURE)}{missing}'
        f'<div class="mx-stage">{map_div}{card}</div>{legend}'
        f'{_why_html(ctx)}'
        f'<section class="mx-tablebox" aria-labelledby="mx-table-h"><h2 id="mx-table-h">Every council</h2>'
        '<p class="small muted">The same figures as the map, as a table you can sort. '
        '<a href="/map/constituencies/">See every constituency</a>.</p>'
        f'{table}</section>'
        f'<script type="application/json" id="mx-context">{_json_script(page_ctx)}</script>'
    )


def constituencies_body(measures, ctx):
    """/map/constituencies/: every constituency for the default measure and year (the no-JS view)."""
    meta = dict(measures["measures"][DEFAULT_MEASURE], key=DEFAULT_MEASURE)
    year = default_year(measures)
    england_value = (measures.get("england") or {}).get(DEFAULT_MEASURE, {}).get(year)
    return (
        '<h1>School money by constituency</h1>'
        '<p class="lead">The share of schools in deficit in every parliamentary constituency in England. '
        'Search for a constituency to open its page, or <a href="/map/">use the map</a> to change the measure and year.</p>'
        f'{_why_html(ctx)}'
        f'<section class="mx-tablebox" aria-label="Every constituency">'
        f'{_table(measures["constituency"], meta, year, england_value, "constituency", False, "mx-ctable")}</section>'
    )


def _og(env, path):
    og = env.get("og_image")
    if callable(og):
        try:
            og = og(path)
        except TypeError:
            og = None
    return og if isinstance(og, str) and og else None


def _write_data(out, name, text):
    folder = Path(out) / "data" / "map"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def _boundaries(path, rel):
    if path is not None:
        path = Path(path)
        return path if path.is_file() else None
    return resolve(rel)


def write_pages(env, *, councils_path=None, constituencies_path=None):
    """Write the map pages and /data/map/*; returns [(path, indexable)] in write order."""
    out = Path(env["out"])
    measures = build_measures(env.get("areas") or {})
    _write_data(out, "measures.json", _dumps(dict(measures, generated=env.get("today"))))
    _write_data(out, "schools.json", _dumps(build_schools(env.get("items") or [])))

    has = {}
    for name, path, rel, prefix, key, budget, simplify in (
            ("councils.geojson", councils_path, COUNCILS_SRC, "council-", "la_code", COUNCILS_BUDGET, False),
            ("constituencies.geojson", constituencies_path, CONSTITUENCIES_SRC, "constituency-", "code", CONSTITUENCIES_BUDGET, True)):
        src = _boundaries(path, rel)
        doc = _load_json(src) if src else None
        has[name] = bool(doc and doc.get("features"))
        if has[name]:
            _write_data(out, name, build_geojson(doc["features"], prefix, key, budget, simplify))

    ctx = map_context()
    written = []
    title = "School money map: deficits, reserves and funding by area"
    description = ("A map of England's school finances by council and constituency: the share of schools in deficit, "
                   "reserves, funding and spending per pupil, from DfE returns.")
    body = map_body(measures, ctx, has_councils=has["councils.geojson"], has_constituencies=has["constituencies.geojson"])
    env["write"]("/map/", env["page"](title, description, "/map/", body, [("Home", "/"), ("Map", "/map/")],
                                       og_image=_og(env, "/map/"), indexable=True, extra_head=_head()))
    written.append(("/map/", True))

    path = "/map/constituencies/"
    env["write"](path, env["page"](
        "School money by constituency", "The share of schools in deficit in every parliamentary constituency in England, from DfE returns.",
        path, constituencies_body(measures, ctx), [("Home", "/"), ("Map", "/map/"), ("Constituencies", path)],
        og_image=_og(env, path), indexable=True, extra_head=_head(with_map=False)))
    written.append((path, True))
    return written
