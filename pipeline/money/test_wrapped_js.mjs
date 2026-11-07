// Pure-model tests for assets/wrapped.js under node (no DOM, no network). Run: node --test pipeline/money/test_wrapped_js.mjs
// Fixtures are built here from the committed gold file data/gold/130932.json (William Patten Primary School).
// WRAPPED_CTX may name a context.json written by wrapped.context_doc() (test_wrapped_js.py does this).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// Arrange (shared): stubs before the scripts load; no test may reach the network.
const memory = new Map();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: { getItem: (k) => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, String(v)), removeItem: (k) => memory.delete(k) },
});
globalThis.fetch = () => Promise.reject(new Error("no network in tests"));
const here = dirname(fileURLToPath(import.meta.url));
await import(pathToFileURL(join(here, "assets", "app.js")).href);
await import(pathToFileURL(join(here, "assets", "wrapped.js")).href);
const MW = globalThis.MoneyWrapped;

const gold = JSON.parse(readFileSync(join(here, "data", "gold", "130932.json"), "utf8"));
const ifs = JSON.parse(readFileSync(join(here, "data", "ifs_context.json"), "utf8"));
const YEARS = Object.keys(gold.years).sort();
const LATEST = YEARS[YEARS.length - 1];
const PTA_YEARS = Object.keys(gold.ptfa.years).sort();
const REAL_LABEL = "in 2025-26 prices (HM Treasury GDP deflator, October 2026)";
// Built from fragments so this file never contains the phrases it guards against.
const BANNED = [["poor", "school"].join(" "), "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", ["no", "PTA"].join(" "), "30" + "7k"];

const pf = (y) => gold.years[y].totals.pipeline_finance_history;
function staffTotal(y) {
  const w = gold.years[y].totals.workbook_derived_columns;
  return w[Object.keys(w).find((k) => k.startsWith("Staff Total"))];
}
const GOLD_KEYS = ["total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "grant_funding", "self_generated", "sen_funding", "pupil_premium", "staff_total"];
const goldValue = (key, y) => (key === "staff_total" ? staffTotal(y) : pf(y)[key]);
const pupilsOf = (y) => pf(y).pupils;

function loadCtx() {
  if (process.env.WRAPPED_CTX) return JSON.parse(readFileSync(process.env.WRAPPED_CTX, "utf8"));
  // Same shape as wrapped.context_doc(), built from the IFS file when the Python wrapper isn't running us.
  const f = (k) => ({ key: k, ...ifs.framings[k] });
  const q = (k) => (ifs.questions[k] || {}).questions || [];
  const staff = ifs.context_lines.school.find((l) => l.id === "staff_share");
  const helps = { in_deficit: ["why_schools_go_into_deficit", "in_deficit"], heading_for_deficit: ["one_deficit_year", "heading_for_deficit"],
    tight: ["why_schools_go_into_deficit", "tight"], healthy: ["funding_vs_spending_per_pupil", "any"], large_reserves: ["one_deficit_year", "large_reserves"] };
  return {
    base_url: "https://money.schoolsinreach.com", real_label: REAL_LABEL,
    ifs: { cite: ifs.source.short_cite, url: ifs.source.url },
    staff: { line: staff, framing: f("why_schools_go_into_deficit") },
    framings: Object.fromEntries(Object.keys(ifs.framings).map((k) => [k, f(k)])),
    what_helps: Object.fromEntries(Object.entries(helps).map(([k, [fk, qk]]) => [k, { text: "What helps: a plan that is clear to everyone.", framing: f(fk), questions: q(qk) }])),
    any_questions: q("any"), school_lines: ifs.context_lines.school, council_lines: ifs.context_lines.council, national_lines: ifs.context_lines.national,
    pta: { not_found: "No registered parents' association found", register_note: "Charities with an income of £5,000 or less don't have to register with the Charity Commission, so a small parents' association may still exist.",
      overlap_note: "Money a parents' association gives the school can also appear in the school's own donations income, so the two are never added together.",
      source: "Charity Commission register", register_url: "https://www.gov.uk/setting-up-charity/register-your-charity" },
  };
}
const CTX = loadCtx();

// /data/s, /data/sx, /data/a fixtures from the gold file: pp = v / same-year pupils.
function fixture({ flags = [], pta = true, real = false } = {}) {
  const pupils = Object.fromEntries(YEARS.map((y) => [y, pupilsOf(y)]));
  const m = {};
  for (const k of GOLD_KEYS) {
    m[k] = {};
    for (const y of YEARS) {
      const v = goldValue(k, y);
      if (v == null) continue;
      m[k][y] = { v, pp: v / pupils[y] };
      if (real) { const idx = { "2018-19": 0.78, "2019-20": 0.8 }[y] || 1; m[k][y].r = v / idx; m[k][y].rpp = v / idx / pupils[y]; }
    }
  }
  const sxPta = {};
  if (pta) {
    for (const y of PTA_YEARS) {
      const r = gold.ptfa.years[y], b = gold.ptfa.breakdown[y] || {};
      sxPta[y] = { income: r.income, spend: r.expenditure, income_pp: r.income / pupils[y], spend_pp: r.expenditure / pupils[y], charity_number: String(gold.ptfa.charity_number),
        confidence: "high", volunteers: r.volunteers, income_lines: b.income_lines, expenditure_lines: b.expenditure_lines };
    }
  }
  const L = pf(LATEST);
  const s = {
    urn: gold.urn, name: gold.name, path: "/school/130932-william-patten-primary-school/",
    council: { code: String(gold.la.code), name: gold.la.name, path: "/council/hackney/" },
    status: "in_deficit", label: "In deficit", reason: "Reserve below zero.", year: LATEST, academy: false, trust: null,
    pupils: L.pupils, income: L.total_income, spend: L.total_expenditure, reserve: L.revenue_reserve,
    years: YEARS.map((y) => ({ y, income: pf(y).total_income, spend: pf(y).total_expenditure, balance: pf(y).in_year_balance, reserve: pf(y).revenue_reserve, pupils: pf(y).pupils, status: null })),
    pp: { total_expenditure: Math.round(L.total_expenditure / L.pupils), grant_funding: Math.round(L.grant_funding / L.pupils), total_income: Math.round(L.total_income / L.pupils) },
    similar: { total_expenditure: 8650, grant_funding: 7600, total_income: 8200 },
    pta: pta ? [{ charity_number: String(gold.ptfa.charity_number), name: gold.ptfa.name, status: gold.ptfa.status, latest_income: gold.ptfa.latest.income,
      history: PTA_YEARS.map((y) => ({ period_end: "20" + y.slice(5) + "-08-31", income: gold.ptfa.years[y].income, expenditure: gold.ptfa.years[y].expenditure })) }] : [],
    tags: { governance: "council-run", phase: "primary" }, band: 3, streak: 3,
  };
  const sx = { years: YEARS, source: "CFR", pupils, m, gap: null, pta: sxPta, flags, trust_central_pp: null };
  const council = { id: "council-204", type: "council", name: "Hackney", path: "/council/hackney/",
    by_year: { [LATEST]: { all: { schools: 58, in_deficit: 14, in_deficit_pct: 24.1 } } }, dsg: { [LATEST]: { balance: -21500000, per_pupil: -640 } } };
  const england = { id: "england", type: "england", name: "England",
    by_year: { "2024-25": { all: { schools: 20100, pta_schools: 9100, pta_pp_median: 31, pta_pp_by_band: { 1: 96, 5: 6 } } } } };
  return { s, sx, council, england };
}
function model(opts = {}, mode = "school") {
  const f = fixture(opts);
  const data = MW.adapt(f.s, f.sx, f.council, f.england, { ...CTX, real_label: opts.realLabel === undefined ? CTX.real_label : opts.realLabel });
  return { data, m: MW.buildCards(data, mode) };
}
function strings(value, out = []) {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => strings(v, out));
  else if (value && typeof value === "object") Object.values(value).forEach((v) => strings(v, out));
  return out;
}
const card = (m, id) => m.cards.find((c) => c.id === id);

test("MoneyWrapped exports the model", () => {
  for (const k of ["adapt", "buildCards", "planFrames", "drawCard", "encodeVideo", "chooseEncoder", "shareLinks", "shareVideo"]) assert.equal(typeof MW[k], "function", k);
});

test("school mode has 8 to 10 cards in story order, opening on the school", () => {
  // Act
  const { m } = model();
  // Assert
  assert.ok(m.cards.length >= 8 && m.cards.length <= 10, String(m.cards.length));
  assert.deepEqual(m.cards.map((c) => c.id), ["intro", "pupils", "funding", "staff", "reserve", "similar", "council", "pta", "helps", "outro"]);
  assert.equal(m.cards[0].title, "William Patten Primary School: your year in money");
  for (const c of m.cards) {
    for (const k of ["id", "kind", "title", "big", "lines", "figures", "chart", "alt"]) assert.ok(k in c, c.id + " " + k);
    assert.ok(c.alt.length > 10, c.id);
  }
});

