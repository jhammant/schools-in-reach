"""Discover and verify keyless WMS overlays (flood, noise, air quality) usable from Leaflet."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from PIL import Image

from common import OGL, OUT, fetch, lonlat_to_merc, log, min_zoom_for_scale, now_iso, write_json

WMS_NS = "{http://www.opengis.net/wms}"
XLINK = "{http://www.w3.org/1999/xlink}href"

# Hackney test extent from the brief (lon -0.10..-0.02, lat 51.53..51.58).
TEST_BBOX_LONLAT = (-0.10, 51.53, -0.02, 51.58)
TEST_SIZE = 512
# A layer must paint at least this share of pixels; a few stray pixels (labels, artefacts) do not count.
MIN_VISIBLE_FRACTION = 0.002
REPEAT_RENDERS = 2

EA_ATTR = "© Environment Agency copyright and/or database right {year}. All rights reserved. Contains OS data © Crown copyright and database right {year}."
DEFRA_NOISE_ATTR = "Strategic noise mapping (Round 4, 2022) © Crown copyright and database rights {year} Defra; contains OS data © Crown copyright and database right {year}."
UKAIR_ATTR = "© Crown copyright {year} Defra via uk-air.defra.gov.uk, licensed under the Open Government Licence v3.0. Modelled by Ricardo (Pollution Climate Mapping)."

EA = "https://environment.data.gov.uk/spatialdata"
UKAIR_CONFIG = "https://uk-air.defra.gov.uk/data/gis-mapping/CONFIG-STUB.js"
UKAIR_SERVER = "https://ukair.maps.rcdo.co.uk/ukairserver/services"


def ukair_pcm_service() -> str:
    """UK-AIR's GIS viewer config names the current PCM service (e.g. 'aq_amb_2024')."""
    try:
        js = fetch(UKAIR_CONFIG, "ukair_config_stub.js").decode("utf-8", "replace")
        m = re.search(r"PCMService\s*=\s*['\"]([\w-]+)['\"]", js)
        if m:
            return m.group(1)
    except Exception as err:  # noqa: BLE001
        log(f"  UK-AIR config unavailable ({err}); using pinned PCM service")
    return "aq_amb_2024"


def candidates() -> list[dict]:
    pcm = ukair_pcm_service()
    return [
        {
            "id": "ea_flood_zones_2_3",
            "title": "Flood Map for Planning: Flood Zones 2 and 3 (rivers and sea)",
            "group": "Flood risk",
            "url": f"{EA}/flood-map-for-planning-flood-zones/wms",
            "layer_match": "Flood_Zones_2_3_Rivers_and_Sea",
            "licence": OGL,
            "attribution": EA_ATTR,
        },
        {
            "id": "ea_flood_zones_climate_change",
            "title": "Flood Map for Planning: Flood Zones plus climate change (rivers and sea)",
            "group": "Flood risk",
            "url": f"{EA}/flood-zones-plus-climate-change/wms",
            "layer_match": "Flood_Zone_River_and_Sea_plus_CCP1",
            "licence": OGL,
            "attribution": EA_ATTR,
        },
        {
            "id": "ea_rofrs",
            "title": "Risk of flooding from rivers and sea (NaFRA2, likelihood bands)",
            "group": "Flood risk",
            "url": f"{EA}/nafra2-risk-of-flooding-from-rivers-and-sea/wms",
            "layer_match": "rofrs_4band",
            "licence": OGL,
            "attribution": EA_ATTR,
        },
        {
            "id": "ea_rofsw",
            "title": "Risk of flooding from surface water (NaFRA2, likelihood bands)",
            "group": "Flood risk",
            "url": f"{EA}/nafra2-risk-of-flooding-from-surface-water/wms",
            "layer_match": "rofsw",
            "licence": OGL,
            "attribution": EA_ATTR,
        },
        {
            "id": "defra_road_noise_lden",
            "title": "Road noise Lden (24-hour weighted), Round 4 strategic noise mapping",
            "group": "Noise",
            "url": f"{EA}/road-noise-all-metrics-england-round-4/wms",
            "layer_match": "Road_Noise_Lden_England_Round_4_All",
            "licence": OGL,
            "attribution": DEFRA_NOISE_ATTR,
        },
        {
            "id": "defra_road_noise_lnight",
            "title": "Road noise Lnight (night-time), Round 4 strategic noise mapping",
            "group": "Noise",
            "url": f"{EA}/road-noise-all-metrics-england-round-4/wms",
            "layer_match": "Road_Noise_Lnight_England_Round_4_All",
            "licence": OGL,
            "attribution": DEFRA_NOISE_ATTR,
        },
        {
            "id": "defra_rail_noise_lden",
            "title": "Rail noise Lden (24-hour weighted), Round 4 strategic noise mapping",
            "group": "Noise",
            "url": f"{EA}/noise-data/wms",
            "layer_match": "Rail_Noise_Lden_England_Round_4_All",
            "licence": OGL,
            "attribution": DEFRA_NOISE_ATTR,
        },
        {
            "id": "defra_pcm_no2_background",
            "title": "NO2 annual mean background concentration, 1 km grid (Defra PCM {year})",
            "group": "Air quality",
            "url": f"{UKAIR_SERVER}/{pcm}/NO2/MapServer/WMSServer",
            "layer_latest_year": True,
            "licence": OGL,
            "attribution": UKAIR_ATTR,
        },
        {
            "id": "defra_pcm_pm25_background",
            "title": "PM2.5 annual mean background concentration, 1 km grid (Defra PCM {year})",
            "group": "Air quality",
            "url": f"{UKAIR_SERVER}/{pcm}/PM25/MapServer/WMSServer",
            "layer_latest_year": True,
            "licence": OGL,
            "attribution": UKAIR_ATTR,
        },
        {
            "id": "defra_pcm_no2_roadside",
            "title": "NO2 annual mean roadside concentration, major roads (Defra PCM {year})",
            "group": "Air quality",
            "url": f"{UKAIR_SERVER}/{pcm}/NO2Roads/MapServer/WMSServer",
            "layer_latest_year": True,
            "licence": OGL,
            "attribution": UKAIR_ATTR,
        },
    ]


