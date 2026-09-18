"""site/data/la/<la_code>/lsoa.geojson for every English DfE LA: LSOA 2021 polygons (BGC
generalised) joined to IoD2025 and Census 2021, with exactly the same properties as
site/data/hackney/layers/lsoa.geojson. Same simplification approach (shapely.coverage_simplify,
so neighbouring LSOAs within an LA keep identical shared edges); big county councils are
simplified further if needed to stay under the ~2.5 MB budget, and that's recorded in the
output's `metadata.notes`.
"""

from __future__ import annotations

import csv
import io
import json

import shapely

import areas
import la_mapping
from common import OGL, ROOT, feature, fetch, log, ons_boundary_attr, round_geom, to_bng, to_wgs
from national_common import write_geojson_to

OUT_ROOT = ROOT / "site" / "data" / "la"
MAX_BYTES = 2_500_000
# Tolerances (metres, BNG) tried in order until the file fits the budget. 4.0 matches Hackney
# exactly (same as areas.SIMPLIFY_M) so la=204 reproduces byte-for-byte-equivalent geometry.
SIMPLIFY_LADDER = [areas.SIMPLIFY_M, 8.0, 16.0, 32.0, 64.0, 96.0, 128.0]

NOMIS_PAGE = 25_000


def national_census() -> dict[str, dict]:
    """All 8 Nomis Census 2021 topic tables for every English LSOA in one bulk (paginated)
    request per table, instead of one request per LA/LAD."""
    t: dict[str, dict[str, dict[str, float]]] = {}
    for table, (ds, dim) in areas.NOMIS_TABLES.items():
        out: dict[str, dict[str, float]] = {}
        offset = 0
        while True:
            raw = fetch(
                f"{areas.NOMIS}/{ds}.data.csv",
                f"nomis_{table}_national_o{offset}.csv",
                params={"geography": "TYPE151", "measures": "20100",
                        "select": f"geography_code,{dim},obs_value",
                        "recordoffset": offset},
            ).decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(raw)))
            if not rows:
                break
            for row in rows:
                code = row["GEOGRAPHY_CODE"]
                if code.startswith("E"):
                    out.setdefault(code, {})[row[dim.upper()]] = float(row["OBS_VALUE"])
            if len(rows) < NOMIS_PAGE:
                break
            offset += NOMIS_PAGE
        t[table] = out
        log(f"  nomis {table}: {len(out)} English LSOAs")
    codes = set(t["TS001"])
    return {code: areas.census_record(code, t) for code in codes}


def national_iod(all_codes: set[str]) -> dict[str, dict]:
    return areas.iod2025(all_codes)


