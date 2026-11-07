"""Area aggregates and socio-economic context for School Money.

Two jobs:

* school_profile(school, council_code, data_root): tags (governance, trust, admissions,
  faith...), intake (free school meals against the council and England medians) and
  the neighbourhood the school sits in (English Indices of Deprivation deciles and
  Census 2021 figures for its LSOA, the same figures averaged over the LSOAs inside
  the last distance it offered a place to, and the ONS income estimate for its MSOA).

* build_areas(...): for England, each region, each council, each constituency and each
  academy trust, the yearly picture: how many schools, pupils, deficits, the median
  per-pupil figures (cash and real terms), split into all / council-run (CFR returns) /
  academy (AAR returns), plus the council's high-needs (DSG) balance per pupil, and a
  national parents' association (PTA) summary.

Combined series. CFR years run April to March and AAR years September to August, and
academy accounts arrive a year later than council returns, so the latest CFR year has
no academy figures yet. The "all" split therefore stops at the last year with academy
returns (2024-25); later years keep only their council-run split, and "all" is None.

PTA years. A charity return goes in the school year containing its period end: April to
March for a council-run school, September to August for an academy, judged by the
school's own return for that year (else its nearest year's). A charity shared by
several schools is split equally between them. Review-flagged charities, and any with a
year's income over HOLD_ABOVE (almost always a mismatch with an independent school's
foundation), are held back from every total, median and ranking.

Band. Every school with both a free-school-meals percentage and an IDACI decile is
ranked twice nationally: once by FSM % (low to high) and once by IDACI decile after
inverting it (the Indices put decile 1 as the most deprived, so 11 - decile puts the
most deprived neighbourhoods last). The two ranks are averaged and the schools cut
into five equal groups. Band 1 holds the fifth of schools whose intake looks least
disadvantaged on both measures; band 5 the most. Pages should word this neutrally,
"a more affluent intake" / "a less affluent intake", never as a judgement of the
school or its families, and should say both inputs: who the pupils are (FSM) and
where the school stands (IDACI), since a school can draw from far beyond its street.

Deciles in lsoa.geojson follow the Indices: 1 = most deprived tenth of England.
Distances in admissions.json are miles; over 7 miles means everyone who applied was
offered a place, so no real catchment exists and it is skipped. A catchment is the set
of LSOAs whose geometric centroid lies within that distance, from the school's own
council and any neighbouring council whose las.json bbox reaches the point; the
school's own LSOA is included only when its centroid qualifies like any other.

Stdlib only. Every loader takes a path and tolerates a missing file.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from pipeline.money import status as health
from pipeline.money.timeline import status_by_year

try:
    from pipeline.money import deflator
except ImportError:  # pragma: no cover - deflator.py ships with the money package
    deflator = None

try:  # finance-series (series.py) owns the PTA year rule; pta_year() below keeps a copy
    from pipeline.money.series import pta_year as series_pta_year
except ImportError:
    series_pta_year = None

try:  # build_money owns these; keep a tiny fallback so this module imports on its own
    from pipeline.money.build_money import reserve_of, per_pupil
except ImportError:  # pragma: no cover - exercised only when build_money is absent
    def reserve_of(row):
        value = row.get("revenue_reserve_incl_trust_share")
        return row.get("revenue_reserve") if value is None else value

    def per_pupil(row, key):
        value, pupils = (row or {}).get(key), (row or {}).get("pupils")
        return value / pupils if value is not None and pupils else None

try:
    from pipeline.seo.build_pages import closed, slug
except ImportError:  # pragma: no cover
    import re
    import unicodedata

    def closed(*records):
        return any(r.get("open") is False or any("closed" in str(r.get(k, "")).lower()
                   for k in ("status", "school_status", "establishment_status")) for r in records)

    def slug(value):
        text = unicodedata.normalize("NFKD", str(value).replace("&", " and "))
        text = text.encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:80].rstrip("-") or "school"

ROOT = Path(__file__).resolve().parents[2]
REAL_ROOT = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
DEFAULT_SITE_DATA = REAL_ROOT / "site/data"
DEFAULT_HISTORY = REAL_ROOT / "pipeline/.cache/dfe/finance_history.jsonl"
DEFAULT_LINKS = REAL_ROOT / "pipeline/.cache/dfe/gias/links.csv"
DEFAULT_PTA = REAL_ROOT / "pipeline/.cache/money/pta.json"
DEFAULT_OUT = REAL_ROOT / "pipeline/.cache/money/areas.json"
DATA_DIR = ROOT / "pipeline/money/data"
DSG_PATH = DATA_DIR / "la_dsg.json"
MSOA_INCOME_PATH = REAL_ROOT / "pipeline/money/data/msoa_income.json"
CONSTITUENCIES_PATH = DATA_DIR / "constituencies_2024.json"

AREA_KEYS = ["imd_decile", "idaci_decile", "income_decile", "pct_level4_plus", "pct_owned",
             "pct_social_rented", "pct_households_not_deprived"]
MIN_SCHOOLS = 5              # fewer than this and an area's statistics are withheld
EVERYONE_OFFERED_MILES = 7   # beyond this the "last distance offered" means no cut-off
KM_PER_MILE = 1.609344
SPLITS = {"all": None, "council-run": "CFR", "academy": "AAR"}
S_KEYS = ["schools", "in_deficit", "in_deficit_pct", "heading", "deficit_total", "deficit_pp", "reserve_median_pp",
          "income_pp_median", "spend_pp_median", "grant_pp_median", "pta_pp_median", "pta_schools", "donations_pp_median",
          "statuses", "gov_pp_median", "gov_rpp_median", "spend_rpp_median", "reserve_median_rpp", "fsm_pct", "pupils"]
HOLD_ABOVE = 500_000         # a parents' association with a year's income above this is held for review
TOP_PTA = 20                 # biggest fundraisers kept, by total and by per pupil


# ----------------------------------------------------------------- loaders

def load_json(path, default=None):
    """Parse a JSON file, or return default when it is missing or unreadable."""
    path = Path(path) if path else None
    if not path or not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def load_las(data_root):
    doc = load_json(Path(data_root) / "england/las.json", {}) or {}
    return {str(la["la_code"]): la for la in doc.get("las", []) if la.get("la_code") is not None}


def load_register(data_root, council_code):
    doc = load_json(Path(data_root) / "la" / str(council_code) / "schools.json", {}) or {}
    return [s for s in doc.get("schools", []) if not closed(s)]


def load_characteristics(data_root, council_code):
    doc = load_json(Path(data_root) / "la" / str(council_code) / "characteristics.json", {}) or {}
    return {str(k): v for k, v in (doc.get("schools") or {}).items()}


def load_admissions(data_root, council_code):
    """{urn: {year: max_distance}} merged over the primary and secondary records."""
    doc = load_json(Path(data_root) / "la" / str(council_code) / "admissions.json", {}) or {}
    out = {}
    for key in ("primary", "secondary"):
        for urn, record in (doc.get(key) or {}).items():
            years = (record or {}).get("years") or {}
            out.setdefault(str(urn), {}).update({str(y): (v or {}).get("max_distance") for y, v in years.items()})
    return out


def load_lsoas(data_root, council_code):
    """{lsoa code: {"centroid": (lat, lon), <AREA_KEYS>...}} for one council."""
    doc = load_json(Path(data_root) / "la" / str(council_code) / "lsoa.geojson", {}) or {}
    out = {}
    for feature in doc.get("features", []):
        props = feature.get("properties") or {}
        code = props.get("lsoa21cd") or props.get("lsoa11cd") or props.get("code")
        if not code:
            continue
        entry = {k: props.get(k) for k in AREA_KEYS}
        entry["centroid"] = centroid(feature.get("geometry") or {})
        out[str(code)] = entry
    return out


def load_msoa_income(path=MSOA_INCOME_PATH):
    """{msoa code: annual net income £}. Accepts the flat {code: £} shape or the ONS
    extract {"msoa": {code: {"net_income_ahc", "total_annual_income", ...}}}."""
    doc = load_json(path)
    if not isinstance(doc, dict):
        return {}
    table = doc.get("msoa") if isinstance(doc.get("msoa"), dict) else doc
    out = {}
    for code, value in table.items():
        if isinstance(value, dict):
            value = value.get("net_income_ahc", value.get("total_annual_income"))
        if isinstance(value, (int, float)):
            out[str(code)] = int(round(value))
    return out


def load_constituency_codes(path=CONSTITUENCIES_PATH):
    """{constituency name: code}. Accepts {name: code} or {code: {"name": ...}}."""
    doc = load_json(path)
    if not isinstance(doc, dict):
        return {}
    out = {}
    for key, value in doc.items():
        if isinstance(value, dict) and value.get("name"):
            out[str(value["name"])] = str(key)
        elif isinstance(value, str):
            out[str(key)] = value
    return out


# ----------------------------------------------------------------- geometry

def centroid(geometry):
    """Geometric centroid of a GeoJSON geometry as (lat, lon).

    Uses the shoelace formula on each outer ring (area weighted across a MultiPolygon),
    treating degrees as planar, which is fine at LSOA scale. Averaging the vertices
    instead would pull the point towards whichever edge was digitised most finely,
    so a long thin LSOA could land inside a catchment its real centre is well outside."""
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if not coords:
        return None
    if kind == "Point":
        return (coords[1], coords[0])
    if kind == "Polygon":
        rings = [coords[0]] if coords and coords[0] else []
    elif kind == "MultiPolygon":
        rings = [poly[0] for poly in coords if poly and poly[0]]
    else:
        return None
    area_sum = lon_sum = lat_sum = 0.0
    vertices = []
    for ring in rings:
        pts = [p for p in ring if len(p) >= 2]
        if len(pts) > 1 and pts[0][:2] == pts[-1][:2]:
            pts = pts[:-1]  # the closing vertex repeats the first
        vertices.extend(pts)
        if len(pts) < 3:
            continue
        twice_area = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip([q[:2] for q in pts], [q[:2] for q in pts[1:] + pts[:1]]):
            cross = x0 * y1 - x1 * y0
            twice_area += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        if twice_area:
            area = twice_area / 2
            area_sum += abs(area)
            lon_sum += abs(area) * cx / (3 * twice_area)
            lat_sum += abs(area) * cy / (3 * twice_area)
    if area_sum:
        return (lat_sum / area_sum, lon_sum / area_sum)
    if vertices:  # degenerate (zero area): fall back to the vertex mean
        return (sum(p[1] for p in vertices) / len(vertices), sum(p[0] for p in vertices) / len(vertices))
    return None


def haversine_km(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


# ----------------------------------------------------------------- tags

def governance(school):
    kind = str(school.get("type") or "")
    group = str(school.get("type_group") or "")
    if kind.lower().startswith("free school") or group.lower().startswith("free school"):
        return "free school"
    if kind.lower().startswith("academ") or group.lower().startswith("academ"):
        return "academy"
    if group == "Independent schools" or "independent" in kind.lower():
        return "independent"
    return "council-run"


def admissions_tag(school):
    policy = str(school.get("admissions_policy") or "").strip().lower()
    return {"selective": "grammar", "partially selective": "partially selective", "non-selective": "non-selective"}.get(policy)


def faith_tag(school):
    for key in ("religious_character", "religious_ethos"):
        value = (school.get(key) or "").strip()
        if value and value.lower() not in ("none", "does not apply", "not applicable"):
            return value
    return None


def trust_name(school):
    return (school.get("trust") or "").strip() or None


def school_fsm(school, characteristics):
    rec = characteristics.get(str(school.get("urn")), {}) if characteristics else {}
    fsm = (rec.get("fsm") or {}).get("eligible_pct") if isinstance(rec, dict) else None
    if fsm is None:
        fsm = school.get("fsm_pct")
    return float(fsm) if isinstance(fsm, (int, float)) else None


def latest_distance(years):
    """Most recent numeric max_distance (miles); None when missing, banded or over 7 miles."""
    for year in sorted(years or {}, reverse=True):
        value = years[year]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return None if value > EVERYONE_OFFERED_MILES else float(value)
    return None


def median_or_none(values, minimum=1):
    values = sorted(v for v in values if v is not None)
    n = len(values)
    if n < max(minimum, 1):
        return None
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2


def average_rank(sorted_values, value):
    """Average rank (1-based) of value among sorted_values, ties sharing their mean rank."""
    lo = bisect.bisect_left(sorted_values, value)
    hi = bisect.bisect_right(sorted_values, value)
    return (lo + hi + 1) / 2


# ----------------------------------------------------------------- profile context

class Context:
    """Per data_root cache of registers, LSOAs and the national band thresholds.
    Built lazily; a4 can profile 20,000 schools without re-reading any file."""

    def __init__(self, data_root, schools=None, msoa_income_path=MSOA_INCOME_PATH):
        self.data_root = Path(data_root)
        self.las = load_las(self.data_root)
        self.schools = schools
        self.msoa_income_path = msoa_income_path
        self._registers = {}
        self._characteristics = {}
        self._admissions = {}
        self._lsoas = {}
        self._msoa_income = None
        self._national = None
        self._fsm_england = None
        self._trust_counts = None

    def register(self, code):
        if code not in self._registers:
            self._registers[code] = load_register(self.data_root, code)
        return self._registers[code]

    def characteristics(self, code):
        if code not in self._characteristics:
            self._characteristics[code] = load_characteristics(self.data_root, code)
        return self._characteristics[code]

    def admissions(self, code):
        if code not in self._admissions:
            self._admissions[code] = load_admissions(self.data_root, code)
        return self._admissions[code]

    def lsoas(self, code):
        if code not in self._lsoas:
            self._lsoas[code] = load_lsoas(self.data_root, code)
        return self._lsoas[code]

    def councils_near(self, code, lat, lon, radius_km):
        """Council codes whose LSOAs might have a centroid within radius_km of (lat, lon):
        the school's own council plus every council whose las.json bbox, grown by the
        radius, contains the point. Councils without a bbox are always included."""
        out = [code] if code else []
        lat_margin = radius_km / 111.0 + 1e-6
        lon_margin = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01)) + 1e-6
        for other in self.council_codes():
            if other in out:
                continue
            bbox = (self.las.get(other) or {}).get("bbox")
            if bbox and len(bbox) == 4:
                west, south, east, north = bbox
                if not (south - lat_margin <= lat <= north + lat_margin
                        and west - lon_margin <= lon <= east + lon_margin):
                    continue
            out.append(other)
        return out

    def lsoas_near(self, code, lat, lon, radius_km):
        """{lsoa code: feature} across every council that could hold an LSOA centroid
        within radius_km of the point; catchments do not stop at council borders."""
        merged = {}
        for other in self.councils_near(code, lat, lon, radius_km):
            merged.update(self.lsoas(other))
        return merged

    @property
    def msoa_income(self):
        if self._msoa_income is None:
            self._msoa_income = load_msoa_income(self.msoa_income_path)
        return self._msoa_income

    def council_codes(self):
        if self.las:
            return [c for c in self.las if (self.data_root / "la" / c / "schools.json").is_file()]
        la_dir = self.data_root / "la"
        return sorted(p.name for p in la_dir.iterdir() if (p / "schools.json").is_file()) if la_dir.is_dir() else []

    def all_schools(self):
        """[(school, council code)] for the schools passed in, else every open school in every register."""
        if self.schools is not None:
            return [(s, council_of(s)) for s in self.schools]
        return [(s, code) for code in self.council_codes() for s in self.register(code)]

    def fsm_of(self, school, code):
        return school_fsm(school, self.characteristics(code) if code else {})

    def trust_count(self, name):
        if self._trust_counts is None:
            self._trust_counts = Counter(trust_name(s) for s, _ in self.all_schools())
        return self._trust_counts.get(name, 0)

    def fsm_council(self, code):
        pool = [s for s, c in self.all_schools() if c == code] if self.schools is not None else self.register(code)
        return median_or_none(self.fsm_of(s, code) for s in pool)

    def fsm_england(self):
        if self._fsm_england is None:
            self._fsm_england = median_or_none(self.fsm_of(s, c) for s, c in self.all_schools())
        return self._fsm_england

    def national(self):
        """Sorted FSM values, sorted inverted IDACI deciles and the four quintile cut points
        of the combined rank, over every school with both measures."""
        if self._national is None:
            fsm_values, idaci_values, pairs = [], [], []
            for school, code in self.all_schools():
                fsm = self.fsm_of(school, code)
                feature = self.lsoas(code).get(str(school.get("lsoa") or "")) if code else None
                idaci = (feature or {}).get("idaci_decile")
                if fsm is None or idaci is None:
                    continue
                fsm_values.append(fsm)
                idaci_values.append(11 - idaci)
                pairs.append((fsm, 11 - idaci))
            fsm_values.sort()
            idaci_values.sort()
            scores = sorted(combined_rank(fsm_values, idaci_values, f, i) for f, i in pairs)
            cuts = [scores[int(len(scores) * q / 5)] for q in range(1, 5)] if len(scores) >= 5 else []
            self._national = (fsm_values, idaci_values, cuts)
        return self._national

    def band(self, fsm, idaci):
        if fsm is None or idaci is None:
            return None
        fsm_values, idaci_values, cuts = self.national()
        if not cuts:
            return None
        return 1 + bisect.bisect_right(cuts, combined_rank(fsm_values, idaci_values, fsm, 11 - idaci))


def combined_rank(fsm_sorted, idaci_sorted, fsm, idaci_inverted):
    return (average_rank(fsm_sorted, fsm) + average_rank(idaci_sorted, idaci_inverted)) / 2


_contexts = {}


def context(data_root, schools=None):
    """The shared Context for data_root. Passing schools builds a fresh one over that list."""
    key = str(Path(data_root).resolve())
    if schools is not None:
        return Context(data_root, schools)
    if key not in _contexts:
        _contexts[key] = Context(data_root)
    return _contexts[key]


def council_of(school, rows=None):
    """Council code for a register entry: an explicit la_code/la, else the first three
    digits of its LAESTAB, else the finance rows' la."""
    for key in ("la_code", "la", "council_code"):
        if school.get(key) not in (None, ""):
            return str(school[key])
    laestab = str(school.get("laestab") or "")
    if len(laestab) >= 7 and laestab[:3].isdigit():
        return laestab[:3]
    for r in rows or []:
        if r.get("la") not in (None, ""):
            return str(r["la"])
    return None