def _text(el, tag):
    x = el.find(WMS_NS + tag)
    return x.text.strip() if x is not None and x.text else None


def read_capabilities(c: dict) -> dict:
    body = fetch(c["url"], None, params={"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"}, timeout=60)
    root = ET.fromstring(body)
    layers = []
    for lyr in root.iter(WMS_NS + "Layer"):
        name = _text(lyr, "Name")
        if not name:
            continue
        legend = lyr.find(f"{WMS_NS}Style/{WMS_NS}LegendURL/{WMS_NS}OnlineResource")
        layers.append({
            "name": name,
            "title": _text(lyr, "Title"),
            "max_scale": float(_text(lyr, "MaxScaleDenominator") or 0) or None,
            "legend": legend.get(XLINK).replace("%26", "&") if legend is not None else None,
        })
    if c.get("layer_latest_year"):
        yearly = [lyr for lyr in layers if lyr["title"] and re.fullmatch(r"\d{4}", lyr["title"])]
        if not yearly:
            raise ValueError("no yearly layers in capabilities")
        chosen = max(yearly, key=lambda lyr: int(lyr["title"]))
        chosen["year"] = int(chosen["title"])
        return chosen
    for lyr in layers:
        if lyr["name"] == c["layer_match"]:
            return lyr
    raise ValueError(f"layer {c['layer_match']} not in capabilities")


def getmap(url: str, layer: str, bbox_merc: tuple[float, float, float, float], size: int) -> dict:
    params = {
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": layer, "STYLES": "",
        "FORMAT": "image/png", "TRANSPARENT": "TRUE", "CRS": "EPSG:3857",
        "BBOX": ",".join(f"{v:.2f}" for v in bbox_merc), "WIDTH": str(size), "HEIGHT": str(size),
    }
    body = fetch(url, None, params=params, timeout=90, retries=2)
    if body[:8] != b"\x89PNG\r\n\x1a\n":
        snippet = body[:200].decode("utf-8", "replace").replace("\n", " ")
        return {"ok": False, "fatal": True, "fraction": 0, "error": f"not a PNG: {snippet}"}
    img = Image.open(io.BytesIO(body)).convert("RGBA")
    total = img.width * img.height
    colours = img.getcolors(maxcolors=total) or []
    visible = [(n, c) for n, c in colours if c[3] > 0]
    opaque = sum(n for n, _ in visible)
    black = sum(n for n, c in visible if max(c[:3]) < 16)
    fraction = opaque / total
    out = {"ok": False, "fatal": False, "fraction": round(fraction, 4), "colours": len(visible), "error": None}
    if fraction < MIN_VISIBLE_FRACTION:
        out["error"] = f"PNG is (almost) fully transparent: {opaque} visible pixels of {total}"
    elif fraction == 1 and len(visible) <= 1:
        out["error"] = "PNG is a single flat colour"
    elif black > 0.5 * opaque:
        out["error"] = "rendering artefact: most visible pixels are pure black"
    else:
        out["ok"] = True
    return out


