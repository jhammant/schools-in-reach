"""Sanity checks on the built layers. Exit status is non-zero if any check fails."""

from __future__ import annotations

import csv
import io
import json
import re

import shapely
from shapely.geometry import Point, shape

from common import CACHE, LAD_CODE, MAX_FILE_BYTES, OUT, buffered_wgs, log, session, to_bng

GEOJSON = ["boundary.geojson", "lsoa.geojson", "pois.geojson", "transport.geojson", "bus_stops.geojson"]
LSOA_PROPS = [
    "lsoa21cd", "lsoa21nm", "imd_rank", "imd_decile", "income_decile", "employment_decile",
    "education_skills_decile", "health_decile", "crime_decile", "barriers_housing_services_decile",
    "living_environment_decile", "idaci_decile", "population", "pct_age_0_15", "pct_owned",
    "pct_social_rented", "pct_private_rented", "pct_level4_plus", "pct_households_not_deprived",
    "pct_white", "pct_asian", "pct_black", "pct_mixed", "pct_other_ethnic", "pct_no_car", "density_per_km2",
]
ENV_KEYS = ["id", "title", "group", "type", "url", "layers", "format", "transparent", "version",
            "attribution", "licence", "legend_url", "verified_at"]


class Checks:
    def __init__(self):
        self.failures: list[str] = []

    def check(self, ok: bool, msg: str) -> None:
        log(f"  [{'PASS' if ok else 'FAIL'}] {msg}")
        if not ok:
            self.failures.append(msg)


def _max_dp(coords) -> int:
    if isinstance(coords, (int, float)):
        s = repr(float(coords))
        return len(s.split(".")[1]) if "." in s and "e" not in s else 0
    return max((_max_dp(c) for c in coords), default=0)