# ----------------------------------------------------------------- school profile

def school_profile(school, council_code, data_root, schools=None, ctx=None):
    """Tags, intake and area for one register entry. See the module docstring for band."""
    ctx = ctx or context(data_root, schools)
    code = str(council_code) if council_code is not None else council_of(school)
    name = trust_name(school)
    gov = governance(school)
    phase = str(school.get("phase") or "")
    fsm = ctx.fsm_of(school, code)
    tags = {
        "governance": gov,
        "trust": name,
        "trust_size": None if not name else ("multi" if ctx.trust_count(name) > 1 else "single"),
        "admissions": admissions_tag(school),
        "faith": faith_tag(school),
        "phase": phase,
        "gender": str(school.get("gender") or ""),
        "sixth_form": bool(school.get("sixth_form")),
    }
    intake = {
        "fsm_pct": fsm,
        "fsm_pct_council": ctx.fsm_council(code) if code else None,
        "fsm_pct_england": ctx.fsm_england(),
    }
    lsoas = ctx.lsoas(code) if code else {}
    lsoa = str(school.get("lsoa") or "") or None
    own = lsoas.get(lsoa) if lsoa else None
    area = {"lsoa": lsoa}
    area.update({k: (own or {}).get(k) for k in AREA_KEYS})
    miles = latest_distance((ctx.admissions(code) if code else {}).get(str(school.get("urn")), {}))
    lat, lon = school.get("lat"), school.get("lon")
    near = ctx.lsoas_near(code, lat, lon, miles * KM_PER_MILE) if None not in (miles, lat, lon) else {}
    area["catchment"] = catchment(school, miles, near)
    msoa = str(school.get("msoa") or "")
    area["msoa_income"] = ctx.msoa_income.get(msoa) if msoa else None
    return {"tags": tags, "intake": intake, "area": area, "band": ctx.band(fsm, area.get("idaci_decile"))}