def _try_write(la_code: str, ordered_codes: list[str], geoms: dict, iod: dict, cen: dict,
                lsoa_names: dict) -> tuple[list[dict], float]:
    """Build features at each simplification tolerance until the serialised size fits
    MAX_BYTES (or we run out of ladder rungs, in which case we keep the coarsest)."""
    bng = [to_bng(geoms[c][1]) for c in ordered_codes]
    last_feats: list[dict] = []
    last_tol = SIMPLIFY_LADDER[0]
    for tol in SIMPLIFY_LADDER:
        simplified = shapely.coverage_simplify(bng, tol)
        feats = []
        for code, g in zip(ordered_codes, simplified):
            props = {"lsoa21cd": code, "lsoa21nm": geoms[code][0] or lsoa_names.get(code)}
            props.update(iod[code])
            props.update(cen[code])
            feats.append(feature(round_geom(to_wgs(g)), props))
        size = len(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
        last_feats, last_tol = feats, tol
        if size <= MAX_BYTES:
            return feats, tol
        log(f"  {la_code}: {len(feats)} LSOAs at {tol} m simplify -> {size/1e6:.2f} MB, over budget; trying coarser")
    return last_feats, last_tol


def build_all(la_codes: list[str] | None = None) -> dict:
    mapping = la_mapping.build_mapping()
    la_lsoas, lsoa_names = la_mapping.la_lsoas(mapping)
    target_las = la_codes or sorted(la_lsoas)

    log("national_lsoa: fetching national census + IoD2025 (once for all LAs)")
    cen = national_census()
    all_codes = set()
    for la in target_las:
        all_codes.update(la_lsoas[la])
    iod = national_iod(all_codes)

    missing_iod = sorted(all_codes - set(iod))
    missing_cen = sorted(all_codes - set(cen))
    if missing_iod or missing_cen:
        raise RuntimeError(f"missing IoD ({len(missing_iod)}) or census ({len(missing_cen)}) for LSOAs: "
                            f"{(missing_iod or missing_cen)[:10]}")

    sources = [
        {
            "title": f"{areas.LSOA_SERVICE.replace('_', ' ')} (ONS Open Geography Portal)",
            "url": f"{areas.ARCGIS}/{areas.LSOA_SERVICE}/FeatureServer",
            "licence": OGL,
            "attribution": ons_boundary_attr(2021),
        },
        {
            "title": f"{areas.latest_lsoa_lookup()} (ONS LSOA 2021 to ward/LAD lookup, used for LA membership)",
            "url": f"{areas.ARCGIS}/{areas.latest_lsoa_lookup()}/FeatureServer",
            "licence": OGL,
            "attribution": "Source: Office for National Statistics licensed under the Open Government Licence v.3.0.",
        },
        {
            "title": "English Indices of Deprivation 2025, File 7 (MHCLG, LSOA 2021 geography)",
            "url": areas.IOD2025_PAGE,
            "licence": OGL,
            "attribution": "Ministry of Housing, Communities and Local Government, English Indices of Deprivation 2025. Contains public sector information licensed under the Open Government Licence v3.0.",
        },
        {
            "title": "Census 2021 topic summaries TS001, TS007B, TS054, TS067, TS011, TS021, TS045, TS006 (ONS via Nomis)",
            "url": "https://www.nomisweb.co.uk/sources/census_2021",
            "licence": OGL,
            "attribution": "Source: Office for National Statistics, Census 2021, licensed under the Open Government Licence v.3.0.",
        },
    ]
    base_notes = [
        "Deciles/ranks: 1 = most deprived (ranks out of 33,755 English LSOAs, IoD2025 File 7).",
        "Census percentages use each table's own total as denominator (ONS cell-key perturbation means totals differ slightly between tables).",
        "pct_age_0_15 uses TS007B broad age bands (0-4, 5-9, 10-15) because TS007A 5-year bands split 15-19.",
        "pct_owned includes shared ownership; 'lives rent free' is in no tenure group.",
        "pct_level4_plus denominator is usual residents aged 16+.",
    ]

    results = {}
    for la_code in target_las:
        codes = la_lsoas[la_code]
        geoms = areas.lsoa_geometries(codes, cache_key=la_code)
        missing_geom = sorted(set(codes) - set(geoms))
        if missing_geom:
            raise RuntimeError(f"LA {la_code}: LSOAs without geometry: {missing_geom}")
        ordered = sorted(codes)
        feats, tol = _try_write(la_code, ordered, geoms, iod, cen, lsoa_names)
        notes = list(base_notes)
        if tol != areas.SIMPLIFY_M:
            notes.append(f"Simplified more than the {areas.SIMPLIFY_M} m default ({tol} m) to stay under the "
                          f"{MAX_BYTES/1e6:.1f} MB budget ({len(codes)} LSOAs).")
        out_path = OUT_ROOT / la_code / "lsoa.geojson"
        size = write_geojson_to(out_path, feats, sources, notes)
        log(f"la {la_code}: wrote {out_path.relative_to(ROOT)}: {len(feats)} LSOAs, {size/1024:.0f} KB"
            + (f" (simplify {tol} m)" if tol != areas.SIMPLIFY_M else ""))
        results[la_code] = {"count": len(feats), "bytes": size, "simplify_m": tol}
    return results


if __name__ == "__main__":  # pragma: no cover
    import sys
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    r = build_all(only)
    total_lsoas = sum(v["count"] for v in r.values())
    total_bytes = sum(v["bytes"] for v in r.values())
    print(f"{len(r)} LAs, {total_lsoas} LSOAs, {total_bytes/1e6:.1f} MB total")
