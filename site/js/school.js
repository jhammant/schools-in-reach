import { $, $$, esc, fmt, humanize } from "./util.js";
import { state, load, laFile, admissionsFor, toggleShortlist, GROUP_META, on, laName } from "./state.js";
import { renderAdmissions, reachPill } from "./admissions.js";
import { ofstedHeadline } from "./ofsted.js";
import * as mapApi from "./map.js";

const TABS = [
  ["overview", "Overview"],
  ["admissions", "Admissions"],
  ["results", "Results"],
  ["pupils", "Pupils"],
  ["money", "Staff & finance"],
  ["ofsted", "Ofsted & parents"],
  ["destinations", "Leavers"],
];

let current = null;

on("shortlist", () => {
  const btn = $("#view-school [data-action=shortlist]");
  if (btn && current) btn.textContent = state.shortlist.has(current.urn) ? "★ On shortlist" : "☆ Add to shortlist";
});

export async function renderSchool(urn, { tab = "overview", onBack } = {}) {
  const s = state.byUrn.get(Number(urn));
  const root = $("#view-school");
  if (!s) {
    root.innerHTML = `<button class="back" data-action="back">← All schools</button><p class="empty">We couldn't find that school.</p>`;
    $("[data-action=back]", root).onclick = onBack;
    return;
  }
  current = s;
  mapApi.focusSchool(s);
  const meta = GROUP_META[s._class.group];
  const rec = admissionsFor(s.urn);
  const sub = [meta?.label, s._class.independent ? "Independent" : s.type, s.gender, s.age_low != null ? `ages ${s.age_low}–${s.age_high}` : null].filter(Boolean).join(" · ");
  const ofsted = s._ofsted ? `<span class="pill plain">Ofsted: ${esc(s._ofsted)}</span>` : "";

  root.innerHTML = `
    <button class="back" data-action="back">← All schools</button>
    <div class="detail-head">
      <h2>${esc(s.name)}</h2>
      <p class="sub">${esc(sub)}</p>
      <div class="pills">${reachPill(rec, s._dist, s)}${s._dist != null ? `<span class="pill plain">${fmt.mi(s._dist)} from ${esc(state.home?.label || "you")}</span>` : ""}${ofsted}</div>
    </div>
    <div class="actions">
      <button class="btn secondary" data-action="shortlist">${state.shortlist.has(s.urn) ? "★ On shortlist" : "☆ Add to shortlist"}</button>
      ${s.website ? `<a class="btn secondary" href="${esc(/^https?:/i.test(s.website) ? s.website : `https://${s.website}`)}" target="_blank" rel="noopener" style="text-decoration:none">Website ↗</a>` : ""}
    </div>
    <div class="subtabs" role="group" aria-label="School sections">${TABS.map(([id, label]) => `<button data-tab="${id}" aria-pressed="${id === tab}">${label}</button>`).join("")}</div>
    <div id="school-body"></div>`;

  $("[data-action=back]", root).onclick = () => {
    mapApi.clearRings();
    onBack();
  };
  $("[data-action=shortlist]", root).onclick = () => toggleShortlist(s.urn);
  $$("[data-tab]", root).forEach((b) =>
    b.addEventListener("click", () => {
      $$("[data-tab]", root).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      showTab(s, b.dataset.tab);
      history.replaceState(null, "", `#school=${s.urn}${s._la ? `&la=${s._la}` : ""}&tab=${b.dataset.tab}`);
    }),
  );
  showTab(s, tab);
}

async function showTab(s, tab) {
  const body = $("#school-body");
  body.innerHTML = `<p class="muted">Loading…</p>`;
  if (tab !== "admissions") mapApi.clearRings();
  const [detail, ofsted, parentview, characteristics, benchmarks] = await Promise.all([
    laFile(s._la, `schools/${s.urn}.json`),
    laFile(s._la, "ofsted.json"),
    laFile(s._la, "parentview.json"),
    laFile(s._la, "characteristics.json"),
    load("england/benchmarks.json").then((b) => b || load("england/benchmarks.dev.json")),
  ]);
  const admissions = state.laData.get(s._la)?.admissions;
  if (current !== s) return;
  const key = String(s.urn);
  const bench = (section) => benchFor(benchmarks, section, s);
  const renderers = {
    overview: () => overviewHtml(s),
    results: () => resultsHtml(s, detail, bench),
    pupils: () => pupilsHtml(s, detail, characteristics?.schools?.[key], bench),
    money: () => moneyHtml(detail, bench),
    ofsted: () => ofstedHtml(ofsted?.schools?.[key]) + parentViewHtml(parentview, parentview?.schools?.[key]),
    destinations: () => (detail?.destinations ? sectionHtml("Where pupils go next", detail.destinations, benchmarks?.destinations ? { ...benchmarks.destinations, laCode: s._la, localLabel: laName(s._la) } : null) : `<p class="empty">We don't have leaver-destination figures for this school yet.</p>`),
  };
  if (tab === "admissions") {
    renderAdmissions(body, s, admissionsFor(s.urn), mapApi, admissions?.sources);
    return;
  }
  body.innerHTML = renderers[tab]();
}