def catchment(school, miles, lsoas):
    """AREA_KEYS averaged over the LSOAs (from any council) whose centroid lies within
    miles of the school, with the distance and count used. The school's own LSOA gets
    no special treatment: a school on the edge of a large LSOA whose centre is beyond
    the distance it offered places to does not draw its pupils from that whole area."""
    lat, lon = school.get("lat"), school.get("lon")
    if miles is None or lat is None or lon is None:
        return None
    radius_km = miles * KM_PER_MILE
    picked = []
    for feature in lsoas.values():
        c = feature.get("centroid")
        if c and haversine_km(lat, lon, c[0], c[1]) <= radius_km:
            picked.append(feature)
    if not picked:
        return None
    out = {}
    for key in AREA_KEYS:
        values = [f.get(key) for f in picked if isinstance(f.get(key), (int, float))]
        out[key] = round(sum(values) / len(values), 1) if values else None
    out["distance_miles"] = miles
    out["lsoas"] = len(picked)
    return out


# ----------------------------------------------------------------- area aggregates

def pta_income_for(charities, end_year):
    """Combined income of a school's PTAs for the financial period ending in calendar
    year end_year. Charities shared with other schools contribute an equal share.
    Kept for older callers; build_areas uses the school-year rule in school_pta()."""
    total, found = 0.0, False
    for charity in charities or []:
        if charity.get("review"):
            continue
        share = 1 + len(charity.get("shared_with") or [])
        for h in charity.get("history") or []:
            if str(h.get("period_end") or "")[:4] == str(end_year) and h.get("income") is not None:
                total += h["income"] / share
                found = True
                break
    return total if found else None


