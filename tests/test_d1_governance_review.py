"""Offline regressions for D1, using the actual series/status producers."""

import json
from pathlib import Path
import subprocess

import pytest

from pipeline.money import deck, series, status
from pipeline.money.test_series import gold_rows


ROOT = Path(__file__).resolve().parents[1]


def finance_row(year, **values):
    """A full-year return, in the producer's input format."""
    source = values.pop("source", "CFR")
    end = int(year[:4]) + 1
    return {
        "urn": "100001", "year": year,
        "period_end": f"{end}-{'08' if source == 'AAR' else '03'}",
        "source": source, "period_months": 12, "pupils": 400,
        "total_income": 1_000_000, "total_expenditure": 990_000,
        "in_year_balance": 10_000, "revenue_reserve": 50_000,
        "phase": "primary", **values,
    }


def school_doc(rows, charities=()):
    """The /data/s fields, including the trust-inclusive status reserve."""
    assessed = status.assess(rows)
    latest = rows[-1]
    return {
        "urn": latest["urn"], "name": "Example Primary School",
        "year": series.year_label(latest), "phase": "Primary",
        "academy": latest["source"] == "AAR",
        "pupils": latest["pupils"], "status": assessed["status"],
        "label": assessed["label"], "reason": assessed["reason"],
        "reserve": assessed["reserve"], "share": assessed["reserve_share"],
        "streak": assessed["deficit_streak"],
        "council": {"code": "204", "name": "Example Council"},
        "years": [
            {
                "y": series.year_label(r), "pupils": r["pupils"],
                "income": r["total_income"], "spend": r["total_expenditure"],
                "balance": r["in_year_balance"],
                "reserve": r.get("revenue_reserve_incl_trust_share", r["revenue_reserve"]),
            }
            for r in rows
        ],
        "pta": list(charities),
    }


def area_doc(ident, years, median):
    return {
        "id": ident, "name": "England" if ident == "england" else "Example Council",
        "by_year": {
            y: {"all": {"pta_pp_median": median, "pta_schools": 10}}
            for y in years
        },
    }


