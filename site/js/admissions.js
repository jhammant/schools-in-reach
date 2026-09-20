import { $, $$, esc, fmt, cssVar, SERIES } from "./util.js";
import { state, isFaithSchool, isSelectiveSchool, hasAdmissionsData, laName } from "./state.js";
import { elevenPlusNote } from "./eleven_plus.js";

const years = (rec) => Object.keys(rec?.years || {}).map(Number).sort((a, b) => a - b);
export const latestYear = (rec) => years(rec).at(-1);

export function groupsOf(y) {
  if (Array.isArray(y.groups) && y.groups.length) return y.groups;
  if (y.max_distance && typeof y.max_distance === "object") return Object.keys(y.max_distance);
  return ["All"];
}

/** Normalise primary (single number) and secondary (per group) year records to { group: miles|null }. */
export function distances(y) {
  if (y.max_distance == null || typeof y.max_distance === "number") return { All: y.max_distance ?? null };
  return y.max_distance;
}

export function allOffered(y) {
  if (Array.isArray(y.all_offered)) return y.all_offered;
  return y.all_offered ? groupsOf(y) : [];
}

function distanceOffers(y, group) {
  const row = (y.criteria || []).find((c) => /distance/i.test(c.label) && !/maximum/i.test(c.label));
  if (!row) return null;
  if (group === "All") return row.total ?? null;
  return row.counts?.[group] ?? null;
}

/* ---------- chance model ---------- */

// Each older year counts this much as the year after it, so recent intakes dominate.
export const RECENCY = 0.75;
// Published "cut-offs" beyond this (7.2 mi, 350 mi) mean everyone in that band was offered.
const OPEN_BAND_MILES = 3;
export const CHANCE_CLASSES = [
  { min: 0.8, label: "80–100%", color: "--chance-1" },
  { min: 0.6, label: "60–80%", color: "--chance-2" },
  { min: 0.4, label: "40–60%", color: "--chance-3" },
  { min: 0.2, label: "20–40%", color: "--chance-4" },
  { min: 0.05, label: "5–20%", color: "--chance-5" },
];

/**
 * Offer-day chance of a place on distance, as a function of distance from the school.
 * Every published band cut-off since the first year is a weighted sample: bands count equally
 * (a child's band isn't known in advance) and recent years count more. Siblings, faith and
 * waiting lists are ignored.
 */
// Admission rules where a straight-line distance from the school doesn't decide places on its own.
export const RULE_CAVEATS = {
  selective: { pill: "Selective school (entrance test)", note: "This school selects children with an entrance test, and distance only counts among those who pass. A distance alone can't predict your chances here, so we don't show one. Ask the school how its test works and when to register." },
  nodal_point: { pill: "Distance from a fixed point", note: "This school measures distance from a nodal point (a fixed spot the council chooses) rather than the school gate, so our straight-line distances won't match the council's and we can't estimate a chance. The council's admissions booklet shows where that point is." },
  catchment_then_distance: { pill: "Catchment area applies", note: "This school gives priority to children who live in its catchment area (the neighbourhood it mainly serves). Distance then decides within each group, so your chances outside the catchment are lower than these figures suggest. Check the council's catchment map to see which side of the line you're on." },
};