def end_year_of(label):
    """"2024-25" -> 2025."""
    head, _, tail = label.partition("-")
    return int(head[:2] + tail) if len(tail) == 2 else int(tail or head)


def local_pta_year(period_end, source):
    """School year label ("2022-23") holding a charity return that ended period_end ("YYYY-MM").
    Council-run (CFR) years run April to March, academy (AAR) years September to August."""
    text = str(period_end or "")
    try:
        year, month = int(text[:4]), int(text[5:7])
    except ValueError:
        return None
    first_month = 9 if str(source).upper() == "AAR" else 4
    start = year if month >= first_month else year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def pta_year(period_end, source):
    """series.pta_year when finance-series is present, else the local copy (same contract)."""
    if series_pta_year is not None:
        try:
            return series_pta_year(period_end, source)
        except (TypeError, ValueError, KeyError):
            pass
    return local_pta_year(period_end, source)


def _months(period_end):
    text = str(period_end or "")
    try:
        return int(text[:4]) * 12 + int(text[5:7])
    except ValueError:
        return None


def return_source(period_end, years):
    """The source ("CFR"/"AAR") of the school's own return for the year holding period_end,
    else of its nearest return in time; CFR when the school has no returns."""
    for r in reversed(years):
        if pta_year(period_end, r.get("source")) == label_of(r):
            return r.get("source")
    target = _months(period_end)
    dated = [r for r in years if _months(r.get("period_end")) is not None]
    if target is None or not dated:
        return "CFR"
    return min(dated, key=lambda r: (abs(_months(r["period_end"]) - target), -_months(r["period_end"])))["source"]


