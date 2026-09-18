import { SITE, $, $$, esc, store } from "./util.js";
import { state, setHome, on, loadLaIndex, ensureLas, lasAtPoints, ringPoints, laForDistrict, admissionsFor } from "./state.js";
import * as mapApi from "./map.js";
import { initList, renderList } from "./list.js";
import { renderSchool } from "./school.js";
import { renderLeague } from "./league.js";
import { renderArea } from "./area.js";
import { renderShortlist } from "./shortlist.js";
import { ofstedHeadline } from "./ofsted.js";
import { initCatchments, renderCatchments, setCatchmentsVisible, highlightCatchment } from "./catchments.js";
import { initPlanner } from "./planner.js";
import { initAds } from "./ads.js";
import { initAnalytics, track } from "./analytics.js";
import { initWelcome } from "./welcome.js";
import { initHelpMe } from "./helpme.js";

let activeView = "schools";
let planner = null;
let listScroll = 0;

function status(html) {
  $("#search-status").innerHTML = html;
}

/** Move to a hash, adding a history entry so the browser Back button walks back through the site. */
function go(hash, push) {
  const url = hash ? `#${hash}` : location.pathname + location.search;
  if (push && (location.hash.slice(1) || "") !== hash) history.pushState(null, "", url);
  else history.replaceState(null, "", url);
}

function showView(view, { push = true } = {}) {
  activeView = view;
  $$(".view").forEach((v) => { v.hidden = v.id !== `view-${view}`; });
  $$(".tabs [data-view]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === view)));
  if (view === "league") renderLeague(selectSchool);
  if (view === "area") renderArea();
  if (view === "shortlist") renderShortlist(selectSchool);
  if (view === "plan") planner?.render();
  if (view !== "school") {
    setCatchmentsVisible(true);
    go(view === "schools" ? "" : view, push);
    // Coming back from a school, put people where they were in the list.
    if (view === "schools" && listScroll) requestAnimationFrame(() => { window.scrollTo({ top: listScroll, behavior: "instant" }); listScroll = 0; });
    else if (view !== "schools") scrollPanelIntoView();
  }
}

/** On phones the window scrolls, not the panel, so a new page has to be brought into view itself. */
function scrollPanelIntoView() {
  const panel = $("#panel");
  panel.scrollTop = 0;
  if (panel.scrollHeight > panel.clientHeight + 4) return; // desktop: the panel is its own scroller
  const top = panel.getBoundingClientRect().top + window.scrollY;
  if (window.scrollY > top) window.scrollTo({ top, behavior: "instant" });
}

function selectSchool(urn, tab, { push = true } = {}) {
  const s = state.byUrn.get(Number(urn));
  listScroll = window.scrollY;
  showView("school", { push: false });
  scrollPanelIntoView();
  const initialTab = tab || (admissionsFor(urn) ? "admissions" : "overview");
  setCatchmentsVisible(false);
  go(`school=${urn}${s?._la ? `&la=${s._la}` : ""}&tab=${initialTab}`, push);
  renderSchool(urn, { tab: initialTab, onBack: () => history.back() });
  try { track("school_opened", { council_code: s?._la ?? null, phase: s?._class?.group ?? null, type_group: s?.type_group ?? null }); } catch { /* analytics must never break the site */ }
  try { track("tab_viewed", { tab: initialTab }); } catch { /* analytics must never break the site */ }
}

async function lookupPostcode(raw) {
  const pc = raw.replace(/\s+/g, "").toUpperCase();
  if (!pc) return null;
  const full = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(pc)}`);
  if (full.ok) {
    const { result } = await full.json();
    return { lat: result.latitude, lon: result.longitude, postcode: result.postcode, label: result.postcode, district: result.admin_district, districtCode: result.codes?.admin_district, country: result.country, precision: "postcode" };
  }
  const outcode = await fetch(`https://api.postcodes.io/outcodes/${encodeURIComponent(pc)}`);
  if (outcode.ok) {
    const { result } = await outcode.json();
    return { lat: result.latitude, lon: result.longitude, postcode: result.outcode, label: `${result.outcode} (district centre)`, district: [].concat(result.admin_district)[0], country: [].concat(result.country)[0], precision: "outcode" };
  }
  return null;
}

