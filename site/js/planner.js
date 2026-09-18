import { $, $$, esc, fmt, store } from "./util.js";
import { state, on, emit, admissionsFor, ensureLas, laName } from "./state.js";
import { chanceModel, chanceAt, distances, allOffered, groupsOf, RECENCY, latestYear } from "./admissions.js";
import { renderTimeline } from "./timeline.js";

/* ================================================================== */
/* Pure maths — DOM-free, unit-tested in tests/planner-math.mjs        */
/* ================================================================== */

/** Sibling priority comes before distance in admissions rules, so treat it as near-certain. */
export const SIBLING_CHANCE = 0.95;

// Beyond this many miles a published "cut-off" means everyone in the band was offered (admissions.js convention).
const OPEN_BAND_MILES = 3;

const yearsOf = (rec) => Object.keys(rec?.years || {}).map(Number).sort((a, b) => a - b);

/**
 * chanceModel(rec) rebuilt from one band's cut-offs only (bands A–E from a test).
 * band null/"unsure", or a base model that isn't distance-based, passes through unchanged.
 * Falls back to the base model when the band has no usable cut-offs.
 */
export function modelForBand(rec, band) {
  const base = chanceModel(rec);
  if (!band || band === "unsure" || !base || base.kind !== "distance") return base;
  const ys = yearsOf(rec);
  const latest = ys.at(-1);
  const points = [];
  ys.forEach((yr) => {
    const y = rec.years[yr];
    if (y.allocation === "random_by_zone") return;
    const w = RECENCY ** (latest - yr);
    if (y.non_preference_offers > 0) {
      points.push({ yr, cutoff: Infinity, w });
      return;
    }
    if (!groupsOf(y).includes(band)) return;
    let cutoff = distances(y)[band];
    if (allOffered(y).includes(band) || (cutoff != null && cutoff > OPEN_BAND_MILES)) cutoff = Infinity;
    if (cutoff == null) return;
    points.push({ yr, cutoff, w });
  });
  if (!points.length) return base;
  points.sort((a, b) => b.cutoff - a.cutoff);
  const total = points.reduce((a, p) => a + p.w, 0);
  const finite = points.map((p) => p.cutoff).filter(Number.isFinite);
  const reach = finite.length ? Math.min(OPEN_BAND_MILES, Math.max(...finite) * 1.25) : OPEN_BAND_MILES;
  return { kind: "distance", points, total, reach, from: ys[0], to: latest, faith: rec.years[latest].allocation === "faith_then_distance" };
}

/**
 * Scale a distance model for demand: delta is a fraction in [-0.2, 0.2].
 * More applicants means the same places run out sooner, so finite cut-offs shrink
 * by sqrt(1/(1+delta)) — the geometric scaling of how far a fixed number of offers reaches.
 */
export function scaleModelForDemand(model, delta) {
  if (!model || model.kind !== "distance" || !delta) return model;
  const f = Math.sqrt(1 / (1 + delta));
  return {
    ...model,
    reach: model.reach * f,
    points: model.points.map((p) => ({ ...p, cutoff: Number.isFinite(p.cutoff) ? p.cutoff * f : p.cutoff })),
  };
}

/** P(X >= k) for X ~ Poisson(mean), by summing the CDF with the term recurrence term *= mean/i. */
export function poissonTail(mean, k) {
  if (k <= 0) return 1;
  let term = Math.exp(-mean);
  let cdf = term;
  for (let i = 1; i < k; i++) {
    term *= mean / i;
    cdf += term;
  }
  return 1 - cdf;
}

/**
 * Equal-preferences outcome simulation: councils offer your highest-ranked school that can
 * offer a place, so P(offer at school i) = c[i] * product over j<i of (1 - c[j]).
 * `chances` may contain nulls (treated as 0). Returns { probs, none }; probs + none sum to 1.
 */
