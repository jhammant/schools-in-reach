"""Check that `--la 204` output matches the existing site/data/hackney/*.json exactly,
apart from the 'generated' timestamp and the new 'la_code'/'la_name' top-level fields.

Usage (from the project root, after `python pipeline/ofsted/build.py --la 204`):
    uv run python pipeline/ofsted/compare_hackney.py

Exits 1 (and prints every field-level difference found) if the two do not match;
0 if they do. Reports what changed even for differences that are expected given
the requested pipeline changes (e.g. nurseries.json's report_url/geocoding source),
rather than silently excluding them - see README notes printed alongside any diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from util import HACKNEY_DIR, LA_CODE, LA_ROOT  # noqa: E402

LA_DIR = LA_ROOT / LA_CODE

FILES = ["ofsted.json", "parentview.json", "nurseries.json", "characteristics.json"]
IGNORE_TOP_LEVEL = {"generated", "la_code", "la_name"}


def deepdiff(a, b, path: str, out: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if path == "$" and k in IGNORE_TOP_LEVEL:
                continue
            deepdiff(a.get(k), b.get(k), f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} (new) vs {len(b)} (old)")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            deepdiff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: new={a!r} old={b!r}")


def main() -> int:
    failed = False
    for name in FILES:
        old_path, new_path = HACKNEY_DIR / name, LA_DIR / name
        if not new_path.exists():
            print(f"{name}: MISSING - run `python pipeline/ofsted/build.py --la 204` first")
            failed = True
            continue
        old = json.loads(old_path.read_text())
        new = json.loads(new_path.read_text())

        if new.get("la_code") != "204" or not new.get("la_name"):
            print(f"{name}: FAIL - la_code/la_name not set as expected (la_code={new.get('la_code')!r}, "
                  f"la_name={new.get('la_name')!r})")
            failed = True

        diffs: list[str] = []
        deepdiff(new, old, "$", diffs)
        if diffs:
            failed = True
            print(f"{name}: {len(diffs)} difference(s)")
            for d in diffs[:50]:
                print(f"  {d}")
            if len(diffs) > 50:
                print(f"  ... and {len(diffs) - 50} more")
        else:
            print(f"{name}: matches site/data/hackney/{name} exactly (apart from {sorted(IGNORE_TOP_LEVEL)})")

    print("\ncompare_hackney", "FAILED" if failed else "passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
