# Geo pipeline: Hackney map layers

Builds the neighbourhood, socio-economic, points-of-interest, transport and environmental
layers for the static site (Leaflet 1.9.4). Open data only, no API keys.

## Run

```bash
cd <repo root>
uv run --with shapely --with pyproj --with pandas --with requests --with pillow \
  python pipeline/geo/build.py                 # all steps
# subsets / re-download:
uv run --with shapely --with pyproj --with pandas --with requests --with pillow \
  python pipeline/geo/build.py --only boundary,lsoa,verify --refresh
```

Steps: `boundary`, `lsoa`, `pois`, `transport` (stations + bus stops), `env`, `police`, `verify`.
Downloads are cached in `pipeline/.cache/geo/` (delete a file or pass `--refresh` to re-fetch).
`boundary` must run before `pois`/`transport` (they clip to it). `verify` exits non-zero on failure.

| Module | Does |
|---|---|
| `common.py` | paths, cached HTTP (browser User-Agent; Overpass gets an identifying one), projections, GeoJSON writer (5 dp, `metadata`, 1.5 MB guard) |
| `areas.py` | ONS boundary + LSOA polygons, IoD2025 join, Census 2021 join (Nomis) |
| `pois.py` | Overpass query, tag to category mapping, filtering, de-duplication |
| `transport.py` | NaPTAN stations grouped and enriched with TfL modes/lines; NaPTAN bus stops |
| `env_layers.py` | discovers and verifies keyless WMS overlays |
| `police.py` | checks data.police.uk and rewrites the summary block at the end of this README |
| `verify.py` | counts, sizes, completeness, spot-checks against the sources, geometry checks |

## Outputs (`site/data/hackney/layers/`)

Every GeoJSON is a WGS84 `FeatureCollection` with a top-level
`"metadata": {"generated", "sources": [{"title","url","licence","attribution"}], "notes"}`.
Show each source's `attribution` wherever the layer is displayed.

### `boundary.geojson`
One polygon for LB Hackney (E09000012). Source: ONS **Local Authority Districts (May 2026) Boundaries UK BFC**,
simplified 2 m (topology-preserving). The newest `Local_Authority_Districts_<Mon>_<YYYY>_Boundaries_UK_BFC`
service is picked automatically. BFC is used rather than BGC because BGC (127 vertices) is too coarse to clip
bus stops and POIs on boundary roads.
Properties: `lad_code`, `lad_name`, `area_km2`.

### `lsoa.geojson`
149 LSOA 2021 polygons: ONS **LSOA (Dec 2021) Boundaries EW BGC V5**, coverage-simplified 4 m
(`shapely.coverage_simplify`, so neighbouring LSOAs keep identical shared edges). Membership comes from the ONS
lookup **LSOA21_WD25_LAD25_EW_LU_v2**.

| Property | Source / definition |
|---|---|
| `lsoa21cd`, `lsoa21nm` | ONS |
| `imd_rank` (1 = most deprived of 33,755), `imd_decile` | **English Indices of Deprivation 2025** (MHCLG, 30 Oct 2025), File 7 CSV; LSOA 2021 geography, so no 2011 to 2021 conversion is needed |
| `income_decile`, `employment_decile`, `education_skills_decile`, `health_decile`, `crime_decile`, `barriers_housing_services_decile`, `living_environment_decile`, `idaci_decile` | IoD2025 domain deciles (1 = most deprived 10%) |
| `population` | Census 2021 TS001 (Nomis `NM_2021_1`) total usual residents |
| `pct_age_0_15` | TS007B broad age bands (`NM_2018_1`): 0-4 + 5-9 + 10-15. TS007A's 5-year bands split 15-19, so TS007B is used |
| `pct_owned`, `pct_social_rented`, `pct_private_rented` | TS054 (`NM_2072_1`) as % of households. Owned includes shared ownership. "Lives rent free" is in none of the three |
| `pct_level4_plus` | TS067 (`NM_2084_1`) Level 4+ as % of residents aged 16+ |
| `pct_households_not_deprived` | TS011 (`NM_2031_1`) "not deprived in any dimension" |
| `pct_white`, `pct_asian`, `pct_black`, `pct_mixed`, `pct_other_ethnic` | TS021 (`NM_2041_1`) high-level groups |
| `pct_no_car` | TS045 (`NM_2063_1`) households with no car or van |
| `density_per_km2` | TS006 (`NM_2026_1`) usual residents per km² |

Percentages are 1 dp and use each table's own total as the denominator. ONS cell-key perturbation means
table totals differ by a few people. Nomis request pattern:
`https://www.nomisweb.co.uk/api/v01/dataset/<id>.data.csv?geography=645923001TYPE151&measures=20100`
(`645923001` = Hackney in Nomis, `TYPE151` = 2021 LSOAs within it).

### `pois.geojson`
About 800 OpenStreetMap points within Hackney + 300 m (Overpass API, `out geom`). Properties: `category`, `name`, `osm` (`node/123`).
Areas are reduced to their centroid, or to point-on-surface if the centroid falls outside the shape.

