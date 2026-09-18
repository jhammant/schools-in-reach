"""Diff the LA-204 build against reference/hackney (values must match apart from `generated`).

Usage:
    uv run python pipeline/dfe/compare_reference.py

Compares schools.json, league_tables.json, the four reference per-school files,
and the benchmark sections (reference `hackney` vs england/benchmarks.json
`la.204`). Prints differences and exits non-zero if any are found.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "reference" / "hackney"
BUILT = ROOT / "out" / "site" / "data"

IGNORE_KEYS = {"generated"}
MAX_DIFFS = 40

diffs: list[str] = []


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in IGNORE_KEYS}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def walk(path: str, a, b) -> None:
    if len(diffs) >= MAX_DIFFS:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key in IGNORE_KEYS:
                continue
            if key not in a:
                diffs.append(f"{path}.{key}: only in built ({b[key]!r:.80})")
            elif key not in b:
                diffs.append(f"{path}.{key}: only in reference ({a[key]!r:.80})")
            else:
                walk(f"{path}.{key}", a[key], b[key])
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: list length ref={len(a)} built={len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            walk(f"{path}[{i}]", x, y)
    elif a != b:
        diffs.append(f"{path}: ref={a!r:.80} built={b!r:.80}")


def compare_file(ref_path: Path, built_path: Path, label: str) -> None:
    if not built_path.exists():
        diffs.append(f"{label}: built file missing: {built_path}")
        return
    walk(label, strip(json.loads(ref_path.read_text())), strip(json.loads(built_path.read_text())))


def la_view(node, la_code: str):
    """Reshape built benchmarks (la: {<code>: ...}) to the reference's hackney view."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "la" and isinstance(v, dict):
                if la_code in v:
                    out["hackney"] = la_view(v[la_code], la_code)
            else:
                out[k] = la_view(v, la_code)
        return out
    if isinstance(node, list):
        return [la_view(v, la_code) for v in node]
    return node


def main() -> int:
    compare_file(REF / "schools.json", BUILT / "la" / "204" / "schools.json", "schools.json")
    compare_file(REF / "league_tables.json", BUILT / "la" / "204" / "league_tables.json", "league_tables.json")
    for urn in ("100218", "100223", "100279", "137442"):
        compare_file(REF / "schools" / f"{urn}.json", BUILT / "la" / "204" / "schools" / f"{urn}.json", f"schools/{urn}.json")

    # Benchmarks: reference "hackney" must equal england/benchmarks.json la.204.
    # The top-level notes legitimately differ (they describe the la structure).
    ref_b = strip(json.loads((REF / "benchmarks.json").read_text()))
    eng_path = BUILT / "england" / "benchmarks.json"
    if not eng_path.exists():
        diffs.append("england/benchmarks.json missing")
    else:
        eng_b = strip(la_view(json.loads(eng_path.read_text()), "204"))
        for key in sorted(set(ref_b) | set(eng_b)):
            if key == "notes":
                continue
            walk(f"benchmarks.{key}", ref_b.get(key), eng_b.get(key))

    if diffs:
        print(f"{len(diffs)} difference(s) (showing up to {MAX_DIFFS}):")
        for d in diffs[:MAX_DIFFS]:
            print(" ", d)
        return 1
    print("All reference values reproduced (only `generated` differs).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