export function combineOutcomes(chances) {
  const c = chances.map((v) => v ?? 0);
  let miss = 1;
  const probs = c.map((p) => {
    const out = p * miss;
    miss *= 1 - p;
    return out;
  });
  return { probs, none: miss };
}

/** Distance offers for a band in one year (mirrors the helper in admissions.js). */
function distanceOffers(y, group) {
  const row = (y.criteria || []).find((c) => /distance/i.test(c.label) && !/maximum/i.test(c.label));
  if (!row) return null;
  if (group === "All") return row.total ?? null;
  return row.counts?.[group] ?? null;
}

/**
 * Chance that the waiting list reaches `dist` miles by the end of the summer term.
 * For each band-year sample with cut-off r < dist, the places that must free up are
 * k = n * (dist^2 - r^2)/r^2 at the midpoint of the half-density/full-density range
 * (0.75 * k_full, like waitingListHtml), then P(Poisson(mean) >= k).
 * mean = meanPerBand scaled by PAN/175 when the PAN is known.
 * Samples are weighted like chanceModel (RECENCY ^ (latest - yr), normalised).
 * Returns null when there are no usable samples.
 */
export function waitingChance(rec, band, dist, meanPerBand, pan) {
  if (dist == null) return null;
  const ys = yearsOf(rec);
  if (!ys.length) return null;
  const latest = ys.at(-1);
  const mean = meanPerBand * (pan ? pan / 175 : 1);
  const samples = [];
  ys.forEach((yr) => {
    const y = rec.years[yr];
    if (y.allocation === "random_by_zone") return;
    const w = RECENCY ** (latest - yr);
    if (y.non_preference_offers > 0) {
      samples.push({ p: 1, w });
      return;
    }
    const groups = groupsOf(y).filter((g) => !band || band === "unsure" || g === band);
    const d = distances(y);
    const open = allOffered(y);
    const usable = groups.filter((g) => open.includes(g) || d[g] != null);
    usable.forEach((g) => {
      let r = d[g];
      if (open.includes(g) || (r != null && r > OPEN_BAND_MILES)) r = Infinity;
      const wEach = w / usable.length;
      if (!Number.isFinite(r) || r >= dist) {
        samples.push({ p: 1, w: wEach });
        return;
      }
      const n = distanceOffers(y, g);
      if (!n) {
        samples.push({ p: 0, w: wEach });
        return;
      }
      const kFull = (n * (dist * dist - r * r)) / (r * r);
      const k = Math.max(1, Math.round(0.75 * kFull));
      samples.push({ p: poissonTail(mean, k), w: wEach });
    });
  });
  if (!samples.length) return null;
  const total = samples.reduce((a, s) => a + s.w, 0);
  return samples.reduce((a, s) => a + s.p * s.w, 0) / total;
}

/** A probability said out loud: 0.5 → "about 5 in 10". */
export function friendlyOdds(p) {
  if (p == null) return "hard to say";
  if (p <= 0) return "about 0 in 10";
  if (p >= 1) return "about 10 in 10";
  const n = Math.min(10, Math.max(1, Math.round(p * 10)));
  return `about ${n} in 10`;
}

/* ================================================================== */
/* Plan state                                                          */
/* ================================================================== */

const MAX_PLAN = 6;

const plan = store.get("plan", []).map(Number).filter((u) => Number.isFinite(u));
const planLa = store.get("planLa", {});
const whatIf = Object.assign({ band: "unsure", demand: 0, freeing: "typical", siblings: {} }, store.get("planWhatIf", {}));

const FREEING_MEANS = { few: 1, typical: 3, many: 6 };

function savePlan() {
  store.set("plan", plan);
  store.set("planLa", planLa);
}

function saveWhatIf() {
  store.set("planWhatIf", whatIf);
}

/** Add a school to the plan (max 6). Records its council so it can be reloaded after a refresh. */
export function addToPlan(urn) {
  const key = Number(urn);
  if (plan.includes(key) || plan.length >= MAX_PLAN) return false;
  plan.push(key);
  const la = state.byUrn.get(key)?._la;
  if (la) planLa[key] = la;
  savePlan();
  emit("plan", plan);
  return true;
}

