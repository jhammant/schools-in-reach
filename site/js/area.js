import { $, $$, esc, fmt, humanize, cssVar, milesBetween, pointInGeometry } from "./util.js";
import { state, load, laFile, laName, nearestLoadedLa, laForDistrict } from "./state.js";
import { getMap } from "./map.js";

/* global L */

const layers = {};
// Which overlays are switched on. Kept apart from the Leaflet layer objects: Leaflet uses `_on` internally.
const active = new Set();
const ui = { measure: "" };

const MEASURE_LABELS = {
  imd_decile: "Index of Multiple Deprivation (decile)",
  income_decile: "Income deprivation (decile)",
  employment_decile: "Employment deprivation (decile)",
  education_skills_decile: "Education & skills deprivation (decile)",
  health_decile: "Health deprivation (decile)",
  crime_decile: "Crime (decile)",
  barriers_housing_services_decile: "Barriers to housing & services (decile)",
  living_environment_decile: "Living environment (decile)",
  idaci_decile: "Children in low-income families, IDACI (decile)",
  population: "Population",
  pct_age_0_15: "% aged 0–15",
  pct_owned: "% homes owned",
  pct_social_rented: "% social rented",
  pct_private_rented: "% private rented",
  pct_level4_plus: "% with degree-level qualifications",
  pct_households_not_deprived: "% households not deprived",
  pct_white: "% White",
  pct_asian: "% Asian",
  pct_black: "% Black",
  pct_mixed: "% Mixed ethnicity",
  pct_other_ethnic: "% Other ethnic group",
  pct_no_car: "% households with no car",
  density_per_km2: "People per km²",
};
const isDecile = (k) => /decile/.test(k);
const SEQ = ["--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6", "--seq-7"];

let areaLa = null;

/** The council to profile: the one at your pin, else the one at the map centre. */
function currentAreaLa() {
  const home = state.home;
  const fromHome = home?.districtCode && laForDistrict(home.districtCode);
  if (fromHome) return String(fromHome.la_code);
  const point = home || (() => { const c = getMap()?.getCenter(); return c ? { lat: c.lat, lon: c.lng } : null; })();
  return point ? nearestLoadedLa(point) : null;
}

export async function renderArea() {
  const root = $("#view-area");
  const la = currentAreaLa();
  if (la !== areaLa) {
    // Council-specific overlays belong to the previous council: drop them.
    ["nurseries", "pois", "shade"].forEach((name) => { layers[name]?.remove(); delete layers[name]; active.delete(name); });
    areaLa = la;
  }
  const [lsoa, pois, transport, envLayers, nurseries] = await Promise.all([
    la ? laFile(la, "lsoa.geojson") : null,
    la ? laFile(la, "pois.geojson") : null,
    load("england/stations.geojson"),
    load("england/env_layers.json"),
    la ? laFile(la, "nurseries.json") : null,
  ]);
  const measureKeys = lsoa?.features?.length
    ? Object.keys(lsoa.features[0].properties).filter((k) => typeof lsoa.features[0].properties[k] === "number" && !/rank$/.test(k))
    : [];
  const envList = Array.isArray(envLayers) ? envLayers : envLayers?.layers || [];
  const nurseryList = Array.isArray(nurseries) ? nurseries : nurseries?.providers || [];

  root.innerHTML = `
    ${la ? `<p class="small muted" style="margin:0 0 6px">${esc(laName(la))}</p>` : `<p class="callout">Zoom in on the map or search a postcode to see an area profile.</p>`}
    <div id="area-profile"></div>

    <h3 class="section">Map layers</h3>
    <div class="toggle-list">
      ${nurseryList.length ? `<label><input type="checkbox" data-layer="nurseries" ${active.has("nurseries") ? "checked" : ""}> Nurseries &amp; childcare (${nurseryList.filter((n) => n.lat != null).length} with an address)</label>` : ""}
      ${pois?.features?.length ? `<label><input type="checkbox" data-layer="pois" ${active.has("pois") ? "checked" : ""}> Parks, libraries, GPs &amp; more</label>` : ""}
      ${transport?.features?.length ? `<label><input type="checkbox" data-layer="transport" ${active.has("transport") ? "checked" : ""}> Stations</label>` : ""}
      ${state.home ? `<label><input type="checkbox" data-layer="crime" ${active.has("crime") ? "checked" : ""}> Reported crime near you (latest month)</label>` : ""}
      ${envList.map((e) => `<label><input type="checkbox" data-env="${esc(e.id)}" ${active.has(`env:${e.id}`) ? "checked" : ""}> ${esc(e.title)}${e.min_zoom ? ` <span class="muted small">(zoom in to see)</span>` : ""}</label>`).join("")}
    </div>

    ${measureKeys.length ? `
    <h3 class="section">Shade neighbourhoods by</h3>
    <select id="measure" style="width:100%">
      <option value="">No shading</option>
      ${measureKeys.map((k) => `<option value="${esc(k)}" ${ui.measure === k ? "selected" : ""}>${esc(MEASURE_LABELS[k] || humanize(k))}</option>`).join("")}
    </select>
    <div id="measure-legend" class="small" style="margin-top:6px"></div>
    <p class="note">Neighbourhoods are census areas (LSOAs) of about 1,500 people. Deciles run from 1, the most deprived 10% in England, to 10, the least deprived.</p>` : ""}
    <p class="note">Sources: MHCLG English Indices of Deprivation, ONS Census 2021, OpenStreetMap contributors, NaPTAN, Ofsted, data.police.uk.</p>`;

  $$("[data-layer]", root).forEach((cb) => cb.addEventListener("change", () => toggle(cb.dataset.layer, cb.checked, { pois, transport, nurseryList })));
  $$("[data-env]", root).forEach((cb) => cb.addEventListener("change", () => toggleEnv(envList.find((e) => e.id === cb.dataset.env), cb.checked)));
  $("#measure", root)?.addEventListener("change", (e) => { ui.measure = e.target.value; shade(lsoa); });
  if (ui.measure) shade(lsoa);
  renderProfile(lsoa, pois, transport, nurseryList);
}

