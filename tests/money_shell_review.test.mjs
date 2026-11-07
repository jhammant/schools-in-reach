import { test } from 'node:test';
import assert from 'node:assert/strict';
// Small offline DOM fixture for app.js interaction tests. No browser, network, or dependencies.
// It implements DOM/event behavior, not any School Money application logic.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const appSource = readFileSync(new URL('../pipeline/money/assets/app.js', import.meta.url), 'utf8');
const glossary = JSON.parse(readFileSync(new URL('../pipeline/money/assets/glossary.json', import.meta.url), 'utf8'));

function matchesSimple(node, selector) {
  if (!node.tagName) return false;
  let matches = true;
  selector = selector.replace(/:not\(([^)]+)\)/g, (_, excluded) => {
    if (matchesSimple(node, excluded)) matches = false;
    return '';
  });
  selector = selector.replace(/\[([^\]=~]+)(?:([~]?=)["']?([^"'\]]*)["']?)?\]/g, (_, name, op, value) => {
    const actual = node.getAttribute(name);
    if (actual === null || (op === '=' && actual !== value) || (op === '~=' && !actual.split(/\s+/).includes(value))) matches = false;
    return '';
  });
  selector = selector.replace(/\.([\w-]+)/g, (_, name) => {
    if (!node.classList.contains(name)) matches = false;
    return '';
  });
  selector = selector.replace(/#([\w-]+)/g, (_, name) => {
    if (node.id !== name) matches = false;
    return '';
  });
  return matches && (!selector || selector === '*' || node.tagName.toLowerCase() === selector.toLowerCase());
}

function matchesSelector(node, selector) {
  return selector.split(',').some(part => {
    const chain = part.trim().split(/\s+(?![^\[]*\])/);
    if (!matchesSimple(node, chain.pop())) return false;
    let ancestor = node.parentNode;
    while (chain.length) {
      const next = chain.pop();
      while (ancestor && !matchesSimple(ancestor, next)) ancestor = ancestor.parentNode;
      if (!ancestor) return false;
      ancestor = ancestor.parentNode;
    }
    return true;
  });
}

