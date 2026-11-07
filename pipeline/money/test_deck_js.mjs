// Pure-model tests for assets/deck.js under node (no DOM, no network).
// Run: node --test pipeline/money/test_deck_js.mjs (test_deck_js.py runs it from pytest).
// Fixtures are built here from pipeline/money/data/gold/130932.json (William Patten Primary School);
// figures are asserted against that file, never against copied literals. The IFS context is the JSON
// deck.py writes: test_deck_js.py passes it in DECK_CONTEXT_FILE, otherwise python3 builds it here.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// Arrange (shared): stubs before the scripts run; no network.
const memory = new Map();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: { getItem: (k) => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, String(v)), removeItem: (k) => memory.delete(k) },
});
globalThis.fetch = () => Promise.reject(new Error("no network in tests"));
const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
await import(pathToFileURL(join(here, "assets", "app.js")).href);
await import(pathToFileURL(join(here, "assets", "deck.js")).href);
const D = globalThis.MoneyDeck;
const A = globalThis.MoneyApp;

const CTX = process.env.DECK_CONTEXT_FILE
  ? JSON.parse(readFileSync(process.env.DECK_CONTEXT_FILE, "utf8"))
  : JSON.parse(execFileSync("python3", ["-c", "import json; from pipeline.money import deck; print(json.dumps(deck.deck_context()))"], { cwd: repo, encoding: "utf8" }));

// ---------------------------------------------------------------- fixtures from the gold file
const gold = JSON.parse(readFileSync(join(here, "data", "gold", "130932.json"), "utf8"));
const deflator = JSON.parse(readFileSync(join(here, "data", "gdp_deflator.json"), "utf8"));
const YEARS = Object.keys(gold.years).sort();
const LATEST = YEARS[YEARS.length - 1];
const fin = (y) => gold.years[y].totals.pipeline_finance_history;
const staffTotal = (y) => Object.entries(gold.years[y].totals.workbook_derived_columns).find(([k]) => k.startsWith("Staff Total"))[1];
const donations = (y) => (gold.years[y].lines.I13 || {}).value ?? null;
const pupils = (y) => fin(y).pupils;
const ppOf = (v, y) => Math.round(v / pupils(y));
const ptfaYears = Object.keys(gold.ptfa.years).sort();
const ptfaEnd = (y) => gold.ptfa.years[y].period.slice(-10);
// The school year the producer counts each charity return in (series.pta_year), as /data/sx keys sx.pta.
const PTA_SCHOOL_YEARS = JSON.parse(execFileSync("python3", ["-c", "import json, sys; from pipeline.money import series; print(json.dumps({e: series.pta_year(e, 'CFR') for e in sys.argv[1:]}))", ...ptfaYears.map(ptfaEnd)], { cwd: repo, encoding: "utf8" }));
const ptaSchoolYear = (y) => PTA_SCHOOL_YEARS[ptfaEnd(y)];