def label_of(row):
    return str(row.get("year") or "").replace("/", "-")


def held_back(charity):
    """Review-flagged charities, and any with a year's income over HOLD_ABOVE, are never counted."""
    if charity.get("review"):
        return True
    return any((h.get("income") or 0) > HOLD_ABOVE for h in charity.get("history") or [])


def school_pta(years, charities):
    """{(year label, source): {"income", "spend", "by_charity": {number: income}, "names": {number: name},
    "confidence"}} for one school's PTAs, by the school-year rule (module docstring). Shared
    charities count 1 / (1 + len(shared_with)) here. Held-back charities are skipped."""
    out = {}
    for charity in charities or []:
        if held_back(charity):
            continue
        share = 1 + len(charity.get("shared_with") or [])
        number = charity.get("charity_number")
        seen = set()
        for h in charity.get("history") or []:
            end = str(h.get("period_end") or "")[:7]
            if h.get("income") is None or not end:
                continue
            source = return_source(end, years)
            label = pta_year(end, source)
            if not label or label in seen:  # two returns in one school year: keep the first listed (newest)
                continue
            seen.add(label)
            slot = out.setdefault((label, source), {"income": 0.0, "spend": None, "by_charity": {}, "names": {},
                                                    "confidence": "high"})
            slot["income"] += h["income"] / share
            if h.get("expenditure") is not None:
                slot["spend"] = (slot["spend"] or 0.0) + h["expenditure"] / share
            slot["by_charity"][number] = slot["by_charity"].get(number, 0.0) + h["income"] / share
            slot["names"][number] = charity.get("name")
            if ((charity.get("match") or {}).get("confidence") or "high") != "high":
                slot["confidence"] = "medium"
    return out


def _usable(row, key, suspect):
    value = row.get(key)
    return None if key in suspect or not isinstance(value, (int, float)) or isinstance(value, bool) else value


def _real(value, row):
    """value in BASE_YEAR prices by the row's own source (CFR financial year, AAR academic year)."""
    if value is None or deflator is None:
        return None
    try:
        return deflator.to_real(value, row.get("year"), row.get("source") or "CFR")
    except (KeyError, TypeError, ValueError):
        return None


def government_funding(row, suspect=()):
    """AAR grant_funding_government, CFR grant_funding (the row key grant_funding_government holds
    the right one for both once finance-series has run; older CFR rows only carry grant_funding)."""
    value = _usable(row, "grant_funding_government", suspect)
    if value is None and row.get("source") == "CFR" and "grant_funding_government" not in suspect:
        value = _usable(row, "grant_funding", suspect)
    return value


def school_years(rows, charities):
    """One entry per full year for a school: the inputs summarise() needs.

    status_by_year() walks status.full_years() in order and always yields one point per
    full year (the year itself is in the rows it assesses), so the two lists are paired
    by position. Pairing by display label would be wrong: in a conversion year a March
    CFR return and an August AAR return both read "2024-25", and the academy's pupils
    and spending would be stitched onto the council-run return's reserve and status.

    Values the finance pipeline marked suspect (row["suspect"]) are left out of the
    per-pupil inputs, so they never reach a median."""
    years = health.full_years(rows)
    points = status_by_year(rows)
    if len(points) != len(years):  # pragma: no cover - guards the invariant above
        raise ValueError(f"status_by_year gave {len(points)} points for {len(years)} full years")
    pta = school_pta(years, charities)
    out = []
    for r, point in zip(years, points):
        suspect = set(r.get("suspect") or [])
        pupils = r.get("pupils") or None
        pp_pupils = None if "pupils" in suspect else pupils

        def pp(value):
            return value / pp_pupils if value is not None and pp_pupils else None

        reserve_ok = not suspect & {"revenue_reserve", "revenue_reserve_incl_trust_share"}
        reserve_pp = point["reserve_pp"] if reserve_ok and pp_pupils else None
        gov = government_funding(r, suspect)
        spend = _usable(r, "total_expenditure", suspect)
        own_pta = pta.get((point["year"], r.get("source")))
        out.append({
            "year": point["year"], "source": r.get("source"), "status": point["status"],
            "reserve": point["reserve"], "reserve_pp": reserve_pp, "pupils": pupils, "pp_pupils": pp_pupils,
            "income_pp": pp(_usable(r, "total_income", suspect)), "spend_pp": pp(spend),
            "grant_pp": pp(_usable(r, "grant_funding", suspect)),
            "gov_pp": pp(gov), "gov_rpp": pp(_real(gov, r)), "spend_rpp": pp(_real(spend, r)),
            "reserve_rpp": pp(_real(point["reserve"], r)) if reserve_pp is not None else None,
            "pta_pp": pp(own_pta["income"]) if own_pta else None,
            "donations_pp": pp(_usable(r, "donations_revenue", suspect)),
            "fsm_pct": _usable(r, "fsm_pct", suspect),
            "trust": (r.get("trust") or "").strip() or None, "company_number": r.get("company_number"),
            "central_pp": _usable(r, "trust_central_spend_per_pupil", suspect) or None,  # 0 = not reported
            "period_end": r.get("period_end"), "phase": r.get("phase"),
        })
    return out