test("every £ figure in the card model equals the gold file, per pupil = round(v / same-year pupils)", () => {
  // Arrange
  const { m } = model();
  let checked = 0;
  // Act / Assert
  for (const c of m.cards) {
    for (const f of c.figures) {
      assert.ok(f.year && f.source, c.id + " figure without year or source");
      if (GOLD_KEYS.includes(f.key)) {
        assert.equal(f.v, goldValue(f.key, f.year), `${c.id} ${f.key} ${f.year}`);
        assert.equal(f.pp, Math.round(f.v / pupilsOf(f.year)), `${c.id} ${f.key} ${f.year} pp`);
        checked++;
      } else if (f.key === "pta_income" || f.key === "pta_spend") {
        const row = gold.ptfa.years[f.year];
        assert.equal(f.v, f.key === "pta_income" ? row.income : row.expenditure);
        assert.equal(f.pp, Math.round(f.v / pupilsOf(f.year)));
        assert.equal(f.source, "Charity Commission register");
        checked++;
      } else if (f.key === "pupils") {
        assert.equal(f.v, pupilsOf(f.year));
        checked++;
      }
    }
  }
  assert.ok(checked >= 9, "only " + checked + " figures checked");
  const funding = card(m, "funding");
  assert.equal(funding.big.text, MW.fmtExact(Math.round(pf(LATEST).grant_funding / pf(LATEST).pupils)));
  assert.equal(funding.big.text, "£8,297");
  assert.equal(card(m, "pupils").big.text, "432.5");
  assert.match(funding.source, /2025-26, DfE CFR return/);
});

test("SERIES key names (total_staff, grant_funding_government, self_generated_income) are read too", () => {
  // Arrange: the build's /data/sx uses series.METRICS names
  const f = fixture();
  for (const [from, to] of [["staff_total", "total_staff"], ["grant_funding", "grant_funding_government"], ["self_generated", "self_generated_income"]]) {
    f.sx.m[to] = f.sx.m[from];
    delete f.sx.m[from];
  }
  // Act
  const data = MW.adapt(f.s, f.sx, f.council, f.england, CTX);
  const staff = card(MW.buildCards(data, "school"), "staff");
  // Assert
  assert.equal(data.latest.staff, staffTotal(LATEST));
  assert.equal(data.latest.grant, pf(LATEST).grant_funding);
  assert.ok(staff.big, "the staff card has a headline figure");
  assert.ok(!strings(staff).some((x) => /isn't published yet/.test(x)), strings(staff).join(" | "));
});

test("the reserve chart is exactly the published reserves, every year in order", () => {
  // Act
  const pts = card(model().m, "reserve").chart.points;
  // Assert
  assert.deepEqual(pts.map((p) => p.y), YEARS);
  assert.deepEqual(pts.map((p) => p.v), YEARS.map((y) => pf(y).revenue_reserve));
  assert.equal(pts.find((p) => p.y === "2019-20").v, 543908);
  assert.equal(pts.find((p) => p.y === "2025-26").v, -210901);
  assert.equal(YEARS[0], "2018-19");
  assert.ok(pts.every((p) => p.suspect === false));
});

test("a deficit is named alongside why (IFS, with pages) and what helps", () => {
  // Act
  const c = card(model().m, "reserve");
  const text = c.lines.join(" ");
  // Assert
  assert.equal(c.status.key, "in_deficit");
  assert.equal(c.status.icon, "▼");
  assert.match(text, /80%.*\(IFS, pp\.62, 63\)/);
  assert.match(text, /What helps:/);
  assert.match(text, /-£488 per pupil/);
  const helps = card(model().m, "helps");
  assert.ok(helps.lines.some((l) => /^What helps:/.test(l)));
  assert.ok(helps.lines.some((l) => /^Ask: /.test(l) && !/\{name\}/.test(l)));
  const council = card(model().m, "council").lines.join(" ");
  assert.match(council, /statutory override.*\(IFS, p\.61\)/);
  assert.match(council, /What helps:/);
  assert.match(card(model().m, "staff").lines.join(" "), /over 80% of schools' costs are staff costs\. \(IFS, p\.63\)/);
});

test("the PTFA card equals the register's income each year", () => {
  // Act
  const { m } = model();
  const c = card(m, "pta");
  // Assert
  assert.deepEqual(c.chart.points.map((p) => p.y), PTA_YEARS);
  assert.deepEqual(c.chart.points.map((p) => p.v), PTA_YEARS.map((y) => gold.ptfa.years[y].income));
  const latest = c.figures.find((f) => f.key === "pta_income");
  assert.equal(latest.v, 48547);
  assert.equal(latest.year, "2024-25");
  assert.match(c.lines.join(" "), /never added together/);
});

test("PTFA mode: money over the years, England gap, Part B lines, thanks and outro", () => {
  // Act
  const { m } = model({}, "ptfa");
  // Assert
  assert.equal(m.mode, "ptfa");
  assert.deepEqual(m.cards.map((c) => c.id), ["intro", "pta-money", "pta-gap", "pta-spend", "thanks", "outro"]);
  assert.deepEqual(card(m, "pta-money").chart.points.map((p) => p.v), PTA_YEARS.map((y) => gold.ptfa.years[y].income));
  const lines = gold.ptfa.breakdown["2024-25"].expenditure_lines;
  const spend = card(m, "pta-spend");
  assert.equal(spend.big.text, "2024-25");
  for (const f of spend.figures) assert.equal(f.v, lines[f.label]);
  assert.equal(spend.figures[0].v, Math.max(...Object.values(lines)));
  assert.match(card(m, "pta-gap").lines.join(" "), /not in the IFS report/);
  assert.match(card(m, "thanks").lines.join(" "), new RegExp("About " + gold.ptfa.years["2024-25"].volunteers + " volunteers helped in 2024-25"));
  assert.match(m.share.url, /\/school\/130932-william-patten-primary-school\/video\/\?mode=ptfa$/);
});

test("PTFA rank appears only when the data carries it", () => {
  // Arrange
  const f = fixture();
  f.s.pta_rank = { council: { rank: 4, of: 31 }, band: { rank: 2, of: 12, band: 3 } };
  // Act
  const m = MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "ptfa");
  const without = model({}, "ptfa").m;
  // Assert
  assert.match(card(m, "pta-rank").lines.join(" "), /Number 4 of 31 .* Hackney/);
  assert.match(card(m, "pta-rank").lines.join(" "), /band 3 of 5/);
  assert.equal(card(without, "pta-rank"), undefined);
});

test("a school with no registered PTA gets the honest wording", () => {
  for (const mode of ["school", "ptfa"]) {
    // Act
    const { m } = model({ pta: false }, mode);
    const all = strings(m).join(" ");
    // Assert
    assert.match(all, /No registered parents' association found/);
    assert.match(all, /£5,000 or less/);
    assert.doesNotMatch(all, new RegExp(BANNED[5], "i"));
  }
  assert.ok(card(model({ pta: false }, "ptfa").m, "register"));
});

test("suspect years in all three flag shapes are marked, never the headline", () => {
  const shapes = [["2025-26"], [{ year: "2025-26", code: "jump", text: "Reserve moved sharply" }], { "2025-26": ["Reserve moved sharply"] }];
  for (const flags of shapes) {
    // Act
    const { data, m } = model({ flags });
    const reserve = card(m, "reserve");
    // Assert
    assert.equal(data.latest.y, "2024-25");
    assert.deepEqual(reserve.chart.points.map((p) => p.y), YEARS, "suspect year still shown");
    assert.equal(reserve.chart.points.find((p) => p.y === "2025-26").suspect, true);
    assert.equal(reserve.chart.points.filter((p) => p.suspect).length, 1);
    assert.equal(reserve.big.v, pf("2024-25").revenue_reserve);
    assert.ok(reserve.lines.some((l) => /Marked year: 2025-26/.test(l)));
    assert.equal(card(m, "funding").big.text, MW.fmtExact(Math.round(pf("2024-25").grant_funding / pf("2024-25").pupils)));
    assert.equal(card(m, "intro").big.text, "2024-25");
    assert.match(m.share.text, /2024-25/);
    assert.doesNotMatch(m.share.text, /2025-26/);
    assert.match(reserve.alt, /2025-26 -£210,901 \(marked year\)/);
  }
});

test("a marked comparison year leaves out the similar-schools card rather than headlining it", () => {
  // Act
  const { m } = model({ flags: [LATEST] });
  // Assert
  assert.equal(card(m, "similar"), undefined);
  assert.ok(m.cards.length >= 8 && m.cards.length <= 10, String(m.cards.length));
});

test("with every year marked, the reserves stay in the chart and no card calls them unpublished", () => {
  // Act
  const { data, m } = model({ flags: YEARS });
  const reserve = card(m, "reserve");
  // Assert
  assert.equal(data.latest, null);
  assert.deepEqual(reserve.chart.points.map((p) => [p.y, p.v, p.suspect]), YEARS.map((y) => [y, pf(y).revenue_reserve, true]));
  assert.equal(reserve.big.v, null);
  assert.ok(reserve.lines.some((l) => /^Marked years: /.test(l)));
  for (const id of ["pupils", "funding", "staff", "reserve"]) assert.doesNotMatch(card(m, id).lines.join(" "), /published yet/, id);
});

test("PTA per pupil is the published value or same-year pupils, never another year's", () => {
  for (const published of [true, false]) {
    // Arrange
    const f = fixture();
    const y = PTA_YEARS[PTA_YEARS.length - 1], row = f.sx.pta[y];
    const want = published ? [Math.round(row.income_pp), Math.round(row.spend_pp)] : [null, null];
    if (!published) { delete row.income_pp; delete row.spend_pp; }
    delete f.sx.pupils[y];
    delete f.s.years.find((r) => r.y === y).pupils;
    // Act
    const c = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "ptfa"), "pta-money");
    // Assert
    assert.deepEqual(["pta_income", "pta_spend"].map((k) => c.figures.find((x) => x.key === k).pp), want, "published=" + published);
  }
});

test("the England PTA gap uses the latest year with PTA figures, not the latest year overall", () => {
  // Arrange
  const f = fixture();
  f.england.by_year[LATEST] = { all: { schools: 20100, pta_schools: 0, pta_pp_median: null } };
  // Act
  const gap = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "ptfa"), "pta-gap");
  // Assert
  assert.ok(gap);
  assert.ok(gap.figures.every((x) => x.year === "2024-25"));
  assert.match(gap.lines.join(" "), /9100 of 20100 schools/);
});

