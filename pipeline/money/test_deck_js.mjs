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
    const p = gold.ptfa.years[y];
    pta[y] = { income: p.income, spend: p.expenditure, income_pp: pupils(y) ? p.income / pupils(y) : null, spend_pp: pupils(y) ? p.expenditure / pupils(y) : null, charity_number: String(gold.ptfa.charity_number), confidence: "high" };
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

const schoolModel = (opts = {}) => D.adapt(sFixture(opts), opts.noSx ? null : sxFixture(opts), COUNCIL, ENGLAND);
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
  for (const k of ["adapt", "schoolDeck", "ptfaDeck", "compareDeck", "areaDeck", "nextIndex", "buildPptx", "chartData", "fmtExact"]) assert.equal(typeof D[k], "function", k);
  assert.equal(D.PPTX_URL, "https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js");
});

test("fmtExact and fmtPupils", () => {
  assert.equal(D.fmtExact(4115.4), "£4,115");
  assert.equal(D.fmtExact(-488), "-£488");
  assert.equal(D.fmtExact(null), "—");
  assert.equal(D.fmtPupils(432.5), "432.5");
  assert.equal(D.fmtPupils(432.54), "432.5");
  assert.equal(D.fmtPupils(435), "435");
});

test("school deck: 8 to 10 well-formed slides", () => {
  // Arrange
  const m = schoolModel();
  // Act
  const deck = D.schoolDeck(m, CTX);
  // Assert
  assert.ok(deck.slides.length >= 8 && deck.slides.length <= 10, String(deck.slides.length));
  assert.equal(deck.filename, gold.name + " - School Money.pptx");
  for (const sl of deck.slides) {
    for (const k of ["id", "kind", "title", "lead", "bullets", "figures", "chart", "note", "sources"]) assert.ok(k in sl, sl.id + " lacks " + k);
    assert.ok(Array.isArray(sl.bullets) && Array.isArray(sl.figures) && Array.isArray(sl.sources));
    assert.ok(sl.sources.length > 0, sl.id + " has sources");
    for (const f of sl.figures) {
      assert.ok(f.year && f.source, sl.id + " figure carries year and source");
      assert.ok(f.text.includes(f.year) && f.text.includes(f.source), sl.id + " figure text names year and source");
    }
    if (sl.chart) {
      assert.ok(["line", "bar", "stack"].includes(sl.chart.type));
      assert.ok(sl.chart.alt && sl.chart.series.every((s) => s.points.every((p) => "y" in p && "v" in p && "suspect" in p)));
    }
  }
  assert.ok(deck.slides[0].lead.includes(D.fmtPupils(pupils(LATEST))), "title shows pupils to 1 dp");
  assert.ok(deck.slides[0].lead.includes(gold.la.name));
});

test("school deck: every £ figure equals the gold file, per pupil = round(v / same-year pupils)", () => {
  // Arrange
  const deck = D.schoolDeck(schoolModel(), CTX);
  const keyed = { total_income: "total_income", total_expenditure: "total_expenditure", grant_funding: "grant_funding", revenue_reserve: "revenue_reserve" };
  let checked = 0;
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
  assert.ok(checked >= 6, "figures checked: " + checked);
  // Assert: chart series, every year
  const funding = findSlide(deck, "funding");
  for (const key of ["grant_funding", "total_income", "total_expenditure"]) {
    const s = seriesOf(funding, key);
    assert.deepEqual(s.points.map((p) => p.y), YEARS);
    s.points.forEach((p) => assert.equal(p.v, ppOf(fin(p.y)[key], p.y), `${key} ${p.y}`));
  }
  const reserve = findSlide(deck, "reserve");
  seriesOf(reserve, "revenue_reserve").points.forEach((p) => assert.equal(p.v, ppOf(fin(p.y).revenue_reserve, p.y)));
  // The two reserve years the brief names, with totals beside.
  for (const y of ["2019-20", LATEST]) {
    const total = A.fmtMoney(fin(y).revenue_reserve);
    assert.ok(reserve.bullets.some((b) => b.startsWith(y) && b.includes(D.fmtExact(ppOf(fin(y).revenue_reserve, y))) && b.includes(total)), y);
  }
  const fig = (id, key) => findSlide(deck, id).figures.find((f) => f.key === key);
  assert.equal(fig("funding", "total_income").v, Math.round(fin(LATEST).total_income));
  assert.equal(fig("funding", "total_expenditure").v, Math.round(fin(LATEST).total_expenditure));
  assert.equal(fig("funding", "grant_funding").v, Math.round(fin(LATEST).grant_funding));
});

