// Pure-helper tests for assets/map.js (MoneyMap) under node: no DOM, no network.
// Run: node --test pipeline/money/test_map_js.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// Arrange (shared): localStorage and fetch stubs before the scripts run; fetch never reaches the network.
const memory = new Map();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: (k) => (memory.has(k) ? memory.get(k) : null),
    setItem: (k, v) => memory.set(k, String(v)),
    removeItem: (k) => memory.delete(k),
  },
});
globalThis.fetch = async () => ({ ok: false, status: 404, json: async () => { throw new Error("not JSON"); } });
const here = dirname(fileURLToPath(import.meta.url));
await import(pathToFileURL(join(here, "assets", "app.js")).href);
await import(pathToFileURL(join(here, "assets", "map.js")).href);
const MM = globalThis.MoneyMap;
const MA = globalThis.MoneyApp;

// Built from pieces so this file never contains the phrases it checks for.
const BANNED = ["poor" + " school", "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", "no" + " pta", "307" + "k"];
const PALETTE = { accent: "#0f6e6a", critical: "#c0392b", plenty: "#0f6e6a", lineStrong: "#b9ae9b", card: "#fffdf9" };
const META = {
  pct_in_deficit: { key: "pct_in_deficit", label: "Share of schools in deficit", unit: "pct", signed: false, scale: "sequential",
    source: "DfE CFR (council-run) and AAR (academy) returns", levels: ["england", "council", "constituency"] },
  deficit_pp: { key: "deficit_pp", label: "Deficit per pupil, schools in deficit", unit: "gbp_pp", signed: true, scale: "diverging",
    source: "DfE CFR (council-run) and AAR (academy) returns", levels: ["england", "council", "constituency"] },
  dsg_pp: { key: "dsg_pp", label: "Council high-needs (DSG) balance per pupil", unit: "gbp_pp", signed: true, scale: "diverging",
    source: "DfE section 251 outturn (Dedicated Schools Grant balance)", levels: ["england", "council"] },
  spend_pp_median: { key: "spend_pp_median", label: "Median spending per pupil", unit: "gbp_pp", signed: false, scale: "sequential",
    source: "DfE CFR (council-run) and AAR (academy) returns", levels: ["england", "council", "constituency"] },
};
const CTX = {
  why: { title: "Why schools go into deficit", text: "Most of a school's money goes on people.", pages: [62, 63] },
  send: { title: "Special educational needs (SEND) pressure", text: "Support for SEND is the fastest-growing part.", pages: [46, 61] },
  cite: "IFS, Annual report on education spending in England: 2025–26 (January 2026)",
  helps: "What helps: a plan agreed with the council or trust.", dsg_note: "Statutory override: since 2020-21 DSG deficits are held apart.",
  cash_note: "£ figures are cash for each year, not adjusted for inflation.", pta_note: "Charities with income of £5,000 or less need not register.",
};
const OPTS = { measures: Object.keys(META), years: ["2023-24", "2024-25", "2025-26"], meta: META,
  defaults: { m: "pct_in_deficit", y: "2025-26", g: "council" } };
const models = [];
function keep(m) { models.push(m); return m; }
function line(model, label) { return model.lines.find((l) => l.label === label); }

// Reference school: /data/s, /data/a and measures fixtures built from the committed gold file.
const GOLD = JSON.parse(readFileSync(join(here, "data", "gold", "130932.json"), "utf8"));
function goldYear(y) { return GOLD.years[y].totals.pipeline_finance_history; }
function goldS() {
  const t = goldYear("2025-26");
  return {
    urn: GOLD.urn, name: GOLD.name, path: `/school/${GOLD.urn}-william-patten-primary-school/`,
    council: { code: String(GOLD.la.code), name: GOLD.la.name, path: "/council/hackney/" },
    status: "in_deficit", label: "In deficit", reason: "Spent more than it received.", year: "2025-26", academy: false,
    pupils: t.pupils, income: t.total_income, income_pp: Math.round(t.total_income / t.pupils),
    spend: t.total_expenditure, spend_pp: Math.round(t.total_expenditure / t.pupils),
    reserve: t.revenue_reserve, reserve_pp: Math.round(t.revenue_reserve / t.pupils),
    years: Object.keys(GOLD.years).map((y) => ({ y, income: goldYear(y).total_income, reserve: goldYear(y).revenue_reserve, pupils: goldYear(y).pupils })),
  };
}