def run_model(body, **payload):
    script = (
        "require('./pipeline/money/assets/deck.js');\n"
        "const D = globalThis.MoneyDeck;\n"
        "const p = " + json.dumps(payload) + ";\n"
        "const result = (() => {\n" + body + "\n})();\n"
        "process.stdout.write(JSON.stringify(result));\n"
    )
    result = subprocess.run(
        ["node"], input=script, text=True, capture_output=True,
        timeout=20, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_pta_comparison_and_target_use_the_producers_school_year():
    # Arrange: keep charity accounting years separate from CFR school years.
    gold, rows = gold_rows()
    charities = [{
        "charity_number": gold["ptfa"]["charity_number"], "name": gold["ptfa"]["name"],
        "history": [
            {"period_end": r["period"][-10:], "income": r["income"],
             "expenditure": r["expenditure"]}
            for r in gold["ptfa"]["years"].values()
        ],
    }]
    sx = series.school_series(rows, charities)
    pupil_year = series.pta_year(charities[0]["history"][-1]["period_end"], "CFR")
    council = area_doc("council-204", sx["years"], 400)

    # Act.
    result = run_model("""
      const m = D.adapt(p.s, p.sx, p.council, p.england);
      const pack = D.ptfaDeck(m);
      return {
        figure: pack.slides.find(s => s.id === 'pta_money').figures[0],
        comparison: pack.slides.find(s => s.id === 'pta_compare').chart.series[0].points,
        target: D.ptaTarget(m),
      };
    """, s=school_doc(rows, charities), sx=sx, council=council,
        england=area_doc("england", sx["years"], 100))

    # Assert: use the same school year the real producer and area medians use.
    assert result["figure"]["pp"] == sx["pta"][pupil_year]["income_pp"], (
        "The per-pupil headline discarded the producer's matching return"
    )
    assert result["target"]["year"] == pupil_year
    assert result["target"]["pupils"] == sx["pupils"][pupil_year]
    assert result["target"]["target"] == round(400 * sx["pupils"][pupil_year])
    assert any(p["y"] == "Example Council, " + pupil_year for p in result["comparison"])


def test_reserve_rating_uses_the_status_rules_trust_inclusive_reserve():
    # Arrange: status.py deliberately includes the school's share of trust reserves.
    rows = [finance_row("2024-25", source="AAR", revenue_reserve=-20_000,
                        revenue_reserve_incl_trust_share=50_000)]
    assessed = status.assess(rows)
    assert assessed["status"] == "healthy"

    # Act.
    result = run_model("""
      const m = D.adapt(p.s, p.sx);
      return [D.schoolDeck(m), D.reviewDeck(m)].map(pack => {
        const summary = pack.slides.find(s => s.id === 'summary');
        return {
          message: summary.messages[0],
          rating: summary.ratings.find(r => r.measure === 'Reserve as a share of income'),
        };
      });
    """, s=school_doc(rows), sx=series.school_series(rows))

    # Assert: the pack must not reclassify a healthy academy as being in deficit.
    for summary in result:
        assert summary["rating"]["level"] == assessed["status"], summary
        assert "£50k" in summary["message"]
        assert not summary["message"].startswith("In deficit")


@pytest.mark.parametrize("gap", ["missing", "suspect"])
def test_unknown_year_breaks_consecutive_deficit_claims(gap):
    # Arrange: only the current year is a confirmed consecutive overspend.
    rows = [
        finance_row("2023-24", total_expenditure=1_010_000,
                    in_year_balance=-10_000, revenue_reserve=-5_000),
        finance_row("2024-25", total_expenditure=990_000,
                    in_year_balance=10_000, revenue_reserve=5_000),
        finance_row("2025-26", total_expenditure=1_010_000,
                    in_year_balance=-10_000, revenue_reserve=-5_000),
    ]
    if gap == "missing":
        rows.pop(1)
    else:
        rows[1]["suspect"] = ["total_expenditure"]

    # Act.
    result = run_model("""
      const pack = D.schoolDeck(D.adapt(p.s, p.sx));
      const summary = pack.slides.find(s => s.id === 'summary');
      return {message: summary.messages[0],
              balance: summary.ratings.find(r => r.measure === 'In-year balance')};
    """, s=school_doc(rows), sx=series.school_series(rows))

    # Assert: a one-percent overspend cannot become red by bridging unknown years.
    assert result["balance"]["level"] == "amber", result["balance"]
    assert "2 years running" not in result["balance"]["why"]
    assert "second year running" not in result["message"]


def test_send_pressure_reports_the_flag_reason_not_an_invented_ehcp_excess():
    # Arrange: SEN funding raises the flag even though EHCP prevalence is below 5.3%.
    rows = [finance_row("2025-26", ehcp_pct=4.1, sen_funding=100_000)]
    sx = series.school_series(rows, sen_share_q3=0.075)
    assert sx["flags"]["high_send"]["reason"] == "sen_share"

    # Act.
    result = run_model("""
      const pack = D.schoolDeck(D.adapt(p.s, p.sx), p.ctx);
      return pack.slides.find(s => s.id === 'pressures').bullets;
    """, s=school_doc(rows), sx=sx, ctx=deck.deck_context())

    # Assert: a below-national EHCP figure must not be called above-national.
    explanation = next(text for text in result if text.startswith("Special needs:"))
    assert "above the national share" not in explanation, explanation
    assert "funding" in explanation.lower(), explanation


def test_england_pta_comparison_survives_a_missing_council_median():
    # Arrange: England has a median; the council has too few returns for one.
    rows = [finance_row("2025-26")]
    charities = [{"charity_number": "1234567", "name": "Friends",
                  "history": [{"period_end": "2026-03", "income": 10_000,
                               "expenditure": 9_000}]}]
    sx = series.school_series(rows, charities)
    council = area_doc("council-204", sx["years"], None)

    # Act.
    result = run_model("""
      const pack = D.ptfaDeck(D.adapt(p.s, p.sx, p.council, p.england));
      return {
        points: pack.slides.find(s => s.id === 'pta_compare').chart.series.flatMap(s => s.points),
        ratings: pack.slides.find(s => s.id === 'summary').ratings,
      };
    """, s=school_doc(rows, charities), sx=sx, council=council,
        england=area_doc("england", sx["years"], 100))

    # Assert: a local-data gap must not remove an available national comparison.
    assert any(p["y"] == "England, 2025-26" and p["v"] == 100 for p in result["points"]), result
    assert any("England" in r["measure"] for r in result["ratings"])


def test_pta_target_does_not_use_suspect_pupil_numbers():
    # Arrange: a published pupil count is explicitly marked suspect by the producer.
    rows = [finance_row("2024-25"),
            finance_row("2025-26", pupils=1, suspect=["pupils"])]
    charities = [{"charity_number": "1234567", "name": "Friends",
                  "history": [{"period_end": "2026-03", "income": 10_000,
                               "expenditure": 9_000}]}]
    sx = series.school_series(rows, charities)
    suspect_year = rows[-1]["year"]
    assert suspect_year in sx["flags"]["suspect"]

    # Act.
    result = run_model("""
      const m = D.adapt(p.s, p.sx, p.council);
      const pack = D.ptfaDeck(m);
      return {
        target: D.ptaTarget(m),
        figures: pack.slides.find(s => s.id === 'ideas').figures,
      };
    """, s=school_doc(rows, charities), sx=sx,
        council=area_doc("council-204", sx["years"], 100))

    # Assert: omit the illustration or use a clearly labelled trustworthy year.
    assert result["target"] is None or result["target"]["year"] != suspect_year, result
    assert all(f["year"] != suspect_year for f in result["figures"])


def test_deck_latest_reserve_is_the_published_status_reserve_on_either_basis():
    # Arrange: an academy whose status counts its share of the trust's reserve, three years running. With contract C3
    # series.school_series says so in reserve_basis; without it the deck falls back to /data/s year by year.
    rows = [finance_row(y, source="AAR", revenue_reserve=10_000, revenue_reserve_incl_trust_share=v)
            for y, v in (("2022-23", 40_000), ("2023-24", 45_000), ("2024-25", 50_000))]
    assessed = status.assess(rows)
    sx = series.school_series(rows)

    # Act.
    result = run_model("""
      const m = D.adapt(p.s, p.sx);
      const pack = D.reviewDeck(m);
      return {
        figure: pack.slides.find(s => s.id === 'reserve_trajectory').figures[0],
        years: m.rows.map(r => r.metrics.revenue_reserve && r.metrics.revenue_reserve.v),
        basis: m.reserveBasis,
      };
    """, s=school_doc(rows), sx=sx)

    # Assert: the headline reserve and the year rows share one basis.
    assert result["figure"]["v"] == round(assessed["reserve"])
    assert result["years"][-1] == round(assessed["reserve"])
    assert result["basis"] == sx.get("reserve_basis")
    assert "trust" in result["figure"]["label"]
