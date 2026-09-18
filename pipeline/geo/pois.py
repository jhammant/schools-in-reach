"""OpenStreetMap points of interest (Overpass API) within Hackney + 300 m."""

from __future__ import annotations

import json
import re

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

from common import (
    OSM_ATTR,
    PIPELINE_UA,
    boundary_shape,
    buffered_wgs,
    feature,
    fetch,
    haversine_m,
    log,
    write_geojson,
)

OVERPASS = "https://overpass-api.de/api/interpreter"
BUFFER_M = 300

# Access values that mean "not open to the public" for recreational places.
RESTRICTED_ACCESS = {"private", "no", "customers", "residents", "permit", "members", "students", "delivery"}
# Places inside school/college/nursery grounds are dropped for these categories unless access is public.
SCHOOL_GROUND_CATEGORIES = {"playground", "swimming_pool", "library", "park"}
PUBLIC_ACCESS = {"yes", "public", "permissive", "designated"}

# leisure=sports_centre is also used for gyms/studios; these are not "leisure centres".
GYM_SPORTS = {
    "fitness", "yoga", "pilates", "weightlifting", "crossfit", "boxing", "kickboxing", "martial_arts",
    "dance", "cycling", "bicycling", "billiards", "snooker", "american pool", "karting", "axe_throwing",
    "escape_game", "trampoline", "bowling", "10pin", "shooting", "laser_tag",
}
GYM_NAME = re.compile(
    r"(gym|fitness|pilates|yoga|health club|crossfit|boxing|bootcamp|rebel|f45|virgin active|"
    r"third space|barry'?s|kobox|fit4less|\bspin\b|\bcycle\b|\bride\b|\bpt\b)",
    re.I,
)
PADDLING = re.compile(r"paddling|splash", re.I)

CATEGORIES = [
    "park", "playground", "library", "leisure_centre", "swimming_pool", "gp", "pharmacy", "dentist",
    "supermarket", "museum", "cinema", "theatre", "community_centre", "place_of_worship",
]


def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    b = f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}"
    return f"""[out:json][timeout:240];
(
  nwr["leisure"~"^(park|playground|sports_centre|swimming_pool)$"]({b});
  nwr["amenity"~"^(library|doctors|pharmacy|dentist|cinema|theatre|community_centre|place_of_worship)$"]({b});
  nwr["healthcare"~"^(doctor|dentist|pharmacy)$"]({b});
  nwr["shop"="supermarket"]({b});
  nwr["tourism"="museum"]({b});
  nwr["amenity"~"^(school|college|kindergarten)$"]({b});
);
out geom qt;"""


def element_geometry(el: dict):
    """Shapely geometry for an Overpass `out geom` element (areas as polygons where possible)."""
    if el["type"] == "node":
        return Point(el["lon"], el["lat"])
    if el["type"] == "way":
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry") or [] if p]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        return LineString(pts) if len(pts) >= 2 else (Point(pts[0]) if pts else None)
    # relation: polygonize member ways (outer minus inner)
    outers, inners = [], []
    for m in el.get("members", []):
        g = [(p["lon"], p["lat"]) for p in m.get("geometry") or [] if p]
        if m.get("type") != "way" or len(g) < 2:
            continue
        (inners if m.get("role") == "inner" else outers).append(LineString(g))
    polys = list(polygonize(unary_union(outers))) if outers else []
    if not polys:
        if el.get("bounds"):
            b = el["bounds"]
            return Point((b["minlon"] + b["maxlon"]) / 2, (b["minlat"] + b["maxlat"]) / 2)
        return None
    area = unary_union(polys)
    holes = list(polygonize(unary_union(inners))) if inners else []
    if holes:
        area = area.difference(unary_union(holes))
    return area


def anchor_point(geom):
    """Centroid for areas; point-on-surface when the centroid falls outside the shape."""
    if geom.geom_type == "Point":
        return geom
    c = geom.centroid
    if geom.geom_type in ("Polygon", "MultiPolygon") and not geom.contains(c):
        return geom.representative_point()
    return c


def split_sports(tags: dict) -> set[str]:
    return {s.strip().lower() for s in re.split(r"[;,]", tags.get("sport", "")) if s.strip()}