async function applyHome(home, { pan = true } = {}) {
  if (home.country && home.country !== "England") {
    if (pan) mapApi.panTo(home.lat, home.lon, 12);
    setHome(null);
    mapApi.setHome(null);
    store.set("home", null);
    status(`<strong>${esc(home.label)}</strong> is in ${esc(home.country)}. Schools in Reach covers England for now.`);
    return;
  }
  setHome(home);
  store.set("home", home);
  mapApi.setHome(home, async (pos) => {
    let extra = { label: "your pin" };
    try {
      const r = await fetch(`https://api.postcodes.io/postcodes?lon=${pos.lon}&lat=${pos.lat}&limit=1`);
      const j = await r.json();
      const hit = j.result?.[0];
      if (hit) extra = { label: `pin near ${hit.postcode}`, district: hit.admin_district, districtCode: hit.codes?.admin_district, country: hit.country };
    } catch { /* keep generic label */ }
    applyHome({ ...pos, ...extra, precision: "pin" }, { pan: false });
  });
  if (pan) mapApi.panTo(home.lat, home.lon, 14);

  const la = (home.districtCode && laForDistrict(home.districtCode)) || null;
  // Your own council first, then any council within about three miles (people often apply across borders).
  const nearby = await lasAtPoints([...ringPoints(home, 1.5), ...ringPoints(home, 3)]);
  await ensureLas([...(la ? [String(la.la_code)] : []), ...nearby].slice(0, 6));
  const council = la ? la.name : home.district;
  const hasCutoffs = la && state.laData.get(String(la.la_code))?.admissions;
  status(
    `Showing distances from <strong>${esc(home.label)}</strong>${council ? ` in ${esc(council)}` : ""}. ${home.precision === "pin" ? "" : "Drag the pin to your exact front door for a more precise distance."}` +
      (la && !hasCutoffs ? ` <span class="muted">We haven't added ${esc(council)} council's admissions cut-offs yet, so chances aren't shown for its schools.</span>` : ""),
  );
}

/** Look up a postcode and set it as home (shared by the search box and the welcome screen). */
async function applyPostcode(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return false;
  status("Looking up postcode…");
  try {
    const home = await lookupPostcode(raw);
    if (!home) {
      status(`Couldn't find “${esc(raw)}”. Check the postcode and try again.`);
      return false;
    }
    await applyHome(home);
    try { track("postcode_searched", { council_code: home.districtCode ?? null, in_england: home.country === "England" }); } catch { /* analytics must never break the site */ }
    if (activeView !== "school") showView("schools");
    return true;
  } catch {
    status("The postcode service didn't respond. Please try again.");
    return false;
  }
}

let loadTimer = 0;
function loadForView() {
  clearTimeout(loadTimer);
  loadTimer = setTimeout(async () => {
    const map = mapApi.getMap();
    if (map.getZoom() < SITE.loadZoom) {
      if (!state.schools.length) status("Zoom in or search a postcode to see schools.");
      return;
    }
    const b = map.getBounds();
    const c = map.getCenter();
    // Sample the view on a grid, centre first, so a council shows up once it covers a real part of the map.
    const points = [{ lat: c.lat, lon: c.lng }];
    for (let i = 0; i <= 3; i++) {
      for (let j = 0; j <= 3; j++) points.push({ lat: b.getSouth() + ((b.getNorth() - b.getSouth()) * (i + 0.5)) / 4, lon: b.getWest() + ((b.getEast() - b.getWest()) * (j + 0.5)) / 4 });
    }
    const codes = (await lasAtPoints(points)).slice(0, 8);
    if (!codes.length) return;
    await ensureLas(codes);
  }, 250);
}

function onSchoolsLoaded(codes) {
  codes.forEach((code) => {
    const ofsted = state.laData.get(code)?.ofsted;
    state.schools.filter((s) => s._la === code).forEach((s) => { s._ofsted = ofstedHeadline(ofsted?.schools?.[String(s.urn)]); });
  });
  mapApi.renderSchools(state.schools, (urn) => selectSchool(urn), highlightCatchment);
  renderList(selectSchool);
  renderCatchments();
  if (activeView === "league") renderLeague(selectSchool);
  if (activeView === "shortlist") renderShortlist(selectSchool);
  if (/Zoom in or search/.test($("#search-status").textContent)) status("");
}

