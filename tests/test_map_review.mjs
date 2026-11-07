// Offline review regressions: execute the unmodified map script with a small DOM
// and Leaflet event double, so fetch ordering and real event handlers are exercised.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const mapSource = readFileSync(new URL('../pipeline/money/assets/map.js', import.meta.url), 'utf8');
const appSource = readFileSync(new URL('../pipeline/money/assets/app.js', import.meta.url), 'utf8');
const years = ['2024-25', '2025-26'];
const meta = {
  pct_in_deficit: { label: 'Share of schools in deficit', unit: 'pct', scale: 'sequential', signed: false,
    source: 'DfE CFR and AAR returns', levels: ['england', 'council', 'constituency'] },
  dsg_pp: { label: 'Council high-needs balance per pupil', unit: 'gbp_pp', scale: 'diverging', signed: true,
    source: 'DfE section 251', levels: ['england', 'council'] },
};

class Element {
  constructor(tag, doc) {
    this.tagName = tag.toUpperCase(); this.doc = doc; this.children = []; this.attrs = {};
    this.listeners = {}; this.style = {}; this.hidden = false; this.value = ''; this._text = '';
    this.classList = {
      add: (...names) => { this.className = [...new Set([...this.className.split(' '), ...names])].join(' '); },
      toggle: (name, on) => {
        const names = new Set(this.className.split(' '));
        if (on) names.add(name); else names.delete(name);
        this.className = [...names].join(' ');
      },
    };
  }
  set id(v) { this.setAttribute('id', v); }
  get id() { return this.getAttribute('id') || ''; }
  set className(v) { this.setAttribute('class', v); }
  get className() { return this.getAttribute('class') || ''; }
  set textContent(v) { this.children.forEach(c => { c.parentNode = null; }); this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  get firstChild() { return this.children[0] || null; }
  get name() { return this.getAttribute('name') || ''; }
  get options() { return this.children.filter(c => c.tagName === 'OPTION'); }
  get tBodies() { return this.children.filter(c => c.tagName === 'TBODY'); }
  get rows() { return this.children.filter(c => c.tagName === 'TR'); }
  get cells() { return this.children.filter(c => ['TH', 'TD'].includes(c.tagName)); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return Object.hasOwn(this.attrs, k) ? this.attrs[k] : null; }
  hasAttribute(k) { return Object.hasOwn(this.attrs, k); }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(c) {
    if (c.tagName === '#FRAGMENT') { [...c.children].forEach(child => this.appendChild(child)); return c; }
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this; this.children.push(c); return c;
  }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); c.parentNode = null; return c; }
  insertBefore(c, before) {
    if (!before) return this.appendChild(c);
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this; this.children.splice(this.children.indexOf(before), 0, c); return c;
  }
  matches(selector) {
    const tag = selector.match(/^[a-z]+/i)?.[0];
    if (tag && this.tagName !== tag.toUpperCase()) return false;
    const id = selector.match(/#([\w-]+)/)?.[1];
    if (id && this.id !== id) return false;
    for (const [, name] of selector.matchAll(/\.([\w-]+)/g)) if (!this.className.split(/\s+/).includes(name)) return false;
    for (const [, key, value] of selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)) {
      if (!this.hasAttribute(key) || (value !== undefined && this.getAttribute(key) !== value)) return false;
    }
    return true;
  }
  querySelectorAll(selector) {
    const parts = selector.split(' '), last = parts.pop(), out = [];
    const visit = node => node.children.forEach(child => {
      if (child.matches(last)) {
        let parent = child.parentNode, i = parts.length - 1;
        while (parent && i >= 0) { if (parent.matches(parts[i])) i--; parent = parent.parentNode; }
        if (i < 0) out.push(child);
      }
      visit(child);
    });
    visit(this); return out;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parentNode?.closest(selector); }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  fire(type) {
    const event = { target: this, preventDefault() {}, stopPropagation() {} };
    for (let node = this; node; node = node.parentNode) for (const fn of node.listeners[type] || []) fn(event);
  }
  click() { this.fire('click'); }
  focus() { this.doc.activeElement = this; }
  contains(node) { return node === this || this.children.some(c => c.contains(node)); }
  scrollIntoView() {}
}