def classify(tags: dict) -> list[str]:
    cats = []
    leisure, amenity, healthcare = tags.get("leisure"), tags.get("amenity"), tags.get("healthcare")
    name = tags.get("name")
    if leisure == "park" and name:
        cats.append("park")
    if leisure == "playground":
        cats.append("playground")
    if amenity == "library" and name:
        cats.append("library")
    if leisure == "sports_centre" and name:
        sports = split_sports(tags)
        gym_like = (sports and sports <= GYM_SPORTS) or (not sports and GYM_NAME.search(name))
        if not gym_like:
            cats.append("leisure_centre")
        if "swimming" in sports:
            cats.append("swimming_pool")
    if leisure == "swimming_pool" and (name or tags.get("access") in PUBLIC_ACCESS) and not PADDLING.search(name or ""):
        cats.append("swimming_pool")
    if name and (amenity == "doctors" or (healthcare == "doctor" and not amenity)):
        cats.append("gp")
    if name and (amenity == "pharmacy" or (healthcare == "pharmacy" and not amenity)):
        cats.append("pharmacy")
    if name and (amenity == "dentist" or (healthcare == "dentist" and not amenity)):
        cats.append("dentist")
    if name and tags.get("shop") == "supermarket":
        cats.append("supermarket")
    if name and tags.get("tourism") == "museum":
        cats.append("museum")
    if name and amenity == "cinema":
        cats.append("cinema")
    if name and amenity == "theatre":
        cats.append("theatre")
    if name and amenity == "community_centre":
        cats.append("community_centre")
    if name and amenity == "place_of_worship":
        cats.append("place_of_worship")
    return list(dict.fromkeys(cats))


def _norm(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


TYPE_PREF_AREA = {"relation": 0, "way": 1, "node": 2}
TYPE_PREF_POINT = {"node": 0, "way": 1, "relation": 2}


def dedupe(items: list[dict]) -> list[dict]:
    """Drop the same place mapped twice (e.g. a node inside its building outline)."""
    kept: list[dict] = []
    by_cat: dict[str, list[dict]] = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)
    for cat, group in by_cat.items():
        pref = TYPE_PREF_AREA if cat in ("park", "leisure_centre", "swimming_pool") else TYPE_PREF_POINT
        group.sort(key=lambda i: (pref[i["osm_type"]], -i["area"]))
        radius = 400 if cat == "park" else 120
        chosen: list[dict] = []
        for it in group:
            dup = False
            for c in chosen:
                d = haversine_m(it["lon"], it["lat"], c["lon"], c["lat"])
                if it["name"] and _norm(it["name"]) == _norm(c["name"]) and d <= radius:
                    dup = True
                elif not it["name"] and not c["name"] and d <= 25:
                    dup = True
                elif cat == "swimming_pool" and d <= 150 and (not it["name"] or not c["name"]):
                    dup = True  # unnamed pool inside/next to a named swimming venue
                if dup:
                    break
            if not dup:
                chosen.append(it)
        kept.extend(chosen)
    return kept


