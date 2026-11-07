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
  assert.match(m.share.url, /\/school\/130932-william-patten-primary-school\/wrapped\/\?mode=ptfa$/);
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
  const url = "https://money.schoolsinreach.com/school/1-a/wrapped/?mode=ptfa", text = "A & B's year: £8,297 per pupil";
  // Act
  const L = MW.shareLinks(url, text);
  // Assert
  assert.equal(L.whatsapp, "https://wa.me/?text=" + encodeURIComponent(text + " " + url));
  assert.equal(L.x, "https://twitter.com/intent/tweet?text=" + encodeURIComponent(text) + "&url=" + encodeURIComponent(url));
  assert.equal(L.facebook, "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(url));
  assert.match(L.email, /^mailto:\?subject=School%20Wrapped&body=/);
  for (const v of Object.values(L)) assert.doesNotMatch(v.split("?").slice(1).join("?"), /[ &]B|£/);
});

test("shareVideo uses native file sharing when canShare, else the fallback", async () => {
  // Arrange
  const file = { name: "x.mp4", type: "video/mp4" }, share = { title: "T", text: "Plain words", url: "https://money.schoolsinreach.com/school/1-a/wrapped/" };
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