test("school deck: staff share from the 'Staff Total' column, beside the IFS 80% line with its page", () => {
  // Arrange
  const deck = D.schoolDeck(schoolModel(), CTX);
  const sl = findSlide(deck, "spending");
  // Act
  const staff = sl.figures.find((f) => f.key === "staff_total");
  const share = staffTotal(LATEST) / fin(LATEST).total_expenditure;
  // Assert
  assert.equal(staff.v, Math.round(staffTotal(LATEST)));
  assert.equal(staff.pp, ppOf(staffTotal(LATEST), LATEST));
  assert.ok(Math.abs(staff.share - share) < 1e-9);
  assert.ok(sl.lead.includes(Math.round(share * 100) + "%"));
  assert.ok(sl.bullets.some((b) => b.includes("over 80%") && b.includes("IFS p.63")));
  assert.equal(sl.chart.type, "stack");
  seriesOf(sl, "staff_total").points.forEach((p) => assert.equal(p.v, ppOf(staffTotal(p.y), p.y)));
});

test("school deck: the deficit is named with its reasons (IFS pages) and what helps", () => {
  // Arrange / Act
  const deck = D.schoolDeck(schoolModel(), CTX);
  const sl = findSlide(deck, "status");
  // Assert
  assert.equal(sl.status.key, "in_deficit");
  assert.ok(sl.lead.startsWith("▼ In deficit"));
  const why = CTX.framings.why_schools_go_into_deficit;
  assert.ok(sl.bullets.some((b) => b.includes(why.text) && b.includes("IFS pp.62–63")));
  assert.ok(sl.bullets.some((b) => b.startsWith("What helps")));
  assert.equal(sl.figures.find((f) => f.key === "revenue_reserve").v, Math.round(fin(LATEST).revenue_reserve));
});

test("school deck: questions fill their placeholders and real terms carry the label", () => {
  // Arrange / Act
  const deck = D.schoolDeck(schoolModel(), CTX);
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
  const deck = D.schoolDeck(m, CTX);
  // Assert
  assert.equal(m.sx, false);
  assert.ok(deck.slides.length >= 8 && deck.slides.length <= 10);
  const inc = seriesOf(findSlide(deck, "funding"), "total_income");
  s.years.forEach((r, i) => assert.equal(inc.points[i].v, Math.round(r.income / r.pupils), r.y));
  seriesOf(findSlide(deck, "reserve"), "revenue_reserve").points.forEach((p, i) => assert.equal(p.v, Math.round(s.years[i].reserve / s.years[i].pupils)));
  assert.equal(seriesOf(findSlide(deck, "funding"), "grant_funding"), undefined, "no grant series without sx");
  assert.notEqual(findSlide(deck, "spending").chart?.type, "stack");
  // Missing values stay null rather than 0.
  assert.equal(m.rows[0].metrics.grant_funding, undefined);
});

test("suspect years are marked, captioned and never the headline (all three flag shapes)", () => {
  for (const flags of [[LATEST], [{ year: LATEST, code: "pupils_jump", text: "pupil count jumps" }], { [LATEST]: ["pupils_jump"] }]) {
    // Arrange / Act
    const deck = D.schoolDeck(D.adapt(sFixture(), sxFixture({ flags }), COUNCIL, ENGLAND), CTX);
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
  }
});