def _fetch_pois_core(boundary, cache_key: str) -> tuple[list[dict], str | None]:
    """Overpass query + classify + dedupe for one area's POIs. Returns (feature list, osm_base).
    Shared by build_pois() (Hackney) and national_pois.py (the 33 London LAs)."""
    area = buffered_wgs(boundary, BUFFER_M)
    minx, miny, maxx, maxy = area.bounds
    query = overpass_query((miny, minx, maxy, maxx))
    raw = fetch(
        OVERPASS,
        f"overpass_pois_{cache_key}.json",
        data={"data": query},
        headers={"User-Agent": PIPELINE_UA, "Accept": "application/json"},
        timeout=300,
    )
    data = json.loads(raw)
    osm_base = data.get("osm3s", {}).get("timestamp_osm_base")
    elements = data["elements"]
    log(f"overpass: {len(elements)} elements (OSM base {osm_base})")

    school_polys = []
    candidates = []
    for el in elements:
        tags = el.get("tags", {})
        if tags.get("amenity") in ("school", "college", "kindergarten"):
            g = element_geometry(el)
            if g is not None and g.geom_type in ("Polygon", "MultiPolygon"):
                school_polys.append(g)
            continue
        cats = classify(tags)
        if not cats:
            continue
        geom = element_geometry(el)
        if geom is None or geom.is_empty:
            continue
        pt = anchor_point(geom)
        candidates.append((el, tags, cats, pt, geom))

    # A leisure centre whose outline contains a mapped pool (often access=customers) has a pool.
    centre_idx = [i for i, c in enumerate(candidates)
                  if "leisure_centre" in c[2] and c[4].geom_type in ("Polygon", "MultiPolygon")]
    for el in elements:
        tags = el.get("tags", {})
        if tags.get("leisure") != "swimming_pool" or tags.get("access") in ("private", "no"):
            continue
        g = element_geometry(el)
        if g is None or PADDLING.search(tags.get("name") or ""):
            continue
        p = anchor_point(g)
        for i in centre_idx:
            if "swimming_pool" not in candidates[i][2] and candidates[i][4].contains(p):
                candidates[i][2].append("swimming_pool")

    school_tree = STRtree(school_polys) if school_polys else None
    items = []
    dropped = {"outside_area": 0, "restricted_access": 0, "school_grounds": 0}
    for el, tags, cats, pt, geom in candidates:
        if not area.contains(pt):
            dropped["outside_area"] += 1
            continue
        access = (tags.get("access") or "").lower()
        in_school = False
        if school_tree is not None:
            in_school = any(school_polys[i].contains(pt) for i in school_tree.query(pt))
        for cat in cats:
            if cat in {"park", "playground", "swimming_pool", "library", "leisure_centre"} and access in RESTRICTED_ACCESS:
                dropped["restricted_access"] += 1
                continue
            if cat in SCHOOL_GROUND_CATEGORIES and in_school and access not in PUBLIC_ACCESS:
                dropped["school_grounds"] += 1
                continue
            items.append({
                "category": cat,
                "name": tags.get("name"),
                "osm_type": el["type"],
                "osm": f"{el['type']}/{el['id']}",
                "lon": pt.x,
                "lat": pt.y,
                "area": geom.area if geom.geom_type in ("Polygon", "MultiPolygon") else 0.0,
            })
    before = len(items)
    items = dedupe(items)
    log(f"pois: {before} candidates -> {len(items)} after de-duplication; dropped {dropped}")

    items.sort(key=lambda i: (CATEGORIES.index(i["category"]), i["name"] or "~", i["osm"]))
    feats = [feature(Point(i["lon"], i["lat"]), {"category": i["category"], "name": i["name"], "osm": i["osm"]})
             for i in items]
    return feats, osm_base


POI_SOURCE_TITLE = "OpenStreetMap via Overpass API (data as of {osm_base})"
POI_NOTES_TAIL = [
    "Tag mapping: park=leisure=park; playground=leisure=playground; library=amenity=library; "
    "leisure_centre=leisure=sports_centre excluding gyms/studios; swimming_pool=public leisure=swimming_pool (not paddling pools) or a leisure centre with sport=swimming or a mapped pool inside it; "
    "gp=amenity=doctors|healthcare=doctor; pharmacy=amenity=pharmacy; dentist=amenity=dentist; supermarket=shop=supermarket; "
    "museum=tourism=museum; cinema/theatre/community_centre/place_of_worship=amenity=*.",
    "All categories except playground require a name. Recreational places with restricted access, and playgrounds/pools/libraries/parks "
    "inside school, college or nursery grounds, are excluded. Schools themselves are not included (see DfE data).",
    "A sports centre with a pool appears as both leisure_centre and swimming_pool.",
]


def build_pois() -> dict:
    boundary = boundary_shape()
    feats, osm_base = _fetch_pois_core(boundary, "204")
    sources = [{
        "title": POI_SOURCE_TITLE.format(osm_base=osm_base),
        "url": "https://www.openstreetmap.org/copyright",
        "licence": "Open Database Licence (ODbL) 1.0",
        "attribution": OSM_ATTR,
    }]
    notes = [
        f"Hackney boundary buffered by {BUFFER_M} m. Areas are reduced to their centroid (point-on-surface if the centroid is outside the shape).",
        *POI_NOTES_TAIL,
    ]
    write_geojson("pois.geojson", feats, sources, notes)
    return {"count": len(feats), "osm_base": osm_base}
