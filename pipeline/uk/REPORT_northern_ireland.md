# Northern Ireland schools

`pipeline/uk/northern_ireland.py` → `site/data/la/N09*/schools.json` (11 councils) and
`site/data/uk/northern_ireland_las.json`. Caches in `pipeline/.cache/uk/ni/`; `--offline` re-runs
offline.

## Sources (all Open Government Licence v3.0)

- DE NI, *School enrolment – school level data 2025/26* (census 10 Oct 2025) + *Available places
  2025/26*. DE's copyright page 404s; OGL via OpenDataNI's licensing of the same data.
- OpenDataNI / DE, *School Locations* Feb 2016 — building coordinates, phone.
- postcodes.io — postcode centroids, ONS council codes.

**Blocked, not worked around:** Schools Plus export POST (`apps.education-ni.gov.uk`) → BIG-IP
"Request Rejected"; `eani.org.uk` (admissions criteria, Area Profiles) → Cloudflare 403.

## Counts

1,098 schools — Primary 775, Secondary 124, Grammar 66, Nursery 93, Special 40. Belfast 177,
Newry 128, Armagh 127, Mid Ulster 120, Causeway 97, Fermanagh 95, Derry 87, Mid & East Antrim 72,
Antrim 71, Ards 67, Lisburn 57. **0 unplaced** (975 building points, 123 centroids).
`urn` = 30000000 + DE ref; no English-URN collisions.

## Verified

Six schools, six councils, every phase: name, postcode, phase and enrolment match the DE workbook;
post-primary names cross-checked in SAER 2024-25. Sampled coordinates reverse-geocode into the right
council, as do all 23 points over 800 m from their postcode centroid.

## Missing

Website, head, religious ethos (except Catholic Maintained), post-primary gender — DE publishes
none. Independent schools and pre-school playgroups are excluded.

## Admissions

NI post-primary admission is criteria-based, not distance-based. DE classes 66 schools as Grammar;
63 use the SEAG assessment (14/21 Nov 2026, Sept 2027 entry), so `selective` records DE's
classification, not SEAG membership. SEAG publishes no cut-off scores and has "no role … in how
each school uses those Outcomes"; each Board of Governors ranks its own criteria. **No open
equivalent of England's "last distance offered" exists.** The only open oversubscription signal is
`capacity` vs `pupils`; application-vs-admission history sits in prospectuses and EA Area Profiles. Families need that history, the criteria and the admissions number.
