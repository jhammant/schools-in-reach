export const SITE = {
  name: "Schools in Reach",
  area: "England",
  dataBase: "data/",
  center: [51.5495, -0.059],
  zoom: 13,
  // Schools load council by council once the map is zoomed in this far.
  loadZoom: 11.5,
};

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);

export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const isDark = () => cssVar("color-scheme") === "dark";
export const SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];

const MILE_M = 1609.344;
export const MILE = MILE_M;

/** Great-circle distance in miles. Within 0.1% of the British National Grid straight line councils use. */
export function milesBetween(a, b) {
  const R = 6371008.8;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return (2 * R * Math.asin(Math.sqrt(h))) / MILE_M;
}

export const fmt = {
  mi: (v, dp = 2) => (v == null || Number.isNaN(v) ? "–" : `${Number(v).toFixed(dp)} mi`),
  pct: (v, dp = 0) => (v == null || v === "" ? "–" : `${Number(v).toFixed(dp)}%`),
  num: (v, dp = 0) => (v == null || v === "" ? "–" : Number(v).toLocaleString("en-GB", { maximumFractionDigits: dp })),
  money: (v) => (v == null || v === "" ? "–" : `£${Math.round(Number(v)).toLocaleString("en-GB")}`),
  signed: (v, dp = 2) => (v == null || v === "" ? "–" : `${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(dp)}`),
  date: (v) => {
    if (!v) return "–";
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  },
};

export async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json();
}

export const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable: shortlist just won't persist */
    }
  },
};

/** Turn a snake_case or camelCase data key into a readable label. */
const TERMS = {
  fsm: "free school meals", eal: "EAL", sen: "SEN", ehcp: "EHCP", fte: "FTE", aps: "APS", ebacc: "EBacc", alevel: "A level",
  he: "higher education", imd: "IMD", idaci: "IDACI", lsoa: "LSOA", gp: "GP", pct: "%", ks3: "KS3", ks4: "KS4", ks5: "KS5", ks2: "KS2", ks1: "KS1",
  qts: "QTS", sen_support: "SEN support", fe: "further education",
};

export function humanize(key) {
  const words = String(key)
    .replace(/([a-z])([A-Z])/g, "$1_$2")
    .split(/_+/)
    .filter(Boolean)
    .map((w) => TERMS[w.toLowerCase()] ?? w.toLowerCase());
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function pointInGeometry(lon, lat, geometry) {
  const inRing = (ring) => {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  };
  const inPolygon = (rings) => inRing(rings[0]) && !rings.slice(1).some(inRing);
  if (geometry.type === "Polygon") return inPolygon(geometry.coordinates);
  if (geometry.type === "MultiPolygon") return geometry.coordinates.some(inPolygon);
  return false;
}
