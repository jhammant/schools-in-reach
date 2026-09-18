# REPORT: DfE pipeline — one borough to all of England

## What changed

- `fetch.py`: added `cscp_england_zip` (the download form's "All of England"
  option is `regions=0`, found by walking the live form); `ees_filtered` now
  takes `la_code=None` to keep every row (all LAs and all ~350k school rows).
- `register.py`: `load_register_england` groups open establishments by LA and
  drops non-English codes (GOR "Not Applicable" or "Wales (pseudo)");
  `school_record` takes the LA code.
- `performance.py`, `finance.py`, `workforce.py`: per-school logic untouched;
  benchmarks now build `la: {<code>: {...}}` alongside `england`. All-England
  census files carry no LA rows, so per-LA census aggregates are computed from
  school rows (verified to match the published LA rows exactly).
- `build.py`: `--la <code>` builds selected LAs; default builds all. Writes
  `out/site/data/la/<code>/{schools.json, league_tables.json, schools/<urn>.json}`,
  `england/las.json` (region, LAD codes, counts, bbox, centroid) and
  `england/benchmarks.json`.
- `verify.py` generalized to any LA; `compare_reference.py` added.

## Run

Downloads (3 CSCP all-England zips ~34 MB, 10 EES CSVs) took ~4 minutes, once,
into the cache. The full build then runs in ~40 seconds.

## Counts and sizes

- 153 local authorities; 25,159 open establishments; 25,159 detail files.
- Output: 226 MB total (`la/` 224 MB, `england/` 1.5 MB).
- Largest league tables: Kent 114.7 KB, Lancashire 110.2 KB, Essex 95.2 KB,
  Hertfordshire 90.8 KB, Hampshire 78.0 KB.
- Sections per school: census 23,486; workforce 21,601; finance 21,319;
  absence 20,425; KS2 15,573; KS4 5,634; destinations 4,167; KS5 2,769.

## Verification

- `--la 204` reproduces every value in `reference/hackney/` (schools.json,
  league_tables.json, the four school files, and all benchmark sections);
  only `generated` differs.
- Live CSCP spot checks, two schools each: Camden (202) 83/83, Kent (886)
  83/83, Manchester (352) 83/83 values match.

## Gaps

- Skipped non-English LA codes: 000, 660–681 (Wales), 701–708 (offshore/
  overseas establishments).
- DfE publishes no LA-level destinations for City of London (201), Isles of
  Scilly (420, KS5/HE only) and Cumberland/Westmorland (942/943, HE only);
  those entries are absent from benchmarks.
