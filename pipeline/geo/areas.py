"""Borough boundary + LSOA 2021 polygons joined to IoD2025 and Census 2021 (Nomis)."""

from __future__ import annotations

import csv
import io
import json
import re

import shapely
from shapely.geometry import shape

from common import (
    LAD_CODE,
    OGL,
    fetch,
    fetch_json,
    feature,
    log,
    ons_boundary_attr,
    round_geom,
    to_bng,
    to_wgs,
    write_geojson,
)

ARCGIS = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"
# Full-resolution (BFC) boundary, lightly simplified: BGC (~127 vertices) is too coarse for clipping
# bus stops / POIs near boundary roads.
LAD_RESOLUTION = "BFC"
LAD_FALLBACK_SERVICE = f"Local_Authority_Districts_May_2026_Boundaries_UK_{LAD_RESOLUTION}"
LSOA_SERVICE = "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5"
LSOA_LOOKUP_FALLBACK = "LSOA21_WD25_LAD25_EW_LU_v2"

IOD2025_PAGE = "https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025"
IOD2025_FILE7 = (
    "https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/"
    "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv"
)

NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset"
# Census 2021 topic summary tables on Nomis (ids looked up via /dataset/def.sdmx.json?search=name-TSxxx*).
NOMIS_TABLES = {
    "TS001": ("NM_2021_1", "c2021_restype_3"),  # usual residents
    "TS007B": ("NM_2018_1", "c2021_age_12a"),  # broad age bands (has an exact 10-15 band)
    "TS054": ("NM_2072_1", "c2021_tenure_9"),
    "TS067": ("NM_2084_1", "c2021_hiqual_8"),
    "TS011": ("NM_2031_1", "c2021_dep_6"),
    "TS021": ("NM_2041_1", "c2021_eth_20"),
    "TS045": ("NM_2063_1", "c2021_cars_5"),
    "TS006": ("NM_2026_1", "cell"),
}
NOMIS_HACKNEY_FALLBACK = "645923001"  # Nomis internal id for Hackney (2022 LAD, TYPE154)

# Vertex tolerance (metres, BNG). BGC is already generalised to ~20 m, so this
# mainly drops redundant vertices while keeping shared LSOA edges identical (coverage simplify).
SIMPLIFY_M = 4.0
BOUNDARY_SIMPLIFY_M = 2.0


# --- boundaries ----------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _ons_services() -> list[dict]:
    return fetch_json(f"{ARCGIS}?f=json", "ons_arcgis_services.json")["services"]


def latest_lad_service() -> tuple[str, int]:
    """Newest 'Local_Authority_Districts_<Mon>_<YYYY>_Boundaries_UK_<res>' FeatureServer."""
    pat = re.compile(
        rf"^Local_Authority_Districts_([A-Za-z]+)_(\d{{4}})_Boundaries_UK_{LAD_RESOLUTION}(?:_V(\d+))?$")
    best = None
    try:
        for s in _ons_services():
            m = pat.match(s["name"])
            if not m or s["type"] != "FeatureServer":
                continue
            month = _MONTHS.get(m.group(1)[:3].lower())
            if not month:
                continue
            key = (int(m.group(2)), month, int(m.group(3) or 0))
            if best is None or key > best[0]:
                best = (key, s["name"])
    except Exception as err:  # noqa: BLE001
        log(f"  could not list ONS services ({err}); using pinned LAD service")
    if best is None:
        return LAD_FALLBACK_SERVICE, 2026
    return best[1], best[0][0]


def _arcgis_query(service: str, params: dict, cache_name: str) -> dict:
    url = f"{ARCGIS}/{service}/FeatureServer/0/query"
    return json.loads(fetch(url, cache_name, data={"f": "geojson", **params}))


