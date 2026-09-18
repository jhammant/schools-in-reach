"""site/data/la/<la_code>/pois.geojson for the 33 London DfE LAs (201-213 inner, 301-320
outer): same categories/properties/filters as Hackney's pois.geojson (pois.py), one Overpass
query per borough with a polite delay between them.
"""

from __future__ import annotations

import time

import areas
import la_mapping
from common import OSM_ATTR, ROOT, log
from national_common import write_geojson_to
from pois import BUFFER_M, POI_NOTES_TAIL, POI_SOURCE_TITLE, _fetch_pois_core

OUT_ROOT = ROOT / "site" / "data" / "la"
LONDON_LA_CODES = [str(c) for c in list(range(201, 214)) + list(range(301, 321))]
DELAY_S = 5.0


def build_all(la_codes: list[str] | None = None) -> dict:
    mapping = la_mapping.build_mapping()
    la_to_lads, la_names = mapping["la_to_lads"], mapping["la_names"]
    targets = la_codes or LONDON_LA_CODES
    results = {}
    for i, la_code in enumerate(targets):
        lads = la_to_lads.get(la_code)
        if not lads or len(lads) != 1:
            log(f"pois: skipping LA {la_code} ({la_names.get(la_code)}): expected exactly 1 LAD, got {lads}")
            continue
        lad_code = lads[0]
        lad = areas.lad_boundary_bng(lad_code)
        boundary = areas.to_wgs(lad["geom_bng"])
        log(f"pois: {la_code} {la_names.get(la_code)} (LAD {lad_code})")
        feats, osm_base = _fetch_pois_core(boundary, la_code)
        sources = [{
            "title": POI_SOURCE_TITLE.format(osm_base=osm_base),
            "url": "https://www.openstreetmap.org/copyright",
            "licence": "Open Database Licence (ODbL) 1.0",
            "attribution": OSM_ATTR,
        }]
        notes = [
            f"{la_names.get(la_code, la_code)} boundary (LAD {lad_code}) buffered by {BUFFER_M} m. "
            "Areas are reduced to their centroid (point-on-surface if the centroid is outside the shape).",
            *POI_NOTES_TAIL,
        ]
        out_path = OUT_ROOT / la_code / "pois.geojson"
        size = write_geojson_to(out_path, feats, sources, notes)
        log(f"la {la_code}: wrote {out_path.relative_to(ROOT)}: {len(feats)} POIs, {size/1024:.0f} KB")
        results[la_code] = {"count": len(feats), "bytes": size, "osm_base": osm_base}
        if i < len(targets) - 1:
            time.sleep(DELAY_S)
    return results


if __name__ == "__main__":  # pragma: no cover
    import sys
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    r = build_all(only)
    total = sum(v["count"] for v in r.values())
    print(f"{len(r)} London LAs, {total} POIs total")