function sxFixture({ flags = [], drop = [] } = {}) {
  const m = {};
  const add = (key, y, v) => {
    if (v == null) return;
    const idx = deflator.financial_years[y];
    (m[key] ||= {})[y] = { v, pp: v / pupils(y), r: idx ? (v * 100) / idx : null, rpp: idx ? (v * 100) / idx / pupils(y) : null };
  };
  for (const y of YEARS) {
    for (const k of ["total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "grant_funding", "self_generated", "sen_funding", "pupil_premium"]) {
      if (!drop.includes(k)) add(k, y, fin(y)[k]);
    }
    add("staff_total", y, staffTotal(y));
    add("donations_revenue", y, donations(y));
  }
  const pta = {};
  for (const y of ptfaYears) {
    const p = gold.ptfa.years[y], sy = ptaSchoolYear(y);
    pta[sy] = { income: p.income, spend: p.expenditure, income_pp: pupils(sy) ? p.income / pupils(sy) : null, spend_pp: pupils(sy) ? p.expenditure / pupils(sy) : null, charity_number: String(gold.ptfa.charity_number), confidence: "high" };
  }
  return { years: YEARS, source: "CFR", pupils: Object.fromEntries(YEARS.map((y) => [y, pupils(y)])), m, gap: null, pta, flags, trust_central_pp: null };
}

function sFixture({ withPta = true } = {}) {
  const f = fin(LATEST);
  const reserve = f.revenue_reserve;
  const status = reserve < 0 ? "in_deficit" : "healthy";
  let streak = 0;
  for (const y of [...YEARS].reverse()) { if (fin(y).in_year_balance < 0) streak++; else break; }
  return {
    urn: gold.urn, name: gold.name, path: "/school/" + gold.urn + "-william-patten-primary-school/",
    council: { code: gold.la.code, name: gold.la.name, path: "/council/hackney/" },
    status, label: D.LABELS[status],
    reason: "In deficit by " + A.fmtMoney(-reserve) + ", " + Math.round((100 * -reserve) / f.total_income) + "% of a year's income: it has spent more over the years than it received.",
    year: LATEST, academy: false, trust: null, pupils: f.pupils,
    income: Math.round(f.total_income), income_pp: ppOf(f.total_income, LATEST), spend: Math.round(f.total_expenditure), spend_pp: ppOf(f.total_expenditure, LATEST),
    reserve: Math.round(reserve), reserve_pp: ppOf(reserve, LATEST), share: reserve / f.total_income, balance: Math.round(f.in_year_balance), streak,
    years: YEARS.map((y) => ({ y, income: Math.round(fin(y).total_income), spend: Math.round(fin(y).total_expenditure), balance: Math.round(fin(y).in_year_balance), reserve: Math.round(fin(y).revenue_reserve), pupils: pupils(y), status: null })),
    pp: { total_income: ppOf(f.total_income, LATEST), total_expenditure: ppOf(f.total_expenditure, LATEST), teaching_staff: ppOf(gold.years[LATEST].lines.E01.value, LATEST) },
    // Similar-school medians are not in the gold file: synthetic values for the comparison slide.
    similar: { total_income: 8800, total_expenditure: 9000, teaching_staff: 4100 },
    income_lines: { grant_funding: Math.round(f.grant_funding), sen_funding: Math.round(f.sen_funding), pupil_premium: Math.round(f.pupil_premium), self_generated_income: Math.round(f.self_generated), donations_revenue: Math.round(donations(LATEST)) },
    lines: {},
    pta: withPta ? [{
      charity_number: String(gold.ptfa.charity_number), name: gold.ptfa.name, status: gold.ptfa.status, latest_income: gold.ptfa.latest.income,
      history: ptfaYears.map((y) => ({ period_end: ptfaEnd(y), income: gold.ptfa.years[y].income, expenditure: gold.ptfa.years[y].expenditure })),
    }] : [],
    tags: { governance: "council-run" }, phase: "primary", band: 3,
  };
}

// Synthetic area documents (the shape of /data/a/<id>.json); only the shape matters here.
function S(n, pct, extra = {}) {
  return { schools: n, in_deficit: Math.round((n * pct) / 100), in_deficit_pct: pct, heading: 3, deficit_total: -2.5e6, deficit_pp: -400, reserve_median_pp: 310,
    income_pp_median: 8900, spend_pp_median: 8950, grant_pp_median: 8300, pta_pp_median: 52, pta_schools: 24, donations_pp_median: 40, ...extra };
}
function areaDoc(id, type, name, scale = 1) {
  const by_year = {}, pupils_by_year = {}, schools_by_year = {}, dsg = {};
  YEARS.forEach((y, i) => {
    by_year[y] = { all: S(60 * scale, 10 + i), "council-run": S(40 * scale, 12 + i), academy: { schools: 4, in_deficit: null, in_deficit_pct: null } };
    pupils_by_year[y] = 25000 * scale; schools_by_year[y] = 60 * scale;
    dsg[y] = { balance: -1e6 * (i + 1), per_pupil: (-1e6 * (i + 1)) / (25000 * scale) };
  });
  return { id, type, name, path: type === "england" ? "/" : "/" + type + "/" + name.toLowerCase().replace(/\W+/g, "-") + "/", pupils_by_year, schools_by_year, by_year, dsg,
    statuses_latest: { in_deficit: 9, heading_for_deficit: 3, tight: 8, healthy: 30, large_reserves: 10 } };
}
const COUNCIL = areaDoc("council-" + gold.la.code, "council", gold.la.name);
const ENGLAND = areaDoc("england", "england", "England", 300);
const CONSTITUENCY = areaDoc("constituency-E14001063", "constituency", "Hackney North and Stoke Newington");

// A synthetic 'nearby' block following the shared contract exactly (N1 writes the real one into /data/s).
const NEAR_YEAR = YEARS[YEARS.length - 2];
function nearbyFixture() {
  const y = NEAR_YEAR, f = fin(y);
  const self = {
    urn: gold.urn, name: gold.name, p: "/school/" + gold.urn + "-william-patten-primary-school/", mi: 0, status: "in_deficit", pupils: pupils(y),
    spend_pp: ppOf(f.total_expenditure, y), income_pp: ppOf(f.total_income, y), gov_pp: ppOf(f.grant_funding, y), reserve_pp: ppOf(f.revenue_reserve, y),
    staff_pct: Math.round((1000 * staffTotal(y)) / f.total_expenditure) / 10, fsm_pct: f.fsm_pct,
    lines: { teaching_staff: ppOf(gold.years[y].lines.E01.value, y), education_support_staff: ppOf(gold.years[y].lines.E03.value, y) },
  };
  const row = (n, mi, extra) => ({ urn: String(100000 + n), name: "Neighbour " + n + " Primary School", p: "/school/" + (100000 + n) + "-neighbour-" + n + "/", mi, ...extra });
  return {
    year: y, phase: "Primary", radius_mi: 0.9, self,
    schools: [
      row(1, 0.2, { status: "healthy", pupils: 410, spend_pp: 7900, income_pp: 8000, gov_pp: 7400, reserve_pp: 420, staff_pct: 74.1, pta_pp: 30, pta_year: "2023-24", fsm_pct: 31.2 }),
      row(2, 0.4, { academy: true, status: "tight", pupils: 380, spend_pp: 7600, income_pp: 7650, gov_pp: 7300, reserve_pp: 90, staff_pct: 76.0, pta_pp: 55, pta_year: "2024-25", pta_confidence: "medium", fsm_pct: 22.5 }),
      row(3, 0.5, { status: "large_reserves" }),
      row(4, 0.7, { pupils: 205.5, spend_pp: 8400, reserve_pp: 900, fsm_pct: 40 }),
      row(5, 0.9, { status: "in_deficit", pupils: 600, spend_pp: 8100, income_pp: 7950, gov_pp: 7500, reserve_pp: -150, staff_pct: 79.9, fsm_pct: 35 }),
    ],
    medians: { spend_pp: 8100, income_pp: 7975, gov_pp: 7400, reserve_pp: 90 },
    rank: { spend_pp: { rank: 1, of: 6 }, reserve_pp: { rank: 6, of: 6 } },
    line_medians: { teaching_staff: 3500, education_support_staff: 1250, premises: 300 },
  };
}
const schoolModel = (opts = {}) => {
  const s = sFixture(opts);
  if (opts.nearby) s.nearby = opts.nearby === true ? nearbyFixture() : opts.nearby;
  return D.adapt(s, opts.noSx ? null : sxFixture(opts), opts.council === undefined ? COUNCIL : opts.council, ENGLAND);
};
const CTXT = { ...CTX, today: "2026-11-07" };
const PACK_ORDER = {
  governors: ["title", "summary", "budget", "funding", "income", "where_money_goes", "nearby", "nearby_table", "nearby_table_2", "pupils", "pressures", "council", "questions", "actions", "sources"],
  ptfa: ["title", "summary", "pta_money", "pta_compare", "pta_spent", "school_brief", "ideas", "questions", "actions", "sources"],
  ptfaNone: ["title", "summary", "not_found", "donations", "pta_compare", "school_brief", "ideas", "questions", "actions", "sources"],
  review: ["title", "summary", "dashboard", "income_mix", "trends", "reserve_trajectory", "nearby", "nearby_table", "nearby_table_2", "questions", "actions", "sources"],
};
// A fake PptxGenJS that records every call (no network, no file).
function fakePptx() {
  const calls = { slides: [], file: null, layout: null };
  class FakePptx {
    constructor() { this.ChartType = { line: "line", bar: "bar" }; }
    set layout(v) { calls.layout = v; }
    addSlide() {
      const rec = { texts: [], charts: [], tables: [], notes: null };
      calls.slides.push(rec);
      return { set background(v) { rec.background = v; }, addText: (t, o) => rec.texts.push([t, o]), addChart: (type, data, o) => rec.charts.push({ type, data, o }),
        addTable: (rows, o) => rec.tables.push({ rows, o }), addNotes: (n) => { rec.notes = n; } };
    }
    writeFile(opts) { calls.file = opts.fileName; return Promise.resolve(opts.fileName); }
  }
  return { calls, FakePptx };
}
const findSlide = (deck, id) => deck.slides.find((s) => s.id === id);
const seriesOf = (sl, key) => sl.chart.series.find((s) => s.key === key);

function strings(value, out = []) {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => strings(v, out));
  else if (value && typeof value === "object") Object.values(value).forEach((v) => strings(v, out));
  return out;
}
const BANNED = ["poor" + " school", "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", "no " + "pta", "307" + "k"];
function assertClean(deck, label) {
  for (const s of strings(deck)) {
    const low = s.toLowerCase();
    for (const w of BANNED) assert.ok(!low.includes(w), `${label}: banned phrase in ${JSON.stringify(s.slice(0, 120))}`);
  }
}

// ---------------------------------------------------------------- tests
test("MoneyDeck exports its API and pins PptxGenJS 3.12.0", () => {
  for (const k of ["adapt", "schoolDeck", "governorsDeck", "ptfaDeck", "reviewDeck", "packDeck", "packView", "compareDeck", "areaDeck", "nextIndex", "buildPptx",
    "chartData", "fmtExact", "summaryMessages", "notesKey", "loadSaved", "saveSaved", "applySaved", "ptaTarget", "speakerNotes"]) assert.equal(typeof D[k], "function", k);
  assert.equal(D.governorsDeck, D.schoolDeck);
  assert.equal(D.PPTX_URL, "https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js");
});