test("MoneyMap exports the pure API", () => {
  for (const k of ["binsFor", "classify", "ramp", "legendModel", "parseState", "serialiseState", "searchHits", "pickTarget",
    "areaCardModel", "schoolCardModel", "fmtExact", "captionText", "schoolRows"]) {
    assert.equal(typeof MM[k], "function", k);
  }
});

test("fmtExact formats to the pound, en-GB", () => {
  assert.equal(MM.fmtExact(4115.4), "£4,115");
  assert.equal(MM.fmtExact(-488.2, true), "-£488");
  assert.equal(MM.fmtExact(25, true), "+£25");
  assert.equal(MM.fmtExact(null), "—");
});

test("sequential bins use quantile breaks with duplicates removed", () => {
  // Arrange
  const values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, null, undefined, NaN];
  // Act
  const bins = MM.binsFor(values, { scale: "sequential", n: 5, unit: "pupils" });
  const flat = MM.binsFor([7, 7, 7, 7], { scale: "sequential", unit: "pupils" });
  // Assert
  assert.deepEqual(bins.thresholds, [3, 5, 7, 9]);
  assert.equal(bins.classes.length, 5);
  assert.equal(MM.classify(1, bins), 0);
  assert.equal(MM.classify(5, bins), 2);
  assert.equal(MM.classify(10, bins), 4);
  assert.equal(flat.classes.length, 1);
  assert.equal(MM.classify(7, flat), 0);
});

test("missing values classify as null, never as the lowest class", () => {
  // Arrange
  const bins = MM.binsFor([10, 20, 30, 40, 50], { scale: "sequential", unit: "pct" });
  // Act / Assert
  for (const v of [null, undefined, NaN, "12", Infinity]) assert.equal(MM.classify(v, bins), null, String(v));
  assert.equal(MM.classify(10, MM.binsFor([], { scale: "sequential" })), null);
});

test("diverging bins are symmetric about 0 with a grey middle class", () => {
  // Arrange
  const values = [-900, -600, -300, -40, 0, 30, 250, 500, 800, 1100];
  // Act
  const bins = MM.binsFor(values, { scale: "diverging", n: 5, unit: "gbp_pp" });
  const colours = MM.ramp("diverging", PALETTE, bins.classes.length);
  // Assert
  assert.equal(bins.classes.length, 5);
  assert.deepEqual(bins.classes.map((c) => c.side), ["neg", "neg", "mid", "pos", "pos"]);
  assert.equal(bins.classes[2].lo, -bins.classes[2].hi);
  assert.equal(MM.classify(0, bins), 2);
  assert.equal(MM.classify(-40, bins), 2);
  assert.equal(MM.classify(-900, bins), 0);
  assert.equal(MM.classify(1100, bins), 4);
  assert.equal(MM.classify(-bins.thresholds[0], bins), 1);
  assert.equal(MM.classify(bins.thresholds[0], bins), 3);
  assert.equal(colours[2], PALETTE.lineStrong);
  assert.equal(colours[0], PALETTE.critical);
  assert.equal(colours[4], PALETTE.plenty);
});

test("sequential ramp is one hue at rising strength", () => {
  // Act
  const colours = MM.ramp("sequential", PALETTE, 5);
  // Assert
  assert.equal(colours.length, 5);
  assert.equal(colours[4], PALETTE.accent);
  assert.equal(new Set(colours).size, 5);
  assert.equal(MM.ramp("sequential", PALETTE, 1).length, 1);
});

test("legend labels carry units and mark England's class", () => {
  // Arrange
  const pp = MM.binsFor([1000, 1100, 1200, 1300, 1500, 1600], { scale: "sequential", n: 3, unit: "gbp_pp" });
  const pct = MM.binsFor([5, 8, 10, 12, 15, 20], { scale: "sequential", n: 3, unit: "pct" });
  // Act
  const a = keep(MM.legendModel(pp, META.spend_pp_median, 1250));
  const b = keep(MM.legendModel(pct, META.pct_in_deficit, 12.4));
  const none = keep(MM.legendModel(MM.binsFor([], {}), META.pct_in_deficit, null));
  // Assert
  assert.deepEqual(a.items.map((i) => i.label), ["£1,000 to £1,199 per pupil", "£1,200 to £1,499 per pupil", "£1,500 to £1,600 per pupil"]);
  assert.deepEqual(a.england, { cls: 1, text: "England: £1,250 per pupil" });
  assert.deepEqual(b.items.map((i) => i.label), ["5.0% to 9.9%", "10.0% to 14.9%", "15.0% to 20.0%"]);
  assert.deepEqual(b.england, { cls: 1, text: "England: 12.4%" });
  assert.deepEqual(a.missing, { label: "No data", cls: null });
  assert.equal(none.england, null);
  assert.equal(none.empty, "Figures for this year aren't published yet.");
});

