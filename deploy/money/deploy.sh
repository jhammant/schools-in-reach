#!/bin/bash
# Build School Money (site_money/), check the payload, stage it into this build context and deploy
# the "school-money" Railway service (money.schoolsinreach.com).
#
# --no-gitignore matters: .gitignore excludes site_money/ and this staging copy (generated from
# open data the pipelines rebuild, deliberately kept out of git). Without the flag `railway up`
# skips them and the image builds without a site: `"/site": not found`.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
# finance_history.jsonl comes from pipeline/dfe/finance_history.py (cached DfE workbooks);
# pta.json from pipeline/money/pta.py. Both are read from pipeline/.cache by default.
if ! (cd "$REPO" && python3 -m pipeline.money.build_money); then
  echo "Deploy aborted: School Money generation failed." >&2
  exit 1
fi
# Count actual output, so an empty or partial payload can never silently ship.
python3 - "$REPO/site_money" <<'PY_CHECK'
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

site = Path(sys.argv[1])
BASE = "https://money.schoolsinreach.com/"


def resolves(loc):
    rel = loc.removeprefix(BASE)
    target = site / rel
    return loc.startswith(BASE) and (target.is_file() or (target / "index.html").is_file() or (rel == "" and (site / "index.html").is_file()))


schools = sum(1 for _ in (site / "school").glob("*/index.html"))
problems = []
if schools < 20_000:
    problems.append(f"only {schools:,} school pages (need 20,000)")
try:
    index = ET.parse(site / "sitemap.xml").getroot()
    maps = [n.text for n in index.findall("{*}sitemap/{*}loc")]
    if not maps or not all(resolves(m) for m in maps):
        problems.append("sitemap index empty or points at missing files")
    for m in maps:
        child = ET.parse(site / m.removeprefix(BASE)).getroot()
        locs = [n.text for n in child.findall("{*}url/{*}loc")]
        missing = [loc for loc in locs if not resolves(loc)]
        if not locs or missing:
            problems.append(f"{m}: {len(missing)} of {len(locs)} locs do not resolve (first: {missing[:3]})")
except (OSError, ET.ParseError, AttributeError) as exc:
    problems.append(f"sitemap unreadable: {exc}")
try:
    if not json.loads((site / "data/search.json").read_text(encoding="utf-8")):
        problems.append("/data/search.json is empty")
except (OSError, ValueError) as exc:
    problems.append(f"/data/search.json unreadable: {exc}")
if not (site / "robots.txt").is_file():
    problems.append("robots.txt missing")
if not (site / "404.html").is_file():
    problems.append("404.html missing")
if problems:
    sys.exit("Deploy aborted: " + "; ".join(problems))
print(f"School Money deploy check passed: {schools:,} school pages, sitemap, search index, robots and 404 present.")
PY_CHECK
rsync -a --delete "$REPO/site_money/" "$HERE/site/"
cd "$HERE" && railway up --detach --no-gitignore --service school-money "$@"
