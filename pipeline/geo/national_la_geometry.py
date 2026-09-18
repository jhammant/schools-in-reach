"""site/data/england/la_geometry.json and la_boundaries.geojson: one polygon per DfE LA
(bbox/centroid/neighbours/lad_codes), built from the ONS Counties and Unitary Authorities
(CTYUA) boundaries -- which are the upper-tier local authorities and, in England, line up
1:1 with DfE LA codes (a county council's CTYUA polygon is already the union of its district
LADs, so we don't need to dissolve LADs ourselves). Matched to DfE LA codes by normalised
name; every match is exact (0 gaps) as of 2026-09-17, but any future mismatch is reported.
"""

from __future__ import annotations

import json
import re

import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

import la_mapping
from common import OGL, ROOT, feature, log, now_iso, to_bng, to_wgs, write_json
from national_common import paginated_features, write_geojson_to

CTYUA_SERVICE = "Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BGC"
GEOMETRY_OUT = ROOT / "site" / "data" / "england" / "la_geometry.json"
BOUNDARIES_OUT = ROOT / "site" / "data" / "england" / "la_boundaries.geojson"
BOUNDARIES_MAX_BYTES = 5_000_000
SIMPLIFY_LADDER = [5.0, 10.0, 20.0, 40.0, 80.0, 150.0]
TOUCH_BUFFER_M = 50.0  # generalised boundaries can leave tiny gaps between true neighbours

CTYUA_SOURCE = {
    "title": f"{CTYUA_SERVICE.replace('_', ' ')} (ONS Open Geography Portal)",
    "url": f"https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/{CTYUA_SERVICE}/FeatureServer",
    "licence": OGL,
    "attribution": "Source: Office for National Statistics licensed under the Open Government Licence v.3.0. "
                    "Contains OS data © Crown copyright and database right 2025",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().replace("&", "and"))


def fetch_ctyua() -> list[dict]:
    feats = paginated_features(CTYUA_SERVICE, "CTYUA25CD LIKE 'E%'", "CTYUA25CD,CTYUA25NM", "ctyua_england",
                                geometry=True)
    log(f"ctyua: {len(feats)} English county/unitary authority polygons")
    return feats


def match_to_la(ctyua_feats: list[dict], la_names: dict[str, str]) -> tuple[dict[str, dict], list[dict]]:
    by_norm = {_norm(v): k for k, v in la_names.items()}
    matched: dict[str, dict] = {}
    gaps: list[dict] = []
    for f in ctyua_feats:
        p = f["properties"]
        la_code = by_norm.get(_norm(p["CTYUA25NM"]))
        if la_code:
            matched[la_code] = f
        else:
            gaps.append({"ctyua_code": p["CTYUA25CD"], "ctyua_name": p["CTYUA25NM"], "la_code": None})
    missing_la = sorted(set(la_names) - set(matched))
    for la_code in missing_la:
        gaps.append({"ctyua_code": None, "ctyua_name": None, "la_code": la_code, "la_name": la_names[la_code]})
    if gaps:
        log(f"la_geometry: {len(gaps)} CTYUA<->DfE LA name-match gap(s): {gaps}")
    else:
        log(f"la_geometry: all {len(matched)} CTYUA polygons matched to DfE LA codes by name")
    return matched, gaps


def build() -> dict:
    mapping = la_mapping.build_mapping()
    la_names, la_to_lads = mapping["la_names"], mapping["la_to_lads"]
    ctyua_feats = fetch_ctyua()
    matched, gaps = match_to_la(ctyua_feats, la_names)

    ordered = sorted(matched)
    bng_geoms = [to_bng(shape(matched[la]["geometry"])) for la in ordered]

    # Neighbours: touching (or nearly touching, to allow for generalisation gaps) polygons.
    buffered = [g.buffer(TOUCH_BUFFER_M) for g in bng_geoms]
    tree = STRtree(buffered)
    neighbours: dict[str, list[str]] = {la: [] for la in ordered}
    for i, la in enumerate(ordered):
        for j in tree.query(buffered[i]):
            j = int(j)
            if j != i and buffered[i].intersects(buffered[j]):
                neighbours[la].append(ordered[j])
    for la in neighbours:
        neighbours[la].sort()

    las = {}
    for i, la in enumerate(ordered):
        geom_wgs = shape(matched[la]["geometry"])
        w, s, e, n = geom_wgs.bounds
        centroid_bng = bng_geoms[i].centroid
        clon, clat = to_wgs(centroid_bng).coords[0]
        las[la] = {
            "name": la_names[la],
            "bbox": [round(w, 5), round(s, 5), round(e, 5), round(n, 5)],
            "centroid": [round(clat, 5), round(clon, 5)],
            "neighbours": neighbours[la],
            "lad_codes": la_to_lads.get(la, []),
        }

    doc = {
        "generated": now_iso(),
        "sources": [CTYUA_SOURCE],
        "las": las,
    }
    if gaps:
        doc["gaps"] = gaps
    size = write_json(GEOMETRY_OUT, doc)
    log(f"wrote {GEOMETRY_OUT.relative_to(ROOT)}: {len(las)} LAs, {size/1024:.0f} KB")

    # Boundaries: one coverage-simplified polygon per LA (shared edges stay identical),
    # laddered up in tolerance until the whole England file fits the budget.
    last_feats, last_tol = None, SIMPLIFY_LADDER[0]
    for tol in SIMPLIFY_LADDER:
        simplified = shapely.coverage_simplify(bng_geoms, tol)
        feats = [
            feature(to_wgs(g), {"la_code": la, "name": la_names[la]})
            for la, g in zip(ordered, simplified)
        ]
        # round_geom isn't used here: coverage_simplify + feature()'s own 5dp rounding is enough,
        # and re-running set_precision risks reintroducing tiny shared-edge mismatches.
        approx_size = len(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
        last_feats, last_tol = feats, tol
        if approx_size <= BOUNDARIES_MAX_BYTES:
            break
        log(f"  la_boundaries at {tol} m -> {approx_size/1e6:.2f} MB, over budget; trying coarser")

    b_size = write_geojson_to(BOUNDARIES_OUT, last_feats, [CTYUA_SOURCE],
                               [f"Coverage-simplified at {last_tol} m (BNG) from CTYUA BGC boundaries; "
                                "shared edges between neighbouring LAs stay identical."],
                               max_bytes=BOUNDARIES_MAX_BYTES)
    log(f"wrote {BOUNDARIES_OUT.relative_to(ROOT)}: {len(last_feats)} LAs, {b_size/1024:.0f} KB "
        f"(simplify {last_tol} m)")
    return {"la_geometry_bytes": size, "la_count": len(las), "boundaries_bytes": b_size,
            "boundaries_simplify_m": last_tol, "gaps": gaps}


if __name__ == "__main__":  # pragma: no cover
    print(build())