test("diverging legend labels read as ranges around zero", () => {
  // Arrange
  const bins = MM.binsFor([-1000, -500, 0, 500, 1000], { scale: "diverging", unit: "gbp_pp" });
  // Act
  const model = keep(MM.legendModel(bins, META.deficit_pp, -300));
  // Assert
  assert.deepEqual(model.items.map((i) => i.label),
    ["-£600 or less per pupil", "-£599 to -£200 per pupil", "-£199 to £199 per pupil", "£200 to £599 per pupil", "£600 or more per pupil"]);
  assert.equal(model.england.cls, 1);
  assert.equal(model.england.text, "England: -£300 per pupil");
});

test("parseState and serialiseState round-trip and omit defaults", () => {
  // Arrange
  const states = [
    { m: "pct_in_deficit", y: "2025-26", g: "council", q: "" },
    { m: "deficit_pp", y: "2023-24", g: "constituency", q: "Hackney & Stoke" },
    { m: "dsg_pp", y: "2024-25", g: "council", q: "" },
  ];
  // Act / Assert
  assert.equal(MM.serialiseState(states[0], OPTS), "");
  assert.deepEqual(MM.parseState("", OPTS), states[0]);
  for (const s of states) {
    const text = MM.serialiseState(s, OPTS);
    assert.deepEqual(MM.parseState(text, OPTS), s, text);
    assert.equal(MM.serialiseState(MM.parseState(text, OPTS), OPTS), text);
  }
  assert.equal(MM.serialiseState(states[1], OPTS), "?m=deficit_pp&y=2023-24&g=constituency&q=Hackney%20%26%20Stoke");
});

test("parseState falls back to defaults on bad input", () => {
  // Act
  const bad = MM.parseState("?m=bogus&y=1999-00&g=moon&q=%E0%A4%A", OPTS);
  const dsg = MM.parseState("?m=dsg_pp&g=constituency", OPTS);
  const long = MM.parseState("?q=" + "a".repeat(200) + "&y=nonsense", OPTS);
  const noYears = MM.parseState("?y=2030-31", {});
  // Assert
  assert.deepEqual(bad, { m: "pct_in_deficit", y: "2025-26", g: "council", q: "" });
  assert.deepEqual(dsg, { m: "pct_in_deficit", y: "2025-26", g: "constituency", q: "" });
  assert.equal(long.q.length, 80);
  assert.equal(long.y, "2025-26");
  assert.equal(noYears.y, "2030-31");
});

test("searchHits uses MoneyApp.rankSearch when app.js is loaded and keeps map rows only", () => {
  // Arrange
  const rows = [
    { t: "school", id: "130932", name: "William Patten Primary School", sub: "Hackney" },
    { t: "council", id: "204", name: "Hackney", sub: "Council" },
    { t: "constituency", id: "E14001272", name: "Hackney North and Stoke Newington", sub: "Constituency" },
    { t: "trust", id: "t1", name: "Hackney Learning Trust", sub: "Trust" },
  ];
  const real = MA.rankSearch;
  let calls = 0;
  MA.rankSearch = (r, q, l) => { calls++; return real(r, q, l); };
  // Act
  let hits;
  try { hits = MM.searchHits(rows, "hackney", 8); } finally { MA.rankSearch = real; }
  // Assert
  assert.equal(calls, 1);
  assert.deepEqual(hits.map((h) => h.t), ["council", "constituency", "school"]);
  assert.ok(!hits.some((h) => h.t === "trust"));
});

test("searchHits falls back to a local ranking without app.js", () => {
  // Arrange
  const rows = [{ t: "council", id: "204", name: "Hackney" }, { t: "school", id: "1", name: "Hackney Free School" }];
  const saved = globalThis.MoneyApp;
  delete globalThis.MoneyApp;
  // Act
  let hits;
  try { hits = MM.searchHits(rows, "hack", 5); } finally { globalThis.MoneyApp = saved; }
  // Assert
  assert.deepEqual(hits.map((h) => h.id), ["1", "204"]);
});