export function chanceModel(rec) {
  const ys = years(rec);
  if (!ys.length) return null;
  const latest = ys.at(-1);
  if (rec.years[latest].allocation === "random_by_zone") return { kind: "lottery", year: latest };
  const rule = RULE_CAVEATS[rec.years[latest].allocation];
  if (rule) return { kind: "rule", rule, year: latest };
  const points = [];
  ys.forEach((yr) => {
    const y = rec.years[yr];
    if (y.allocation === "random_by_zone") return;
    const w = RECENCY ** (latest - yr);
    if (y.non_preference_offers > 0) {
      points.push({ yr, cutoff: Infinity, w });
      return;
    }
    const d = distances(y);
    const open = allOffered(y);
    const cutoffs = groupsOf(y)
      .map((g) => (open.includes(g) || (d[g] != null && d[g] > OPEN_BAND_MILES) ? Infinity : d[g]))
      .filter((v) => v != null);
    cutoffs.forEach((cutoff) => points.push({ yr, cutoff, w: w / cutoffs.length }));
  });
  if (!points.length) return { kind: "unknown", year: latest };
  const total = points.reduce((a, p) => a + p.w, 0);
  const byDistance = [...points].sort((a, b) => b.cutoff - a.cutoff);
  const finite = points.map((p) => p.cutoff).filter(Number.isFinite);
  // How far to draw: a little beyond the furthest real cut-off, so an "everyone offered" band doesn't paint the whole map.
  const reach = finite.length ? Math.min(OPEN_BAND_MILES, Math.max(...finite) * 1.25) : OPEN_BAND_MILES;
  return { kind: "distance", points: byDistance, total, reach, from: ys[0], to: latest, faith: rec.years[latest].allocation === "faith_then_distance" };
}

export function chanceAt(model, miles) {
  if (model?.kind !== "distance") return null;
  let hit = 0;
  for (const p of model.points) {
    if (p.cutoff >= miles) hit += p.w;
    else break;
  }
  return hit / model.total;
}

/** Furthest distance at which the chance is still at least `p` (Infinity if it never drops that low). */
export function radiusForChance(model, p) {
  let acc = 0;
  for (const pt of model.points) {
    acc += pt.w;
    if (acc / model.total >= p - 1e-9) return pt.cutoff;
  }
  return 0;
}

export const chanceClass = (c) => CHANCE_CLASSES.find((k) => c >= k.min) || null;

export const STATUS_COLOR = { in: "--good", spare: "--good", all: "--good", some: "--warning", out: "--neutral", lottery: "--neutral", unknown: "--neutral" };

/** How a school's latest published cut-offs compare with a home distance. */
export function reachStatus(rec, dist) {
  const year = latestYear(rec);
  if (!year) return null;
  const y = rec.years[year];
  if (y.allocation === "random_by_zone") return { status: "lottery", year, label: `Places by random draw (${year})` };
  if (y.non_preference_offers > 0) return { status: "spare", year, label: `Room for all in ${year}` };
  const offeredAll = allOffered(y);
  const dist_ = distances(y);
  const groups = groupsOf(y).filter((g) => dist_[g] != null || offeredAll.includes(g));
  if (!groups.length) return { status: "unknown", year, label: `No distance figures published (${year})` };
  if (dist == null) {
    const vals = groups.map((g) => dist_[g]).filter((v) => v != null);
    const range = vals.length ? `${Math.min(...vals).toFixed(2)}–${Math.max(...vals).toFixed(2)} mi` : "everyone";
    return { status: "unknown", year, label: vals.length ? `${year}: places reached ${vals.length > 1 ? range : range.split("–")[0]}` : `${year}: room for all` };
  }
  const hits = groups.filter((g) => offeredAll.includes(g) || dist_[g] >= dist).length;
  const bandWord = groups.length === 1 ? "" : " bands";
  if (hits === groups.length) return { status: "in", year, hits, total: groups.length, label: groups.length === 1 ? `In reach in ${year}` : `In reach, every${bandWord.slice(0, -1)} (${year})` };
  if (hits > 0) return { status: "some", year, hits, total: groups.length, label: `In reach, ${hits} of ${groups.length}${bandWord} (${year})` };
  return { status: "out", year, hits, total: groups.length, label: `Places stopped a little closer in ${year}` };
}