test("real terms appear only with sx r/rpp and the deflator caption", () => {
  // Act
  const withReal = card(model({ real: true }).m, "funding").lines.join(" ");
  const noLabel = card(model({ real: true, realLabel: null }).m, "funding").lines.join(" ");
  const noReal = card(model().m, "funding").lines.join(" ");
  // Assert
  assert.match(withReal, new RegExp("Shown " + REAL_LABEL.replace(/[()]/g, "\\$&")));
  assert.doesNotMatch(noLabel, /prices/);
  assert.doesNotMatch(noReal, /prices/);
});

test("missing documents become cards in words", () => {
  // Act
  const none = MW.buildCards(null, "school");
  const err = MW.buildCards({ error: "Figures for this school aren't published yet.", path: "/school/1-x/" }, "school");
  const f = fixture();
  const bare = MW.buildCards(MW.adapt(f.s, null, null, null, null), "school");
  // Assert
  assert.equal(none.cards.length, 1);
  assert.match(err.cards[0].lines[0], /aren't published yet/);
  assert.equal(err.cards[0].link, "/school/1-x/");
  assert.match(card(bare, "council").lines.join(" "), /aren't published yet/);
  assert.deepEqual(card(bare, "reserve").chart.points.map((p) => p.v), YEARS.map((y) => pf(y).revenue_reserve));
});

test("planFrames: cards x fps x seconds, keyframes exactly at card starts", () => {
  // Act
  const frames = MW.planFrames(10);
  const short = MW.planFrames(3, 30, 3);
  // Assert
  assert.equal(frames.length, 10 * 30 * 3);
  assert.deepEqual(frames.filter((f) => f.key).map((f) => f.frame), [0, 90, 180, 270, 360, 450, 540, 630, 720, 810]);
  assert.deepEqual(short.map((f) => f.frame), [...Array(270).keys()]);
  const first = short.filter((f) => f.card === 0);
  assert.equal(first[0].t, 0);
  assert.equal(first[first.length - 1].t, 1);
  assert.ok(first.every((f, i) => i === 0 || f.t > first[i - 1].t));
  assert.equal(first.filter((f) => f.transition).length, 12, "last 0.4 s at 30 fps");
  assert.equal(short.filter((f) => f.card === 2 && f.fade > 0).length, 0, "the last card holds");
});

function fakeEncoders({ supported = ["avc1.640028"] } = {}) {
  const log = { checked: [], configs: [], encoded: [], frames: [], chunks: 0, order: [] };
  class VideoFrame {
    constructor(source, init) { this.source = source; this.timestamp = init.timestamp; this.duration = init.duration; this.closed = false; log.frames.push(this); }
    close() { this.closed = true; }
  }
  class VideoEncoder {
    static isConfigSupported(c) { log.checked.push(c.codec); return Promise.resolve({ supported: supported.includes(c.codec), config: c }); }
    constructor(init) { this.init = init; this.encodeQueueSize = 0; }
    configure(c) { log.configs.push(c); }
    encode(frame, opts) {
      log.encoded.push({ timestamp: frame.timestamp, key: opts.keyFrame, open: !frame.closed });
      this.init.output({ type: opts.keyFrame ? "key" : "delta", timestamp: frame.timestamp }, {});
    }
    flush() { log.order.push("flush"); return Promise.resolve(); }
    close() { log.order.push("close"); }
  }
  class ArrayBufferTarget { constructor() { this.buffer = null; } }
  class Muxer {
    constructor(o) { this.o = o; log.muxer = o; }
    addVideoChunk() { log.chunks++; }
    finalize() { log.order.push("finalize"); this.o.target.buffer = new ArrayBuffer(32); }
  }
  return { log, VideoFrame, VideoEncoder, ArrayBufferTarget, Muxer };
}

test("encodeVideo drives WebCodecs and the muxer frame by frame", async () => {
  // Arrange
  const F = fakeEncoders();
  const cards = model().m.cards.slice(0, 3), rendered = [], progress = [];
  // Act
  const out = await MW.encodeVideo({ cards, fps: 30, seconds: 3, render: (f) => { rendered.push(f.frame); return { canvas: f.frame }; },
    VideoEncoder: F.VideoEncoder, VideoFrame: F.VideoFrame, Muxer: F.Muxer, ArrayBufferTarget: F.ArrayBufferTarget, onProgress: (p) => progress.push(p) });
  // Assert
  assert.equal(F.log.frames.length, 270);
  assert.equal(F.log.chunks, 270);
  assert.deepEqual(F.log.encoded.map((e, i) => (e.key ? i : -1)).filter((i) => i >= 0), [0, 90, 180]);
  assert.ok(F.log.encoded.every((e) => e.open), "encoded before close");
  assert.ok(F.log.frames.every((f) => f.closed), "every frame closed");
  assert.ok(F.log.encoded.every((e, i) => i === 0 || e.timestamp > F.log.encoded[i - 1].timestamp), "monotonic timestamps");
  assert.equal(F.log.encoded[1].timestamp, Math.round(1e6 / 30));
  assert.equal(F.log.frames[0].duration, Math.round(1e6 / 30));
  assert.deepEqual(F.log.order, ["flush", "close", "finalize"]);
  assert.equal(F.log.checked[0], "avc1.640028");
  assert.deepEqual({ codec: F.log.configs[0].codec, width: F.log.configs[0].width, height: F.log.configs[0].height, framerate: F.log.configs[0].framerate, bitrate: F.log.configs[0].bitrate },
    { codec: "avc1.640028", width: 1080, height: 1920, framerate: 30, bitrate: 6e6 });
  assert.deepEqual(F.log.muxer.video, { codec: "avc", width: 1080, height: 1920 });
  assert.equal(F.log.muxer.fastStart, "in-memory");
  assert.ok(F.log.muxer.target instanceof F.ArrayBufferTarget);
  assert.deepEqual(rendered, [...Array(270).keys()]);
  assert.equal(progress[progress.length - 1], 1);
  assert.ok(progress.every((p, i) => p >= 0 && p <= 1 && (i === 0 || p >= progress[i - 1])));
  assert.equal(out.type, "video/mp4");
  assert.ok(out.blob instanceof Blob);
  assert.equal(out.blob.type, "video/mp4");
});

test("encodeVideo falls back through the codec list and fails clearly when none fit", async () => {
  // Arrange
  const F = fakeEncoders({ supported: ["avc1.4d0028"] });
  const N = fakeEncoders({ supported: [] });
  const args = (X) => ({ cards: [model().m.cards[0]], fps: 2, seconds: 1, render: () => ({}), VideoEncoder: X.VideoEncoder, VideoFrame: X.VideoFrame, Muxer: X.Muxer, ArrayBufferTarget: X.ArrayBufferTarget });
  // Act
  await MW.encodeVideo(args(F));
  // Assert
  assert.equal(F.log.configs[0].codec, "avc1.4d0028");
  await assert.rejects(MW.encodeVideo(args(N)), /can't make an MP4/);
  await assert.rejects(MW.encodeVideo({ cards: [] }), /WebCodecs/);
});

test("chooseEncoder picks webcodecs, then MediaRecorder, then PNG", () => {
  // Arrange
  const canvas = { captureStream() {} };
  function VideoEncoder() {} function MediaRecorder() {}
  // Act / Assert
  assert.equal(MW.chooseEncoder({ VideoEncoder, Muxer: function () {}, MediaRecorder, canvas }), "webcodecs");
  assert.equal(MW.chooseEncoder({ VideoEncoder, Mp4Muxer: { Muxer: function () {} } }), "webcodecs");
  assert.equal(MW.chooseEncoder({ VideoEncoder, MediaRecorder, canvas }), "mediarecorder");
  assert.equal(MW.chooseEncoder({ MediaRecorder, canvas: {} }), "png");
  assert.equal(MW.chooseEncoder({}), "png");
});

test("shareLinks encodes the text and URL for every network", () => {
  // Arrange
  const url = "https://money.schoolsinreach.com/school/1-a/video/?mode=ptfa", text = "A & B's year: £8,297 per pupil";
  // Act
  const L = MW.shareLinks(url, text);
  // Assert
  assert.equal(L.whatsapp, "https://wa.me/?text=" + encodeURIComponent(text + " " + url));
  assert.equal(L.x, "https://twitter.com/intent/tweet?text=" + encodeURIComponent(text) + "&url=" + encodeURIComponent(url));
  assert.equal(L.facebook, "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(url));
  assert.match(L.email, /^mailto:\?subject=School%20money%20in%2030%20seconds&body=/);
  for (const v of Object.values(L)) assert.doesNotMatch(v.split("?").slice(1).join("?"), /[ &]B|£/);
});

test("shareVideo uses native file sharing when canShare, else the fallback", async () => {
  // Arrange
  const file = { name: "x.mp4", type: "video/mp4" }, share = { title: "T", text: "Plain words", url: "https://money.schoolsinreach.com/school/1-a/video/" };
  const calls = [];
  const yes = { canShare: (d) => d.files[0] === file, share: (d) => { calls.push(d); return Promise.resolve(); } };
  const no = { canShare: () => false, share: () => { throw new Error("must not share"); } };
  // Act
  const a = await MW.shareVideo(file, share, yes);
  const b = await MW.shareVideo(file, share, no);
  const c = await MW.shareVideo(file, share, {});
  // Assert
  assert.equal(a.method, "native");
  assert.deepEqual(calls[0], { files: [file], title: "T", text: "Plain words", url: share.url });
  assert.equal(b.method, "fallback");
  assert.equal(b.copy, share.url);
  assert.equal(b.download, file);
  assert.equal(b.links.facebook, "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(share.url));
  assert.equal(c.method, "fallback");
});

function fakeCanvas() {
  const calls = [];
  const g = {
    font: "10px x", fillStyle: "", strokeStyle: "", lineWidth: 1, globalAlpha: 1, textAlign: "left", textBaseline: "top",
    measureText(t) { const m = /(\d+)px/.exec(this.font); return { width: String(t).length * (m ? +m[1] : 10) * 0.55 }; },
    fillText(t, x, y) { calls.push({ op: "fillText", t: String(t), x, y, align: this.textAlign, width: this.measureText(t).width, alpha: this.globalAlpha }); },
    fillRect(x, y, w, h) { calls.push({ op: "fillRect", x, y, w, h, style: this.fillStyle }); },
  };
  for (const k of ["save", "restore", "beginPath", "moveTo", "lineTo", "stroke", "fill", "arc", "rect", "roundRect"]) g[k] = (...a) => calls.push({ op: k, a });
  return { g, calls };
}
const PALETTE = Object.fromEntries(MW.PALETTE_KEYS.map((k, i) => [k, "#" + String(100000 + i * 1111).slice(0, 6)]));

test("drawCard counts up with t, keeps text inside the safe margins and draws the QR on the outro", () => {
  // Arrange
  const { m } = model();
  const funding = card(m, "funding"), outro = card(m, "outro");
  const qr = { size: 21, dark: (r, c) => (r + c) % 2 === 0 };
  // Act
  const at0 = fakeCanvas(), at1 = fakeCanvas(), still = fakeCanvas(), withQr = fakeCanvas(), noQr = fakeCanvas();
  MW.drawCard(at0.g, funding, 0, PALETTE, { index: 2, count: 10 });
  MW.drawCard(at1.g, funding, 1, PALETTE, { index: 2, count: 10 });
  MW.drawCard(still.g, funding, 0, PALETTE, { index: 2, count: 10, reducedMotion: true });
  MW.drawCard(withQr.g, outro, 1, PALETTE, { qr });
  MW.drawCard(noQr.g, outro, 1, PALETTE, {});
  // Assert
  const texts = (c) => c.calls.filter((x) => x.op === "fillText").map((x) => x.t);
  assert.ok(texts(at0).includes("£0"));
  assert.ok(texts(at1).includes("£8,297"));
  assert.ok(texts(still).includes("£8,297"), "reduced motion draws the final card");
  const modules = (c) => c.calls.filter((x) => x.op === "fillRect").length;
  assert.ok(modules(withQr) - modules(noQr) > 100, "QR modules drawn");
  assert.ok(texts(noQr).some((t) => t.includes("money.schoolsinreach.com")), "URL text without the QR");
  for (const c of m.cards) {
    for (const t of [0, 0.5, 1]) {
      const f = fakeCanvas();
      MW.drawCard(f.g, c, t, PALETTE, { index: 0, count: m.cards.length, qr: c.qr ? qr : null });
      if (t === 1) assert.ok(!f.calls.some((x) => x.op === "fillText" && x.t.endsWith("…")), `${c.id}: every line fits without cutting`);
      for (const x of f.calls.filter((y) => y.op === "fillText" && y.align === "left")) {
        assert.ok(x.x >= 90 && x.x + x.width <= 1080 - 90 + 1, `${c.id} t=${t} "${x.t}" overflows`);
        assert.ok(x.y >= 0 && x.y < 1920, `${c.id} y`);
      }
    }
  }
});

test("the outro draws the whole school URL, wrapped and uncut, with or without the QR", () => {
  // Arrange
  const f = fixture();
  f.s.path = "/school/130932-st-mary-and-st-johns-church-of-england-voluntary-aided-primary-school-and-nursery/";
  const outro = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "school"), "outro");
  const url = outro.qr.url.replace(/^https?:\/\//, "");
  for (const qr of [null, { size: 21, dark: () => true }]) {
    // Act
    const c = fakeCanvas();
    MW.drawCard(c.g, outro, 1, PALETTE, { qr });
    // Assert
    const texts = c.calls.filter((x) => x.op === "fillText");
    assert.ok(texts.map((x) => x.t).join("").includes(url), "whole URL drawn");
    assert.ok(!texts.some((x) => x.t.endsWith("…")), "nothing cut");
    for (const x of texts.filter((y) => y.align === "left")) assert.ok(x.x + x.width <= 1080 - 90 + 1, `"${x.t}" overflows`);
  }
});

test("wrapText breaks long words and lines at the width", () => {
  // Arrange
  const { g } = fakeCanvas();
  g.font = "40px x";
  // Act
  const lines = MW.wrapText(g, "money.schoolsinreach.com/school/130932-william-patten-primary-school/ is the page for every figure", 600);
  // Assert
  assert.ok(lines.length > 2);
  for (const l of lines) assert.ok(g.measureText(l).width <= 600, l);
});

test("library URLs are pinned exactly once in wrapped.js", () => {
  // Arrange
  const src = readFileSync(join(here, "assets", "wrapped.js"), "utf8");
  // Act / Assert
  for (const url of Object.values(MW.LIBS)) {
    assert.match(url, /^https:\/\/(cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net)\/.*@?\d+\.\d+\.\d+/);
    assert.equal(src.split(url).length - 1, 1, url);
  }
});

test("no banned words in any card string, either mode, or in the unit's front-end sources", () => {
  // Arrange
  const models = [model().m, model({}, "ptfa").m, model({ pta: false }).m, model({ pta: false }, "ptfa").m, model({ flags: ["2022-23"] }).m, model({ real: true }).m, MW.buildCards(null, "school")];
  const sources = ["wrapped.js", "wrapped.css"].map((f) => readFileSync(join(here, "assets", f), "utf8"));
  // Act
  const all = models.flatMap((m) => strings(m)).concat(sources);
  // Assert
  for (const text of all) for (const word of BANNED) assert.ok(!text.toLowerCase().includes(word.toLowerCase()), `"${word}" in: ${text.slice(0, 120)}`);
});

test("the funding card shows spending per pupil in red when the school spent more than came in", () => {
  // Arrange: William Patten 2025-26 spent £4,097,753 against £3,927,968 income
  const { m } = model();
  const L = pf(LATEST), spp = Math.round(L.total_expenditure / L.pupils), ipp = Math.round(L.total_income / L.pupils);
  // Act
  const c = card(m, "funding");
  // Assert
  assert.equal(c.verdict.tone, "bad");
  assert.ok(c.verdict.text.includes(spp.toLocaleString("en-GB")), c.verdict.text);
  assert.ok(c.verdict.sub.includes((spp - ipp).toLocaleString("en-GB")) && c.verdict.sub.startsWith("▼"), c.verdict.sub);
  assert.ok(c.lines.some((l) => l.startsWith("Spending was ")), "the text version says it too");
});

test("the funding card is green when a school spent less than came in", () => {
  // Arrange: a year with an in-year surplus
  const f = fixture();
  const y = LATEST;
  f.sx.m.total_expenditure[y] = { v: pf(y).total_income - 43_250, pp: (pf(y).total_income - 43_250) / pf(y).pupils };
  // Act
  const c = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "school"), "funding");
  // Assert
  assert.equal(c.verdict.tone, "good");
  assert.ok(c.verdict.sub.startsWith("✓"), c.verdict.sub);
});

test("PTFA comparison bars put this PTFA beside England in the same year", () => {
  // Act
  const c = card(model({}, "ptfa").m, "pta-gap");
  // Assert
  assert.equal(c.title, "How the PTFA compares");
  assert.ok(c.bars && c.bars.length >= 2, JSON.stringify(c.bars));
  assert.ok(c.bars[0].mine && c.bars[0].label === "This PTFA");
  assert.ok(c.bars.some((b) => b.label === "England's middle PTA" && b.v === 31));
  assert.ok(c.barsNote.includes("2024-25"));
});

test("every card is drawn on its own bold background", () => {
  // Arrange
  const fills = [];
  const g = new Proxy({}, { get: (o, k) => (k in o ? o[k] : (k === "measureText" ? () => ({ width: 100 }) : () => {})),
    set: (o, k, v) => { if (k === "fillStyle") fills.push(v); o[k] = v; return true; } });
  const { m } = model();
  // Act
  const firsts = m.cards.map((c, i) => { fills.length = 0; MW.drawCard(g, c, 1, {}, { index: i, count: m.cards.length }); return fills[0]; });
  // Assert: the first fill is the card background, and the cards don't all share one
  assert.ok(new Set(firsts).size >= 5, firsts.join(","));
  assert.ok(firsts.every((f) => /^#[0-9A-F]{6}$/i.test(f)), firsts.join(","));
});

// ---------------------------------------------------------------- nearby (the SHARED 'nearby' contract in /data/s)
// A synthetic contract in exactly the SHARED shape: this school's row from the gold file's 2024-25 return, then 8
// fictional neighbours nearest first (one without a 2024-25 return, two academies, PTA years 2024-25 and 2023-24).
// rank and medians are worked out from the rows, as the build does.
const NEARBY_YEAR = "2024-25";
function nearbyContract() {
  const g = pf(NEARBY_YEAR), pp = (v) => Math.round(v / g.pupils);
  const self = { urn: String(gold.urn), name: gold.name, p: "/school/130932-william-patten-primary-school/", mi: 0, status: "in_deficit",
    pupils: g.pupils, spend_pp: pp(g.total_expenditure), income_pp: pp(g.total_income), gov_pp: pp(g.grant_funding), reserve_pp: pp(g.revenue_reserve),
    fsm_pct: g.fsm_pct, pta_pp: pp(gold.ptfa.years[NEARBY_YEAR].income), pta_year: NEARBY_YEAR };
  const row = (urn, name, mi, extra) => ({ urn: String(urn), name, p: `/school/${urn}-x/`, mi, ...extra });
  const schools = [
    row(900001, "Elm Lane Primary School", 0.2, { status: "healthy", pupils: 410, spend_pp: 9120, fsm_pct: 22.4, pta_pp: 64, pta_year: "2024-25" }),
    row(900002, "Oak Hill Primary School", 0.3, { status: "tight", pupils: 380.5, spend_pp: 8410, fsm_pct: 31, pta_pp: 12, pta_year: "2023-24" }),
    row(900003, "Birch Road Primary School", 0.4, { fsm_pct: 18.2, pta_pp: 40, pta_year: "2024-25" }),
    row(900004, "St Anne's Church of England Primary School", 0.5, { status: "healthy", pupils: 205, spend_pp: 8990, fsm_pct: 15, pta_pp: 85, pta_year: "2024-25" }),
    row(900005, "Rowan Academy", 0.6, { academy: true, status: "large_reserves", pupils: 630, spend_pp: 8200, fsm_pct: 40.1 }),
    row(900006, "Maple Grove Primary School", 0.7, { status: "healthy", pupils: 300, spend_pp: 9500, pta_pp: 20, pta_year: "2024-25" }),
    row(900007, "Willow Park Primary Academy", 0.8, { academy: true, pupils: 415, spend_pp: 8700 }),
    row(900008, "Hazel Street Primary School", 0.9, { status: "healthy", pupils: 240, spend_pp: 8050 }),
  ];
  const values = [self, ...schools].map((r) => r.spend_pp).filter((v) => v != null).sort((a, b) => a - b);
  const mid = values.length % 2 ? values[(values.length - 1) / 2] : (values[values.length / 2 - 1] + values[values.length / 2]) / 2;
  return { year: NEARBY_YEAR, phase: "Primary", radius_mi: 0.9, self, schools,
    medians: { spend_pp: Math.round(mid) },
    rank: { spend_pp: { rank: values.filter((v) => v > self.spend_pp).length + 1, of: values.length } } };
}
function nearbyModel(nearby, mode = "school", edit = () => {}) {
  const f = fixture();
  if (nearby !== undefined) f.s.nearby = nearby;
  edit(f);
  return MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), mode);
}
const textOf = (c) => strings(c).join(" | ");

test("the nearby card follows the similar card and shows the contract's spending rank", () => {
  // Arrange
  const contract = nearbyContract();
  // Act
  const m = nearbyModel(contract);
  const c = card(m, "nearby");
  // Assert
  assert.deepEqual(m.cards.map((x) => x.id), ["intro", "pupils", "funding", "staff", "reserve", "similar", "nearby", "council", "pta", "helps", "outro"]);
  const { rank, of } = contract.rank.spend_pp;
  assert.equal(c.big.text, `${rank}th of ${of}`);
  assert.equal(c.big.text, "4th of 8");
  assert.equal(c.big.unit, "for spending per pupil among nearby primary schools");
  assert.ok(c.lines[0].includes("the 4th highest of 8 nearby primary schools"), c.lines[0]);
  assert.ok(c.lines[0].includes(MW.fmtExact(contract.medians.spend_pp)), c.lines[0]);
});

test("nearby bars are the contract's spend_pp for this school and its 4 nearest neighbours with figures", () => {
  // Arrange
  const contract = nearbyContract();
  const nearest = contract.schools.filter((r) => r.spend_pp != null).slice(0, 4);
  // Act
  const c = card(nearbyModel(contract), "nearby");
  // Assert
  assert.deepEqual(c.bars.map((b) => b.v), [contract.self.spend_pp, ...nearest.map((r) => r.spend_pp)]);
  assert.equal(c.bars[0].v, Math.round(pf(NEARBY_YEAR).total_expenditure / pf(NEARBY_YEAR).pupils), "this school's bar is its gold 2024-25 figure");
  assert.deepEqual(c.bars.map((b) => b.label), ["This school", "Elm Lane", "Oak Hill", "St Anne's", "Rowan"]);
  assert.deepEqual(c.bars.map((b) => !!b.mine), [true, false, false, false, false]);
  assert.deepEqual(c.bars.map((b) => b.text), c.bars.map((b) => MW.fmtExact(b.v)));
  assert.ok(c.barsNote.startsWith("Spending per pupil, 2024-25"), c.barsNote);
  assert.ok(c.figures.length >= 5 && c.figures.every((f) => f.year === NEARBY_YEAR && f.source), JSON.stringify(c.figures));
  assert.match(c.source, /2024-25, DfE CFR return/);
  assert.match(c.source, /2024-25, DfE AAR return/);
});

test("the nearby card names its year, the different intakes and the mixed council-run and academy years", () => {
  // Arrange
  const contract = nearbyContract();
  // Act
  const all = card(nearbyModel(contract), "nearby").lines.join(" ");
  const councilOnly = nearbyModel(nearbyContract(), "school", (f) => f.s.nearby.schools.forEach((r) => delete r.academy));
  // Assert
  assert.match(all, /In 2024-25 this school spent/);
  assert.match(all, /different intakes: 13\.4% of pupils here are eligible for free school meals, against 15% to 40\.1%/);
  assert.match(all, /Council-run years run April-March and academy years September-August/);
  assert.match(all, /These are 2024-25 figures.*this school's latest is 2025-26/, "two years shown together are each labelled");
  assert.match(all, /this one included, all within 0\.9 miles/);
  assert.doesNotMatch(card(councilOnly, "nearby").lines.join(" "), /April-March/);
});

test("without the nearby contract the school story is unchanged", () => {
  for (const nearby of [undefined, null, {}, { year: "2024-25", schools: [] }]) {
    // Act
    const m = nearbyModel(nearby);
    // Assert
    assert.deepEqual(m.cards.map((c) => c.id), ["intro", "pupils", "funding", "staff", "reserve", "similar", "council", "pta", "helps", "outro"], JSON.stringify(nearby));
  }
});

test("a malformed nearby contract never throws and never prints 0, NaN or a missing value", () => {
  // Arrange
  const broken = [
    "nearby", 7, [], { schools: "x" }, { year: 2024, schools: nearbyContract().schools },
    { year: "2024-25", schools: [null, 5, "x", { name: 7 }, { urn: "1" }] },
    { ...nearbyContract(), self: "x", rank: { spend_pp: { rank: "first", of: 2 } }, medians: { spend_pp: "abc" } },
    { ...nearbyContract(), rank: { spend_pp: { rank: 9, of: 8 } }, radius_mi: -1, phase: 12 },
    { ...nearbyContract(), schools: nearbyContract().schools.map((r) => ({ ...r, spend_pp: "lots", fsm_pct: 140, pta_pp: -5, mi: null, academy: "yes" })) },
    { ...nearbyContract(), self: { spend_pp: null }, rank: {} },
    { ...nearbyContract(), rank: {}, schools: nearbyContract().schools.map((r) => ({ ...r, spend_pp: 0 })) },
  ];
  for (const nearby of broken) {
    for (const mode of ["school", "ptfa"]) {
      // Act
      const m = nearbyModel(nearby, mode);
      const c = card(m, mode === "ptfa" ? "pta-gap" : "nearby");
      // Assert
      if (!c) continue;
      const text = textOf(c);
      assert.doesNotMatch(text, /NaN|undefined|null|£0\b|—/, JSON.stringify(nearby).slice(0, 80) + " -> " + text);
      for (const b of c.bars || []) assert.ok(typeof b.v === "number" && isFinite(b.v) && b.v > 0, JSON.stringify(b));
    }
  }
  const out = card(nearbyModel(broken[7]), "nearby");
  assert.equal(out.big, null, "an impossible rank is dropped, the bars stay");
  assert.equal(out.bars.length, 5);
  const rankOnly = card(nearbyModel(broken[8]), "nearby");
  assert.equal(rankOnly.big.text, "4th of 8", "the build's rank stands when neighbour rows are unreadable");
  assert.equal(rankOnly.bars, undefined);
  assert.equal(card(nearbyModel(broken[10]), "nearby"), undefined, "no neighbour figures and no rank: no card");
  assert.equal(card(nearbyModel(broken[9]), "nearby"), undefined, "no figure for this school and no rank: no card");
});

test("with no rank the nearby card shows only the bars; with one neighbour it still compares", () => {
  // Arrange
  const noRank = { ...nearbyContract(), rank: {} };
  const one = { ...nearbyContract(), rank: {}, schools: nearbyContract().schools.slice(0, 1) };
  // Act
  const a = card(nearbyModel(noRank), "nearby"), b = card(nearbyModel(one), "nearby");
  // Assert
  assert.equal(a.big, null);
  assert.equal(a.bars.length, 5);
  assert.doesNotMatch(a.lines.join(" "), /highest|lowest/);
  assert.deepEqual(b.bars.map((x) => x.label), ["This school", "Elm Lane"]);
  assert.match(b.barsNote, /this school and the nearest with figures/);
});

test("PTFA mode shows at most 3 nearby PTA bars, nearest first, and only from the card's year", () => {
  // Arrange
  const contract = nearbyContract();
  const want = contract.schools.filter((r) => r.pta_year === "2024-25").slice(0, 3);
  // Act
  const c = card(nearbyModel(contract, "ptfa"), "pta-gap");
  const near = c.bars.filter((b) => / PTA$/.test(b.label) && !/middle/.test(b.label));
  // Assert
  assert.deepEqual(near.map((b) => b.label), ["Elm Lane PTA", "Birch Road PTA", "St Anne's PTA"]);
  assert.deepEqual(near.map((b) => b.v), want.map((r) => r.pta_pp));
  assert.ok(!near.some((b) => b.label.startsWith("Oak Hill")), "a 2023-24 PTA is not set beside 2024-25 figures");
  assert.ok(c.bars[0].mine && c.bars[0].label === "This PTFA");
  assert.equal(c.bars[0].v, Math.round(gold.ptfa.years["2024-25"].income / pupilsOf("2024-25")));
  assert.equal(c.bars[c.bars.length - 1].label, "England's middle PTA");
  assert.match(c.barsNote, /2024-25/);
  assert.match(c.lines.join(" "), /different intakes/);
  assert.match(c.lines.join(" "), /not in the IFS report/);
  assert.ok(c.figures.filter((f) => f.key === "nearby_pta_pp").every((f) => f.year === "2024-25" && f.source === "Charity Commission register"));
  assert.ok(!c.figures.some((f) => /donation/i.test(f.key)), "PTA income is never added to school donations");
});

test("PTFA mode without England figures sets nearby PTAs beside this PTFA's own latest year", () => {
  // Arrange
  const contract = nearbyContract();
  contract.schools[0].pta_confidence = "medium";
  // Act
  const c = card(nearbyModel(contract, "ptfa", (f) => { f.england = null; }), "pta-gap");
  const without = card(nearbyModel(undefined, "ptfa", (f) => { f.england = null; }), "pta-gap");
  // Assert
  assert.equal(without, undefined, "no England figures and no contract: no card, as before");
  assert.deepEqual(c.bars.map((b) => b.label), ["This PTFA", "Elm Lane PTA", "Birch Road PTA", "St Anne's PTA"]);
  assert.equal(c.big.text, MW.fmtExact(c.bars[0].v));
  assert.match(c.big.unit, /year to Aug 2025/);
  assert.match(c.lines.join(" "), /Elm Lane PTA was matched with lower confidence/);
});

test("PTFA mode treats undated England PTA figures as missing and uses this PTFA's own latest year", () => {
  // Arrange
  const contract = nearbyContract();
  const undated = { id: "england", type: "england", name: "England", pta: { bands: { 1: 96, 5: 6 } } };
  // Act
  const c = card(nearbyModel(contract, "ptfa", (f) => { f.england = undated; }), "pta-gap");
  const without = card(nearbyModel(undefined, "ptfa", (f) => { f.england = undated; }), "pta-gap");
  // Assert
  assert.equal(without, undefined, "undated England figures and no contract: no card, never 'in null'");
  assert.deepEqual(c.bars.map((b) => b.label), ["This PTFA", "Elm Lane PTA", "Birch Road PTA", "St Anne's PTA"]);
  assert.match(c.barsNote, /2024-25/);
  assert.match(c.big.unit, /year to Aug 2025/);
  assert.ok(!c.figures.some((f) => /^pta_band|^pta_pp_median$/.test(f.key)), "undated England figures are left out");
  assert.doesNotMatch(textOf(c), /\bnull\b|\bundefined\b|NaN/);
});

test("PTFA mode keeps the council's same-year PTA comparison when England's figures are missing", () => {
  // Arrange: Hackney publishes a 2024-25 median; England's file did not load and there are no nearby PTAs.
  const f = fixture();
  f.council.by_year["2024-25"] = { all: { schools: 60, pta_schools: 12, pta_pp_median: 62.46 } };
  // Act
  const m = MW.buildCards(MW.adapt(f.s, f.sx, f.council, null, CTX), "ptfa");
  const c = card(m, "pta-gap");
  // Assert
  assert.ok(c, "the council's median is a comparison on its own");
  assert.equal(c.big.v, card(m, "pta-money").big.v);
  assert.match(c.lines[0], /^Year to Aug 2025: this PTFA raised £111 per pupil, about double Hackney's typical PTA \(£62\)\.$/);
  assert.deepEqual(c.bars.map((b) => b.label), ["This PTFA", "Hackney's middle PTA"]);
  assert.doesNotMatch(textOf(c), /\bnull\b|\bundefined\b|NaN/);
});

test("PTFA mode with no per-pupil figure of its own shows the council's same-year median, with its year", () => {
  // Arrange: no pupil count for 2024-25, so this PTFA has a total but no per-pupil figure; England did not load.
  const f = fixture();
  f.council.by_year["2024-25"] = { all: { schools: 60, pta_schools: 12, pta_pp_median: 62.46 } };
  delete f.sx.pupils["2024-25"];
  f.s.years.find((r) => r.y === "2024-25").pupils = null;
  f.sx.pta["2024-25"].income_pp = null;
  // Act
  const c = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, null, CTX), "ptfa"), "pta-gap");
  // Assert
  assert.deepEqual(c.big, { v: 62.46, text: "£62", fmt: "exact", unit: "per pupil, Hackney's typical PTA" });
  assert.ok(c.lines.includes("The middle registered parents' association in Hackney raised £62 per pupil in the year to Aug 2025."), c.lines.join("\n"));
  assert.doesNotMatch(textOf(c), /\bnull\b|\bundefined\b|NaN|nearby/i);
});

test("with no sx.pta, two returns ending in one school year are added together and a repeated return counts once", () => {
  // Arrange: the register history alone; the association moved its year end from March to August 2025.
  const f = fixture();
  f.sx.pta = {};
  f.s.pta[0].history = [{ period_end: "2025-03-31", income: 10000, expenditure: 9000 }, { period_end: "2025-08-31", income: 20000, expenditure: 18000 },
    { period_end: "2025-08-31", income: 20000, expenditure: 18000 }, { period_end: "2024-08-31", income: 32743, expenditure: 36767 }];
  // Act
  const d = MW.adapt(f.s, f.sx, f.council, f.england, CTX);
  // Assert: as series._pta counts it, one row per school year.
  assert.deepEqual(d.pta.years.map((r) => [r.y, r.income, r.spend]), [["2023-24", 32743, 36767], ["2024-25", 30000, 27000]]);
  assert.equal(d.pta.latest.pp, Math.round(30000 / pupilsOf("2024-25")));
});

test("PTFA mode keeps to 3 nearby PTAs when more share the year", () => {
  // Arrange
  const contract = nearbyContract();
  contract.schools.forEach((r, i) => { r.pta_pp = 10 + i; r.pta_year = "2024-25"; });
  // Act
  const c = card(nearbyModel(contract, "ptfa"), "pta-gap");
  // Assert
  assert.deepEqual(c.bars.filter((b) => !b.mine && !/middle/.test(b.label)).map((b) => b.v), [10, 11, 12]);
});

test("every card theme, the new nearby one included, keeps ink, sub and big at 4.5:1 or more on its background", () => {
  // Arrange: WCAG 2 relative luminance and contrast ratio
  const lum = (hex) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const nearbyTheme = MW.CARD_THEME.nearby;
  // Act / Assert
  assert.ok(MW.THEMES[nearbyTheme], "nearby has a theme");
  const others = Object.entries(MW.CARD_THEME).filter(([id]) => id !== "nearby").map(([, t]) => t);
  assert.ok(!others.includes(nearbyTheme), "the nearby theme is new, not shared with another card");
  for (const [name, th] of Object.entries(MW.THEMES)) {
    for (const k of ["ink", "sub", "big"]) assert.ok(ratio(th[k], th.bg) >= 4.5, `${name}.${k} ${ratio(th[k], th.bg).toFixed(2)}:1`);
  }
  assert.ok(["#FFFFFF", "#1D1A10"].includes(MW.THEMES[nearbyTheme].ink));
});

test("the nearby cards draw inside the margins without cutting a line", () => {
  // Arrange
  const school = nearbyModel(nearbyContract()), ptfa = nearbyModel(nearbyContract(), "ptfa");
  for (const [m, id] of [[school, "nearby"], [ptfa, "pta-gap"]]) {
    const c = card(m, id), f = fakeCanvas();
    // Act
    MW.drawCard(f.g, c, 1, PALETTE, { index: m.cards.indexOf(c), count: m.cards.length });
    // Assert
    const texts = f.calls.filter((x) => x.op === "fillText");
    assert.ok(!texts.some((x) => x.t.endsWith("…")), `${id}: ${texts.filter((x) => x.t.endsWith("…")).map((x) => x.t).join(" | ")}`);
    for (const x of texts.filter((y) => y.align === "left")) assert.ok(x.x >= 90 && x.x + x.width <= 1080 - 90 + 1, `${id} "${x.t}" overflows`);
    assert.ok(texts.some((x) => x.t === "This school" || x.t === "This PTFA"), id);
  }
});

test("no banned words in the nearby cards in either mode", () => {
  // Arrange
  const variants = [nearbyContract(), { ...nearbyContract(), rank: { spend_pp: { rank: 1, of: 8 } } }, { ...nearbyContract(), rank: { spend_pp: { rank: 8, of: 8 } } }];
  // Act
  const all = variants.flatMap((v) => [nearbyModel(v), nearbyModel(v, "ptfa")]).flatMap((m) => strings(m));
  // Assert
  for (const text of all) for (const word of BANNED) assert.ok(!text.toLowerCase().includes(word.toLowerCase()), `"${word}" in: ${text.slice(0, 120)}`);
  assert.ok(all.some((t) => t.includes("the highest of 8")) && all.some((t) => t.includes("the lowest of 8")));
});

test("short school names drop the phase and type words but never empty a name", () => {
  // Arrange
  const names = { "ST JOHN AND ST JAMES C OF E PRIMARY SCHOOL": "St John and St James", "Hackney Free and Parochial Church of England School (Secondary)": "Hackney Free and Parochial",
    "The Academy": "The Academy", "Clapton Girls' Academy": "Clapton Girls'", "Mossbourne Community Academy": "Mossbourne" };
  for (const [name, want] of Object.entries(names)) {
    // Act
    const contract = { ...nearbyContract(), schools: [{ urn: "1", name, mi: 0.1, spend_pp: 9000 }] };
    const c = card(nearbyModel(contract), "nearby");
    // Assert
    assert.equal(c.bars[1].label, want);
  }
});

// ---------------------------------------------------------------- fix wave 1: comparisons in words, years, bases, links
const PHRASING = JSON.parse(readFileSync(process.env.PHRASING_CASES || join(here, "data", "phrasing_cases.json"), "utf8"));
const CC_LINK = "https://register-of-charities.charitycommission.gov.uk/charity-search?p_p_id=uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet" +
  "&p_p_lifecycle=0&p_p_state=maximized&p_p_mode=view&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_regId=1103834" +
  "&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_subId=0";
// Every line of a card is drawn in full: no ellipsis, and each line's closing words appear (a URL may wrap mid-word).
function assertFits(c, label) {
  const f = fakeCanvas();
  MW.drawCard(f.g, c, 1, PALETTE, { index: 0, count: 10, reducedMotion: true });
  const texts = f.calls.filter((x) => x.op === "fillText").map((x) => x.t);
  const drawn = texts.join(" ");
  assert.ok(!texts.some((t) => t.endsWith("…")), `${label}: cut ${texts.filter((t) => t.endsWith("…")).join(" | ")}`);
  for (const l of c.lines) if (!/https?:/.test(l)) assert.ok(drawn.includes(l.split(" ").slice(-2).join(" ")), `${label}: not drawn: ${l}`);
}
// Hackney's PTA medians from the live council file: 2024-25 is the PTFA's latest school year.
function withCouncilPta(f, years = { "2024-25": 62.46205357142857, "2023-24": 59.738435453138855 }) {
  for (const [y, v] of Object.entries(years)) (f.council.by_year[y] ||= { all: {} }).all = { ...(f.council.by_year[y].all || {}), schools: 60, pta_pp_median: v, pta_schools: 12 };
  return f;
}

test("ratioWords matches the shared phrasing table (contract C1)", () => {
  // Arrange
  assert.ok(PHRASING.length >= 30);
  for (const c of PHRASING) {
    // Act / Assert
    assert.equal(MW.ratioWords(c.a, c.b), c.words, JSON.stringify(c));
  }
  for (const bad of ["100", true, NaN, Infinity, [100], {}]) assert.equal(MW.ratioWords(bad, 100), null, String(bad));
});

test("charityUrl puts the number mid-URL and the PTFA card links the register (contract C9)", () => {
  // Act
  const c = card(model({}, "ptfa").m, "pta-money");
  // Assert
  assert.equal(MW.charityUrl(1103834), CC_LINK);
  assert.equal(MW.charityUrl(undefined), "https://register-of-charities.charitycommission.gov.uk/");
  assert.equal(c.link, CC_LINK);
  assert.equal(c.linkText, "Charity 1103834 on the Charity Commission register");
});

test("the PTFA comparison card headlines this PTFA's own per pupil, in the money card's year, with the ratio in words", () => {
  // Arrange: the PTFA money card's year is the latest return, 2024-25 (the year to Aug 2025).
  const f = withCouncilPta(fixture());
  // Act
  const m = MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "ptfa");
  const money = card(m, "pta-money"), gap = card(m, "pta-gap");
  // Assert
  const want = Math.round(gold.ptfa.years["2024-25"].income / pupilsOf("2024-25"));
  assert.equal(money.big.v, want);
  assert.deepEqual([gap.big.v, gap.big.text, gap.big.unit], [want, MW.fmtExact(want), "raised per pupil, year to Aug 2025"], "this PTFA's figure, not England's");
  assert.equal(gap.lines[0], "Year to Aug 2025: this PTFA raised " + MW.fmtExact(want) + " per pupil, " + MW.ratioWords(want, 62.46205357142857) +
    " Hackney's typical PTA (£62) and " + MW.ratioWords(want, 31) + " England's (£31).");
  assert.ok(gap.bars.some((b) => b.label === "Hackney's middle PTA" && b.v === 62.46205357142857));
  assert.match(gap.barsNote, /year to Aug 2025 \(2024-25\)/);
  assert.ok(money.lines[0].startsWith("Year to Aug 2025: " + MW.fmtExact(gold.ptfa.years["2024-25"].income) + " raised"), money.lines[0]);
  assert.match(money.source, /^year to Aug 2025, Charity Commission register/);
  assertFits(gap, "pta-gap");
});

