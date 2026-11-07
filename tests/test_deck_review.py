"""Independent C2 regression probes; fixtures use the gold data and real PTA writer."""

import json
from pathlib import Path
import subprocess

import pytest

from pipeline.money import pta


REPO = Path(__file__).resolve().parents[1]
GOLD = json.loads((REPO / "pipeline/money/data/gold/130932.json").read_text())

JS_SETUP = r"""
const assert = require('node:assert/strict');
require('./pipeline/money/assets/deck.js');
const D = globalThis.MoneyDeck;
const gold = JSON.parse(require('node:fs').readFileSync('pipeline/money/data/gold/130932.json', 'utf8'));
const years = Object.keys(gold.years).sort();
const latest = years.at(-1);
const fin = y => gold.years[y].totals.pipeline_finance_history;
function school() {
  const f = fin(latest);
  return {
    urn: gold.urn, name: gold.name, year: latest,
    council: {code: gold.la.code, name: gold.la.name},
    pupils: f.pupils, status: 'in_deficit', pta: [],
    years: years.map(y => ({y, pupils: fin(y).pupils,
      income: fin(y).total_income, spend: fin(y).total_expenditure,
      reserve: fin(y).revenue_reserve, balance: fin(y).in_year_balance})),
    income_lines: {grant_funding: f.grant_funding,
      self_generated_income: f.self_generated},
  };
}
function series(flags = []) {
  const m = {};
  for (const key of ['total_income', 'total_expenditure', 'revenue_reserve',
    'in_year_balance', 'grant_funding', 'self_generated']) {
    m[key] = Object.fromEntries(years.map(y => [y, {
      v: fin(y)[key], pp: fin(y)[key] / fin(y).pupils,
    }]));
  }
  return {years, source: 'CFR', pupils: Object.fromEntries(years.map(y => [y, fin(y).pupils])), m, flags};
}
"""


