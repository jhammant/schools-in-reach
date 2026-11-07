// Tests for assets/app.js under node (no browser, no network): the pure helpers, then the SERIES drill,
// table filters and pinned rows wired up on a small fake DOM. Run: node --test pipeline/money/test_app_js.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

// Arrange (shared): a localStorage stub before the script runs; node's own localStorage needs a flag.
const memory = new Map();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: (k) => (memory.has(k) ? memory.get(k) : null),
    setItem: (k, v) => memory.set(k, String(v)),
    removeItem: (k) => memory.delete(k),
  },
});
const here = dirname(fileURLToPath(import.meta.url));
await import(pathToFileURL(join(here, "assets", "app.js")).href);
const M = globalThis.MoneyApp;

test("MoneyApp exports the helpers", () => {
  for (const k of ["fmtMoney", "perPupil", "parsePostcode", "rankSearch", "pinLimits", "togglePin", "importShortlist", "postcodeLookup",
                   "seriesDrill", "parseTags", "rowShown", "pinnedFirst"]) {
    assert.ok(M[k], k);
  }
});

test("fmtMoney formats like charts.money", () => {
  assert.equal(M.fmtMoney(-1_234_567), "-£1.2m");
  assert.equal(M.fmtMoney(543_210), "£543k");
  assert.equal(M.fmtMoney(950), "£950");
  assert.equal(M.fmtMoney(1_250_000_000), "£1.25bn");
  assert.equal(M.fmtMoney(25_000, true), "+£25k");
  assert.equal(M.fmtMoney(0), "£0");
  assert.equal(M.fmtMoney(null), "—");
  assert.equal(M.fmtMoney("x"), "—");
});

test("unitOf and fmtUnit keep percentages and counts out of pounds", () => {
  assert.equal(M.unitOf("in_deficit_pct", null, ""), "pct");
  assert.equal(M.unitOf("total_income", null, "£1.2m £6,000 per pupil"), "money");
  assert.equal(M.unitOf("reserve_share", null, "4.5%"), "pct");
  assert.equal(M.unitOf("revenue_reserve_incl_trust_share", null, "£80k"), "money");
  assert.equal(M.unitOf("schools", "n", ""), "n");
  assert.equal(M.fmtUnit(12.4, "pct"), "12.4%");
  assert.equal(M.fmtUnit(12, "pct"), "12%");
  assert.equal(M.fmtUnit(-2.5, "pct", true), "-2.5%");
  assert.equal(M.fmtUnit(1234, "n"), "1,234");
  assert.equal(M.fmtUnit(null, "pct"), "—");
  assert.equal(M.fmtUnit(1_234_567, "money"), "£1.2m");
  assert.equal(M.fmtUnit(1_234_567, "money", false, true), "£1,234,567");
});

test("perPupil divides by the same row's pupils and is null without pupils", () => {
  assert.equal(M.perPupil(1_234_567, 300), 4115);
  assert.equal(M.perPupil(1000, null), null);
  assert.equal(M.perPupil(1000, 0), null);
  assert.equal(M.perPupil(null, 300), null);
  assert.equal(M.perPupil(-3000, 300), -10);
});

test("parsePostcode finds the outward district", () => {
  assert.deepEqual(M.parsePostcode("E8 1AA"), { district: "E8", inward: "1AA", full: "E8 1AA" });
  assert.equal(M.parsePostcode("n16 0ab").district, "N16");
  assert.equal(M.parsePostcode("  sw1a1aa ").district, "SW1A");
  assert.equal(M.parsePostcode("EC1A").district, "EC1A");
  assert.equal(M.parsePostcode("hello"), null);
  assert.equal(M.parsePostcode("William Patten"), null);
  assert.equal(M.parsePostcode(""), null);
  assert.equal(M.parsePostcode(null), null);
});

const ROWS = [
  { t: "trust", id: "hackney-learning-trust", name: "Hackney Learning Trust", sub: "", status: null, p: "/trust/hackney-learning-trust/" },
  { t: "school", id: "100001", name: "Stoke Newington School", sub: "Hackney", status: "healthy", p: "/school/100001-stoke-newington-school/" },
  { t: "council", id: "204", name: "Hackney", sub: "London", status: null, p: "/council/hackney/" },
  { t: "school", id: "100002", name: "Hackney New School", sub: "Hackney", status: "tight", p: "/school/100002-hackney-new-school/" },
  { t: "constituency", id: "hackney-north", name: "Hackney North and Stoke Newington", sub: "", status: null, p: "/constituency/hackney-north/" },
  { t: "school", id: "100003", name: "William Patten Primary School", sub: "Stoke Newington, Hackney", status: "in_deficit", p: "/school/100003-william-patten-primary-school/" },
  { t: "school", id: "100004", name: "Thomas Fairchild Community School", sub: "Hoxton, Hackney", status: "healthy", p: "/school/100004-thomas-fairchild/" },
];

