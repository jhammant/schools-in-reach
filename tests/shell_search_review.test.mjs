// Independent review regressions. Offline DOM fixture copied from test_app_js.mjs; no app logic is stubbed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
const here = join(dirname(fileURLToPath(import.meta.url)), "../pipeline/money");
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
  const calls = [], timers = [], replaced = [];
  const fixtures = { "/assets/glossary.json": glossary, ...data };
  const url = new URL(path, "https://money.schoolsinreach.com/");
  const location = { href: url.href, search: url.search, pathname: url.pathname, replace: (u) => replaced.push(u) };
  const ctx = vm.createContext({
    document, console, URL, URLSearchParams, location, Node, ...globals,
    history: { replaceState() {} },
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
  return { document, calls, memory, fixtures, location, replaced, flushTimers() { timers.splice(0).forEach((fn) => fn()); } };
}

const school = {
  t: "school", id: "130932", name: "William Patten Primary School", sub: "Hackney",
  p: "/school/130932-william-patten-primary-school/",
};
const council = { t: "council", id: "204", name: "Hackney", sub: "London", p: "/council/hackney/" };

function searchPage(doc) {
  add(add(doc.body, "main", { id: "main" }), "h1", {}, "Search");
}

test("retry-evicts-invalid-index: Try again refetches a rejected index document", async () => {
  // Arrange: a successful HTTP response with an unusable index, e.g. a partial build.
  for (const invalid of [[], { error: "temporarily unavailable" }]) {
    const h = boot({ path: "/search/?q=patten", data: { "/data/search.json": invalid }, setup: searchPage });
    await settle();
    const box = h.document.querySelector(".search-results");
    assert.match(box.textContent, /Search is unavailable/);

    // Act: the server has recovered and the reader uses the offered retry button.
    h.fixtures["/data/search.json"] = [school];
    box.querySelector("button").click();
    await settle();

    // Assert: retry must make a new request, not reuse fetchJSON's cached bad value.
    assert.equal(h.calls.filter((u) => u === "/data/search.json").length, 2);
    assert.match(box.textContent, /William Patten Primary School/);
    assert.doesNotMatch(box.textContent, /unavailable/);
  }
});

test("import-unavailable-index: a failed request does not reject the import handler", async () => {
  // Arrange: this saved list makes the import button visible; the index fetch will 404.
  const h = boot({ storage: { shortlist: [school.id] }, setup: (doc) => add(doc.body, "main", { id: "main" }) });
  const offer = h.document.querySelector(".pin-import");

  // Act.
  offer.querySelector("button").click();
  // Let rejected promise callbacks surface. node:test fails on an unhandled rejection.
  await new Promise((resolve) => setImmediate(resolve));

  // Assert: the click exercised the failed request without crashing a promise continuation.
  assert.equal(h.calls.filter((u) => u === "/data/search.json").length, 1);
});

test("area-typos: council search ignores area words before fuzzy matching", () => {
  // Arrange: the frozen search-index shape uses the bare council name.
  const context = vm.createContext({});
  vm.runInContext(appSource, context);
  const search = context.MoneyApp.searchMatches;

  // Act / Assert: one missing or swapped letter should work with either area phrase.
  for (const query of ["Hakney council", "schools in Hacnkey"]) {
    const matches = search([school, council], query, 8);
    assert.equal(matches.rows[0]?.id, council.id, query);
    assert.equal(matches.fuzzy, true, query);
  }
});