class DomNode {
  constructor(tag, doc, text = '') {
    this.tagName = tag && tag.toUpperCase();
    this.ownerDocument = doc;
    this.parentNode = null;
    this.childNodes = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.style = {};
    this.value = '';
    this._text = text;
  }
  setAttribute(k, v) { this.attributes.set(k, String(v)); }
  getAttribute(k) { return this.attributes.get(k) ?? null; }
  hasAttribute(k) { return this.attributes.has(k); }
  removeAttribute(k) { this.attributes.delete(k); }
  get id() { return this.getAttribute('id') || ''; }
  set id(v) { this.setAttribute('id', v); }
  get className() { return this.getAttribute('class') || ''; }
  set className(v) { this.setAttribute('class', v); }
  get hidden() { return this.hasAttribute('hidden'); }
  set hidden(v) { if (v) this.setAttribute('hidden', ''); else this.removeAttribute('hidden'); }
  get disabled() { return this.hasAttribute('disabled'); }
  set disabled(v) { if (v) this.setAttribute('disabled', ''); else this.removeAttribute('disabled'); }
  get href() { return this.getAttribute('href') || ''; }
  set href(v) { this.setAttribute('href', v); }
  get tabIndex() { return Number(this.getAttribute('tabindex') ?? -1); }
  set tabIndex(v) { this.setAttribute('tabindex', v); }
  get classList() {
    const node = this;
    return {
      contains: c => node.className.split(/\s+/).includes(c),
      add: (...names) => { node.className = [...new Set([...node.className.split(/\s+/).filter(Boolean), ...names])].join(' '); },
      remove: (...names) => { node.className = node.className.split(/\s+/).filter(c => !names.includes(c)).join(' '); },
      toggle(c, force) { const add = force ?? !this.contains(c); if (add) this.add(c); else this.remove(c); return add; },
    };
  }
  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  removeChild(child) {
    this.childNodes.splice(this.childNodes.indexOf(child), 1);
    child.parentNode = null;
    return child;
  }
  get children() { return this.childNodes.filter(c => c.tagName); }
  get textContent() { return this._text + this.childNodes.map(c => c.textContent).join(''); }
  set textContent(v) {
    for (const c of this.childNodes) c.parentNode = null;
    this.childNodes = [];
    this._text = String(v ?? '');
  }
  matches(selector) { return matchesSelector(this, selector); }
  closest(selector) { return this.matches(selector) ? this : this.parentNode?.closest(selector) || null; }
  querySelectorAll(selector) {
    const found = [];
    for (const child of this.children) {
      if (child.matches(selector)) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  contains(node) { return this === node || this.childNodes.some(c => c.contains(node)); }
  get isConnected() { return this.ownerDocument?.contains(this) || false; }
  get offsetParent() { return this.isConnected && !this.closest('[hidden]') ? this.parentNode : null; }
  getBoundingClientRect() { return { left: 20, top: 50, right: 300, bottom: 94, width: 280, height: 44 }; }
  scrollIntoView() {}
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }
  dispatchEvent(event) {
    event.target ??= this;
    event.currentTarget = this;
    event.preventDefault ??= function () { this.defaultPrevented = true; };
    for (const fn of this.listeners.get(event.type) || []) fn(event);
    if (event.bubbles !== false && this.parentNode) this.parentNode.dispatchEvent(event);
    return !event.defaultPrevented;
  }
  click() { return this.dispatchEvent({ type: 'click', bubbles: true }); }
  focus() {
    if (!this.isConnected || this.closest('[hidden]')) return;
    const doc = this.ownerDocument;
    if (doc.activeElement === this) return;
    doc.activeElement?.dispatchEvent({ type: 'focusout', bubbles: true, relatedTarget: this });
    doc.activeElement = this;
    this.dispatchEvent({ type: 'focus', bubbles: false });
    this.dispatchEvent({ type: 'focusin', bubbles: true });
  }
  blur() {
    this.dispatchEvent({ type: 'focusout', bubbles: true });
    this.dispatchEvent({ type: 'blur', bubbles: false });
    this.ownerDocument.activeElement = this.ownerDocument.body;
  }
  createTHead() { return this.appendChild(this.ownerDocument.createElement('thead')); }
  createTBody() { return this.appendChild(this.ownerDocument.createElement('tbody')); }
  insertRow() { return this.appendChild(this.ownerDocument.createElement('tr')); }
  insertCell() { return this.appendChild(this.ownerDocument.createElement('td')); }
  get tBodies() { return this.children.filter(c => c.tagName === 'TBODY'); }
  get rows() { return this.children.filter(c => c.tagName === 'TR'); }
  get cells() { return this.children.filter(c => c.tagName === 'TD' || c.tagName === 'TH'); }
}

class Document extends DomNode {
  constructor() {
    super(null, null);
    this.ownerDocument = this;
    this.documentElement = this.appendChild(this.createElement('html'));
    this.documentElement.setAttribute('data-audience', 'parent');
    this.body = this.documentElement.appendChild(this.createElement('body'));
    this.activeElement = this.body;
  }
  createElement(tag) { return new DomNode(tag, this); }
  createElementNS(ns, tag) { return this.createElement(tag); }
  createTextNode(text) { return new DomNode(null, this, String(text)); }
  getElementById(id) { return this.querySelector('#' + id); }
}

function element(parent, tag, attrs = {}, text = '') {
  const node = parent.ownerDocument.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  node.textContent = text;
  return parent.appendChild(node);
}

async function settle() {
  // Drain the asynchronous fetch/json/render promise chains without wall-clock delays.
  for (let n = 0; n < 30; n++) await Promise.resolve();
}

function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}