async function main() {
  $$("[data-site-name]").forEach((el) => { el.textContent = SITE.name; });
  $$("[data-site-area]").forEach((el) => { el.textContent = `${SITE.area} beta`; });

  const map = mapApi.initMap();
  initCatchments(selectSchool);
  initAds();
  initAnalytics();

  // Analytics for interactions that live in other modules (school tabs, catchment controls).
  document.addEventListener("click", (e) => {
    const tabBtn = e.target?.closest?.("[data-tab]");
    if (tabBtn) { try { track("tab_viewed", { tab: tabBtn.dataset.tab }); } catch { /* analytics must never break the site */ } }
  });
  let heatView = "heat";
  const catchCtrl = document.querySelector(".catch-control");
  catchCtrl?.addEventListener("click", () => {
    const pressedView = catchCtrl.querySelector('[data-view-mode][aria-pressed="true"]');
    if (pressedView) heatView = pressedView.dataset.viewMode;
    const phase = catchCtrl.querySelector('[data-catch][aria-pressed="true"]')?.dataset.catch || "off";
    try { track("heatmap_mode_changed", { phase, view: heatView }); } catch { /* analytics must never break the site */ }
  });
  initList(selectSchool);
  planner = initPlanner({ selectSchool });
  $("#shortlist-count").textContent = state.shortlist.size || "";
  $$(".tabs [data-view]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

  // Back and forward: rebuild the view the address bar now describes, without adding more history.
  window.addEventListener("popstate", async () => {
    const p = new URLSearchParams(location.hash.slice(1));
    const urn = p.get("school");
    if (urn) {
      if (!state.byUrn.has(Number(urn))) await ensureLas([p.get("la") || "204"]);
      selectSchool(Number(urn), p.get("tab"), { push: false });
      return;
    }
    const view = location.hash.slice(1);
    showView(["league", "area", "shortlist", "plan"].includes(view) ? view : "schools", { push: false });
  });

  const las = await loadLaIndex();
  if (!las.length) {
    status("School data is still being prepared. Please check back shortly.");
    return;
  }

  on("schools", onSchoolsLoaded);
  on("home", () => {
    renderList(selectSchool);
    renderCatchments();
    if (activeView === "area") renderArea();
    if (activeView === "league") renderLeague(selectSchool);
    if (activeView === "shortlist") renderShortlist(selectSchool);
    if (activeView === "school") {
      const params = new URLSearchParams(location.hash.slice(1));
      if (params.get("school")) renderSchool(params.get("school"), { tab: params.get("tab") || "admissions", onBack: () => history.back() });
    }
  });
  on("shortlist", () => {
    $("#shortlist-count").textContent = state.shortlist.size || "";
    if (activeView === "shortlist") renderShortlist(selectSchool);
  });
  map.on("moveend", () => {
    loadForView();
    if (!state.home && activeView === "schools") renderList(selectSchool);
  });

  $("#search").addEventListener("submit", (e) => {
    e.preventDefault();
    applyPostcode($("#postcode").value);
  });

  async function reverseGeocode(point) {
    let extra = { label: "your location" };
    try {
      const r = await fetch(`https://api.postcodes.io/postcodes?lon=${point.lon}&lat=${point.lat}&limit=1`);
      const j = await r.json();
      const hit = j.result?.[0];
      if (hit) extra = { label: "your location", district: hit.admin_district, districtCode: hit.codes?.admin_district, country: hit.country };
    } catch { /* distances still work without the council */ }
    return extra;
  }

  /** Ask the browser for the device location. Resolves true once a home is set. Gentle mode doesn't nag on refusal. */
  async function locateFromBrowser(gentle = false) {
    if (!navigator.geolocation) {
      if (!gentle) status("Your browser can't share its location, so please type a postcode instead.");
      return false;
    }
    if (!gentle) status("Finding your location…");
    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const point = { lat: pos.coords.latitude, lon: pos.coords.longitude };
          const extra = await reverseGeocode(point);
          await applyHome({ ...point, ...extra, precision: "pin" });
          resolve(true);
        },
        () => {
          if (gentle) store.set("geoAsked", true);
          else status("Location permission was declined — that's fine, you can type a postcode instead.");
          resolve(false);
        },
        { enableHighAccuracy: true, timeout: 8000 },
      );
    });
  }

  /** No precise location: start near the visitor's IP if it's in England, else London. */
  async function startNearIp() {
    try {
      const j = await (await fetch("https://ipwho.is/")).json();
      const lat = j.latitude, lon = j.longitude;
      if (j.success !== false && typeof lat === "number" && typeof lon === "number" && lat > 49.9 && lat < 55.9 && lon > -6 && lon < 2) {
        mapApi.panTo(lat, lon, 13);
        status(`We've started near ${esc(j.city || "you")}. Type your postcode for exact distances.`);
        return;
      }
    } catch { /* fall through to London */ }
    mapApi.panTo(51.5074, -0.1278, 12);
    status("Type your postcode to see schools near you.");
  }

  $("#locate").addEventListener("click", () => locateFromBrowser());

  // Callbacks for the welcome screen and the "Help me!" guide.
  initHelpMe({ selectSchool, applyPostcode });
  const useMyLocation = async () => {
    const ok = await locateFromBrowser(false);
    if (!ok) store.set("geoAsked", true);
    return ok;
  };
  const openWelcome = initWelcome({ applyPostcode, useMyLocation, explore: () => startNearIp() });

  const params = new URLSearchParams(location.hash.slice(1));
  const saved = store.get("home", null);
  if (saved?.lat) {
    $("#postcode").value = saved.precision === "postcode" ? saved.postcode : "";
    await applyHome(saved, { pan: !params.get("school") });
  } else if (!params.get("school") && !store.get("welcomed")) {
    // First visit: show the welcome screen; the location prompt waits until they choose.
    openWelcome();
    loadForView();
  } else if (!params.get("school") && !store.get("geoAsked")) {
    status("We'll use your location to show nearby schools. You can type a postcode instead at any time.");
    if (!(await locateFromBrowser(true))) await startNearIp();
    loadForView();
  } else {
    loadForView();
  }

  if (params.get("school")) {
    const urn = Number(params.get("school"));
    if (!state.byUrn.has(urn)) await ensureLas([params.get("la") || "204"]);
    const s = state.byUrn.get(urn);
    if (s?.lat != null) mapApi.panTo(s.lat, s.lon, 14);
    selectSchool(urn, params.get("tab"));
  } else if (["league", "area", "shortlist", "plan"].includes(location.hash.slice(1))) {
    showView(location.hash.slice(1), { push: false });
  }
}

main();
