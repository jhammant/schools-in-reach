"""Build England-wide map layers for the static site (site/data/la/<code>/ and
site/data/england/). This is separate from pipeline/geo/build.py (Hackney-only,
site/data/hackney/layers/), which it does not touch or depend on.

Usage (from the project root):
    uv run --with shapely --with pyproj --with pandas --with requests \\
        python pipeline/geo/build_national.py [--only mapping,lsoa,stations,la_geometry,pois,verify]

Steps:
  mapping     - la_mapping.py: DfE LA <-> ONS LAD/LSOA mapping (cached; everything else needs it)
  lsoa        - national_lsoa.py: site/data/la/<code>/lsoa.geojson for all 153 English DfE LAs
  stations    - national_stations.py: site/data/england/stations.geojson
  la_geometry - national_la_geometry.py: site/data/england/la_geometry.json + la_boundaries.geojson
  pois        - national_pois.py: site/data/la/<code>/pois.geojson for the 33 London LAs
  verify      - national_verify.py: sanity checks; exits non-zero on failure

Downloads are cached in pipeline/.cache/geo/ and pipeline/.cache/shared/ (GIAS). Re-running
without --refresh reuses everything already fetched (national census/IoD/NaPTAN downloads
are the slow part; per-LA/per-borough geometry and Overpass queries are cached per LA/LAD).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

STEPS = ["mapping", "lsoa", "stations", "la_geometry", "pois", "verify"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help=f"comma-separated subset of: {','.join(STEPS)}")
    ap.add_argument("--refresh", action="store_true", help="ignore cached downloads")
    ap.add_argument("--las", help="comma-separated DfE LA codes to restrict lsoa/pois steps to (default: all)")
    args = ap.parse_args()
    common.REFRESH = args.refresh
    steps = args.only.split(",") if args.only else STEPS
    unknown = set(steps) - set(STEPS)
    if unknown:
        ap.error(f"unknown steps: {sorted(unknown)}")
    common.CACHE.mkdir(parents=True, exist_ok=True)
    las = args.las.split(",") if args.las else None

    if "mapping" in steps:
        import la_mapping
        la_mapping.build_mapping(refresh=args.refresh)
    if "lsoa" in steps:
        import national_lsoa
        national_lsoa.build_all(las)
    if "stations" in steps:
        import national_stations
        national_stations.build_stations()
    if "la_geometry" in steps:
        import national_la_geometry
        national_la_geometry.build()
    if "pois" in steps:
        import national_pois
        national_pois.build_all(las)
    if "verify" in steps:
        import national_verify
        return national_verify.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