async function renderProfile(lsoa, pois, transport, nurseryList) {
  const box = $("#area-profile");
  const home = state.home;
  if (!home) {
    box.innerHTML = `<p class="callout">Search a postcode or place the pin to see a profile of the neighbourhood: deprivation, housing, qualifications, crime, stations and amenities.</p>`;
    return;
  }
  const feature = lsoa?.features?.find((f) => pointInGeometry(home.lon, home.lat, f.geometry));
  const p = feature?.properties;
  const decileRow = (k) => (p?.[k] == null ? "" : `<tr><td>${esc(MEASURE_LABELS[k] || humanize(k))}</td><td class="num" style="width:40px">${p[k]}</td><td style="width:40%"><div class="decile">${Array.from({ length: 10 }, (_, i) => `<i class="${i < p[k] ? "on" : ""}"></i>`).join("")}</div></td></tr>`);
  const pctRow = (k) => (p?.[k] == null ? "" : `<tr><td>${esc(MEASURE_LABELS[k] || humanize(k))}</td><td class="num">${k.startsWith("pct") ? fmt.pct(p[k], 1) : fmt.num(p[k])}</td></tr>`);

  const near = (features, radius) => (features || []).map((f) => ({ f, d: milesBetween(home, { lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] }) })).filter((x) => x.d <= radius).sort((a, b) => a.d - b.d);
  const stations = near(transport?.features, 1.5).slice(0, 4);
  const poiCounts = {};
  near(pois?.features, 0.5).forEach(({ f }) => { poiCounts[f.properties.category] = (poiCounts[f.properties.category] || 0) + 1; });
  const nurseriesNear = nurseryList.filter((n) => n.lat != null && milesBetween(home, n) <= 0.5).length;

  box.innerHTML = `
    <h3 class="section" style="margin-top:4px">Your neighbourhood${p ? ` <span class="muted">· ${esc(p.lsoa21nm || p.lsoa21cd || "")}</span>` : ""}</h3>
    ${p ? `
      <table><tbody>${["imd_decile", "idaci_decile", "income_decile", "employment_decile", "education_skills_decile", "health_decile", "crime_decile", "barriers_housing_services_decile", "living_environment_decile"].map(decileRow).join("")}</tbody></table>
      <p class="note">Deprivation deciles: 1 is among the most deprived 10% of neighbourhoods in England, 10 the least.</p>
      <table><tbody>${["population", "pct_age_0_15", "pct_owned", "pct_social_rented", "pct_private_rented", "pct_level4_plus", "pct_households_not_deprived", "pct_no_car", "density_per_km2"].map(pctRow).join("")}</tbody></table>`
      : `<p class="note">${lsoa ? "Your pin is just outside this council's neighbourhoods. Move it slightly or check the next council." : "Neighbourhood data for this council isn't available yet."}</p>`}

    ${stations.length ? `<h3 class="section">Nearest stations</h3><table><tbody>${stations.map(({ f, d }) => `<tr><td>${esc(f.properties.name)}<br><span class="muted small">${esc([...[].concat(f.properties.modes || []).map((m) => humanize(m)), ...[].concat(f.properties.lines || [])].join(" · "))}</span></td><td class="num">${fmt.mi(d)}</td></tr>`).join("")}</tbody></table>` : ""}

    ${Object.keys(poiCounts).length || nurseriesNear ? `<h3 class="section">Within half a mile</h3><div class="pills">${nurseriesNear ? `<span class="pill plain">${nurseriesNear} nurseries &amp; childcare</span>` : ""}${Object.entries(poiCounts).sort((a, b) => b[1] - a[1]).map(([c, n]) => `<span class="pill plain">${n} ${esc(humanize(c).toLowerCase())}${n > 1 && !/s$/.test(c) ? "s" : ""}</span>`).join("")}</div>` : ""}

    <h3 class="section">Crime within a mile</h3>
    <div id="crime-summary" class="small muted">Loading from data.police.uk…</div>`;
  loadCrime();
}

