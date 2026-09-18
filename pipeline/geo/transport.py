"""Rail/Overground/Underground/DLR/Elizabeth line stations and bus stops (NaPTAN + TfL Unified API)."""

from __future__ import annotations

import csv
import io
import json
import re
import time

from shapely.geometry import Point

from common import (
    OGL,
    boundary_shape,
    buffered_wgs,
    feature,
    fetch,
    log,
    write_geojson,
)

NAPTAN = "https://naptan.api.dft.gov.uk/v1/access-nodes"
TFL = "https://api.tfl.gov.uk/StopPoint"
STATION_BUFFER_M = 1000
BUS_MAX_BYTES = 1_000_000

NAPTAN_SOURCE = {
    "title": "NaPTAN (National Public Transport Access Nodes), DfT",
    "url": "https://naptan.api.dft.gov.uk/v1/access-nodes",
    "licence": OGL,
    "attribution": "Contains public sector information licensed under the Open Government Licence v3.0 (Department for Transport, NaPTAN).",
}
TFL_SOURCE = {
    "title": "TfL Unified API StopPoint (modes and lines served)",
    "url": "https://api.tfl.gov.uk/",
    "licence": "TfL Open Data transport data terms (OGL-based)",
    "attribution": "Powered by TfL Open Data. Contains OS data © Crown copyright and database rights 2016 and Geomni UK Map data © and database rights 2019.",
}

MODE_NAMES = {
    "national-rail": "national_rail",
    "overground": "overground",
    "tube": "underground",
    "dlr": "dlr",
    "elizabeth-line": "elizabeth_line",
}
MODE_ORDER = list(MODE_NAMES.values())


def naptan_rows(area_codes: str, cache: str) -> list[dict]:
    raw = fetch(NAPTAN, cache, params={"dataFormat": "csv", "atcoAreaCodes": area_codes}, timeout=300)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def _pt(row: dict) -> Point | None:
    try:
        return Point(float(row["Longitude"]), float(row["Latitude"]))
    except (TypeError, ValueError):
        return None


def clean_station_name(name: str) -> str:
    name = re.sub(r"\s+(Rail|Underground|DLR|Elizabeth line|London Overground)\s+Station$", "", name)
    name = re.sub(r"\s+Station$", "", name)
    return re.sub(r"\s*\((London)\)$", "", name).strip()


def naptan_to_tfl_id(atco: str) -> str:
    # NaPTAN access-node ATCO codes -> TfL stop-area ids: 9100XXXX -> 910GXXXX, 9400ZZLUXXX -> 940GZZLUXXX
    if atco.startswith("9100"):
        return "910G" + atco[4:]
    if atco.startswith("9400"):
        return "940G" + atco[4:]
    return atco


def tfl_stoppoints(ids: list[str]) -> dict[str, dict]:
    """Map each requested TfL id -> resolved StopPoint (station or hub) from the Unified API."""
    resolved: dict[str, dict] = {}
    for i in range(0, len(ids), 10):
        batch = ids[i:i + 10]
        body = fetch(f"{TFL}/{','.join(batch)}", f"tfl_stoppoint_{'_'.join(batch)}.json", retries=3)
        data = json.loads(body)
        items = data if isinstance(data, list) else [data]
        for sp in items:
            members = set()

            def walk(node):
                members.add(node.get("naptanId"))
                for ch in node.get("children", []) or []:
                    if ch.get("stopType") in ("NaptanRailStation", "NaptanMetroStation", "TransportInterchange"):
                        walk(ch)

            walk(sp)
            for rid in batch:
                if rid in members:
                    resolved[rid] = sp
        time.sleep(0.3)
    return resolved


