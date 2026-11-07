"""Offline counterexamples for the comparisons-stories independent review."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON = r"""
const assert = require('node:assert/strict');
require('./pipeline/money/assets/wrapped.js');
require('./pipeline/money/assets/deck.js');
const W = globalThis.MoneyWrapped;
const D = globalThis.MoneyDeck;
const year = '2024-25';
function fixture() {
  const s = {
    urn: '130932', name: 'William Patten Primary School',
    year, pupils: 437.5, status: 'healthy', academy: false,
    council: {code: '204', name: 'Hackney'},
    years: [{y: year, pupils: 437.5, income: 3861666,
      spend: 3831287, reserve: 10000}],
    pta: [{charity_number: 1103834, name: 'William Patten PTFA',
      history: [{period_end: '2025-08', income: 48547, expenditure: 50100}]}],
  };
  const sx = {
    years: [year], pupils: {[year]: 437.5}, m: {},
    source: {[year]: 'CFR'}, flags: {suspect: {}},
    pta: {[year]: {income: 48547, spend: 50100, income_pp: 111,
      spend_pp: 115, charity_number: 1103834, confidence: 'high'}},
  };
  const council = {id: 'council-204', type: 'council', name: 'Hackney',
    by_year: {[year]: {all: {schools: 60, pta_schools: 12, pta_pp_median: 62.46}}}};
  const england = {id: 'england', type: 'england', name: 'England',
    by_year: {[year]: {all: {schools: 20000, pta_schools: 9000,
      pta_pp_median: 31, pta_pp_by_band: {'1': 96, '5': 6}}}}};
  return {s, sx, council, england};
}
const card = (model, id) => model.cards.find(c => c.id === id);
const slide = (model, id) => model.slides.find(s => s.id === id);
"""


def run_node(body):
    result = subprocess.run(
        ["node", "-e", COMMON + "\n" + body],
        cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_video_keeps_same_year_council_comparison_without_england():
    run_node(r"""
// Arrange: the council has the requested same-year comparator; England did not load.
const f = fixture();
// Act
const model = W.buildCards(W.adapt(f.s, f.sx, f.council, null, null), 'ptfa');
const comparison = card(model, 'pta-gap');
// Assert
assert.ok(comparison, 'The council comparison must survive missing England data');
assert.equal(comparison.big.v, card(model, 'pta-money').big.v);
assert.match(comparison.lines.join(' '), /about double Hackney's typical PTA/);
""")


def test_deck_same_year_zero_income_does_not_claim_a_different_year():
    run_node(r"""
// Arrange: zero is a valid income; the PTA and both medians are all 2024-25.
const f = fixture();
f.s.pta[0].history[0].income = 0;
f.sx.pta[year].income = 0;
f.sx.pta[year].income_pp = 0;
// Act
const deck = D.ptfaDeck(D.adapt(f.s, f.sx, f.council, f.england), {});
const ratings = slide(deck, 'summary').ratings.filter(r => /^Per pupil against/.test(r.measure));
// Assert
assert.equal(ratings.length, 2);
for (const r of ratings) assert.doesNotMatch(r.value, /a different year/,
  'A null ratio phrase does not mean the years differ: ' + r.value);
""")


def test_deck_compares_the_whole_academic_year_when_two_returns_end_in_it():
    run_node(r"""
// Arrange: an association changes its accounting date from March to August.
// series._pta and the area medians sum both distinct returns in 2024-25.
const f = fixture();
f.s.pta[0].history = [
  {period_end: '2025-03', income: 10000, expenditure: 9000},
  {period_end: '2025-08', income: 20000, expenditure: 18000},
];
f.sx.pta[year] = {income: 30000, spend: 27000, income_pp: 69,
  spend_pp: 62, charity_number: 1103834, confidence: 'high'};
// Act
const deck = D.ptfaDeck(D.adapt(f.s, f.sx, f.council, f.england), {});
const comparison = slide(deck, 'pta_compare');
const own = comparison.figures.find(f => f.key === 'pta_income');
// Assert: the comparison is with annual medians, so include both of that year's returns.
assert.equal(own.v, 30000, 'The comparison omits the earlier return in the same academic year');
assert.equal(own.pp, Math.round(30000 / 437.5));
assert.doesNotMatch(slide(deck, 'summary').messages.join(' '), /up 100% on the year before/,
  'Two returns from one academic year are not two different years');
""")