test("fmtExact, fmtPupils and fmtDate", () => {
  assert.equal(D.fmtExact(4115.4), "£4,115");
  assert.equal(D.fmtExact(-488), "-£488");
  assert.equal(D.fmtExact(null), "—");
  assert.equal(D.fmtPupils(432.5), "432.5");
  assert.equal(D.fmtPupils(432.54), "432.5");
  assert.equal(D.fmtPupils(435), "435");
  assert.equal(D.fmtDate("2026-11-07"), "7 November 2026");
});

test("view=school, no view and view=governors all build the governors' pack; other views are not packs", () => {
  // Arrange
  const m = schoolModel();
  // Act / Assert
  for (const v of ["school", "governors", "", undefined, "SCHOOL"]) assert.equal(D.packView(v), "governors", String(v));
  assert.equal(D.packView("ptfa"), "ptfa");
  assert.equal(D.packView("review"), "review");
  assert.equal(D.packView("compare"), null);
  assert.deepEqual(D.packDeck("school", m, CTXT).slides.map((s) => s.id), D.schoolDeck(m, CTXT).slides.map((s) => s.id));
  assert.equal(D.packDeck("school", m, CTXT).kind, "governors");
  assert.equal(D.packDeck("review", m, CTXT).kind, "review");
  assert.equal(D.packDeck("compare", m, CTXT), null);
});

test("every pack: slides in order and well-formed for William Patten", () => {
  const cases = [
    ["governors", D.schoolDeck(schoolModel({ nearby: true }), CTXT), PACK_ORDER.governors],
    ["ptfa", D.ptfaDeck(schoolModel({ nearby: true }), CTXT), PACK_ORDER.ptfa],
    ["ptfa without a PTA", D.ptfaDeck(schoolModel({ withPta: false }), CTXT), PACK_ORDER.ptfaNone],
    ["review", D.reviewDeck(schoolModel({ nearby: true }), CTXT), PACK_ORDER.review],
  ];
  for (const [label, deck, order] of cases) {
    // Assert: order, unique ids, titles
    assert.deepEqual(deck.slides.map((s) => s.id), order, label);
    assert.equal(new Set(deck.slides.map((s) => s.id)).size, deck.slides.length, label + " ids unique");
    assert.ok(deck.filename.endsWith(" - School Money.pptx") && deck.filename.startsWith(gold.name), deck.filename);
    for (const sl of deck.slides) {
      for (const k of ["id", "kind", "title", "lead", "bullets", "figures", "chart", "note", "notes", "sources"]) assert.ok(k in sl, label + " " + sl.id + " lacks " + k);
      assert.ok(sl.title, label + " " + sl.id + " title");
      assert.ok(sl.sources.length > 0, label + " " + sl.id + " has sources");
      for (const f of sl.figures) {
        assert.ok(f.year && f.source, label + " " + sl.id + " figure carries year and source");
        assert.ok(f.text.includes(f.year) && f.text.includes(f.source), label + " " + sl.id + " figure text names year and source");
      }
      if (sl.chart) {
        assert.ok(["line", "bar", "stack"].includes(sl.chart.type));
        assert.ok(sl.chart.alt && sl.chart.series.every((s) => s.points.every((p) => "y" in p && "v" in p && "suspect" in p)));
      }
      if (sl.table) for (const r of sl.table.rows) assert.equal(r.cells.length, sl.table.columns.length, label + " " + sl.id + " row width");
    }
    // Title: editable meeting line prefilled per pack, today's date injected.
    const title = deck.slides[0];
    assert.equal(title.meta.date, "7 November 2026");
    assert.equal(title.meta.preparedFor, D.PACKS[deck.view].meeting, label);
    assert.ok(title.lead.includes(D.fmtPupils(pupils(LATEST))), "title shows pupils to 1 dp");
    assert.ok(title.lead.includes(gold.la.name));
    // Actions: editable rows, and the sources slide links FBIT.
    const acts = deck.slides.find((s) => s.id === "actions");
    assert.ok(acts.actions.length >= 3 && acts.actions.every((a) => "action" in a && "owner" in a && "by" in a));
    const sources = deck.slides.at(-1);
    assert.equal(sources.title, "Sources and how to check");
    assert.ok(sources.links.some((l) => l.href === CTX.links.fbit + gold.urn), label + " FBIT link");
  }
  const meetings = cases.map(([, d]) => d.slides[0].meta.preparedFor);
  assert.deepEqual([...new Set(meetings)], ["Governors' finance committee", "PTFA committee meeting", "School financial review"]);
});

test("governors' pack: every £ figure equals the gold file, per pupil = round(v / same-year pupils)", () => {
  // Arrange
  const keyed = { total_income: "total_income", total_expenditure: "total_expenditure", grant_funding: "grant_funding", revenue_reserve: "revenue_reserve", in_year_balance: "in_year_balance" };
  let checked = 0;
  for (const deck of [D.schoolDeck(schoolModel({ nearby: true }), CTXT), D.reviewDeck(schoolModel({ nearby: true }), CTXT)]) {
    // Act / Assert: figures
    for (const sl of deck.slides) {
      for (const f of sl.figures) {
        if (!keyed[f.key] || !gold.years[f.year]) continue;
        const v = fin(f.year)[keyed[f.key]];
        assert.equal(f.v, Math.round(v), `${sl.id} ${f.key} ${f.year} total`);
        assert.equal(f.pp, ppOf(v, f.year), `${sl.id} ${f.key} ${f.year} per pupil`);
        checked++;
      }
    }
  }
  assert.ok(checked >= 8, "figures checked: " + checked);
  // Assert: chart series, every year
  const deck = D.schoolDeck(schoolModel(), CTXT);
  const funding = findSlide(deck, "funding");
  for (const key of ["grant_funding", "total_income", "total_expenditure"]) {
    const s = seriesOf(funding, key);
    assert.deepEqual(s.points.map((p) => p.y), YEARS);
    s.points.forEach((p) => assert.equal(p.v, ppOf(fin(p.y)[key], p.y), `${key} ${p.y}`));
  }
  const budget = findSlide(deck, "budget");
  for (const key of ["in_year_balance", "revenue_reserve"]) seriesOf(budget, key).points.forEach((p) => assert.equal(p.v, ppOf(fin(p.y)[key], p.y), key + " " + p.y));
  // The review pack's trends table: per pupil with the total beside, every year.
  const trends = findSlide(D.reviewDeck(schoolModel(), CTXT), "trends");
  for (const y of ["2019-20", LATEST]) {
    const row = trends.table.rows.find((r) => r.cells[0].text === y);
    assert.ok(row.cells[5].text.includes(D.fmtExact(ppOf(fin(y).revenue_reserve, y))) && row.cells[5].text.includes(A.fmtMoney(fin(y).revenue_reserve)), y);
    assert.equal(row.cells[1].text, D.fmtPupils(pupils(y)));
  }
});