function boot({ storage = {}, data = {}, url = 'https://money.schoolsinreach.com/', setup = () => {} } = {}) {
  const document = new Document();
  const timers = new Map();
  let timerId = 0;
  const calls = [];
  const memory = new Map(Object.entries(storage).map(([k, v]) => [k, JSON.stringify(v)]));
  let currentUrl = new URL(url);
  const location = {
    get href() { return currentUrl.href; },
    set href(value) { currentUrl = new URL(String(value), currentUrl); },
    get search() { return currentUrl.search; },
    get pathname() { return currentUrl.pathname; },
  };
  const fixtures = { '/assets/glossary.json': glossary, ...data };
  const ctx = vm.createContext({
    document, Node: DomNode, console, URL, URLSearchParams, location,
    history: { replaceState(_state, _title, value) { location.href = String(value); } },
    localStorage: { getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, String(v)) },
    setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch(url) {
      calls.push(String(url));
      const fixture = fixtures[url];
      return Promise.resolve(fixture).then(value => ({ ok: value != null, status: value == null ? 404 : 200, json: () => Promise.resolve(value) }));
    },
  });
  ctx.window = ctx;
  ctx.innerWidth = 1000;
  ctx.innerHeight = 800;
  setup(document);
  vm.runInContext(appSource, ctx, { filename: 'pipeline/money/assets/app.js' });
  return {
    document, ctx, calls, memory,
    flushTimers() { const pending = [...timers.values()]; timers.clear(); for (const fn of pending) fn(); },
  };
}

const school = {
  urn: '100001', name: 'Example Primary', path: '/school/100001-example-primary/',
  council: { code: '204', name: 'Hackney', path: '/council/hackney/' },
  status: 'healthy', year: '2024-25', pupils: 200,
  income: 1200000, income_pp: 6000, spend: 1100000, spend_pp: 5500,
  reserve: 60000, reserve_pp: 300, share: 0.05, balance: 100000, balance_pp: 500,
  years: [{ y: '2024-25', income: 1200000, spend: 1100000, reserve: 60000, pupils: 200 }],
  pp: { total_income: 6000, total_expenditure: 5500 }, similar: {},
  check: 'https://financial-benchmarking-and-insights-tool.education.gov.uk/school/100001',
};
const searchRows = [
  { t: 'school', id: '100001', name: 'Example Primary', p: school.path },
  { t: 'school', id: '100002', name: 'Example Secondary', p: '/school/100002-example-secondary/' },
  { t: 'council', id: '204', name: 'Example Council', p: '/council/example/' },
];

function money(parent, attrs = {}) {
  return element(parent, 'span', { class: 'mf', 'data-mf': 'total_income', 'data-v': '1200000', 'data-pp': '6000', 'data-year': '2024-25', ...attrs }, '£1.2m');
}

function searchSetup(doc) {
  const form = element(doc.body, 'form');
  element(form, 'input', { id: 'q', type: 'search' });
}

test('control: glossary, nested drill, focus trap, close and focus restoration work after loading', async () => {
  const h = boot({ setup(doc) {
    money(doc.body, { 'data-drill': '#income' });
    element(doc.body, 'script', { id: 'income', type: 'application/json' }, JSON.stringify({
      title: 'Income breakdown', year: '2024-25',
      rows: [{ key: 'grant_funding', label: 'Grants', v: 1000000, pp: 5000 }],
      series: [{ y: '2023-24', v: 1000000 }, { y: '2024-25', v: 1200000 }],
      src: school.check,
    }));
  } });
  const original = h.document.querySelector('.mf');
  original.focus();
  original.click();
  await settle();
  const drill = h.document.querySelector('.drill');
  assert.equal(drill.hidden, false);
  assert.match(drill.textContent, /Income breakdown/);
  assert.match(drill.textContent, /What this means/);
  assert.ok(drill.querySelector('svg'));
  const last = drill.querySelector('a.check');
  last.focus();
  last.dispatchEvent({ type: 'keydown', key: 'Tab' });
  assert.equal(h.document.activeElement, drill.querySelector('button.close'));
  drill.querySelector('.mf').click();
  await settle();
  assert.match(drill.textContent, /Grants/);
  assert.ok(drill.querySelector('button.quiet'));
  h.document.activeElement.dispatchEvent({ type: 'keydown', key: 'Escape' });
  assert.equal(drill.hidden, true);
  assert.equal(h.document.activeElement, original);
});

