#!/bin/bash
# Copy the public site into this build context (nothing else from the project is uploaded) and deploy to Railway.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete --exclude fleet.app.yaml "$HERE/../../site/" "$HERE/site/"
cd "$HERE" && railway up --detach --service schools-in-reach "$@"