test("summary: the three key messages for William Patten come from the gold file", () => {
  // Arrange
  const m = schoolModel();
  const f = fin(LATEST);
  let run = 0;
  for (const y of [...YEARS].reverse()) { if (fin(y).revenue_reserve < 0) run++; else break; }
  const words = ["", "first", "second", "third", "fourth", "fifth"];
  const peakY = YEARS.reduce((a, y) => (fin(y).revenue_reserve > fin(a).revenue_reserve ? y : a), YEARS[0]);
  const spendPp = f.total_expenditure / f.pupils;
  const sim = sFixture().similar.total_expenditure;
  // Act
  const msgs = D.summaryMessages(m, CTXT, "governors");
  const slideMsgs = findSlide(D.schoolDeck(m, CTXT), "summary").messages;
  // Assert
  assert.deepEqual(slideMsgs, msgs);
  assert.equal(msgs.length, 3);
  assert.equal(msgs[0], "In deficit by " + A.fmtMoney(-f.revenue_reserve) + " (" + Math.round((100 * -f.revenue_reserve) / f.total_income) + "% of a year's income) at the end of " +
    LATEST + (run >= 2 ? ", the " + words[run] + " year running" : ""));
  assert.ok(run >= 2, "gold has a multi-year deficit");
  const diff = Math.round(spendPp) - sim;
  assert.equal(msgs[1], "Spends " + D.fmtExact(spendPp) + " per pupil in " + LATEST + ", " + D.fmtExact(Math.abs(diff)) + (diff > 0 ? " more" : " less") +
    " than similar schools' median; staff costs are " + Math.round((100 * staffTotal(LATEST)) / f.total_expenditure) + "% of spending");
  assert.ok(msgs[2].startsWith("The reserve fell from " + D.fmtExact(fin(peakY).revenue_reserve) + " in " + peakY + " to " + D.fmtExact(f.revenue_reserve) + " in " + LATEST), msgs[2]);
  // The deficit is named beside its reasons and what helps.
  const summary = findSlide(D.schoolDeck(m, CTXT), "summary");
  assert.ok(summary.note.startsWith("Why this happens") && summary.note.includes("IFS pp.62–63"));
  assert.ok(summary.note.includes("What helps: a recovery plan agreed with the council"));
});

test("ratings: in-year balance and reserve carry icon, word and the right level", () => {
  // Arrange
  const f = fin(LATEST);
  const share = f.in_year_balance / f.total_income;
  let run = 0;
  for (const y of [...YEARS].reverse()) { if (fin(y).in_year_balance < 0) run++; else break; }
  const expected = f.in_year_balance >= 0 ? "green" : run >= 2 || share <= -0.03 ? "red" : "amber";
  // Act
  const ratings = findSlide(D.schoolDeck(schoolModel(), CTXT), "summary").ratings;
  const bal = ratings.find((r) => r.measure === "In-year balance");
  const res = ratings.find((r) => r.measure === "Reserve as a share of income");
  // Assert
  assert.equal(bal.level, expected);
  assert.equal(bal.icon, D.RAG[expected].icon);
  assert.equal(bal.word, D.RAG[expected].word);
  assert.ok(bal.text.startsWith(bal.icon + " " + bal.word));
  assert.ok(bal.value.includes(LATEST) && bal.value.includes(D.fmtExact(ppOf(f.in_year_balance, LATEST))));
  assert.equal(res.level, f.revenue_reserve < 0 ? "in_deficit" : res.level);
  assert.equal(res.icon, D.ICONS.in_deficit);
  assert.equal(res.word, "In deficit");
  assert.equal(res.tone, "critical");
  // A healthy reserve (5% of income) and a large one (10%) for a primary school.
  for (const [pct, key] of [[0.05, "healthy"], [0.1, "large_reserves"], [0.02, "tight"]]) {
    const sx = sxFixture();
    sx.m.revenue_reserve[LATEST] = { v: pct * f.total_income, pp: (pct * f.total_income) / f.pupils };
    const r = findSlide(D.schoolDeck(D.adapt(sFixture(), sx, COUNCIL, ENGLAND), CTXT), "summary").ratings.find((x) => x.measure === "Reserve as a share of income");
    assert.equal(r.level, key, String(pct));
    assert.equal(r.word, D.LABELS[key]);
    assert.ok(r.icon && r.text.includes(r.word));
  }
  // A surplus year is on track.
  const sx2 = sxFixture();
  sx2.m.in_year_balance[LATEST] = { v: 1000, pp: 1000 / f.pupils };
  const ok = findSlide(D.schoolDeck(D.adapt(sFixture(), sx2, COUNCIL, ENGLAND), CTXT), "summary").ratings.find((x) => x.measure === "In-year balance");
  assert.equal(ok.level, "green");
  assert.equal(ok.word, "On track");
});

test("where the money goes: categories against similar and nearby schools, each column labelled with its year", () => {
  // Arrange / Act
  const deck = D.schoolDeck(schoolModel({ nearby: true }), CTXT);
  const sl = findSlide(deck, "where_money_goes");
  const cols = sl.table.columns;
  // Assert
  assert.ok(cols[1].endsWith(LATEST) && cols[2].endsWith(LATEST) && cols[5].endsWith(NEAR_YEAR), cols.join(" | "));
  assert.ok(cols.includes("This school, " + NEAR_YEAR), "this school's figure for the nearby year beside the nearby median");
  const teachers = sl.table.rows.find((r) => r.key === "teaching_staff");
  assert.equal(teachers.cells[1].text, D.fmtExact(ppOf(gold.years[LATEST].lines.E01.value, LATEST)));
  assert.equal(teachers.cells[2].text, D.fmtExact(sFixture().similar.teaching_staff));
  assert.equal(teachers.cells[5].text, D.fmtExact(nearbyFixture().line_medians.teaching_staff));
  assert.ok(teachers.rag && teachers.cells[4].text === teachers.rag.icon + " " + teachers.rag.word);
  assert.equal(sl.table.rows.find((r) => r.key === "energy").cells[1].text, "—", "a category with no figure shows a dash, never £0");
  assert.ok(sl.note.includes("different years"));
  assert.ok(sl.lead.includes(Math.round((100 * staffTotal(LATEST)) / fin(LATEST).total_expenditure) + "%"), "staff share in the lead");
  assert.ok(sl.note.includes("over 80%") && sl.note.includes("IFS p.63"));
});

test("nearby: rank sentences, table, year/phase/CFR-AAR/intake notes and the compare link", () => {
  // Arrange
  const nb = nearbyFixture();
  // Act
  const deck = D.schoolDeck(schoolModel({ nearby: nb }), CTXT);
  const sl = findSlide(deck, "nearby"), t = findSlide(deck, "nearby_table"), t2 = findSlide(deck, "nearby_table_2");
  // Assert
  assert.ok(sl.bullets.some((b) => b.startsWith("Spending per pupil: the highest of 6 nearby primary schools")), sl.bullets.join("\n"));
  assert.ok(sl.bullets.some((b) => b.startsWith("Reserve per pupil: 6th highest of 6")));
  assert.ok(!sl.bullets.some((b) => b.startsWith("Parents' association")), "no PTA rank in the contract, so no sentence");
  assert.ok(sl.note.includes("Nearby figures are for " + NEAR_YEAR) && sl.note.includes(LATEST));
  assert.ok(sl.note.includes("April to March") && sl.note.includes("September to August"));
  assert.ok(sl.note.includes("free school meals"));
  assert.equal(seriesOf(sl, "school").points[0].v, nb.self.spend_pp);
  assert.equal(seriesOf(sl, "nearby").points[0].v, nb.medians.spend_pp);
  assert.ok(seriesOf(sl, "school").name.includes(NEAR_YEAR));
  // Split across slides, 4 neighbours each, this school on every one and the median on the last.
  assert.equal(t.table.rows.length, 1 + 4);
  assert.equal(t2.table.rows.length, 1 + (nb.schools.length - 4) + 1);
  assert.ok(t2.table.rows[0].self && t2.table.rows.at(-1).median && !t.table.rows.at(-1).median);
  assert.ok(t.title.endsWith("(1 of 2)") && t2.title.endsWith("(2 of 2)"));
  assert.ok(t.table.rows[0].self && t.table.rows[0].cells[0].text.includes("(this school)"));
  assert.equal(t.table.rows[1].cells[1].text, "0.2");
  assert.equal(t.table.rows[1].cells[2].status, "healthy");
  assert.equal(t.table.rows[1].cells[6].text, D.fmtExact(30) + " (2023-24)", "PTA per pupil carries its own year");
  assert.ok(t.table.rows[2].cells[0].text.includes("academy"));
  assert.ok(t.table.rows[2].cells[6].text.endsWith("*") && t.note.includes("lower confidence"));
  const bare = t.table.rows[3].cells;
  assert.equal(bare[2].status, "large_reserves");
  for (const k of [3, 4, 5, 6, 7]) assert.equal(bare[k].text, "—", "missing values are dashes, never 0");
  assert.equal(t.links[0].href, "/compare/?urns=" + [gold.urn, ...nb.schools.map((r) => r.urn)].join(","), "this school first, nearest next, 6 at most");
  assert.ok(t.title.includes(NEAR_YEAR) && t.table.columns[2].includes(NEAR_YEAR));
  assertClean(deck, "nearby");
});

