#!/bin/bash
# Nightly reading of parents' associations' accounts (loom job pta-accounts-night, 20:00): read until 09:00 with
# the local models, two at a time (backing off while the load average is over 60), then unload them so the Mac is free in the day. Resumable; one run at a time;
# exits at once when every association has been read. caffeinate keeps the Mac awake while it runs (not with the lid shut).
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$(dirname "$0")/../.."
exec caffeinate -i python3 -m pipeline.money.pta_accounts --workers 2 --stop-at 09:00 --manage-models
