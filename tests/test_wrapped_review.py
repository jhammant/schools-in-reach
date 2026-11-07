"""Offline regression probes for the C3 independent review."""

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMMON = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
require('./pipeline/money/assets/wrapped.js');
const MW = globalThis.MoneyWrapped;
const gold = JSON.parse(fs.readFileSync('./pipeline/money/data/gold/130932.json', 'utf8'));
const years = Object.keys(gold.years).sort();
const pf = y => gold.years[y].totals.pipeline_finance_history;
const last = years.at(-1);
function fixture() {
  const s = {
    urn: gold.urn, name: gold.name,
    path: '/school/130932-william-patten-primary-school/',
    year: last, status: 'in_deficit', academy: false,
    council: {code: '204', name: 'Hackney'},
    tags: {phase: 'primary', governance: 'council-run'},
    years: years.map(y => ({y, income: pf(y).total_income,
      spend: pf(y).total_expenditure, reserve: pf(y).revenue_reserve,
      pupils: pf(y).pupils})),
    similar: {total_expenditure: 8650},
    pta: [{charity_number: String(gold.ptfa.charity_number), name: gold.ptfa.name}]
  };
  const sx = {years, pupils: {}, m: {}, pta: {}, flags: []};
  for (const y of years) {
    sx.pupils[y] = pf(y).pupils;
    for (const key of ['total_income', 'total_expenditure', 'revenue_reserve', 'grant_funding']) {
      sx.m[key] ||= {};
      sx.m[key][y] = {v: pf(y)[key], pp: pf(y)[key] / pf(y).pupils};
    }
  }
  for (const [y, p] of Object.entries(gold.ptfa.years)) {
    sx.pta[y] = {income: p.income, spend: p.expenditure,
      income_pp: p.income / pf(y).pupils, spend_pp: p.expenditure / pf(y).pupils};
  }
  return {s, sx};
}
function cards(f, mode='school', england=null) {
  return MW.buildCards(MW.adapt(f.s, f.sx, null, england, null), mode).cards;
}
"""


def run_node(body):
    result = subprocess.run(
        ["node", "-e", COMMON + "\n" + body],
        cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_comparison_does_not_headline_a_flagged_year():
    run_node(r"""
const f = fixture();
f.sx.flags = [{year: last, code: 'unusual', text: 'Published figure needs checking'}];
const story = cards(f);
assert.equal(story.find(c => c.id === 'reserve').chart.points.at(-1).suspect, true);
const c = story.find(c => c.id === 'similar');
const flaggedPP = Math.round(pf(last).total_expenditure / pf(last).pupils);
assert.ok(!c || !c.big || c.big.v !== flaggedPP,
  'The comparison still headlines the flagged latest-year spending: ' + JSON.stringify(c && c.big));
""")


def test_all_flagged_reserves_remain_visible_in_the_chart():
    run_node(r"""
const f = fixture();
f.sx.flags = [...years];
const c = cards(f).find(c => c.id === 'reserve');
assert.ok(c.chart, 'Published reserves must remain plotted even when none can be used as a headline');
assert.deepEqual(c.chart.points.map(p => [p.y, p.v, p.suspect]),
  years.map(y => [y, pf(y).revenue_reserve, true]));
assert.match(c.lines.join(' '), /marked|unusual|check/i);
""")


@pytest.mark.parametrize("has_published_pp", [False, True])
def test_pta_per_pupil_uses_only_same_year_data(has_published_pp):
    setting = "const hasPublishedPP = " + str(has_published_pp).lower() + ";\n"
    run_node(setting + r"""
const f = fixture();
const ptaYear = Object.keys(f.sx.pta).sort().at(-1);
const expectedIncome = hasPublishedPP ? Math.round(f.sx.pta[ptaYear].income_pp) : null;
const expectedSpend = hasPublishedPP ? Math.round(f.sx.pta[ptaYear].spend_pp) : null;
if (!hasPublishedPP) {
  delete f.sx.pta[ptaYear].income_pp;
  delete f.sx.pta[ptaYear].spend_pp;
}
delete f.sx.pupils[ptaYear];
delete f.s.years.find(r => r.y === ptaYear).pupils;
const c = cards(f, 'ptfa').find(c => c.id === 'pta-money');
const income = c.figures.find(v => v.key === 'pta_income');
const spending = c.figures.find(v => v.key === 'pta_spend');
assert.equal(spending.year, ptaYear);
assert.equal(income.pp, expectedIncome, 'Do not invent PTA per-pupil income from a different year\'s pupils');
assert.equal(spending.pp, expectedSpend,
  'An explicitly published spend_pp must not be replaced by division using a different year\'s pupils');
""")


def test_national_pta_gap_survives_a_later_year_without_returns():
    run_node(r"""
