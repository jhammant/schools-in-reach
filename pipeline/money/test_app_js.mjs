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
                   "seriesDrill", "parseTags", "rowShown", "pinnedFirst", "READERS", "READER_TITLES", "pageOf", "audienceLinks"]) {
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

test("rankSearch: exact name > prefix > word match > substring, type order school, council, constituency, trust", () => {
  const names = M.rankSearch(ROWS, "hackney").map((r) => r.id);
  // The council named exactly that first, then prefix hits (school before constituency before trust), then word/substring hits.
  assert.deepEqual(names.slice(0, 4), ["204", "100002", "hackney-north", "hackney-learning-trust"]);
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
  insertBefore(child, before) {
    if (!before) return this.appendChild(child);
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.splice(this.childNodes.indexOf(before), 0, child);
    return child;
  }
  get nextSibling() { const s = this.parentNode && this.parentNode.childNodes; return s ? s[s.indexOf(this) + 1] || null : null; }
  get firstChild() { return this.childNodes[0] || null; }
  get children() { return this.childNodes.filter((c) => c.tagName); }
  get textContent() { return this._text + this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(v) {
    // Like a browser: an element's text becomes one text child (so moving its children moves the text too).
    for (const c of this.childNodes) c.parentNode = null;
    this.childNodes = [];
    if (!this.tagName) { this._text = String(v ?? ""); return; }
    this._text = "";
    if (String(v ?? "")) this.appendChild(new Node(null, this.ownerDocument, String(v)));
  }
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
  scrollIntoView() {}
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
  createTHead() { return this.insertBefore(this.ownerDocument.createElement("thead"), this.firstChild); }
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

function boot({ storage = {}, data = {}, setup = () => {}, path = "/", globals = {} } = {}) {
  // Arrange (shared): a fake page at path, storage and fetch, then app.js runs against them. Timers wait for
  // flushTimers(); fixtures can be changed after boot (a failed request, then a good one).
  const document = new Doc();
  const memory = new Map(Object.entries(storage).map(([k, v]) => [k, JSON.stringify(v)]));
  const calls = [], timers = [], replaced = [], urls = [];
  const fixtures = { "/assets/glossary.json": glossary, ...data };
  const url = new URL(path, "https://money.schoolsinreach.com/");
  const location = { href: url.href, search: url.search, pathname: url.pathname, replace: (u) => replaced.push(u) };
  const ctx = vm.createContext({
    document, console, URL, URLSearchParams, location, Node, ...globals,
    history: { replaceState(_state, _title, path) { urls.push(path); const next = new URL(path, url); location.search = next.search; } },
    localStorage: { getItem: (k) => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, String(v)) },
    setTimeout: (fn) => timers.push(fn), clearTimeout() {},
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
  return { document, calls, memory, fixtures, location, replaced, urls, flushTimers() { timers.splice(0).forEach((fn) => fn()); } };
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

test("nearestRows sorts a district's schools by distance from the exact postcode and says how far", () => {
  // Arrange: N16's centre, and two schools; the second is nearer the exact postcode
  const doc = { district: "N16", lat: 51.5615, lon: -0.0760, schools: [
    { id: "1", name: "Centre School", lat: 51.5615, lon: -0.0760, p: "/school/1-centre-school/", sub: "London N16 1AA", status: "healthy" },
    { id: "2", name: "North School", lat: 51.5700, lon: -0.0760, p: "/school/2-north-school/", sub: "London N16 2BB", status: null }] };
  // Act
  const fromCentre = M.nearestRows(doc, null, 10);
  const fromNorth = M.nearestRows(doc, { lat: 51.5701, lon: -0.0760 }, 10);
  // Assert
  assert.deepEqual(fromCentre.map((r) => r.id), ["1", "2"]);
  assert.deepEqual(fromNorth.map((r) => r.id), ["2", "1"]);
  assert.match(fromNorth[0].sub, /^under 0\.1 miles · London N16 2BB$/);
  assert.match(fromNorth[1].sub, /^0\.6 miles · /);
  assert.equal(M.nearestRows(null, null, 10).length, 0);
});

test("milesBetween is a great-circle distance in miles", () => {
  // Act: one degree of latitude
  const d = M.milesBetween({ lat: 51, lon: 0 }, { lat: 52, lon: 0 });
  // Assert
  assert.ok(Math.abs(d - 69.09) < 0.1, String(d));
});

// ---------------------------------------------------------------- readers: "Show me what matters to a"
const SCHOOL_PAGE = { kind: "school", path: "/school/100001-example-primary/", urn: "100001",
                      sections: ["status", "funding", "reserve", "income", "spending", "ptfa", "split", "questions", "check"] };
const VIDEO = "/school/100001-example-primary/video/";
const hrefs = (reader, page) => M.audienceLinks(reader, page).map((l) => l.href);
const area = (path, extra = {}) => ({ ...M.pageOf(path), sections: ["schools"], ...extra });

test("pageOf tells a school page, an area page and anything else apart by its path", () => {
  // Act / Assert
  assert.deepEqual(M.pageOf("/school/100001-example-primary/"), { kind: "school", path: "/school/100001-example-primary/", urn: "100001" });
  assert.equal(M.pageOf("/council/hackney/").kind, "council");
  assert.equal(M.pageOf("/council/hackney/2/").kind, "council");
  assert.equal(M.pageOf("/constituency/hackney-north-and-stoke-newington/").kind, "constituency");
  assert.equal(M.pageOf("/trust/good-trust/").kind, "trust");
  for (const p of ["/", "/council/", "/trust/", "/school/100001-example-primary/video/", "/guides/governors/", "/deck/", undefined]) {
    assert.equal(M.pageOf(p).kind, "other", String(p));
  }
});

test("audienceLinks on a school page points each reader at that school's own pages and sections", () => {
  // Act / Assert
  assert.deepEqual(hrefs("parent", SCHOOL_PAGE), ["#status", "#questions", VIDEO, "#ptfa", "#split"]);
  assert.deepEqual(hrefs("governor", SCHOOL_PAGE), ["/deck/?urn=100001&view=governors", "#spending", "#questions", "/tools/budget-check/", "#reserve"]);
  assert.deepEqual(hrefs("ptfa", SCHOOL_PAGE), ["/deck/?urn=100001&view=ptfa", VIDEO + "?mode=ptfa", "#ptfa", "/tools/pta-planner/", "/guides/ptfa/"]);
  assert.deepEqual(hrefs("leader", SCHOOL_PAGE), ["/deck/?urn=100001&view=review", "#spending", "/tools/", "/compare/", "#funding"]);
  assert.deepEqual(hrefs("pupil", SCHOOL_PAGE), [VIDEO, "#split", "/guides/pupils/", "#income", "/map/"]);
  assert.deepEqual(M.audienceLinks("pupil", SCHOOL_PAGE)[1], { text: "How my school's money is split", href: "#split" });
  assert.equal(M.audienceLinks("governor", SCHOOL_PAGE)[0].text, "Governors' presentation");
  assert.equal(M.READER_TITLES.governor, "For governors");
});

test("audienceLinks uses #nearby for governors and leaders once the page has it", () => {
  // Arrange
  const withNearby = { ...SCHOOL_PAGE, sections: [...SCHOOL_PAGE.sections, "nearby"] };
  // Act / Assert
  assert.deepEqual(hrefs("governor", withNearby).slice(0, 3), ["/deck/?urn=100001&view=governors", "#spending", "#nearby"]);
  assert.deepEqual(hrefs("leader", withNearby).slice(0, 3), ["/deck/?urn=100001&view=review", "#spending", "#nearby"]);
});

test("audienceLinks never links a missing section, a video that was not made or the page itself", () => {
  // Arrange: a school page without a full-year return has no sections, video or presentation
  const plain = { ...SCHOOL_PAGE, sections: [] };
  for (const reader of M.READERS) {
    // Act
    const hs = hrefs(reader, plain);
    // Assert
    assert.ok(hs.length >= 3, reader);
    assert.ok(hs.every((h) => !h.startsWith("#") && !h.startsWith("/school/") && !h.startsWith("/deck/")), `${reader}: ${hs}`);
  }
  assert.ok(!hrefs("parent", { ...SCHOOL_PAGE, sections: ["status"] }).includes("#questions"));
  assert.ok(!hrefs("governor", M.pageOf("/guides/governors/")).includes("/guides/governors/"));
  assert.ok(!hrefs("parent", M.pageOf("/")).includes("/"));
  // A path that is not a real school path gets no school links at all.
  const forged = { kind: "school", path: '/school/1-x/"><b>', urn: "1", sections: ["status"] };
  assert.ok(hrefs("parent", forged).every((h) => !h.includes("<") && !h.startsWith("/school/")));
  assert.deepEqual(M.audienceLinks("teacher", SCHOOL_PAGE), []);
  assert.deepEqual(M.audienceLinks(null, SCHOOL_PAGE), []);
});

test("audienceLinks on area pages: the area's presentation, its table and the map", () => {
  // Arrange
  const council = area("/council/hackney/", { areaId: "council-204" });
  const constituency = area("/constituency/hackney-north/", { areaId: "constituency-hackney-north" });
  // Act / Assert
  assert.deepEqual(hrefs("governor", council).slice(0, 3), ["/deck/?area=council-204", "#schools", "/map/"]);
  assert.deepEqual(hrefs("parent", council).slice(0, 3), ["#schools", "/map/", "/deck/?area=council-204"]);
  assert.ok(hrefs("leader", constituency).includes("/map/?g=constituency"));
  assert.equal(M.audienceLinks("governor", council)[0].text, "Present this area");
  // Trusts have no area document, and a later page of a table has no pin: no presentation for either.
  for (const page of [area("/trust/good-trust/", { areaId: "trust-good-trust" }), area("/council/hackney/2/")]) {
    assert.ok(hrefs("governor", page).every((h) => !h.startsWith("/deck/")), page.path);
    assert.ok(hrefs("governor", page).includes("#schools"), page.path);
  }
});

test("every reader gets three to five different links on every kind of page", () => {
  // Arrange
  const pages = [SCHOOL_PAGE, { ...SCHOOL_PAGE, sections: [] }, area("/council/hackney/", { areaId: "council-204" }),
                 area("/constituency/x/", { areaId: "constituency-x" }), area("/trust/t/"), M.pageOf("/"),
                 M.pageOf("/guides/parents/"), M.pageOf("/tools/"), M.pageOf("/map/"), M.pageOf("/video/")];
  for (const page of pages) {
    for (const reader of M.READERS) {
      // Act
      const links = M.audienceLinks(reader, page);
      // Assert
      assert.ok(links.length >= 3 && links.length <= 5, `${reader} on ${page.path}: ${links.length}`);
      assert.equal(new Set(links.map((l) => l.href)).size, links.length, `${reader} on ${page.path}`);
      assert.ok(links.every((l) => l.text && l.text.length <= 30), `${reader} on ${page.path}`);
    }
  }
});

function readerPage(doc, { slot = true, picker = true } = {}) {
  // The home picker and panel slot, or the strip alone on another page.
  const main = add(doc.body, "main", { id: "main" });
  if (picker) {
    const fieldset = add(main, "fieldset", { class: "audience" });
    add(fieldset, "legend", {}, "Show me what matters to a");
    const chips = add(fieldset, "span", { class: "aud-chips" });
    for (const r of M.READERS) add(chips, "button", { type: "button", "data-audience": r, "aria-pressed": "false" }, r);
    add(fieldset, "button", { type: "button", class: "aud-clear" }, "Clear");
  }
  if (slot) add(picker ? main : doc.body, "div", { id: "for-you" });
  return main;
}
const schoolPin = JSON.stringify({ type: "school", id: "100001", name: "Example Primary", p: "/school/100001-example-primary/" });

test("choosing a reader presses its chip, saves it and shows that reader's quick links", () => {
  // Arrange
  const h = boot({ path: "/school/100001-example-primary/", setup(doc) {
    const main = readerPage(doc);
    add(add(main, "section", { id: "status", class: "sp-sec" }), "button", { type: "button", class: "pin", "data-pin": schoolPin, "aria-pressed": "false" });
    for (const id of ["spending", "questions", "reserve"]) add(main, "section", { id, class: "sp-sec" });
  } });
  const html = h.document.documentElement, panel = h.document.getElementById("for-you");
  const chip = (r) => h.document.querySelector(`button[data-audience="${r}"]`);
  assert.equal(panel.children.length, 0);
  assert.equal(html.getAttribute("data-reader"), null);
  assert.ok(M.READERS.every((r) => chip(r).getAttribute("aria-pressed") === "false"));
  // Act
  chip("governor").click();
  // Assert
  assert.deepEqual(M.READERS.map((r) => chip(r).getAttribute("aria-pressed")), ["false", "true", "false", "false", "false"]);
  assert.equal(html.getAttribute("data-reader"), "governor");
  assert.equal(html.getAttribute("data-audience"), "governor");
  assert.equal(h.memory.get("moneyAudience"), '"governor"');
  assert.equal(panel.querySelector(".fy-title").textContent, "For governors");
  assert.equal(panel.querySelector("nav").getAttribute("aria-labelledby"), "fy-title");
  assert.equal(panel.querySelector(".fy-sub").textContent, "Quick links for Example Primary");
  assert.deepEqual(panel.querySelectorAll("a").map((a) => a.getAttribute("href")),
    ["/deck/?urn=100001&view=governors", "#spending", "#questions", "/tools/budget-check/", "#reserve"]);
  assert.equal(h.document.querySelector('[role="status"]').textContent, "For governors: 5 quick links below");
  // Act: another chip, then the chosen chip again
  chip("pupil").click();
  assert.equal(panel.querySelector(".fy-title").textContent, "For pupils");
  assert.equal(panel.querySelectorAll("nav").length, 1);
  chip("pupil").click();
  // Assert: cleared
  assert.ok(M.READERS.every((r) => chip(r).getAttribute("aria-pressed") === "false"));
  assert.equal(panel.children.length, 0);
  assert.equal(html.getAttribute("data-reader"), null);
  assert.equal(html.getAttribute("data-audience"), "parent");
  assert.equal(h.memory.get("moneyAudience"), "null");
});

test("a saved reader shows on load, and Clear empties the panel and keeps focus in the picker", () => {
  // Arrange / Act
  const h = boot({ storage: { moneyAudience: "ptfa" }, setup: (doc) => readerPage(doc) });
  const panel = h.document.getElementById("for-you");
  // Assert
  assert.equal(h.document.querySelector('button[data-audience="ptfa"]').getAttribute("aria-pressed"), "true");
  assert.equal(panel.querySelector(".fy-title").textContent, "For PTFA committees");
  assert.equal(panel.querySelector(".fy-sub").textContent, "Quick links");
  assert.deepEqual(panel.querySelectorAll("a").map((a) => a.getAttribute("href")),
    ["/guides/ptfa/", "/tools/pta-planner/", "/ptfa/", "/video/"]);
  assert.equal(h.document.querySelector('[role="status"]').textContent, "");  // nothing announced on load
  // Act
  h.document.querySelector("button.aud-clear").click();
  // Assert
  assert.equal(panel.children.length, 0);
  assert.equal(h.document.querySelectorAll('button[data-audience][aria-pressed="true"]').length, 0);
  assert.equal(h.document.activeElement, h.document.querySelector('button[data-audience="parent"]'));
  assert.equal(h.document.querySelector('[role="status"]').textContent, "Choice cleared");
  assert.equal(h.memory.get("moneyAudience"), "null");
});

test("an unknown saved reader is ignored, and a page without the panel slot still presses chips", () => {
  // Arrange / Act
  const h = boot({ storage: { moneyAudience: "<b>teacher</b>" }, setup: (doc) => readerPage(doc, { slot: false }) });
  // Assert
  assert.equal(h.document.documentElement.getAttribute("data-reader"), null);
  h.document.querySelector('button[data-audience="leader"]').click();
  assert.equal(h.document.querySelector('button[data-audience="leader"]').getAttribute("aria-pressed"), "true");
  assert.equal(h.document.querySelector('[role="status"]').textContent, "For school leaders chosen");
});

test("on a council page the schools table gets an id and the panel links the area's presentation", () => {
  // Arrange / Act
  const h = boot({ storage: { moneyAudience: "governor" }, path: "/council/hackney/", setup(doc) {
    const main = readerPage(doc);
    add(main, "button", { type: "button", class: "pin", "aria-pressed": "false",
                          "data-pin": JSON.stringify({ type: "area", id: "council-204", name: "Hackney", p: "/council/hackney/" }) });
    add(main, "table", { "data-sortable": "" });
  } });
  // Assert
  assert.equal(h.document.querySelector("table").id, "schools");
  assert.equal(h.document.querySelector(".fy-sub").textContent, "Quick links for Hackney");
  assert.deepEqual(h.document.querySelectorAll("#for-you a").map((a) => a.getAttribute("href")),
    ["/deck/?area=council-204", "#schools", "/map/", "/guides/governors/", "/tools/budget-check/"]);
});

// ---------------------------------------------------------------- forgiving search
const INDEX = [
  ...ROWS,
  { t: "school", id: "100005", name: "St Mary's CofE Primary School", sub: "Islington", status: "healthy", p: "/school/100005-st-mary-s/" },
  { t: "school", id: "100006", name: "Saint Joseph's Catholic Primary", sub: "Camden", status: null, p: "/school/100006-saint-joseph-s/" },
  { t: "council", id: "301", name: "Barking and Dagenham", sub: "London", status: null, p: "/council/barking-and-dagenham/" },
  { t: "school", id: "140001", name: "Mossbourne Community Academy", sub: "London, Hackney", status: "reserve_held_by_trust", p: "/school/140001-mossbourne/" },
];
const ids = (m) => m.rows.map((r) => r.id);

test("fold ignores case, accents, apostrophes and punctuation, and reads & as and", () => {
  assert.equal(M.fold("St. Mary's  C of E"), "st marys cofe");
  assert.equal(M.fold("Barking & Dagenham"), "barking and dagenham");
  assert.equal(M.fold("Stoke-on-Trent"), "stoke on trent");
  assert.equal(M.fold("Ecole Française"), "ecole francaise");
  assert.equal(M.fold(null), "");
});

test("editDistance counts one or two typos, swapped letters as one, and stops past its limit", () => {
  assert.equal(M.editDistance("willam", "william", 1), 1);
  assert.equal(M.editDistance("paten", "patten", 1), 1);
  assert.equal(M.editDistance("patetn", "patten", 1), 1, "a swapped pair is one edit");
  assert.equal(M.editDistance("pattern", "patten", 2), 1);
  assert.equal(M.editDistance("hackney", "hackney", 0), 0);
  assert.equal(M.editDistance("zzzzzz", "patten", 2), 3, "max + 1 once it must be more than max");
});

test("a typo or two still finds the school, flagged fuzzy for a 'Did you mean' line", () => {
  for (const q of ["Willam Paten", "wiliam paten", "william pattern", "WILLIAM  PATEN"]) {
    // Act
    const m = M.searchMatches(INDEX, q, 8);
    // Assert
    assert.equal(m.fuzzy, true, q);
    assert.equal(m.rows[0].id, "100003", q);
  }
  const exact = M.searchMatches(INDEX, "william patten", 8);
  assert.equal(exact.fuzzy, false);
  assert.deepEqual(ids(exact), ["100003"]);
  assert.deepEqual(M.searchMatches(INDEX, "zzz", 8), { rows: [], fuzzy: false, urn: false }, "three letters allow no typo");
  assert.deepEqual(M.searchMatches(INDEX, "qqqqqqqq", 8).rows, []);
});

test("a name with its place, Saint for St, missing apostrophes and & all match", () => {
  assert.deepEqual(ids(M.searchMatches(INDEX, "william patten hackney", 8)), ["100003"]);
  assert.equal(M.searchMatches(INDEX, "saint marys", 8).rows[0].id, "100005");
  assert.equal(M.searchMatches(INDEX, "st. mary's c of e", 8).rows[0].id, "100005");
  assert.equal(M.searchMatches(INDEX, "st josephs", 8).rows[0].id, "100006");
  assert.equal(M.searchMatches(INDEX, "barking & dagenham", 8).rows[0].id, "301");
});

test("digits that are a URN or a council code go straight to it", () => {
  const m = M.searchMatches(INDEX, " 100003 ", 8);
  assert.equal(m.urn, true);
  assert.equal(m.rows[0].id, "100003");
  assert.equal(M.searchMatches(INDEX, "204", 8).rows[0].id, "204");
  assert.deepEqual(M.searchMatches(INDEX, "999999", 8).rows, [], "an unknown URN is not fuzzed into another school");
});

test("area words find the council: 'schools in Hackney', 'Hackney council', 'London Borough of Hackney'", () => {
  for (const q of ["schools in Hackney", "Hackney council", "London Borough of Hackney", "primary schools in hackney"]) {
    const m = M.searchMatches(INDEX, q, 8);
    assert.equal(m.rows[0].id, "204", q);
    assert.ok(ids(m).includes("hackney-north"), q);
    assert.equal(m.fuzzy, false, q);
  }
});

test("area words with a typo in the place still find the council, flagged fuzzy", () => {
  for (const q of ["Hakney council", "schools in Hacnkey"]) {
    // Act
    const m = M.searchMatches(INDEX, q, 8);
    // Assert
    assert.equal(m.rows[0].id, "204", q);
    assert.equal(m.fuzzy, true, q);
  }
});

test("opts.types keeps one kind of row, and limit is respected", () => {
  assert.deepEqual(M.searchMatches(INDEX, "hackney", 8, { types: ["school"] }).rows.map((r) => r.t).filter((t) => t !== "school"), []);
  assert.equal(M.rankSearch(INDEX, "school", 2).length, 2);
});

test("a 27,000-entry index answers exact and fuzzy queries quickly, normalising each row once", () => {
  // Arrange
  const words = ["Oak", "Ash", "Elm", "Park", "Hill", "Green", "Brook", "Field", "Saint", "Mary's", "Church", "Valley"];
  const big = [];
  for (let i = 0; i < 27000; i++) {
    big.push({ t: i % 50 ? "school" : "council", id: String(100000 + i), name: `${words[i % 12]} ${words[(i * 7) % 12]} ${words[(i * 5) % 11]} Primary School ${i}`,
               sub: `Town ${i % 300}, County ${i % 40}`, p: `/school/${100000 + i}-x/` });
  }
  big.push({ t: "school", id: "130932", name: "William Patten Primary School", sub: "London, Hackney", p: "/school/130932-william-patten-primary-school/" });
  M.searchMatches(big, "warm up", 8);
  // Act
  const t0 = performance.now();
  const exact = M.searchMatches(big, "william patten", 8);
  const fuzzy = M.searchMatches(big, "willam paten", 8);
  const elapsed = performance.now() - t0;
  // Assert
  assert.equal(exact.rows[0].id, "130932");
  assert.equal(fuzzy.rows[0].id, "130932");
  assert.ok(elapsed < 1500, `two searches took ${elapsed.toFixed(0)}ms`);
});

function searchBox(doc) {
  const form = add(doc.body, "form", { class: "search", role: "search", action: "/search/" });
  add(form, "input", { id: "q", type: "search" });
}
function typeInto(h, value) {
  const q = h.document.getElementById("q");
  q.value = value;
  q.dispatchEvent({ type: "input" });
  h.flushTimers();
  return q;
}
const options = (doc) => doc.querySelectorAll('[role="option"]').map((o) => o.querySelector(".name").textContent);

test("the search box is a combobox; a typo shows 'Did you mean' and the status says it once", async () => {
  // Arrange
  const h = boot({ data: { "/data/search.json": INDEX }, setup: searchBox });
  // Act
  const q = typeInto(h, "Willam Paten");
  await settle();
  // Assert
  assert.equal(q.getAttribute("role"), "combobox");
  assert.equal(q.getAttribute("aria-expanded"), "true");
  assert.deepEqual(options(h.document), ["William Patten Primary School"]);
  const note = h.document.querySelector("#q-list .note");
  assert.match(note.textContent, /Did you mean William Patten Primary School\?/);
  assert.equal(note.getAttribute("aria-hidden"), "true");
  assert.match(h.document.querySelector('form [role="status"]').textContent, /Did you mean William Patten Primary School\?/);
});

test("a held-by-the-trust school shows its own badge, icon and words", async () => {
  // Arrange
  const h = boot({ data: { "/data/search.json": INDEX }, setup: searchBox });
  // Act
  typeInto(h, "mossbourne");
  await settle();
  // Assert
  const badge = h.document.querySelector("#q-list .badge");
  assert.ok(badge.classList.contains("s-reserve_held_by_trust"));
  assert.equal(badge.textContent, "◇ Reserve held by the trust");
});

test("a failed index request says search is unavailable, offers browsing, and the next search tries again", async () => {
  // Arrange: the index 404s on the first request
  const h = boot({ setup: searchBox });
  // Act
  typeInto(h, "patten");
  await settle();
  // Assert
  assert.match(h.document.querySelector("#q-list .note").textContent, /Search is unavailable just now/);
  assert.deepEqual(h.document.querySelectorAll('[role="option"]').map((o) => o.querySelector(".name").textContent),
    ["Councils and regions", "Schools on the map", "Academy trusts"]);
  // Act again: the index is back
  h.fixtures["/data/search.json"] = INDEX;
  typeInto(h, "patten ");
  await settle();
  // Assert
  assert.equal(h.calls.filter((u) => u === "/data/search.json").length, 2);
  assert.deepEqual(options(h.document), ["William Patten Primary School"]);
});

test("Enter on a full URN goes straight to that school", async () => {
  // Arrange
  const h = boot({ data: { "/data/search.json": INDEX }, setup: searchBox });
  const q = typeInto(h, "100003");
  await settle();
  // Act
  q.dispatchEvent({ type: "keydown", key: "Enter" });
  // Assert
  assert.equal(h.location.href, "/school/100003-william-patten-primary-school/");
  // Act again: a postcode typed after it never inherits the URN's shortcut
  h.location.href = "/";
  typeInto(h, "N16");
  await settle();
  q.dispatchEvent({ type: "keydown", key: "Enter" });
  assert.equal(h.location.href, "/");
});

test("typing a full postcode reads local district and display data; nothing goes to postcodes.io", async () => {
  // Arrange
  const n16 = { district: "N16", lat: 51.56, lon: -0.075, schools: [{ id: "100003", name: "William Patten Primary School", lat: 51.5618, lon: -0.075, p: "/school/100003-x/" }] };
  const h = boot({ data: { "/data/postcodes/N16.json": n16 }, setup: searchBox, globals: {} });
  // Act
  typeInto(h, "N16 0NX");
  await settle();
  // Assert
  assert.deepEqual(h.calls.filter((u) => !u.startsWith("/assets/")), ["/data/postcodes/N16.json", "/data/search.json", "/data/fundraising.json"]);
  assert.deepEqual(options(h.document), ["William Patten Primary School"]);
});

test("/search/ with a typo lists close matches under 'Did you mean' and does not jump; a URN does", async () => {
  // Arrange / Act
  const setup = (doc) => { const main = add(doc.body, "main", { id: "main" }); add(main, "h1", {}, "Search"); };
  const typo = boot({ path: "/search/?q=Willam+Paten", data: { "/data/search.json": INDEX }, setup });
  const urn = boot({ path: "/search/?q=100003", data: { "/data/search.json": INDEX }, setup });
  await settle();
  // Assert
  const box = typo.document.querySelector(".search-results");
  assert.match(box.querySelector("h2").textContent, /Close matches for “Willam Paten”/);
  assert.equal(box.querySelector(".dym a").getAttribute("href"), "/school/100003-william-patten-primary-school/");
  assert.match(box.querySelector(".dym").textContent, /^No exact matches\. Did you mean William Patten Primary School\?$/);
  assert.deepEqual(typo.replaced, []);
  assert.deepEqual(urn.replaced, ["/school/100003-william-patten-primary-school/"]);
});

test("/search/ when the index fails: an unavailable state with browse links and a working Try again", async () => {
  // Arrange
  const h = boot({ path: "/search/?q=patten", setup: (doc) => { add(add(doc.body, "main", { id: "main" }), "h1", {}, "Search"); } });
  await settle();
  const box = h.document.querySelector(".search-results");
  // Assert
  assert.equal(box.querySelector("h2").textContent, "Search is unavailable just now");
  assert.deepEqual(box.querySelectorAll(".browse a").map((a) => a.getAttribute("href")), ["/areas/", "/map/", "/trust/"]);
  // Act
  h.fixtures["/data/search.json"] = INDEX;
  box.querySelector("button").click();
  await settle();
  // Assert
  assert.match(box.querySelector("h2").textContent, /Results for “patten”/);
});

test("an unusable index answer (an empty list) is unavailable too, and Try again fetches it afresh", async () => {
  // Arrange: the server answers 200 with an empty list, then recovers
  const h = boot({ path: "/search/?q=patten", data: { "/data/search.json": [] },
    setup: (doc) => { add(add(doc.body, "main", { id: "main" }), "h1", {}, "Search"); } });
  await settle();
  const box = h.document.querySelector(".search-results");
  assert.equal(box.querySelector("h2").textContent, "Search is unavailable just now");
  h.fixtures["/data/search.json"] = INDEX;
  // Act
  box.querySelector("button").click();
  await settle();
  // Assert
  assert.equal(h.calls.filter((u) => u === "/data/search.json").length, 2);
  assert.match(box.querySelector("h2").textContent, /Results for “patten”/);
});

test("importing a saved list while the index fails says so, keeps the offer, and a second try pins", async () => {
  // Arrange: a saved shortlist; the index 404s on the first request
  const h = boot({ storage: { shortlist: ["100003"] }, setup: (doc) => add(doc.body, "main", { id: "main" }) });
  const importButton = () => h.document.querySelector(".pin-import button");
  // Act
  importButton().click();
  await settle();
  // Assert
  assert.match(h.document.querySelector(".pinbar .msg").textContent, /didn't load, so nothing was added/);
  assert.equal(h.document.querySelector(".pin-import").hidden, false);
  assert.deepEqual(JSON.parse(h.memory.get("moneyPinned")), []);
  // Act again: the index is back
  h.fixtures["/data/search.json"] = INDEX;
  importButton().click();
  await settle();
  // Assert
  assert.match(h.document.querySelector(".pinbar .msg").textContent, /Added 1 from your shortlist/);
});

// ---------------------------------------------------------------- phone menu
test("the Menu button opens and closes the nav; Escape closes it and puts focus back on the button", () => {
  // Arrange
  const h = boot({ setup(doc) {
    const wrap = add(add(doc.body, "header", { class: "top" }), "div", { class: "wrap" });
    add(wrap, "button", { type: "button", class: "menu-toggle", "aria-expanded": "false", "aria-controls": "main-nav" }, "Menu");
    add(add(wrap, "nav", { class: "main-nav", id: "main-nav" }), "a", { href: "/map/" }, "Map");
  } });
  const button = h.document.querySelector(".menu-toggle"), link = h.document.querySelector("#main-nav a");
  // Act / Assert
  button.click();
  assert.equal(button.getAttribute("aria-expanded"), "true");
  link.focus();
  h.document.dispatchEvent({ type: "keydown", key: "Escape" });
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(h.document.activeElement, button);
  button.click();
  button.click();
  assert.equal(button.getAttribute("aria-expanded"), "false");
});

// ---------------------------------------------------------------- sortable tables
function sortable(doc, cls = "responsive sortable") {
  const table = add(doc.body, "table", { "data-sortable": "", class: cls });
  const head = add(add(table, "thead"), "tr");
  for (const text of ["School", "Reserve"]) add(head, "th", { scope: "col" }, text);
  const body = add(table, "tbody");
  for (const [name, v] of [["Beta", 300], ["Alpha", -50], ["Gamma", 120]]) {
    const tr = add(body, "tr");
    add(tr, "td", {}, name);
    add(tr, "td", { "data-sort": String(v) }, String(v));
  }
  return table;
}
const order = (t) => t.tBodies[0].rows.map((r) => r.cells[0].textContent);

test("sortable headers become native buttons with a plain label copy, and no th is a tab stop", () => {
  // Arrange / Act
  const h = boot({ setup: (doc) => sortable(doc) });
  const ths = h.document.querySelectorAll("thead th");
  // Assert
  for (const th of ths) {
    assert.equal(th.getAttribute("tabindex"), null);
    assert.equal(th.querySelector("button.sort").type, "button");
    assert.equal(th.querySelector(".th-label").textContent, th.querySelector("button.sort").textContent);
  }
  // Act: the header button sorts ascending, then descending, and tells the phone controls
  ths[1].querySelector("button.sort").click();
  const t = h.document.querySelector("table");
  assert.deepEqual(order(t), ["Alpha", "Gamma", "Beta"]);
  assert.equal(ths[1].getAttribute("aria-sort"), "ascending");
  ths[1].querySelector("button.sort").click();
  assert.deepEqual(order(t), ["Beta", "Gamma", "Alpha"]);
  const controls = h.document.querySelector(".sort-controls");
  assert.equal(controls.querySelector("select").value, "1");
  assert.equal(controls.querySelector(".sort-dir").textContent, "Descending");
  assert.equal(controls.querySelector(".sort-dir").getAttribute("aria-label"), "Direction: Descending. Change to ascending");
  assert.match(controls.querySelector('[role="status"]').textContent, /Sorted by Reserve, descending/);
});

test("the phone controls: a labelled Sort by select and a direction button, before a responsive table", () => {
  // Arrange
  const h = boot({ setup: (doc) => { sortable(doc); sortable(doc, "mini"); } });
  const [controls, plain] = h.document.querySelectorAll(".sort-controls");
  const select = controls.querySelector("select"), label = controls.querySelector("label");
  // Assert
  assert.ok(controls.classList.contains("for-responsive"));
  assert.ok(!plain.classList.contains("for-responsive"), "only a table whose header row is clipped on a phone needs them");
  assert.equal(label.getAttribute("for"), select.id);
  assert.equal(label.textContent, "Sort by");
  assert.deepEqual(select.querySelectorAll("option").map((o) => o.textContent), ["Table order", "School", "Reserve"]);
  assert.equal(controls.nextSibling.tagName, "TABLE");
  // Act
  select.value = "0";
  select.dispatchEvent({ type: "change" });
  const t = h.document.querySelectorAll("table")[0];
  assert.deepEqual(order(t), ["Alpha", "Beta", "Gamma"]);
  controls.querySelector(".sort-dir").click();
  assert.deepEqual(order(t), ["Gamma", "Beta", "Alpha"]);
  select.value = "";
  select.dispatchEvent({ type: "change" });
  assert.deepEqual(order(t), ["Beta", "Alpha", "Gamma"], "Table order puts the rows back");
});

test("a header a page script rewrites gets its button back", () => {
  // Arrange: a MutationObserver stub the test can fire
  const observers = [];
  class MutationObserver { constructor(fn) { this.fn = fn; observers.push(this); } observe() {} }
  const h = boot({ setup: (doc) => sortable(doc), globals: { MutationObserver } });
  const th = h.document.querySelectorAll("thead th")[1];
  // Act: the map rewrites its measure column's header
  th.textContent = "Reserve per pupil, 2024-25";
  observers.forEach((o) => o.fn([]));
  // Assert
  assert.equal(th.querySelector("button.sort").textContent, "Reserve per pupil, 2024-25");
  assert.equal(h.document.querySelector(".sort-controls select").querySelectorAll("option")[2].textContent, "Reserve per pupil, 2024-25");
});

// ---------------------------------------------------------------- compare
const CMP_SCHOOL = {
  urn: "100003", name: "William Patten Primary School", path: "/school/100003-william-patten-primary-school/", status: "in_deficit", year: "2025-26",
  pupils: 432.5, income: 3927968, income_pp: 9082, spend: 4097753, spend_pp: 9475, reserve: -210901, reserve_pp: -488, share: -0.054,
  balance: -169784, balance_pp: -393, years: [{ y: "2025-26", income: 3927968, reserve: -210901 }], pp: { total_income: 9082, total_expenditure: 9475 },
  similar: { total_income: 7553, total_expenditure: 7672 }, similar_meta: { year: "2025-26", peers: 17, method: "Same phase, nearest in size and FSM." },
};
const CMP_ACADEMY = { ...CMP_SCHOOL, urn: "140001", name: "Mossbourne Community Academy", path: "/school/140001-mossbourne/", academy: true,
  reserve_basis: "incl_trust_share", similar_meta: undefined, status: "reserve_held_by_trust" };
function comparePage(doc, { listbox = false, status = false } = {}) {
  const app = add(doc.body, "section", { id: "compare-app" });
  const form = add(app, "form", { class: "finder", role: "search" });
  add(form, "input", { id: "cmp-find", type: "search" });
  add(app, "ul", listbox ? { id: "cmp-results", class: "results", role: "listbox" } : { id: "cmp-results", class: "results" });
  if (status) add(app, "p", { id: "cmp-status", class: "visually-hidden", role: "status", "aria-live": "polite" });
  add(app, "ul", { id: "cmp-chosen" });
  add(app, "div", { id: "cmp-out" });
}

test("compare results are 'Compare <school>' buttons with the count in a polite status, old or new markup", async () => {
  for (const markup of [{ listbox: true }, { status: true }]) {
    // Arrange
    const h = boot({ path: "/compare/", data: { "/data/search.json": INDEX }, setup: (doc) => comparePage(doc, markup) });
    const input = h.document.getElementById("cmp-find");
    // Act
    input.value = "william patten";
    input.dispatchEvent({ type: "input" });
    await settle();
    // Assert
    const results = h.document.getElementById("cmp-results");
    assert.equal(results.getAttribute("role"), null, JSON.stringify(markup));
    assert.equal(results.getAttribute("aria-label"), "Matching schools");
    assert.deepEqual(results.querySelectorAll("li button").map((b) => b.textContent), ["Compare William Patten Primary School"]);
    const status = h.document.querySelectorAll("#cmp-status");
    assert.equal(status.length, 1);
    assert.equal(status[0].getAttribute("aria-live"), "polite");
    assert.equal(status[0].textContent, "1 school matches.");
  }
});

test("Enter in the compare finder searches instead of submitting the page", () => {
  // Arrange
  const h = boot({ path: "/compare/", data: { "/data/search.json": INDEX }, setup: (doc) => comparePage(doc) });
  const form = h.document.querySelector("form.finder");
  // Act
  const allowed = form.dispatchEvent({ type: "submit" });
  // Assert
  assert.equal(allowed, false);
});

test("compare names School Money's similar schools with their count and year, and labels a trust-share reserve", async () => {
  // Arrange / Act
  const h = boot({ path: "/compare/?urns=100003,140001", data: { "/data/s/100003.json": CMP_SCHOOL, "/data/s/140001.json": CMP_ACADEMY },
                   setup: (doc) => comparePage(doc) });
  h.location.search = "?urns=100003,140001";
  await settle();
  // Assert
  const out = h.document.getElementById("cmp-out").textContent;
  assert.match(out, /similar schools \(17 schools, 2025-26\) £7,553/);
  assert.match(out, /Compared with/);
  assert.doesNotMatch(out, /DfE similar/);
  assert.match(out, /Similar schools are School Money's own comparison groups, not the DfE's\. Same phase, nearest in size and FSM\./);
  assert.match(out, /including its share of the trust's reserve/);
  assert.match(out, /Reserve held by the trust/);
});

test("the compare area table names the DSG measure in full with its year and denominator", async () => {
  // Arrange
  const council = { id: "council-204", name: "Hackney", path: "/council/hackney/",
    by_year: { "2025-26": { all: { schools: 60, in_deficit: 15 } } },
    dsg: { "2024-25": { balance: -16493653, per_pupil: -518 }, "2025-26": { balance: -16249115, per_pupil: -513, provisional: true } } };
  // Act
  const h = boot({ path: "/compare/?areas=council-204", data: { "/data/a/council-204.json": council }, setup: (doc) => comparePage(doc) });
  await settle();
  // Assert
  const out = h.document.getElementById("cmp-out").textContent;
  assert.match(out, /Dedicated Schools Grant balance \(all four blocks\)/);
  assert.match(out, /-£16\.2m \(2025-26, provisional; -£513 per pupil at the council's schools on this site\)/);
  assert.doesNotMatch(out, /high-needs|schools budget/i);
});

// Fundraising finder and search: realistic joined fixtures, exercising the rendered controls as well as ranking.
const FIND_INDEX = [
  { t: "council", id: "204", name: "Hackney", p: "/council/hackney/" },
  { t: "council", id: "210", name: "Southwark", p: "/council/southwark/" },
  { t: "school", id: "1", name: "Northwold School", sub: "Hackney", ph: 1, status: "healthy", p: "/school/1-northwold/" },
  { t: "school", id: "2", name: "Mossbourne Academy", sub: "Hackney", ph: 2, status: "in_deficit", p: "/school/2-mossbourne/" },
  { t: "school", id: "3", name: "Harris Academy", sub: "Peckham, Southwark", ph: 2, status: "healthy", p: "/school/3-harris/" },
  { t: "school", id: "4", name: "St Mary's Primary", sub: "Islington", ph: 1, status: null, p: "/school/4-st-marys/" },
  { t: "school", id: "5", name: "Park School", sub: "Hackney", ph: 1, status: "healthy", p: "/school/5-park/" },
];
const FUND_DATA = {
  v: 2, columns: ["id", "c", "b", "lat", "lon", "income", "pp", "year", "charities", "flags", "change"],
  pupils: { "1": 300, "2": 1000, "4": 100, "5": 200 },
  councils: { "204": ["Hackney", "London", 76], "210": ["Southwark", "London", null], "999": ["Far away", "North East", 10] },
  year: "2024-25", england: 31,
  rows: [
    ["2", "204", 3, 51.55, -0.06, 20000, 20, "2024-25", ["111111"], 0, [4200, 26.6, 4]],
    ["3", "210", 1, 51.49, -0.07, 50000, null, "2025-26", ["222222"], 3, 4],
    ["4", "999", 5, 54, -1, 0, 0, "2024-25", ["333333"], 0, [0, null, 0]],
    ["5", "204", 2, 51.56, -0.06, 10000, 50, "2024-25", ["444444"], 0, [-1000, -9.1, -5]],
  ],
};
const findData = { "/data/search.json": FIND_INDEX, "/data/fundraising.json": FUND_DATA };
const searchSetup = (doc) => add(add(doc.body, "main"), "h1", {}, "Search");
const finderSetup = (doc) => add(doc.body, "div", { id: "fundraising-controls" });
const change = (node, value) => { node.value = value; node.dispatchEvent({ type: "change" }); };

for (const sort of ["name", "total", "pp", "change", "change_pct", "pupils", "distance"]) {
  for (const dir of ["asc", "desc"]) {
    test(`${sort} ${dir}: search and finder order values before missing values, including zero and negatives`, () => {
      // Arrange: input deliberately puts the missing value first; a separate row has no association.
      const point = { lat: 51.5, lon: 0 };
      const make = (id, name, value, lat) => ({ t: "school", id, name, pupils: value,
        fund: { income: value, pp: value, change: value == null ? 1 : [value, value, value], lat, lon: 0 } });
      const rows = [make("missing", "", null, null), make("zero", "Bee", 0, 51.51),
        make("negative", "Aye", -10, 51.5), make("positive", "See", 20, 51.52)];
      const expected = dir === "asc" ? ["negative", "zero", "positive", "missing"] : ["positive", "zero", "negative", "missing"];
      // Act
      const finder = M.filterFundraisers(rows, { sort, dir }, sort === "distance" ? point : null, {});
      const search = M.filterSearch(rows, { sort, dir });
      // Assert: distance's existing radius filter leaves unlocated schools out.
      assert.deepEqual(finder.map((r) => r.id), sort === "distance" ? expected.slice(0, 3) : expected);
      if (sort !== "distance") assert.deepEqual(search.map((r) => r.id), expected);
      assert.equal(rows[0].id, "missing", "input not mutated");
    });
  }
}

test("relevance direction reverses the ranked results without including non-matches", () => {
  // Arrange
  const ranked = M.rankSearch(FIND_INDEX, "hackney", 100);
  // Act
  const desc = M.filterSearch(ranked, { sort: "relevance", dir: "desc" });
  const asc = M.filterSearch(ranked, { sort: "relevance", dir: "asc" });
  // Assert
  assert.deepEqual(desc, ranked);
  assert.deepEqual(asc, ranked.slice().reverse());
});

test("all sorts and directions round-trip through URLs, with sensible defaults and fallbacks", () => {
  // Arrange
  const sorts = ["relevance", "name", "total", "pp", "change", "change_pct", "pupils", "distance"];
  for (const sort of sorts) {
    for (const dir of ["asc", "desc"]) {
      // Act
      const query = M.stateQuery({ sort, dir, postcode: "E8" });
      const search = M.searchState(query), finder = M.finderState(query);
      // Assert
      assert.equal(search.sort, sort === "distance" ? "" : sort);
      assert.equal(finder.sort, sort === "relevance" ? "total" : sort);
      assert.equal(search.dir, dir);
      assert.equal(finder.dir, dir);
    }
  }
  assert.equal(M.searchState("?sort=name&dir=nonsense").dir, "asc");
  assert.equal(M.searchState("?sort=change").dir, "desc");
  assert.equal(M.finderState("?sort=distance&postcode=E8").dir, "asc");
  assert.equal(M.finderState("?sort=distance").sort, "total");
  assert.equal(M.searchState("?sort=unknown").sort, "");
});

test("change words cover gains, falls, zero, zero baseline and every withheld reason", () => {
  // Arrange
  const f = { year: "2024-25", change: [4200, 12, -3] };
  // Act / Assert
  assert.equal(M.incomeChangeText(f), "Up £4,200 (+12%) on 2023-24 · Down £3 per pupil");
  assert.equal(M.incomeChangeText({ ...f, change: [-4200, -12, null] }), "Down £4,200 (-12%) on 2023-24");
  assert.equal(M.incomeChangeText({ ...f, change: [0, 0, 0] }), "No change (£0) (0%) on 2023-24 · No change (£0) per pupil");
  assert.match(M.incomeChangeText({ ...f, change: [4200, null, null] }), /percentage unavailable: previous income was zero or below/);
  for (const reason of [1, 2, 3, 4, 5, 6]) assert.match(M.incomeChangeText({ ...f, change: reason }), /^No change figure: /);
});

test("search restores direction, changes sort defaults, and sorts pupils without requiring an association", async () => {
  // Arrange
  const h = boot({ path: "/search/?sort=pupils&dir=desc", data: findData, setup: searchSetup });
  await settle();
  // Act / Assert
  assert.deepEqual(h.document.querySelectorAll(".results li").map((li) => li.querySelector("a").textContent),
    ["Mossbourne Academy", "Northwold School", "Park School", "St Mary's Primary", "Harris Academy"]);
  assert.match(h.document.querySelector(".search-results").textContent, /Up £4,200/);
  assert.equal(h.document.querySelector('label[for="search-dir"]').textContent, "Direction");
  change(h.document.querySelector("#search-sort"), "name"); await settle();
  assert.equal(h.document.querySelector("#search-dir").value, "asc");
  assert.match(h.urls.at(-1), /sort=name&dir=asc/);
  change(h.document.querySelector("#search-dir"), "desc"); await settle();
  assert.equal(h.document.querySelector(".results a").textContent, "St Mary's Primary");
  assert.match(h.urls.at(-1), /sort=name&dir=desc/);
});

test("finder distance needs a postcode, uses ascending by default, and preserves the submitted direction", async () => {
  // Arrange
  const h = boot({ path: "/ptfa/", data: { ...findData, "/data/postcodes/E8.json": { lat: 51.55, lon: -0.06 } }, setup: finderSetup });
  await settle();
  const sort = h.document.querySelector("#fund-sort"), dir = h.document.querySelector("#fund-dir");
  const distance = sort.querySelectorAll("option").find((o) => o.value === "distance");
  assert.equal(distance.disabled, true);
  // Act
  const postcode = h.document.querySelector("#fund-postcode"); postcode.value = "E8"; postcode.dispatchEvent({ type: "input" });
  change(sort, "distance");
  h.document.querySelector("form").dispatchEvent({ type: "submit" }); await settle();
  // Assert
  assert.equal(distance.disabled, false);
  assert.equal(dir.value, "asc");
  assert.equal(h.document.querySelector(".results a").textContent, "Mossbourne Academy");
  assert.match(h.urls.at(-1), /sort=distance&dir=asc/);
  // Act
  change(dir, "desc"); h.document.querySelector("form").dispatchEvent({ type: "submit" }); await settle();
  // Assert
  assert.equal(h.document.querySelector(".results a").textContent, "Harris Academy");
  assert.match(h.urls.at(-1), /sort=distance&dir=desc/);
  assert.equal(h.document.querySelector('label[for="fund-dir"]').textContent, "Direction");
});

test("browser history restores the sort and direction on search and finder", async () => {
  for (const prefix of ["search", "fund"]) {
    // Arrange
    const events = {};
    const path = prefix === "search" ? "/search/?sort=total" : "/ptfa/?sort=total";
    const h = boot({ path, data: findData, setup: prefix === "search" ? searchSetup : finderSetup,
      globals: { addEventListener: (type, fn) => { events[type] = fn; } } });
    await settle();
    // Act
    h.location.search = "?sort=name&dir=desc";
    events.popstate(); await settle();
    // Assert
    assert.equal(h.document.querySelector("#" + prefix + "-sort").value, "name");
    assert.equal(h.document.querySelector("#" + prefix + "-dir").value, "desc");
    assert.equal(h.document.querySelector(".results a").textContent, "St Mary's Primary");
  }
});

test("distance without a point has no values to rank; malformed changes are rejected", () => {
  // Arrange
  const rows = M.withFundraising(FIND_INDEX, M.fundraisingRows(FUND_DATA));
  // Act / Assert
  for (const dir of ["asc", "desc"]) {
    assert.deepEqual(M.filterFundraisers(rows, { sort: "distance", dir }, null, FUND_DATA.councils).map((r) => r.id), ["2", "3", "4", "5"]);
  }
  for (const bad of [null, [], [1, null], [null, 10, 5], [1, "10", 5], 0, 7]) {
    const doc = structuredClone(FUND_DATA); doc.rows[0][10] = bad;
    assert.equal(M.fundraisingRows(doc), null);
  }
});

test("phase plus area includes the council and every matching phase; names with places still work", () => {
  // Arrange
  const queries = ["primary schools in hackney", "hackney secondary"];
  // Act
  const hits = queries.map((q) => M.searchMatches(FIND_INDEX, q, 50).rows);
  // Assert
  assert.deepEqual(hits[0].map((r) => r.id), ["204", "5", "1"]);
  assert.deepEqual(hits[1].map((r) => r.id), ["204", "2"]);
  assert.equal(M.searchMatches(FIND_INDEX, "harris peckham").rows[0].id, "3");
  assert.equal(M.searchMatches(FIND_INDEX, "mossbourne hackney").rows[0].id, "2");
  assert.deepEqual(M.queryIntent("secondary schools near E8").postcode, { district: "E8", inward: null, full: null });
});

test("fundraising keywords offer the finder first, including Friends of", () => {
  // Arrange
  const queries = ["pta", "ptfa", "pfa", "fundraising", "parents association", "parents’ association", "friends of"];
  // Act / Assert
  for (const q of queries) assert.equal(M.searchMatches(FIND_INDEX, q).rows[0].p, "/ptfa/#fundraising-finder", q);
});

test("dead ends identify a known area and offer names elsewhere, or a postcode hint and council browse", () => {
  // Arrange / Act
  const local = M.searchNextSteps(FIND_INDEX, "st marys hackney");
  const unknown = M.searchNextSteps(FIND_INDEX, "zzzzzzzzz");
  // Assert
  assert.match(local.message, /Nothing called 'st marys' in Hackney/);
  assert.equal(local.rows[0].p, "/council/hackney/");
  assert.equal(local.rows[1].id, "4");
  assert.match(unknown.message, /postcode/);
  assert.equal(unknown.rows.at(-1).p, "/council/");
});

test("dropdown shows phase and PTA figures, total when suppressed, and helpful dead ends", async () => {
  // Arrange
  const h = boot({ data: findData, setup: searchBox });
  assert.ok(!h.calls.includes("/data/fundraising.json"), "lazy until search");
  // Act
  typeInto(h, "harris peckham"); await settle();
  // Assert
  assert.match(h.document.querySelector("#q-list").textContent, /Secondary.*£50,000 total.*2025-26/);
  assert.doesNotMatch(h.document.querySelector("#q-list").textContent, /£0 per pupil/);
  // Act
  typeInto(h, "st marys hackney"); await settle();
  // Assert
  assert.match(h.document.querySelector("#q-list").textContent, /Nothing called 'st marys' in Hackney/);
  assert.ok(options(h.document).includes("St Mary's Primary"));
  assert.ok(options(h.document).includes("Browse by council"));
});

test("phase near postcode filters before limiting, shows phase and fundraising, and stays on-site while typing", async () => {
  // Arrange
  const district = { lat: 51.55, lon: -0.06, schools: FIND_INDEX.filter((r) => r.t === "school").map((r) => ({ ...r, lat: 51.55, lon: -0.06 })) };
  const h = boot({ data: { ...findData, "/data/postcodes/E8.json": district }, setup: searchBox });
  // Act
  typeInto(h, "secondary schools near E8"); await settle();
  // Assert
  assert.deepEqual(options(h.document), ["Mossbourne Academy", "Harris Academy"]);
  assert.match(h.document.querySelector("#q-list").textContent, /£20 per pupil/);
  assert.ok(h.calls.every((u) => u.startsWith("/")));
});

test("search filters honour all URL fields and apply before limiting, null incomes sort last", () => {
  // Arrange
  const rows = M.withFundraising(FIND_INDEX, M.fundraisingRows(FUND_DATA));
  const state = M.searchState("?q=hackney&phase=primary&status=healthy&pta=1&sort=pp");
  // Act
  const hits = M.filterSearch(rows, state);
  // Assert
  assert.deepEqual(hits.map((r) => r.id), ["5"]);
  assert.equal(M.stateQuery(state), "q=hackney&phase=primary&status=healthy&pta=1&sort=pp&dir=desc");
  assert.deepEqual(M.filterSearch(rows, { sort: "pp" }).map((r) => r.id), ["5", "2", "4", "1", "3"]);
  assert.deepEqual(M.filterSearch(rows, { status: "unknown" }).map((r) => r.id), ["4"]);
});

test("a sort the search page doesn't offer falls back to relevance instead of a blank choice", () => {
  // Arrange
  const query = "?q=primary+hackney&sort=pta_pp";
  // Act
  const state = M.searchState(query);
  // Assert
  assert.equal(state.sort, "");
  assert.equal(state.q, "primary hackney");
  assert.equal(M.searchState("?sort=total").sort, "total");
});

test("search page restores shareable filters, updates the URL, shows results without redirecting a unique name", async () => {
  // Arrange
  const h = boot({ path: "/search/?q=hackney&phase=primary&status=healthy&pta=1&sort=pp", data: findData, setup: searchSetup });
  await settle();
  // Assert
  assert.equal(h.document.querySelector("#search-phase").value, "primary");
  assert.equal(h.document.querySelector("#search-pta").value, "1");
  assert.deepEqual(h.document.querySelectorAll(".results a").map((a) => a.textContent), ["Park School"]);
  assert.deepEqual(h.replaced, []);
  // Act
  change(h.document.querySelector("#search-phase"), "secondary"); await settle();
  // Assert
  assert.match(h.urls.at(-1), /phase=secondary/);
  assert.match(h.document.querySelector(".search-results").textContent, /Clear the filters/);
});

test("search results paginate after filtering, so a school beyond the old first 50 can be found", async () => {
  // Arrange
  const rows = Array.from({ length: 80 }, (_, i) => ({ t: "school", id: String(1000 + i), name: `Example School ${i}`, sub: "Hackney", ph: i === 79 ? 2 : 1, p: `/school/${1000 + i}/` }));
  const h = boot({ path: "/search/?q=example&phase=secondary", data: { ...findData, "/data/search.json": rows }, setup: searchSetup });
  // Act
  await settle();
  // Assert
  assert.match(h.document.querySelector(".search-results").textContent, /Example School 79/);
  // Act
  change(h.document.querySelector("#search-phase"), ""); await settle();
  h.document.querySelector(".more-results").click();
  // Assert
  assert.equal(h.document.querySelectorAll(".results a").length, 80);
});

test("fundraiser filters combine region, council, phase, band and radius; sort treats missing pp as unknown", () => {
  // Arrange
  const rows = M.withFundraising(FIND_INDEX, M.fundraisingRows(FUND_DATA));
  // Act
  const selected = M.filterFundraisers(rows, { region: "London", council: "204", phase: "primary", band: "2", sort: "pp" }, { lat: 51.55, lon: -0.06 }, FUND_DATA.councils);
  const total = M.filterFundraisers(rows, { sort: "total" }, null, FUND_DATA.councils);
  const pp = M.filterFundraisers(rows, { sort: "pp" }, null, FUND_DATA.councils);
  // Assert
  assert.deepEqual(selected.map((r) => r.id), ["5"]);
  assert.deepEqual(total.map((r) => r.id), ["3", "2", "5", "4"]);
  assert.deepEqual(pp.map((r) => r.id), ["5", "2", "4", "3"]);
  assert.deepEqual(M.filterFundraisers(rows, {}, { lat: 51.55, lon: -0.06 }, FUND_DATA.councils).map((r) => r.id), ["3", "2", "5"]);
});

test("finder defaults to static lists; submitted controls show medians, school, charity and compare links", async () => {
  // Arrange
  const h = boot({ path: "/ptfa/", data: findData, setup: finderSetup });
  await settle();
  assert.equal(h.document.querySelector(".fund-results").textContent, "");
  // Act
  h.document.querySelector("#fund-council").value = "204";
  h.document.querySelector("#fund-sort").value = "pp";
  h.document.querySelector("form").dispatchEvent({ type: "submit" }); await settle();
  // Assert
  const box = h.document.querySelector(".fund-results");
  assert.match(box.textContent, /England median: £31 per pupil. Hackney median: £76 per pupil \(2024-25\)/);
  assert.equal(box.querySelector(".results a").href, "/school/5-park/");
  assert.ok(box.querySelectorAll("a").some((a) => a.href.includes("regId=444444")));
  assert.ok(box.querySelectorAll("a").some((a) => a.href === "/compare/?urns=5"));
  assert.match(h.urls.at(-1), /council=204.*sort=pp/);
});

test("finder restores a council link, caps at 25 and reports unavailable medians", async () => {
  // Arrange
  const index = Array.from({ length: 30 }, (_, i) => ({ ...FIND_INDEX[4], id: String(100 + i), name: `Academy ${i}` }));
  const data = { ...FUND_DATA, rows: index.map((r, i) => [r.id, "210", 1, 51.49, -0.07, 10000 + i, null, "2025-26", ["222222"], 0, 4]) };
  const h = boot({ path: "/ptfa/?council=210", data: { "/data/search.json": index, "/data/fundraising.json": data }, setup: finderSetup });
  // Act
  await settle();
  // Assert
  assert.equal(h.document.querySelector("#fund-council").value, "210");
  assert.match(h.document.querySelector(".fund-results").textContent, /Showing 25 of 30/);
  assert.equal(h.document.querySelectorAll(".results li").length, 25);
  assert.match(h.document.querySelector(".fund-medians").textContent, /Southwark median: unavailable/);
});

test("finder uses the postcode district centre, validates input and recovers from load failure", async () => {
  // Arrange
  const h = boot({ path: "/ptfa/?postcode=E8+1AA", data: findData, setup: finderSetup });
  await settle();
  assert.match(h.document.querySelector(".fund-results").textContent, /district could not be loaded/);
  h.fixtures["/data/postcodes/E8.json"] = { lat: 51.55, lon: -0.06 };
  // Act
  h.document.querySelector("form").dispatchEvent({ type: "submit" }); await settle();
  // Assert
  assert.match(h.document.querySelector(".fund-results").textContent, /Showing 3 of 3/);
  assert.ok(h.calls.every((u) => !u.includes("postcodes.io")));
  // Act
  h.document.querySelector("#fund-postcode").value = "not a postcode";
  h.document.querySelector("form").dispatchEvent({ type: "submit" }); await settle();
  // Assert
  assert.match(h.document.querySelector(".fund-results").textContent, /Enter a postcode or district/);
});

test("fundraising data failures leave search usable and can be retried", async () => {
  // Arrange
  const h = boot({ path: "/search/?q=mossbourne", data: { "/data/search.json": FIND_INDEX }, setup: searchSetup });
  await settle();
  assert.match(h.document.querySelector(".search-results").textContent, /Mossbourne Academy/);
  h.fixtures["/data/fundraising.json"] = FUND_DATA;
  // Act
  h.document.querySelector(".search-results button").click(); await settle();
  // Assert
  assert.match(h.document.querySelector(".search-results").textContent, /£20 per pupil/);
  assert.doesNotMatch(h.document.querySelector(".search-results").textContent, /could not be loaded/);
});

test("malformed fundraising data is rejected and the finder retries without hiding the static fallback", async () => {
  // Arrange
  const h = boot({ path: "/ptfa/", data: { ...findData, "/data/fundraising.json": { ...FUND_DATA, rows: [null] } }, setup: finderSetup });
  await settle();
  assert.match(h.document.querySelector("#fundraising-controls").textContent, /still browse the top lists/);
  h.fixtures["/data/fundraising.json"] = FUND_DATA;
  // Act
  h.document.querySelector("button").click(); await settle();
  // Assert
  assert.ok(h.document.querySelector("#fund-council"));
  assert.equal(h.calls.filter((u) => u === "/data/fundraising.json").length, 2);
});

test("clearing a preselected council survives a region change", async () => {
  // Arrange
  const h = boot({ path: "/ptfa/?council=204", data: findData, setup: finderSetup });
  await settle();
  // Act
  h.document.querySelector("#fund-council").value = "";
  change(h.document.querySelector("#fund-region"), "London");
  // Assert
  assert.equal(h.document.querySelector("#fund-council").value, "");
});

// ---------------------------------------------------------------- header and audience flow
test("every legacy audience survives navigation to a page without a picker; Close clears it and restores focus", () => {
  for (const reader of M.READERS) {
    // Arrange
    const setup = (doc) => {
      add(doc.body, "input", { id: "q", type: "search" });
      const main = readerPage(doc, { picker: false });
      for (const id of ["status", "spending", "reserve", "ptfa", "questions", "split"]) add(main, "section", { id });
    };
    const path = "/school/100001-example-primary/";
    // Act
    const h = boot({ storage: { moneyAudience: reader }, path, setup });
    // Assert
    assert.equal(h.document.querySelector("fieldset.audience"), null);
    assert.equal(h.document.documentElement.getAttribute("data-reader"), reader);
    assert.equal(h.document.querySelector(".fy-title").textContent, M.READER_TITLES[reader]);
    assert.equal(h.memory.get("moneyAudience"), JSON.stringify(reader));
    assert.ok(h.document.querySelectorAll("#for-you a").length >= 4);
    // Act
    const close = h.document.querySelector(".fy-close");
    close.focus();
    close.click();
    const next = boot({ storage: { moneyAudience: JSON.parse(h.memory.get("moneyAudience")) }, path, setup });
    // Assert
    assert.equal(h.document.activeElement, h.document.getElementById("q"));
    assert.equal(h.document.getElementById("for-you").children.length, 0);
    assert.equal(next.document.getElementById("for-you").children.length, 0);
    assert.equal(next.document.documentElement.getAttribute("data-reader"), null);
  }
});

test("a first visit has no quick links until a home audience choice is made", () => {
  // Arrange
  const h = boot({ path: "/", setup: (doc) => readerPage(doc) });
  // Act
  const before = h.document.getElementById("for-you").children.length;
  h.document.querySelector('button[data-audience="ptfa"]').click();
  // Assert
  assert.equal(before, 0);
  assert.equal(h.memory.get("moneyAudience"), '"ptfa"');
  assert.ok(h.document.querySelectorAll("#for-you a").some(a => a.getAttribute("href") === "/guides/ptfa/"));
});

test("Escape closes More before the phone menu and restores focus to its disclosure", () => {
  // Arrange
  const h = boot({ setup(doc) {
    const header = add(doc.body, "header");
    add(header, "button", { class: "menu-toggle", "aria-expanded": "true", "aria-controls": "main-nav" });
    const more = add(add(header, "nav", { id: "main-nav" }), "details", { class: "nav-more", open: "" });
    add(more, "summary", {}, "More");
    add(more, "a", { href: "/map/" }, "Map");
  } });
  const more = h.document.querySelector("details");
  more.querySelector("a").focus();
  // Act
  h.document.dispatchEvent({ type: "keydown", key: "Escape" });
  // Assert
  assert.equal(more.hasAttribute("open"), false);
  assert.equal(h.document.activeElement, more.querySelector("summary"));
  assert.equal(h.document.querySelector(".menu-toggle").getAttribute("aria-expanded"), "true");
  // Act
  h.document.dispatchEvent({ type: "keydown", key: "Escape" });
  // Assert
  assert.equal(h.document.querySelector(".menu-toggle").getAttribute("aria-expanded"), "false");
  assert.equal(h.document.activeElement, h.document.querySelector(".menu-toggle"));
});

test("the single home finder still loads suggestions and opens a school with the keyboard", async () => {
  // Arrange
  const h = boot({ data: { "/data/search.json": INDEX }, path: "/", setup(doc) {
    const form = add(doc.body, "form", { class: "finder home-search", action: "/search/", role: "search" });
    add(form, "input", { id: "find", name: "q", type: "search", autocomplete: "off" });
  } });
  const input = h.document.getElementById("find");
  // Act
  input.focus();
  input.value = "william patten";
  input.dispatchEvent({ type: "input" });
  h.flushTimers();
  await settle();
  input.dispatchEvent({ type: "keydown", key: "ArrowDown" });
  // Assert
  assert.equal(h.document.getElementById("q"), null);
  assert.equal(input.getAttribute("aria-expanded"), "true");
  assert.equal(input.getAttribute("aria-activedescendant"), "find-opt-0");
  // Act
  input.dispatchEvent({ type: "keydown", key: "Enter" });
  // Assert
  assert.equal(h.location.href, INDEX.find(row => row.id === "100003").p);
});
