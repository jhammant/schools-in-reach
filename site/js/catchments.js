import { cssVar, esc, MILE } from "./util.js";
import { state, admissionsFor, isFaithSchool } from "./state.js";
import { latestYear, groupsOf, distances, allOffered, chanceModel, chanceAt, CHANCE_CLASSES, chanceClass, heatBands } from "./admissions.js";
import { getMap, heatShapes } from "./map.js";

/* global L */

// Published "cut-offs" above this (e.g. 7.2 or 350 miles) mean everyone in that band got a place, not a real boundary.
const MAX_MEANINGFUL_MILES = 3;
// Heat surface resolution: roughly 60 m cells.
const CELL_METRES = 60;
// The all-schools surface starts at this chance; a single school's own view shows the full scale.
const SURFACE_MIN = 0.2;
const SURFACE_CLASSES = CHANCE_CLASSES.filter((k) => k.min >= SURFACE_MIN);
// Below SURFACE_MIN but still inside a busy school's modelled area: a quiet tint, so it reads differently from "no data".
const LOW_CLASS = { label: "Under 20%", color: "--chance-low" };
// Schools that usually take everyone who applies aren't painted as heat, but living near one is good news worth showing.
const OPEN_CLASS = { label: "A school with space for everyone is nearby", color: "--chance-open" };
const OPEN_NEARBY_MILES = 1.5;

const ui = { phase: "secondary", view: "heat", visible: true, includeFaith: false, linesScope: "covers" };
// Drawing every school's ring at once is unreadable, so the lines view starts with the ones that reach you.
const LINES_MIN = 3;
const LINES_NEAR_MAX = 8;
let layer;
let control;
let onSelect = () => {};
const shapes = new Map();
let heatSchools = [];
let openSchools = [];
let heatOverlay = null;
let hoverFrame = 0;
let hoverRing = null;

/** The outline for a school's latest year: inner = every band got in, outer = at least one band got in. */
export function catchmentFor(school) {
  const rec = admissionsFor(school.urn);
  if (!rec) return null;
  const year = latestYear(rec);
  const y = rec.years[year];
  if (!y || y.allocation === "random_by_zone") return { year, kind: "lottery" };
  if (y.non_preference_offers > 0) return { year, kind: "spare" };
  const d = distances(y);
  const vals = groupsOf(y).map((g) => d[g]).filter((v) => v != null && v <= MAX_MEANINGFUL_MILES);
  if (!vals.length) return { year, kind: allOffered(y).length ? "spare" : "none" };
  return { year, kind: "distance", inner: Math.min(...vals), outer: Math.max(...vals), banded: vals.length > 1, faith: y.allocation === "faith_then_distance" };
}

const shortName = (name) => name.replace(/\s*(and Sixth Form|School and Sixth Form|Community School|Primary School|School|Academy)$/i, "").replace(/^The /, "") || name;
const northOf = (lat, lon, meters) => [lat + meters / 111320, lon];
const inPhase = (s) => (ui.phase === "primary" ? s._class.group === "primary" : ["secondary", "allthrough"].includes(s._class.group));
const pct = (c) => (c > 0.99 ? "99%+" : c < 0.01 ? "<1%" : `${Math.round(c * 100)}%`);

export function initCatchments(selectSchool) {
  onSelect = selectSchool;
  const map = getMap();
  map.createPane("catchments").style.zIndex = 350;
  // Labels sit above the school markers (overlay pane, 400) but never catch clicks.
  const labels = map.createPane("catchmentLabels");
  labels.style.zIndex = 450;
  labels.style.pointerEvents = "none";
  layer = L.layerGroup().addTo(map);

  control = L.control({ position: "topright" });
  control.onAdd = () => {
    const div = L.DomUtil.create("div", "catch-control");
    // On a phone the panel would cover the map, so it starts as a chip you tap open.
    if (window.matchMedia("(max-width: 860px)").matches) div.classList.add("collapsed");
    L.DomEvent.disableClickPropagation(div);
    L.DomEvent.disableScrollPropagation(div);
    div.addEventListener("click", (e) => {
      if (e.target.closest(".catch-title")) {
        const open = div.classList.toggle("collapsed");
        e.target.closest(".catch-title").setAttribute("aria-expanded", String(!open));
        return;
      }
      const phase = e.target.closest("[data-catch]");
      const view = e.target.closest("[data-view-mode]");
      const scope = e.target.closest("[data-lines-scope]");
      if (phase) ui.phase = phase.dataset.catch;
      if (view) ui.view = view.dataset.viewMode;
      if (scope) ui.linesScope = scope.dataset.linesScope;
      if (phase || view || scope) renderCatchments();
    });
    div.addEventListener("change", (e) => {
      if (e.target.matches("[data-include-faith]")) {
        ui.includeFaith = e.target.checked;
        renderCatchments();
      }
    });
    return div;
  };
  control.addTo(map);

  const readAt = (e) => {
    if (ui.view !== "heat" || !ui.visible || ui.phase === "off") return;
    // Moving over the control itself must not rewrite the readout you're about to click.
    if (e.originalEvent?.target?.closest?.(".catch-control")) return;
    cancelAnimationFrame(hoverFrame);
    hoverFrame = requestAnimationFrame(() => showReadout({ lat: e.latlng.lat, lon: e.latlng.lng }, "At this spot"));
  };
  map.on("mousemove", readAt);
  map.on("click", readAt);
  map.on("mouseout", () => {
    if (ui.view === "heat") showReadout(state.home, "From your pin");
  });
}