async function fetchCrime(home) {
  const key = `${home.lat.toFixed(4)},${home.lon.toFixed(4)}`;
  if (layers._crimeKey === key) return layers._crimeData;
  const [crimes, updated] = await Promise.all([
    fetch(`https://data.police.uk/api/crimes-street/all-crime?lat=${home.lat.toFixed(5)}&lng=${home.lon.toFixed(5)}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))),
    fetch("https://data.police.uk/api/crime-last-updated").then((r) => (r.ok ? r.json() : null)).catch(() => null),
  ]);
  layers._crimeKey = key;
  layers._crimeData = { crimes, month: crimes[0]?.month || updated?.date?.slice(0, 7) };
  return layers._crimeData;
}

async function loadCrime() {
  const box = $("#crime-summary");
  if (!box || !state.home) return;
  try {
    const { crimes, month } = await fetchCrime(state.home);
    const counts = {};
    crimes.forEach((c) => { counts[c.category] = (counts[c.category] || 0) + 1; });
    const monthLabel = month ? new Date(`${month}-01`).toLocaleDateString("en-GB", { month: "long", year: "numeric" }) : "the latest month";
    box.classList.remove("muted");
    box.innerHTML = `<p>${fmt.num(crimes.length)} crimes reported within a mile in ${esc(monthLabel)}.</p>
      <table><tbody>${Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([c, n]) => `<tr><td>${esc(humanize(c.replace(/-/g, "_")))}</td><td class="num">${n}</td></tr>`).join("")}</tbody></table>
      <p class="note">Locations are approximate: to protect privacy, police.uk places each crime at a nearby anonymous point.</p>`;
  } catch (err) {
    box.textContent = `We couldn't load crime data (${err.message}). Please try again in a moment.`;
  }
}

async function toggle(name, onOff, { pois, transport, nurseryList }) {
  const map = getMap();
  if (onOff) active.add(name);
  else active.delete(name);
  if (layers[name]) {
    if (onOff) layers[name].addTo(map);
    else layers[name].remove();
    if (!(name === "crime" && onOff)) return;
  }
  if (!onOff) return;
  const muted = cssVar("--text-secondary");
  const surface = cssVar("--surface-1");
  let layer;
  if (name === "nurseries") {
    layer = L.layerGroup(nurseryList.filter((n) => n.lat != null).map((n) =>
      L.circleMarker([n.lat, n.lon], { radius: 5, color: surface, weight: 1.5, fillColor: cssVar("--s7"), fillOpacity: 0.9 })
        .bindPopup(`<strong>${esc(n.name || "Childcare provider")}</strong><br>${esc(n.provider_type || "")}${n.places ? `<br>${n.places} places` : ""}${n.provider_subtype ? ` · ${esc(n.provider_subtype)}` : ""}${n.latest_grade || n.overall_effectiveness ? `<br>Ofsted: ${esc(n.latest_grade || n.overall_effectiveness)}` : ""}${n.latest_inspection_date ? ` (${esc(fmt.date(n.latest_inspection_date))})` : ""}${n.address || n.postcode ? `<br>${esc([n.address, n.postcode].filter(Boolean).join(", "))}` : ""}`),
    ));
  } else if (name === "pois") {
    layer = L.geoJSON(pois, {
      pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4, color: surface, weight: 1, fillColor: muted, fillOpacity: 0.85 }),
      onEachFeature: (f, l) => l.bindTooltip(`${esc(f.properties.name || humanize(f.properties.category))} · ${esc(humanize(f.properties.category))}`),
    });
  } else if (name === "transport") {
    layer = L.geoJSON(transport, {
      pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 6, color: cssVar("--text-primary"), weight: 2, fillColor: surface, fillOpacity: 1 }),
      onEachFeature: (f, l) => l.bindTooltip(`${esc(f.properties.name)}${f.properties.modes ? ` · ${esc([].concat(f.properties.modes).join(", "))}` : ""}`),
    });
  } else if (name === "crime") {
    if (layers.crime) layers.crime.remove();
    try {
      const { crimes } = await fetchCrime(state.home);
      layer = L.layerGroup(crimes.slice(0, 3000).map((c) =>
        L.circleMarker([+c.location.latitude, +c.location.longitude], { radius: 3, stroke: false, fillColor: cssVar("--critical"), fillOpacity: 0.55 })
          .bindTooltip(`${esc(humanize(c.category.replace(/-/g, "_")))} · ${esc(c.location.street?.name || "")}`),
      ));
    } catch {
      return;
    }
  }
  if (!layer || !active.has(name)) return;
  layers[name] = layer;
  layer.addTo(map);
}