| category | OSM tags |
|---|---|
| park | `leisure=park` |
| playground | `leisure=playground` (the only category allowed without a name) |
| library | `amenity=library` |
| leisure_centre | `leisure=sports_centre`, excluding gyms and studios (sport only fitness/yoga/boxing/…, or gym-like names) |
| swimming_pool | public `leisure=swimming_pool` (not paddling pools), or a leisure centre with `sport=swimming` or a mapped pool inside its outline |
| gp | `amenity=doctors` / `healthcare=doctor` |
| pharmacy, dentist | `amenity=*` / `healthcare=*` |
| supermarket | `shop=supermarket` |
| museum | `tourism=museum` |
| cinema, theatre, community_centre, place_of_worship | `amenity=*` |

Filters: a name is required (except playgrounds). Parks, playgrounds, pools, libraries and leisure centres with
`access=private|no|customers|residents|…` are dropped. Playgrounds, pools, libraries and parks inside
school/college/nursery grounds are dropped unless their access is public. Schools are not included (they come
from DfE). Places mapped twice (a node inside its building, or relation plus way) are de-duplicated by
category + name + distance. A sports centre with a pool appears under both leisure_centre and swimming_pool.

### `transport.geojson`
Stations with a NaPTAN access node within 1 km of the boundary: rail `RLY 9100*` (area 910) and Underground/DLR
`MET 9400ZZLU*/9400ZZDL*` (area 940). Nodes are grouped into stations/interchanges using TfL Unified API
StopPoint hubs (`https://api.tfl.gov.uk/StopPoint/<ids>`, no key needed at this volume), which also provide
modes and lines.
Properties: `name`, `modes` (`national_rail|overground|underground|dlr|elizabeth_line`), `lines` (TfL names, e.g.
`Weaver`, `Mildmay`, `Windrush`, `Victoria`, `Elizabeth line`, `Greater Anglia`), `in_borough`, `naptan` (ATCO codes).
If the TfL API is down, the build falls back to NaPTAN-only modes (`national_rail`/`underground`/`dlr`, no lines).

### `bus_stops.geojson`
Active on-street bus stops (NaPTAN `BCT`, area 490) inside the boundary. Properties: `name`, `indicator`
(stop letter or label such as `Stop H`, `->N`), `atco`. The step deletes the file if it would exceed 1 MB.

### `env_layers.json`
A verified list of WMS overlays for `L.tileLayer.wms`:

```text
{"metadata": {"generated": "…", "how_verified": "…", "sources": […], "dropped": [{"id","url","reason"}]},
 "layers": [{"id","title","group","type":"wms","url","layers","format","transparent","version",
             "attribution","licence","legend_url","verified_at","min_zoom?","data_year?","verification"}]}
```

```javascript
const lyr = L.tileLayer.wms(e.url, {
  layers: e.layers, format: e.format, transparent: e.transparent, version: e.version,
  attribution: e.attribution, minZoom: e.min_zoom ?? 0, opacity: 0.6,
});
```

**How layers are verified:** each candidate must list the layer in GetCapabilities. Then a WMS 1.3.0 GetMap PNG
is requested in EPSG:3857 for lon -0.10..-0.02, lat 51.53..51.58 at 512×512. A layer passes only if:

- the response is a PNG;
- at least 0.2% of pixels are visible;
- it is not one flat colour and not mostly pure black;
- every test tile gives the same result when rendered three times.

Layers with `MaxScaleDenominator 50000` (EA flood layers) render blank at 512 px over that extent, so they are
tested as a 2×2 tile grid and get `min_zoom: 14`. Below zoom 14 the service returns transparent tiles.

| id | Service | Result |
|---|---|---|
| `ea_flood_zones_2_3` | EA Flood Map for Planning, Flood Zones 2 and 3 (`spatialdata/flood-map-for-planning-flood-zones`) | verified, min_zoom 14 |
| `ea_flood_zones_climate_change` | EA Flood Zones plus climate change | verified |
| `ea_rofrs` | EA NaFRA2 risk of flooding from rivers and sea (`rofrs_4band`) | verified, min_zoom 14 |
| `ea_rofsw` | EA NaFRA2 risk of flooding from surface water (`rofsw`) | verified, min_zoom 14 |
| `defra_road_noise_lden` / `defra_road_noise_lnight` | Defra strategic noise mapping Round 4, roads (`…_All`) | verified |
| `defra_rail_noise_lden` | Defra strategic noise mapping Round 4, rail | verified |
| `defra_pcm_no2_background` / `defra_pcm_pm25_background` | Defra UK-AIR Pollution Climate Mapping, 1 km background annual mean, latest year (2024) | verified |
| `defra_pcm_no2_roadside` | UK-AIR PCM roadside NO2 (`NO2Roads`) | **dropped**: the same request returns different, often garbled, images |

Not found as keyless WMS/tiles: the London Atmospheric Emissions Inventory (LAEI) concentration maps (London
Datastore has downloads only) and the Imperial/LondonAir maps. The UK-AIR PCM service name (`aq_amb_2024`) is read
from UK-AIR's viewer config (`CONFIG-STUB.js`), so a newer year is picked up automatically.
Licences: EA and Defra layers are OGL v3 (attribution strings are in each entry).

