import { SITE, getJSON, milesBetween, store, pointInGeometry } from "./util.js";

const cache = new Map();

/** Fetch a data file once. Optional files resolve to null so a missing dataset hides its section instead of breaking the page. */
export function load(name) {
  if (!cache.has(name)) {
    cache.set(
      name,
      getJSON(SITE.dataBase + name).catch((err) => {
        console.warn(`[data] ${err.message}`);
        return null;
      }),
    );
  }
  return cache.get(name);
}

/** A file inside one local authority's folder, e.g. laFile("204", "ofsted.json"). */
export const laFile = (laCode, name) => load(`la/${laCode}/${name}`);

export const state = {
  las: [], // index of English local authorities
  laByCode: new Map(),
  laByDistrict: new Map(), // ONS district code -> DfE LA code, from the official lookup
  laData: new Map(), // la_code -> { admissions, ofsted }
  schools: [],
  byUrn: new Map(),
  home: null, // { lat, lon, label, postcode?, district? }
  shortlist: new Set(store.get("shortlist", [])),
  // urn -> la_code, so a shortlisted school can be reloaded after a refresh anywhere on the map.
  shortlistLa: store.get("shortlistLa", {}),
};

const listeners = new Map();
export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
}
export function emit(event, payload) {
  (listeners.get(event) || []).forEach((fn) => fn(payload));
}

export async function loadLaIndex() {
  const [index, geometry] = await Promise.all([load("england/las.json"), load("england/la_geometry.json")]);
  state.las = index?.las || [];
  state.las.forEach((la) => state.laByCode.set(String(la.la_code), la));
  // School-derived district lists include schools a council runs outside its own borders, so prefer the ONS mapping.
  Object.entries(geometry?.las || {}).forEach(([code, g]) => (g.lad_codes || []).forEach((lad) => state.laByDistrict.set(lad, code)));
  return state.las;
}

/** Local authorities whose school bounding box overlaps a lat/lon box, nearest first. */
export function lasInBounds(south, west, north, east, centre) {
  const hits = state.las.filter((la) => {
    const [w, s, e, n] = la.bbox || [];
    return la.bbox && w <= east && e >= west && s <= north && n >= south;
  });
  if (centre) hits.sort((a, b) => milesBetween(centre, { lat: a.centroid[0], lon: a.centroid[1] }) - milesBetween(centre, { lat: b.centroid[0], lon: b.centroid[1] }));
  return hits.map((la) => String(la.la_code));
}

export function lasNear(point, miles = 3) {
  const dLat = miles / 69.05;
  const dLon = miles / (Math.cos((point.lat * Math.PI) / 180) * 69.17);
  return lasInBounds(point.lat - dLat, point.lon - dLon, point.lat + dLat, point.lon + dLon, point);
}

let boundaries = null;

/** Simplified council boundaries with a bounding box per feature, for point-in-council lookups. */
async function loadBoundaries() {
  if (!boundaries) {
    boundaries = load("england/la_boundaries_lite.geojson").then((fc) =>
      (fc?.features || []).map((f) => {
        let w = 180, s = 90, e = -180, n = -90;
        const walk = (c) => (typeof c[0] === "number" ? ((w = Math.min(w, c[0])), (e = Math.max(e, c[0])), (s = Math.min(s, c[1])), (n = Math.max(n, c[1]))) : c.forEach(walk));
        walk(f.geometry.coordinates);
        return { code: String(f.properties.la_code), geometry: f.geometry, bbox: [w, s, e, n] };
      }),
    );
  }
  return boundaries;
}

/** Councils containing any of these points, in order of first hit. Falls back to school bounding boxes if boundaries are unavailable. */
export async function lasAtPoints(points) {
  const shapes = await loadBoundaries();
  if (!shapes.length) {
    const p = points[0];
    return p ? lasNear(p, 1) : [];
  }
  const found = [];
  points.forEach(({ lat, lon }) => {
    const hit = shapes.find((b) => lon >= b.bbox[0] && lon <= b.bbox[2] && lat >= b.bbox[1] && lat <= b.bbox[3] && pointInGeometry(lon, lat, b.geometry));
    if (hit && !found.includes(hit.code)) found.push(hit.code);
  });
  return found;
}

/** The point itself plus a ring of points `miles` away: which councils matter for someone living here. */
export function ringPoints(point, miles, steps = 8) {
  const dLat = miles / 69.05;
  const dLon = miles / (Math.cos((point.lat * Math.PI) / 180) * 69.17);
  return [point, ...Array.from({ length: steps }, (_, i) => {
    const a = (i * 2 * Math.PI) / steps;
    return { lat: point.lat + dLat * Math.cos(a), lon: point.lon + dLon * Math.sin(a) };
  })];
}

/** The council of the loaded school nearest a point: a cheap stand-in for "which council is this". */
export function nearestLoadedLa(point) {
  let best = null;
  let bestD = Infinity;
  for (const s of state.schools) {
    if (s.lat == null) continue;
    const d = (s.lat - point.lat) ** 2 + ((s.lon - point.lon) * Math.cos((point.lat * Math.PI) / 180)) ** 2;
    if (d < bestD) { bestD = d; best = s._la; }
  }
  return best;
}

export const laForDistrict = (ladCode) => {
  const code = state.laByDistrict.get(ladCode);
  if (code) return state.laByCode.get(code) || null;
  return state.las.find((la) => (la.lad_codes || []).includes(ladCode)) || null;
};