def summarise(entries):
    """S over a list of per-school-year entries (see school_years)."""
    n = len(entries)
    if n < MIN_SCHOOLS:
        return {k: (n if k == "schools" else None) for k in S_KEYS}
    deficits = [e for e in entries if e["reserve"] is not None and e["reserve"] < 0]
    deficit_total = sum(e["reserve"] for e in deficits)
    deficit_pupils = sum(e["pupils"] or 0 for e in deficits)
    pta = [e["pta_pp"] for e in entries if e.get("pta_pp") is not None]

    def med(key):
        return median_or_none([e.get(key) for e in entries])

    return {
        "schools": n,
        "in_deficit": len(deficits),
        "in_deficit_pct": round(100 * len(deficits) / n, 1),
        "heading": sum(1 for e in entries if e["status"] == "heading_for_deficit"),
        "deficit_total": deficit_total,
        "deficit_pp": deficit_total / deficit_pupils if deficit_pupils else None,
        "reserve_median_pp": med("reserve_pp"),
        "income_pp_median": med("income_pp"),
        "spend_pp_median": med("spend_pp"),
        "grant_pp_median": med("grant_pp"),
        "pta_pp_median": median_or_none(pta, MIN_SCHOOLS),
        "pta_schools": len(pta),
        "donations_pp_median": med("donations_pp"),
        "statuses": dict(Counter(e["status"] for e in entries if e.get("status"))),
        "gov_pp_median": med("gov_pp"),
        "gov_rpp_median": med("gov_rpp"),
        "spend_rpp_median": med("spend_rpp"),
        "reserve_median_rpp": med("reserve_rpp"),
        "fsm_pct": med("fsm_pct"),
        "pupils": sum(e["pupils"] or 0 for e in entries),
    }


def new_area(name):
    return {"name": name, "pupils_by_year": {}, "schools_by_year": {}, "by_year": {}, "dsg": {}, "statuses_latest": {},
            "combined_last_year": None, "dsg_pupils_by_year": {}}


def carried_pupils(per_school_years):
    """Pupils per year where a school without a return that year counts its previous year's
    roll (one year only), so the newest DSG year still divides by every school's pupils."""
    years = sorted({y for own in per_school_years for y in own})
    totals = {}
    for n, year in enumerate(years):
        previous = years[n - 1] if n else None
        total = 0
        for own in per_school_years:
            value = own.get(year)
            if value is None and previous is not None:
                value = own.get(previous)
            total += value or 0
        totals[year] = total
    return totals


def fill_area(area, items, combined_last):
    """by_year, pupils, schools and statuses for one area from [(entries, latest status)]."""
    per_year = defaultdict(list)          # every return ending in the year (feeds the source splits)
    per_year_schools = defaultdict(list)  # one entry per school per year, its latest return
    rolls = []
    for entries, latest in items:
        if latest:
            area["statuses_latest"][latest] = area["statuses_latest"].get(latest, 0) + 1
        last_by_year = {}
        for e in entries:
            per_year[e["year"]].append(e)
            last_by_year[e["year"]] = e  # entries are oldest first
        for year, e in last_by_year.items():
            per_year_schools[year].append(e)
        rolls.append({y: e["pupils"] for y, e in last_by_year.items() if e["pupils"]})
    area["combined_last_year"] = combined_last
    for year in sorted(per_year):
        entries, per_school = per_year[year], per_year_schools[year]
        combined = combined_last is None or year <= combined_last
        if combined:
            area["pupils_by_year"][year] = sum(e["pupils"] or 0 for e in per_school)
            area["schools_by_year"][year] = len(per_school)
        area["by_year"][year] = {split: (summarise(per_school) if combined else None) if source is None
                                 else summarise([e for e in entries if e["source"] == source])
                                 for split, source in SPLITS.items()}
    area["dsg_pupils_by_year"] = carried_pupils(rolls)


def fill_dsg(area, values):
    pupils = area["dsg_pupils_by_year"]
    for year, balance in sorted((values or {}).items()):
        roll = pupils.get(year)
        area["dsg"][year] = {"balance": balance, "per_pupil": balance / roll if balance is not None and roll else None}


def trust_key(entry, register_trust):
    """(group id, name) of the trust an academy return belongs to: company number when known."""
    name = entry["trust"] or register_trust
    number = entry["company_number"]
    if number not in (None, ""):
        return f"company:{number}", name
    return (f"name:{name.casefold()}", name) if name else (None, None)


def build_trusts(trust_items, trust_names, central):
    """{slug: A + company_number, central_pp, path} for every trust with an academy return."""
    out = {}
    for group, items in sorted(trust_items.items(), key=lambda kv: str(trust_names.get(kv[0]) or kv[0])):
        name = trust_names.get(group) or group.partition(":")[2]
        number = group.partition(":")[2] if group.startswith("company:") else None
        key = slug(name)
        if key in out:  # two trusts with one slug: tell them apart by company number
            key = f"{key}-{slug(number or len(out))}"
        area = new_area(name)
        fill_area(area, items, None)
        area["company_number"] = number
        area["central_pp"] = {y: round(statistics.median(v)) for y, v in sorted(central.get(group, {}).items()) if v}
        area["path"] = f"/trust/{key}/"
        out[key] = area
    return out


def school_band(ctx, school, code):
    """The school's intake band (1-5): the register's own when given, else areas' national ranking."""
    band = school.get("band")
    if isinstance(band, int) and 1 <= band <= 5:
        return band
    if ctx is None or not code:
        return None
    try:
        feature = ctx.lsoas(code).get(str(school.get("lsoa") or "")) or {}
        return ctx.band(ctx.fsm_of(school, code), feature.get("idaci_decile"))
    except (OSError, ValueError, TypeError):
        return None