def verify(c: dict) -> dict:
    lyr = read_capabilities(c)
    x0, y0 = lonlat_to_merc(TEST_BBOX_LONLAT[0], TEST_BBOX_LONLAT[1])
    x1, y1 = lonlat_to_merc(TEST_BBOX_LONLAT[2], TEST_BBOX_LONLAT[3])
    tiles = [(x0, y0, x1, y1)]
    results = [getmap(c["url"], lyr["name"], tiles[0], TEST_SIZE)]
    if not results[0]["ok"] and not results[0]["fatal"]:
        # Many EA layers switch off above 1:50,000; retry as a 2x2 grid of 512 px tiles (about 1:31,000).
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        tiles = [(x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1)]
        results = [getmap(c["url"], lyr["name"], b, TEST_SIZE) for b in tiles]
    passing = [(b, r) for b, r in zip(tiles, results) if r["ok"]]
    if not passing:
        return {"layer": lyr, "tiles": len(tiles), "result": results[0]}
    # Render every tile twice more: a healthy service returns the same picture each time
    # (one service tested returned random garbage for some requests).
    for bbox, first in zip(tiles, results):
        repeats = [getmap(c["url"], lyr["name"], bbox, TEST_SIZE) for _ in range(REPEAT_RENDERS)]
        fractions = [first["fraction"]] + [r["fraction"] for r in repeats]
        if len({r["ok"] for r in [first, *repeats]}) > 1 or max(fractions) - min(fractions) > 0.01:
            bad = {**first, "ok": False,
                   "error": f"inconsistent renders of the same tile (visible fractions {fractions})"}
            return {"layer": lyr, "tiles": len(tiles), "result": bad}
    _, best = max(passing, key=lambda br: br[1]["fraction"])
    return {"layer": lyr, "tiles": len(tiles), "result": best}


def legend_ok(url: str | None) -> bool:
    if not url:
        return False
    try:
        body = fetch(url, None, timeout=60, retries=1)
        return body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"GIF" or body[:3] == b"\xff\xd8\xff"
    except Exception:  # noqa: BLE001
        return False


def build_env_layers() -> dict:
    verified, dropped = [], []
    today = datetime.now(timezone.utc).date().isoformat()
    year = datetime.now(timezone.utc).year
    for c in candidates():
        try:
            v = verify(c)
        except Exception as err:  # noqa: BLE001
            dropped.append({"id": c["id"], "url": c["url"], "reason": str(err)[:300]})
            log(f"env DROP {c['id']}: {err}")
            continue
        lyr, res = v["layer"], v["result"]
        if not res["ok"]:
            dropped.append({"id": c["id"], "url": c["url"], "reason": res["error"]})
            log(f"env DROP {c['id']}: {res['error']}")
            continue
        data_year = lyr.get("year")
        entry = {
            "id": c["id"],
            "title": c["title"].format(year=data_year),
            "group": c["group"],
            "type": "wms",
            "url": c["url"],
            "layers": lyr["name"],
            "format": "image/png",
            "transparent": True,
            "version": "1.3.0",
            "attribution": c["attribution"].format(year=year),
            "licence": c["licence"],
            "legend_url": lyr["legend"] if legend_ok(lyr["legend"]) else None,
            "verified_at": now_iso(),
        }
        if lyr.get("max_scale"):
            entry["min_zoom"] = min_zoom_for_scale(lyr["max_scale"])
        if data_year:
            entry["data_year"] = data_year
        entry["verification"] = {
            "bbox_lonlat": list(TEST_BBOX_LONLAT),
            "crs": "EPSG:3857",
            "size_px": TEST_SIZE,
            "tiles_needed": v["tiles"],
            "visible_pixel_fraction": res["fraction"],
        }
        verified.append(entry)
        log(f"env OK   {c['id']}: layer={lyr['name']} visible={res['fraction']} tiles={v['tiles']}"
            + (f" min_zoom={entry['min_zoom']}" if "min_zoom" in entry else ""))

    doc = {
        "metadata": {
            "generated": now_iso(),
            "verified_on": today,
            "how_verified": (
                "GetCapabilities checked for the layer, then WMS 1.3.0 GetMap PNG requested in EPSG:3857 for "
                f"bbox lon {TEST_BBOX_LONLAT[0]}..{TEST_BBOX_LONLAT[2]}, lat {TEST_BBOX_LONLAT[1]}..{TEST_BBOX_LONLAT[3]} at "
                f"{TEST_SIZE}x{TEST_SIZE}; accepted only if the response is a PNG in which at least 0.2% of pixels are visible (non-transparent) and not one flat colour. "
                "Layers with a MaxScaleDenominator were re-tested as a 2x2 grid of 512 px tiles. Every tile is rendered three times and must match; mostly pure-black output is treated as a rendering artefact."
            ),
            "leaflet_usage": "L.tileLayer.wms(url, {layers, format, transparent, version, attribution, minZoom: min_zoom})",
            "sources": [
                {"title": "Environment Agency / Defra Data Services Platform WMS", "url": "https://environment.data.gov.uk/",
                 "licence": OGL, "attribution": EA_ATTR.format(year=year)},
                {"title": "Defra UK-AIR Pollution Climate Mapping (Ricardo ArcGIS WMS)", "url": "https://uk-air.defra.gov.uk/data/gis-mapping/",
                 "licence": OGL, "attribution": UKAIR_ATTR.format(year=year)},
            ],
            "dropped": dropped,
        },
        "layers": verified,
    }
    size = write_json(OUT / "env_layers.json", doc)
    log(f"wrote env_layers.json: {len(verified)} verified, {len(dropped)} dropped, {size/1024:.0f} KB")
    return {"verified": [e["id"] for e in verified], "dropped": dropped}