test('control: pins update buttons, counts and comparison URLs', () => {
  const h = boot({ setup(doc) {
    element(doc.body, 'span', { 'data-pin-count': '' });
    element(doc.body, 'button', { 'data-pin': JSON.stringify({ type: 'school', id: '100001', name: school.name, p: school.path }) });
  } });
  const pin = h.document.querySelector('[data-pin]');
  pin.click();
  assert.equal(pin.getAttribute('aria-pressed'), 'true');
  assert.equal(h.document.querySelector('[data-pin-count]').textContent, '1');
  assert.equal(h.document.querySelector('.pinbar a').href, '/compare/?urns=100001');
  pin.click();
  assert.equal(h.document.querySelector('.pinbar').hidden, true);
});

test('control: search uses the shared index and ArrowDown can navigate', async () => {
  const h = boot({ data: { '/data/search.json': searchRows }, setup: searchSetup });
  const q = h.document.getElementById('q');
  q.focus();
  q.value = 'example';
  q.dispatchEvent({ type: 'input' });
  h.flushTimers();
  await settle();
  assert.equal(h.document.querySelectorAll('[role="option"]').length, 3);
  q.dispatchEvent({ type: 'keydown', key: 'ArrowDown' });
  assert.equal(q.getAttribute('aria-activedescendant'), 'q-opt-0');
  q.dispatchEvent({ type: 'keydown', key: 'Enter' });
  assert.equal(h.ctx.location.href, 'https://money.schoolsinreach.com' + school.path);
});

test('control: focusing a school preview uses the shared school shape and cache', async () => {
  const h = boot({ data: { '/data/s/100001.json': school }, setup(doc) {
    element(doc.body, 'a', { href: school.path, 'data-preview': 'school:100001' }, school.name);
  } });
  const a = h.document.querySelector('a');
  a.focus();
  await settle();
  const preview = h.document.querySelector('.preview');
  assert.equal(preview.hidden, false);
  assert.match(preview.textContent, /Healthy/);
  assert.match(preview.textContent, /£6,000/);
  a.blur();
  a.focus();
  await settle();
  assert.equal(h.calls.filter(x => x === '/data/s/100001.json').length, 1);
});

test('percentages keep their units in both tooltip and drill', async () => {
  // This is the same non-currency figure required in test_site.py's NATIONAL_FIXTURE.
  const h = boot({ setup(doc) {
    element(doc.body, 'span', { class: 'mf', 'data-mf': 'in_deficit_pct', 'data-v': '12.4', 'data-year': '2024-25' }, '12.4%');
  } });
  const figure = h.document.querySelector('.mf');
  figure.focus();
  await settle();
  const tooltip = h.document.getElementById('money-tip').textContent;
  figure.click();
  await settle();
  const headline = h.document.querySelector('.drill .headline').textContent;
  assert.ok(!tooltip.includes('£') && !headline.includes('£'), `Percentage became money: tooltip=${tooltip}; headline=${headline}`);
  assert.match(tooltip, /12\.4%/);
  assert.match(headline, /12\.4%/);
});

test('import is accessible with zero existing pins', async () => {
  const h = boot({ storage: { shortlist: [100001], plan: ['100002'] }, data: { '/data/search.json': searchRows } });
  const imports = h.document.querySelectorAll('button').filter(b => b.textContent.startsWith('Import Schools in Reach'));
  assert.equal(imports.length, 2);
  assert.ok(imports.every(b => !b.closest('[hidden]')), 'Both one-tap import buttons are inside the hidden empty pin bar');
  imports[0].click();
  await settle();
  const saved = JSON.parse(h.memory.get('moneyPinned'));
  assert.equal(saved[0].id, '100001');
  assert.equal(saved[0].name, school.name);
});

