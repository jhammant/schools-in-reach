#!/usr/bin/env bash
# Cut a Greater London basemap from the latest Protomaps daily OpenStreetMap build (ODbL).
# Serve it statically (nginx supports HTTP range requests); later move it to a CDN bucket and change TILES_URL in site/js/map.js.
set -euo pipefail
BUILD="${1:-$(curl -s https://build-metadata.protomaps.dev/builds.json | python3 -c 'import sys,json; print(json.load(sys.stdin)[-1]["key"])')}"
OUT="$(dirname "$0")/../../site/tiles/london.pmtiles"
pmtiles extract "https://build.protomaps.com/${BUILD}" "$OUT" --bbox=-0.5700,51.2500,0.3700,51.7200 --maxzoom=15 --download-threads=8
pmtiles show "$OUT" | head -20