/* ---------- benchmarks ---------- */

const PHASE_KEYS = ["all", "primary", "secondary", "special", "nursery", "post16", "all_through", "alternative_provision"];

function phaseKey(s) {
  const g = s._class.group;
  if (g === "allthrough") return "secondary";
  return g;
}

/** The local-authority side of a benchmark block: {la: {<code>: ...}} nationally, or the older {hackney: ...}. */
const localSide = (block, laCode) => block?.la?.[laCode] ?? block?.hackney ?? null;

/** Benchmarks are either flat or split by phase ({la: {204: {primary: {...}}}}); pick the school's council and phase. */
function benchFor(benchmarks, section, s) {
  const b = benchmarks?.[section];
  if (!b) return null;
  const pick = (side) => {
    if (!side || typeof side !== "object") return null;
    const split = Object.keys(side).some((k) => PHASE_KEYS.includes(k) && side[k] && typeof side[k] === "object" && !Array.isArray(side[k]));
    return split ? side[phaseKey(s)] || side.all || null : side;
  };
  return { hackney: pick(localSide(b, s._la)), england: pick(b.england), labels: b.labels, year: b.year, laCode: s._la, localLabel: laName(s._la) };
}

/* ---------- generic measure tables ---------- */

const SKIP = new Set(["year", "labels", "trend", "history", "_suppressed", "notes", "note", "source", "sources", "census_date", "period_months", "fsm_pct_source", "salary_year", "method"]);
const COUNT_KEY = /(^|_)(pupils|cohort|count|schools|submissions|headcount|students|eligible|responses|ehcp|sen_support|girls|boys|fte|places|entries|number)(_|$)/;
const MONEY_KEY = /income|expenditure|spend|salary|cost|balance|reserve|revenue|per_pupil|grant|funding|self_generated|staff$|premises|supplies|energy|catering|_costs?$/;

function formatValue(key, label, v, parent = "") {
  if (v == null || v === "") return "–";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v !== "number") return esc(v);
  const k = key.toLowerCase();
  const ctx = `${parent} ${key} ${label}`.toLowerCase();
  if (/pct|percent|%|_rate/.test(k) || /\bpercent|%/.test(String(label))) return fmt.pct(v, 1);
  if (COUNT_KEY.test(k)) return Number.isInteger(v) ? fmt.num(v) : v.toFixed(1);
  if (/progress|value_added|\bva\b|p8|ci_lower|ci_upper|score/.test(ctx) && !/attainment|aps|scaled/.test(k)) return fmt.signed(v);
  if (MONEY_KEY.test(k) || /income|expenditure|per_pupil|finance/.test(parent)) return fmt.money(v);
  return Number.isInteger(v) ? fmt.num(v) : v.toFixed(2);
}