export function reachPill(rec, dist, school = null) {
  const r = rec && reachStatus(rec, dist);
  if (!r) return "";
  const ruled = chanceModel(rec);
  if (ruled?.kind === "rule") return `<span class="pill" style="--dot: var(--neutral)" title="${esc(ruled.rule.note)}">${esc(ruled.rule.pill)}</span>`;
  if (dist != null && r.status !== "lottery") {
    const model = chanceModel(rec);
    const c = chanceAt(model, dist);
    if (c != null) {
      const status = c >= 0.6 ? "--good" : c >= 0.2 ? "--warning" : "--neutral";
      const word = c >= 0.6 ? "Good chance" : c >= 0.2 ? "Worth a try" : "Long shot";
      const pct = c > 0.99 ? "99%+" : c < 0.01 ? "under 1%" : `${Math.round(c * 100)}%`;
      const frame = c > 0.99 ? "nearly every family at your distance got a place" : c < 0.01 ? "very few families at your distance got a place" : `about ${Math.round(c * 10)} in 10 families at your distance got a place`;
      const faith = school && isFaithSchool(school);
      return `<span class="pill" style="--dot: var(${faith ? "--neutral" : status})" title="${esc(`${r.label}. An estimate from ${model.from}–${model.to} offer days: ${frame}.${faith ? " Faith criteria usually come before distance at this school." : ""}`)}">${word} · ${pct}${faith ? " · faith school" : ""}</span>`;
    }
  }
  return `<span class="pill" style="--dot: var(${STATUS_COLOR[r.status]})">${esc(r.label)}</span>`;
}

/* ---------- detail tab ---------- */

