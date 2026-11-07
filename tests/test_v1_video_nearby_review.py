"""Offline regression probes for the V1 independent review."""

from test_wrapped_review import run_node


def test_ptfa_uses_own_year_when_england_comparison_year_is_missing():
    run_node(r"""
// Arrange: England still has a bands payload, but its year is missing.
// The school and its nearby PTAs have explicitly dated, usable accounts.
const f = fixture();
const ownYear = Object.keys(f.sx.pta).sort().at(-1);
const olderYear = Object.keys(f.sx.pta).sort().at(-2);
const row = (urn, name, mi, pta_pp, pta_year) => ({
  urn, name, p: '/school/' + urn + '-example/', mi, pta_pp, pta_year,
});
f.s.nearby = {
  year: ownYear, phase: 'Primary', radius_mi: 0.4,
  self: row(String(f.s.urn), f.s.name, 0,
    Math.round(f.sx.pta[ownYear].income_pp), ownYear),
  schools: [
    row('900001', 'Elm Lane Primary School', 0.2, 64, ownYear),
    row('900002', 'Oak Hill Primary School', 0.3, 12, olderYear),
    row('900003', 'Birch Road Primary School', 0.4, 85, ownYear),
  ],
  medians: {}, rank: {},
};
const england = {pta: {bands: {'1': 96, '5': 6}}};

// Act
const c = cards(f, 'ptfa', england).find(c => c.id === 'pta-gap');

// Assert: no England year means use this school's own PTA year.
assert.ok(c, 'Dated nearby PTA figures must remain available');
assert.deepEqual((c.bars || []).filter(b =>
  b.label === 'Elm Lane PTA' || b.label === 'Birch Road PTA'
).map(b => b.v), [64, 85],
  'Missing England year must not suppress the same-year nearby PTA bars');
assert.ok(c.bars.some(b => b.mine &&
  b.v === Math.round(f.sx.pta[ownYear].income_pp)));
assert.ok(!c.bars.some(b => b.label === 'Oak Hill PTA'));
assert.ok(c.barsNote.includes(ownYear));
assert.doesNotMatch(c.lines.join(' '), /\bnull\b|\bundefined\b/);
""")