test("PTFA deck: 6 to 8 slides, income per charity year equals the register, overlap note, never summed", () => {
  // Arrange
  const m = schoolModel();
  // Act
  const deck = D.ptfaDeck(m, CTX);
  // Assert
  assert.ok(deck.slides.length >= 6 && deck.slides.length <= 8, String(deck.slides.length));
  const money = findSlide(deck, "pta_money");
  const inc = seriesOf(money, "pta_income"), sp = seriesOf(money, "pta_spend");
  assert.deepEqual(inc.points.map((p) => p.y), ptfaYears);
  assert.deepEqual(inc.points.map((p) => p.v), ptfaYears.map((y) => gold.ptfa.years[y].income));
  assert.deepEqual(sp.points.map((p) => p.v), ptfaYears.map((y) => gold.ptfa.years[y].expenditure));
  assert.ok(money.figures.every((f) => f.year.includes("charity year")), "years labelled as charity years");
  assert.ok(money.lead.includes("31 August"));
  const charity = findSlide(deck, "charity");
  assert.ok(charity.links.some((l) => l.href.endsWith("/charity-details/" + gold.ptfa.charity_number)));
  const overlap = findSlide(deck, "overlap");
  assert.ok(/never added together/.test(overlap.lead));
  const ideas = findSlide(deck, "ideas");
  for (const w of ["Gift Aid", "match funding", "small donations scheme", "wish-list"]) assert.ok(ideas.bullets.some((b) => b.includes(w)), w);
  assert.ok(ideas.links.some((l) => l.href === "/guides/ptfa/"));
  // Never summed: no figure or chart value equals any PTA income + school donations total.
  const sums = new Set();
  // (Years with £0 donations are skipped: income + 0 is just the PTA's own figure.)
  for (const p of ptfaYears) for (const y of YEARS) if (donations(y)) sums.add(Math.round(gold.ptfa.years[p].income + donations(y)));
  for (const sl of deck.slides) {
    for (const f of sl.figures) assert.ok(!sums.has(f.v) && !sums.has(f.pp), sl.id + " " + f.key);
    for (const s of sl.chart ? sl.chart.series : []) for (const p of s.points) assert.ok(!sums.has(p.v), sl.id);
  }
  assertClean(deck, "ptfa");
});

