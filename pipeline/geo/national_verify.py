"""Sanity checks for the national geo build (site/data/la/<code>/{lsoa,pois}.geojson,
site/data/england/{stations,la_geometry,la_boundaries}.geojson). Companion to pipeline/geo/verify.py
(which only checks the Hackney-only site/data/hackney/layers/ outputs). Exit status is
non-zero if any check fails.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from common import ROOT, log

LA_ROOT = ROOT / "site" / "data" / "la"
ENGLAND_ROOT = ROOT / "site" / "data" / "england"
LSOA_PROPS = [
    "lsoa21cd", "lsoa21nm", "imd_rank", "imd_decile", "income_decile", "employment_decile",
    "education_skills_decile", "health_decile", "crime_decile", "barriers_housing_services_decile",
    "living_environment_decile", "idaci_decile", "population", "pct_age_0_15", "pct_owned",
    "pct_social_rented", "pct_private_rented", "pct_level4_plus", "pct_households_not_deprived",
    "pct_white", "pct_asian", "pct_black", "pct_mixed", "pct_other_ethnic", "pct_no_car", "density_per_km2",
]
LONDON_LA_CODES = {str(c) for c in list(range(201, 214)) + list(range(301, 321))}
KNOWN_STATIONS = ["Manchester Piccadilly", "Leeds", "Clapham Junction", "Newcastle", "Birmingham New Street"]


class Checks:
    def __init__(self):
        self.failures: list[str] = []

    def check(self, ok: bool, msg: str) -> None:
        log(f"  [{'PASS' if ok else 'FAIL'}] {msg}")
        if not ok:
            self.failures.append(msg)


def run() -> int:
    c = Checks()

    log("verify: lsoa.geojson per LA")
    lsoa_paths = sorted(glob.glob(str(LA_ROOT / "*" / "lsoa.geojson")))
    seen: dict[str, str] = {}
    total = 0
    oversize = []
    missing_props = []
    for p in lsoa_paths:
        la_code = Path(p).parent.name
        fc = json.loads(Path(p).read_text())
        size = Path(p).stat().st_size
        if size > 2_600_000:
            oversize.append((la_code, size))
        for f in fc["features"]:
            code = f["properties"]["lsoa21cd"]
            if code in seen:
                c.failures.append(f"LSOA {code} in both LA {seen[code]} and {la_code}")
            seen[code] = la_code
            if any(f["properties"].get(k) is None for k in LSOA_PROPS):
                missing_props.append((la_code, code))
        total += len(fc["features"])
    c.check(len(lsoa_paths) == 153, f"{len(lsoa_paths)} LA lsoa.geojson files (expected 153)")
    c.check(total == len(seen), f"{total} total LSOA features, {len(seen)} unique (no LSOA in two LAs)")
    c.check(not oversize, f"all lsoa.geojson files under budget (over: {oversize})")
    c.check(not missing_props, f"every LSOA has all {len(LSOA_PROPS)} properties (missing: {missing_props[:5]})")

    log("verify: la 204 (Hackney) matches site/data/hackney/layers/lsoa.geojson")
    hackney = json.loads((ROOT / "site" / "data" / "hackney" / "layers" / "lsoa.geojson").read_text())
    la204 = json.loads((LA_ROOT / "204" / "lsoa.geojson").read_text())
    ha = {f["properties"]["lsoa21cd"]: f for f in hackney["features"]}
    hb = {f["properties"]["lsoa21cd"]: f for f in la204["features"]}
    mismatches = [k for k in ha if ha[k]["properties"] != hb.get(k, {}).get("properties")
                  or ha[k]["geometry"] != hb.get(k, {}).get("geometry")]
    c.check(set(ha) == set(hb) and not mismatches,
            f"la/204/lsoa.geojson matches hackney/layers/lsoa.geojson feature-for-feature "
            f"({len(ha)} LSOAs, {len(mismatches)} mismatches)")

    log("verify: pois.geojson for the 33 London LAs")
    poi_paths = sorted(glob.glob(str(LA_ROOT / "*" / "pois.geojson")))
    poi_las = {Path(p).parent.name for p in poi_paths}
    c.check(poi_las == LONDON_LA_CODES, f"pois.geojson written for exactly the 33 London LAs "
            f"(missing: {sorted(LONDON_LA_CODES - poi_las)}, extra: {sorted(poi_las - LONDON_LA_CODES)})")
    hackney_pois = json.loads((ROOT / "site" / "data" / "hackney" / "layers" / "pois.geojson").read_text())
    la204_pois = json.loads((LA_ROOT / "204" / "pois.geojson").read_text())
    pa = {f["properties"]["osm"]: (f["properties"]["category"], f["geometry"]) for f in hackney_pois["features"]}
    pb = {f["properties"]["osm"]: (f["properties"]["category"], f["geometry"]) for f in la204_pois["features"]}
    c.check(pa == pb, f"la/204/pois.geojson matches hackney/layers/pois.geojson ({len(pa)} OSM ids)")

    log("verify: england/stations.geojson")
    stations = json.loads((ENGLAND_ROOT / "stations.geojson").read_text())
    feats = stations["features"]
    by_mode: dict[str, int] = {}
    for f in feats:
        for m in f["properties"]["modes"]:
            by_mode[m] = by_mode.get(m, 0) + 1
    log(f"  stations by mode: {dict(sorted(by_mode.items()))}")
    names_lower = [f["properties"]["name"].lower() for f in feats]
    missing_known = [name for name in KNOWN_STATIONS if not any(name.lower() in n for n in names_lower)]
    c.check(not missing_known, f"known stations present: {KNOWN_STATIONS} (missing: {missing_known})")
    c.check(len(feats) > 2000, f"{len(feats)} stations total (plausible national count)")

    log("verify: england/la_geometry.json + la_boundaries.geojson")
    la_geo = json.loads((ENGLAND_ROOT / "la_geometry.json").read_text())
    las = la_geo["las"]
    c.check(len(las) == 153, f"la_geometry.json has {len(las)} LAs (expected 153)")
    no_neigh = [k for k, v in las.items() if not v["neighbours"]]
    c.check(set(no_neigh) <= {"420", "921"},
            f"only island LAs (Isles of Scilly 420, Isle of Wight 921) have zero neighbours (got: {no_neigh})")
    boundaries = json.loads((ENGLAND_ROOT / "la_boundaries.geojson").read_text())
    b_codes = {f["properties"]["la_code"] for f in boundaries["features"]}
    c.check(b_codes == set(las), "la_boundaries.geojson covers the same 153 LA codes as la_geometry.json")
    c.check((ENGLAND_ROOT / "la_boundaries.geojson").stat().st_size < 5_000_000, "la_boundaries.geojson under 5 MB")

    log("verify: total sizes")
    total_bytes = sum(Path(p).stat().st_size for p in lsoa_paths)
    total_bytes += sum(Path(p).stat().st_size for p in poi_paths)
    for name in ("stations.geojson", "la_geometry.json", "la_boundaries.geojson"):
        total_bytes += (ENGLAND_ROOT / name).stat().st_size
    log(f"  {total_bytes/1e6:.1f} MB across all national_* outputs "
        f"({len(lsoa_paths)} lsoa.geojson + {len(poi_paths)} pois.geojson + 3 england/*.json)")

    if c.failures:
        log(f"verify: {len(c.failures)} FAILED")
        return 1
    log("verify: all checks passed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
