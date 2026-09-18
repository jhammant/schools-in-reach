import { SITE, MILE, cssVar, esc, isDark } from "./util.js";
import { GROUP_META } from "./state.js";

/* global L, protomapsL */

// UK-wide basemap on its own host (CORS + range requests), so site deploys never re-copy the 3 GB file.
const TILES_URL = "https://tiles.schoolsinreach.com/tiles/uk.pmtiles";

let map;
let schoolLayer;
let ringLayer;
let homeMarker;
let markerRenderer;
const markers = new Map();

export function initMap() {
  map = L.map("map", { zoomControl: true, zoomSnap: 0.5, minZoom: 6, maxZoom: 18, maxBounds: [[49.5, -9], [61, 2.2]] }).setView(SITE.center, SITE.zoom);
  markerRenderer = L.canvas({ padding: 0.5 });
  // Self-hosted Protomaps vector basemap (one PMTiles file, read with HTTP range requests): no API key or per-tile cost.
  // To scale, upload the file to a CDN bucket and point TILES_URL at it.
  protomapsL
    .leafletLayer({
      url: TILES_URL,
      flavor: isDark() ? "dark" : "light",
      lang: "en",
      maxDataZoom: 15,
      attribution: '<a href="https://protomaps.com">Protomaps</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    })
    .addTo(map);
  map.createPane("rings").style.zIndex = 390;
  schoolLayer = L.layerGroup().addTo(map);
  ringLayer = L.layerGroup().addTo(map);
  addLegend();
  return map;
}

export const getMap = () => map;

function addLegend() {
  const legend = L.control({ position: "bottomleft" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "map-legend");
    div.innerHTML = [
      ["--s1", "Primary"],
      ["--s2", "Secondary"],
      ["--s3", "Nursery, 16+, all-through, special"],
    ]
      .map(([c, l]) => `<div><span class="swatch" style="background:${cssVar(c)}"></span>${l}</div>`)
      .join("") + `<div><span class="swatch" style="background:transparent;box-shadow:0 0 0 2px ${cssVar("--text-secondary")}"></span>Hollow: independent</div>`;
    return div;
  };
  legend.addTo(map);
}

export function renderSchools(schools, onSelect, onHover = () => {}) {
  schoolLayer.clearLayers();
  markers.clear();
  schools.forEach((s) => {
    if (s.lat == null) return;
    const color = cssVar(GROUP_META[s._class.group]?.color || "--s3");
    const marker = L.circleMarker([s.lat, s.lon], {
      renderer: markerRenderer,
      radius: 7,
      color: s._class.independent ? color : cssVar("--surface-1"),
      weight: s._class.independent ? 3 : 2,
      fillColor: s._class.independent ? cssVar("--surface-1") : color,
      fillOpacity: 1,
    })
      .bindTooltip(esc(s.name), { direction: "top", offset: [0, -6] })
      .on("click", () => onSelect(s.urn))
      .on("mouseover", () => onHover(s.urn))
      .on("mouseout", () => onHover(null));
    marker.addTo(schoolLayer);
    markers.set(s.urn, marker);
  });
}

export function filterMarkers(visibleUrns) {
  markers.forEach((m, urn) => {
    const show = visibleUrns.has(urn);
    if (show && !schoolLayer.hasLayer(m)) m.addTo(schoolLayer);
    if (!show && schoolLayer.hasLayer(m)) schoolLayer.removeLayer(m);
  });
}

export function focusSchool(school) {
  const m = markers.get(school.urn);
  markers.forEach((mk) => mk.setRadius(7));
  if (m) {
    m.setRadius(11);
    m.bringToFront();
  }
}

export function setHome(home, onMove) {
  if (homeMarker) homeMarker.remove();
  if (!home) return;
  const icon = L.divIcon({
    className: "",
    iconSize: [0, 0],
    html: `<div class="home-pin"><svg viewBox="0 0 30 38" aria-hidden="true"><path d="M15 1C7.3 1 1 7.2 1 14.9 1 25.3 15 37 15 37s14-11.7 14-22.1C29 7.2 22.7 1 15 1z" fill="${cssVar("--text-primary")}" stroke="${cssVar("--surface-1")}" stroke-width="2"/><circle cx="15" cy="14.5" r="5" fill="${cssVar("--surface-1")}"/></svg></div>`,
  });
  homeMarker = L.marker([home.lat, home.lon], { icon, draggable: true, zIndexOffset: 2000, title: "Your location (drag to your exact home)" })
    .bindTooltip("Drag me to your exact front door", { direction: "top", offset: [0, -40] })
    .addTo(map);
  homeMarker.on("dragend", () => {
    const p = homeMarker.getLatLng();
    onMove({ lat: p.lat, lon: p.lng });
  });
}

// Five-ish label bearings spread around the lower arc keep near-identical rings readable.
const bearing = (i, n) => 150 + (n <= 1 ? 30 : (i * 120) / (n - 1));

function offset(lat, lon, meters, deg) {
  const R = 6371008.8;
  const br = (deg * Math.PI) / 180;
  const p1 = (lat * Math.PI) / 180;
  const l1 = (lon * Math.PI) / 180;
  const dr = meters / R;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(dr) + Math.cos(p1) * Math.sin(dr) * Math.cos(br));
  const l2 = l1 + Math.atan2(Math.sin(br) * Math.sin(dr) * Math.cos(p1), Math.cos(dr) - Math.sin(p1) * Math.sin(p2));
  return [(p2 * 180) / Math.PI, (l2 * 180) / Math.PI];
}

function circlePoints(lat, lon, miles, steps = 96) {
  return Array.from({ length: steps }, (_, i) => offset(lat, lon, miles * MILE, (i * 360) / steps));
}

/** A school's chance bands as rings (each class is a disc with the next class's disc cut out, so colours never stack). */
export function heatShapes(school, heat, { pane = "rings", fillOpacity = 0.55 } = {}) {
  const group = L.layerGroup();
  heat.forEach((band, i) => {
    const inner = heat[i + 1]?.miles || 0;
    if (band.miles - inner < 0.005) return;
    const outerRing = circlePoints(school.lat, school.lon, band.miles);
    const shape = inner > 0 ? [outerRing, circlePoints(school.lat, school.lon, inner).reverse()] : [outerRing];
    L.polygon(shape, { pane, stroke: false, fillColor: band.color, fillOpacity, interactive: false }).addTo(group);
  });
  return group;
}

export function showRings(school, rings, { home, heat = [] } = {}) {
  ringLayer.clearLayers();
  const bounds = L.latLngBounds([[school.lat, school.lon]]);
  if (heat.length) {
    heatShapes(school, heat).addTo(ringLayer);
    bounds.extend(L.latLng(school.lat, school.lon).toBounds(2 * Math.max(...heat.map((b) => b.miles)) * MILE));
  }
  if (!heat.length && rings.length) {
    const minR = Math.min(...rings.map((r) => r.miles));
    L.circle([school.lat, school.lon], { pane: "rings", radius: minR * MILE, stroke: false, fillColor: cssVar("--accent"), fillOpacity: 0.1, interactive: false }).addTo(ringLayer);
  }
  rings.forEach((r, i) => {
    L.circle([school.lat, school.lon], { pane: "rings", radius: r.miles * MILE, color: r.color, weight: heat.length ? 1.5 : 2, opacity: heat.length ? 0.9 : 1, fill: false })
      .bindTooltip(`Furthest offer: ${esc(r.label)} mi`, { sticky: true })
      .addTo(ringLayer);
    L.marker(offset(school.lat, school.lon, r.miles * MILE, bearing(i, rings.length)), {
      interactive: false,
      icon: L.divIcon({ className: "", iconSize: [0, 0], html: `<span class="ring-label" style="border-color:${r.color}">${esc(r.label)}</span>` }),
    }).addTo(ringLayer);
    bounds.extend(L.latLng(school.lat, school.lon).toBounds(2 * r.miles * MILE));
  });
  if (home) {
    L.polyline([[home.lat, home.lon], [school.lat, school.lon]], { pane: "rings", color: cssVar("--text-primary"), weight: 2, dashArray: "6 5", interactive: false }).addTo(ringLayer);
    bounds.extend([home.lat, home.lon]);
  }
  map.fitBounds(bounds.pad(0.08), { maxZoom: 16 });
}

export function clearRings() {
  ringLayer.clearLayers();
}

export function panTo(lat, lon, zoom = 15) {
  map.setView([lat, lon], Math.max(map.getZoom(), zoom));
}