test("pickTarget matches a boundary by id, then by normalised name", () => {
  // Arrange
  const councils = { type: "FeatureCollection", features: [
    { properties: { id: "council-202", code: "202", name: "Camden" } },
    { properties: { id: "council-204", code: "204", name: "Hackney" } }] };
  const constituencies = [{ properties: { id: "constituency-E14001272", code: "E14001272", name: "Hackney North & Stoke Newington" } }];
  // Act
  const byId = MM.pickTarget({ t: "council", id: "204", name: "London Borough of Hackney" }, { council: councils, constituency: constituencies });
  const byName = MM.pickTarget({ t: "constituency", id: "hackney-north-and-stoke-newington", name: "Hackney North and Stoke Newington" }, constituencies);
  const none = MM.pickTarget({ t: "council", id: "999", name: "Nowhere" }, councils);
  // Assert
  assert.deepEqual(byId, { kind: "area", geo: "council", id: "council-204", featureIndex: 1 });
  assert.deepEqual(byName, { kind: "area", geo: "constituency", id: "constituency-E14001272", featureIndex: 0 });
  assert.deepEqual(none, { kind: "area", geo: "council", id: "council-999", featureIndex: -1 });
  assert.deepEqual(MM.pickTarget({ t: "school", id: 130932, name: "William Patten" }, councils), { kind: "school", urn: "130932" });
  assert.equal(MM.pickTarget({ t: "trust", id: "t1", name: "Trust" }, councils), null);
});

test("area card states the year, source, England comparison and deficit counts", () => {
  // Arrange
  const entry = { id: "council-204", name: "Hackney", p: "/council/hackney/",
    m: { pct_in_deficit: { "2023-24": 11.1, "2024-25": 14.5, "2025-26": 18.2 }, pupils: { "2025-26": 25432.5 } } };
  const england = { pct_in_deficit: { "2025-26": 12.4 } };
  const areaDoc = { id: "council-204", type: "council", name: "Hackney", by_year: { "2025-26": { all: { schools: 55, in_deficit: 10 } } } };
  // Act
  const model = keep(MM.areaCardModel(entry, META.pct_in_deficit, "2025-26", england, areaDoc, CTX));
  // Assert
  const first = model.lines[0];
  assert.equal(`${first.label}: ${first.text}`, "Share of schools in deficit, 2025-26: 18.2% (England 12.4%)");
  assert.equal(line(model, "Schools in deficit").text, "10 of 55 in 2025-26");
  assert.equal(line(model, "Pupils, 2025-26").text, "25,432.5");
  assert.equal(line(model, "Source").text, "2025-26, DfE CFR (council-run) and AAR (academy) returns");
  assert.ok(line(model, "Why schools go into deficit").text.includes("p.62–63"));
  assert.ok(line(model, "What helps"));
  assert.deepEqual(model.spark, [{ y: "2023-24", v: 11.1 }, { y: "2024-25", v: 14.5 }, { y: "2025-26", v: 18.2 }]);
  assert.deepEqual(model.pin, { type: "area", id: "council-204", name: "Hackney", p: "/council/hackney/" });
  assert.deepEqual(model.open, { href: "/council/hackney/", text: "Open the Hackney page" });
});

test("area card says a missing figure isn't published, never £0", () => {
  // Arrange
  const entry = { id: "council-201", name: "City of London", p: "/council/city-of-london/", m: {} };
  // Act
  const model = keep(MM.areaCardModel(entry, META.spend_pp_median, "2025-26", { spend_pp_median: { "2025-26": 7400 } }, null, CTX));
  const dsg = keep(MM.areaCardModel({ id: "council-204", name: "Hackney", m: { dsg_pp: { "2025-26": -512 } } }, META.dsg_pp, "2025-26",
    -849, { dsg: { "2025-26": { balance: -23100000, per_pupil: -512 } } }, CTX));
  // Assert
  assert.equal(model.lines[0].text, "Not published for this year (England £7,400 per pupil)");
  assert.ok(!JSON.stringify(model).includes("£0"));
  assert.equal(dsg.lines[0].text, "-£512 per pupil, total -£23.1m (England -£849 per pupil)");
  assert.ok(line(dsg, "High-needs budgets").text.startsWith("Statutory override"));
  assert.ok(line(dsg, "Special educational needs (SEND) pressure"));
  assert.ok(line(dsg, "What helps"));
});