def lad_boundary_bng(lad_code: str) -> dict:
    """Full-resolution (BFC) LAD boundary in BNG for any English LAD code, from the same
    ONS service used for Hackney. Shared by build_boundary() and the national modules
    (national_la_geometry.py, national_pois.py)."""
    service, year = latest_lad_service()
    layer = fetch_json(f"{ARCGIS}/{service}/FeatureServer/0?f=json", f"{service}_layer.json")
    code_field = next(f["name"] for f in layer["fields"] if re.fullmatch(r"LAD\d\dCD", f["name"]))
    name_field = code_field[:-2] + "NM"
    fc = _arcgis_query(
        service,
        {"where": f"{code_field}='{lad_code}'", "outFields": f"{code_field},{name_field}", "outSR": 4326},
        f"{service}_{lad_code}.geojson",
    )
    assert len(fc["features"]) == 1, f"expected 1 LAD feature for {lad_code}, got {len(fc['features'])}"
    name = fc["features"][0]["properties"][name_field]
    geom_bng = to_bng(shape(fc["features"][0]["geometry"]))
    return {"service": service, "year": year, "name": name, "geom_bng": geom_bng}


def build_boundary() -> dict:
    log(f"boundary: LAD={LAD_CODE}")
    lad = lad_boundary_bng(LAD_CODE)
    service, year, geom_bng = lad["service"], lad["year"], lad["geom_bng"]
    simp = shapely.simplify(geom_bng, BOUNDARY_SIMPLIFY_M, preserve_topology=True)
    geom = round_geom(to_wgs(simp))
    props = {
        "lad_code": LAD_CODE,
        "lad_name": lad["name"],
        "area_km2": round(geom_bng.area / 1e6, 2),
    }
    sources = [{
        "title": f"{service.replace('_', ' ')} (ONS Open Geography Portal)",
        "url": f"{ARCGIS}/{service}/FeatureServer",
        "licence": OGL,
        "attribution": ons_boundary_attr(year),
    }]
    write_geojson("boundary.geojson", [feature(geom, props)], sources)
    return {"service": service, "year": year, "geom_bng": geom_bng}


# --- LSOA membership + geometry ------------------------------------------------------------

def latest_lsoa_lookup() -> str:
    pat = re.compile(r"^LSOA21_WD(\d\d)_LAD(\d\d)_EW_LU(?:_v(\d+))?$")
    best = None
    try:
        for s in _ons_services():
            m = pat.match(s["name"])
            if m and s["type"] == "FeatureServer":
                key = (int(m.group(2)), int(m.group(3) or 0))
                if best is None or key > best[0]:
                    best = (key, s["name"])
    except Exception:  # noqa: BLE001
        pass
    return best[1] if best else LSOA_LOOKUP_FALLBACK


def hackney_lsoa_codes() -> tuple[list[str], str]:
    svc = latest_lsoa_lookup()
    layer = fetch_json(f"{ARCGIS}/{svc}/FeatureServer/0?f=json", f"{svc}_layer.json")
    lad_field = next(f["name"] for f in layer["fields"] if re.fullmatch(r"LAD\d\dCD", f["name"]))
    data = json.loads(fetch(
        f"{ARCGIS}/{svc}/FeatureServer/0/query",
        f"{svc}_{LAD_CODE}.json",
        data={"f": "json", "where": f"{lad_field}='{LAD_CODE}'", "outFields": "LSOA21CD",
              "returnGeometry": "false", "resultRecordCount": 2000},
    ))
    codes = sorted({f["attributes"]["LSOA21CD"] for f in data["features"]})
    log(f"lsoa lookup {svc}: {len(codes)} LSOAs in {LAD_CODE}")
    return codes, svc


def lsoa_geometries(codes: list[str], cache_key: str | None = None) -> dict[str, tuple[str, object]]:
    """WGS84 LSOA21 polygons for the given codes (used for Hackney and, per-LA, by
    national_lsoa.py). Paginated in case a single LA has more LSOAs than one page (largest
    county DfE LAs have under 1000; the service caps around 2000/page)."""
    cache_key = cache_key or LAD_CODE
    in_list = ",".join(f"'{c}'" for c in codes)
    out: dict[str, tuple[str, object]] = {}
    offset = 0
    page = 2000
    while True:
        fc = _arcgis_query(
            LSOA_SERVICE,
            {"where": f"LSOA21CD IN ({in_list})", "outFields": "LSOA21CD,LSOA21NM", "outSR": 4326,
             "resultRecordCount": page, "resultOffset": offset},
            f"{LSOA_SERVICE}_{cache_key}_p{offset}.geojson",
        )
        feats = fc["features"]
        for f in feats:
            p = f["properties"]
            out[p["LSOA21CD"]] = (p["LSOA21NM"], shape(f["geometry"]))
        if len(feats) < page:
            break
        offset += page
    return out