function removeFromPlan(urn) {
  const i = plan.indexOf(Number(urn));
  if (i < 0) return;
  plan.splice(i, 1);
  delete whatIf.siblings[urn];
  savePlan();
  saveWhatIf();
  emit("plan", plan);
}

function moveInPlan(urn, dir) {
  const i = plan.indexOf(Number(urn));
  const j = i + dir;
  if (i < 0 || j < 0 || j >= plan.length) return;
  [plan[i], plan[j]] = [plan[j], plan[i]];
  savePlan();
  emit("plan", plan);
}

/** For shortlist.js's "Add to my plan" button: is this school already ranked, and is the plan full? */
export const isInPlan = (urn) => plan.includes(Number(urn));
export const planFull = () => plan.length >= MAX_PLAN;

/* ================================================================== */
/* Chances with the what-if scenarios applied                          */
/* ================================================================== */

function modelFor(school) {
  const rec = admissionsFor(school.urn);
  if (!rec) return { rec: null, model: null };
  let model = modelForBand(rec, whatIf.band);
  model = scaleModelForDemand(model, (whatIf.demand || 0) / 100);
  return { rec, model };
}

/** Offer-day chance for one school with every scenario applied (sibling beats distance). */
function chanceFor(school) {
  if (whatIf.siblings[school.urn]) return { chance: SIBLING_CHANCE, sibling: true, rec: admissionsFor(school.urn), model: null };
  const { rec, model } = modelFor(school);
  const chance = model?.kind === "distance" && school._dist != null ? chanceAt(model, school._dist) : null;
  return { chance, sibling: false, rec, model };
}

function latestCutoffText(rec) {
  const yr = latestYear(rec);
  if (!yr) return "–";
  const y = rec.years[yr];
  if (y.non_preference_offers > 0) return `all offered (${yr})`;
  const d = distances(y);
  const open = allOffered(y);
  const groups = groupsOf(y).filter((g) => !whatIf.band || whatIf.band === "unsure" || g === whatIf.band);
  const vals = groups.map((g) => (open.includes(g) ? Infinity : d[g])).filter((v) => v != null);
  if (!vals.length) return "–";
  if (vals.every((v) => !Number.isFinite(v))) return `all offered (${yr})`;
  const finite = vals.filter(Number.isFinite);
  const text = finite.length > 1 ? `${Math.min(...finite).toFixed(2)}–${Math.max(...finite).toFixed(2)} mi` : `${finite[0].toFixed(2)} mi`;
  return `${text} (${yr})`;
}

/** Green, amber or neutral only — never red for a child's chances. */
function chancePill(chance, sibling) {
  if (chance == null) return `<span class="pill" style="--dot: var(--neutral)">hard to estimate</span>`;
  const color = chance >= 0.6 ? "--good" : chance >= 0.25 ? "--warning" : "--neutral";
  const pct = chance > 0.99 ? "99%+" : chance < 0.01 ? "under 1%" : `${Math.round(chance * 100)}%`;
  return `<span class="pill" style="--dot: var(${color})" title="${sibling ? "Siblings are usually offered before distance is considered." : "Estimated from past offer-day cut-offs, with your what-if choices applied."}">${pct}${sibling ? " · sibling" : ""}</span>`;
}

/* ================================================================== */
/* Rendering                                                           */
/* ================================================================== */

const ordinal = (i) => ["1st", "2nd", "3rd", "4th", "5th", "6th"][i] || `${i + 1}th`;
const SEG_COLORS = ["--seq-6", "--seq-5", "--seq-4", "--seq-3", "--seq-2", "--seq-1"];

let selectSchoolFn = null;
let planView = null;

const planSchools = () => plan.map((u) => state.byUrn.get(u)).filter(Boolean);