def run_node(body):
    result = subprocess.run(
        ["node"], input=JS_SETUP + "\n" + body,
        cwd=REPO, text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ptfa_preserves_history_emitted_by_pta_writer_without_sx():
    # Arrange: use the actual producer, whose period_end precision is YYYY-MM.
    number = GOLD["ptfa"]["charity_number"]
    matches = {str(GOLD["urn"]): [{"charity_number": number, "name": GOLD["ptfa"]["name"]}]}
    returns = [
        {"registered_charity_number": number, "fin_period_end_date": row["period"][-10:],
         "total_gross_income": row["income"], "total_gross_expenditure": row["expenditure"]}
        for row in GOLD["ptfa"]["years"].values()
    ]
    pta.attach_history(matches, returns)
    run_node("const charities = " + json.dumps(matches[str(GOLD["urn"])]) + r""";
const s = school();
s.pta = charities;
// Act: /data/sx is optional, so /data/s history must supply the chart.
const deck = D.ptfaDeck(D.adapt(s, null, null, null));
const slide = deck.slides.find(s => s.id === 'pta_money');
// Assert: all published income and spending survive the adapter.
assert.ok(slide.chart, 'The producer supplied five charity years, but the deck dropped all of them');
for (const [key, field] of [['pta_income', 'income'], ['pta_spend', 'expenditure']]) {
  assert.deepEqual(slide.chart.series.find(s => s.key === key).points.map(p => p.v),
    Object.keys(gold.ptfa.years).sort().map(y => gold.ptfa.years[y][field]));
}
""")


def test_december_charity_year_keeps_matching_per_pupil_values():
    run_node(r"""
// Arrange: contract year labels and an actual calendar-year charity return.
const s = school();
s.pta = [{charity_number: '1234567', name: 'Parents association', history: [
  {period_end: '2025-12-31', income: 40000, expenditure: 30000},
]}];
const sx = series();
sx.pta = {'2024-25': {income: 40000, spend: 30000,
  income_pp: 40000 / fin('2024-25').pupils,
  spend_pp: 30000 / fin('2024-25').pupils, charity_number: '1234567'}};
// Act.
const deck = D.ptfaDeck(D.adapt(s, sx, null, null));
// Assert: December must match the same end-year school row, like other months.
const figure = deck.slides.find(s => s.id === 'pta_money').figures[0];
assert.equal(figure.pp, Math.round(sx.pta['2024-25'].income_pp),
  'A December charity period must not lose its available per-pupil value');
""")


def test_compare_keeps_distinct_schools_that_share_a_name():
    run_node(r"""
// Arrange: URNs differ but school names need not be unique.
const a = school();
const b = school();
b.urn = '100002';
b.years = b.years.map(r => ({...r, income: r.income * 2}));
// Act: chartData feeds both the on-screen SVG and PowerPoint native chart.
const deck = D.compareDeck([a, b]);
const chart = deck.slides.find(s => s.id === 'income').chart;
const rendered = D.chartData(chart);
// Assert: neither school's measurement may be overwritten by the other's name.
assert.deepEqual(rendered.flatMap(s => s.values).filter(v => v !== null),
  chart.series.flatMap(s => s.points.map(p => p.v)));
""")


@pytest.mark.parametrize("all_years", [False, True], ids=["latest_flagged", "all_flagged"])
def test_school_headline_figures_never_use_suspect_years(all_years):
    flags = "years" if all_years else "[latest]"
    run_node("const flags = " + flags + r""";
// Arrange / Act.
const deck = D.schoolDeck(D.adapt(school(), series(flags), null, null));
// Assert: flagged measurements stay in the charts, never in headline figures.
const funding = deck.slides.find(s => s.id === 'funding').chart;
assert.ok(funding.series[0].points.some(p => p.suspect));
const headlines = deck.slides.flatMap(s => s.figures.map(f => ({slide: s.id, ...f})));
assert.deepEqual(headlines.filter(f => flags.includes(f.year)), [],
  'Headline figures must use a trustworthy year or explain that none is available');
""")


def test_income_summary_fallback_keeps_the_totals_year_and_denominator():
    run_node(r"""
// Arrange: the latest year is flagged and one series metric is missing.
// income_lines is still the latest /data/s snapshot, not the prior year's data.
const s = school();
const sx = series([latest]);
delete sx.m.grant_funding;
// Act.
const deck = D.schoolDeck(D.adapt(s, sx, null, null));
const slide = deck.slides.find(s => s.id === 'income');
// Assert: omission is honest; displaying a value with another year's label isn't.
for (const f of slide.figures.filter(f => f.key === 'grant_funding')) {
  assert.equal(f.v, Math.round(fin(f.year).grant_funding),
    'The grant total must come from the year printed beside it');
  assert.equal(f.pp, Math.round(fin(f.year).grant_funding / fin(f.year).pupils),
    'The denominator must be the same year as the displayed total');
}
""")


@pytest.mark.parametrize("route", ["compare", "area"])
@pytest.mark.parametrize("failure", ["404", "bad_json"])
def test_fetch_failures_are_explained_on_a_slide(route, failure):
    run_node("const scenario = " + json.dumps({"route": route, "failure": failure}) + r""";
// A minimal DOM records the same nodes the browser displays. All fetches are
// stubbed; no network, browser dependency, or repository-external file is used.
class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attributes = {};
    this._text = '';
    this.className = '';
    const updateClass = (name, on) => {
      const classes = new Set(this.className.split(/\s+/).filter(Boolean));
      if (on) classes.add(name); else classes.delete(name);
      this.className = [...classes].join(' ');
    };
    this.classList = {add: name => updateClass(name, true), toggle: updateClass};
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(x => x.textContent).join(' '); }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
}
const app = new Element('div');
const message = new Element('p');
const nodes = {'deck-app': app, 'deck-msg': message, 'deck-live': new Element('p'),
  'deck-count': new Element('span'), 'deck-context': new Element('script')};
nodes['deck-context'].textContent = '{}';
const testDocument = {
  getElementById: id => nodes[id] || null,
  querySelector: () => null,
  createElement: tag => new Element(tag),
  createElementNS: (ns, tag) => new Element(tag),
  createTextNode: text => ({textContent: text}),
  addEventListener() {},
};
const a = {...school(), urn: '100001', name: 'School One'};
const b = {...school(), urn: '100002', name: 'School Two'};
const docs = {
  '/data/s/100001.json': a, '/data/s/100002.json': b,
  '/data/sx/100001.json': series(), '/data/sx/100002.json': series(),
  '/data/sx/100003.json': series(),
  '/data/a/constituency-E123.json': {id: 'constituency-E123', type: 'constituency',
    name: 'Example constituency', pupils_by_year: {[latest]: 1000},
    by_year: {[latest]: {all: {schools: 10, in_deficit: 2, in_deficit_pct: 20,
      income_pp_median: 9000, spend_pp_median: 9100, reserve_median_pp: 200,
      grant_pp_median: 8500, pta_pp_median: 100, pta_schools: 5}}}},
};
const failedPath = scenario.route === 'compare' ? '/data/s/100003.json' : '/data/a/england.json';
const fetch = async url => {
  if (url === failedPath) {
    return scenario.failure === '404'
      ? {ok: false, status: 404}
      : {ok: true, json: async () => { throw new SyntaxError('Invalid JSON'); }};
  }
  assert.ok(url in docs, 'Unexpected request: ' + url);
  return {ok: true, json: async () => docs[url]};
};
const location = {origin: 'https://review.invalid', pathname: '/deck/', hash: '',
  search: scenario.route === 'compare' ? '?urns=100001,100002,100003&view=compare' : '?area=constituency-E123'};
require('node:vm').runInNewContext(
  require('node:fs').readFileSync('pipeline/money/assets/deck.js', 'utf8'),
  {document: testDocument, fetch, location, URLSearchParams, history: {replaceState() {}}},
);
// Allow the fetch promise chain and render to finish.
setImmediate(() => {
  const slides = app.children.filter(e => e.tagName === 'SECTION');
  assert.ok(slides.length, 'The deck must render');
  const slideText = slides.map(e => e.textContent).join(' ');
  assert.ok(
    /not published|aren.t published|not readable|not available|unavailable|unreadable|couldn.t (?:be )?load|could not (?:be )?load|failed to load|missing/i.test(slideText),
    'Fetch failures must be explained inside a slide, so print and PowerPoint preserve the warning');
});
""")