const f = fixture();
const england = {by_year: {
  '2024-25': {all: {schools: 20100, pta_schools: 9100,
    pta_pp_median: 31, pta_pp_by_band: {'1': 96, '5': 6}}},
  '2025-26': {all: {schools: 20100, pta_schools: 0, pta_pp_median: null}}
}};
const c = cards(f, 'ptfa', england).find(c => c.id === 'pta-gap');
assert.ok(c, 'The required national PTA gap is available in 2024-25 and must not disappear');
assert.ok(c.figures.every(v => v.year === '2024-25'), 'Use the year of the PTA figures');
assert.deepEqual(c.figures.filter(v => /^pta_band/.test(v.key)).map(v => v.pp), [96, 6]);
""")


def test_outro_keeps_the_complete_school_url_when_qr_is_unavailable():
    run_node(r"""
const f = fixture();
// A normal school slug at the existing 80-character slug limit.
f.s.path = '/school/130932-st-mary-and-st-johns-church-of-england-voluntary-aided-primary-school-and-nursery/';
const c = cards(f).find(c => c.id === 'outro');
const drawn = [];
const g = {
  font: '',
  // The same deterministic font-width model used by the unit's canvas tests.
  measureText(t) { return {width: String(t).length * Number(/(\d+)px/.exec(this.font)?.[1] || 10) * 0.55}; },
  fillText(t) { drawn.push(String(t)); }
};
for (const k of ['save', 'restore', 'fillRect', 'beginPath', 'moveTo', 'lineTo', 'stroke', 'fill', 'arc', 'rect', 'roundRect']) g[k] = () => {};
MW.drawCard(g, c, 1, {}, {qr: null});
const url = c.qr.url.replace(/^https?:\/\//, '');
assert.ok(drawn.join('').includes(url), 'QR fallback truncates the destination URL: ' + drawn.join(' | '));
""")


def test_interrupted_response_body_renders_a_failure_card():
    run_node(r"""
const vm = require('node:vm');
const errors = [];
process.on('unhandledRejection', error => errors.push(error));
// Minimal DOM and canvas surfaces; all fetches are local fakes and no timers advance the story.
const g = {font: '', measureText(t) { return {width: String(t).length * 16}; }};
for (const k of ['save', 'restore', 'fillRect', 'fillText', 'beginPath', 'moveTo', 'lineTo', 'stroke', 'fill', 'arc', 'rect', 'roundRect']) g[k] = () => {};
class Element {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.attrs = {}; this.style = {}; this.className = ''; this._text = ''; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  appendChild(e) { if (e.parent) e.parent.removeChild(e); this.children.push(e); e.parent = this; return e; }
  removeChild(e) { this.children = this.children.filter(c => c !== e); e.parent = null; }
  get firstChild() { return this.children[0] || null; }
  set textContent(t) { this._text = String(t); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  addEventListener() {}
  getContext() { return g; }
  focus() {}
  contains(e) { return e === this || this.children.some(c => c.contains(e)); }
  querySelector(selector) { return descendants(this).find(c => selector[0] === '.' ? c.className.split(' ').includes(selector.slice(1)) : c.tagName === selector.toUpperCase()) || null; }
}
function descendants(e) { return e.children.flatMap(c => [c, ...descendants(c)]); }
const rootEl = new Element('main');
rootEl.setAttribute('data-urn', gold.urn);
rootEl.setAttribute('data-name', gold.name);
rootEl.setAttribute('data-path', '/school/130932-william-patten-primary-school/');
const doc = {
  readyState: 'complete', documentElement: new Element('html'),
  body: new Element('body'), head: new Element('head'),
  createElement: tag => new Element(tag), createTextNode: t => {const e = new Element('span'); e.textContent = t; return e;},
  getElementById: id => id === 'wrapped-app' ? rootEl : null,
  addEventListener() {}
};
doc.activeElement = doc.body;
const context = {
  document: doc, location: {search: ''}, URLSearchParams, Blob,
  performance: {now: () => 100},
  matchMedia: () => ({matches: true, addEventListener() {}}),
  getComputedStyle: () => ({getPropertyValue: () => '#000000'}),
  requestAnimationFrame: () => 1, cancelAnimationFrame() {}, setTimeout, clearTimeout,
  fetch: () => Promise.resolve({ok: true, text: () => Promise.reject(new Error('Connection closed while reading JSON'))})
};
vm.runInNewContext(fs.readFileSync('./pipeline/money/assets/wrapped.js', 'utf8'), context);
setTimeout(() => {
  try {
    assert.equal(errors.length, 0, 'Response-body failure escaped without a card: ' + errors.map(e => e.message).join('; '));
    const canvas = rootEl.querySelector('canvas');
    assert.ok(canvas, 'The story must replace its loading message with a failure card');
    assert.match(canvas.getAttribute('aria-label'), /couldn't load|try again|not ready|unavailable|not published/i);
  } catch (error) { console.error(error); process.exitCode = 1; }
}, 20);
""")
