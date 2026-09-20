"""UK-wide council boundaries for the map's "which councils am I looking at?" lookup.

England already has site/data/england/la_boundaries_lite.geojson, keyed by DfE LA code.
This adds Wales, Scotland and Northern Ireland from the same ONS Counties and Unitary
Authorities layer and writes one combined file the browser loads instead.

Welsh councils keep their DfE LA codes (660-681, matched by name); Scottish and Northern
Irish councils are keyed by their ONS code (S12…, N09…), which is what their school data
directories are named after.

Usage (from the project root):
    uv run --with shapely --with requests python pipeline/uk/boundaries.py

Output:
    site/data/uk/la_boundaries_lite.geojson   England + Wales + Scotland + NI
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "geo"))

from areas import ARCGIS, latest_lad_service  # noqa: E402
from common import fetch_json  # noqa: E402
from national_common import paginated_features  # noqa: E402

# The counties/unitaries layer is England and Wales only; Scottish and Northern Irish
# councils are districts, so they come from the UK-wide LAD layer instead.
CTYUA_SERVICE = "Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BGC"
ENGLAND_LITE = ROOT / "site" / "data" / "england" / "la_boundaries_lite.geojson"
UK_DIR = ROOT / "site" / "data" / "uk"
OUT = UK_DIR / "la_boundaries_lite.geojson"
TOLERANCE_DEG = 0.004  # ~400 m, enough to decide which council a map point falls in


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().replace("&", "and"))


def round_coords(obj, dp=4):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], dp), round(obj[1], dp)]
        return [round_coords(o, dp) for o in obj]
    return obj


def nation_codes() -> dict[str, dict]:
    """Council code by normalised name, from whichever nation index files exist."""
    wanted: dict[str, dict] = {}
    for name, prefix in (("wales_las.json", "W"), ("scotland_las.json", "S"), ("northern_ireland_las.json", "N")):
        path = UK_DIR / name
        if not path.exists():
            print(f"  (no {name} yet — skipping that nation)")
            continue
        data = json.loads(path.read_text())
        for la in data["las"]:
            wanted[_norm(la["name"])] = {"la_code": str(la["la_code"]), "name": la["name"], "prefix": prefix}
    return wanted


def _rename(feats: list[dict], code_field: str, name_field: str) -> list[dict]:
    """Normalise ONS field names so the two layers can be handled the same way."""
    for f in feats:
        p = f["properties"]
        p["CTYUA25CD"] = p.get(code_field) or p.get("CTYUA25CD")
        p["CTYUA25NM"] = p.get(name_field) or p.get("CTYUA25NM")
    return feats


def main() -> None:
    UK_DIR.mkdir(parents=True, exist_ok=True)
    wanted = nation_codes()
    if not wanted:
        raise SystemExit("No nation index files found in site/data/uk/ — run the nation pipelines first.")

    prefixes = sorted({w["prefix"] for w in wanted.values()})
    feats = []
    if "W" in prefixes:
        feats += _rename(paginated_features(CTYUA_SERVICE, "CTYUA25CD LIKE 'W%'", "CTYUA25CD,CTYUA25NM",
                                            "ctyua_wales", geometry=True), "CTYUA25CD", "CTYUA25NM")
    district_prefixes = [p for p in prefixes if p in {"S", "N"}]
    if district_prefixes:
        service, _year = latest_lad_service()
        # Generalised boundaries are a fraction of the size and plenty for a point-in-council test.
        service = service.replace("_BFC", "_BGC")
        # The code column is named for the layer's year (LAD24CD, LAD25CD…), so read it off the layer.
        layer = fetch_json(f"{ARCGIS}/{service}/FeatureServer/0?f=json", f"{service}_layer.json")
        code_field = next(f["name"] for f in layer["fields"] if re.fullmatch(r"LAD\d\dCD", f["name"]))
        print(f"  LAD layer {service}, code field {code_field}")
        where = " OR ".join(f"{code_field} LIKE '{p}%'" for p in district_prefixes)
        feats += _rename(paginated_features(service, where, f"{code_field},{code_field[:-2]}NM",
                                            "lad_scotland_ni", geometry=True), code_field, f"{code_field[:-2]}NM")
    print(f"{len(feats)} council polygons from ONS for {', '.join(prefixes)}")

    features = json.loads(ENGLAND_LITE.read_text())["features"]
    print(f"{len(features)} English councils carried over")

    matched, gaps = 0, []
    for f in feats:
        p = f["properties"]
        target = wanted.get(_norm(p["CTYUA25NM"]))
        if not target:
            # ONS code is the key for Scotland and NI even when the name differs slightly.
            target = next((w for w in wanted.values() if w["la_code"] == p["CTYUA25CD"]), None)
        if not target:
            gaps.append(f"{p['CTYUA25CD']} {p['CTYUA25NM']}")
            continue
        geom = shape(f["geometry"]).simplify(TOLERANCE_DEG, preserve_topology=True)
        g = mapping(geom)
        features.append({
            "type": "Feature",
            "properties": {"la_code": target["la_code"], "name": target["name"]},
            "geometry": {"type": g["type"], "coordinates": round_coords(g["coordinates"])},
        })
        matched += 1

    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(f"added {matched} councils; {len(features)} total, {OUT.stat().st_size / 1024:.0f} KB -> {OUT}")
    if gaps:
        print("no school data for these ONS areas (expected where a nation isn't built yet):")
        for g in gaps[:20]:
            print("  ", g)


if __name__ == "__main__":
    main()