test("rankSearch: prefix > word match > substring, type order school, council, constituency, trust", () => {
  const names = M.rankSearch(ROWS, "hackney").map((r) => r.id);
  // Prefix hits first (school before council before constituency before trust), then word/substring hits.
  assert.deepEqual(names.slice(0, 4), ["100002", "204", "hackney-north", "hackney-learning-trust"]);
  assert.ok(names.indexOf("100001") > 3, "Stoke Newington School matches only via its sub text");
  assert.ok(names.indexOf("100003") > 3);
  assert.equal(M.rankSearch(ROWS, "patten")[0].id, "100003", "word prefix beats substring");
  assert.equal(M.rankSearch(ROWS, "new sch")[0].id, "100002", "every word a word-prefix in the name");
  assert.equal(M.rankSearch(ROWS, "ewing")[0].name, "Stoke Newington School", "substring still matches");
  assert.deepEqual(M.rankSearch(ROWS, "zzz"), []);
  assert.deepEqual(M.rankSearch(ROWS, "   "), []);
  assert.equal(M.rankSearch(ROWS, "hackney", 2).length, 2, "limit respected");
  assert.equal(M.rankSearch(ROWS, "hackney").length, Math.min(8, 7));
});

test("pinLimits and togglePin: toggle, limits per type counted separately, input not mutated", () => {
  assert.deepEqual(M.pinLimits, { school: 6, area: 4 });
  const start = [];
  let r = M.togglePin(start, { type: "school", id: 1, name: "A", p: "/school/1-a/" });
  assert.equal(r.action, "added");
  assert.deepEqual(r.list, [{ type: "school", id: "1", name: "A", p: "/school/1-a/" }]);
  assert.deepEqual(start, [], "input list untouched");
  r = M.togglePin(r.list, { type: "school", id: "1", name: "A", p: "/school/1-a/" });
  assert.equal(r.action, "removed");
  assert.deepEqual(r.list, []);

  let list = [];
  for (let i = 1; i <= 6; i++) list = M.togglePin(list, { type: "school", id: i, name: "S" + i, p: "/s/" + i }).list;
  assert.equal(list.length, 6);
  r = M.togglePin(list, { type: "school", id: 7, name: "S7", p: "/s/7" });
  assert.equal(r.action, "full");
  assert.equal(r.limit, 6);
  assert.equal(r.list.length, 6, "7th school rejected");
  // Areas are counted separately from schools.
  for (let i = 1; i <= 4; i++) {
    r = M.togglePin(list, { type: "area", id: "council-" + i, name: "C" + i, p: "/council/c" + i + "/" });
    assert.equal(r.action, "added", "area " + i + " fits beside 6 schools");
    list = r.list;
  }
  assert.equal(list.length, 10);
  r = M.togglePin(list, { type: "area", id: "england", name: "England", p: "/" });
  assert.equal(r.action, "full");
  assert.equal(r.limit, 4, "5th area rejected");
  // Removing one school frees a slot.
  list = M.togglePin(list, { type: "school", id: "3" }).list;
  assert.equal(M.togglePin(list, { type: "school", id: 7, name: "S7", p: "/s/7" }).action, "added");
});

test("importShortlist: strings and numbers, de-duplicated, unknown skipped, limit respected", () => {
  const lookup = (urn) => (Number(urn) >= 100001 && Number(urn) <= 100009 ? { name: "School " + urn, p: "/school/" + urn + "-x/" } : null);
  const existing = [{ type: "school", id: "100001", name: "School 100001", p: "/school/100001-x/" }, { type: "area", id: "england", name: "England", p: "/" }];
  const r = M.importShortlist(existing, ["100001", 100002, "100002", 100003, " 100004 ", "999999", "abc", null], lookup);
  assert.equal(r.added, 3, "100002, 100003, 100004");
  assert.equal(r.skipped, 1, "100001 already pinned");
  assert.equal(r.unknown, 1, "999999 has no money page");
  assert.deepEqual(r.list.filter((p) => p.type === "school").map((p) => p.id), ["100001", "100002", "100003", "100004"]);
  assert.equal(r.list.filter((p) => p.type === "area").length, 1, "areas kept");
  assert.equal(existing.length, 2, "input not mutated");

  const big = M.importShortlist([], [100001, 100002, 100003, 100004, 100005, 100006, 100007, 100008], lookup);
  assert.equal(big.list.length, 6, "limit of 6 schools");
  assert.equal(big.added, 6);
  assert.equal(big.skipped, 2);

  // A map works as the lookup too.
  const viaMap = M.importShortlist([], [100001], { "100001": { name: "Mapped", p: "/school/100001-mapped/" } });
  assert.equal(viaMap.list[0].name, "Mapped");
});