test('loading dialog owns keyboard focus and can be escaped before the network replies', async () => {
  const pending = deferred();
  const h = boot({ data: { '/assets/glossary.json': pending.promise }, setup(doc) { money(doc.body); } });
  const figure = h.document.querySelector('.mf');
  figure.focus();
  figure.click();
  const drill = h.document.querySelector('.drill');
  assert.equal(drill.hidden, false);
  assert.ok(drill.contains(h.document.activeElement), 'Visible aria-modal dialog leaves focus on the underlying figure until fetch resolves');
  h.document.activeElement.dispatchEvent({ type: 'keydown', key: 'Escape' });
  assert.equal(drill.hidden, true);
  pending.resolve({});
  await settle();
});

test('closed dialog request cannot overwrite a newly selected figure', async () => {
  const slow = deferred();
  const h = boot({ data: {
    '/data/drill/first.json': slow.promise,
    '/data/drill/second.json': { title: 'Second figure', year: '2024-25', rows: [] },
  }, setup(doc) {
    money(doc.body, { id: 'first', 'data-v': '100', 'data-drill': '/data/drill/first.json' });
    money(doc.body, { id: 'second', 'data-v': '200', 'data-drill': '/data/drill/second.json' });
  } });
  h.document.getElementById('first').click();
  await settle();
  h.document.querySelector('.drill-backdrop').click();
  h.document.getElementById('second').click();
  await settle();
  assert.equal(h.document.getElementById('drill-title').textContent, 'Second figure');
  slow.resolve({ title: 'First figure', year: '2024-25', rows: [] });
  await settle();
  assert.equal(h.document.getElementById('drill-title').textContent, 'Second figure', 'The closed first request replaced the second figure');
});

test('touch preview opens before following the school link', async () => {
  const h = boot({ data: { '/data/s/100001.json': school }, setup(doc) {
    element(doc.body, 'a', { href: school.path, 'data-preview': 'school:100001' }, school.name);
  } });
  const link = h.document.querySelector('a');
  link.dispatchEvent({ type: 'pointerover', pointerType: 'touch' });
  link.dispatchEvent({ type: 'pointerdown', pointerType: 'touch' });
  link.dispatchEvent({ type: 'pointerup', pointerType: 'touch' });
  const click = { type: 'click', pointerType: 'touch', bubbles: true };
  link.dispatchEvent(click);
  h.flushTimers();
  await settle();
  const preview = h.document.querySelector('.preview');
  assert.ok(preview && !preview.hidden, 'Touch is ignored by pointerover and link clicks, so the preview never opens');
  assert.equal(click.defaultPrevented, true, 'The preview tap must not immediately navigate away');
});

test('ArrowUp from an unselected search list chooses the last result', async () => {
  const h = boot({ data: { '/data/search.json': searchRows }, setup: searchSetup });
  const q = h.document.getElementById('q');
  q.focus();
  q.value = 'example';
  q.dispatchEvent({ type: 'input' });
  h.flushTimers();
  await settle();
  q.dispatchEvent({ type: 'keydown', key: 'ArrowUp' });
  const options = h.document.querySelectorAll('[role="option"]');
  assert.equal(q.getAttribute('aria-activedescendant'), options.at(-1).id);
});

test('compare income retains the total and per-pupil money-figure interaction', async () => {
  const h = boot({ url: 'https://money.schoolsinreach.com/compare/?urns=100001', data: { '/data/s/100001.json': school }, setup(doc) {
    const app = element(doc.body, 'section', { id: 'compare-app' });
    element(app, 'ul', { id: 'cmp-chosen' });
    element(app, 'div', { id: 'cmp-out' });
  } });
  await settle();
  const out = h.document.getElementById('cmp-out');
  assert.match(out.textContent, /£6,000/);
  const income = out.querySelector('[data-mf="total_income"]');
  assert.ok(income, 'Compare renders plain per-pupil text, so income has no total, tooltip or drill');
  assert.equal(income.getAttribute('data-v'), '1200000');
  assert.equal(income.getAttribute('data-pp'), '6000');
});