def phase_tag(row_phase, school):
    text = str(row_phase or school.get("phase") or "").strip().lower().replace("-", " ")
    return {"primary": "primary", "secondary": "secondary", "special": "special", "all through": "all-through",
            "nursery": "nursery"}.get(text, "other" if text else None)


def pta_window(by_year):
    """(first, newest) school years whose returns count as a school's "latest": the newest year
    with at least 60% as many schools as the best-covered year, and the year before it. Charity
    returns are filed up to ten months after their year ends, so the newest year is always
    partial, and a council-run school's July return lands a school year later than an
    academy's (April-March against September-August), so one year alone would skew the mix."""
    if not by_year:
        return None, None
    best = max(v["schools"] for v in by_year.values())
    newest = max(y for y, v in by_year.items() if v["schools"] >= 0.6 * best)
    start = int(newest[:4]) - 1
    return f"{start}-{(start + 1) % 100:02d}", newest


def build_pta(records):
    """The national 'pta' block from one record per school: {"urn", "name", "council", "band",
    "tags", "years": {label: {"income", "spend", "pupils", "by_charity", "names"}}}."""
    by_year = {}
    charities_by_year = defaultdict(set)
    for rec in records:
        for label, slot in rec["years"].items():
            charities_by_year[label].update(slot["by_charity"])
    for label in sorted(charities_by_year):
        slots = [rec["years"][label] for rec in records if label in rec["years"]]
        pps = [s["income"] / s["pupils"] for s in slots if s["pupils"]]
        spends = [s["spend"] for s in slots if s["spend"] is not None]
        by_year[label] = {"ptas": len(charities_by_year[label]), "schools": len(slots),
                          "income": round(sum(s["income"] for s in slots)),
                          "spend": round(sum(spends)) if spends else None,
                          "median_pp": median_or_none(pps, MIN_SCHOOLS)}
    first, newest = pta_window(by_year)
    latest = []  # (record, its latest year in the window; returns after it are still being filed)
    for rec in records:
        recent = [y for y in rec["years"] if first and first <= y <= newest]
        if recent:
            latest.append((rec, max(recent)))
    with_pupils = [(rec, y) for rec, y in latest if rec["years"][y]["pupils"]]

    def group(pairs):
        pps = [rec["years"][y]["income"] / rec["years"][y]["pupils"] for rec, y in pairs]
        if len(pps) < MIN_SCHOOLS:
            return {"schools": len(pps), "median_pp": None, "mean_pp": None}
        return {"schools": len(pps), "median_pp": statistics.median(pps), "mean_pp": sum(pps) / len(pps)}

    by_band = {str(band): group([(r, y) for r, y in with_pupils if r["band"] == band]) for band in range(1, 6)}
    by_tag = defaultdict(dict)
    for tag in ("governance", "admissions", "phase", "faith"):
        for value in sorted({r["tags"][y].get(tag) for r, y in with_pupils if r["tags"][y].get(tag)}):
            by_tag[tag][value] = group([(r, y) for r, y in with_pupils if r["tags"][y].get(tag) == value])
    top = []
    for rec, label in latest:
        slot = rec["years"][label]
        number = max(slot["by_charity"], key=lambda k: slot["by_charity"][k])
        top.append({"urn": rec["urn"], "name": rec["name"], "council": rec["council"], "council_name": rec["council_name"],
                    "charity_number": number, "charity_name": slot["names"].get(number), "year_end": label,
                    "income": round(slot["income"]), "spend": round(slot["spend"]) if slot["spend"] is not None else None,
                    "pupils": slot["pupils"], "pp": round(slot["income"] / slot["pupils"]) if slot["pupils"] else None,
                    "confidence": slot["confidence"]})
    by_total = sorted(top, key=lambda t: (-t["income"], t["urn"]))[:TOP_PTA]
    by_pp = sorted((t for t in top if t["pp"] is not None), key=lambda t: (-t["pp"], t["urn"]))[:TOP_PTA]
    keep = {t["urn"] for t in by_total} | {t["urn"] for t in by_pp}
    return {"year": newest, "window": [first, newest] if newest else None, "latest_schools": len(latest),
            "by_year": by_year, "by_band": by_band, "by_tag": dict(by_tag),
            "top": sorted((t for t in top if t["urn"] in keep), key=lambda t: (-t["income"], t["urn"]))}


def held_charities(pta):
    """Unflagged charities over HOLD_ABOVE, by charity only (no school named): never ranked."""
    out = {}
    for charities in pta.values():
        for charity in charities or []:
            if charity.get("review") or not held_back(charity):
                continue
            number = charity.get("charity_number")
            income = max((h.get("income") or 0) for h in charity.get("history") or [])
            out[number] = {"charity_number": number, "name": charity.get("name"), "income": round(income)}
    return sorted(out.values(), key=lambda c: -c["income"])