test("postcodeLookup resolves null without a fetch implementation or network", async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = () => Promise.reject(new Error("offline"));
  try {
    assert.equal(await M.postcodeLookup("E8"), null);
    assert.equal(await M.postcodeLookup(""), null);
  } finally {
    globalThis.fetch = saved;
  }
});

// A SERIES file as series.school_series writes it to /data/sx/<urn>.json (SHARED 'SERIES CONTRACT').
const SERIES = {
  years: ["2022-23", "2023-24", "2024-25"],
  source: { "2022-23": "CFR", "2023-24": "CFR", "2024-25": "AAR" },
  pupils: { "2022-23": 300, "2023-24": 290, "2024-25": 280 },
  m: {
    total_income: { "2022-23": { v: 1800000, pp: 6000, r: 2000000, rpp: 6667 }, "2023-24": { v: 1850000, pp: 6379 }, "2024-25": { v: 1900000, pp: 6786 } },
    grant_funding_government: { "2024-25": { v: 1700000, pp: 6071 } },
    donations_revenue: { "2024-25": { v: 12000, pp: 43 } },
    total_expenditure: { "2022-23": { v: 1790000, pp: 5967 }, "2024-25": { v: 1950000, pp: 6964 } },
    teaching_staff: { "2024-25": { v: 900000, pp: 3214 } },
  },
  gap: {}, pta: {}, flags: { falling_rolls: null, pass_through: null, high_send: null, suspect: { "2024-25": ["donations_revenue"] }, not_reported: {} },
  trust_central_pp: {},
};
const CHECK = "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/100001";

test("seriesDrill builds the shared drill payload from one metric of a SERIES file", () => {
  // Act
  const d = M.seriesDrill(SERIES, "total_income", { year: "2024-25", src: CHECK, file: "/data/sx/100001.json", label: (k) => "L:" + k });
  // Assert
  assert.deepEqual(Object.keys(d).sort(), ["rows", "series", "src", "title", "year"]);
  assert.equal(d.title, "L:total_income");
  assert.equal(d.year, "2024-25");
  assert.equal(d.src, CHECK);
  assert.deepEqual(d.series, [{ y: "2022-23", v: 1800000, pp: 6000 }, { y: "2023-24", v: 1850000, pp: 6379 }, { y: "2024-25", v: 1900000, pp: 6786 }]);
  assert.deepEqual(d.rows.map((r) => [r.key, r.v, r.pp, r.drill]), [
    ["grant_funding_government", 1700000, 6071, "/data/sx/100001.json#m:grant_funding_government"],
    ["donations_revenue", 12000, 43, "/data/sx/100001.json#m:donations_revenue"],
  ]);
  assert.equal(d.rows[1].suspect, true, "flagged values stay marked");
});

test("seriesDrill: missing years fall back to the latest, missing metrics give null, gaps are skipped", () => {
  // Act / Assert
  const spend = M.seriesDrill(SERIES, "total_expenditure", { year: "2023-24" });
  assert.equal(spend.year, "2024-25", "no 2023-24 value, so the latest year with one");
  assert.deepEqual(spend.series.map((p) => p.y), ["2022-23", "2024-25"]);
  assert.deepEqual(spend.rows.map((r) => r.key), ["teaching_staff"]);
  assert.equal(spend.src, null);
  assert.equal(M.seriesDrill(SERIES, "energy"), null);
  assert.equal(M.seriesDrill(null, "total_income"), null);
  assert.equal(M.seriesDrill({ years: "x", m: { a: 1 } }, "a"), null);
  assert.ok(M.SX_REF.test("/data/sx/100001.json#m:total_income"));
  assert.ok(!M.SX_REF.test("/data/sx/../x.json#m:total_income"));
});