test("a council PTA median for another year is never set beside this PTFA's year", () => {
  // Arrange: Hackney has a median only for 2023-24.
  const f = withCouncilPta(fixture(), { "2023-24": 59.7 });
  // Act
  const gap = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "ptfa"), "pta-gap");
  // Assert
  assert.ok(!gap.bars.some((b) => /Hackney/.test(b.label)));
  assert.doesNotMatch(gap.lines.join(" "), /Hackney's typical PTA/);
  assert.match(gap.lines[0], /^Year to Aug 2025: this PTFA raised £\d+ per pupil, .+ England's typical PTA \(£31\)\.$/);
});

test("a PTFA matched with lower confidence says so", () => {
  // Arrange
  const f = fixture();
  f.s.pta[0].match = { method: "llm" };
  // Act
  const c = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "ptfa"), "pta-money");
  // Assert
  assert.ok(c.lines.some((l) => l.includes("matched with lower confidence")));
  assert.ok(!card(model({}, "ptfa").m, "pta-money").lines.some((l) => l.includes("lower confidence")));
});

test("the similar-schools card is School Money's, with its count and year from similar_meta (contract C2)", () => {
  // Arrange
  const f = fixture();
  f.s.similar_meta = { year: LATEST, peers: 17, method: "Same phase, similar size and intake." };
  // Act
  const withMeta = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "school"), "similar");
  const without = card(model().m, "similar");
  // Assert
  assert.equal(withMeta.barsNote, "School Money's similar schools (17 schools, " + LATEST + "): the closest in phase, size and free school meals.");
  assert.match(without.barsNote, /^Per pupil in .+\. School Money's similar schools: /);
  for (const c of [withMeta, without]) {
    assert.ok(!textOf(c).includes("DfE similar"), "never the DfE's comparison");
    assert.ok(c.figures.filter((x) => /^similar_/.test(x.key)).every((x) => x.source === "School Money's similar schools"));
    const spend = c.lines.find((l) => l.startsWith("Spending:"));
    const mine = Math.round(pf(LATEST).total_expenditure / pf(LATEST).pupils);
    assert.equal(spend, "Spending: " + MW.fmtExact(mine) + " per pupil, " + MW.ratioWords(mine, 8650) + " the middle of similar schools (£8,650).");
    assertFits(c, "similar");
  }
});

