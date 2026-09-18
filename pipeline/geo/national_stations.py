"""site/data/england/stations.geojson: every rail, Underground, Overground, Elizabeth line, DLR,
tram and metro station in England, one point per physical station/interchange.

Source: NaPTAN national access-nodes (one national CSV download, cached, filtered client-side --
the API's `stopTypes` query param turned out not to filter server-side, so we just download once
and slice locally). StopType RLY = heavy/main-line rail. StopType MET also covers London
Underground/DLR/trams *and* heritage/tourist railways (Severn Valley, Talyllyn, etc) and Scotland's
Glasgow Subway/Edinburgh Trams under the same StopType, so MET rows are restricted to the England
systems in MET_SYSTEMS below (identified by the operator code embedded in the ATCOCode, e.g.
9400ZZLU... = London Underground, 9400ZZMA... = Manchester Metrolink).

Within Greater London + the Elizabeth line's full extent (Reading/Heathrow to Shenfield) the TfL
Unified API resolves interchanges and gives real mode names (national_rail vs overground vs
elizabeth_line) and line names, exactly as Hackney's transport.geojson does. Outside that area
there is no free interchange API, so entrances/platforms are merged by name+proximity, and a
separate pass merges rail<->metro/tram pairs within 200 m regardless of name (this is what turns
NaPTAN's separate "Newcastle Rail Station" and "Central Station (Tyne and Wear Metro)" rows, ~110 m
apart, into one Newcastle Central Station point with modes ["national_rail","metro"]).
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from collections import Counter

from shapely.geometry import Point
from shapely.strtree import STRtree

from common import ROOT, feature, fetch, haversine_m, log, to_bng
from national_common import england_boundary_wgs, write_geojson_to
from transport import NAPTAN, NAPTAN_SOURCE, TFL, TFL_SOURCE, naptan_to_tfl_id

OUT_PATH = ROOT / "site" / "data" / "england" / "stations.geojson"
MAX_BYTES = 5_000_000

# England's real light-rail/metro/tram operators, keyed by the 2-letter code embedded in the
# ATCOCode after "ZZ" (e.g. 9400ZZMA... -> Manchester Metrolink). Everything else under
# StopType MET is either a heritage/tourist railway or outside England (Glasgow Subway 'GL',
# Edinburgh Trams 'ED') and is dropped.
MET_SYSTEMS = {
    "LU": "underground",   # London Underground
    "DL": "dlr",            # Docklands Light Railway
    "TW": "metro",           # Tyne and Wear Metro
    "MA": "tram",            # Manchester Metrolink
    "SY": "tram",            # Sheffield Supertram
    "NO": "tram",            # Nottingham Express Transit
    "WM": "tram",             # West Midlands Metro
    "BP": "tram",             # Blackpool Tramway
    "CR": "tram",             # Croydon Tramlink (also TfL-covered)
}
RAIL_FAMILY = {"national_rail", "overground", "elizabeth_line"}

# TfL-covered extent: Greater London plus the Elizabeth line's full run (Reading/Heathrow to
# Shenfield) and the Metropolitan line's outer termini (Amersham/Chesham).
TFL_BBOX = (-1.10, 51.15, 0.60, 51.80)  # lon_min, lat_min, lon_max, lat_max

SUFFIX_PAREN = re.compile(
    r"\s*\((?:[^()]*(?:Metrolink|Metro|Tramway|Tramlink|Supertram|Underground|DLR|Overground|Railway)[^()]*)\)\s*$",
    re.I,
)


def clean_name(name: str | None) -> str:
    name = SUFFIX_PAREN.sub("", name or "")
    name = re.sub(r"\s+Tram Stop$", "", name, flags=re.I)
    name = re.sub(r"\s+(Rail|Underground|DLR|Elizabeth line|London Overground|Metro)\s+Station$", "", name, flags=re.I)
    name = re.sub(r"\s+Station$", "", name, flags=re.I)
    name = re.sub(r"\s*\((London)\)$", "", name).strip()
    return name


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def naptan_rows_national() -> list[dict]:
    raw = fetch(NAPTAN, "naptan_national.csv", params={"dataFormat": "csv"}, timeout=600)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def build_candidates(rows: list[dict], england) -> list[dict]:
    out = []
    dropped_outside = 0
    dropped_heritage = 0
    for r in rows:
        if r["Status"] != "active" or r["StopType"] not in ("RLY", "MET"):
            continue
        try:
            lon, lat = float(r["Longitude"]), float(r["Latitude"])
        except (TypeError, ValueError):
            continue
        if r["StopType"] == "RLY":
            mode = "national_rail"
        else:
            m = re.search(r"ZZ([A-Z]{2})", r["ATCOCode"])
            system = m.group(1) if m else None
            if system not in MET_SYSTEMS:
                dropped_heritage += 1
                continue
            mode = MET_SYSTEMS[system]
        pt = Point(lon, lat)
        if not england.contains(pt) and not england.buffer(0.01).contains(pt):
            dropped_outside += 1
            continue
        out.append({
            "atco": r["ATCOCode"],
            "name": clean_name(r["CommonName"]),
            "mode": mode,
            "lon": lon,
            "lat": lat,
        })
    log(f"naptan: {len(out)} active RLY/MET candidates in England "
        f"(dropped {dropped_outside} outside England, {dropped_heritage} non-England MET systems)")
    return out


def tfl_lookup(tfl_ids: list[str]) -> dict[str, dict]:
    """Resolved TfL StopPoints for the given ids, tolerating individual batch failures
    (most non-London ids simply aren't in TfL's system) instead of aborting the whole build."""
    resolved: dict[str, dict] = {}
    for i in range(0, len(tfl_ids), 10):
        batch = tfl_ids[i:i + 10]
        try:
            body = fetch(f"{TFL}/{','.join(batch)}", f"tfl_stoppoint_national_{'_'.join(batch)}.json", retries=2,
                          timeout=60)
        except Exception as err:  # noqa: BLE001
            log(f"  TfL batch failed ({len(batch)} ids): {err}")
            time.sleep(0.3)
            continue
        data = json.loads(body)
        items = data if isinstance(data, list) else [data]
        for sp in items:
            if "naptanId" not in sp:
                continue
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


MODE_NAMES = {
    "national-rail": "national_rail",
    "overground": "overground",
    "tube": "underground",
    "dlr": "dlr",
    "elizabeth-line": "elizabeth_line",
    "tram": "tram",
}
MODE_ORDER = ["national_rail", "overground", "elizabeth_line", "underground", "dlr", "tram", "metro"]


def group_via_tfl(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """TfL-hub grouping for candidates inside TFL_BBOX (mirrors transport.py's Hackney logic).
    Returns (grouped_points, leftover_candidates_not_resolved_by_tfl)."""
    lon0, lat0, lon1, lat1 = TFL_BBOX
    in_bbox, out_bbox = [], []
    for c in candidates:
        (in_bbox if lon0 <= c["lon"] <= lon1 and lat0 <= c["lat"] <= lat1 else out_bbox).append(c)
    tfl_ids = sorted({naptan_to_tfl_id(c["atco"]) for c in in_bbox})
    log(f"tfl: looking up {len(tfl_ids)} stop ids across {len(in_bbox)} in-bbox candidates")
    resolved = tfl_lookup(tfl_ids)

    groups: dict[str, dict] = {}
    leftover: list[dict] = []
    for c in in_bbox:
        tid = naptan_to_tfl_id(c["atco"])
        sp = resolved.get(tid)
        if sp is None:
            leftover.append(c)
            continue
        key = sp["naptanId"]
        g = groups.setdefault(key, {"naptan": set(), "sp": sp})
        g["naptan"].add(c["atco"])

    points = []
    for key, g in groups.items():
        sp = g["sp"]
        modes_raw = [m["modeName"] for m in sp.get("lineModeGroups", []) if m["modeName"] in MODE_NAMES]
        modes = sorted({MODE_NAMES[m] for m in modes_raw}, key=MODE_ORDER.index)
        if not modes:
            continue
        line_ids = {lid for m in sp.get("lineModeGroups", []) if m["modeName"] in MODE_NAMES
                    for lid in m["lineIdentifier"]}
        lines = sorted({ln["name"] for ln in sp.get("lines", []) if ln["id"] in line_ids})
        points.append({
            "name": clean_name(sp["commonName"]),
            "modes": modes,
            "lines": lines,
            "naptan": sorted(g["naptan"]),
            "lon": sp["lon"],
            "lat": sp["lat"],
        })
    return points, out_bbox + leftover


def group_by_name_proximity(candidates: list[dict], radius_m: float = 80.0) -> list[dict]:
    """Merge candidates with the same normalised name within `radius_m` of each other (handles
    NaPTAN's multiple platform/entrance rows for one station, e.g. 5 Clapham-Junction-style rows).
    No TfL data here, so `lines` stays empty and `modes` is just what NaPTAN/MET_SYSTEMS implies."""
    by_name: dict[str, list[dict]] = {}
    for c in candidates:
        by_name.setdefault(_norm(c["name"]), []).append(c)
    points = []
    for _name, items in by_name.items():
        used = [False] * len(items)
        for i, c in enumerate(items):
            if used[i]:
                continue
            cluster = [c]
            used[i] = True
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                if haversine_m(c["lon"], c["lat"], items[j]["lon"], items[j]["lat"]) <= radius_m:
                    cluster.append(items[j])
                    used[j] = True
            lon = sum(x["lon"] for x in cluster) / len(cluster)
            lat = sum(x["lat"] for x in cluster) / len(cluster)
            modes = sorted({x["mode"] for x in cluster}, key=MODE_ORDER.index)
            points.append({
                "name": cluster[0]["name"],
                "modes": modes,
                "lines": [],
                "naptan": sorted({x["atco"] for x in cluster}),
                "lon": lon,
                "lat": lat,
            })
    return points


def merge_rail_metro_interchanges(points: list[dict], radius_m: float = 200.0) -> list[dict]:
    """Second pass: a plain rail point and a metro/tram/underground/dlr point within `radius_m`
    of each other are almost always the same interchange under two different NaPTAN names
    (e.g. Newcastle Rail Station + Central Station (Tyne and Wear Metro)). Union-find merge,
    restricted to rail<->non-rail pairs only, so closely-spaced same-family stops never merge."""
    n = len(points)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    bng_pts = [to_bng(Point(p["lon"], p["lat"])) for p in points]
    rail_idx = [i for i, p in enumerate(points) if set(p["modes"]) & RAIL_FAMILY]
    other_idx = [i for i, p in enumerate(points) if not (set(p["modes"]) & RAIL_FAMILY)]
    if rail_idx and other_idx:
        tree = STRtree([bng_pts[i] for i in other_idx])
        for i in rail_idx:
            buf = bng_pts[i].buffer(radius_m)
            for hit in tree.query(buf):
                j = other_idx[hit]
                if bng_pts[i].distance(bng_pts[j]) <= radius_m:
                    union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    merged = []
    for members in groups.values():
        pts = [points[k] for k in members]
        # Prefer a rail-family point's name (usually the "proper" station name).
        named = next((p for p in pts if set(p["modes"]) & RAIL_FAMILY), pts[0])
        lon = sum(p["lon"] for p in pts) / len(pts)
        lat = sum(p["lat"] for p in pts) / len(pts)
        modes = sorted({m for p in pts for m in p["modes"]}, key=MODE_ORDER.index)
        lines = sorted({ln for p in pts for ln in p["lines"]})
        naptan = sorted({a for p in pts for a in p["naptan"]})
        merged.append({"name": named["name"], "modes": modes, "lines": lines, "naptan": naptan, "lon": lon, "lat": lat})
    return merged


def build_stations() -> dict:
    england = england_boundary_wgs()
    rows = naptan_rows_national()
    candidates = build_candidates(rows, england)

    tfl_points, leftover = group_via_tfl(candidates)
    name_points = group_by_name_proximity(leftover)
    all_points = tfl_points + name_points
    log(f"stations: {len(tfl_points)} TfL-resolved + {len(name_points)} name/proximity-grouped "
        f"= {len(all_points)} before interchange merge")
    final = merge_rail_metro_interchanges(all_points)
    final.sort(key=lambda p: p["name"])

    feats = [
        feature(Point(round(p["lon"], 5), round(p["lat"], 5)),
                {"name": p["name"], "modes": p["modes"], "lines": p["lines"], "naptan": p["naptan"]})
        for p in final
    ]
    sources = [NAPTAN_SOURCE, TFL_SOURCE]
    notes = [
        "England only (clipped to the ONS England country boundary). NaPTAN StopType RLY = "
        "heavy/main-line rail; StopType MET is restricted to England's Underground/DLR/tram/metro "
        "systems (London Underground, DLR, Tyne and Wear Metro, Manchester Metrolink, Sheffield "
        "Supertram, Nottingham Express Transit, West Midlands Metro, Blackpool Tramway, Croydon "
        "Tramlink); heritage/tourist railways and Scotland's Glasgow Subway/Edinburgh Trams, which "
        "NaPTAN also files under MET, are excluded.",
        "modes: national_rail, overground, elizabeth_line, underground, dlr, tram, metro.",
        f"Within Greater London and the Elizabeth line's full extent (bbox lon {TFL_BBOX[0]}..{TFL_BBOX[2]}, "
        f"lat {TFL_BBOX[1]}..{TFL_BBOX[3]}) stations are grouped and enriched with modes/lines via the TfL "
        "Unified API, as in the Hackney build. Elsewhere, NaPTAN rows are merged by name + proximity "
        "(<=80 m), and a rail<->metro/tram/underground/dlr point pair within 200 m is treated as one "
        "interchange regardless of name (this is what merges e.g. Newcastle's mainline and Tyne and Wear "
        "Metro stations into one point); lines is only populated where TfL data was available.",
    ]
    size = write_geojson_to(OUT_PATH, feats, sources, notes, max_bytes=MAX_BYTES)
    log(f"wrote {OUT_PATH.relative_to(ROOT)}: {len(feats)} stations, {size/1024:.0f} KB")
    mode_counts = Counter(m for p in final for m in p["modes"])
    log(f"stations by mode: {dict(sorted(mode_counts.items()))}")
    return {"count": len(feats), "bytes": size, "by_mode": dict(mode_counts)}


if __name__ == "__main__":  # pragma: no cover
    print(build_stations())
