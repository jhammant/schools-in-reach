"""Build Hackney map layers for the static site.

Usage (from the project root):
    uv run --with shapely --with pyproj --with pandas --with requests --with pillow \
        python pipeline/geo/build.py [--only boundary,lsoa,pois,transport,env,police,verify] [--refresh]

Outputs go to site/data/hackney/layers/; raw downloads are cached in pipeline/.cache/geo/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

STEPS = ["boundary", "lsoa", "pois", "transport", "env", "police", "verify"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help=f"comma-separated subset of: {','.join(STEPS)}")
    ap.add_argument("--refresh", action="store_true", help="ignore cached downloads")
    args = ap.parse_args()
    common.REFRESH = args.refresh
    steps = args.only.split(",") if args.only else STEPS
    unknown = set(steps) - set(STEPS)
    if unknown:
        ap.error(f"unknown steps: {sorted(unknown)}")
    common.CACHE.mkdir(parents=True, exist_ok=True)
    common.OUT.mkdir(parents=True, exist_ok=True)

    if "boundary" in steps:
        import areas
        areas.build_boundary()
    if "lsoa" in steps:
        import areas
        areas.build_lsoa()
    if "pois" in steps:
        import pois
        pois.build_pois()
    if "transport" in steps:
        import transport
        transport.build_transport()
        transport.build_bus_stops()
    if "env" in steps:
        import env_layers
        env_layers.build_env_layers()
    if "police" in steps:
        import police
        police.check_police_api()
    if "verify" in steps:
        import verify
        return verify.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