test("the nearby and council cards say the comparison in words", () => {
  // Arrange
  const f = fixture();
  f.council.by_year[LATEST].all.spend_pp_median = 7900;
  // Act
  const nb = card(nearbyModel(nearbyContract()), "nearby");
  const council = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "school"), "council");
  // Assert
  const c = nearbyContract(), words = MW.ratioWords(c.self.spend_pp, c.medians.spend_pp);
  assert.ok(nb.lines[0].endsWith("That is " + words + " the middle value, " + MW.fmtExact(c.medians.spend_pp) + "."), nb.lines[0]);
  const mine = Math.round(pf(LATEST).total_expenditure / pf(LATEST).pupils);
  assert.ok(council.lines.includes("This school spent " + MW.ratioWords(mine, 7900) + " Hackney's middle school per pupil in " + LATEST + "."), council.lines.join("\n"));
  assert.match(council.barsNote, /mix primary and secondary/);
  assertFits(nb, "nearby");
  assertFits(council, "council");
});

test("deficit cards add one calm line: schools in deficit keep running while a plan brings the budget back", () => {
  // Act
  const { m } = model();
  const reserve = card(m, "reserve"), council = card(m, "council");
  // Assert
  assert.ok(reserve.lines.includes("Schools in deficit keep running: the council agrees a plan to bring the budget back into balance."), reserve.lines.join("\n"));
  assert.ok(council.lines.includes("Schools in deficit keep running: the council or trust agrees a plan to bring the budget back into balance."));
  assertFits(reserve, "reserve");
  assertFits(council, "council");
  // A healthy school's reserve card has no deficit line.
  const f = fixture();
  for (const y of YEARS) f.sx.m.revenue_reserve[y] = { v: 300000, pp: 300000 / pupilsOf(y) };
  f.s.status = "healthy";
  const healthy = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "school"), "reserve");
  assert.ok(!healthy.lines.some((l) => /keep running/.test(l)));
});

