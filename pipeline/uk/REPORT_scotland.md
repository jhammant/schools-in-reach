# Scotland school register

`python3 pipeline/uk/scotland.py`. Downloads cached under `pipeline/.cache/uk/scotland/`; re-runs are offline.

## Sources — all Open Government Licence v3.0

- School contact details: January 2026, Scottish Government: <https://www.gov.scot/publications/school-contact-details/>
- Pupil census supplementary statistics 2025, table 9.1 School Level Pupil Rolls: <https://www.gov.scot/publications/pupil-census-supplementary-statistics/>
- Local Authority Districts (April 2025) Names and Codes, ONS: <https://geoportal.statistics.gov.uk/>
- postcodes.io centroids, from the ONS Postcode Directory: <https://postcodes.io/>

## Counts

2,427 publicly funded schools open on 2026-01-31, all 32 councils: 1,943 primary, 334 secondary, 28 all-through, 122 special. The seven grant-aided schools are filed under the council their postcode falls in.

## Verified

- Pupil total 695,923 — exactly the published 2025 Scotland total.
- Derived phase matches the census school type for all 2,409 schools with a roll.
- All 2,416 geocoded schools fall inside their own council's ONS boundary (point-in-polygon).
- Name, postcode, phase and roll hand-checked for Notre Dame High (Glasgow), Dingwall Primary (Highland), Brae High (Shetland, 120+181 all-through), Orchard Brae (Aberdeen, special) and Madras College (Fife).

## Missing

11 schools lack coordinates: 10 Edinburgh primaries with a blank postcode, and Victoria Primary, whose published EH7 4TN does not exist (probably EH6 4TN; not corrected). Capacity, head teacher and single-sex status are not published in Scottish open data; ages are derived from the department flags. 18 pupil-support services have no roll. Independent schools are registered separately and absent. No emails or head names copied.

## Catchment boundaries

Scotland has a national dataset: "School Catchments — Scotland" (Improvement Service / Spatial Hub; licence Open; updated 2026-08-01; GeoJSON, WFS, SHP, CSV; four layers; excludes Jordanhill), <https://data.spatialhub.scot/dataset/school_catchments-is>. Downloading needs a free account, so it was not fetched.

Council endpoints verified live (ArcGIS REST/WFS, feature count): Aberdeen City 49, Argyll and Bute 79, Dumfries and Galloway 91, East Dunbartonshire 26, Fife 119+, Highland 29, Moray, North Ayrshire 40, Perth and Kinross 17+, Scottish Borders 24, Stirling 35. Listed but unverified: Dundee, Edinburgh, North Lanarkshire, South Ayrshire. Angus's INSPIRE links are dead.
