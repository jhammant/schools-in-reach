"""Build Ofsted, Parent View, childcare and pupil-characteristics data for every
English local authority.

Usage (from the project root):
    uv run --with pandas --with openpyxl --with odfpy python pipeline/ofsted/build.py
        [--refresh]          re-download source pages/files instead of using pipeline/.cache/ofsted
        [--only NAME ...]    ofsted | parentview | nurseries | characteristics
        [--la CODE ...]      DfE LA code(s) to write (default: every English LA, ~153)
        [--verify]           spot-check the --la 204 (Hackney) output against reports.ofsted.gov.uk (network)

Each national source file is fetched and parsed once, then split by LA; only the
LAs requested (all, by default) are written. Writes
site/data/la/<la_code>/{ofsted,parentview,nurseries,characteristics}.json.
nurseries.json additionally needs pandas (NSPL postcode lookup): run with
`uv run --with pandas`.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import characteristics  # noqa: E402
import nurseries  # noqa: E402
import parentview  # noqa: E402
import schools  # noqa: E402
from util import la_registry, now_iso, write_la_json  # noqa: E402

BUILDERS = {
    "ofsted": ("ofsted.json", schools.build_all),
    "parentview": ("parentview.json", parentview.build_all),
    "nurseries": ("nurseries.json", nurseries.build_all),
    "characteristics": ("characteristics.json", characteristics.build_all),
}
MAX_BYTES = 1_000_000


def metrics(name: str, payload: dict) -> Counter:
    if name == "ofsted":
        s = payload["schools"]
        return Counter(schools=len(s), with_ofsted_data=sum(1 for v in s.values() if v.get("inspectorate") == "Ofsted"),
                       with_isi_inspectorate=sum(1 for v in s.values() if v.get("inspectorate") == "ISI"))
    if name == "parentview":
        s = payload["schools"]
        return Counter(schools=len(s), current_release=sum(1 for v in s.values() if "current" in v))
    if name == "nurseries":
        c = payload["counts"]
        return Counter(providers=c["providers"], geocoded=c["geocoded"],
                       without_coordinates=c["providers"] - c["geocoded"])
    if name == "characteristics":
        return Counter(schools=len(payload["schools"]))
    return Counter()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only", nargs="+", choices=sorted(BUILDERS))
    ap.add_argument("--la", nargs="+", help="DfE LA code(s) to write (default: every English LA)")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    registry = la_registry()  # {la_code: la_name}, ~153 English LAs
    if args.la:
        la_codes = list(dict.fromkeys(args.la))
        unknown = [c for c in la_codes if c not in registry]
        if unknown:
            print(f"unknown LA code(s): {unknown} (see util.la_registry() for valid codes)", file=sys.stderr)
            return 2
    else:
        la_codes = list(registry)

    failed = False
    generated = now_iso()
    grand_bytes = 0
    for name in args.only or BUILDERS:
        filename, builder = BUILDERS[name]
        by_la = builder(refresh=args.refresh)  # {la_code: data}, every English LA computed once

        written = 0
        total_bytes = 0
        total = Counter()
        for la_code in la_codes:
            data = by_la.get(la_code)
            if data is None:
                continue  # this LA has no rows for this source (e.g. too few Parent View submissions anywhere)
            payload = {"generated": generated, "la_code": la_code, "la_name": registry[la_code], **data}
            path = write_la_json(la_code, filename, payload)
            size = path.stat().st_size
            total_bytes += size
            written += 1
            total += metrics(name, payload)
            if size > MAX_BYTES:
                print(f"  WARNING: la/{la_code}/{filename} exceeds {MAX_BYTES} bytes ({size} bytes)")
                failed = True
        grand_bytes += total_bytes
        stats = ", ".join(f"{k} {v}" for k, v in total.items())
        print(f"{filename}: {written}/{len(la_codes)} LAs written, {total_bytes / 1024:.1f} KB total - {stats}")

    print(f"\n{len(la_codes)} LAs written; total output size {grand_bytes / 1024:.1f} KB "
         f"({grand_bytes / 1024 / 1024:.1f} MB)")

    if args.verify:
        import verify  # noqa: E402

        failed = verify.run("204") or failed
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
