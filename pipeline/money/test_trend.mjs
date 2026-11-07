// Tests for assets/trend.js under node with a minimal fake DOM (no browser, no network).
// Run: node --test pipeline/money/test_trend.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("./assets/trend.js", import.meta.url), "utf8");

// A fake DOM: elements with attributes, children, simple selectors (tag, .class, [attr], [attr="v"],
// comma lists), closest() and bubbling click events. Just what trend.js touches.
function matches(node, selector) {
  return selector.split(",").some((part) => {
    let rest = part.trim();
    let ok = true;
    rest = rest.replace(/\[([\w-]+)(?:=["']?([^"'\]]*)["']?)?\]/g, (_, name, value) => {
      const actual = node.getAttribute(name);
      if (actual === null || (value !== undefined && actual !== value)) ok = false;
      return "";
    });
    rest = rest.replace(/\.([\w-]+)/g, (_, name) => {
      if (!(node.getAttribute("class") || "").split(/\s+/).includes(name)) ok = false;
      return "";
    });
    return ok && (!rest || rest.toLowerCase() === node.tagName.toLowerCase());
  });
}

class El {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase();
    this.attributes = new Map(Object.entries(attrs));
    this.children = [];
    this.parentNode = null;
    this.listeners = {};
  }
  getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; }
  setAttribute(k, v) { this.attributes.set(k, String(v)); }
  hasAttribute(k) { return this.attributes.has(k); }
  removeAttribute(k) { this.attributes.delete(k); }
  append(tag, attrs) { const c = new El(tag, attrs); c.parentNode = this; this.children.push(c); return c; }
  querySelectorAll(selector) {
    const out = [];
    for (const c of this.children) {
      if (matches(c, selector)) out.push(c);
      out.push(...c.querySelectorAll(selector));
    }
    return out;
  }
  closest(selector) { return matches(this, selector) ? this : this.parentNode && this.parentNode.closest ? this.parentNode.closest(selector) : null; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  click() {
    const event = { type: "click", target: this };
    for (let n = this; n; n = n.parentNode) (n.listeners.click || []).forEach((fn) => fn(event));
  }
}

function storageWith(initial, { broken = false } = {}) {
  const memory = new Map(Object.entries(initial));
  return {
    memory,
    getItem(k) { if (broken) throw new Error("SecurityError"); return memory.has(k) ? memory.get(k) : null; },
    setItem(k, v) { if (broken) throw new Error("QuotaExceededError"); memory.set(k, String(v)); },
  };
}

// Two .trend blocks as B2/B3 emit them: default markup is cash and per pupil.
function page() {
  const doc = new El("html");
  const blocks = [0, 1].map(() => {
    const box = doc.append("section", { class: "trend" });
    box.append("button", { "data-basis-toggle": "cash", "aria-pressed": "true" });
    box.append("button", { "data-basis-toggle": "real", "aria-pressed": "false" });
    box.append("button", { "data-unit-toggle": "pp", "aria-pressed": "true" });
    box.append("button", { "data-unit-toggle": "total", "aria-pressed": "false" });
    const pp = box.append("div", { "data-unit": "pp" });
    const total = box.append("div", { "data-unit": "total", hidden: "" });
    for (const block of [pp, total]) {
      const svg = block.append("svg");
      svg.append("g", { "data-basis": "cash" });
      svg.append("g", { "data-basis": "real", display: "none" });
    }
    return box;
  });
  return { doc, blocks };
}

function boot(store) {
  // Arrange (shared): run trend.js against the fake page with the given storage.
  const { doc, blocks } = page();
  const ctx = vm.createContext({ document: doc, localStorage: store });
  vm.runInContext(source, ctx, { filename: "pipeline/money/assets/trend.js" });
  return { doc, blocks, api: ctx.MoneyTrend };
}

const display = (box, basis) => box.querySelectorAll(`g[data-basis="${basis}"]`).map((g) => g.getAttribute("display"));
const button = (box, attr, value) => box.querySelectorAll(`[${attr}="${value}"]`)[0];

test("without a saved choice the markup default (cash, per pupil) is left alone", () => {
  // Act
  const { blocks } = boot(storageWith({}));
  // Assert
  assert.deepEqual(display(blocks[0], "cash"), [null, null]);
  assert.deepEqual(display(blocks[0], "real"), ["none", "none"]);
  assert.equal(blocks[0].querySelectorAll('[data-unit="total"]')[0].hasAttribute("hidden"), true);
});

test("choosing real terms switches every .trend on the page and is remembered", () => {
  // Arrange
  const store = storageWith({});
  const { blocks } = boot(store);
  // Act
  button(blocks[0], "data-basis-toggle", "real").click();
  // Assert
  for (const box of blocks) {
    assert.deepEqual(display(box, "cash"), ["none", "none"]);
    assert.deepEqual(display(box, "real"), [null, null]);
    assert.equal(button(box, "data-basis-toggle", "real").getAttribute("aria-pressed"), "true");
    assert.equal(button(box, "data-basis-toggle", "cash").getAttribute("aria-pressed"), "false");
  }
  assert.equal(store.memory.get("moneyBasis"), "real");
  // Act again: back to cash.
  button(blocks[1], "data-basis-toggle", "cash").click();
  assert.deepEqual(display(blocks[0], "real"), ["none", "none"]);
  assert.equal(store.memory.get("moneyBasis"), "cash");
});

test("a saved basis applies to every .trend on load; an unknown value is ignored", () => {
  // Act
  const saved = boot(storageWith({ moneyBasis: "real" }));
  const junk = boot(storageWith({ moneyBasis: "<script>" }));
  // Assert
  for (const box of saved.blocks) assert.deepEqual(display(box, "real"), [null, null]);
  assert.deepEqual(display(junk.blocks[0], "real"), ["none", "none"]);
});

test("the unit toggle swaps per-pupil and total blocks in its own container only", () => {
  // Arrange
  const { blocks } = boot(storageWith({}));
  // Act
  button(blocks[0], "data-unit-toggle", "total").click();
  // Assert
  assert.equal(blocks[0].querySelectorAll('[data-unit="total"]')[0].hasAttribute("hidden"), false);
  assert.equal(blocks[0].querySelectorAll('[data-unit="pp"]')[0].hasAttribute("hidden"), true);
  assert.equal(button(blocks[0], "data-unit-toggle", "total").getAttribute("aria-pressed"), "true");
  assert.equal(button(blocks[0], "data-unit-toggle", "pp").getAttribute("aria-pressed"), "false");
  assert.equal(blocks[1].querySelectorAll('[data-unit="total"]')[0].hasAttribute("hidden"), true);
});

test("storage that throws never breaks the toggles", () => {
  // Arrange
  const { blocks, api } = boot(storageWith({}, { broken: true }));
  // Act
  button(blocks[0], "data-basis-toggle", "real").click();
  // Assert
  assert.deepEqual(display(blocks[1], "real"), [null, null]);
  assert.equal(api.readBasis(null), null);
  assert.doesNotThrow(() => api.saveBasis(storageWith({}, { broken: true }), "real"));
});

test("a page without localStorage still boots", () => {
  // Act
  const { blocks } = boot(undefined);
  button(blocks[0], "data-basis-toggle", "real").click();
  // Assert
  assert.deepEqual(display(blocks[0], "real"), [null, null]);
});
