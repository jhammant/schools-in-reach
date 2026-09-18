"""Shared helpers for the geo pipeline: paths, cached HTTP, projections, GeoJSON output."""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "pipeline" / ".cache" / "geo"
OUT = ROOT / "site" / "data" / "hackney" / "layers"

LAD_CODE = "E09000012"  # London Borough of Hackney
LAD_NAME = "Hackney"

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
# Overpass asks for an identifying User-Agent (it returns 406 without one).
PIPELINE_UA = "SchoolCatchmentArea-geo-pipeline/1.0 (open-data school & neighbourhood research)"

MAX_FILE_BYTES = 1_500_000
COORD_DP = 5

# Set by build.py --refresh: ignore cached downloads and fetch again.
REFRESH = False

_session: requests.Session | None = None

_to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
_to_wgs = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
_to_merc = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def log(msg: str) -> None:
    print(f"[geo] {msg}", flush=True)


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": BROWSER_UA})
    return _session


def fetch(
    url: str,
    cache_name: str | None,
    *,
    params: dict | None = None,
    data: dict | None = None,
    headers: dict | None = None,
    timeout: int = 180,
    retries: int = 3,
) -> bytes:
    """GET (or POST when `data` is given) with retries; cache the body under CACHE/cache_name."""
    if cache_name:
        path = CACHE / cache_name
        if path.exists() and path.stat().st_size > 0 and not REFRESH:
            return path.read_bytes()
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if data is not None:
                r = session().post(url, params=params, data=data, headers=headers, timeout=timeout)
            else:
                r = session().get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code} for {r.url}")
            r.raise_for_status()
            body = r.content
            if cache_name:
                CACHE.mkdir(parents=True, exist_ok=True)
                (CACHE / cache_name).write_bytes(body)
            return body
        except Exception as err:  # noqa: BLE001 - retry any transport/HTTP failure
            last_err = err
            wait = 5 * attempt
            log(f"  fetch failed ({err}); retry {attempt}/{retries} in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def fetch_json(url: str, cache_name: str | None, **kw):
    return json.loads(fetch(url, cache_name, **kw))


# --- projections -----------------------------------------------------------------------

def to_bng(geom):
    return transform(_to_bng.transform, geom)


def to_wgs(geom):
    return transform(_to_wgs.transform, geom)


def lonlat_to_merc(lon: float, lat: float) -> tuple[float, float]:
    return _to_merc.transform(lon, lat)


def min_zoom_for_scale(max_scale_denominator: float) -> int:
    """Smallest Leaflet (EPSG:3857) zoom whose OGC scale is <= max_scale_denominator."""
    for z in range(0, 23):
        res = 40075016.68557849 / (256 * 2**z)
        if res / 0.00028 <= max_scale_denominator:
            return z
    return 22


# --- GeoJSON output --------------------------------------------------------------------

def round_geom(geom, dp: int = COORD_DP):
    """Round coordinates to `dp` decimals, repairing any validity problems rounding introduces.
    On a polygonal input, rounding can occasionally collapse a thin spur into a self-touching
    edge; make_valid() then returns a GeometryCollection with a dangling LineString/Point
    alongside the real Polygon(s) (seen on some LSOAs nationally, not on Hackney's smaller set).
    We keep only the polygonal part in that case, since the input was polygonal."""
    rounded = shapely.set_precision(geom, 10**-dp, mode="pointwise")
    if not rounded.is_valid:
        rounded = shapely.make_valid(rounded)
    if rounded.geom_type == "GeometryCollection" and geom.geom_type in ("Polygon", "MultiPolygon"):
        polys = [g for g in rounded.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        rounded = shapely.union_all(polys) if polys else rounded
    return rounded


def _round_coords(obj, dp: int):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), dp) for v in obj]
        return [_round_coords(o, dp) for o in obj]
    return obj


def feature(geom, props: dict) -> dict:
    g = mapping(geom)
    g = {"type": g["type"], "coordinates": _round_coords(g["coordinates"], COORD_DP)}
    return {"type": "Feature", "properties": props, "geometry": g}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def write_geojson(name: str, features: list[dict], sources: list[dict], notes: list[str] | None = None) -> Path:
    meta = {"generated": now_iso(), "sources": sources}
    if notes:
        meta["notes"] = notes
    fc = {"type": "FeatureCollection", "metadata": meta, "features": features}
    path = OUT / name
    size = write_json(path, fc)
    log(f"wrote {path.relative_to(ROOT)}: {len(features)} features, {size/1024:.0f} KB")
    if size > MAX_FILE_BYTES:
        raise RuntimeError(f"{name} is {size} bytes, over the {MAX_FILE_BYTES} byte budget")
    return path


def load_geojson(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def boundary_shape():
    """Hackney boundary (WGS84 shapely geometry) from the already-built boundary layer."""
    fc = load_geojson("boundary.geojson")
    return shape(fc["features"][0]["geometry"])


def buffered_wgs(geom_wgs, metres: float):
    return to_wgs(to_bng(geom_wgs).buffer(metres))


def haversine_m(lon1, lat1, lon2, lat2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --- attribution strings ---------------------------------------------------------------

def ons_boundary_attr(year: int) -> str:
    return (
        "Source: Office for National Statistics licensed under the Open Government Licence v.3.0. "
        f"Contains OS data © Crown copyright and database right {year}"
    )


OGL = "Open Government Licence v3.0"
OSM_ATTR = "© OpenStreetMap contributors, ODbL"