test("PTFA deck with no registered PTA: honest wording and the £5,000 explanation", () => {
  // Arrange
  const m = D.adapt(sFixture({ withPta: false }), sxFixture(), COUNCIL, ENGLAND);
  // Act
  const deck = D.ptfaDeck(m, CTX);
  const text = strings(deck).join("\n");
  // Assert
  assert.ok(deck.slides.length >= 6 && deck.slides.length <= 8, String(deck.slides.length));
  assert.ok(text.includes("No registered parents' association found"));
  assert.ok(text.includes("£5,000 or less"));
  assert.ok(text.includes("another name"));
  assert.ok(/donations line may still show parents' giving/.test(text));
  assert.ok(!text.toLowerCase().includes("no " + "pta"));
  const don = findSlide(deck, "donations").figures[0];
  assert.equal(don.v, Math.round(donations(LATEST)));
  assertClean(deck, "no-pta");
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
  // A missing area doc is said in words.
  assert.match(D.areaDeck(null, ENGLAND, CTX).message, /couldn't be loaded/);
  // A withheld median (fewer than 5 schools) stays missing, never 0.
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

test("buildPptx: one 16:9 slide per model slide, model text and series, sources as notes", async () => {
  // Arrange: a fake PptxGenJS that records calls.
  const calls = { slides: [], file: null, layout: null };
  class FakePptx {
    constructor() { this.ChartType = { line: "line", bar: "bar" }; }
    set layout(v) { calls.layout = v; }
    addSlide() {
      const rec = { texts: [], charts: [], notes: null };
      calls.slides.push(rec);
      return { set background(v) { rec.background = v; }, addText: (t, o) => rec.texts.push([t, o]), addChart: (type, data, o) => rec.charts.push({ type, data, o }), addNotes: (n) => { rec.notes = n; } };
    }
    writeFile(opts) { calls.file = opts.fileName; return Promise.resolve(opts.fileName); }
  }
  const deck = D.schoolDeck(schoolModel(), CTX);
  const palette = { paper: "#f6f2ea", ink: " #1c1b18", "ink-2": "#5b574f", grid: "rgb(232, 226, 214)", accent: "#0f6e6a", c1: "#0f6e6a", c2: "#b5542a", c3: "#5b4ea8", c4: "#6b7f1f", critical: "#c0392b" };
  // Act
  const name = await D.buildPptx(deck, FakePptx, palette);
  // Assert
  assert.equal(calls.layout, "LAYOUT_16x9");
  assert.equal(calls.slides.length, deck.slides.length);
  assert.equal(calls.file, "William Patten Primary School - School Money.pptx");
  assert.equal(name, calls.file);
  deck.slides.forEach((sl, i) => {
    const rec = calls.slides[i];
    assert.equal(rec.texts[0][0], sl.title);
    assert.equal(rec.notes, sl.sources.join("\n"));
    assert.equal(rec.background.color, "F6F2EA");
    if (!sl.chart) { assert.equal(rec.charts.length, 0); return; }
    assert.equal(rec.charts.length, 1);
    const data = rec.charts[0].data;
    assert.equal(rec.charts[0].type, sl.chart.type === "line" ? "line" : "bar");
    sl.chart.series.forEach((s, k) => {
      assert.equal(data[k].name, s.name);
      assert.deepEqual(data[k].values, s.points.map((p) => p.v));
      assert.deepEqual(data[k].labels, s.points.map((p) => p.y + (p.suspect ? " ◆" : "")));
    });
    if (sl.chart.type === "stack") assert.equal(rec.charts[0].o.barGrouping, "stacked");
  });
  const status = calls.slides[deck.slides.findIndex((s) => s.id === "status")];
  assert.equal(status.texts[1][1].color, "C0392B", "status colour read from the palette");
  const figTexts = calls.slides.flatMap((r) => r.texts.flatMap(([t]) => (Array.isArray(t) ? t.map((p) => p.text) : [t])));
  assert.ok(figTexts.some((t) => t.includes(D.fmtExact(ppOf(fin(LATEST).total_income, LATEST)))), "figure text from the model");
});

test("no model string uses a banned phrase or leaves a placeholder", () => {
  const decks = [
    D.schoolDeck(schoolModel(), CTX), D.schoolDeck(schoolModel({ noSx: true }), CTX), D.ptfaDeck(schoolModel(), CTX),
    D.ptfaDeck(D.adapt(sFixture({ withPta: false }), null, null, null), CTX), D.areaDeck(COUNCIL, ENGLAND, CTX),
    D.compareDeck([], CTX), D.schoolDeck(D.adapt(null), CTX), D.ptfaDeck(D.adapt(null), CTX),
    D.schoolDeck(D.adapt({ ...sFixture(), status: null, academy: true, trust: "Example Learning Trust" }, sxFixture(), null, null), CTX),
  ];
  decks.forEach((d, i) => {
    assertClean(d, "deck " + i);
    for (const s of strings(d)) assert.ok(!/\{(name|overseer|reserve|years)\}/.test(s), s);
    assert.ok(d.slides.length >= 1 && d.title && d.filename.endsWith(".pptx"));
  });
  const academy = decks[8];
  assert.ok(findSlide(academy, "questions").bullets.some((b) => b.includes("Example Learning Trust")), "{overseer} is the trust for academies");
});
