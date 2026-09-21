#!/bin/bash
# Copy the public site into this build context (nothing else is uploaded) and deploy to Railway.
#
# --no-gitignore matters: .gitignore excludes site/data and this staging copy (400 MB of
# generated open data the pipelines rebuild, deliberately kept out of git). Without the flag
# `railway up` skips them and the image builds without a site: `"/site": not found`.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if ! python3 "$HERE/../../pipeline/seo/build_pages.py"; then
  echo "Deploy aborted: static school page generation failed." >&2
  exit 1
fi
# Count actual output, so an empty or partial payload can never silently ship.
python3 - "$HERE/../../site" <<'PY_CHECK'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
site = Path(sys.argv[1])
count = sum(1 for _ in (site / "school").glob("*/index.html"))
try:
    root = ET.parse(site / "sitemap.xml").getroot()
    locations = root.findall("{*}sitemap/{*}loc")
    valid = bool(locations) and all(
        (site / location.text.removeprefix("https://www.schoolsinreach.com/")).is_file()
        for location in locations
    )
except (OSError, ET.ParseError, AttributeError):
    valid = False
if count < 10_000 or not valid:
    sys.exit(f"Deploy aborted: SEO payload incomplete ({count:,} school pages; valid sitemap: {valid}). Need at least 10,000 school pages and a sitemap with existing child files.")
print(f"SEO deploy check passed: {count:,} school pages and sitemap present.")
PY_CHECK
rsync -a --delete --exclude fleet.app.yaml "$HERE/../../site/" "$HERE/site/"
cd "$HERE" && railway up --detach --no-gitignore --service schools-in-reach "$@"