# --- IoD 2025 -------------------------------------------------------------------------------

IOD_DECILE_COLUMNS = {
    "imd_decile": "Index of Multiple Deprivation (IMD) Decile",
    "income_decile": "Income Decile",
    "employment_decile": "Employment Decile",
    "education_skills_decile": "Education, Skills and Training Decile",
    "health_decile": "Health Deprivation and Disability Decile",
    "crime_decile": "Crime Decile",
    "barriers_housing_services_decile": "Barriers to Housing and Services Decile",
    "living_environment_decile": "Living Environment Decile",
    "idaci_decile": "Income Deprivation Affecting Children Index (IDACI) Decile",
}


def iod2025(codes: set[str]) -> dict[str, dict]:
    raw = fetch(IOD2025_FILE7, "iod2025_file7.csv").decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    cols = reader.fieldnames or []

    def col(prefix: str) -> str:
        matches = [c for c in cols if c.startswith(prefix)]
        if len(matches) != 1:
            raise KeyError(f"IoD column '{prefix}' matched {matches}")
        return matches[0]

    rank_col = col("Index of Multiple Deprivation (IMD) Rank")
    decile_cols = {k: col(v) for k, v in IOD_DECILE_COLUMNS.items()}
    out = {}
    for row in reader:
        code = row["LSOA code (2021)"]
        if code in codes:
            rec = {"imd_rank": int(row[rank_col])}
            rec.update({k: int(row[c]) for k, c in decile_cols.items()})
            out[code] = rec
    return out


# --- Census 2021 via Nomis --------------------------------------------------------------------

def nomis_hackney_id() -> str:
    try:
        d = fetch_json(
            f"{NOMIS}/NM_2021_1/geography/2092957699TYPE154.def.sdmx.json",
            "nomis_lad_search.json",
            params={"search": "Hackney"},
        )
        for c in d["structure"]["codelists"]["codelist"][0]["code"]:
            ann = {a["annotationtitle"]: a["annotationtext"] for a in c["annotations"]["annotation"]}
            if ann.get("GeogCode") == LAD_CODE:
                return str(c["value"])
    except Exception as err:  # noqa: BLE001
        log(f"  nomis geography lookup failed ({err}); using pinned id")
    return NOMIS_HACKNEY_FALLBACK


def nomis_table(table: str, geography: str) -> dict[str, dict[str, float]]:
    ds, dim = NOMIS_TABLES[table]
    raw = fetch(
        f"{NOMIS}/{ds}.data.csv",
        f"nomis_{table}_{geography}.csv",
        params={"geography": geography, "measures": "20100",
                "select": f"geography_code,{dim},obs_value"},
    ).decode("utf-8-sig")
    out: dict[str, dict[str, float]] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        out.setdefault(row["GEOGRAPHY_CODE"], {})[row[dim.upper()]] = float(row["OBS_VALUE"])
    return out


def _pct(num: float, den: float) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def census_record(code: str, t: dict[str, dict[str, dict[str, float]]]) -> dict:
    """One LSOA's census properties from already-fetched per-table dicts (table -> geography
    code -> category -> value). Shared by census() (single-LAD, Hackney) and
    national_lsoa.py's national bulk fetch (same tables, fetched for all English LSOAs)."""
    pop = t["TS001"][code]
    age = t["TS007B"][code]
    ten = t["TS054"][code]
    qual = t["TS067"][code]
    dep = t["TS011"][code]
    eth = t["TS021"][code]
    car = t["TS045"][code]
    return {
        "population": int(pop["0"]),
        "pct_age_0_15": _pct(age["1"] + age["2"] + age["3"], age["0"]),
        # owned = owns outright + with mortgage/loan + shared ownership (ONS groups shared
        # ownership with mortgage in its own 'owns with a mortgage or loan or shared ownership')
        "pct_owned": _pct(ten["1001"] + ten["1002"], ten["0"]),
        "pct_social_rented": _pct(ten["1003"], ten["0"]),
        "pct_private_rented": _pct(ten["1004"], ten["0"]),
        "pct_level4_plus": _pct(qual["6"], qual["0"]),
        "pct_households_not_deprived": _pct(dep["1"], dep["0"]),
        "pct_white": _pct(eth["1004"], eth["0"]),
        "pct_asian": _pct(eth["1001"], eth["0"]),
        "pct_black": _pct(eth["1002"], eth["0"]),
        "pct_mixed": _pct(eth["1003"], eth["0"]),
        "pct_other_ethnic": _pct(eth["1005"], eth["0"]),
        "pct_no_car": _pct(car["1"], car["0"]),
        "density_per_km2": round(t["TS006"][code]["0"]),
    }