function measureTable(obj, bench, parent = "") {
  if (!obj || typeof obj !== "object") return "";
  const labels = { ...(bench?.labels && typeof bench.labels === "object" ? bench.labels : {}), ...(obj.labels || {}) };
  const hack = bench?.hackney || null;
  const eng = bench?.england || null;
  const hasBench = Boolean(hack || eng);
  const rows = [];
  const nested = [];
  const notes = [];
  Object.entries(obj).forEach(([key, v]) => {
    if (/_note$/.test(key) && typeof v === "string") { notes.push(v); return; }
    if (SKIP.has(key) || key.startsWith("_")) return;
    if (v && typeof v === "object" && !Array.isArray(v)) { nested.push([key, v]); return; }
    if (Array.isArray(v)) return;
    const label = typeof labels[key] === "string" ? labels[key] : humanize(key);
    const suppressed = (obj._suppressed || []).includes(key);
    const bh = hack && typeof hack[key] !== "object" ? hack[key] : undefined;
    const be = eng && typeof eng[key] !== "object" ? eng[key] : undefined;
    rows.push(`<tr><td>${esc(label)}</td><td class="num"><strong>${suppressed ? "not shown" : formatValue(key, label, v, parent)}</strong></td>${hasBench ? `<td class="num">${formatValue(key, label, bh, parent)}</td><td class="num">${formatValue(key, label, be, parent)}</td>` : ""}</tr>`);
  });
  let html = rows.length
    ? `<table><thead><tr><th>Measure</th><th class="num">School</th>${hasBench ? `<th class="num">${esc(bench.localLabel || "Council")}</th><th class="num">England</th>` : ""}</tr></thead><tbody>${rows.join("")}</tbody></table>`
    : "";
  if (notes.length) html += `<p class="note">${notes.map(esc).join(" ")}</p>`;
  nested.forEach(([key, v]) => {
    let childBench = null;
    const block = bench?.[key];
    if (block && (block.la || block.hackney || block.england)) childBench = { hackney: localSide(block, bench.laCode), england: block.england, labels: block.labels || bench.labels?.[key], laCode: bench.laCode, localLabel: bench.localLabel };
    else if (hack?.[key] || eng?.[key]) childBench = { hackney: hack?.[key], england: eng?.[key], labels: labels[key] && typeof labels[key] === "object" ? labels[key] : null, laCode: bench?.laCode, localLabel: bench?.localLabel };
    const title = typeof labels[key] === "string" ? labels[key] : humanize(key);
    html += `<h4 style="margin:14px 0 6px;font-size:13px">${esc(title)}${v.year ? ` <span class="muted small">${esc(v.year)}</span>` : ""}</h4>${v.note ? `<p class="note">${esc(v.note)}</p>` : ""}${measureTable(v, childBench, `${parent} ${key}`)}${trendTable(v.trend || v.history, v.labels)}`;
  });
  return html;
}

function trendTable(trend, labels = {}) {
  if (!trend) return "";
  const entries = Array.isArray(trend) ? trend.map((t) => [t.year, t]) : Object.entries(trend);
  if (entries.length < 2) return "";
  const keys = [...new Set(entries.flatMap(([, t]) => Object.keys(t).filter((k) => k !== "year" && t[k] != null && typeof t[k] !== "object")))];
  if (!keys.length) return "";
  const label = (k) => (typeof labels?.[k] === "string" ? labels[k] : humanize(k));
  return `<h4 style="margin:14px 0 6px;font-size:13px">Recent years</h4><div style="overflow-x:auto"><table><thead><tr><th>Year</th>${keys.map((k) => `<th class="num">${esc(label(k))}</th>`).join("")}</tr></thead><tbody>${entries
    .map(([yr, t]) => `<tr><td>${esc(yr)}</td>${keys.map((k) => `<td class="num">${formatValue(k, label(k), t[k])}</td>`).join("")}</tr>`)
    .join("")}</tbody></table></div>`;
}

function sectionHtml(title, obj, bench) {
  if (!obj) return "";
  return `<h3 class="section">${esc(title)}${obj.year ? ` <span class="muted">· ${esc(obj.year)}</span>` : ""}</h3>${obj.note ? `<p class="note">${esc(obj.note)}</p>` : ""}${measureTable(obj, bench)}${trendTable(obj.trend || obj.history, obj.labels)}${obj.notes ? `<p class="note">${esc([].concat(obj.notes).join(" "))}</p>` : ""}`;
}

/* ---------- tabs ---------- */

function overviewHtml(s) {
  const address = [s.street, s.locality, s.town, s.postcode].filter(Boolean).join(", ");
  const fill = s.capacity && s.pupils ? Math.round((100 * s.pupils) / s.capacity) : null;
  const yesNo = (v) => (typeof v === "boolean" ? (v ? "Yes" : "No") : v);
  const rows = [
    ["Address", esc(address)],
    ["Headteacher", esc(s.head)],
    ["Phone", esc(s.phone)],
    ["Type", esc(s.type)],
    ["Trust or federation", esc(s.trust || s.federation)],
    ["Religious character", esc(s.religious_character)],
    ["Admissions policy", esc(s.admissions_policy)],
    ["Sixth form", esc(yesNo(s.sixth_form))],
    ["Nursery provision", esc(yesNo(s.nursery_provision))],
    ["Special needs (SEN) provision", esc((s.sen_provision || []).join("; "))],
    ["Specialist unit (resourced provision)", s.resourced_provision ? esc([s.resourced_provision.type, s.resourced_provision.on_roll != null ? `${s.resourced_provision.on_roll} on roll` : null, s.resourced_provision.capacity != null ? `capacity ${s.resourced_provision.capacity}` : null].filter(Boolean).join(" · ")) : ""],
    ["Ward", esc(s.ward)],
    ["Neighbourhood", esc(s.lsoa_name)],
    ["Opened", esc(s.open_date ? fmt.date(s.open_date) : "")],
  ].filter(([, v]) => v);
  return `
    <div class="stats">
      <div class="stat"><b>${fmt.num(s.pupils)}</b><span>pupils${s.capacity ? ` of ${fmt.num(s.capacity)} places` : ""}</span></div>
      <div class="stat"><b>${fill != null ? `${fill}%` : "–"}</b><span>full</span></div>
      <div class="stat"><b>${fmt.pct(s.fsm_pct, 1)}</b><span>free school meals (lower income)</span></div>
      <div class="stat"><b style="font-size:16px">${esc(s._ofsted || "–")}</b><span>Ofsted</span></div>
    </div>
    <h3 class="section">Details</h3>
    <table><tbody>${rows.map(([k, v]) => `<tr><th style="width:38%">${k}</th><td>${v}</td></tr>`).join("")}</tbody></table>
    <p class="note">School register details come from the Department for Education's Get Information About Schools service. URN ${s.urn}.</p>`;
}