function toggleEnv(def, onOff) {
  if (!def) return;
  const key = `env:${def.id}`;
  const map = getMap();
  if (!layers[key]) {
    layers[key] = L.tileLayer.wms(def.url, {
      layers: def.layers,
      format: def.format || "image/png",
      transparent: def.transparent !== false,
      version: def.version || "1.3.0",
      opacity: 0.65,
      attribution: def.attribution || "",
      minZoom: def.min_zoom || 0,
    });
    layers[key].setZIndex(300);
  }
  if (onOff) {
    active.add(key);
    layers[key].addTo(map);
  } else {
    active.delete(key);
    layers[key].remove();
  }
}

function shade(lsoa) {
  const map = getMap();
  if (layers.shade) layers.shade.remove();
  const legend = $("#measure-legend");
  if (!ui.measure || !lsoa) { if (legend) legend.innerHTML = ""; return; }
  const k = ui.measure;
  const values = lsoa.features.map((f) => f.properties[k]).filter((v) => typeof v === "number").sort((a, b) => a - b);
  let colorFor;
  let legendHtml;
  if (isDecile(k)) {
    colorFor = (v) => cssVar(SEQ[Math.round(((10 - v) / 9) * (SEQ.length - 1))]);
    legendHtml = `<div style="display:flex;gap:2px;align-items:center">More deprived ${[1, 3, 5, 7, 10].map((d) => `<span class="swatch" style="border-radius:2px;width:22px;background:${colorFor(d)}"></span>`).join("")} Less deprived</div>`;
  } else {
    const q = (p) => values[Math.min(values.length - 1, Math.floor(p * values.length))];
    const breaks = [0.2, 0.4, 0.6, 0.8].map(q);
    const steps = [SEQ[1], SEQ[2], SEQ[3], SEQ[4], SEQ[5]];
    colorFor = (v) => cssVar(steps[breaks.filter((b) => v >= b).length]);
    const f = (v) => (k.startsWith("pct") ? `${v.toFixed(0)}%` : fmt.num(v));
    legendHtml = `<div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">${steps.map((s, i) => `<span style="display:inline-flex;align-items:center;gap:3px"><span class="swatch" style="border-radius:2px;width:16px;background:${cssVar(s)}"></span>${i === 0 ? `&lt; ${f(breaks[0])}` : i === 4 ? `≥ ${f(breaks[3])}` : `${f(breaks[i - 1])}–${f(breaks[i])}`}</span>`).join("")}</div>`;
  }
  layers.shade = L.geoJSON(lsoa, {
    style: (f) => ({ weight: 0.6, color: cssVar("--surface-1"), fillOpacity: 0.55, fillColor: typeof f.properties[k] === "number" ? colorFor(f.properties[k]) : "transparent" }),
    onEachFeature: (f, l) => l.bindTooltip(`${esc(f.properties.lsoa21nm || f.properties.lsoa21cd)}<br>${esc(MEASURE_LABELS[k] || humanize(k))}: ${f.properties[k] == null ? "–" : k.startsWith("pct") ? fmt.pct(f.properties[k], 1) : fmt.num(f.properties[k], 1)}`, { sticky: true }),
  }).addTo(map);
  layers.shade.bringToBack();
  if (legend) legend.innerHTML = legendHtml;
}