function fixtureDOM(context) {
  const doc = new Element('#document'); doc.doc = doc;
  doc.createElement = tag => new Element(tag, doc);
  doc.createElementNS = (_, tag) => doc.createElement(tag);
  doc.createDocumentFragment = () => doc.createElement('#fragment');
  doc.createTextNode = text => { const n = doc.createElement('#text'); n.textContent = text; return n; };
  doc.getElementById = id => doc.querySelector('#' + id);
  const add = (parent, tag, id, cls) => {
    const n = doc.createElement(tag); if (id) n.id = id; if (cls) n.className = cls; return parent.appendChild(n);
  };
  doc.documentElement = add(doc, 'html'); doc.body = add(doc.documentElement, 'body');
  const block = add(doc.body, 'script', 'mx-context'); block.textContent = JSON.stringify(context);
  const host = add(doc.body, 'div', 'money-map');
  host.setAttribute('data-default-measure', 'pct_in_deficit'); host.setAttribute('data-default-year', years.at(-1));
  host.setAttribute('data-years', JSON.stringify(years));
  const controls = add(doc.body, 'div', 'mx-controls');
  const measure = add(controls, 'select', 'mx-measure');
  for (const key of Object.keys(meta)) { const opt = add(measure, 'option'); opt.value = key; }
  add(controls, 'input', 'mx-year'); add(controls, 'output', 'mx-year-out');
  for (const geo of ['council', 'constituency']) {
    const r = add(controls, 'input'); r.setAttribute('name', 'g'); r.value = geo;
  }
  add(controls, 'input', 'mx-q'); const list = add(controls, 'ul', 'mx-q-list'); list.hidden = true;
  add(doc.body, 'div', 'mx-legend');
  const card = add(doc.body, 'div', 'mx-card'); card.hidden = true;
  add(card, 'button', null, 'mx-close'); add(card, 'div', null, 'mx-card-body');
  const tablebox = add(doc.body, 'section', null, 'mx-tablebox'); add(tablebox, 'h2', 'mx-table-h');
  const table = add(tablebox, 'table', 'mx-table'); table.setAttribute('data-sortable', '');
  add(table, 'caption'); const head = add(table, 'thead'), tr = add(head, 'tr');
  add(tr, 'th'); add(tr, 'th'); add(table, 'tbody');
  return doc;
}

function feature(id, name) {
  return { type: 'Feature', properties: { id, name }, geometry: { type: 'Polygon', coordinates: [[[0, 51], [1, 51], [0, 52], [0, 51]]] } };
}
function deferred() {
  let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve };
}
const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };

