"""Offline regressions found in the independent areas-build review."""

import json
import re
import subprocess
from pathlib import Path

import pytest

from pipeline.money import area_pages, build_money
from pipeline.money.test_build_money import full_rows, make_site, row, school


def model(tmp_path, registers, rows):
    args = make_site(tmp_path, [("204", "Hackney")], {"204": registers}, rows)
    return build_money.build_model(*args)[1]


def test_map_does_not_reconstruct_withheld_per_pupil_values(tmp_path):
    # Arrange: the published JSON deliberately withholds figures for a mismatched roll.
    items = model(
        tmp_path,
        [school(100001, "Federation lead", federation="Three Schools")],
        full_rows("100001", federated="Lead school", suspect=["pupils"]),
    )
    document = build_money.school_json(items[0])
    assert document["income_pp"] is None
    assert document["reserve_pp"] is None

    # Act: consume the actual Python output through the production map adapter.
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
require('./pipeline/money/assets/map.js');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const card = globalThis.MoneyMap.schoolCardModel(payload, {});
const figures = card.lines.filter(line => /^(Reserve|Income) per pupil/.test(line.label));
assert.equal(figures.length, 2);
for (const figure of figures) {
  assert.doesNotMatch(figure.text, /£[0-9,.]+\s+per pupil/, 'Map republished a withheld figure: ' + figure.label + ': ' + figure.text);
}
"""
    result = subprocess.run(
        ["node", "-e", script], input=json.dumps(document), text=True,
        capture_output=True, cwd=Path(__file__).resolve().parents[1], check=False,
    )

    # Assert
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("surface", ["school", "council"])
def test_fallback_pages_never_divide_by_suspect_pupils(tmp_path, surface):
    # Arrange: all full-year pupil counts are flagged as not matching the money.
    items = model(
        tmp_path,
        [school(100001, "Federation lead", federation="Three Schools")],
        full_rows("100001", reserve=-100_000, federated="Lead school", suspect=["pupils"]),
    )
    item = items[0]
    assert build_money.per_pupil(item["latest"], "total_income") is None

    # Act: use the actual fallback renderers covered by this unit's contract.
    if surface == "school":
        html = build_money.render_school(item, None)
    else:
        html = build_money.render_council(item["council"], None)[0][1]

    # Assert: no money figure may quietly use the suspect roll as its denominator.
    main = html.split("<main", 1)[1].split("</main>", 1)[0]
    invalid = re.findall(r'<span\b[^>]*data-mf="[^"]*"[^>]*data-pp="[^"]*"[^>]*>', main)
    assert not invalid, "Per-pupil figures survived the pupil flag: " + repr(invalid)


def test_reserve_rank_excludes_flagged_peer_reserves(tmp_path):
    # Arrange: the subject's reserve share is below all ten valid peers'.
    registers = [school(100000 + i, f"School {i}") for i in range(12)]
    rows = [row("100000", "2025-03", 2_000_000, 1_990_000, 100_000)]
    rows += [row(str(100000 + i), "2025-03", 2_000_000, 1_990_000, 200_000)
             for i in range(1, 11)]
    rows += [row("100011", "2025-03", 2_000_000, 1_990_000, 0,
                 suspect=["revenue_reserve"])]
    subject = next(item for item in model(tmp_path, registers, rows) if item["urn"] == "100000")

    # Act
    rank = build_money.reserve_rank(subject)

    # Assert: the flagged zero cannot make the subject rank above another school.
    assert rank == 0, f"Flagged reserve influenced the displayed percentile: {rank}"


def test_reduced_area_excludes_suspect_pupils_from_per_pupil_statistics():
    # Arrange: five valid deficits and three federation returns with unusable pupil counts.
    rows = [row(str(100000 + i), "2025-03", 2_000_000, 2_100_000,
                -100_000 * (i + 1), pupils=100) for i in range(5)]
    rows += [row(str(100010 + i), "2025-03", 2_000_000, 2_100_000,
                 -900_000, pupils=10, federated="Lead school", suspect=["pupils"])
             for i in range(3)]

    # Act: this supplies /data/a when the optional areas module is unavailable.
    summary = build_money.area_stats([{"years": [r]} for r in rows], "2024-25")

    # Assert: totals retain the returns, while per-pupil values use only matched money and rolls.
    assert summary["schools"] == 8
    assert summary["deficit_total"] == -4_200_000
    assert summary["deficit_pp"] == -3_000
    assert summary["reserve_median_pp"] == -3_000


def test_debts_chart_marks_its_provisional_dsg_year():
    # Arrange: no external files; one audited year followed by a provisional one.
    england = {
        "name": "England", "by_year": {},
        "dsg": {
            "2023-24": {"balance": -1_000_000, "per_pupil": -100, "pupils": 10_000},
            "2024-25": {"balance": -2_000_000, "per_pupil": -200, "pupils": 10_000,
                        "provisional": True},
        },
    }

    # Act
    result = area_pages.render_debts({"england": england, "councils": {}}, {})
    figures = re.findall(r'<figure\b.*?</figure>', result["intro"], re.S)
    chart = next(figure for figure in figures if area_pages.DSG_NAME in figure)

    # Assert: the chart itself must disclose the provisional status of its newest point.
    assert "2024-25" in chart
    assert "provisional" in chart.lower(), "The debts chart presents unaudited DSG figures without a warning"


@pytest.mark.parametrize("surface", ["league", "debts"])
def test_dsg_denominator_survives_table_pagination(surface):
    # Arrange: enough councils to put DSG figures onto continuation pages.
    area = {
        "by_year": {},
        "dsg": {"2024-25": {"balance": -2_000_000, "per_pupil": -200,
                             "pupils": 10_000, "provisional": True}},
    }
    councils = {
        str(100 + i): dict(area, name=f"Council {i}", code=str(100 + i), path=f"/council/council-{i}/")
        for i in range(100)
    }
    doc = {"england": dict(area, name="England"), "councils": councils}
    ctx = {"areas": doc, "paths": {}}
    if surface == "league":
        path, result = "/council/", area_pages.render_council_league(councils, ctx)
    else:
        path, result = "/debts/", area_pages.render_debts(doc, ctx)

    # Act
    pages = build_money.area_result_pages(path, [("School Money", "/")], result, None)

    # Assert: a separately accessible continuation page must still explain this denominator.
    assert len(pages) > 1
    continuation = pages[1][1].split("<main", 1)[1].split("</main>", 1)[0]
    assert 'data-mf="dsg' in continuation
    assert "schools on this site" in continuation, f"{pages[1][0]} drops the DSG denominator"