test("the council card names the DSG measure with its year, denominator and provisional status (contract C8)", () => {
  // Arrange
  const f = fixture();
  f.council.dsg[LATEST].provisional = true;
  // Act
  const c = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "school"), "council");
  // Assert
  assert.ok(c.lines.includes("Council's Dedicated Schools Grant balance (all four blocks), " + LATEST + " (provisional): -£21.5m (-£640 per pupil at its schools on this site)."), c.lines.join("\n"));
  assert.equal(c.figures.find((x) => x.key === "dsg_balance").label, "Dedicated Schools Grant balance (all four blocks)");
  assert.doesNotMatch(textOf(c), /high needs \(Dedicated Schools Grant\) balance|High needs balance/);
});

test("reserve_basis labels the reserve the series shows; without it the card reads as before (contract C3)", () => {
  // Arrange
  const f = fixture();
  f.s.academy = true; f.s.tags.governance = "academy"; f.s.trust = "Example Learning Trust";
  f.sx.reserve_basis = "incl_trust_share";
  // Act
  const c = card(MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "school"), "reserve");
  const plain = card(model().m, "reserve");
  // Assert
  assert.ok(c.lines[0].startsWith("Reserve at the end of " + LATEST + ", including its share of the trust's reserve: "), c.lines[0]);
  assert.equal(c.big.unit, "reserve, including its share of the trust's");
  assert.equal(c.figures[0].v, pf(LATEST).revenue_reserve, "the series figure, as /data/sx gives it");
  assert.ok(c.lines.includes("Schools in deficit keep running: Example Learning Trust agrees a plan to bring the budget back into balance."));
  assert.ok(plain.lines[0].startsWith("Reserve at the end of " + LATEST + ": "));
  assert.equal(plain.big.unit, "reserve");
});

