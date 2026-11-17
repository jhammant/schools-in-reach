#!/bin/bash
# Morning deploy of School Money (loom job school-money-morning-deploy, 09:15): only when the parents' association
# data (pta.json, pta_accounts.json) changed since the last deploy, only when the money tests pass, and never at the
# same time as another deploy (the shared lock directory).
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.asdf/shims:$HOME/.asdf/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"   # asdf: the railway CLI
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CACHE="$REPO/pipeline/.cache/money"
MARK="$CACHE/last_deploy"
LOCK="$CACHE/deploy.lock"
cd "$REPO"
log() { echo "$(date '+%F %T') $*"; }
# Fold in anything the PTA website crawl found (its journal outlives the session that ran it). A merge that lowers
# the number of schools with a matched association is rolled back.
if [ -f "$CACHE/pta_crawl.results.jsonl" ]; then
  python3 -c "from pipeline.money import pta_crawl as c; j = c.Journal(c.journal_path(c.OUT)); c.write_outputs(c.OUT, j.latest())" \
    || log "could not rebuild the crawl outputs"
  if [ "$CACHE/pta_crawl.json" -nt "$CACHE/pta.json" ]; then
    before=$(python3 -c "import json; print(len(json.load(open('$CACHE/pta.json'))['schools']))")
    cp "$CACHE/pta.json" "$CACHE/pta.json.morning-prev"
    if python3 -m pipeline.money.pta >"$CACHE/morning_pta.log" 2>&1; then
      after=$(python3 -c "import json; print(len(json.load(open('$CACHE/pta.json'))['schools']))")
      if [ "$after" -lt "$before" ]; then cp "$CACHE/pta.json.morning-prev" "$CACHE/pta.json"; log "PTA merge lowered matched schools ($before -> $after); rolled back"
      else log "merged crawl finds: $before -> $after schools with an association"; fi
    else cp "$CACHE/pta.json.morning-prev" "$CACHE/pta.json"; log "pta.py failed; pta.json restored"; fi
  fi
fi
changed=$(find "$CACHE/pta.json" "$CACHE/pta_accounts.json" -newer "$MARK" 2>/dev/null | wc -l | tr -d ' ')
if [ -f "$MARK" ] && [ "$changed" = "0" ]; then log "no new parents' association data since the last deploy"; exit 0; fi
python3 -m pipeline.money.pta_accounts --reverify || log "re-verify failed"
# The two timing benchmarks are left out: they fail when the Mac is busy (the local models reading accounts push the
# load average past 400), which says nothing about whether the site is right.
if ! python3 -m pytest -q -p no:cacheprovider pipeline/money tests -k "money or areas or a1_ or a4_ or a5_ or b1_ or b3_ or shell or search or deploy" \
     --deselect pipeline/money/test_build_money.py::HardeningTest::test_six_thousand_schools_build_in_under_a_minute \
     --deselect pipeline/money/test_build_money.py::RealNearbyTest::test_add_nearby_runs_in_a_few_seconds >"$CACHE/morning_tests.log" 2>&1; then
  log "tests failed; not deploying (see $CACHE/morning_tests.log)"; exit 1
fi
until mkdir "$LOCK" 2>/dev/null; do log "waiting for another deploy"; sleep 60; done
trap 'rmdir "$LOCK"' EXIT
log "deploying"
if ./deploy/money/deploy.sh; then touch "$MARK"; log "deployed"; else log "deploy FAILED"; exit 1; fi