test("nearby degrades: absent, empty or broken contracts never throw and say so plainly", () => {
  for (const nearby of [undefined, null, {}, { year: "2024-25", schools: [] }, { schools: "x", medians: null, rank: 5 }, { schools: [{ mi: 0.3 }, null, 7] }]) {
    // Arrange / Act
    const m = D.adapt({ ...sFixture(), nearby }, sxFixture(), COUNCIL, ENGLAND);
    const decks = [D.schoolDeck(m, CTXT), D.reviewDeck(m, CTXT), D.ptfaDeck(m, CTXT)];
    // Assert
    for (const deck of decks.slice(0, 2)) {
      const sl = findSlide(deck, "nearby");
      assert.match(sl.lead, /aren't published for this school yet/, JSON.stringify(nearby));
      assert.ok(!deck.slides.some((s) => s.id.startsWith("nearby_table")));
      const table = findSlide(deck, deck.kind === "review" ? "dashboard" : "where_money_goes").table;
      const col = table.columns.findIndex((h) => h.startsWith("Nearby"));
      assert.ok(table.rows.every((r) => r.cells[col].text === "—"), "nearby column shows a dash");
      assert.equal(summaryRating(deck, "Spending per pupil against nearby"), undefined);
    }
    assert.ok(findSlide(decks[2], "pta_compare").bullets.some((b) => b.includes("Nearby comparisons aren't published")));
  }
});
function summaryRating(deck, prefix) { return findSlide(deck, "summary").ratings.find((r) => r.measure.startsWith(prefix)); }

test("notes round-trip through localStorage per urn and pack, and into the PowerPoint speaker notes", async () => {
  // Arrange
  memory.clear();
  const key = D.notesKey(gold.urn, "governors");
  assert.equal(D.notesKey(gold.urn, "school"), key, "view=school shares the governors' notes");
  assert.notEqual(D.notesKey(gold.urn, "ptfa"), key);
  const saved = { notes: { summary: "Ask the head about supply costs.\nSecond line.", budget: "Recovery plan due in March." }, actions: null, meeting: "Finance committee, spring term", date: "12 March 2027" };
  // Act
  assert.equal(D.saveSaved(globalThis.localStorage, key, saved), true);
  const back = D.loadSaved(globalThis.localStorage, key);
  const other = D.loadSaved(globalThis.localStorage, D.notesKey(gold.urn, "ptfa"));
  const deck = D.applySaved(D.schoolDeck(schoolModel(), CTXT), back);
  const { calls, FakePptx } = fakePptx();
  await D.buildPptx(deck, FakePptx, {});
  // Assert
  assert.deepEqual(back.notes, saved.notes);
  assert.deepEqual(other.notes, {}, "another pack's notes are separate");
  assert.equal(deck.slides[0].meta.preparedFor, saved.meeting);
  assert.equal(deck.slides[0].meta.date, saved.date);
  const i = deck.slides.findIndex((s) => s.id === "summary");
  const sl = deck.slides[i];
  assert.equal(calls.slides[i].notes, saved.notes.summary + "\n\nSources:\n" + sl.sources.join("\n"), "notes first, then sources");
  const plain = deck.slides.findIndex((s) => s.id === "funding");
  assert.equal(calls.slides[plain].notes, deck.slides[plain].sources.join("\n"), "no notes: sources only");
  assert.ok(calls.slides[0].texts.some(([t]) => typeof t === "string" && t.includes(saved.meeting) && t.includes(saved.date)));
  // Blocked or broken storage never throws.
  const broken = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("full"); } };
  assert.deepEqual(D.loadSaved(broken, key).notes, {});
  assert.equal(D.saveSaved(broken, key, saved), false);
  assert.deepEqual(D.loadSaved(null, key).notes, {});
  globalThis.localStorage.setItem(key, "{not json");
  assert.deepEqual(D.loadSaved(globalThis.localStorage, key).notes, {});
});

test("actions rows are saved and exported to the PowerPoint as an editable table", async () => {
  // Arrange
  memory.clear();
  const key = D.notesKey(gold.urn, "review");
  const actions = [{ action: "Ask why bought-in services are high", owner: "Chair", by: "Spring term" }, { action: "Check supply cover", owner: "", by: "" }];
  D.saveSaved(globalThis.localStorage, key, { notes: {}, actions, meeting: null, date: null });
  // Act
  const deck = D.applySaved(D.reviewDeck(schoolModel(), CTXT), D.loadSaved(globalThis.localStorage, key));
  const { calls, FakePptx } = fakePptx();
  await D.buildPptx(deck, FakePptx, {});
  // Assert
  const i = deck.slides.findIndex((s) => s.kind === "actions");
  assert.deepEqual(deck.slides[i].actions, actions);
  const rows = calls.slides[i].tables[0].rows.map((r) => r.map((c) => c.text));
  assert.deepEqual(rows, [["Action or decision", "Owner", "By when"], ...actions.map((a) => [a.action, a.owner, a.by])]);
  // Tables on other slides go out as tables too, ratings as icon + word text.
  const dash = deck.slides.findIndex((s) => s.id === "dashboard");
  assert.equal(calls.slides[dash].tables[0].rows[0].length, deck.slides[dash].table.columns.length);
  const sum = calls.slides[deck.slides.findIndex((s) => s.id === "summary")];
  const text = sum.texts.flatMap(([t]) => (Array.isArray(t) ? t.map((p) => p.text) : [t])).join(" ");
  assert.ok(text.includes("▼ Needs attention") || text.includes("▼ In deficit"), "ratings as icon + word");
});