test("reserve held by the trust: its own grey badge and a supportive story, never 'Tight' or a deficit (contract C4)", () => {
  // Arrange: an academy in a pooling trust, own reserve £0 every year.
  const f = fixture();
  Object.assign(f.s, { academy: true, trust: "Example Learning Trust", status: "reserve_held_by_trust", label: "Reserve held by the trust", reason: "" });
  f.s.tags.governance = "academy";
  for (const y of YEARS) f.sx.m.revenue_reserve[y] = { v: 0, pp: 0 };
  // Act
  const m = MW.buildCards(MW.adapt(f.s, f.sx, f.council, f.england, CTX), "school");
  const reserve = card(m, "reserve");
  // Assert
  assert.deepEqual(MW.STATUS.reserve_held_by_trust, { label: "Reserve held by the trust", icon: "◇", colour: "held", fallback: "#6b7280" });
  assert.ok(MW.PALETTE_KEYS.includes("held"));
  assert.equal(reserve.status.key, "reserve_held_by_trust");
  assert.ok(reserve.lines.some((l) => l.startsWith("Example Learning Trust keeps the reserves of all its academies together") && l.includes("not a shortfall")));
  assert.ok(!reserve.lines.some((l) => /keep running|recovery plan/.test(l)));
  for (const c of m.cards) assert.doesNotMatch(textOf(c), /\bTight\b/, c.id);
  const helps = card(m, "helps");
  // wrapped.context_doc() carries the held story (the pytest wrapper passes it in); without it the healthy wording stands.
  const held = (CTX.what_helps || {}).reserve_held_by_trust;
  if (held) assert.equal(helps.lines[0], held.text);
  assert.doesNotMatch(helps.lines[0], /recovery|deficit/);
  // The badge outline is the neutral grey when the palette has no --held.
  const fc = fakeCanvas();
  const strokes = [];
  const g = new Proxy(fc.g, { set: (o, k, v) => { if (k === "strokeStyle") strokes.push(v); o[k] = v; return true; } });
  MW.drawCard(g, reserve, 1, {}, { index: 4, count: m.cards.length });
  assert.ok(strokes.includes("#6b7280"), strokes.join(","));
  assertFits(reserve, "held reserve");
});