def build_areas(history_rows_by_urn, schools, pta, dsg, data_root, constituencies_path=CONSTITUENCIES_PATH):
    """Yearly aggregates for England, regions, councils, constituencies and academy trusts, plus
    the national PTA block. history_rows_by_urn: {urn: rows (with predecessors)}; schools:
    register entries (council known from la_code / laestab / the rows); pta: pta.json or its
    "schools" dict; dsg: la_dsg.json dict; data_root: site/data (for las.json, and the LSOA
    files the PTA bands need); constituencies_path: optional {name: code} map, missing is fine."""
    las = load_las(data_root)
    if isinstance(pta, dict) and isinstance(pta.get("schools"), dict):
        pta = pta["schools"]
    pta = pta or {}
    dsg = dsg or {}
    codes = load_constituency_codes(constituencies_path)
    band_ctx = Context(data_root, list(schools)) if (Path(data_root) / "la").is_dir() else None
    buckets = defaultdict(list)       # (type, id) -> [(entries, latest status)]
    names = {}
    trust_items, trust_names, central = defaultdict(list), {}, defaultdict(lambda: defaultdict(list))
    pta_records = []
    for school in schools:
        urn = str(school.get("urn"))
        rows = history_rows_by_urn.get(urn) or []
        if not rows:
            continue
        entries = school_years(rows, pta.get(urn))
        if not entries:
            continue
        verdict = health.assess(rows)
        latest = verdict["status"] if verdict else None
        code = council_of(school, rows)
        la = las.get(code, {})
        keys = [("england", "england")]
        if la.get("region"):
            keys.append(("region", la["region"]))
        if code:
            keys.append(("council", code))
        constituency = (school.get("constituency") or "").strip()
        if constituency:
            keys.append(("constituency", codes.get(constituency, constituency)))
        for kind, key in keys:
            buckets[(kind, key)].append((entries, latest))
            names.setdefault((kind, key), {"england": "England", "region": key, "council": la.get("name") or code,
                                           "constituency": constituency}[kind])
        by_trust = defaultdict(list)
        for e in entries:
            if e["source"] != "AAR":
                continue
            group, name = trust_key(e, trust_name(school))
            if group:
                by_trust[group].append(e)
                trust_names[group] = name or trust_names.get(group)
                if e["central_pp"] is not None:
                    central[group][e["year"]].append(e["central_pp"])
        latest_group = trust_key(entries[-1], trust_name(school))[0] if entries[-1]["source"] == "AAR" else None
        for group, own in by_trust.items():
            trust_items[group].append((own, latest if group == latest_group else None))
        pta_records.append(pta_record(school, code, la, rows, entries, pta.get(urn), band_ctx))
    combined_last = max((e["year"] for items in buckets.values() for entries, _ in items for e in entries
                         if e["source"] == "AAR"), default=None)
    out = {"england": None, "regions": {}, "councils": {}, "constituencies": {}}
    for (kind, key), items in buckets.items():
        area = new_area(names[(kind, key)])
        fill_area(area, items, combined_last)
        values = None
        if kind == "council":
            values = ((dsg.get("las") or {}).get(key) or {}).get("values")
        elif kind == "england":
            values = dsg.get("england")
        fill_dsg(area, values)
        if kind == "england":
            out["england"] = area
        else:
            out[{"region": "regions", "council": "councils", "constituency": "constituencies"}[kind]][key] = area
    if out["england"] is None:
        out["england"] = new_area("England")
    out["trusts"] = build_trusts(trust_items, trust_names, central)
    out["pta"] = build_pta([r for r in pta_records if r["years"]])
    out["pta"]["held"] = held_charities(pta)
    return out


def pta_record(school, code, la, rows, entries, charities, band_ctx):
    """One school's PTA years for build_pta, each with that year's pupils (None when the school
    has no return for it, so no per-pupil figure is made up)."""
    by_key = {(e["year"], e["source"]): e for e in entries}
    years, tags = {}, {}
    for (label, source), slot in sorted(school_pta(health.full_years(rows), charities).items()):
        entry = by_key.get((label, source))
        own = years.setdefault(label, {"income": 0.0, "spend": None, "by_charity": {}, "names": {},
                                       "confidence": "high", "pupils": None})
        own["income"] += slot["income"]
        if slot["spend"] is not None:
            own["spend"] = (own["spend"] or 0.0) + slot["spend"]
        for number, income in slot["by_charity"].items():
            own["by_charity"][number] = own["by_charity"].get(number, 0.0) + income
        own["names"].update(slot["names"])
        if slot["confidence"] != "high":
            own["confidence"] = "medium"
        if entry and entry["pp_pupils"]:
            own["pupils"] = entry["pp_pupils"]
        tags[label] = {"governance": "academy" if source == "AAR" else "council-run",
                       "admissions": admissions_tag(school),
                       "phase": phase_tag(entry["phase"] if entry else None, school),
                       "faith": "faith" if faith_tag(school) else "no faith"}
    return {"urn": str(school.get("urn")), "name": school.get("name"), "council": code,
            "council_name": la.get("name") or code, "band": school_band(band_ctx, school, code) if years else None,
            "tags": tags, "years": years}


# ----------------------------------------------------------------- command line

def main(argv=None):
    parser = argparse.ArgumentParser(description="Build area aggregates for School Money.")
    parser.add_argument("--site-data", type=Path, default=DEFAULT_SITE_DATA)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--links", type=Path, default=DEFAULT_LINKS)
    parser.add_argument("--pta", type=Path, default=DEFAULT_PTA)
    parser.add_argument("--dsg", type=Path, default=DSG_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    from pipeline.money.build_money import load_history, load_predecessors, school_rows
    by_urn = load_history(args.history)
    pred = load_predecessors(args.links)
    schools, rows_by_urn = [], {}
    for code in load_las(args.site_data):
        for school in load_register(args.site_data, code):
            school = dict(school, la_code=code)
            urn = str(school["urn"])
            rows = school_rows(urn, by_urn, pred)
            if rows:
                schools.append(school)
                rows_by_urn[urn] = rows
    areas = build_areas(rows_by_urn, schools, load_json(args.pta, {}), load_json(args.dsg, {}), args.site_data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "generated": date.today().isoformat(),
        "source": "DfE CFR and AAR via finance_history.jsonl; DfE DSG balances; Charity Commission register",
        "areas": areas,
    }, ensure_ascii=False), encoding="utf-8")
    england = areas["england"]
    latest = max(england["by_year"], default=None)
    print(f"schools {len(schools)}, councils {len(areas['councils'])}, regions {len(areas['regions'])}, "
          f"constituencies {len(areas['constituencies'])}, years {len(england['by_year'])}, "
          f"latest {latest}: {england['by_year'][latest]['all'] if latest else {}}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
