// Pure-helper tests for assets/tools.js (MoneyTools) under node: no DOM, no network (fetch is stubbed).
// Run: node --test pipeline/money/test_tools_js.mjs. test_tools_js.py runs it with MONEY_STATUS_CASES set to a
// JSON file of {cases, expected} worked out by status.py, so the port is checked against the Python.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// Arrange (shared): localStorage and fetch stubs before the scripts run.
const memory = new Map();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: { getItem: (k) => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, String(v)), removeItem: (k) => memory.delete(k) },
});
const requested = [];
let routes = {};
globalThis.fetch = (url) => {
  requested.push(String(url));
  const body = routes[url];
  if (body === undefined) return Promise.resolve({ ok: false, status: 404, json: () => Promise.reject(new Error("404")) });
  if (body === "not json") return Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new SyntaxError("Unexpected token")) });
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(body))) });
};
const here = dirname(fileURLToPath(import.meta.url));
await import(pathToFileURL(join(here, "assets", "app.js")).href);
await import(pathToFileURL(join(here, "assets", "tools.js")).href);
const T = globalThis.MoneyTools;

// Fixtures built from the committed reference school (William Patten Primary, URN 130932).
const gold = JSON.parse(readFileSync(join(here, "data", "gold", "130932.json"), "utf8"));
const ifs = JSON.parse(readFileSync(join(here, "data", "ifs_context.json"), "utf8"));
const YEARS = Object.keys(gold.years).sort();
const fin = (y) => gold.years[y].totals.pipeline_finance_history;
const LATEST = YEARS[YEARS.length - 1];
const METRICS = ["total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "grant_funding"];
function makeSx(flags) {
  const m = {};
  for (const k of METRICS) {
    m[k] = {};
    for (const y of YEARS) m[k][y] = { v: fin(y)[k], pp: fin(y)[k] / fin(y).pupils };
  }
  return { years: YEARS, source: "CFR", pupils: Object.fromEntries(YEARS.map((y) => [y, fin(y).pupils])), m, flags: flags || [] };
}
const ptaHistory = Object.entries(gold.ptfa.years).map(([, v]) => ({ period_end: v.period.split(" to ")[1], income: v.income, expenditure: v.expenditure }));
const S = {
  urn: "130932", name: gold.name, path: "/school/130932-william-patten-primary-school/", council: { code: "204", name: "Hackney", path: "/council/hackney/" },
  status: "in_deficit", label: "In deficit", academy: false, pupils: fin(LATEST).pupils, band: 3,
  years: YEARS.map((y) => ({ y, income: fin(y).total_income, spend: fin(y).total_expenditure, balance: fin(y).in_year_balance, reserve: fin(y).revenue_reserve, pupils: fin(y).pupils })),
  pta: [{ charity_number: gold.ptfa.charity_number, name: gold.ptfa.name, status: "Registered", latest_income: gold.ptfa.latest.income, history: ptaHistory }],
};
const COUNCIL = { id: "council-204", type: "council", name: "Hackney", path: "/council/hackney/",
  by_year: { "2023-24": { all: { schools: 60, pta_pp_median: 21 } }, "2024-25": { all: { schools: 58, pta_pp_median: 24.5, pta_schools: 30 } }, "2025-26": { all: { schools: 57, pta_pp_median: null } } } };
const CTX = { ifs: { cite: ifs.source.short_cite, url: ifs.source.url, framings: Object.fromEntries(Object.entries(ifs.framings).map(([k, f]) => [k, { title: f.title, text: f.text, pages: "pp. " + f.pages.join(", ") }])) } };

// Every string a model produces, for the banned-words check.
const outputs = [];
function keep(value) { outputs.push(value); return value; }
function strings(value, out = []) {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => strings(v, out));
  else if (value && typeof value === "object") Object.values(value).forEach((v) => strings(v, out));
  return out;
}