test("only genuine per-year entries in sx.flags.suspect mark a year (the series shape)", () => {
  for (const [flags, marked] of [
    [{ falling_rolls: null, pass_through: null, high_send: { ehcp_pct: 5.5 }, suspect: {}, not_reported: {} }, []],
    [{ falling_rolls: null, suspect: { "2024-25": ["pupils"] }, not_reported: {} }, ["2024-25"]],
    [{ suspect: { "2023-24": [], "2022-23": ["total_income"] } }, ["2022-23"]],
    [{ "2023-24": [] }, []],
  ]) {
    // Arrange
    const f = fixture();
    f.sx.flags = flags;
    // Act
    const data = MW.adapt(f.s, f.sx, f.council, f.england, CTX);
    // Assert
    assert.deepEqual(data.years.filter((r) => r.suspect).map((r) => r.y), marked, JSON.stringify(flags));
  }
});

test("with reserve_basis, a year the series leaves out has no reserve rather than another basis's figure (contract C3)", () => {
  // Arrange: the trust-share basis has no figure for 2024-25, which /data/s still carries.
  const f = fixture();
  f.sx.reserve_basis = "incl_trust_share";
  delete f.sx.m.revenue_reserve["2024-25"];
  // Act
  const data = MW.adapt(f.s, f.sx, f.council, f.england, CTX);
  const without = MW.adapt(f.s, { ...f.sx, reserve_basis: undefined }, f.council, f.england, CTX);
  // Assert
  assert.equal(data.years.find((r) => r.y === "2024-25").reserve, null);
  assert.equal(without.years.find((r) => r.y === "2024-25").reserve, pf("2024-25").revenue_reserve, "today's fallback without reserve_basis");
});

test("federation years: the PTFA cards never divide by the whole federation's pupils", () => {
  // Arrange: a federation lead school whose every return covers the whole federation (series.federation_years)
  const flags = { suspect: {}, federation_years: YEARS };
  // Act
  const school = model({ flags }).m, ptfa = model({ flags }, "ptfa").m;
  // Assert: PTA totals stay, with no per-pupil figure beside them
  for (const m of [school, ptfa]) {
    // This association's own figures (England's and band medians are per pupil by definition).
    const figures = m.cards.flatMap((c) => c.figures || []).filter((f) => ["pta_income", "pta_spend", "pta_line"].includes(f.key));
    assert.ok(figures.length > 0);
    for (const f of figures) assert.equal(f.pp == null, true, f.key + " " + f.year + " pp " + f.pp);
  }
  assert.equal(card(school, "pta").figures.find((f) => f.key === "pta_income").v, 48547);
});