export function setCatchmentPhase(phase) {
  if (phase === ui.phase || !["primary", "secondary"].includes(phase)) return;
  ui.phase = phase;
  renderCatchments();
}

/** Hide the all-schools layer while one school's own heat and rings are on show. */
export function setCatchmentsVisible(visible) {
  ui.visible = visible;
  renderCatchments();
}

/* ---------- control ---------- */

function updateControl(summary) {
  const div = control?.getContainer();
  if (!div) return;
  const color = cssVar(ui.phase === "primary" ? "--s1" : "--s2");
  const seg = (attr, id, label, on) => `<button ${attr}="${id}" aria-pressed="${on}">${label}</button>`;
  let body = "";
  if (ui.phase !== "off") {
    const views = `<div class="seg seg-2">${seg("data-view-mode", "heat", "Chance heat map", ui.view === "heat")}${seg("data-view-mode", "lines", "Cut-off lines", ui.view === "lines")}</div>`;
    const key =
      ui.view === "heat"
        ? !ui.visible
          ? `<div class="catch-note">These are this school's own chance bands. Go back to the list to see every school.</div>`
          : !summary.count
            ? `<div class="catch-note legend-empty">We don't have past admissions figures for the councils here yet, so there's no heat map for this area. Each school's page still shows its details, and we're adding councils one at a time.</div>`
            : `<div class="heat-legend compact">${[...SURFACE_CLASSES, LOW_CLASS].map((k) => `<span><i style="background:${cssVar(k.color)}"></i>${k.label}</span>`).join("")}
             <span class="legend-plain"><i style="background:${cssVar(OPEN_CLASS.color)}"></i>${OPEN_CLASS.label}</span>
             <span class="legend-plain"><i class="plain"></i>No colour: no figures for this area yet</span></div>
           <label class="catch-check"><input type="checkbox" data-include-faith ${ui.includeFaith ? "checked" : ""}> Include faith schools</label>
           <div class="catch-readout" id="catch-readout"></div>
           <div class="catch-note">Colour shows your best chance at any of the ${summary.count} busy (oversubscribed) ${ui.phase} schools, using how far places reached in ${summary.from}–${summary.to}. Recent years count more. Grey-blue means places at those busy schools haven't reached that far lately. Purple means a school within ${OPEN_NEARBY_MILES} miles usually offers a place to everyone who applies: tap the map to see which. Siblings and waiting-list places aren't counted.</div>`
        : `<div class="seg seg-2">${seg("data-lines-scope", "covers", state.home ? "Schools that reach you" : "Nearest schools", ui.linesScope === "covers")}${seg("data-lines-scope", "all", "Every school", ui.linesScope === "all")}</div>
           <div class="catch-key"><span class="key-fill" style="background:${color}33;border-color:${color}"></span>${ui.phase === "secondary" ? "Offered a place in every band" : "Offered a place on distance"} (${summary.to})</div>
           ${ui.phase === "secondary" ? `<div class="catch-key"><span class="key-dash" style="border-color:${color}"></span>Offered in at least one band</div>` : ""}
           <div class="catch-note">Each ring is one school: how far its places reached in ${summary.to}. ${summary.hidden ? `Showing ${summary.count} of ${summary.count + summary.hidden}. ` : `Showing ${summary.count}. `}${state.home ? "Bold rings cover your pin." : "Search a postcode to see which cover you."} No ring means places were usually spare, or decided by a random draw.</div>`;
    body = views + key;
  }
  div.innerHTML = `<button type="button" class="catch-title" aria-expanded="${div.classList.contains("collapsed") ? "false" : "true"}">Catchment areas</button><div class="seg">${seg("data-catch", "secondary", "Secondary", ui.phase === "secondary")}${seg("data-catch", "primary", "Primary", ui.phase === "primary")}${seg("data-catch", "off", "Off", ui.phase === "off")}</div>${body}`;
}