def census(geography: str) -> dict[str, dict]:
    t = {name: nomis_table(name, geography) for name in NOMIS_TABLES}
    return {code: census_record(code, t) for code in t["TS001"]}


def build_lsoa() -> dict:
    codes, lookup_svc = hackney_lsoa_codes()
    geoms = lsoa_geometries(codes)
    missing_geom = sorted(set(codes) - set(geoms))
    if missing_geom:
        raise RuntimeError(f"LSOAs without geometry: {missing_geom}")

    iod = iod2025(set(codes))
    geo_id = nomis_hackney_id()
    cen = census(f"{geo_id}TYPE151")
    missing_iod = sorted(set(codes) - set(iod))
    missing_cen = sorted(set(codes) - set(cen))
    if missing_iod or missing_cen:
        raise RuntimeError(f"missing IoD {missing_iod} / census {missing_cen}")

    # Topology-preserving simplification over the whole LSOA coverage (shared edges stay shared).
    ordered = sorted(codes)
    bng = [to_bng(geoms[c][1]) for c in ordered]
    simplified = shapely.coverage_simplify(bng, SIMPLIFY_M)

    feats = []
    for code, g in zip(ordered, simplified):
        props = {"lsoa21cd": code, "lsoa21nm": geoms[code][0]}
        props.update(iod[code])
        props.update(cen[code])
        feats.append(feature(round_geom(to_wgs(g)), props))

    sources = [
        {
            "title": f"{LSOA_SERVICE.replace('_', ' ')} (ONS Open Geography Portal)",
            "url": f"{ARCGIS}/{LSOA_SERVICE}/FeatureServer",
            "licence": OGL,
            "attribution": ons_boundary_attr(2021),
        },
        {
            "title": f"{lookup_svc} (ONS LSOA 2021 to ward/LAD lookup, used for membership)",
            "url": f"{ARCGIS}/{lookup_svc}/FeatureServer",
            "licence": OGL,
            "attribution": "Source: Office for National Statistics licensed under the Open Government Licence v.3.0.",
        },
        {
            "title": "English Indices of Deprivation 2025, File 7 (MHCLG, LSOA 2021 geography)",
            "url": IOD2025_PAGE,
            "licence": OGL,
            "attribution": "Ministry of Housing, Communities and Local Government, English Indices of Deprivation 2025. Contains public sector information licensed under the Open Government Licence v3.0.",
        },
        {
            "title": "Census 2021 topic summaries TS001, TS007B, TS054, TS067, TS011, TS021, TS045, TS006 (ONS via Nomis)",
            "url": "https://www.nomisweb.co.uk/sources/census_2021",
            "licence": OGL,
            "attribution": "Source: Office for National Statistics, Census 2021, licensed under the Open Government Licence v.3.0.",
        },
    ]
    notes = [
        "Deciles/ranks: 1 = most deprived (ranks out of 33,755 English LSOAs).",
        "Census percentages use each table's own total as denominator (ONS cell-key perturbation means totals differ slightly between tables).",
        "pct_age_0_15 uses TS007B broad age bands (0-4, 5-9, 10-15) because TS007A 5-year bands split 15-19.",
        "pct_owned includes shared ownership; 'lives rent free' is in no tenure group.",
        "pct_level4_plus denominator is usual residents aged 16+.",
    ]
    write_geojson("lsoa.geojson", feats, sources, notes)
    return {"codes": codes, "lookup": lookup_svc, "nomis_geo": geo_id}