test("school card for the reference school matches the gold file", () => {
  // Arrange
  const s = goldS(), t = goldYear("2025-26");
  // Act
  const model = keep(MM.schoolCardModel(s, CTX));
  // Assert
  assert.equal(model.title, GOLD.name);
  assert.deepEqual(model.status, { key: "in_deficit", icon: "▼", label: "In deficit" });
  assert.equal(line(model, "Status, 2025-26").text, "▼ In deficit");
  assert.equal(line(model, "Reserve per pupil, 2025-26").text,
    `${MM.fmtExact(Math.round(t.revenue_reserve / t.pupils), true)} per pupil (total ${MA.fmtMoney(t.revenue_reserve, true)})`);
  assert.equal(line(model, "Income per pupil, 2025-26").text,
    `${MM.fmtExact(Math.round(t.total_income / t.pupils))} per pupil (total ${MA.fmtMoney(t.total_income)})`);
  assert.equal(line(model, "Pupils, 2025-26").text, "432.5");
  assert.equal(line(model, "Source").text, "2025-26, DfE CFR return");
  assert.ok(line(model, "Why schools go into deficit"));
  assert.ok(line(model, "What helps"));
  assert.deepEqual(model.pin, { type: "school", id: "130932", name: GOLD.name, p: s.path });
  assert.deepEqual(model.open, { href: s.path, text: "Open the school page" });
  assert.ok(model.links.some((l) => l.href === "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/130932"));
});

test("school card without figures says so and never shows £0", () => {
  // Arrange
  const sparse = { urn: 999001, name: "Sparse School", status: null, year: "2025-26", academy: true, pupils: null };
  // Act
  const model = keep(MM.schoolCardModel(sparse, CTX));
  const failed = keep(MM.schoolCardModel(null, CTX, { urn: "999002", name: "Unloaded School" }));
  // Assert
  assert.equal(line(model, "Reserve per pupil, 2025-26").text, "Not published for this year");
  assert.equal(line(model, "Income per pupil, 2025-26").text, "Not published for this year");
  assert.equal(line(model, "Status, 2025-26").text, "No published status for this school");
  assert.equal(line(model, "Source").text, "2025-26, DfE AAR return");
  assert.ok(!JSON.stringify(model).includes("£0"));
  assert.equal(failed.lines[0].text, "This school's figures couldn't be loaded just now. Its page has them.");
  assert.equal(failed.open.href, "/school/999002-unloaded-school/");
  assert.equal(failed.pin.id, "999002");
});

test("the pin payload is exactly {type, id, name, p}", () => {
  // Arrange / Act
  const school = keep(MM.schoolCardModel(goldS(), CTX)).pin;
  const areaPin = keep(MM.areaCardModel({ id: "constituency-E14001272", name: "Hackney North", p: "/constituency/E14001272/", m: {} },
    META.pct_in_deficit, "2025-26", {}, null, CTX)).pin;
  // Assert
  assert.deepEqual(Object.keys(school), ["type", "id", "name", "p"]);
  assert.deepEqual(Object.keys(areaPin), ["type", "id", "name", "p"]);
  assert.equal(MA.togglePin([], areaPin).action, "added");
});

test("deficits are only named alongside why and what helps", () => {
  // Assert
  for (const m of models.filter((x) => x && x.lines)) {
    const text = JSON.stringify(m.lines);
    if (/deficit/i.test(text)) {
      assert.ok(m.lines.some((l) => l.kind === "why"), m.title);
      assert.ok(m.lines.some((l) => l.kind === "helps"), m.title);
    }
  }
});

test("captions and school rows decode", () => {
  // Arrange
  const doc = { key: { status: ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves"], phase: ["primary", "secondary"],
    governance: ["council-run", "academy"], fields: ["urn", "lat", "lon", "status", "phase", "governance", "name"] },
  rows: [[130932, 51.5592, -0.0663, 0, 0, 0, GOLD.name], [1, 52, -1, -1, 1, 1, "No Status Academy"], ["bad"]] };
  // Act
  const rows = MM.schoolRows(doc);
  const caption = MM.captionText(META.pct_in_deficit, "2025-26", 12.4, "council");
  models.push({ caption });
  // Assert
  assert.equal(caption, "Share of schools in deficit, 2025-26, by council. England: 12.4%. Source: DfE CFR (council-run) and AAR (academy) returns.");
  assert.deepEqual(rows[0], { urn: "130932", lat: 51.5592, lon: -0.0663, status: "in_deficit", phase: "primary", governance: "council-run", name: GOLD.name });
  assert.equal(rows[1].status, null);
  assert.equal(rows.length, 2);
  assert.equal(MM.dotVisible(rows[1], { phase: ["secondary"], gov: ["academy"], status: ["none"] }), true);
  assert.equal(MM.dotVisible(rows[0], { phase: ["primary"], gov: ["council-run"], status: ["healthy"] }), false);
});

test("no model string uses banned words", () => {
  // Arrange
  const text = JSON.stringify(models).toLowerCase();
  // Act
  const found = BANNED.filter((w) => text.includes(w));
  // Assert
  assert.ok(models.length >= 8);
  assert.deepEqual(found, []);
});