function showReadout(point, heading) {
  const box = document.getElementById("catch-readout");
  if (!box) return;
  if (!point) {
    box.innerHTML = `<span class="muted">Hover over or tap the map to see your chances at nearby schools.</span>`;
    return;
  }
  const rows = heatSchools
    .map(({ s, model }) => {
      const miles = distanceMiles(point, s);
      return { s, miles, c: miles > model.reach ? 0 : chanceAt(model, miles) };
    })
    .filter((r) => r.c >= 0.05)
    .sort((a, b) => b.c - a.c || a.miles - b.miles)
    .slice(0, 5);
  const covered = heatSchools.some(({ s, model }) => distanceMiles(point, s) <= model.reach);
  const open = openNearby(point);
  if (!rows.length && !covered && !open) {
    box.innerHTML = `<div class="readout-head">${esc(heading)}</div><span class="muted">We don't have past admissions figures for this area yet. Each school's page still shows its details.</span>`;
    return;
  }
  box.innerHTML = `<div class="readout-head">${esc(heading)}</div>${
    rows.length
      ? rows.map((r) => `<button class="readout-row" data-urn="${r.s.urn}"><i style="background:${cssVar(chanceClass(r.c)?.color || "--chance-5")}"></i><span>${esc(shortName(r.s.name))}</span><b>${pct(r.c)}</b></button>`).join("")
      : `<span class="muted">Places at the busy ${ui.phase} schools nearby haven't reached this spot in recent years.${open ? "" : " Schools with space are shown in the Schools list, and waiting lists often move over the summer."}</span>`
  }${open}`;
  box.querySelectorAll("[data-urn]").forEach((b) => b.addEventListener("click", () => onSelect(Number(b.dataset.urn), "admissions")));
}

function openNearby(point) {
  const near = openSchools
    .map((s) => ({ s, miles: distanceMiles(point, s) }))
    .filter((x) => x.miles <= OPEN_NEARBY_MILES)
    .sort((a, b) => a.miles - b.miles)
    .slice(0, 3);
  return near.length ? `<div class="readout-open">Usually has space for everyone: ${near.map((x) => `<button class="link-btn" data-urn="${x.s.urn}">${esc(shortName(x.s.name))}</button>`).join(", ")}</div>` : "";
}

/* ---------- rendering ---------- */

/** Flat-earth miles: accurate to well under 0.1% across a borough, and fast enough for a per-pixel surface. */
function distanceMiles(a, b) {
  const kx = Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180) * 69.17;
  return Math.hypot((a.lon - b.lon) * kx, (a.lat - b.lat) * 69.05);
}

export function renderCatchments() {
  if (!layer) return;
  layer.clearLayers();
  shapes.clear();
  heatSchools = [];
  openSchools = [];
  heatOverlay = null;
  hoverRing = null;
  if (!ui.visible || ui.phase === "off") {
    updateControl({});
    return;
  }
  hoverRing = null;
  const candidates = state.schools.filter((s) => s.lat != null && !s._class.independent && inPhase(s));
  if (ui.view === "heat") renderHeat(candidates);
  else renderLines(candidates);
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function renderHeat(candidates) {
  const modelled = candidates
    .filter((s) => ui.includeFaith || !isFaithSchool(s))
    .map((s) => ({ s, model: chanceModel(admissionsFor(s.urn) || { years: {} }) }))
    .filter(({ model }) => model?.kind === "distance");
  // A school that took everyone most years has no real distance limit: show it as "space nearby", not as heat.
  heatSchools = modelled.filter(({ model }) => chanceAt(model, MAX_MEANINGFUL_MILES) < 0.5);
  openSchools = modelled.filter(({ model }) => chanceAt(model, MAX_MEANINGFUL_MILES) >= 0.5).map(({ s }) => s);
  if (!heatSchools.length) {
    updateControl({ from: "", to: "" });
    return;
  }
  const from = Math.min(...heatSchools.map((h) => h.model.from));
  const to = Math.max(...heatSchools.map((h) => h.model.to));
  updateControl({ from, to, count: heatSchools.length });

  // Grid covering every school's drawable reach.
  let south = 90, north = -90, west = 180, east = -180;
  [...heatSchools, ...openSchools.map((s) => ({ s, model: { reach: OPEN_NEARBY_MILES } }))].forEach(({ s, model }) => {
    const reach = model.reach;
    const dLat = reach / 69.05;
    const dLon = reach / (Math.cos((s.lat * Math.PI) / 180) * 69.17);
    south = Math.min(south, s.lat - dLat);
    north = Math.max(north, s.lat + dLat);
    west = Math.min(west, s.lon - dLon);
    east = Math.max(east, s.lon + dLon);
  });
  const stepLat = CELL_METRES / 111320;
  const stepLon = CELL_METRES / (111320 * Math.cos((((south + north) / 2) * Math.PI) / 180));
  const rows = Math.ceil((north - south) / stepLat);
  const cols = Math.ceil((east - west) / stepLon);
  const colors = SURFACE_CLASSES.map((k) => hexToRgb(cssVar(k.color)));
  const lowColor = hexToRgb(cssVar(LOW_CLASS.color));
  const openColor = hexToRgb(cssVar(OPEN_CLASS.color));
  // Mark cells near a school with space for everyone by stamping a circle per school, cheaper than testing every cell.
  const nearOpen = new Uint8Array(rows * cols);
  for (const s of openSchools) {
    const r0 = Math.max(0, Math.floor((north - s.lat - OPEN_NEARBY_MILES / 69.05) / stepLat));
    const r1 = Math.min(rows - 1, Math.ceil((north - s.lat + OPEN_NEARBY_MILES / 69.05) / stepLat));
    const dLon = OPEN_NEARBY_MILES / (Math.cos((s.lat * Math.PI) / 180) * 69.17);
    const c0 = Math.max(0, Math.floor((s.lon - dLon - west) / stepLon));
    const c1 = Math.min(cols - 1, Math.ceil((s.lon + dLon - west) / stepLon));
    for (let r = r0; r <= r1; r++) {
      const lat = north - (r + 0.5) * stepLat;
      for (let c = c0; c <= c1; c++) if (distanceMiles({ lat, lon: west + (c + 0.5) * stepLon }, s) <= OPEN_NEARBY_MILES) nearOpen[r * cols + c] = 1;
    }
  }

  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(cols, rows);
  for (let r = 0; r < rows; r++) {
    const lat = north - (r + 0.5) * stepLat;
    for (let c = 0; c < cols; c++) {
      const point = { lat, lon: west + (c + 0.5) * stepLon };
      let best = 0;
      let covered = false;
      for (const { s, model } of heatSchools) {
        const miles = distanceMiles(point, s);
        if (miles > model.reach) continue;
        covered = true;
        const ch = chanceAt(model, miles);
        if (ch > best) best = ch;
        if (best >= 0.999) break;
      }
      const k = SURFACE_CLASSES.findIndex((cl) => best >= cl.min);
      const i = (r * cols + c) * 4;
      if (k >= 0) {
        [img.data[i], img.data[i + 1], img.data[i + 2]] = colors[k];
        img.data[i + 3] = 115;
      } else if (nearOpen[r * cols + c]) {
        [img.data[i], img.data[i + 1], img.data[i + 2]] = openColor;
        img.data[i + 3] = 70;
      } else if (covered) {
        [img.data[i], img.data[i + 1], img.data[i + 2]] = lowColor;
        img.data[i + 3] = 70;
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  heatOverlay = L.imageOverlay(canvas.toDataURL(), [[north - rows * stepLat, west], [north, west + cols * stepLon]], { pane: "catchments", interactive: false, className: "heat-overlay" }).addTo(layer);
  showReadout(state.home, "From your pin");
}

function renderLines(candidates) {
  const color = cssVar(ui.phase === "primary" ? "--s1" : "--s2");
  const home = state.home;
  let to = null;
  const all = candidates
    .map((s) => ({ s, c: catchmentFor(s) }))
    .filter(({ c }) => c?.kind === "distance");
  const items = scopeLines(all, home)
    // Big areas first so small ones stay on top and clickable.
    .sort((a, b) => b.c.outer - a.c.outer);
  const hidden = all.length - items.length;

  items.forEach(({ s, c }) => {
    to = Math.max(to || 0, c.year);
    const dist = home ? s._dist : null;
    const covers = dist == null ? null : dist <= c.inner ? "all" : dist <= c.outer ? "some" : "none";
    // Tight catchments read stronger than sprawling ones, so a 2.9-mile area doesn't swamp a 0.4-mile one.
    const tightness = Math.max(0.4, Math.min(1.6, 0.8 / c.inner));
    const base = {
      // Rings overlap heavily, so keep fills faint: the outline carries the meaning, and hover fills one in.
      fillOpacity: covers == null ? 0.05 * tightness : covers === "all" ? 0.1 : covers === "some" ? 0.06 : 0.02,
      opacity: covers == null ? 0.7 : covers === "none" ? 0.2 : 1,
      weight: covers === "all" || covers === "some" ? 2.5 : 1.5,
    };
    const fill = L.circle([s.lat, s.lon], { pane: "catchments", radius: c.inner * MILE, color, fillColor: color, ...base });
    const outer = c.banded && c.outer - c.inner > 0.01
      ? L.circle([s.lat, s.lon], { pane: "catchments", radius: c.outer * MILE, color, weight: base.weight, opacity: base.opacity, dashArray: "6 6", fill: false, interactive: false })
      : null;
    const tip = `<strong>${esc(s.name)}</strong><br>${c.year} last distance offered:${c.banded ? `${c.inner.toFixed(2)}–${c.outer.toFixed(2)} mi, depending on band` : `${c.inner.toFixed(2)} mi`}${c.faith ? "<br>Faith is considered before distance" : ""}${dist != null ? `<br>You: ${dist.toFixed(2)} mi (${covers === "all" ? "inside for every band" : covers === "some" ? "inside for some bands" : "a little further than last year's places reached"})` : ""}<br><em>Click for details</em>`;
    fill
      .bindTooltip(tip, { sticky: true })
      .on("click", () => onSelect(s.urn, "admissions"))
      .on("mouseover", () => highlightCatchment(s.urn))
      .on("mouseout", () => highlightCatchment(null));
    if (outer) outer.addTo(layer);
    fill.addTo(layer);
    let label = null;
    if (items.length <= 16) {
      label = L.marker(northOf(s.lat, s.lon, c.inner * MILE), {
        pane: "catchmentLabels",
        interactive: false,
        icon: L.divIcon({ className: "", iconSize: [0, 0], html: `<span class="catch-label" style="border-color:${color}">${esc(shortName(s.name))}</span>` }),
      }).addTo(layer);
    }
    shapes.set(s.urn, { fill, outer, label, base });
  });
  updateControl({ to, count: items.length, hidden });
}

/**
 * Which rings to draw. "covers" keeps the ones that reach the family's pin (topped up with the
 * nearest few so the map is never empty); with no pin it falls back to the nearest to the map centre.
 */
function scopeLines(all, home) {
  if (ui.linesScope === "all" || !all.length) return all;
  const from = home || (() => { const c = getMap().getCenter(); return { lat: c.lat, lon: c.lng }; })();
  const withDist = all.map((it) => ({ ...it, _d: home && it.s._dist != null ? it.s._dist : distanceMiles(from, it.s) }));
  const covering = home ? withDist.filter((it) => it._d <= it.c.outer) : [];
  if (covering.length >= LINES_MIN) return covering;
  const rest = withDist.filter((it) => !covering.includes(it)).sort((a, b) => a._d - b._d);
  return [...covering, ...rest.slice(0, Math.max(LINES_MIN, LINES_NEAR_MAX) - covering.length)];
}

export function highlightCatchment(urn) {
  if (ui.view === "heat") {
    // In heat view, hovering a school previews that school's own chance pattern over a faded surface.
    hoverRing?.remove();
    hoverRing = null;
    heatOverlay?.setOpacity(1);
    const s = urn != null ? state.byUrn.get(urn) : null;
    if (!s || !ui.visible || ui.phase === "off" || !inPhase(s)) return;
    const model = chanceModel(admissionsFor(s.urn) || { years: {} });
    if (model?.kind !== "distance") return;
    heatOverlay?.setOpacity(0.25);
    hoverRing = L.layerGroup([
      heatShapes(s, heatBands(model), { pane: "catchments", fillOpacity: 0.6 }),
      L.circleMarker([s.lat, s.lon], { pane: "catchmentLabels", radius: 1, opacity: 0, fillOpacity: 0, interactive: false })
        .bindTooltip(`${esc(shortName(s.name))}${isFaithSchool(s) ? " (faith school)" : ""}`, { permanent: true, direction: "top", offset: [0, -10] }),
    ]).addTo(layer);
    return;
  }
  shapes.forEach(({ fill, outer, label, base }, key) => {
    const on = urn != null && key === urn;
    const dim = urn != null && !on && shapes.has(urn);
    fill.setStyle(on ? { fillOpacity: 0.32, opacity: 1, weight: 3 } : dim ? { fillOpacity: base.fillOpacity * 0.3, opacity: 0.15, weight: base.weight } : base);
    outer?.setStyle(on ? { opacity: 1, weight: 3 } : dim ? { opacity: 0.15 } : { opacity: base.opacity, weight: base.weight });
    label?.setOpacity(dim ? 0.25 : 1);
  });
}