test("parseTags and rowShown: OR within a group, AND across groups", () => {
  // Arrange
  const tags = M.parseTags("governance:academy phase:primary  faith:none bad: :x");
  // Act / Assert
  assert.deepEqual(tags, { governance: ["academy"], phase: ["primary"], faith: ["none"] });
  assert.equal(M.rowShown(tags, {}), true);
  assert.equal(M.rowShown(tags, { phase: ["primary", "secondary"] }), true);
  assert.equal(M.rowShown(tags, { phase: ["secondary"] }), false);
  assert.equal(M.rowShown(tags, { phase: ["primary"], governance: ["council-run"] }), false);
  assert.equal(M.rowShown(tags, { phase: [] }), true);
  assert.equal(M.rowShown({}, { phase: ["primary"] }), false);
});

test("pinnedFirst keeps the existing order inside each part and never mutates its input", () => {
  // Arrange
  const rows = ["1", "2", "3", "4"];
  // Act
  const out = M.pinnedFirst(rows, (r) => r, { 3: true, 1: true });
  // Assert
  assert.deepEqual(out, ["1", "3", "2", "4"]);
  assert.deepEqual(rows, ["1", "2", "3", "4"]);
});

// ---------------------------------------------------------------- the same features on a fake DOM
// Elements with attributes, children, bubbling events and the selectors app.js uses (tag, .class, #id,
// [attr], [attr="v"], descendant chains, comma lists). Enough to boot app.js; it holds no app logic.
function simple(node, sel) {
  if (!node.tagName) return false;
  let ok = true;
  sel = sel.replace(/\[([^\]=~^]+)(?:([~^]?=)["']?([^"'\]]*)["']?)?\]/g, (_, name, op, value) => {
    const a = node.getAttribute(name);
    if (a === null || (op === "=" && a !== value) || (op === "~=" && !a.split(/\s+/).includes(value)) || (op === "^=" && !a.startsWith(value))) ok = false;
    return "";
  });
  sel = sel.replace(/\.([\w-]+)/g, (_, c) => { if (!node.classList.contains(c)) ok = false; return ""; });
  sel = sel.replace(/#([\w-]+)/g, (_, id) => { if (node.id !== id) ok = false; return ""; });
  return ok && (!sel || sel === "*" || node.tagName.toLowerCase() === sel.toLowerCase());
}
function matches(node, selector) {
  return selector.split(",").some((part) => {
    const chain = part.trim().split(/\s+(?![^[]*\])/);
    if (!simple(node, chain.pop())) return false;
    let up = node.parentNode;
    while (chain.length) {
      const want = chain.pop();
      while (up && !simple(up, want)) up = up.parentNode;
      if (!up) return false;
      up = up.parentNode;
    }
    return true;
  });
}
class Node {
  constructor(tag, doc, text = "") {
    this.tagName = tag && tag.toUpperCase();
    this.ownerDocument = doc;
    this.parentNode = null;
    this.childNodes = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.style = {};
    this.value = "";
    this._text = text;
  }
  setAttribute(k, v) { this.attributes.set(k, String(v)); }
  getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; }
  hasAttribute(k) { return this.attributes.has(k); }
  removeAttribute(k) { this.attributes.delete(k); }
  get id() { return this.getAttribute("id") || ""; }
  set id(v) { this.setAttribute("id", v); }
  get className() { return this.getAttribute("class") || ""; }
  set className(v) { this.setAttribute("class", v); }
  get hidden() { return this.hasAttribute("hidden"); }
  set hidden(v) { if (v) this.setAttribute("hidden", ""); else this.removeAttribute("hidden"); }
  get href() { return this.getAttribute("href") || ""; }
  set href(v) { this.setAttribute("href", v); }
  set tabIndex(v) { this.setAttribute("tabindex", v); }
  get classList() {
    const n = this;
    const list = () => n.className.split(/\s+/).filter(Boolean);
    return {
      contains: (c) => list().includes(c),
      add: (...c) => { n.className = [...new Set([...list(), ...c])].join(" "); },
      remove: (...c) => { n.className = list().filter((x) => !c.includes(x)).join(" "); },
      toggle: (c, force) => { const on = force ?? !list().includes(c); if (on) n.classList.add(c); else n.classList.remove(c); return on; },
    };
  }
  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  removeChild(child) { this.childNodes.splice(this.childNodes.indexOf(child), 1); child.parentNode = null; return child; }
  get children() { return this.childNodes.filter((c) => c.tagName); }
  get textContent() { return this._text + this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(v) { for (const c of this.childNodes) c.parentNode = null; this.childNodes = []; this._text = String(v ?? ""); }
  matches(sel) { return matches(this, sel); }
  closest(sel) { return this.matches(sel) ? this : (this.parentNode && this.parentNode.closest ? this.parentNode.closest(sel) : null); }
  querySelectorAll(sel) {
    const out = [];
    for (const c of this.children) { if (c.matches(sel)) out.push(c); out.push(...c.querySelectorAll(sel)); }
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  contains(n) { return this === n || this.childNodes.some((c) => c.contains(n)); }
  get offsetParent() { return this.parentNode; }
  getBoundingClientRect() { return { left: 0, top: 0, right: 10, bottom: 10, width: 10, height: 10 }; }
  addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(fn); }
  dispatchEvent(e) {
    e.target ??= this;
    e.preventDefault ??= function () { this.defaultPrevented = true; };
    for (const fn of this.listeners.get(e.type) || []) fn(e);
    if (e.bubbles !== false && this.parentNode) this.parentNode.dispatchEvent(e);
    return !e.defaultPrevented;
  }
  click() { return this.dispatchEvent({ type: "click", bubbles: true }); }
  focus() { this.ownerDocument.activeElement = this; }
  createTBody() { return this.appendChild(this.ownerDocument.createElement("tbody")); }
  insertRow() { return this.appendChild(this.ownerDocument.createElement("tr")); }
  insertCell() { return this.appendChild(this.ownerDocument.createElement("td")); }
  get tBodies() { return this.children.filter((c) => c.tagName === "TBODY"); }
  get rows() { return this.children.filter((c) => c.tagName === "TR"); }
  get cells() { return this.children.filter((c) => c.tagName === "TD" || c.tagName === "TH"); }
}
class Doc extends Node {
  constructor() {
    super(null, null);
    this.ownerDocument = this;
    this.documentElement = this.appendChild(this.createElement("html"));
    this.body = this.documentElement.appendChild(this.createElement("body"));
    this.activeElement = this.body;
  }
  createElement(tag) { return new Node(tag, this); }
  createElementNS(_ns, tag) { return this.createElement(tag); }
  createTextNode(text) { return new Node(null, this, String(text)); }
  getElementById(id) { return this.querySelector("#" + id); }
}
function add(parent, tag, attrs = {}, text = "") {
  const n = parent.ownerDocument.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text) n.textContent = text;
  return parent.appendChild(n);
}
const appSource = readFileSync(join(here, "assets", "app.js"), "utf8");
const glossary = JSON.parse(readFileSync(join(here, "assets", "glossary.json"), "utf8"));
async function settle() { for (let n = 0; n < 40; n++) await Promise.resolve(); }

