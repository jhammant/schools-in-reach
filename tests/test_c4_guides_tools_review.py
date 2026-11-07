"""Offline review regressions for C4's actual rendered forms and browser handlers.

The small DOM double implements the DOM operations tools.js uses. Form fields come
from guides.tool_page, not a separately maintained copy of the form. No packages,
network, production data or existing source/test edits are needed.
"""

import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pipeline.money import guides


ROOT = Path(__file__).resolve().parents[1]


class FormTree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "body", "attrs": {}, "children": []}
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(node)
        if tag not in {"input", "br", "meta", "link", "img", "hr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)


DRIVER = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const code = fs.readFileSync('pipeline/money/assets/tools.js', 'utf8');
const memory = new Map();
const requests = [];

class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase();
    this.attrs = {...attrs};
    this.children = [];
    this.parentNode = null;
    this.handlers = {};
    this.hidden = Object.hasOwn(attrs, 'hidden');
  }
  get id() { return this.attrs.id || ''; }
  set id(v) { this.attrs.id = String(v); }
  get className() { return this.attrs.class || ''; }
  set className(v) { this.attrs.class = String(v); }
  get type() { return this.attrs.type || (this.tagName === 'INPUT' ? 'text' : ''); }
  set type(v) { this.attrs.type = String(v); }
  get value() {
    if (this.currentValue !== undefined) return this.currentValue;
    if (this.tagName === 'SELECT') {
      const options = this.querySelectorAll('option');
      const selected = options.find(o => Object.hasOwn(o.attrs, 'selected')) || options[0];
      return selected ? selected.value : '';
    }
    if (this.tagName === 'TEXTAREA') return this.textContent;
    return this.attrs.value || '';
  }
  set value(v) { this.currentValue = String(v); }
  get textContent() { return this.children.map(c => c.textContent).join(''); }
  set textContent(v) { this.children = [{textContent: String(v), parentNode: this}]; }
  appendChild(node) { node.parentNode = this; this.children.push(node); return node; }
  removeChild(node) { this.children.splice(this.children.indexOf(node), 1); node.parentNode = null; return node; }
  get firstChild() { return this.children[0] || null; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  contains(node) { return node === this || this.children.some(c => c instanceof Element && c.contains(node)); }
  matches(selector) {
    const attr = /^\[([^=\]]+)(?:=['"]?([^'"\]]+)['"]?)?\]$/.exec(selector);
    if (attr) return Object.hasOwn(this.attrs, attr[1]) && (attr[2] === undefined || this.attrs[attr[1]] === attr[2]);
    if (selector.startsWith('#')) return this.id === selector.slice(1);
    const [tag, cls] = selector.split('.');
    return (!tag || this.tagName.toLowerCase() === tag) && (!cls || this.className.split(/\s+/).includes(cls));
  }
  querySelectorAll(selector) {
    const out = [];
    for (const child of this.children) if (child instanceof Element) {
      if (child.matches(selector)) out.push(child);
      out.push(...child.querySelectorAll(selector));
    }
    return out;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  get elements() {
    return ['input', 'select', 'textarea', 'button'].flatMap(tag => this.querySelectorAll(tag));
  }
  addEventListener(type, listener) { (this.handlers[type] ||= []).push(listener); }
  fire(type) {
    const event = {type, target: this, preventDefault() {}};
    for (let e = this; e; e = e.parentNode) {
      for (const listener of e.handlers?.[type] || []) listener(event);
    }
  }
  focus() {}
  select() {}
  reset() { for (const e of this.elements) delete e.currentValue; }
}
function build(spec) {
  if (typeof spec === 'string') return {textContent: spec};
  const el = new Element(spec.tag, spec.attrs);
  for (const child of spec.children) el.appendChild(build(child));
  return el;
}
function mount(search = '') {
  const body = build(payload.tree);
  const document = {
    body, readyState: 'complete',
    getElementById: id => body.querySelector('#' + id),
    querySelectorAll: selector => body.querySelectorAll(selector),
    createElement: tag => new Element(tag),
    createElementNS: (_ns, tag) => new Element(tag),
    createTextNode: text => ({textContent: String(text)}),
  };
  const context = {
    document, location: {search}, navigator: {}, console,
    localStorage: {
      getItem: key => memory.get(key) || null,
      setItem: (key, value) => memory.set(key, String(value)),
      removeItem: key => memory.delete(key),
    },
    fetch: async url => {
      requests.push(url);
      assert.ok(url.startsWith('/data/'), url);
      const response = payload.routes[url];
      return {ok: response !== undefined, json: async () => JSON.parse(JSON.stringify(response))};
    },
  };
  vm.runInNewContext(code, context, {filename: 'tools.js'});
  return {
    get: id => document.getElementById(id),
    set(id, value) { const field = document.getElementById(id); assert.ok(field, id); field.value = value; field.fire('input'); },
    submit: id => document.getElementById(id).fire('submit'),
    click: id => document.getElementById(id).fire('click'),
    flush: () => new Promise(resolve => setImmediate(resolve)),
  };
}
"""


def browser_check(slug, routes, scenario):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    body = guides.tool_page(
        slug, lambda _title, _description, _path, body, _crumbs, **_kw: body,
        guides.tools_context(guides.load_ifs()),
    )
    payload = {"tree": FormTree(body).root, "routes": routes}
    script = DRIVER + "\n(async () => {\n" + scenario + "\n})().catch(e => { console.error(e); process.exit(1); });"
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, input=json.dumps(payload),
        text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def school(urn, name, *, council=None, years=None):
    return {
        "urn": urn, "name": name, "council": council,
        "pupils": 100, "phase": "primary", "academy": False,
        "pta": [], "years": years or [],
    }


def test_pta_added_event_survives_reload():
    browser_check("pta-planner", {}, r"""
      const first = mount();
      first.set('pp-pupils', '100');
      first.set('pp-inc-1', '1000');
      first.click('pp-add');
      first.set('pp-name-4', 'Spring fair');
      first.set('pp-inc-4', '2000');
      first.submit('pp-form');
      assert.match(first.get('pp-out').textContent, /£3,000 in total/);
      assert.equal(JSON.parse(memory.get('moneyToolsDraft')).pta['pp-inc-4'], '2000');

      const reloaded = mount();
      reloaded.submit('pp-form');
      assert.match(reloaded.get('pp-out').textContent, /£3,000 in total/,
        'Reload must restore added events as well as the first three, so the saved total is unchanged');
    """)


def test_budget_draft_preserves_history_and_status():
    s = school("130932", "History School", years=[
        {"y": "2023-24", "income": 3_000_000, "spend": 3_150_000,
         "reserve": 150_000, "balance": -150_000, "pupils": 100},
        {"y": "2024-25", "income": 3_000_000, "spend": 3_010_000,
         "reserve": 140_000, "balance": -10_000, "pupils": 100},
    ])
    browser_check("budget-check", {"/data/s/130932.json": s}, r"""
      const first = mount();
      first.set('bc-urn', '130932');
      first.submit('bc-load');
      await first.flush();
      assert.match(first.get('bc-load-status').textContent, /2 years of published figures/);
      // Stop the forecast after one year, so its status still needs the earlier history.
      first.set('bc-sp-1', '3010000');
      for (const i of [2, 3]) { first.set('bc-inc-' + i, ''); first.set('bc-sp-' + i, ''); }
      first.submit('bc-form');
      const before = first.get('bc-out').querySelector('.lead').textContent;
      assert.match(before, /Heading for deficit/);

      const reloaded = mount();
      await reloaded.flush();
      reloaded.submit('bc-form');
      const after = reloaded.get('bc-out').querySelector('.lead').textContent;
      assert.equal(after, before,
        'Returning to an unchanged saved forecast must not lose its historical deficit streak/runway');
    """)


def test_pta_changing_school_drops_previous_council():
    routes = {
        "/data/s/130932.json": school("130932", "First School", council={"code": "204", "name": "Hackney"}),
        "/data/s/100002.json": school("100002", "Second School"),
        "/data/a/council-204.json": {
            "id": "council-204", "name": "Hackney",
            "by_year": {"2025-26": {"all": {"pta_pp_median": 25}}},
        },
    }
    browser_check("pta-planner", routes, r"""
      const page = mount();
      page.set('pp-inc-1', '1000');
      page.set('pp-urn', '130932');
      page.submit('pp-load');
      await page.flush();
      page.submit('pp-form');
      assert.match(page.get('pp-out').textContent, /Hackney/);

      page.set('pp-urn', '100002');
      page.submit('pp-load');
      await page.flush();
      assert.match(page.get('pp-load-status').textContent, /Second School/);
      page.submit('pp-form');
      assert.doesNotMatch(page.get('pp-out').textContent, /Hackney/,
        'A school without council data must not inherit the previous school council comparison');
    """)


def test_budget_prefill_uses_secondary_threshold_from_published_tags():
    # areas.school_profile preserves GIAS's title-case phase in tags.phase;
    # build_money.school_json includes those tags but has no top-level phase.
    s = school("100001", "Secondary School", years=[
        {"y": "2025-26", "income": 3_000_000, "spend": 3_000_000,
         "reserve": 180_000, "balance": 0, "pupils": 100},
    ])
    del s["phase"]
    s["tags"] = {"phase": "Secondary"}
    s["status"] = "large_reserves"
    browser_check("budget-check", {"/data/s/100001.json": s}, r"""
      const page = mount('?urn=100001');
      await page.flush();
      assert.match(page.get('bc-load-status').textContent, /Loaded Secondary School/);
      page.submit('bc-form');
      assert.match(page.get('bc-out').querySelector('.lead').textContent, /Large reserves/,
        'A 6% reserve is large for a secondary school, whose threshold is 5%, not 8%');
    """)