async function boot({ search = '', omitArea = false, holdMeasures = false, holdConstituencies = false, schoolDoc } = {}) {
  const area = { name: 'Hackney', p: '/council/hackney/', m: {
    pct_in_deficit: { '2024-25': 10, '2025-26': 20 }, dsg_pp: { '2025-26': -50 },
  } };
  const data = { years, measures: meta, england: { pct_in_deficit: { '2024-25': 11, '2025-26': 12 } },
    council: omitArea ? {} : { 'council-204': area },
    constituency: { 'constituency-E14001272': { name: 'Hackney North', p: '/constituency/E14001272/', m: { pct_in_deficit: { '2025-26': 30 } } } },
  };
  const context = { years, measures: meta, data: { measures: '/data/map/measures.json', council: '/data/map/councils.geojson',
    constituency: '/data/map/constituencies.geojson', schools: '/data/map/schools.json' } };
  const doc = fixtureDOM(context), pending = deferred(), pendingConstituencies = deferred(), requests = [];
  const routes = {
    '/data/map/measures.json': data,
    '/data/map/councils.geojson': { features: [feature('council-204', 'Hackney')] },
    '/data/map/constituencies.geojson': { features: [feature('constituency-E14001272', 'Hackney North')] },
    '/data/search.json': [
      { t: 'council', id: '204', name: 'Hackney' },
      { t: 'constituency', id: 'E14001272', name: 'Hackney North' },
      { t: 'school', id: '130932', name: 'William Patten' },
    ],
    '/data/map/schools.json': { key: { status: [], phase: [], governance: [] }, rows: [] },
    '/data/s/130932.json': schoolDoc,
    '/data/a/council-204.json': { id: 'council-204', name: 'Hackney', path: '/council/hackney/',
      by_year: { '2024-25': { all: { schools: 10, in_deficit: 1 } }, '2025-26': { all: { schools: 10, in_deficit: 2 } } } },
  };
  const layers = new Map(), geoLayers = [], overlay = doc.createElement('div');
  const map = {
    zoom: 6, on() {}, fitBounds() {}, getContainer: () => doc.getElementById('money-map'),
    getPanes: () => ({ overlayPane: overlay }), getZoom() { return this.zoom; },
    getBounds: () => ({ pad() { return this; }, contains: () => true }), removeLayer() {},
    flyTo(_, z) { this.zoom = z; }, setView(_, z) { this.zoom = z; },
  };
  const group = { addTo() { return this; }, clearLayers() {}, eachLayer() {} };
  const L = {
    map: () => map, canvas: () => ({}), layerGroup: () => group,
    geoJSON(collection, options) {
      const group = { addTo() { return this; }, setStyle() {}, resetStyle() {} }; geoLayers.push(collection);
      for (const f of collection.features) {
        const layer = { events: {}, bindTooltip(fn) { this.tooltip = fn; return this; },
          on(type, fn) { this.events[type] = fn; return this; }, setStyle() {}, bringToFront() {}, getBounds: () => [] };
        layers.set(f.properties.id, layer); options.style(f); options.onEachFeature(f, layer);
      }
      return group;
    },
  };
  const location = { search, pathname: '/map/', hash: '' }, urls = [];
  const sandbox = vm.createContext({ console, setTimeout, clearTimeout, URLSearchParams,
    localStorage: { getItem: () => null }, location,
    history: { replaceState(_, __, url) { urls.push(url); location.search = url.includes('?') ? url.slice(url.indexOf('?')) : ''; } },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    getComputedStyle: () => ({ colorScheme: 'light', getPropertyValue: () => '#777777' }),
    fetch: async url => {
      requests.push(url); if (holdMeasures && url === '/data/map/measures.json') await pending.promise;
      if (holdConstituencies && url === '/data/map/constituencies.geojson') await pendingConstituencies.promise;
      const body = routes[url]; return { ok: body !== undefined, json: async () => body };
    }, L,
  });
  vm.runInContext(appSource, sandbox); // the actual MoneyApp pure helpers
  sandbox.document = doc;
  vm.runInContext(mapSource, sandbox);
  await flush();
  return { doc, layers, data, requests, urls, routes, sandbox, geoLayers,
    releaseMeasures: async () => { pending.resolve(); await flush(); },
    releaseConstituencies: async () => { pendingConstituencies.resolve(); await flush(); } };
}

test('control: normal load renders the table and opens and closes a populated area card', async () => {
  // Arrange
  const app = await boot();
  assert.match(app.doc.getElementById('mx-table').textContent, /Hackney.*20\.0%/);
  // Act
  app.layers.get('council-204').events.click(); await flush();
  // Assert
  const card = app.doc.getElementById('mx-card');
  assert.equal(card.hidden, false);
  assert.match(card.textContent, /Hackney.*20\.0%/);
  assert.equal(JSON.parse(card.querySelector('[data-pin]').getAttribute('data-pin')).id, 'council-204');
  card.querySelector('.mx-close').click();
  assert.equal(card.hidden, true);
  assert.equal(app.doc.activeElement, app.doc.getElementById('money-map'));
});

test('fractional pupil legend ranges contain their classified values', () => {
  // Arrange: pupil counts are FTEs, preserved to 0.1 by build_measures.
  const sandbox = vm.createContext({}); vm.runInContext(mapSource, sandbox);
  const M = sandbox.MoneyMap, values = [100.1, 100.2, 100.3, 100.4, 100.5];
  // Act
  const bins = M.binsFor(values, { scale: 'sequential', unit: 'pupils' });
  // Assert: displayed inclusive intervals must contain the values they colour.
  for (const v of values) {
    const range = bins.classes[M.classify(v, bins)];
    assert.ok(range.lo <= v && range.hi >= v, `${v} assigned to ${range.lo}..${range.hi}`);
  }
});