function boot({ storage = {}, data = {}, setup = () => {} } = {}) {
  // Arrange (shared): a fake page, storage and fetch, then app.js runs against them.
  const document = new Doc();
  const memory = new Map(Object.entries(storage).map(([k, v]) => [k, JSON.stringify(v)]));
  const calls = [];
  const fixtures = { "/assets/glossary.json": glossary, ...data };
  const url = new URL("https://money.schoolsinreach.com/");
  const ctx = vm.createContext({
    document, console, URL, URLSearchParams, location: { href: url.href, search: "", pathname: "/" },
    history: { replaceState() {} },
    localStorage: { getItem: (k) => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, String(v)) },
    setTimeout: () => 0, clearTimeout() {},
    fetch(u) {
      calls.push(String(u));
      const value = fixtures[u];
      return Promise.resolve({ ok: value != null, status: value == null ? 404 : 200, json: () => Promise.resolve(value) });
    },
  });
  ctx.window = ctx;
  ctx.innerWidth = 1000;
  ctx.innerHeight = 800;
  setup(document);
  vm.runInContext(appSource, ctx, { filename: "pipeline/money/assets/app.js" });
  return { document, calls, memory };
}

test("a /data/sx/ drill fetches the SERIES file and shows its trend, breakdown and source", async () => {
  // Arrange
  const h = boot({ data: { "/data/sx/100001.json": SERIES }, setup(doc) {
    add(doc.body, "span", { class: "mf", "data-mf": "total_income", "data-v": "1900000", "data-pp": "6786", "data-year": "2024-25",
                            "data-src": CHECK, "data-drill": "/data/sx/100001.json#m:total_income" }, "£1.9m");
  } });
  // Act
  h.document.querySelector(".mf").click();
  await settle();
  // Assert
  const drill = h.document.querySelector(".drill");
  assert.equal(drill.hidden, false);
  assert.deepEqual(h.calls.filter((u) => u.startsWith("/data/sx/")), ["/data/sx/100001.json"]);
  assert.match(drill.textContent, /Over time/);
  assert.match(drill.textContent, /Breakdown/);
  assert.match(drill.textContent, /figure under review/);
  const nested = drill.querySelectorAll(".mf");
  assert.deepEqual(nested.map((n) => n.getAttribute("data-drill")),
    ["/data/sx/100001.json#m:grant_funding_government", "/data/sx/100001.json#m:donations_revenue"]);
  assert.equal(drill.querySelector("a.check").href, CHECK);
  // Act again: a breakdown line drills into its own series, reusing the cached file.
  nested[0].click();
  await settle();
  assert.match(drill.querySelector("#drill-title").textContent, /government/i);
  assert.equal(h.calls.filter((u) => u.startsWith("/data/sx/")).length, 1);
});

