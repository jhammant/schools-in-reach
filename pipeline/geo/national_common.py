"""Shared helpers for the national (England-wide) geo build: paginated ArcGIS queries,
the England country outline, and misc small utilities used by more than one national_*
module. Hackney's own pipeline (areas.py / build.py) is untouched."""

from __future__ import annotations

import json
import re
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

from areas import ARCGIS
from common import fetch, fetch_json, log, now_iso, write_json


def layer_meta(service: str) -> dict:
    return fetch_json(f"{ARCGIS}/{service}/FeatureServer/0?f=json", f"{service}_layer.json")


def paginated_features(
    service: str,
    where: str,
    out_fields: str,
    cache_prefix: str,
    *,
    geometry: bool = False,
    out_sr: int = 4326,
    page_size: int = 1000,
) -> list[dict]:
    """Fetch every ArcGIS feature matching `where`, paging with resultOffset (services here
    cap at 1000-2000 records per call and silently truncate rather than erroring)."""
    all_feats: list[dict] = []
    offset = 0
    while True:
        params = {
            "f": "geojson" if geometry else "json",
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true" if geometry else "false",
            "resultRecordCount": page_size,
            "resultOffset": offset,
        }
        if geometry:
            params["outSR"] = out_sr
        url = f"{ARCGIS}/{service}/FeatureServer/0/query"
        body = fetch(url, f"{cache_prefix}_p{offset}.json", data=params)
        data = json.loads(body)
        feats = data["features"]
        all_feats.extend(feats)
        if len(feats) < page_size:
            break
        offset += page_size
    log(f"  {service}: {len(all_feats)} features ({cache_prefix})")
    return all_feats


COUNTRY_SERVICE = "Countries_December_2025_Boundaries_UK_BUC"
COUNTRY_FALLBACK_SERVICES = [
    "Countries_December_2025_Boundaries_UK_BUC",
    "Countries_December_2023_Boundaries_UK_BUC",
    "Countries_December_2022_UK_BUC",
]


def england_boundary_wgs():
    """England's outline (ultra-generalised), for clipping national point layers to England
    only (drops Scotland/Wales NaPTAN stops etc). Falls back through a few known service
    names/years since 'latest' naming isn't auto-discovered here."""
    for svc in COUNTRY_FALLBACK_SERVICES:
        try:
            layer = layer_meta(svc)
            code_field = next(f["name"] for f in layer["fields"] if re.fullmatch(r"CTRY\d\dCD", f["name"]))
            feats = paginated_features(svc, f"{code_field}='E92000001'", f"{code_field}", f"{svc}_england",
                                        geometry=True)
            if feats:
                geoms = [shape(f["geometry"]) for f in feats]
                return unary_union(geoms)
        except Exception as err:  # noqa: BLE001
            log(f"  country service {svc} failed ({err})")
    raise RuntimeError("could not fetch an England country boundary from any known ONS service")


def write_geojson_to(path: Path, features: list[dict], sources: list[dict], notes: list[str] | None = None,
                      max_bytes: int | None = None) -> int:
    """Like common.write_geojson but to an arbitrary path and with a caller-chosen size cap
    (Hackney's 1.5 MB guard is too tight for national per-LA files)."""
    meta = {"generated": now_iso(), "sources": sources}
    if notes:
        meta["notes"] = notes
    fc = {"type": "FeatureCollection", "metadata": meta, "features": features}
    size = write_json(path, fc)
    if max_bytes and size > max_bytes:
        raise RuntimeError(f"{path} is {size} bytes, over the {max_bytes} byte budget")
    return size
