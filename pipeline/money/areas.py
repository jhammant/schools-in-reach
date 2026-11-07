"""Area aggregates and socio-economic context for School Money.

Two jobs:

* school_profile(school, council_code, data_root): tags (governance, trust, admissions,
  faith...), intake (free school meals against the council and England medians) and
  the neighbourhood the school sits in (English Indices of Deprivation deciles and
  Census 2021 figures for its LSOA, the same figures averaged over the LSOAs inside
  the last distance it offered a place to, and the ONS income estimate for its MSOA).

* build_areas(...): for England, each region, each council and each constituency, the
  yearly picture: how many schools, pupils, deficits, the median per-pupil figures,
  split into all / council-run (CFR returns) / academy (AAR returns), plus the
  council's high-needs (DSG) balance per pupil.

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
offered a place, so no real catchment exists and it is skipped.

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
from pipeline.money.timeline import status_by_year, year_label

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
          "income_pp_median", "spend_pp_median", "grant_pp_median", "pta_pp_median", "pta_schools", "donations_pp_median"]


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
    """Mean of the outer ring's vertices as (lat, lon); good enough for LSOA-sized areas."""
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if not coords:
        return None
    if kind == "Polygon":
        ring = coords[0]
    elif kind == "MultiPolygon":
        ring = max((poly[0] for poly in coords if poly), key=len, default=None)
    elif kind == "Point":
        return (coords[1], coords[0])
    else:
        return None
    if not ring:
        return None
    return (sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring))


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
    values = [v for v in values if v is not None]
    return statistics.median(values) if len(values) >= minimum else None


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
    area["catchment"] = catchment(school, ctx.admissions(code) if code else {}, lsoas, own)
    msoa = str(school.get("msoa") or "")
    area["msoa_income"] = ctx.msoa_income.get(msoa) if msoa else None
    return {"tags": tags, "intake": intake, "area": area, "band": ctx.band(fsm, area.get("idaci_decile"))}


def catchment(school, admissions, lsoas, own=None):
    """AREA_KEYS averaged over the LSOAs whose centroid lies within the school's last
    distance offered (plus its own LSOA), with the distance and count used."""
    miles = latest_distance(admissions.get(str(school.get("urn")), {}))
    lat, lon = school.get("lat"), school.get("lon")
    if miles is None or lat is None or lon is None:
        return None
    radius_km = miles * KM_PER_MILE
    picked = []
    for code, feature in lsoas.items():
        c = feature.get("centroid")
        if feature is own or (c and haversine_km(lat, lon, c[0], c[1]) <= radius_km):
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
    year end_year. Charities shared with other schools contribute an equal share."""
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


def summarise(entries):
    """S over a list of per-school-year entries (see school_years)."""
    n = len(entries)
    if n < MIN_SCHOOLS:
        return {k: (n if k == "schools" else None) for k in S_KEYS}
    deficits = [e for e in entries if e["reserve"] is not None and e["reserve"] < 0]
    deficit_total = sum(e["reserve"] for e in deficits)
    deficit_pupils = sum(e["pupils"] or 0 for e in deficits)
    pta = [e["pta_pp"] for e in entries if e["pta_pp"] is not None]
    return {
        "schools": n,
        "in_deficit": len(deficits),
        "in_deficit_pct": round(100 * len(deficits) / n, 1),
        "heading": sum(1 for e in entries if e["status"] == "heading_for_deficit"),
        "deficit_total": deficit_total,
        "deficit_pp": deficit_total / deficit_pupils if deficit_pupils else None,
        "reserve_median_pp": median_or_none(e["reserve_pp"] for e in entries),
        "income_pp_median": median_or_none(e["income_pp"] for e in entries),
        "spend_pp_median": median_or_none(e["spend_pp"] for e in entries),
        "grant_pp_median": median_or_none(e["grant_pp"] for e in entries),
        "pta_pp_median": median_or_none(pta, MIN_SCHOOLS),
        "pta_schools": len(pta),
        "donations_pp_median": median_or_none(e["donations_pp"] for e in entries),
    }


def school_years(rows, charities):
    """One entry per full year for a school: the inputs summarise() needs."""
    by_label = {year_label(r): r for r in health.full_years(rows)}
    out = []
    for point in status_by_year(rows):
        r = by_label.get(point["year"])
        if r is None:
            continue
        pupils = r.get("pupils") or None
        pta = pta_income_for(charities, end_year_of(point["year"]))
        out.append({
            "year": point["year"], "source": r.get("source"), "status": point["status"],
            "reserve": point["reserve"], "reserve_pp": point["reserve_pp"], "pupils": pupils,
            "income_pp": per_pupil(r, "total_income"), "spend_pp": per_pupil(r, "total_expenditure"),
            "grant_pp": per_pupil(r, "grant_funding"),
            "pta_pp": pta / pupils if pta is not None and pupils else None,
            "donations_pp": per_pupil(r, "donations_revenue"),
        })
    return out


def new_area(name):
    return {"name": name, "pupils_by_year": {}, "schools_by_year": {}, "by_year": {}, "dsg": {}, "statuses_latest": {}}


def build_areas(history_rows_by_urn, schools, pta, dsg, data_root, constituencies_path=CONSTITUENCIES_PATH):
    """Yearly aggregates for England, regions, councils and constituencies.
    history_rows_by_urn: {urn: rows (with predecessors)}; schools: register entries
    (council known from la_code / laestab / the rows); pta: pta.json or its "schools"
    dict; dsg: la_dsg.json dict; data_root: site/data (for las.json);
    constituencies_path: optional {name: code} map, missing is fine."""
    las = load_las(data_root)
    if isinstance(pta, dict) and isinstance(pta.get("schools"), dict):
        pta = pta["schools"]
    pta = pta or {}
    dsg = dsg or {}
    codes = load_constituency_codes(constituencies_path)
    buckets = defaultdict(list)       # (type, id) -> [(entries, latest status)]
    names = {}
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
    out = {"england": None, "regions": {}, "councils": {}, "constituencies": {}}
    for (kind, key), items in buckets.items():
        area = new_area(names[(kind, key)])
        per_year = defaultdict(list)
        for entries, latest in items:
            if latest:
                area["statuses_latest"][latest] = area["statuses_latest"].get(latest, 0) + 1
            for e in entries:
                per_year[e["year"]].append(e)
        for year in sorted(per_year):
            entries = per_year[year]
            area["pupils_by_year"][year] = sum(e["pupils"] or 0 for e in entries)
            area["schools_by_year"][year] = len(entries)
            area["by_year"][year] = {split: summarise([e for e in entries if source is None or e["source"] == source])
                                     for split, source in SPLITS.items()}
        values = None
        if kind == "council":
            values = ((dsg.get("las") or {}).get(key) or {}).get("values")
        elif kind == "england":
            values = dsg.get("england")
        for year, balance in sorted((values or {}).items()):
            pupils = area["pupils_by_year"].get(year)
            area["dsg"][year] = {"balance": balance, "per_pupil": balance / pupils if balance is not None and pupils else None}
        if kind == "england":
            out["england"] = area
        else:
            out[{"region": "regions", "council": "councils", "constituency": "constituencies"}[kind]][key] = area
    if out["england"] is None:
        out["england"] = new_area("England")
    return out


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