function resultsHtml(s, d, bench) {
  if (!d) return `<p class="empty">We couldn't find exam results for this school yet.</p>`;
  const html = [
    sectionHtml("Key stage 2 (end of primary)", d.ks2, bench("ks2")),
    sectionHtml("GCSE / key stage 4", d.ks4, bench("ks4")),
    sectionHtml("Sixth form / 16–18", d.ks5, bench("ks5")),
  ].join("");
  return html || `<p class="empty">${s._class.independent ? "Independent schools don't have to publish results in the national performance tables, so none are shown here." : "No exam results are published for this school yet."}</p>`;
}

function pupilsHtml(s, d, chars, bench) {
  let html = "";
  if (d?.census) html += sectionHtml("Pupils", d.census, bench("census"));
  if (chars) {
    const eth = chars.ethnicity_pct;
    if (eth) {
      const entries = Object.entries(eth).filter(([, v]) => typeof v === "number").sort((a, b) => b[1] - a[1]);
      html += `<h3 class="section">Ethnicity <span class="muted">· January 2026 census</span></h3>
        <table><tbody>${entries.map(([k, v]) => `<tr><td>${esc(humanize(k))}</td><td class="num" style="width:60px">${fmt.pct(v, 1)}</td><td style="width:45%"><div class="bar"><i style="width:${Math.min(100, v)}%"></i></div></td></tr>`).join("")}</tbody></table>`;
      if (chars.ethnicity_detail_pct) {
        html += `<details><summary>Detailed ethnic groups</summary><table><tbody>${Object.entries(chars.ethnicity_detail_pct)
          .filter(([, v]) => typeof v === "number" && v > 0)
          .sort((a, b) => b[1] - a[1])
          .map(([k, v]) => `<tr><td>${esc(humanize(k))}</td><td class="num">${fmt.pct(v, 1)}</td></tr>`)
          .join("")}</tbody></table></details>`;
      }
    }
    const rest = Object.fromEntries(Object.entries(chars).filter(([k]) => !["name", "phase", "establishment_type", "sex_of_school", "ethnicity_pct", "ethnicity_detail_pct", "ethnicity_base"].includes(k)));
    html += sectionHtml("Characteristics & class sizes", rest, null);
  }
  if (d?.absence) html += sectionHtml("Attendance", d.absence, bench("absence"));
  if (s.sen_provision?.length) html += `<h3 class="section">Special educational needs provision</h3><p>${esc(s.sen_provision.join("; "))}</p>`;
  return html || `<p class="empty">We don't have pupil data for this school yet.</p>`;
}

function moneyHtml(d, bench) {
  const html = sectionHtml("Workforce", d?.workforce, bench("workforce")) + sectionHtml("Finance", d?.finance, bench("finance"));
  return html || `<p class="empty">We don't have staff or finance figures for this school yet.</p>`;
}

const JUDGEMENT_LABELS = {
  overall_effectiveness: "Overall effectiveness",
  quality_of_education: "Quality of education",
  behaviour_and_attitudes: "Behaviour and attitudes",
  personal_development: "Personal development",
  leadership_and_management: "Leadership and management",
  safeguarding_effective: "Safeguarding effective",
  early_years: "Early years",
  sixth_form: "Sixth form",
  safeguarding_standards: "Safeguarding standards",
  inclusion: "Inclusion",
  curriculum_and_teaching: "Curriculum and teaching",
  achievement: "Achievement",
  attendance_and_behaviour: "Attendance and behaviour",
  personal_development_and_wellbeing: "Personal development and well-being",
  post_16: "Post-16",
  leadership_and_governance: "Leadership and governance",
};