def build_transport() -> dict:
    boundary = boundary_shape()
    area = buffered_wgs(boundary, STATION_BUFFER_M)
    rows = naptan_rows("910,940", "naptan_910_940.csv")
    stations = []
    for r in rows:
        if r["Status"] != "active":
            continue
        atco = r["ATCOCode"]
        if not ((r["StopType"] == "RLY" and atco.startswith("9100"))
                or (r["StopType"] == "MET" and (atco.startswith("9400ZZLU") or atco.startswith("9400ZZDL")))):
            continue
        p = _pt(r)
        if p is not None and area.contains(p):
            stations.append(r)
    log(f"naptan: {len(stations)} station access nodes within {STATION_BUFFER_M} m")

    tfl_ids = sorted({naptan_to_tfl_id(r["ATCOCode"]) for r in stations})
    try:
        tfl = tfl_stoppoints(tfl_ids)
    except Exception as err:  # noqa: BLE001
        log(f"  TfL API unavailable ({err}); falling back to NaPTAN-only modes")
        tfl = {}

    groups: dict[str, dict] = {}
    for r in stations:
        tid = naptan_to_tfl_id(r["ATCOCode"])
        sp = tfl.get(tid)
        key = sp["naptanId"] if sp else "name:" + clean_station_name(r["CommonName"]).lower()
        g = groups.setdefault(key, {"naptan": [], "pts": [], "sp": sp, "names": []})
        g["naptan"].append(r["ATCOCode"])
        g["pts"].append(_pt(r))
        g["names"].append(clean_station_name(r["CommonName"]))

    feats = []
    for key, g in groups.items():
        sp = g["sp"]
        if sp:
            modes_raw = [m["modeName"] for m in sp.get("lineModeGroups", []) if m["modeName"] in MODE_NAMES]
            modes = sorted({MODE_NAMES[m] for m in modes_raw}, key=MODE_ORDER.index)
            line_ids = {lid for m in sp.get("lineModeGroups", []) if m["modeName"] in MODE_NAMES
                        for lid in m["lineIdentifier"]}
            lines = sorted({ln["name"] for ln in sp.get("lines", []) if ln["id"] in line_ids})
            name = clean_station_name(sp["commonName"])
            lon, lat = sp["lon"], sp["lat"]
        else:
            modes = sorted({"underground" if a.startswith("9400ZZLU") else "dlr" if a.startswith("9400ZZDL")
                            else "national_rail" for a in g["naptan"]}, key=MODE_ORDER.index)
            lines = []
            name = g["names"][0]
            lon = sum(p.x for p in g["pts"]) / len(g["pts"])
            lat = sum(p.y for p in g["pts"]) / len(g["pts"])
        if not modes:
            log(f"  skipping {name}: no rail modes reported by TfL")
            continue
        props = {
            "name": name,
            "modes": modes,
            "lines": lines,
            "in_borough": boundary.contains(Point(lon, lat)),
            "naptan": sorted(g["naptan"]),
        }
        feats.append(feature(Point(lon, lat), props))
    feats.sort(key=lambda f: f["properties"]["name"])
    notes = [
        f"Stations with a NaPTAN rail (RLY 9100*) or Underground/DLR (MET 9400ZZLU*/ZZDL*) access node within {STATION_BUFFER_M} m of the Hackney boundary.",
        "Access nodes are grouped into stations/interchanges using TfL StopPoint hubs; position is the TfL hub/station coordinate.",
        "modes: national_rail, overground, underground, dlr, elizabeth_line. lines: TfL line names (Overground lines use their 2024 names).",
        "in_borough: station point lies inside the Hackney boundary.",
    ]
    write_geojson("transport.geojson", feats, [NAPTAN_SOURCE, TFL_SOURCE], notes)
    return {"count": len(feats)}


def build_bus_stops() -> dict:
    boundary = boundary_shape()
    rows = naptan_rows("490", "naptan_490.csv")
    feats = []
    for r in rows:
        if r["StopType"] != "BCT" or r["Status"] != "active":
            continue
        p = _pt(r)
        if p is None or not boundary.contains(p):
            continue
        indicator = (r["Indicator"] or "").strip() or None
        feats.append(feature(p, {"name": r["CommonName"], "indicator": indicator, "atco": r["ATCOCode"]}))
    feats.sort(key=lambda f: (f["properties"]["name"], f["properties"]["indicator"] or ""))
    notes = ["Active on-street bus stops (NaPTAN StopType BCT, London area 490) inside the Hackney boundary. indicator is the stop letter/label (e.g. 'Stop H', '->N')."]
    path = write_geojson("bus_stops.geojson", feats, [NAPTAN_SOURCE], notes)
    size = path.stat().st_size
    if size > BUS_MAX_BYTES:
        path.unlink()
        log(f"bus_stops.geojson would be {size} bytes (> {BUS_MAX_BYTES}); not written")
        return {"count": 0, "skipped": True}
    return {"count": len(feats), "bytes": size}
