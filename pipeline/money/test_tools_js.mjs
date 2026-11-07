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
  assert.equal(cases.length, 40);
  cases.forEach((c, i) => {
    // Act
    const got = keep(T.assess(c.rows)), want = expected[i];
    // Assert
    if (want === null) { assert.equal(got, null, c.name); return; }
    for (const k of ["status", "label", "rank", "deficit_streak", "reason", "year", "source", "reserve", "years", "trust_share_included"]) {
      assert.equal(got[k], want[k], c.name + ": " + k);
    }
    for (const k of ["reserve_share", "runway_years", "pupils_change"]) {
      if (want[k] === null) assert.equal(got[k], null, c.name + ": " + k);
      else assert.ok(Math.abs(got[k] - want[k]) < 1e-9, c.name + ": " + k + " " + got[k] + " vs " + want[k]);
    }
  });
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