test("PTFA pack: income per charity year equals the register, comparisons name their year, never summed", () => {
  // Arrange
  const m = schoolModel({ nearby: true });
  // Act
  const deck = D.ptfaDeck(m, CTXT);
  // Assert
  const money = findSlide(deck, "pta_money");
  const inc = seriesOf(money, "pta_income"), sp = seriesOf(money, "pta_spend");
  assert.deepEqual(inc.points.map((p) => p.y), ptfaYears.map(ptaSchoolYear), "each return in the school year the producer counts it in");
  assert.deepEqual(inc.points.map((p) => p.v), ptfaYears.map((y) => gold.ptfa.years[y].income));
  assert.deepEqual(sp.points.map((p) => p.v), ptfaYears.map((y) => gold.ptfa.years[y].expenditure));
  assert.ok(money.figures.every((f) => f.year.includes("charity year")), "years labelled as charity years");
  assert.ok(money.lead.includes("31 August"));
  assert.ok(money.links.some((l) => l.href.endsWith("/charity-details/" + gold.ptfa.charity_number)));
  const cmp = findSlide(deck, "pta_compare");
  assert.ok(cmp.chart.series[0].points.every((p) => /\d{4}-\d{2}$/.test(p.y)), "every bar names its year");
  assert.ok(cmp.bullets.some((b) => b.includes("Neighbour 2 Primary School") && b.includes("(2024-25)") && b.includes("matched with lower confidence")));
  const brief = findSlide(deck, "school_brief");
  assert.ok(/never added together/.test(brief.note));
  assert.equal(brief.status.key, "in_deficit");
  assert.ok(brief.bullets.some((b) => b.includes("Why this happens") && b.includes("What helps")), "the school's deficit is named beside its reasons and what helps");
  const ideas = findSlide(deck, "ideas");
  for (const w of ["Gift Aid", "match funding", "small donations scheme", "wish-list"]) assert.ok(ideas.bullets.some((b) => b.includes(w)), w);
  assert.ok(ideas.links.some((l) => l.href === "/guides/ptfa/"));
  const q = findSlide(deck, "questions");
  assert.equal(q.title, "Questions for the school");
  assert.ok(q.bullets.some((b) => b.includes("extra money")) && q.bullets.every((b) => !/[{}]/.test(b)));
  const msgs = findSlide(deck, "summary").messages;
  assert.equal(msgs.length, 3);
  const lastY = ptfaYears.at(-1), lastSchoolY = ptaSchoolYear(lastY);
  assert.ok(msgs[0].startsWith("Raised " + D.fmtExact(gold.ptfa.years[lastY].income) + " in the charity year to "), msgs[0]);
  assert.ok(msgs[0].includes("(school year " + lastSchoolY + "), " + D.fmtExact(gold.ptfa.years[lastY].income / pupils(lastSchoolY)) + " per pupil"), "per pupil uses the same school year's pupils: " + msgs[0]);
  // Never summed: no figure or chart value equals any PTA income + school donations total.
  const sums = new Set();
  for (const p of ptfaYears) for (const y of YEARS) if (donations(y)) sums.add(Math.round(gold.ptfa.years[p].income + donations(y)));
  for (const sl of deck.slides) {
    for (const f of sl.figures) assert.ok(!sums.has(f.v) && !sums.has(f.pp), sl.id + " " + f.key);
    for (const s of sl.chart ? sl.chart.series : []) for (const p of s.points) assert.ok(!sums.has(p.v), sl.id);
  }
  assertClean(deck, "ptfa");
});

test("PTFA target: the council's median per pupil times the same year's pupils, labelled as an illustration", () => {
  // Arrange: a council whose PTA median is well above this association, so the target is a real gap.
  const council = areaDoc("council-" + gold.la.code, "council", gold.la.name);
  Object.values(council.by_year).forEach((b) => { b.all.pta_pp_median = 400; });
  const m = schoolModel({ council });
  const lastY = ptfaYears.at(-1), schoolY = ptaSchoolYear(lastY);
  // Act
  const t = D.ptaTarget(m);
  const deck = D.ptfaDeck(m, CTXT);
  // Assert
  assert.equal(t.year, schoolY, "the school year the association's latest return is counted in");
  assert.equal(t.pupils, pupils(schoolY), "the same year's pupils");
  assert.equal(t.target, Math.round(400 * pupils(schoolY)));
  assert.equal(t.gap, Math.round(400 * pupils(schoolY) - gold.ptfa.years[lastY].income));
  assert.match(t.message, /illustration/);
  const fig = findSlide(deck, "ideas").figures.find((f) => f.key === "pta_target");
  assert.equal(fig.v, t.target);
  assert.equal(fig.year, schoolY);
  assert.ok(fig.label.startsWith("Illustration"));
  // Above the median: says so, still an illustration.
  const above = D.ptaTarget(schoolModel());
  assert.ok(above.gap <= 0 && above.message.startsWith("Already raises more"));
});