const inflight = new Map();

/** Load schools, admissions and Ofsted for these local authorities (once each) and merge them into state. */
export async function ensureLas(codes) {
  const wanted = [...new Set(codes.map(String))].filter((c) => state.laByCode.has(c) && !state.laData.has(c));
  if (!wanted.length) return false;
  await Promise.all(
    wanted.map((code) => {
      if (!inflight.has(code)) {
        inflight.set(
          code,
          Promise.all([laFile(code, "schools.json"), laFile(code, "admissions.json"), laFile(code, "ofsted.json")]).then(([schools, admissions, ofsted]) => {
            const rows = Array.isArray(schools) ? schools : schools?.schools || [];
            rows.forEach((s) => {
              s.urn = Number(s.urn);
              s._la = code;
              s._class = classify(s);
              if (s._class.hidden) return;
              if (state.home && s.lat != null) s._dist = milesBetween(state.home, s);
              if (!state.byUrn.has(s.urn)) {
                state.byUrn.set(s.urn, s);
                state.schools.push(s);
              }
            });
            // A file with no schools in it (e.g. a council that publishes nothing) counts as no data.
            const hasRows = admissions && (Object.keys(admissions.secondary || {}).length || Object.keys(admissions.primary || {}).length);
            state.laData.set(code, { admissions: hasRows ? admissions : null, ofsted, schoolCount: rows.length });
          }),
        );
      }
      return inflight.get(code);
    }),
  );
  emit("schools", wanted);
  return true;
}

export function setHome(home) {
  state.home = home;
  state.schools.forEach((s) => {
    s._dist = home && s.lat != null ? milesBetween(home, s) : null;
  });
  emit("home", home);
}

export function toggleShortlist(urn) {
  const key = Number(urn);
  if (state.shortlist.has(key)) {
    state.shortlist.delete(key);
    delete state.shortlistLa[key];
  } else {
    state.shortlist.add(key);
    const la = state.byUrn.get(key)?._la;
    if (la) state.shortlistLa[key] = la;
  }
  store.set("shortlist", [...state.shortlist]);
  store.set("shortlistLa", state.shortlistLa);
  emit("shortlist", state.shortlist);
}

/** Classify a school for filters, colours and which results to show. */
export function classify(s) {
  const phase = (s.phase || "").toLowerCase();
  const typeGroup = (s.type_group || "").toLowerCase();
  const type = (s.type || "").toLowerCase();
  const independent = typeGroup.includes("independent");
  let group;
  if (typeGroup.includes("special") || type.includes("special") || type.includes("pupil referral") || type.includes("alternative provision")) group = "special";
  else if (phase === "nursery") group = "nursery";
  else if (phase.includes("primary")) group = "primary";
  else if (phase.includes("secondary")) group = "secondary";
  else if (phase.includes("all-through") || phase.includes("all through")) group = "allthrough";
  else if (phase.includes("16")) group = "post16";
  else {
    const lo = Number(s.age_low);
    const hi = Number(s.age_high);
    if (hi && hi <= 11) group = "primary";
    else if (lo >= 16) group = "post16";
    else if (lo >= 10) group = "secondary";
    else if (hi >= 16) group = "allthrough";
    else group = "primary";
  }
  const hasSixth = s.sixth_form === true || /has a sixth form/i.test(String(s.sixth_form || "")) || Number(s.age_high) >= 18;
  // Not schools a parent is choosing between: universities, online providers and other odd register entries.
  const hidden = typeGroup.includes("universities") || /higher education|online provider|miscellaneous|other government department|offshore|overseas|service children/.test(type);
  // FE colleges only appear when looking for sixth form / 16+ options.
  const college = typeGroup.includes("colleges");
  if (college) group = "post16";
  return { group, independent, hasSixth, hidden, college };
}

export const GROUP_META = {
  primary: { label: "Primary", color: "--s1" },
  secondary: { label: "Secondary", color: "--s2" },
  allthrough: { label: "All-through", color: "--s3" },
  post16: { label: "Sixth form / 16+", color: "--s3" },
  nursery: { label: "Nursery school", color: "--s3" },
  special: { label: "Special school", color: "--s3" },
};

/** Faith schools usually rank faith criteria before distance, so a distance-only chance can mislead. */
export const isFaithSchool = (s) => Boolean(s?.religious_character) && !/does not apply|^none$|not applicable/i.test(s.religious_character);

export function matchesPhase(s, wanted) {
  if (!wanted) return true;
  const { group, hasSixth } = s._class;
  if (wanted === "primary") return group === "primary" || group === "allthrough";
  if (wanted === "secondary") return group === "secondary" || group === "allthrough";
  if (wanted === "post16") return group === "post16" || hasSixth;
  return group === wanted;
}

export function admissionsFor(urn) {
  const s = state.byUrn.get(Number(urn));
  const a = s && state.laData.get(s._la)?.admissions;
  if (!a) return null;
  const key = String(urn);
  if (a.secondary?.[key]) return { phase: "secondary", ...a.secondary[key] };
  if (a.primary?.[key]) return { phase: "primary", ...a.primary[key] };
  return null;
}

/** Whether we hold any admissions allocation data for a school's council. */
export const hasAdmissionsData = (s) => Boolean(s && state.laData.get(s._la)?.admissions);

export const laName = (code) => state.laByCode.get(String(code))?.name || "this council";