test('boundary without measures has a named no-data tooltip', async () => {
  // Arrange / Act: a boundary can exist even when no school return populated the aggregate.
  const { layers } = await boot({ omitArea: true });
  const tooltip = layers.get('council-204').tooltip();
  // Assert
  assert.match(tooltip.textContent, /Hackney/);
  assert.match(tooltip.textContent, /not published|no data/i);
});

test('boundary tooltip remains usable while new geography is loading', async () => {
  // Arrange: councils remain on screen until the first constituency fetch completes.
  const app = await boot({ holdConstituencies: true });
  const constituency = app.doc.querySelectorAll('input[name="g"]').find(r => r.value === 'constituency');
  // Act
  constituency.fire('change'); await flush();
  const tooltip = app.layers.get('council-204').tooltip();
  // Assert: the visible council must still use council figures, not the new geography's block.
  assert.match(tooltip.textContent, /Hackney/);
  assert.match(tooltip.textContent, /20\.0%/);
  await app.releaseConstituencies();
});

test('area card waits for measures before displaying a query selection', async () => {
  // Arrange: search and boundaries are cached; the larger measures download is slower.
  const app = await boot({ search: '?q=Hackney', holdMeasures: true });
  // Act
  await app.releaseMeasures();
  // Assert: a successfully fetched dataset must replace any loading/failure placeholder.
  const card = app.doc.getElementById('mx-card');
  assert.equal(card.hidden, false);
  assert.match(card.textContent, /Hackney/);
  assert.match(card.textContent, /20\.0%/);
});

test('constituency search resets a council-only measure', async () => {
  // Arrange: choose the DSG measure using the real control handler.
  const app = await boot();
  const input = app.doc.getElementById('mx-measure'); input.value = 'dsg_pp'; input.fire('change');
  await flush();
  // Act: select a constituency from the combobox.
  const q = app.doc.getElementById('mx-q'); q.value = 'Hackney North'; q.fire('input');
  await new Promise(r => setTimeout(r, 100)); await flush();
  app.doc.getElementById('mx-q-list').children[0].click(); await flush();
  // Assert: the same geography rules must apply to search as to the radio controls.
  assert.equal(input.value, 'pct_in_deficit');
  assert.match(app.doc.getElementById('mx-card').textContent, /30\.0%/);
});

test('area card refreshes when the selected year changes', async () => {
  // Arrange
  const app = await boot(); app.layers.get('council-204').events.click(); await flush();
  assert.match(app.doc.getElementById('mx-card').textContent, /20\.0%/);
  // Act
  const slider = app.doc.getElementById('mx-year'); slider.value = '0'; slider.fire('input'); await flush();
  // Assert: if the card stays open, it must show the selected year and value.
  const card = app.doc.getElementById('mx-card');
  assert.ok(card.hidden || /Share of schools in deficit, 2024-25.*10\.0%/.test(card.textContent), card.textContent);
});

test('partial school response retains the requested identity and open link', async () => {
  // Arrange: JSON was fetched but is missing the identity fields.
  const app = await boot({ search: '?q=William%20Patten', schoolDoc: { pupils: 432.5, year: '2025-26' } });
  // Assert: missing fields must not discard the known search identity or navigation.
  const card = app.doc.getElementById('mx-card');
  assert.match(card.textContent, /William Patten/);
  assert.ok(card.querySelector('a.mx-open'));
  const pin = card.querySelector('[data-pin]'); assert.ok(pin);
  assert.equal(JSON.parse(pin.getAttribute('data-pin')).id, '130932');
});

test('search edits update the URL query state', async () => {
  // Arrange
  const app = await boot({ search: '?q=Hackney' });
  const q = app.doc.getElementById('mx-q');
  // Act: edit the selected search, then clear it.
  q.value = 'Camden'; q.fire('input');
  await new Promise(r => setTimeout(r, 100)); await flush();
  // Assert: sharing/reloading the URL must preserve the current input, not the old selection.
  assert.equal(new URLSearchParams(app.sandbox.location.search).get('q'), 'Camden');
  q.value = ''; q.fire('input');
  await new Promise(r => setTimeout(r, 100)); await flush();
  assert.equal(new URLSearchParams(app.sandbox.location.search).has('q'), false);
});