test("PTFA pack with no registered PTA: honest wording and the £5,000 explanation", () => {
  // Arrange
  const m = D.adapt(sFixture({ withPta: false }), sxFixture(), COUNCIL, ENGLAND);
  // Act
  const deck = D.ptfaDeck(m, CTXT);
  const text = strings(deck).join("\n");
  // Assert
  assert.ok(text.includes("No registered parents' association found"));
  assert.ok(text.includes("£5,000 or less"));
  assert.ok(text.includes("another name"));
  assert.ok(/donations line may still show parents' giving/.test(text));
  assert.ok(!text.toLowerCase().includes("no " + "pta"));
  assert.equal(findSlide(deck, "donations").figures[0].v, Math.round(donations(LATEST)));
  assert.ok(findSlide(deck, "summary").messages[0].startsWith("No registered parents' association found"));
  assertClean(deck, "no-pta");
});

test("series flags: marked years from flags.suspect, and the pressures slide quotes IFS lines with pages", () => {
  // Arrange: the shape series.py writes.
  const sx = sxFixture({ flags: { falling_rolls: null, pass_through: { year: LATEST, income_rise: 120000, staff_rise: 100000 },
    high_send: { ehcp_pct: 5.5, sen_share: 0.065, reason: "ehcp" }, suspect: { [YEARS[1]]: ["total_income"] }, not_reported: {} } });
  // Act
  const m = D.adapt(sFixture(), sx, COUNCIL, ENGLAND);
  const deck = D.schoolDeck(m, CTXT);
  const pr = findSlide(deck, "pressures");
  // Assert
  assert.equal(m.rows.find((r) => r.y === YEARS[1]).suspect, true);
  assert.equal(m.rows.find((r) => r.y === LATEST).suspect, false);
  assert.ok(pr.bullets.some((b) => b.startsWith("Special needs: 5.5%") && b.includes("IFS p.58")));
  assert.ok(pr.bullets.some((b) => b.startsWith("Pass-through grants") && b.includes("IFS p.50")));
  assert.ok(pr.bullets.some((b) => b.includes("£7,000") && b.includes("IFS p.7")), "primary spend set beside the IFS £7,000");
  assert.ok(!strings(deck).some((s) => s.includes("8,400")), "the IFS all-age £8,400 is never a comparator");
});

test("council picture: schools in deficit, DSG with the statutory override note, medians mix phases", () => {
  const sl = findSlide(D.schoolDeck(schoolModel(), CTXT), "council");
  assert.ok(sl.note.includes("Statutory override"));
  assert.ok(sl.note.includes("IFS p.61"));
  assert.ok(sl.bullets.some((b) => b.includes("mix primary and secondary")));
  assert.equal(sl.figures.find((f) => f.key === "dsg").year, YEARS.at(-1));
  assert.match(findSlide(D.schoolDeck(schoolModel({ council: null }), CTXT), "council").lead, /couldn't be loaded/);
});

test("academy: pupil premium is 'not reported in academy accounts', never £0", () => {
  // Arrange
  const s = { ...sFixture(), academy: true, trust: "Example Learning Trust", tags: { governance: "academy" }, income_lines: { ...sFixture().income_lines, pupil_premium: null } };
  const sx = sxFixture({ drop: ["pupil_premium"] });
  sx.source = "AAR";
  // Act
  const deck = D.schoolDeck(D.adapt(s, sx, COUNCIL, ENGLAND), CTXT);
  const inc = findSlide(deck, "income");
  // Assert
  assert.ok(inc.bullets.some((b) => b.includes("pupil premium: not reported in academy accounts")));
  assert.ok(!inc.bullets.some((b) => /pupil premium £0/.test(b)));
  assert.ok(findSlide(deck, "title").bullets.some((b) => b.includes("September to August")));
});

test("school deck reads the SERIES names the build writes (total_staff, grant_funding_government, self_generated_income)", () => {
  // Arrange: /data/sx from series.py, not the deck's own names
  const sx = sxFixture();
  for (const [from, to] of [["staff_total", "total_staff"], ["grant_funding", "grant_funding_government"], ["self_generated", "self_generated_income"]]) {
    sx.m[to] = sx.m[from];
    delete sx.m[from];
  }
  // Act
  const deck = D.schoolDeck(D.adapt(sFixture(), sx, COUNCIL, ENGLAND), CTXT);
  const grant = findSlide(deck, "income").figures.find((f) => f.key === "grant_funding");
  const staff = findSlide(deck, "summary").ratings.find((r) => r.measure === "Staff costs share");
  // Assert
  assert.equal(grant.v, Math.round(fin(LATEST).grant_funding));
  assert.ok(staff.value.startsWith(Math.round((100 * staffTotal(LATEST)) / fin(LATEST).total_expenditure) + "%"));
});

test("school deck: the deficit is named with its reasons (IFS pages) and what helps", () => {
  // Arrange / Act
  const sl = findSlide(D.schoolDeck(schoolModel(), CTXT), "budget");
  // Assert
  assert.equal(sl.status.key, "in_deficit");
  assert.ok(sl.lead.startsWith("▼ In deficit"));
  const why = CTX.framings.why_schools_go_into_deficit;
  assert.ok(sl.note.startsWith("Why this happens: " + why.text) && sl.note.includes("IFS pp.62–63"), "the full IFS framing, with its pages");
  assert.ok(sl.bullets.some((b) => b.startsWith("What helps")));
  assert.equal(sl.figures.find((f) => f.key === "revenue_reserve").v, Math.round(fin(LATEST).revenue_reserve));
  assert.deepEqual(sl.ratings.map((r) => r.measure), ["In-year balance", "Reserve as a share of income"]);
});

test("school deck: questions fill their placeholders and real terms carry the label", () => {
  // Arrange / Act
  const deck = D.schoolDeck(schoolModel(), CTXT);
  const q = findSlide(deck, "questions");
  const funding = findSlide(deck, "funding");
  // Assert
  assert.ok(q.bullets.length >= 3);
  assert.ok(q.bullets.every((b) => !/[{}]/.test(b)), "no placeholder left");
  assert.ok(q.bullets.some((b) => b.includes(gold.name)));
  assert.ok(q.bullets.some((b) => b.includes("the council")));
  const real = funding.bullets.find((b) => b.startsWith("In real terms"));
  assert.ok(real && real.includes(CTX.real_label), "real-terms caption");
  const first = YEARS[0];
  const rpp = (fin(first).total_income * 100) / deflator.financial_years[first] / pupils(first);
  assert.ok(real.includes(D.fmtExact(rpp)));
  assert.ok(findSlide(deck, "sources").bullets.some((b) => b.includes(CTX.cite)));
});

test("school deck without /data/sx falls back to /data/s years", () => {
  // Arrange
  const s = sFixture();
  // Act
  const m = D.adapt(s, null, COUNCIL, ENGLAND);
  const deck = D.schoolDeck(m, CTXT);
  // Assert
  assert.equal(m.sx, false);
  assert.deepEqual(deck.slides.map((x) => x.id), PACK_ORDER.governors.filter((id) => !id.startsWith("nearby_table")));
  const inc = seriesOf(findSlide(deck, "funding"), "total_income");
  s.years.forEach((r, i) => assert.equal(inc.points[i].v, Math.round(r.income / r.pupils), r.y));
  seriesOf(findSlide(deck, "budget"), "revenue_reserve").points.forEach((p, i) => assert.equal(p.v, Math.round(s.years[i].reserve / s.years[i].pupils)));
  assert.equal(seriesOf(findSlide(deck, "funding"), "grant_funding"), undefined, "no grant series without sx");
  // Missing values stay null rather than 0.
  assert.equal(m.rows[0].metrics.grant_funding, undefined);
});

test("suspect years are marked, captioned and never the headline (all three flag shapes)", () => {
  for (const flags of [[LATEST], [{ year: LATEST, code: "pupils_jump", text: "pupil count jumps" }], { [LATEST]: ["pupils_jump"] }, { suspect: { [LATEST]: ["pupils"] } }]) {
    // Arrange / Act
    const deck = D.schoolDeck(D.adapt(sFixture(), sxFixture({ flags }), COUNCIL, ENGLAND), CTXT);
    const funding = findSlide(deck, "funding");
    // Assert
    const last = seriesOf(funding, "total_income").points.at(-1);
    assert.equal(last.y, LATEST);
    assert.equal(last.suspect, true, "kept and marked, not dropped");
    assert.ok(funding.note.includes(LATEST + " is marked"));
    const prev = YEARS[YEARS.length - 2];
    assert.equal(funding.figures.find((f) => f.key === "total_income").year, prev, "headline uses the last unmarked year");
    assert.ok(funding.chart.alt.includes("(marked)"));
    assert.ok(D.chartData(funding.chart)[0].labels.at(-1).endsWith("◆"));
    // This school's own headline figures (council and charity figures are other bodies' years).
    for (const sl of deck.slides) for (const f of sl.figures) if (f.source === "DfE CFR return") assert.notEqual(f.year, LATEST, sl.id + " " + f.key);
    for (const msg of findSlide(deck, "summary").messages) assert.ok(!msg.includes(LATEST), msg);
  }
});

test("compare deck: 3 schools, and a clear message outside 2 to 6", () => {
  // Arrange
  const base = sFixture();
  const other = (urn, name, scale) => ({ ...base, urn, name, path: "/school/" + urn + "-x/", years: base.years.map((r) => ({ ...r, income: Math.round(r.income * scale), pupils: r.pupils * scale })), pta: [] });
  const list = [{ s: base, sx: sxFixture() }, { s: other("100001", "Stoke Newington Primary", 1.2), sx: null }, { s: other("100002", "Clapton Park Primary", 0.8), sx: null }];
  // Act
  const deck = D.compareDeck(list, CTX);
  // Assert
  assert.equal(deck.slides.length, 7);
  const income = findSlide(deck, "income");
  assert.equal(income.chart.series[0].points.length, 3);
  assert.equal(income.chart.series[0].points[0].v, ppOf(fin(LATEST).total_income, LATEST));
  assert.ok(findSlide(deck, "status").note.includes("What helps"));
  for (const n of [1, 7]) {
    const bad = D.compareDeck(Array.from({ length: n }, () => ({ s: base })), CTX);
    assert.match(bad.message, /between 2 and 6/);
    assert.equal(bad.slides.length, 1);
  }
  assertClean(deck, "compare");
});

test("area deck: council has DSG with the statutory override note; constituency has none", () => {
  // Arrange / Act
  const council = D.areaDeck(COUNCIL, ENGLAND, CTX);
  const cons = D.areaDeck(CONSTITUENCY, ENGLAND, CTX);
  // Assert
  assert.ok(findSlide(council, "dsg"));
  assert.ok(findSlide(council, "dsg").note.includes("Statutory override"));
  assert.ok(findSlide(council, "dsg").bullets.some((b) => b.includes("IFS p.61")));
  assert.equal(findSlide(cons, "dsg"), undefined);
  const deficits = findSlide(council, "deficits");
  assert.equal(seriesOf(deficits, "area").points.length, YEARS.length);
  assert.ok(deficits.note.startsWith("Why this happens") && deficits.note.includes("IFS pp.62–63"));
  assert.ok(deficits.bullets.some((b) => b.startsWith("What helps")));
  const med = findSlide(council, "medians");
  assert.equal(seriesOf(med, "england").points.length, 4);
  assert.ok(findSlide(council, "pta").bullets.some((b) => b.includes("never added together")));
  assert.equal(council.filename, gold.la.name + " - School Money.pptx");
  assert.match(D.areaDeck(null, ENGLAND, CTX).message, /couldn't be loaded/);
  const small = areaDoc("constituency-E1", "constituency", "Tiny");
  Object.values(small.by_year).forEach((b) => { b.all = { schools: 3, in_deficit: null, in_deficit_pct: null }; });
  const tiny = D.areaDeck(small, ENGLAND, CTX);
  assert.ok(seriesOf(findSlide(tiny, "medians"), "area") === undefined);
  assertClean(council, "council");
  assertClean(cons, "constituency");
});

test("nextIndex steps with the keyboard and stays in range", () => {
  assert.equal(D.nextIndex(0, "ArrowRight", 10), 1);
  assert.equal(D.nextIndex(0, " ", 10), 1);
  assert.equal(D.nextIndex(3, "PageDown", 10), 4);
  assert.equal(D.nextIndex(9, "ArrowRight", 10), 9);
  assert.equal(D.nextIndex(3, "ArrowLeft", 10), 2);
  assert.equal(D.nextIndex(0, "PageUp", 10), 0);
  assert.equal(D.nextIndex(5, "Home", 10), 0);
  assert.equal(D.nextIndex(5, "End", 10), 9);
  assert.equal(D.nextIndex(5, "x", 10), 5);
  assert.equal(D.nextIndex(0, "ArrowRight", 0), 0);
});

test("buildPptx: one 16:9 slide per model slide, model text and series, notes then sources", async () => {
  // Arrange
  const { calls, FakePptx } = fakePptx();
  const deck = D.schoolDeck(schoolModel({ nearby: true }), CTXT);
  const palette = { paper: "#f6f2ea", ink: " #1c1b18", "ink-2": "#5b574f", grid: "rgb(232, 226, 214)", accent: "#0f6e6a", pack: "#4338ca", c1: "#0f6e6a", c2: "#b5542a", c3: "#5b4ea8", c4: "#6b7f1f", critical: "#c0392b" };
  // Act
  const name = await D.buildPptx(deck, FakePptx, palette);
  // Assert
  assert.equal(calls.layout, "LAYOUT_16x9");
  assert.equal(calls.slides.length, deck.slides.length);
  assert.equal(calls.file, gold.name + " - Governors finance pack - School Money.pptx");
  assert.equal(name, calls.file);
  deck.slides.forEach((sl, i) => {
    const rec = calls.slides[i];
    assert.equal(rec.texts[0][0], sl.title);
    assert.equal(rec.notes, D.speakerNotes(sl));
    assert.equal(rec.background.color, "F6F2EA");
    assert.equal(rec.tables.length, sl.table || sl.kind === "actions" ? 1 : 0, sl.id + " tables");
    if (!sl.chart) { assert.equal(rec.charts.length, 0); return; }
    assert.equal(rec.charts.length, 1);
    const data = rec.charts[0].data;
    assert.equal(rec.charts[0].type, sl.chart.type === "line" ? "line" : "bar");
    sl.chart.series.forEach((s, k) => {
      assert.equal(data[k].name, s.name);
      assert.deepEqual(data[k].values, s.points.map((p) => p.v));
      assert.deepEqual(data[k].labels, s.points.map((p) => p.y + (p.suspect ? " ◆" : "")));
    });
  });
  const budget = calls.slides[deck.slides.findIndex((s) => s.id === "budget")];
  assert.equal(budget.texts[1][1].color, "C0392B", "status colour read from the palette");
  const table = calls.slides[deck.slides.findIndex((s) => s.id === "nearby_table")].tables[0];
  assert.equal(table.rows[0][0].options.fill.color, "4338CA", "table header in the pack accent");
  const figTexts = calls.slides.flatMap((r) => r.texts.flatMap(([t]) => (Array.isArray(t) ? t.map((p) => p.text) : [t])));
  assert.ok(figTexts.some((t) => t.includes(D.fmtExact(ppOf(fin(LATEST).total_income, LATEST)))), "figure text from the model");
});

test("no pack string uses a banned phrase or leaves a placeholder", () => {
  const decks = [
    D.schoolDeck(schoolModel({ nearby: true }), CTXT), D.schoolDeck(schoolModel({ noSx: true }), CTXT), D.ptfaDeck(schoolModel({ nearby: true }), CTXT),
    D.reviewDeck(schoolModel({ nearby: true }), CTXT), D.reviewDeck(schoolModel({ noSx: true }), CTXT),
    D.ptfaDeck(D.adapt(sFixture({ withPta: false }), null, null, null), CTXT), D.areaDeck(COUNCIL, ENGLAND, CTX),
    D.compareDeck([], CTX), D.schoolDeck(D.adapt(null), CTX), D.ptfaDeck(D.adapt(null), CTX), D.reviewDeck(D.adapt(null), CTX),
    D.schoolDeck(D.adapt({ ...sFixture(), status: null, academy: true, trust: "Example Learning Trust" }, sxFixture(), null, null), CTXT),
    D.reviewDeck(D.adapt(sFixture(), sxFixture({ flags: YEARS }), COUNCIL, ENGLAND), CTXT),
  ];
  decks.forEach((d, i) => {
    assertClean(d, "deck " + i);
    for (const s of strings(d)) assert.ok(!/\{(name|overseer|reserve|years)\}/.test(s), s);
    assert.ok(d.slides.length >= 1 && d.title && d.filename.endsWith(".pptx"));
    assert.ok(!/undefined|NaN|null/.test(D.deckText(d)), "deck " + i + ": " + (D.deckText(d).match(/.{0,60}(undefined|NaN|null).{0,20}/) || [""])[0]);
  });
  const academy = decks[11];
  assert.ok(findSlide(academy, "questions").bullets.some((b) => b.includes("Example Learning Trust")), "{overseer} is the trust for academies");
});