function leagueTable(doc, rows) {
  const filters = add(doc.body, "div", { class: "table-filters", "data-filters": "" });
  for (const f of ["phase:primary", "phase:secondary", "governance:academy"]) add(filters, "button", { type: "button", "data-filter": f, "aria-pressed": "false" }, f);
  const table = add(doc.body, "table", { "data-sortable": "", class: "responsive sortable" });
  const head = add(add(table, "thead"), "tr");
  add(head, "th", {}, "School");
  const body = add(table, "tbody");
  for (const [urn, tags] of rows) {
    const td = add(add(body, "tr"), "td");
    add(td, "span", { "data-tags": tags });
    add(td, "a", { href: `/school/${urn}-x/`, "data-preview": `school:${urn}` }, `School ${urn}`);
  }
  return table;
}
const ROWS_TAGGED = [
  ["100001", "governance:council-run phase:primary"],
  ["100002", "governance:academy phase:secondary"],
  ["100003", "governance:academy phase:primary"],
];
const visible = (doc) => doc.querySelectorAll("tbody tr").filter((r) => !r.hidden).map((r) => r.querySelector("a").textContent);

test("table filters show rows matching any value in a group and every active group", () => {
  // Arrange
  const h = boot({ setup: (doc) => leagueTable(doc, ROWS_TAGGED) });
  const button = (f) => h.document.querySelector(`[data-filter="${f}"]`);
  // Act / Assert: nothing pressed, every row shows.
  assert.deepEqual(visible(h.document), ["School 100001", "School 100002", "School 100003"]);
  button("phase:primary").click();
  assert.equal(button("phase:primary").getAttribute("aria-pressed"), "true");
  assert.deepEqual(visible(h.document), ["School 100001", "School 100003"]);
  button("phase:secondary").click();
  assert.deepEqual(visible(h.document), ["School 100001", "School 100002", "School 100003"]);
  button("governance:academy").click();
  assert.deepEqual(visible(h.document), ["School 100002", "School 100003"]);
  assert.match(h.document.querySelector(".filter-count").textContent, /Showing 2 of 3/);
  for (const f of ["phase:primary", "phase:secondary", "governance:academy"]) button(f).click();
  assert.deepEqual(visible(h.document), ["School 100001", "School 100002", "School 100003"]);
});

test("pinned schools' rows move to the top of every sortable table on load", () => {
  // Arrange / Act
  const h = boot({ storage: { moneyPinned: [{ type: "school", id: "100003", name: "School 100003", p: "/school/100003-x/" }] },
                   setup: (doc) => { leagueTable(doc, ROWS_TAGGED); leagueTable(doc, ROWS_TAGGED.slice().reverse()); } });
  // Assert
  for (const table of h.document.querySelectorAll("table[data-sortable]")) {
    const rows = table.tBodies[0].rows;
    assert.equal(rows[0].querySelector("a").textContent, "School 100003");
    assert.ok(rows[0].classList.contains("pinned"));
    assert.equal(rows.filter((r) => r.classList.contains("pinned")).length, 1);
  }
  assert.deepEqual(h.document.querySelectorAll("table")[0].tBodies[0].rows.map((r) => r.querySelector("a").textContent),
    ["School 100003", "School 100001", "School 100002"]);
});
