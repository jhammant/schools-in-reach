#!/bin/bash
# Copy the public site into this build context (nothing else is uploaded) and deploy to Railway.
#
# --no-gitignore matters: .gitignore excludes site/data and this staging copy (400 MB of
# generated open data the pipelines rebuild, deliberately kept out of git). Without the flag
# `railway up` skips them and the image builds without a site: `"/site": not found`.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete --exclude fleet.app.yaml "$HERE/../../site/" "$HERE/site/"
cd "$HERE" && railway up --detach --no-gitignore --service schools-in-reach "$@"
