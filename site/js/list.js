import { $, esc, fmt, cssVar } from "./util.js";
import { state, matchesPhase, GROUP_META, admissionsFor, hasAdmissionsData, laName, isSelectiveSchool } from "./state.js";
import { reachPill, reachStatus } from "./admissions.js";
import { highlightCatchment, setCatchmentPhase } from "./catchments.js";
import { filterMarkers, getMap } from "./map.js";

// Long lists slow the panel down; the map still shows every match.
const MAX_ROWS = 200;

const filters = { text: "", phase: "", sector: "", gender: "", faith: "", reach: "", selective: "" };

export function initList(onSelect) {
  const bind = (id, key) =>
    $(id).addEventListener("input", (e) => {
      filters[key] = e.target.value.trim();
      renderList(onSelect);
    });
  bind("#filter-text", "text");
  bind("#filter-phase", "phase");
  bind("#filter-sector", "sector");
  bind("#filter-gender", "gender");
  bind("#filter-faith", "faith");
  bind("#filter-selective", "selective");
  bind("#filter-reach", "reach");
  $("#filter-phase").addEventListener("input", (e) => setCatchmentPhase(e.target.value));
  $("#school-list").addEventListener("mouseover", (e) => {
    const li = e.target.closest("[data-urn]");
    highlightCatchment(li ? Number(li.dataset.urn) : null);
  });
  $("#school-list").addEventListener("mouseleave", () => highlightCatchment(null));
  $("#school-list").addEventListener("click", (e) => {
    const li = e.target.closest("[data-urn]");
    if (li) onSelect(Number(li.dataset.urn));
  });
  $("#school-list").addEventListener("keydown", (e) => {
    const li = e.target.closest("[data-urn]");
    if (li && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      onSelect(Number(li.dataset.urn));
    }
  });
}

function visible(s) {
  if (s._class.college && filters.phase !== "post16") return false;
  if (filters.text && !s.name.toLowerCase().includes(filters.text.toLowerCase())) return false;
  if (!matchesPhase(s, filters.phase)) return false;
  if (filters.sector === "state" && s._class.independent) return false;
  if (filters.sector === "independent" && !s._class.independent) return false;
  if (filters.gender && (s.gender || "Mixed") !== filters.gender) return false;
  const faith = s.religious_character && !/does not apply|none|not applicable/i.test(s.religious_character);
  if (filters.faith === "none" && faith) return false;
  if (filters.faith === "faith" && !faith) return false;
  if (filters.selective === "selective" && !isSelectiveSchool(s)) return false;
  if (filters.selective === "non" && isSelectiveSchool(s)) return false;
  if (filters.reach && state.home) {
    if (s._class.independent) return false;
    if (!hasAdmissionsData(s)) return false;
    const rec = admissionsFor(s.urn);
    const r = rec ? reachStatus(rec, s._dist) : null;
    // No published cut-off for a state primary/secondary means it wasn't oversubscribed.
    const likely = r ? ["in", "some", "spare"].includes(r.status) : ["primary", "secondary", "allthrough"].includes(s._class.group);
    if (!likely) return false;
  }
  return true;
}

export function renderList(onSelect) {
  const matching = state.schools.filter(visible);
  filterMarkers(new Set(matching.map((s) => s.urn)));
  const bounds = getMap()?.getBounds();
  // Once the map has been moved away from home, the list should show what you're looking at.
  const awayFromHome = !!(state.home && bounds && !bounds.contains([state.home.lat, state.home.lon]));
  let rows = matching;
  if (state.home && !awayFromHome) {
    rows = [...matching].sort((a, b) => (a._dist ?? 99) - (b._dist ?? 99));
  } else {
    const centre = bounds?.getCenter();
    rows = matching
      .filter((s) => s.lat != null && (!bounds || bounds.contains([s.lat, s.lon])))
      .sort((a, b) => (centre ? Math.hypot(a.lat - centre.lat, a.lon - centre.lng) - Math.hypot(b.lat - centre.lat, b.lon - centre.lng) : a.name.localeCompare(b.name)));
  }
  const shown = rows.slice(0, MAX_ROWS);
  const manyLas = new Set(shown.map((s) => s._la)).size > 1;

  const welcome = $("#welcome");
  if (welcome) welcome.hidden = !!state.home;

  $("#list-summary").innerHTML = state.home && !awayFromHome
    ? `${matching.filter((s) => s._dist != null && s._dist <= 5).length} schools within 5 miles of ${esc(state.home.label)}, nearest first${rows.length > MAX_ROWS ? ` (showing the closest ${MAX_ROWS})` : ""}.`
    : awayFromHome
      ? `${rows.length ? `${rows.length} schools where you're looking${rows.length > MAX_ROWS ? ` (showing ${MAX_ROWS})` : ""}.` : "Still loading schools for this area — zoom in a little if nothing appears."} <button type="button" class="link-btn" data-action="home-view">Back to ${esc(state.home.label)}</button>`
      : `${rows.length} schools in this map view${rows.length > MAX_ROWS ? ` (showing ${MAX_ROWS})` : ""}. Search a postcode to sort them by distance and see your chances.`;

  $("#school-list").innerHTML = shown.length
    ? shown
        .map((s) => {
          const meta = GROUP_META[s._class.group];
          const color = cssVar(meta?.color || "--s3");
          const bits = [meta?.label, s._class.independent ? "Independent" : s.type_group, s.gender && s.gender !== "Mixed" ? s.gender : null, s.age_low != null && s.age_high != null ? `Ages ${s.age_low}–${s.age_high}` : null, manyLas ? laName(s._la) : null].filter(Boolean);
          const ofsted = s._ofsted ? `<span class="pill plain">Ofsted: ${esc(s._ofsted)}</span>` : "";
          const faith = s.religious_character && !/does not apply|none|not applicable/i.test(s.religious_character) ? `<span class="pill plain">${esc(s.religious_character)}</span>` : "";
          const selective = isSelectiveSchool(s) ? `<span class="pill plain" title="Places depend on an entrance test, usually taken in September of Year 6">Grammar · entrance test</span>` : "";
          const rec = admissionsFor(s.urn);
          return `
            <li class="school-item" data-urn="${s.urn}" tabindex="0">
              <span class="dot ${s._class.independent ? "independent" : ""}" style="background:${color};--dot:${color}"></span>
              <div>
                <h3>${esc(s.name)}</h3>
                <div class="meta">${esc(bits.join(" · "))}</div>
                <div class="pills">${reachPill(rec, s._dist, s)}${selective}${ofsted}${faith}</div>
              </div>
              <div class="dist">${state.home && s._dist != null ? fmt.mi(s._dist) : ""}</div>
            </li>`;
        })
        .join("")
    : `<li class="empty">${state.schools.length ? "No schools match these filters here." : "Zoom in or search a postcode to load schools."}</li>`;
}