## Street-level crime (data.police.uk), called client-side

No key. CORS is open (`Access-Control-Allow-Origin: *`). Licence: OGL v3.0; attribute
"Contains public sector information licensed under the Open Government Licence v3.0 (data.police.uk)".

**Crimes within 1 mile of a point** (the radius is fixed by the API):

```text
GET https://data.police.uk/api/crimes-street/all-crime?lat=51.5597&lng=-0.0763&date=2026-07
```

**Crimes within a custom polygon.** `poly` is `lat,lng` pairs separated by `:`. The ring closes automatically.

```text
GET https://data.police.uk/api/crimes-street/all-crime?poly=51.5620,-0.0800:51.5620,-0.0726:51.5574,-0.0726:51.5574,-0.0800&date=2026-07
```

URLs longer than 4094 characters return 400. For detailed polygons (e.g. an LSOA or catchment), send a POST
with a form-encoded body instead:

```javascript
const body = new URLSearchParams({ poly: latlngs.map(p => `${p.lat.toFixed(5)},${p.lng.toFixed(5)}`).join(':'), date: '2026-07' });
const crimes = await (await fetch('https://data.police.uk/api/crimes-street/all-crime', { method: 'POST', body })).json();
```

- Omit `date` to get the latest month. To filter by category, replace `all-crime` with a category slug (e.g. `burglary`).
- **Available months:** `GET https://data.police.uk/api/crimes-street-dates` returns
  `[{"date":"2026-07","stop-and-search":["avon-and-somerset",…]}, …]`, newest first, about 36 months.
  `GET https://data.police.uk/api/crime-last-updated` returns `{"date":"2026-07-01"}`. Data lags about 2 months.
- **Categories:** `GET https://data.police.uk/api/crime-categories?date=2026-07` returns `[{"url":"all-crime","name":"All crime"},{"url":"anti-social-behaviour","name":"Anti-social behaviour"},…]`
  (15 entries including `all-crime`).
- **Response:** a JSON array with one object per crime:

  ```json
  {"category":"burglary","location_type":"Force","location":{"latitude":"51.560123","longitude":"-0.076543",
   "street":{"id":1234567,"name":"On or near Church Street"}},"context":"","outcome_status":{"category":"Investigation complete; no suspect identified","date":"2026-07"},
   "persistent_id":"4f1c…","id":123456789,"location_subtype":"","month":"2026-07"}
  ```

  `latitude`/`longitude` are **strings**. `outcome_status` may be `null`. `location_type` is `Force` or `BTP`.
  Locations are snapped to anonymised map points, so many crimes share a coordinate. Group or cluster by
  `location.street.id` or by lat/lng.
- **Rate limit:** leaky bucket, 15 requests/second with bursts up to 30. Going over returns HTTP 429, so back off and retry.
- **Cap:** if an area holds more than 10,000 crimes, the API returns **HTTP 503** and no data. Keep polygons
  neighbourhood-sized, or split the area. A whole-borough Hackney polygon (about 3,600 crimes a month) is fine.
  A Greater-London-sized polygon returns 503.

Latest verification (generated by `build.py --only police`; summary counts only):

<!-- police-check:start -->
_Last checked 2026-09-16T23:20:16+00:00 by `build.py --only police`._

- Months available: 36 (2023-08 to 2026-07); latest = **2026-07**.
- `Access-Control-Allow-Origin: *` on crime responses, so browser `fetch()` works.
- 1-mile radius around lat 51.5597, lng -0.0763 (2026-07): **1428 crimes** (HTTP 200).
- Whole-borough polygon (56 points) via POST: HTTP 200, 3642 crimes.
- ~500 m square polygon via GET: HTTP 200, 69 crimes.
- Greater-London-sized polygon: HTTP 503 (over the 10,000-crime cap).

| Category (2026-07, 1 mile of test point) | Crimes |
|---|---|
| Violence and sexual offences | 372 |
| Anti-social behaviour | 339 |
| Theft from the person | 111 |
| Public order | 107 |
| Other theft | 93 |
| Vehicle crime | 93 |
| Burglary | 78 |
| Shoplifting | 78 |
| Bicycle theft | 53 |
| Drugs | 53 |
| Robbery | 36 |
| Other crime | 9 |
| Possession of weapons | 6 |
<!-- police-check:end -->

## Known gaps / caveats
- **OSM completeness varies.** Swimming pools come out low (3): Britannia Leisure Centre's pool is not mapped in
  OSM, and Kings Hall Leisure Centre is not tagged as a sports centre. Some `amenity=library` tags are special
  collections. Fix upstream in OSM and rebuild.
- `leisure_centre` also covers sports venues (tennis pavilion, bowls club, 5-a-side, climbing walls), because
  OSM uses one tag for all of them.
- LSOA polygons are generalised (BGC, about 20 m) while the borough outline is full resolution. Edges can differ
  by up to about 20 m.
- TfL `lines` reflect TfL's current service data (e.g. `c2c` appears at Liverpool Street).
- Police locations are approximate by design. Show "on or near" wording.