def run() -> int:
    c = Checks()
    data = {}
    log("verify: files")
    for name in GEOJSON:
        path = OUT / name
        if not path.exists():
            c.check(False, f"{name} exists")
            continue
        fc = json.loads(path.read_text(encoding="utf-8"))
        data[name] = fc
        size = path.stat().st_size
        meta = fc.get("metadata", {})
        srcs_ok = bool(meta.get("sources")) and all(
            all(s.get(k) for k in ("title", "url", "licence", "attribution")) for s in meta["sources"])
        dp = max((_max_dp(f["geometry"]["coordinates"]) for f in fc["features"]), default=0)
        c.check(size < MAX_FILE_BYTES and bool(meta.get("generated")) and srcs_ok and dp <= 5,
                f"{name}: {len(fc['features'])} features, {size/1024:.0f} KB, metadata ok={srcs_ok}, max dp={dp}")
    env_path = OUT / "env_layers.json"
    env = json.loads(env_path.read_text(encoding="utf-8"))
    c.check(all(all(k in e for k in ENV_KEYS) and e["type"] == "wms" for e in env["layers"]),
            f"env_layers.json: {len(env['layers'])} verified layers, {len(env['metadata']['dropped'])} dropped, "
            f"{env_path.stat().st_size/1024:.0f} KB, all entries have required keys")

    boundary = shape(data["boundary.geojson"]["features"][0]["geometry"])
    c.check(boundary.is_valid and boundary.geom_type in ("Polygon", "MultiPolygon"), "boundary geometry valid")

    log("verify: LSOAs")
    lsoa = data["lsoa.geojson"]["features"]
    lookup_file = next(CACHE.glob(f"LSOA21_WD*_LAD*_EW_LU*_{LAD_CODE}.json"))
    ons_codes = {f["attributes"]["LSOA21CD"] for f in json.loads(lookup_file.read_text())["features"]}
    out_codes = {f["properties"]["lsoa21cd"] for f in lsoa}
    raw_iod = list(csv.DictReader(io.StringIO((CACHE / "iod2025_file7.csv").read_text(encoding="utf-8-sig"))))
    iod_codes = {r["LSOA code (2021)"] for r in raw_iod if r["Local Authority District code (2024)"] == LAD_CODE}
    c.check(out_codes == ons_codes, f"LSOA count {len(out_codes)} matches ONS lookup {lookup_file.stem} ({len(ons_codes)})")
    c.check(iod_codes == ons_codes, f"IoD2025 lists the same {len(iod_codes)} Hackney LSOAs")
    missing = [f["properties"]["lsoa21cd"] for f in lsoa if any(f["properties"].get(k) is None for k in LSOA_PROPS)]
    c.check(not missing, f"every LSOA has all {len(LSOA_PROPS)} IMD + census properties (missing: {missing[:5]})")
    c.check(all(shape(f["geometry"]).is_valid for f in lsoa), "all LSOA geometries valid")

    # Spot-check IMD deciles for the most and least deprived Hackney LSOA against the raw CSV row.
    by_code = {f["properties"]["lsoa21cd"]: f["properties"] for f in lsoa}
    raw_by_code = {r["LSOA code (2021)"]: r for r in raw_iod}
    ranked = sorted(by_code.values(), key=lambda p: p["imd_rank"])
    for p in (ranked[0], ranked[-1]):
        row = raw_by_code[p["lsoa21cd"]]
        raw_decile = int(row["Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)"])
        raw_idaci = int(row["Income Deprivation Affecting Children Index (IDACI) Decile (where 1 is most deprived 10% of LSOAs)"])
        raw_rank = int(row["Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)"])
        c.check((raw_decile, raw_idaci, raw_rank) == (p["imd_decile"], p["idaci_decile"], p["imd_rank"]),
                f"IoD spot-check {p['lsoa21cd']} ({p['lsoa21nm']}): IMD decile {p['imd_decile']} / IDACI decile "
                f"{p['idaci_decile']} / rank {p['imd_rank']} == File 7 ({raw_decile}/{raw_idaci}/{raw_rank})")

    # Census spot-check: fresh single-LSOA Nomis request (not the cached borough download).
    code = ranked[len(ranked) // 2]["lsoa21cd"]
    r = session().get("https://www.nomisweb.co.uk/api/v01/dataset/NM_2063_1.data.csv",
                      params={"geography": code, "measures": "20100", "select": "c2021_cars_5,obs_value"}, timeout=60)
    vals = {row["C2021_CARS_5"]: float(row["OBS_VALUE"]) for row in csv.DictReader(io.StringIO(r.text))}
    expect = round(100 * vals["1"] / vals["0"], 1)
    c.check(expect == by_code[code]["pct_no_car"],
            f"Census spot-check {code}: pct_no_car {by_code[code]['pct_no_car']} == Nomis TS045 {int(vals['1'])}/{int(vals['0'])} = {expect}")

    # Geometry sanity: centroids inside the borough and LSOAs tile the borough.
    tol = boundary.buffer(0.0003)  # ~20-30 m: LSOAs are generalised (BGC), the boundary is full resolution
    outside = [f["properties"]["lsoa21cd"] for f in lsoa if not tol.contains(shape(f["geometry"]).centroid)]
    c.check(not outside, f"all {len(lsoa)} LSOA centroids fall inside the boundary (outside: {outside})")
    union = shapely.union_all([shape(f["geometry"]) for f in lsoa])
    a_union, a_bound = to_bng(union).area, to_bng(boundary).area
    c.check(abs(a_union - a_bound) / a_bound < 0.01,
            f"LSOA union area {a_union/1e6:.2f} km2 vs boundary {a_bound/1e6:.2f} km2")
    minx, miny, maxx, maxy = boundary.bounds
    c.check(-0.12 < minx < maxx < 0.0 and 51.50 < miny < maxy < 51.60,
            f"boundary bbox plausible for Hackney: {tuple(round(v, 4) for v in boundary.bounds)}")
    pops = sum(p["population"] for p in by_code.values())
    c.check(240_000 < pops < 280_000, f"LSOA populations sum to {pops:,} (Census 2021 Hackney ~259k)")

    log("verify: points")
    poi_area = buffered_wgs(boundary, 320)
    pois = data["pois.geojson"]["features"]
    bad = [f["properties"]["osm"] for f in pois if not poi_area.contains(shape(f["geometry"]))]
    osm_ok = all(re.fullmatch(r"(node|way|relation)/\d+", f["properties"]["osm"]) for f in pois)
    c.check(not bad and osm_ok, f"{len(pois)} POIs within boundary+300 m, osm ids well-formed (outside: {bad[:5]})")
    counts = {}
    for f in pois:
        counts[f["properties"]["category"]] = counts.get(f["properties"]["category"], 0) + 1
    c.check(len(counts) == 14, f"POI categories present: {dict(sorted(counts.items()))}")

    st_area = buffered_wgs(boundary, 1100)
    stations = data["transport.geojson"]["features"]
    bad = [f["properties"]["name"] for f in stations if not st_area.contains(shape(f["geometry"])) or not f["properties"]["modes"]]
    in_b = sum(1 for f in stations if f["properties"]["in_borough"])
    c.check(not bad, f"{len(stations)} stations ({in_b} in borough) within boundary+1 km with modes (bad: {bad})")

    stops = data["bus_stops.geojson"]["features"]
    bad = [f["properties"]["atco"] for f in stops if not boundary.contains(shape(f["geometry"]))]
    c.check(not bad and (OUT / "bus_stops.geojson").stat().st_size < 1_000_000,
            f"{len(stops)} bus stops inside boundary, file < 1 MB")

    if c.failures:
        log(f"verify: {len(c.failures)} FAILED")
        return 1
    log("verify: all checks passed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