function compareHtml(loaded) {
  return `<div style="overflow-x:auto"><table class="plan-compare">
    <thead><tr><th></th>${loaded.map((s) => `<th><button class="plan-name" data-select="${s.urn}">${esc(s.name)}</button></th>`).join("")}</tr></thead>
    <tbody>
      <tr><th>Distance</th>${loaded.map((s) => `<td>${s._dist != null ? fmt.mi(s._dist) : "–"}</td>`).join("")}</tr>
      <tr><th>Ofsted</th>${loaded.map((s) => `<td>${esc(s._ofsted || "–")}</td>`).join("")}</tr>
      <tr><th>Estimated chance</th>${loaded.map((s) => {
        const { chance, sibling, model } = chanceFor(s);
        const caveat = model?.kind === "rule" ? ` <span class="pill" style="--dot: var(--neutral)" title="${esc(model.rule.note)}">${esc(model.rule.pill)}</span>` : "";
        return `<td>${chancePill(chance, sibling)}${caveat}</td>`;
      }).join("")}</tr>
      <tr><th>Latest cut-off</th>${loaded.map((s) => `<td>${latestCutoffText(admissionsFor(s.urn))}</td>`).join("")}</tr>
    </tbody>
  </table></div>`;
}

function outcomeHtml(loaded) {
  const outcomes = loaded.map((s) => chanceFor(s).chance);
  const { probs, none } = combineOutcomes(outcomes);
  const segments = loaded.map((s, i) => ({ label: `your ${ordinal(i)} choice, ${s.name}`, p: probs[i], school: true })).concat([{ label: "none of these", p: none, school: false }]);
  const pctSum = segments.reduce((a, seg) => a + seg.p * 100, 0);
  const bestIdx = probs.reduce((best, p, i) => (p > probs[best] ? i : best), 0);
  const noneMostLikely = none > 0 && none >= Math.max(...probs, 0);
  const mostLikely = noneMostLikely
    ? `Right now the single most likely outcome is <strong>none of these on offer day</strong> — but taken together your schools are still promising, and waiting lists move a lot between March and July.`
    : `Most likely: <strong>your ${ordinal(bestIdx)} choice, ${esc(loaded[bestIdx].name)}</strong> (${friendlyOdds(probs[bestIdx])}).`;
  const html = `
    <div class="plan-bar" role="img" aria-label="Estimated chances on offer day">
      ${segments.map((seg, i) => `<span class="plan-seg" style="width:${Math.max(seg.p * 100, seg.p > 0 ? 1.5 : 0)}%;background:var(${seg.school ? SEG_COLORS[i % SEG_COLORS.length] : "--neutral"})" title="${esc(seg.label)}: ${(seg.p * 100).toFixed(1)}%">${seg.p >= 0.08 ? `${Math.round(seg.p * 100)}%` : ""}</span>`).join("")}
    </div>
    <p class="plan-most-likely">${mostLikely}</p>
    <ul class="plan-outcome-list">
      ${segments.map((seg) => `<li><strong>${(seg.p * 100).toFixed(1)}%</strong> — ${esc(seg.label)} (${friendlyOdds(seg.p)})${seg.school ? "" : ` <span class="muted">— the council then offers the nearest school with space, and waiting lists and appeals begin.</span>`}`).join("")}
    </ul>`;
  return { html, pctSum, probs, none, bestIdx, noneMostLikely };
}