export function renderAdmissions(root, school, rec, mapApi, sources) {
  if (!rec) {
    mapApi.clearRings();
    const { group, independent } = school._class;
    const council = laName(school._la);
    let msg = "We don't have admissions figures for this school yet.";
    if (independent) msg = "This is an independent school, so it sets its own admissions — entrance assessments, interviews and fees — and there's no council distance figure to show.";
    else if (!hasAdmissionsData(school)) msg = `We haven't added ${council} council's admissions figures yet. We're working through councils one at a time, starting with London.`;
    else if (group === "secondary" || group === "allthrough") msg = `This school isn't in ${council}'s published list of oversubscribed secondary schools, which usually means every child who applied and didn't get a higher preference was offered a place.`;
    else if (group === "primary") msg = "No reception figures were found for this school. It may well have had a place for every child who applied.";
    root.innerHTML = `${isSelectiveSchool(school) ? elevenPlusNote(school, council) : ""}<div class="callout">${esc(msg)}</div>`;
    return;
  }

  const ys = years(rec);
  const ui = { year: ys.at(-1), group: "all" };
  const home = state.home;
  const dist = school._dist;
  const model = chanceModel(rec);

  const draw = () => {
    const y = rec.years[ui.year];
    const groups = groupsOf(y);
    const dists = distances(y);
    const offeredAll = allOffered(y);
    const colorOf = (g) => cssVar(SERIES[groups.indexOf(g) % SERIES.length]);
    const shown = ui.group === "all" ? groups : [ui.group];
    const siblings = (y.criteria || []).find((c) => /sibling/i.test(c.label) && !/former|non[- ]faith/i.test(c.label));
    const distRow = distanceOffers(y, "All");
    const numericDists = groups.map((g) => dists[g]).filter((v) => v != null);
    const furthest = numericDists.length ? Math.max(...numericDists) : null;

    let verdict = model?.kind === "rule" ? `<div class="callout" style="--dot: var(--neutral)"><strong>${esc(model.rule.pill)}.</strong> ${esc(model.rule.note)}</div>` : "";
    const r = reachStatus(rec, dist);
    if (home && dist != null && y.allocation !== "random_by_zone" && model?.kind !== "rule") {
      const hitsAllYears = [];
      const missesAllYears = [];
      let totalAllYears = 0;
      ys.forEach((yr) => {
        const yy = rec.years[yr];
        const dd = distances(yy);
        const oa = allOffered(yy);
        groupsOf(yy).forEach((g) => {
          if (dd[g] == null && !oa.includes(g)) return;
          totalAllYears += 1;
          const tag = `${yr}${groupsOf(yy).length > 1 ? ` ${g}` : ""}`;
          if (oa.includes(g) || dd[g] >= dist) hitsAllYears.push(tag);
          else missesAllYears.push(tag);
        });
      });
      const chance = chanceAt(model, dist);
      const chanceFrame = chance == null || chance > 0.99 ? "" : chance < 0.01 ? "Very few families at your distance got a place." : `That's about ${Math.round(chance * 10)} in 10 families at your distance.`;
      const chanceText = chance == null ? "" : `<div class="chance-big">${chance > 0.99 ? "99%+" : chance < 0.01 ? "Under 1%" : `${Math.round(chance * 100)}%`} <span>estimated chance of a place, based on distance</span></div>${chanceFrame ? `<p class="small" style="margin:0 0 6px">${chanceFrame}</p>` : ""}`;
      verdict = `
        <div class="callout" style="--dot: var(${chance == null ? STATUS_COLOR[r?.status] || "--neutral" : chance >= 0.6 ? "--good" : chance >= 0.2 ? "--warning" : "--neutral"})">
          ${chanceText}
          <strong>You're ${fmt.mi(dist)} away in a straight line.</strong>
          ${furthest != null ? `In ${ui.year}, places on distance reached families up to ${fmt.mi(furthest, 3)} away.` : ""}
          ${totalAllYears === 0 ? `The council didn't publish a distance figure for this school in ${ys.length > 1 ? `these ${ys.length} years` : "this year"}. That usually means it had room for everyone, or places weren't decided on distance.` : `Across ${ys.length} year${ys.length > 1 ? "s" : ""} of data, places reached your distance in`} ${totalAllYears === 0 ? "" : `${hitsAllYears.length} of ${totalAllYears} ${groups.length > 1 ? "band-years" : "years"}${hitsAllYears.length && hitsAllYears.length <= 6 ? ` (${esc(hitsAllYears.join(", "))})` : missesAllYears.length && missesAllYears.length <= 6 ? `; in ${esc(missesAllYears.join(", "))} places went to families living a little closer` : ""}.`}
        </div>`;
    }

    root.innerHTML = `
      ${isSelectiveSchool(school) ? elevenPlusNote(school, laName(school._la)) : ""}
      ${verdict}
      <div class="stats">
        <div class="stat"><b>${fmt.num(y.applications)}</b><span>applied in ${ui.year}</span></div>
        <div class="stat"><b>${fmt.num(y.pan)}</b><span>places available (PAN)</span></div>
        <div class="stat"><b>${y.applications && y.pan ? (y.applications / y.pan).toFixed(1) : "–"}</b><span>applications per place</span></div>
        <div class="stat"><b>${siblings ? fmt.num(siblings.total) : "–"}</b><span>places to siblings</span></div>
        <div class="stat"><b>${fmt.num(distRow)}</b><span>places on distance</span></div>
      </div>

      ${model?.kind === "distance" ? `
      <h3 class="section">Chance of a place: green is good</h3>
      <div class="heat-legend">${CHANCE_CLASSES.map((k) => `<span><i style="background:${cssVar(k.color)}"></i>${k.label}</span>`).join("")}</div>
      <p class="note">The shading on the map shows your estimated chance of a place at each distance from the school. It's worked out from ${model.from}–${model.to} offer days, with recent years counting more${groupsOf(rec.years[model.to]).length > 1 ? " and every band counting equally, since you won't know your child's band in advance" : ""}. It doesn't include siblings${model.faith ? ", faith criteria" : ""} or waiting-list places, so treat it as a guide, not a promise.</p>` : ""}

      <h3 class="section">How far places reached, year by year</h3>
      <div class="chips" data-role="years">${ys.map((yr) => `<button class="chip" data-year="${yr}" aria-pressed="${yr === ui.year}">${yr}</button>`).join("")}</div>
      ${groups.length > 1 ? `<div class="chips" data-role="groups"><button class="chip" data-group="all" aria-pressed="${ui.group === "all"}">All bands</button>${groups.map((g) => `<button class="chip" data-group="${esc(g)}" aria-pressed="${ui.group === g}"><span class="swatch" style="background:${colorOf(g)}"></span>${esc(g)}</button>`).join("")}</div>` : ""}
      ${y.allocation === "random_by_zone" ? `<div class="callout">Places here are decided by a random draw within zones, so there's no distance figure to show.</div>` : `<div class="chart-wrap"><svg class="chart" viewBox="0 0 400 220" role="img" aria-label="Furthest distance offered each year"></svg><div class="tooltip"></div></div>
      <p class="note">Each dot is the furthest family that got a place on distance${groups.length > 1 ? " in one band (left to right). Bands are the ability groups some schools use so every level is represented" : ""}, as at National Offer Day (the day offers arrive — 1 March for secondary, mid-April for primary). ${home ? "The dashed line is your distance: dots above it reached you." : "Search your postcode to compare with your distance."} Click a year to draw it on the map.</p>`}

      <h3 class="section">Who was offered a place in ${ui.year}</h3>
      <div style="overflow-x:auto">
      <table>
        <thead><tr><th>Priority group</th>${groups.length > 1 ? groups.map((g) => `<th class="num">${esc(g)}</th>`).join("") : ""}<th class="num">Total</th></tr></thead>
        <tbody>
          ${(y.criteria || []).map((c) => `<tr><td>${esc(c.label)}</td>${groups.length > 1 ? groups.map((g) => `<td class="num">${c.counts?.[g] ?? ""}</td>`).join("") : ""}<td class="num">${c.total ?? ""}</td></tr>`).join("")}
          ${y.allocation !== "random_by_zone" ? `<tr><td><strong>Furthest distance (mi)</strong></td>${groups.length > 1 ? groups.map((g) => `<td class="num">${offeredAll.includes(g) ? "all" : dists[g] != null ? dists[g] : ""}</td>`).join("") : ""}<td class="num">${groups.length === 1 ? (offeredAll.length ? "all" : dists.All ?? "") : ""}</td></tr>` : ""}
          ${y.non_preference_offers ? `<tr><td>Offered to children who hadn't applied</td>${groups.length > 1 ? groups.map(() => "<td></td>").join("") : ""}<td class="num">${y.non_preference_offers}</td></tr>` : ""}
        </tbody>
      </table>
      </div>
      ${(y.notes || []).length ? `<p class="note">${y.notes.map(esc).join("<br>")}</p>` : ""}

      ${home && dist != null && y.allocation !== "random_by_zone" ? waitingListHtml(y, groups, dists, dist, ui.year) : ""}

      <p class="note">Source: ${(sources || []).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(", ") || `${esc(laName(school._la))} council`}. ${distanceNote(school)} Distances here are straight lines from ${home?.postcode ? "your postcode centre or the pin you placed" : "the pin"}, so they can differ a little from the council's own measurement.</p>
    `;

    if (y.allocation !== "random_by_zone") drawChart($(".chart-wrap", root), rec, ys, ui, dist, (yr) => { ui.year = yr; draw(); });
    $$('[data-role="years"] .chip', root).forEach((b) => b.addEventListener("click", () => { ui.year = Number(b.dataset.year); if (!groupsOf(rec.years[ui.year]).includes(ui.group)) ui.group = "all"; draw(); }));
    $$('[data-role="groups"] .chip', root).forEach((b) => b.addEventListener("click", () => { ui.group = b.dataset.group; draw(); }));

    const rings = shown
      .filter((g) => dists[g] != null && dists[g] < 5)
      .map((g) => ({ miles: dists[g], color: colorOf(g), label: `${groups.length > 1 ? `${g} ` : ""}${dists[g].toFixed(2)}` }));
    const heat = model?.kind === "distance" ? heatBands(model) : [];
    if (rings.length || heat.length) mapApi.showRings(school, rings, { home: home && dist != null ? home : null, distance: dist, heat });
    else mapApi.clearRings();
  };

  draw();
}

/** Nested discs for each chance class, largest first: [{ miles, color }]. Open-ended areas are capped for drawing. */
export function heatBands(model, { minChance = 0 } = {}) {
  return [...CHANCE_CLASSES]
    .filter((k) => k.min >= minChance)
    .reverse()
    .map((k) => ({ miles: Math.min(radiusForChance(model, k.min), model.reach), color: cssVar(k.color), label: k.label }))
    .filter((b) => b.miles > 0);
}

function distanceNote(school) {
  const a = state.laData.get(school._la)?.admissions;
  if (a?.distance_method === "walking_route") return `${laName(school._la)} measures the shortest walking route, which is usually a little longer than a straight line, so real distances may be bigger than these.`;
  if (a?.distance_notes) return esc(a.distance_notes);
  return "Councils usually measure from your home's address point to the school's measuring point.";
}

function waitingListHtml(y, groups, dists, dist, year) {
  const rows = groups
    .filter((g) => dists[g] != null && dists[g] < dist)
    .map((g) => {
      const n = distanceOffers(y, g);
      const r = dists[g];
      if (!n || !r) return null;
      const k = (n * (dist * dist - r * r)) / (r * r);
      return { g, r, n, lo: Math.max(1, Math.round(k / 2)), hi: Math.max(1, Math.round(k)) };
    })
    .filter(Boolean);
  if (!rows.length) return "";
  return `
    <h3 class="section">Could the waiting list help?</h3>
    <p class="small">After offer day, places that families turn down go to the next child on the waiting list${groups.length > 1 ? " in the same band" : ""}, in the same priority order. Based on how close together the ${year} distance places were, this is roughly how many places would need to free up for places to reach your distance. The range assumes families further out on the list are between half as dense and just as dense, so the true number could be a little different.</p>
    <table>
      <thead><tr>${groups.length > 1 ? "<th>Band</th>" : ""}<th class="num">Reached (mi)</th><th class="num">Places on distance</th><th class="num">Places needed</th></tr></thead>
      <tbody>${rows.map((x) => `<tr>${groups.length > 1 ? `<td>${esc(x.g)}</td>` : ""}<td class="num">${x.r.toFixed(3)}</td><td class="num">${x.n}</td><td class="num"><strong>${x.lo === x.hi ? x.lo : `${x.lo}–${x.hi}`}</strong></td></tr>`).join("")}</tbody>
    </table>
    <p class="note">This is our estimate, not published data: councils don't say how far waiting lists move. A handful of places freeing up in a band is common; dozens is not. It's always worth joining the waiting list — ask the council for your child's position after offer day.</p>`;
}

function drawChart(wrap, rec, ys, ui, dist, onYear) {
  if (!wrap) return;
  const svg = wrap.querySelector("svg");
  const tip = wrap.querySelector(".tooltip");
  const W = 400, H = 220, m = { t: 16, r: 12, b: 26, l: 36 };
  const allVals = [];
  ys.forEach((yr) => Object.values(distances(rec.years[yr])).forEach((v) => v != null && allVals.push(v)));
  const sorted = [...allVals].sort((a, b) => a - b);
  const p90 = sorted.length ? sorted[Math.floor(sorted.length * 0.9)] : 1;
  const yMax = Math.min(5, Math.max(p90 * 1.2, dist ? dist * 1.15 : 0, 0.5));
  const x = (i) => m.l + ((i + 0.5) * (W - m.l - m.r)) / ys.length;
  const y = (v) => m.t + ((yMax - Math.min(v, yMax)) * (H - m.t - m.b)) / yMax;
  const colW = (W - m.l - m.r) / ys.length;
  const surface = cssVar("--surface-1");
  const ticks = niceTicks(yMax);
  let s = "";

  ys.forEach((yr, i) => {
    if (yr === ui.year) s += `<rect x="${x(i) - colW / 2 + 1}" y="${m.t - 8}" width="${colW - 2}" height="${H - m.t - m.b + 8}" rx="4" fill="${cssVar("--surface-2")}"/>`;
  });
  ticks.forEach((v) => {
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="${cssVar("--grid")}"/>`;
    s += `<text x="${m.l - 6}" y="${y(v) + 3}" text-anchor="end">${v.toFixed(v < 1 ? 2 : 1)}</text>`;
  });
  s += `<text x="${m.l - 6}" y="${m.t - 5}" text-anchor="end">mi</text>`;
  if (dist != null && dist <= yMax) {
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(dist)}" y2="${y(dist)}" stroke="${cssVar("--text-primary")}" stroke-width="1.5" stroke-dasharray="4 3"/>`;
    s += `<text x="${W - m.r}" y="${y(dist) - 5}" text-anchor="end" style="fill:${cssVar("--text-primary")};font-weight:600">You ${dist.toFixed(2)} mi</text>`;
  }
  ys.forEach((yr, i) => {
    const yy = rec.years[yr];
    const groups = groupsOf(yy);
    const dd = distances(yy);
    const vals = groups.map((g) => dd[g]).filter((v) => v != null);
    if (vals.length > 1) s += `<line x1="${x(i)}" x2="${x(i)}" y1="${y(Math.max(...vals))}" y2="${y(Math.min(...vals))}" stroke="${cssVar("--border")}" stroke-width="2"/>`;
    const step = Math.min(5.5, (colW * 0.8) / Math.max(groups.length, 1));
    groups.forEach((g, j) => {
      const v = dd[g];
      if (v == null) return;
      const active = ui.group === "all" || ui.group === g;
      const cx = x(i) + (j - (groups.length - 1) / 2) * step;
      const clipped = v > yMax;
      s += `<circle cx="${cx}" cy="${y(v)}" r="4.5" fill="${cssVar(SERIES[j % SERIES.length])}" stroke="${surface}" stroke-width="2" opacity="${active ? 1 : 0.18}"
        data-tip="${esc(`${yr}${groups.length > 1 ? ` · ${g}` : ""}: ${v} mi${clipped ? " (off the scale)" : ""}${dist != null ? (v >= dist ? " · reached you" : ` · places stopped ${(dist - v).toFixed(2)} mi closer`) : ""}`)}"/>`;
    });
    s += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" style="${yr === ui.year ? `fill:${cssVar("--text-primary")};font-weight:700` : ""}">'${String(yr).slice(2)}</text>`;
    s += `<rect data-year="${yr}" x="${x(i) - colW / 2}" y="0" width="${colW}" height="${H}" fill="transparent" style="cursor:pointer"/>`;
  });
  svg.innerHTML = s;

  svg.onmousemove = (e) => {
    const r = svg.getBoundingClientRect();
    const scale = r.width / W;
    let best = null;
    let bestD = 14;
    svg.querySelectorAll("circle[data-tip]").forEach((c) => {
      const dd = Math.hypot(+c.getAttribute("cx") * scale - (e.clientX - r.left), +c.getAttribute("cy") * scale - (e.clientY - r.top));
      if (dd < bestD) { bestD = dd; best = c; }
    });
    if (!best) { tip.style.display = "none"; return; }
    tip.textContent = best.dataset.tip;
    tip.style.display = "block";
    const wr = wrap.getBoundingClientRect();
    tip.style.left = `${Math.max(0, Math.min(e.clientX - wr.left + 12, wr.width - tip.offsetWidth - 4))}px`;
    tip.style.top = `${e.clientY - wr.top - 34}px`;
  };
  svg.onmouseleave = () => { tip.style.display = "none"; };
  svg.onclick = (e) => { const t = e.target.closest("[data-year]"); if (t) onYear(Number(t.dataset.year)); };
}

function niceTicks(max) {
  const step = max <= 0.8 ? 0.2 : max <= 1.6 ? 0.25 : max <= 3 ? 0.5 : 1;
  const out = [];
  for (let v = step; v <= max + 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}