test("status parity with status.py for every generated case", { skip: !process.env.MONEY_STATUS_CASES && "MONEY_STATUS_CASES not set" }, () => {
  // Arrange
  const { cases, expected } = JSON.parse(readFileSync(process.env.MONEY_STATUS_CASES, "utf8"));
  assert.equal(cases.length, 50);
  cases.forEach((c, i) => {
    // Act
    const got = keep(T.assess(c.rows, c.basis)), want = expected[i];
    // Assert
    if (want === null) { assert.equal(got, null, c.name); return; }
    for (const k of ["status", "label", "rank", "deficit_streak", "reason", "year", "source", "reserve", "years", "trust_share_included", "reserve_basis"]) {
      assert.equal(got[k], want[k], c.name + ": " + k);
    }
    for (const k of ["reserve_share", "runway_years", "pupils_change"]) {
      if (want[k] === null) assert.equal(got[k], null, c.name + ": " + k);
      else assert.ok(Math.abs(got[k] - want[k]) < 1e-9, c.name + ": " + k + " " + got[k] + " vs " + want[k]);
    }
  });
});

// The live shapes builders emit, copied from the built site's /data/sx/130932.json and /data/s/130932.json (William
// Patten, 4 metrics kept): sx.source is a per-year map and sx.flags holds named flags beside flags.suspect.
const LIVE_SX = {"years": ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"], "source": {"2018-19": "CFR", "2019-20": "CFR", "2020-21": "CFR", "2021-22": "CFR", "2022-23": "CFR", "2023-24": "CFR", "2024-25": "CFR", "2025-26": "CFR"}, "pupils": {"2018-19": 435.0, "2019-20": 443.0, "2020-21": 430.5, "2021-22": 429.0, "2022-23": 432.0, "2023-24": 427.5, "2024-25": 437.5, "2025-26": 432.5}, "m": {"total_income": {"2018-19": {"v": 3035769, "pp": 6979}, "2019-20": {"v": 3025090, "pp": 6829}, "2020-21": {"v": 2971071, "pp": 6901}, "2021-22": {"v": 3169383, "pp": 7388}, "2022-23": {"v": 3270918, "pp": 7572}, "2023-24": {"v": 3548990, "pp": 8302}, "2024-25": {"v": 3861666, "pp": 8827}, "2025-26": {"v": 3927968, "pp": 9082}}, "total_expenditure": {"2018-19": {"v": 2844921, "pp": 6540}, "2019-20": {"v": 2991578, "pp": 6753}, "2020-21": {"v": 3073370, "pp": 7139}, "2021-22": {"v": 3342036, "pp": 7790}, "2022-23": {"v": 3529501, "pp": 8170}, "2023-24": {"v": 3630857, "pp": 8493}, "2024-25": {"v": 3831287, "pp": 8757}, "2025-26": {"v": 4097753, "pp": 9475}}, "revenue_reserve": {"2018-19": {"v": 510395, "pp": 1173}, "2019-20": {"v": 543908, "pp": 1228}, "2020-21": {"v": 441609, "pp": 1026}, "2021-22": {"v": 268955, "pp": 627}, "2022-23": {"v": 10371, "pp": 24}, "2023-24": {"v": -71496, "pp": -167}, "2024-25": {"v": -41117, "pp": -94}, "2025-26": {"v": -210901, "pp": -488}}, "in_year_balance": {"2018-19": {"v": 190848, "pp": 439}, "2019-20": {"v": 33512, "pp": 76}, "2020-21": {"v": -102299, "pp": -238}, "2021-22": {"v": -172654, "pp": -402}, "2022-23": {"v": -258583, "pp": -599}, "2023-24": {"v": -81867, "pp": -192}, "2024-25": {"v": 30379, "pp": 69}, "2025-26": {"v": -169784, "pp": -393}}}, "flags": {"falling_rolls": null, "pass_through": null, "high_send": {"ehcp_pct": 5.5, "sen_share": 0.0652, "reason": "ehcp"}, "suspect": {}, "not_reported": {}}, "trust_central_pp": {}};
const LIVE_S = {"urn": "130932", "name": "William Patten Primary School", "path": "/school/130932-william-patten-primary-school/", "council": {"code": "204", "name": "Hackney", "path": "/council/hackney/"}, "status": "in_deficit", "label": "In deficit", "reason": "In deficit by £211k, 5% of a year's income: it has spent more over the years than it received.", "year": "2025-26", "academy": false, "trust": null, "pupils": 432.5, "tags": {"governance": "council-run", "trust": null, "trust_size": null, "admissions": null, "faith": null, "phase": "Primary", "gender": "Mixed", "sixth_form": false}, "band": 1, "years": [{"y": "2018-19", "income": 3035769, "spend": 2844921, "balance": 190848, "reserve": 510395, "pupils": 435, "status": "large_reserves"}, {"y": "2019-20", "income": 3025090, "spend": 2991578, "balance": 33512, "reserve": 543908, "pupils": 443, "status": "large_reserves"}, {"y": "2020-21", "income": 2971071, "spend": 3073370, "balance": -102299, "reserve": 441609, "pupils": 430.5, "status": "large_reserves"}, {"y": "2021-22", "income": 3169383, "spend": 3342036, "balance": -172654, "reserve": 268955, "pupils": 429, "status": "large_reserves"}, {"y": "2022-23", "income": 3270918, "spend": 3529501, "balance": -258583, "reserve": 10371, "pupils": 432, "status": "heading_for_deficit"}, {"y": "2023-24", "income": 3548990, "spend": 3630857, "balance": -81867, "reserve": -71496, "pupils": 427.5, "status": "in_deficit"}, {"y": "2024-25", "income": 3861666, "spend": 3831287, "balance": 30379, "reserve": -41117, "pupils": 437.5, "status": "in_deficit"}, {"y": "2025-26", "income": 3927968, "spend": 4097753, "balance": -169784, "reserve": -210901, "pupils": 432.5, "status": "in_deficit"}], "pta": [{"charity_number": 1103834, "name": "WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION", "status": "Registered", "latest_income": 48547.0, "history": [{"period_end": "2025-08", "income": 48547.0, "expenditure": 50100.0}, {"period_end": "2024-08", "income": 32743.0, "expenditure": 36767.0}, {"period_end": "2023-08", "income": 32339.0, "expenditure": 23683.0}, {"period_end": "2022-08", "income": 15951.0, "expenditure": 9339.0}, {"period_end": "2021-08", "income": 12602.0, "expenditure": 21451.0}]}]};
const CHARITY_1103834 = "https://register-of-charities.charitycommission.gov.uk/charity-search?p_p_id=uk_gov_ccew_onereg_charitydetails_web_portlet_" +
  "CharityDetailsPortlet&p_p_lifecycle=0&p_p_state=maximized&p_p_mode=view&_uk_gov_ccew_onereg_charitydetails_web_portlet_" +
  "CharityDetailsPortlet_regId=1103834&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_subId=0";

test("live sx shape: the source is read per year and named flags are not years", () => {
  // Arrange
  const sx = JSON.parse(JSON.stringify(LIVE_SX)), s = JSON.parse(JSON.stringify(LIVE_S));
  // Act
  const p = T.prefillFrom(sx, s);
  // Assert
  assert.equal(p.source, "CFR");
  assert.ok(!/object/i.test(String(p.source)));
  assert.deepEqual(p.flagged, []);
  assert.equal(p.rows.length, 8);
  assert.ok(p.rows.every((r) => r.source === "CFR" && r.period_end.endsWith("-03-31")));
  assert.equal(T.assess(p.rows).status, "in_deficit");
  assert.equal(T.assess(p.rows).reserve, -210901);
  assert.equal(p.reserveBasis, "own");
});

test("live sx shape: only genuine per-year suspect entries are flagged", () => {
  // Arrange
  const sx = JSON.parse(JSON.stringify(LIVE_SX));
  sx.flags.suspect = { "2021-22": ["pupils"], "2022-23": [] };
  // Act
  const p = T.prefillFrom(sx, LIVE_S);
  // Assert
  assert.deepEqual(p.flagged, ["2021-22"]);
  assert.equal(p.rows.find((r) => r.year === "2021-22").flagged, true);
  assert.deepEqual(T.flaggedYears({ falling_rolls: null, high_send: { reason: "ehcp" }, suspect: {}, not_reported: {} }), []);
});

test("an academy on the trust basis: one basis per year, the headline matches, pooled years are held by the trust", () => {
  // Arrange: Mossbourne-like sx as series.py writes it
  const years = ["2021-22", "2022-23", "2023-24", "2024-25"];
  const own = { "2021-22": 4237000, "2022-23": 0, "2023-24": 0, "2024-25": 0 };
  const sx = { years, source: Object.fromEntries(years.map((y) => [y, "AAR"])), pupils: Object.fromEntries(years.map((y) => [y, 1440])),
    reserve_basis: "incl_trust_share",
    m: { total_income: Object.fromEntries(years.map((y) => [y, { v: 14000000 }])),
      total_expenditure: Object.fromEntries(years.map((y) => [y, { v: 13500000 }])),
      in_year_balance: Object.fromEntries(years.map((y) => [y, { v: 500000 }])),
      revenue_reserve: { "2024-25": { v: 3087254 } },
      revenue_reserve_own: Object.fromEntries(years.map((y) => [y, { v: own[y] }])) },
    flags: { suspect: {}, reserve_basis_missing: ["2021-22", "2022-23", "2023-24"], reserve_held_by_trust: ["2022-23", "2023-24", "2024-25"] } };
  const s = { urn: "134693", name: "Example Academy", academy: true, tags: { trust_size: "multi" }, years: [] };
  // Act
  const p = T.prefillFrom(sx, s);
  const last = p.rows[p.rows.length - 1];
  const before = T.assess(p.rows.slice(0, 3));
  // Assert
  assert.equal(p.reserveBasis, "incl_trust_share");
  assert.equal(last.revenue_reserve_incl_trust_share, 3087254);
  assert.equal(last.revenue_reserve, 0);
  assert.ok(p.rows.slice(0, 3).every((r) => !("revenue_reserve_incl_trust_share" in r)));
  assert.equal(T.assess(p.rows).reserve, 3087254);
  assert.equal(T.assess(p.rows).trust_share_included, true);
  assert.match(T.assess(p.rows).reason, /including its share of the trust's reserve/);
  assert.equal(before.status, "reserve_held_by_trust");
  assert.equal(T.projectRows(p.rows, [{ income: 14000000, spend: 14100000 }])[0].revenue_reserve_incl_trust_share, 2987254);
});

test("the new status has its label and icon, and charity links are built with charityUrl", () => {
  // Arrange / Act / Assert
  assert.equal(T.ORDER[T.ORDER.length - 1], "reserve_held_by_trust");
  assert.equal(T.LABELS.reserve_held_by_trust, "Reserve held by the trust");
  assert.equal(T.ICONS.reserve_held_by_trust, "◇");
  assert.equal(T.charityUrl(1103834), CHARITY_1103834);
  assert.equal(T.charityUrl(" 1103834 "), CHARITY_1103834);
  assert.equal(T.sourceOf({ "2024-25": "AAR" }, "2024-25", "CFR"), "AAR");
  assert.equal(T.sourceOf({ "2024-25": "AAR" }, "2023-24", "CFR"), "CFR");
  assert.equal(T.sourceOf("AAR", "2023-24", "CFR"), "AAR");
});


test("money and rounding follow Python's half-to-even formatting", () => {
  // Arrange / Act / Assert
  assert.equal(T.money(2500), "£2k");
  assert.equal(T.money(3500), "£4k");
  assert.equal(T.money(1_250_000), "£1.2m");
  assert.equal(T.money(1_750_000), "£1.8m");
  assert.equal(T.money(-210_901), "-£211k");
  assert.equal(T.money(500.5), "£500");
  assert.equal(T.pyFixed(0.05, 1), "0.1");
  assert.equal(T.pyFixed(-0.4, 0), "-0");
});

test("prefillFrom reads /data/sx and matches the reference school's file", () => {
  // Arrange
  const sx = makeSx();
  // Act
  const p = keep(T.prefillFrom(sx, S));
  const last = p.rows[p.rows.length - 1];
  // Assert
  assert.equal(p.rows.length, YEARS.length);
  assert.equal(last.year, LATEST);
  assert.equal(last.period_end, "2026-03-31");
  assert.equal(last.total_income, fin(LATEST).total_income);
  assert.equal(last.total_expenditure, fin(LATEST).total_expenditure);
  assert.equal(last.revenue_reserve, fin(LATEST).revenue_reserve);
  assert.equal(last.pupils, fin(LATEST).pupils);
  assert.equal(p.rows.find((r) => r.year === "2019-20").revenue_reserve, fin("2019-20").revenue_reserve);
  assert.equal(T.assess(p.rows).status, "in_deficit");
  assert.equal(T.assess(p.rows).reserve, fin(LATEST).revenue_reserve);
});

test("prefillFrom falls back to /data/s years when sx or a metric is missing", () => {
  // Arrange
  const partial = makeSx();
  delete partial.m.revenue_reserve;
  // Act
  const fromS = T.prefillFrom(null, S), mixed = T.prefillFrom(partial, S);
  // Assert
  assert.equal(fromS.rows.length, YEARS.length);
  assert.equal(fromS.rows[fromS.rows.length - 1].revenue_reserve, fin(LATEST).revenue_reserve);
  assert.equal(mixed.rows[mixed.rows.length - 1].revenue_reserve, fin(LATEST).revenue_reserve);
  assert.deepEqual(T.prefillFrom(null, null).rows, []);
});

test("flagged years are kept and marked, whatever shape flags take", () => {
  // Arrange
  const shapes = [["2021-22"], [{ year: "2021-22", code: "x", text: "odd" }], { "2021-22": ["odd"], "2022-23": [] }];
  for (const flags of shapes) {
    // Act
    const p = T.prefillFrom(makeSx(flags), S);
    // Assert
    assert.deepEqual(p.flagged, ["2021-22"]);
    assert.equal(p.rows.length, YEARS.length);
    assert.equal(p.rows.find((r) => r.year === "2021-22").flagged, true);
    assert.equal(p.rows.find((r) => r.year === "2022-23").flagged, undefined);
  }
});

test("projectRows adds 12-month years after the last full year", () => {
  // Arrange
  const history = T.prefillFrom(makeSx(), S).rows, last = fin(LATEST);
  // Act
  const rows = keep(T.projectRows(history, [
    { income: 4_000_000, spend: 3_950_000 }, { income: 4_050_000, spend: 4_000_000, reserve: 10_000 }, { income: 4_100_000, spend: 4_000_000 }, { income: 1, spend: 1 },
  ]));
  // Assert
  assert.equal(rows.length, 3);
  assert.deepEqual(rows.map((r) => r.year), ["2026-27", "2027-28", "2028-29"]);
  assert.deepEqual(rows.map((r) => r.period_end), ["2027-03-31", "2028-03-31", "2029-03-31"]);
  assert.ok(rows.every((r) => r.period_months === 12 && r.projected));
  assert.equal(rows[0].in_year_balance, 50_000);
  assert.equal(rows[0].revenue_reserve, last.revenue_reserve + 50_000);
  assert.equal(rows[1].revenue_reserve, 10_000);
  assert.equal(rows[2].revenue_reserve, 10_000 + 100_000);
  assert.equal(rows[0].pupils, last.pupils);
  assert.equal(T.projectRows(history, [{ income: "", spend: 1 }, { income: 5, spend: 1 }]).length, 0);
});

test("budgetCheck gives a status for each year, the runway and a supportive explanation", () => {
  // Arrange
  const history = T.prefillFrom(makeSx(), S).rows, last = fin(LATEST);
  const flat = [1, 2, 3].map(() => ({ income: last.total_income, spend: last.total_expenditure }));
  const recover = [{ income: 4_100_000, spend: 3_950_000 }, { income: 4_150_000, spend: 4_000_000 }, { income: 4_200_000, spend: 4_050_000 }];
  // Act
  const stuck = keep(T.budgetCheck(history, flat, CTX)), back = keep(T.budgetCheck(history, recover, CTX));
  const drawing = keep(T.budgetCheck([{ year: "2025-26", period_end: "2026-03-31", period_months: 12, total_income: 3e6, in_year_balance: 0, revenue_reserve: 400_000, source: "CFR" }],
    [{ income: 3e6, spend: 3.15e6 }, { income: 3e6, spend: 3.15e6 }], CTX));
  // Assert
  assert.equal(stuck.now.status, "in_deficit");
  assert.equal(stuck.years.length, 3);
  assert.ok(stuck.years.every((y) => y.status === "in_deficit" && y.reason.startsWith("In deficit by")));
  assert.equal(stuck.years[2].reserve, last.revenue_reserve + 3 * (last.total_income - last.total_expenditure));
  assert.match(stuck.explanation.join(" "), /still be below zero/);
  assert.ok(stuck.helps.length >= 2);
  assert.ok(stuck.context.some((c) => /\(IFS 2026 report, pp\. 62, 63\)$/.test(c.text)));
  assert.equal(back.status, "healthy");
  assert.equal(back.years[2].year, "2028-29");
  assert.match(back.explanation.join(" "), /back above zero by the end of 2027-28/);
  assert.equal(drawing.status, "heading_for_deficit");
  assert.equal(drawing.years[1].reserve, 100_000);
  assert.equal(drawing.runway_years, 100_000 / ((0 + 150_000 + 150_000) / 3));
  assert.match(drawing.years[1].reason, /runs out in about 1 year\.$/);
  assert.ok(drawing.context.some((c) => c.title === ifs.framings.one_deficit_year.title));
  assert.match(T.budgetCheck([], [], CTX).summary, /Enter the last full year/);
});

test("planPta adds events, Gift Aid on declared donations only, per pupil and the gap", () => {
  // Arrange
  const pupils = fin(LATEST).pupils;
  // Act
  const plan = keep(T.planPta({ events: [{ name: "Summer fair", income: 1000, donations: 2000 }, { name: "Quiz", income: "£500", donations: 0 }, { name: "", income: 0, donations: 0 }],
    pupils, giftAidShare: 0.5, targetPp: 10 }));
  // Assert
  assert.equal(plan.events.length, 2);
  assert.equal(plan.income, 1500);
  assert.equal(plan.donations, 2000);
  assert.equal(plan.giftAid, 0.25 * 2000 * 0.5);
  assert.equal(plan.total, 1500 + 2000 + 250);
  assert.equal(plan.perPupil, 3750 / pupils);
  assert.equal(plan.target, 10 * pupils);
  assert.equal(plan.gap, 10 * pupils - 3750);
  assert.equal(T.planPta({ events: [{ donations: 100 }], giftAidShare: 7 }).giftAid, 25);
  assert.equal(T.planPta({ events: [{ donations: 100 }], giftAidShare: -1 }).giftAid, 0);
  assert.equal(T.planPta({ events: [{ income: 100 }] }).perPupil, null);
  assert.ok(T.planPta({ events: [{ income: 6000 }] }).notes.some((n) => n.includes("£5,000")));
});

test("comparePta uses the latest council median and band medians only when present", () => {
  // Arrange
  const plan = T.planPta({ events: [{ income: 5000, donations: 4000 }], pupils: 432.5, giftAidShare: 0.5 });
  plan.band = 2;
  // Act
  const plain = keep(T.comparePta(plan, COUNCIL)), banded = keep(T.comparePta(plan, COUNCIL, { 1: 30, 2: 18, 3: 12 }));
  const listed = T.comparePta(plan, COUNCIL, [30, 18, 12, 9, 6]), none = keep(T.comparePta(plan, null));
  // Assert
  assert.equal(plain.year, "2024-25");
  assert.equal(plain.medianPp, 24.5);
  assert.ok(Math.abs(plain.differencePp - (plan.perPupil - 24.5)) < 1e-9);
  assert.equal(plain.bandAvailable, false);
  assert.ok(plain.sentences.some((s) => s.includes("aren't available")));
  assert.ok(plain.sentences.some((s) => s.includes("Charity Commission register") && s.includes("2024-25")));
  assert.equal(banded.bandMedianPp, 18);
  assert.equal(listed.bandMedianPp, 18);
  assert.ok(banded.sentences.some((s) => s.includes("band 2 of 5")));
  assert.equal(none.medianPp, null);
  assert.ok(none.sentences.every((s) => !s.includes("NaN") && !s.includes("undefined")));
});

test("adapt reads the parents' association and its latest year from /data/s", () => {
  // Act
  const school = T.adapt(S, null, null).school;
  // Assert
  assert.equal(school.pta.length, 1);
  assert.equal(school.pta[0].number, String(gold.ptfa.charity_number));
  assert.equal(school.pta[0].income, gold.ptfa.years["2024-25"].income);
  assert.equal(school.pta[0].period_end, gold.ptfa.years["2024-25"].period.split(" to ")[1]);
  assert.equal(T.adapt({ ...S, pta: [{ name: "x", review: "check" }] }, null, null).school.pta.length, 0);
});

test("embedSnippet escapes the name and keeps only digits of the URN", () => {
  // Act
  const code = keep(T.embedSnippet("130932", 'St Mary & St John\'s "Big" <School>'));
  // Assert
  assert.equal(code, '<iframe src="https://money.schoolsinreach.com/embed/130932/" title="School Money: St Mary &amp; St John&#39;s &quot;Big&quot; &lt;School&gt;" width="320" height="140" loading="lazy" style="border:0"></iframe>');
  assert.equal(T.embedSnippet('1"><script>2', "x").includes("/embed/12/"), true);
  assert.equal(T.embedSnippet("", "x"), "");
});

test("every request goes to a /data/ path, and odd URNs or ids request nothing", async () => {
  // Arrange
  routes = { "/data/sx/130932.json": makeSx(), "/data/s/130932.json": S, "/data/a/council-204.json": COUNCIL, "/data/s/100002.json": "not json" };
  requested.length = 0;
  // Act
  const ok = keep(await T.loadSchool("130932"));
  const missing = keep(await T.loadSchool("100001"));
  const broken = keep(await T.loadSchool("100002"));
  const odd = await Promise.all(["../../etc/passwd", "130932?x=1", "https://evil.example/1", "", null].map((u) => T.loadSchool(u)));
  const area = await T.loadArea("council-204");
  const areaOdd = await Promise.all(["../secret", "//evil.example", "council 204"].map((a) => T.loadArea(a)));
  const raw = await Promise.all(["../x.json", "//evil.example/x.json", "https://evil.example/x.json", "s/../../x.json"].map((p) => T.getJSON(p)));
  // Assert
  assert.ok(requested.length > 0);
  assert.ok(requested.every((u) => u.startsWith("/data/")), requested.join(", "));
  assert.equal(ok.ok, true);
  assert.equal(ok.data.school.name, gold.name);
  assert.equal(missing.ok, false);
  assert.match(missing.message, /aren't published/);
  assert.equal(broken.ok, false);
  assert.ok(odd.every((r) => r.ok === false));
  assert.equal(area.name, "Hackney");
  assert.ok(areaOdd.every((a) => a === null));
  assert.ok(raw.every((a) => a === null));
  assert.equal(requested.filter((u) => u.includes("evil") || u.includes("..")).length, 0);
  assert.deepEqual(requested, ["/data/sx/130932.json", "/data/s/130932.json", "/data/sx/100001.json", "/data/s/100001.json",
    "/data/sx/100002.json", "/data/s/100002.json", "/data/a/council-204.json"]);
});

test("no output string uses banned words or the old PTFA figure", () => {
  // Arrange
  const banned = ["po" + "or school", "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", "no " + "pta", "307" + "k"];
  const all = strings(outputs).concat(strings(T.LABELS));
  // Act
  const hits = all.filter((s) => banned.some((b) => s.toLowerCase().includes(b)));
  // Assert
  assert.ok(all.length > 50);
  assert.deepEqual(hits, []);
});