function gradesTable(grades) {
  const rows = Object.entries(grades || {}).filter(([, v]) => v != null && v !== "Not applicable");
  if (!rows.length) return "";
  return `<table><tbody>${rows.map(([k, v]) => `<tr><td>${esc(JUDGEMENT_LABELS[k] || humanize(k))}</td><td><strong>${esc(typeof v === "boolean" ? (v ? "Yes" : "No") : v)}</strong></td></tr>`).join("")}</tbody></table>`;
}

function inspectionHtml(title, insp) {
  if (!insp) return "";
  const when = [insp.date ? fmt.date(insp.date) : null, insp.type].filter(Boolean).join(" · ");
  let body = "";
  if (insp.kind === "report_card") body = `<p class="small">Report card inspection (the newer framework, from November 2025). Schools get a grade for each area rather than one overall grade.</p>${gradesTable(insp.report_card)}`;
  else if (insp.kind === "ungraded") body = `<p><strong>${esc(insp.outcome || "Ungraded inspection")}</strong></p>`;
  else if (insp.judgements) body = gradesTable(insp.judgements);
  else if (insp.overall_effectiveness) body = gradesTable({ overall_effectiveness: insp.overall_effectiveness });
  return `<h3 class="section">${esc(title)}${when ? ` <span class="muted">· ${esc(when)}</span>` : ""}</h3>${body}`;
}

function ofstedHtml(o) {
  if (!o) return `<p class="empty">We couldn't find any inspection reports for this school yet.</p>`;
  if (o.inspectorate === "ISI") {
    return `<h3 class="section">Inspection</h3><p>${esc(o.note || "Inspected by the Independent Schools Inspectorate.")}</p>${o.isi_url ? `<p><a href="${esc(o.isi_url)}" target="_blank" rel="noopener">Read this school's ISI reports ↗</a></p>` : ""}`;
  }
  let html = o.latest ? inspectionHtml("Latest inspection", o.latest) : `<p class="empty">This school hasn't had a published inspection yet.</p>`;
  if (o.latest?.kind === "ungraded" && o.last_graded) html += inspectionHtml("Most recent graded inspection", o.last_graded);
  if (o.previous && o.previous !== o.last_graded) html += inspectionHtml("Previous inspection", o.previous);
  if (o.independent_standards) html += `<h3 class="section">Independent school standards</h3>${gradesTable(o.independent_standards)}`;
  if (o.report_url) html += `<p><a href="${esc(o.report_url)}" target="_blank" rel="noopener">Read the Ofsted reports ↗</a></p>`;
  return html;
}

function parentViewHtml(pv, entry) {
  if (!entry) return `<h3 class="section">Ofsted Parent View</h3><p class="note">Ofsted's Parent View survey is only published for schools with at least 10 responses, and this school doesn't have one yet.</p>`;
  const survey = entry.current || entry.previous_question_set;
  if (!survey) return "";
  const release = pv.releases?.[survey.release];
  const set = pv.question_sets?.[release?.question_set] || {};
  const rows = Object.entries(survey.responses || {}).map(([q, answers]) => {
    const text = set[q]?.text || q;
    const agree = answers["Strongly agree"] != null ? (answers["Strongly agree"] || 0) + (answers.Agree || 0) : null;
    if (agree != null) {
      return `<tr><td>${esc(text)}</td><td class="num" style="width:56px">${fmt.pct(agree)}</td><td style="width:28%"><div class="bar"><i style="width:${Math.min(100, agree)}%"></i></div></td></tr>`;
    }
    const parts = Object.entries(answers).filter(([, v]) => v != null).map(([a, v]) => `${esc(a)} ${v}%`).join(" · ");
    return `<tr><td>${esc(text)}</td><td colspan="2" class="small">${parts}</td></tr>`;
  });
  return `
    <h3 class="section">Ofsted Parent View <span class="muted">· ${esc(release?.title?.replace(/^Parent View management information: /i, "") || survey.release)}</span></h3>
    <p class="small">${fmt.num(survey.submissions)} parent responses${survey.response_rate_pct != null ? ` (${fmt.pct(survey.response_rate_pct, 0)} of pupils)` : ""}.${entry.current ? "" : " These answers come from the previous version of the survey, before Ofsted changed the questions in November 2025."}</p>
    <table><tbody>${rows.join("")}</tbody></table>
    <p class="note">Percentages show parents who agreed or strongly agreed, where the question uses that scale.</p>`;
}

export { ofstedHeadline };
