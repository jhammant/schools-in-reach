"""Simplify England LA boundaries into a small file the browser can use to work out which councils are in view."""
import json
from pathlib import Path

from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "site/data/england/la_boundaries.geojson"
OUT = ROOT / "site/data/england/la_boundaries_lite.geojson"
TOLERANCE_DEG = 0.004  # roughly 400 m: plenty to pick which council a map point is in


def round_coords(obj, dp=4):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], dp), round(obj[1], dp)]
        return [round_coords(o, dp) for o in obj]
    return obj


def main():
    src = json.loads(SRC.read_text())
    features = []
    for f in src["features"]:
        geom = shape(f["geometry"]).simplify(TOLERANCE_DEG, preserve_topology=True)
        g = mapping(geom)
        features.append({"type": "Feature", "properties": {"la_code": str(f["properties"]["la_code"]), "name": f["properties"].get("name")}, "geometry": {"type": g["type"], "coordinates": round_coords(g["coordinates"])}})
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(f"{len(features)} LAs, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