function waitingHtml(loaded, bestIdx, noneMostLikely) {
  const freeingMean = FREEING_MEANS[whatIf.freeing] ?? 3;
  const upto = noneMostLikely ? loaded.length : bestIdx;
  const rows = loaded.slice(0, upto).map((s) => {
    const rec = admissionsFor(s.urn);
    if (!rec) return null;
    const yr = latestYear(rec);
    const pan = yr ? rec.years[yr]?.pan : null;
    const p = waitingChance(rec, whatIf.band, s._dist, freeingMean, pan);
    if (p == null) return null;
    return { s, p };
  }).filter(Boolean);
  if (!rows.length) return "";
  const word = { few: "a few", typical: "a typical number of", many: "many" }[whatIf.freeing] || "a typical number of";
  return `
    <p>For each school above your most likely one, this is the estimated chance the waiting list reaches you by the end of the summer term if ${word} places free up. Accept your offer meanwhile — it doesn't hurt your waiting-list position.</p>
    <ul class="plan-waiting">
      ${rows.map(({ s, p }) => `<li><strong>${esc(s.name)}</strong>: if you don't get it on offer day, ${friendlyOdds(p)} by July</li>`).join("")}
    </ul>`;
}

/** Re-render only the scenario-dependent sections (so the demand slider survives its own input event). */
function renderDynamic() {
  const loaded = planSchools();
  const out = outcomeHtml(loaded);
  $("#plan-outcome", planView).innerHTML = out.html;
  $("#plan-outcome", planView).setAttribute("data-pct-sum", out.pctSum.toFixed(1));
  $("#plan-compare-wrap", planView).innerHTML = loaded.length ? compareHtml(loaded) : "";
  $("#plan-waiting-wrap", planView).innerHTML = waitingHtml(loaded, out.bestIdx, out.noneMostLikely);
  const likelyNote = loaded.length && !out.noneMostLikely ? { offer: `Most likely: your ${ordinal(out.bestIdx)} choice, ${loaded[out.bestIdx].name}.` } : {};
  renderTimeline($("#plan-timeline", planView), { today: new Date(), planNote: likelyNote });
  $$("[data-select]", planView).forEach((b) => b.addEventListener("click", () => selectSchoolFn?.(Number(b.dataset.select))));
}

function renderPlan() {
  if (!planView) return;
  $("#plan-count").textContent = plan.length || "";

  // Load councils for plan schools that aren't in memory yet (e.g. after a refresh).
  const missingLas = plan.filter((u) => !state.byUrn.has(u)).map((u) => planLa[u]).filter(Boolean);
  if (missingLas.length) ensureLas(missingLas); // the "schools" event re-renders once loaded

  const schools = plan.map((u) => state.byUrn.get(u));
  const loaded = schools.filter(Boolean);
  const home = state.home;

  const listHtml = schools.length
    ? `<ol id="plan-list" class="plan-list">
        ${schools.map((s, i) => {
          if (!s) return `<li class="plan-row"><span class="rank">${i + 1}</span><span class="muted">Loading…</span></li>`;
          const { chance, sibling } = chanceFor(s);
          return `<li class="plan-row" data-urn="${s.urn}">
            <span class="rank">${i + 1}</span>
            <div class="plan-main">
              <button class="plan-name" data-select="${s.urn}">${esc(s.name)}</button>
              <span class="plan-meta">${esc(laName(s._la))}${s._dist != null ? ` · ${fmt.mi(s._dist)}` : ""} ${chancePill(chance, sibling)}</span>
              <label class="plan-sib"><input type="checkbox" class="plan-sibling" data-urn="${s.urn}" ${sibling ? "checked" : ""}> sibling at this school</label>
            </div>
            <div class="plan-tools">
              <button class="plan-move" data-urn="${s.urn}" data-dir="-1" ${i === 0 ? "disabled" : ""} aria-label="Move ${esc(s.name)} up">↑</button>
              <button class="plan-move" data-urn="${s.urn}" data-dir="1" ${i === schools.length - 1 ? "disabled" : ""} aria-label="Move ${esc(s.name)} down">↓</button>
              <button class="plan-remove" data-urn="${s.urn}" aria-label="Remove ${esc(s.name)} from the plan">✕</button>
            </div>
          </li>`;
        }).join("")}
      </ol>`
    : `<p class="empty">Your plan is empty. Add schools from your shortlist or search below — up to ${MAX_PLAN}, the usual number of preferences on a London secondary application (primary varies by council).</p>`;

  const shortlistAdds = [...state.shortlist].filter((u) => !plan.includes(u)).map((u) => state.byUrn.get(u)).filter(Boolean);
  const addHtml = `
    ${shortlistAdds.length ? `<div class="chips plan-chips">${shortlistAdds.map((s) => `<button class="chip" data-add="${s.urn}">+ ${esc(s.name)}</button>`).join("")}</div>` : ""}
    <input id="plan-search" type="search" placeholder="Search schools by name to add…" aria-label="Search schools to add to the plan">
    <div id="plan-search-results" class="plan-search-results"></div>
    ${plan.length >= MAX_PLAN ? `<p class="note">Your plan is full at ${MAX_PLAN} schools — the usual London secondary number of preferences. Remove one to add another.</p>` : ""}`;

  const distLine = home
    ? `Distances use your home pin${home.label ? ` (${esc(home.label)})` : ""} — drag the pin on the map to try a different address.`
    : `Search a postcode at the top of the page so we can measure your distance to each school.`;
  const whatIfHtml = `
    <h3 class="section">What if…?</h3>
    <div class="callout" style="--dot: var(--neutral)">Every number here is an estimate from past years — real cut-offs move each year. Use this to feel prepared, not to count certainties.</div>
    <div class="whatif">
      <label>Your child's band from the test
        <select id="plan-band">
          <option value="unsure"${whatIf.band === "unsure" ? " selected" : ""}>Not sure yet</option>
          ${["A", "B", "C", "D", "E"].map((b) => `<option value="${b}"${whatIf.band === b ? " selected" : ""}>Band ${b}</option>`).join("")}
        </select>
      </label>
      <label>Demand compared with last year: <strong id="plan-demand-label">${whatIf.demand > 0 ? "+" : ""}${whatIf.demand || 0}%</strong>
        <input id="plan-demand" type="range" min="-20" max="20" step="1" value="${whatIf.demand || 0}"
          title="If more families apply, the same number of places runs out sooner, so cut-off distances shrink. We scale cut-offs by √(1/(1+change)): +20% demand shortens cut-offs by about 9%, -20% stretches them by about 12%.">
      </label>
      <label>Places that free up after offer day
        <select id="plan-freeing">
          <option value="few"${whatIf.freeing === "few" ? " selected" : ""}>Few</option>
          <option value="typical"${whatIf.freeing === "typical" ? " selected" : ""}>Typical</option>
          <option value="many"${whatIf.freeing === "many" ? " selected" : ""}>Many</option>
        </select>
      </label>
      <p class="note plan-dist-note">${distLine}</p>
    </div>`;

  planView.innerHTML = `
    <h2 class="plan-title">My plan</h2>
    <p class="plan-intro">Pick up to ${MAX_PLAN} schools, put them in the order you'd want them, and see how the chances add up. Everything is saved in this browser only.</p>
    ${listHtml}
    <h3 class="section">Add a school</h3>
    ${addHtml}
    <h3 class="section" id="plan-compare-head"${loaded.length ? "" : " hidden"}>Compare your schools</h3>
    <div id="plan-compare-wrap"></div>
    ${whatIfHtml}
    <h3 class="section">How offer day is likely to go</h3>
    <p>Councils offer you the highest school on your list that can offer a place, so your order matters — always list schools in the order you truly want them.</p>
    <div id="plan-outcome" data-pct-sum="100.0"></div>
    <h3 class="section" id="plan-waiting-head">If you don't get it on offer day</h3>
    <div id="plan-waiting-wrap"></div>
    <h3 class="section">What happens when</h3>
    <div id="plan-timeline"></div>`;

  renderDynamic();

  $$("[data-select]", planView).forEach((b) => b.addEventListener("click", () => selectSchoolFn?.(Number(b.dataset.select))));
  $$("[data-add]", planView).forEach((b) => b.addEventListener("click", () => addToPlan(Number(b.dataset.add))));
  $$(".plan-remove", planView).forEach((b) => b.addEventListener("click", () => removeFromPlan(b.dataset.urn)));
  $$(".plan-move", planView).forEach((b) => b.addEventListener("click", () => moveInPlan(b.dataset.urn, Number(b.dataset.dir))));
  $$(".plan-sibling", planView).forEach((c) => c.addEventListener("change", () => {
    whatIf.siblings[c.dataset.urn] = c.checked;
    if (!c.checked) delete whatIf.siblings[c.dataset.urn];
    saveWhatIf();
    renderPlan();
  }));
  $("#plan-band", planView).addEventListener("change", (e) => { whatIf.band = e.target.value; saveWhatIf(); renderPlan(); });
  $("#plan-demand", planView).addEventListener("input", (e) => {
    whatIf.demand = Number(e.target.value);
    saveWhatIf();
    $("#plan-demand-label", planView).textContent = `${whatIf.demand > 0 ? "+" : ""}${whatIf.demand}%`;
    renderDynamic();
  });
  $("#plan-freeing", planView).addEventListener("change", (e) => { whatIf.freeing = e.target.value; saveWhatIf(); renderDynamic(); });
  $("#plan-search", planView).addEventListener("input", (e) => renderSearchResults(e.target.value));

  // Hide the waiting-list heading when there is nothing above the most likely school.
  const hasWaiting = Boolean($("#plan-waiting-wrap", planView).innerHTML.trim());
  $("#plan-waiting-head", planView).hidden = !hasWaiting;
}

function renderSearchResults(query) {
  const box = $("#plan-search-results", planView);
  const q = query.trim().toLowerCase();
  if (q.length < 2) {
    box.innerHTML = "";
    return;
  }
  const matches = state.schools.filter((s) => !plan.includes(s.urn) && s.name.toLowerCase().includes(q)).slice(0, 8);
  box.innerHTML = matches.length
    ? matches.map((s) => `<div class="plan-match"><span>${esc(s.name)} <span class="muted small">${esc(laName(s._la))}${s._dist != null ? ` · ${fmt.mi(s._dist)}` : ""}</span></span><button class="chip" data-add="${s.urn}">Add</button></div>`).join("")
    : `<p class="note">No schools matching “${esc(query.trim())}” are loaded yet — zoom the map or search a postcode nearby first.</p>`;
  $$("[data-add]", box).forEach((b) => b.addEventListener("click", () => addToPlan(Number(b.dataset.add))));
}

/* ================================================================== */
/* Mounting                                                            */
/* ================================================================== */

/**
 * Mount the "My plan" tab and panel. Called once from app.js with the app's selectSchool.
 * Inserts its own stylesheet, tab button (after Shortlist) and view section, and manages
 * showing itself; app.js's showView hides all .view elements, so other tabs keep working.
 */
export function initPlanner({ selectSchool }) {
  selectSchoolFn = selectSchool;

  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "css/planner.css";
  document.head.appendChild(link);

  const tab = document.createElement("button");
  tab.setAttribute("role", "tab");
  tab.dataset.view = "plan";
  tab.setAttribute("aria-selected", "false");
  tab.innerHTML = `My plan <span id="plan-count" class="count"></span>`;
  const shortlistTab = $('.tabs [data-view="shortlist"]');
  shortlistTab.after(tab);

  planView = document.createElement("section");
  planView.id = "view-plan";
  planView.className = "view";
  planView.setAttribute("role", "tabpanel");
  planView.hidden = true;
  $("#view-shortlist").after(planView);

  $("#plan-count").textContent = plan.length || "";

  tab.addEventListener("click", () => {
    $$(".view").forEach((v) => { v.hidden = v !== planView; });
    $$(".tabs [data-view]").forEach((b) => b.setAttribute("aria-selected", String(b === tab)));
    renderPlan();
  });

  const refresh = () => {
    $("#plan-count").textContent = plan.length || "";
    if (!planView.hidden) renderPlan();
  };
  on("home", refresh);
  on("schools", refresh);
  on("shortlist", refresh);
  on("plan", refresh);

  return { render: renderPlan };
}
