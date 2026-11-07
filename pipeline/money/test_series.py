"""Tests for pipeline/money/series.py: the SERIES dict behind /data/sx/<urn>.json.

Fixtures are hand-built rows in the finance_history.jsonl shape. The William Patten
tests use the committed gold file; the real-data test reads finance_history.jsonl
from the main checkout when it exists.
"""

import json
import unittest
from pathlib import Path

from pipeline.money import deflator, series

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "pipeline" / "money" / "data" / "gold" / "130932.json"
REAL_HISTORY = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/dfe/finance_history.jsonl")


def row(year: str, **values) -> dict:
    """A full-year history row: '2023-24' is a CFR year (ends March), '2023/24' an AAR year (ends August)."""
    aar = "/" in year
    end = int(year[:4]) + 1
    base = {"urn": "100001", "year": year, "period_end": f"{end}-{'08' if aar else '03'}",
            "source": "AAR" if aar else "CFR", "period_months": 12, "did_not_supply": False, "pupils": 200,
            "total_income": 1_000_000, "total_expenditure": 980_000, "revenue_reserve": 50_000,
            "in_year_balance": 20_000, "total_staff": 800_000, "lines": {}}
    base.update(values)
    return base


def charity(number, history, **extra) -> dict:
    """A pta.json charity record; history is [(period_end, income, expenditure)]."""
    record = {"charity_number": number, "name": f"Friends {number}", "status": "Registered",
              "history": [{"period_end": end, "income": income, "expenditure": spend} for end, income, spend in history]}
    record.update(extra)
    return record


def gold_rows() -> tuple[dict, list[dict]]:
    """William Patten's eight CFR years from the gold file, in the history-row shape."""
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    rows = []
    for year, data in gold["years"].items():
        values = dict(data["totals"]["pipeline_finance_history"])
        lines = {code: v["value"] for code, v in data["lines"].items()}
        lines.update({code: v["value"] for code, v in data.get("subtotal_lines", {}).items()})
        values.update(urn=gold["urn"], year=year, period_end=f"{int(year[:4]) + 1}-03", source="CFR",
                      period_months=12, did_not_supply=False, lines=lines,
                      cfr_additional_grants_i18=lines.get("I18"))
        rows.append(values)
    return gold, rows


class MetricsTest(unittest.TestCase):
    def test_metric_order_groups_and_glossary_keys(self):
        # Arrange
        glossary = json.loads((REPO / "pipeline/money/assets/glossary.json").read_text(encoding="utf-8"))
        # Act
        keys = [key for key, _, _ in series.METRICS]
        # Assert
        self.assertEqual(keys[:3], ["total_income", "grant_funding_government", "sen_funding"])
        self.assertEqual(keys[9:11], ["other_dfe_grants", "total_expenditure"])
        self.assertEqual(keys[-2:], ["revenue_reserve", "in_year_balance"])
        self.assertEqual(len(keys), 28)
        self.assertEqual([g for _, _, g in series.METRICS], ["income"] * 10 + ["spend"] * 16 + ["balance"] * 2)
        for key, glossary_key, _ in series.METRICS:
            self.assertEqual(glossary_key, key)
            self.assertIn(glossary_key, glossary)


class CashRealPerPupilTest(unittest.TestCase):
    def test_real_is_cash_times_100_over_the_right_index(self):
        # Arrange: a council-run year and an academy year with the same label.
        cfr = series.school_series([row("2019-20", total_income=1_000_000)])
        aar = series.school_series([row("2019/20", total_income=1_000_000)])
        # Act
        cfr_cell = cfr["m"]["total_income"]["2019-20"]
        aar_cell = aar["m"]["total_income"]["2019-20"]
        # Assert: CFR uses the financial-year index, AAR the academic-year index.
        self.assertEqual(cfr_cell["r"], round(1_000_000 * 100 / deflator.index("2019-20", "CFR")))
        self.assertEqual(aar_cell["r"], round(1_000_000 * 100 / deflator.index("2019/20", "AAR")))
        self.assertNotEqual(cfr_cell["r"], aar_cell["r"])
        self.assertEqual(cfr_cell["rpp"], round(cfr_cell["r"] / 200))
        self.assertEqual((cfr["source"], aar["source"]), ({"2019-20": "CFR"}, {"2019-20": "AAR"}))

    def test_per_pupil_uses_the_same_years_pupils(self):
        # Arrange
        rows = [row("2022-23", pupils=400, total_expenditure=2_000_000), row("2023-24", pupils=250, total_expenditure=2_000_000)]
        # Act
        s = series.school_series(rows)
        # Assert
        self.assertEqual(s["years"], ["2022-23", "2023-24"])
        self.assertEqual(s["pupils"], {"2022-23": 400.0, "2023-24": 250.0})
        self.assertEqual(s["m"]["total_expenditure"]["2022-23"]["pp"], 5000)
        self.assertEqual(s["m"]["total_expenditure"]["2023-24"]["pp"], 8000)

    def test_missing_values_are_left_out_never_zero(self):
        # Arrange: no SEN figure in 2023-24 and no pupil number in 2024-25.
        rows = [row("2022-23", sen_funding=30_000), row("2023-24", sen_funding=None), row("2024-25", pupils=None, sen_funding=10)]
        # Act
        s = series.school_series(rows)
        # Assert
        self.assertEqual(sorted(s["m"]["sen_funding"]), ["2022-23", "2024-25"])
        self.assertEqual(set(s["m"]["sen_funding"]["2024-25"]), {"v", "r"})
        self.assertNotIn("2024-25", s["pupils"])
        self.assertNotIn("energy", s["m"])

    def test_rounds_to_the_pound_halves_away_from_zero(self):
        # Arrange
        s = series.school_series([row("2025-26", total_income=2_500.5, in_year_balance=-2_500.5, pupils=None)])
        # Act / Assert: 2025-26 is the base year, so real equals cash.
        self.assertEqual(s["m"]["total_income"]["2025-26"], {"v": 2501, "r": 2501})
        self.assertEqual(s["m"]["in_year_balance"]["2025-26"]["v"], -2501)

    def test_gap_pairs_government_funding_with_spending(self):
        # Arrange
        s = series.school_series([row("2024-25", grant_funding_government=1_600_000, total_expenditure=1_800_000)])
        # Act
        gap = s["gap"]["2024-25"]
        # Assert
        gov, spend = s["m"]["grant_funding_government"]["2024-25"], s["m"]["total_expenditure"]["2024-25"]
        self.assertEqual(gap, {"gov_pp": 8000, "spend_pp": 9000, "gov_rpp": gov["rpp"], "spend_rpp": spend["rpp"]})

    def test_older_key_names_and_derived_other_dfe_grants(self):
        # Arrange: a row from an older finance_history.jsonl without other_dfe_grants or the second key names.
        rows = [row("2023-24", self_generated=40_000, total_staff=None, total_staff_costs=700_000, cfr_additional_grants_i18=9_000),
                row("2025-26", lines={"I06": 12_000}), row("2023/24", aar_other_dfe_revenue_grants=7_000)]
        # Act
        s = series.school_series(rows[:2])
        aar = series.school_series(rows[2:])
        # Assert
        self.assertEqual(s["m"]["self_generated_income"]["2023-24"]["v"], 40_000)
        self.assertEqual(s["m"]["total_staff"]["2023-24"]["v"], 700_000)
        self.assertEqual(s["m"]["other_dfe_grants"]["2023-24"]["v"], 9_000)
        self.assertEqual(s["m"]["other_dfe_grants"]["2025-26"]["v"], 12_000)
        self.assertEqual(aar["m"]["other_dfe_grants"]["2023-24"]["v"], 7_000)
        self.assertEqual(series.other_dfe_grants(row("2024-25", other_dfe_grants=5)), 5)

    def test_only_full_years_are_shown(self):
        # Arrange: a 7-month academy year after conversion and a federation member with no return.
        rows = [row("2021-22"), row("2022/23", period_months=7), row("2023/24", did_not_supply=True)]
        # Act
        s = series.school_series(rows)
        # Assert
        self.assertEqual(s["years"], ["2021-22"])

    def test_json_round_trip_and_empty_rows(self):
        # Arrange
        rows = [row("2022/23", suspect=["fsm_pct"], fsm_pct=646.2, trust_central_spend_per_pupil=512.4),
                row("2023/24", trust_central_spend_per_pupil=530.0)]
        # Act
        s = series.school_series(rows, [charity(1, [("2023-08", 5_000, 4_000)])])
        empty = series.school_series([])
        # Assert
        self.assertEqual(json.loads(json.dumps(s)), s)
        self.assertEqual(s["trust_central_pp"], {"2022-23": 512, "2023-24": 530})
        self.assertEqual(empty["years"], [])
        self.assertIsNone(empty["flags"]["high_send"])
        self.assertEqual(json.loads(json.dumps(empty)), empty)


class FlagsTest(unittest.TestCase):
    def test_falling_rolls_fires_on_a_five_percent_drop(self):
        # Arrange
        rows = [row("2021-22", pupils=400), row("2022-23", pupils=410), row("2023-24", pupils=380)]
        # Act
        flag = series.school_series(rows)["flags"]["falling_rolls"]
        # Assert
        self.assertEqual(flag, {"from": 400.0, "to": 380.0, "change": -0.05})

    def test_falling_rolls_fires_on_three_years_of_small_falls(self):
        # Arrange: down 1% a year, 3% overall.
        rows = [row(f"{y}-{str(y + 1)[2:]}", pupils=p) for y, p in ((2020, 400), (2021, 396), (2022, 392), (2023, 388))]
        # Act
        flag = series.school_series(rows)["flags"]["falling_rolls"]
        # Assert
        self.assertIsNotNone(flag)
        self.assertEqual(flag["change"], -0.03)

    def test_falling_rolls_quiet_for_a_small_fall_or_one_year(self):
        # Arrange: down 4% with a rise in between; and a single year.
        rows = [row("2021-22", pupils=400), row("2022-23", pupils=390), row("2023-24", pupils=395), row("2024-25", pupils=384)]
        # Act / Assert
        self.assertIsNone(series.school_series(rows)["flags"]["falling_rolls"])
        self.assertIsNone(series.school_series(rows[:1])["flags"]["falling_rolls"])

    def test_falling_rolls_needs_the_latest_count_and_back_to_back_years(self):
        # Arrange: small falls across a missing year, a year with no count, and a drop with no latest count.
        across_gap = [row(y, pupils=p) for y, p in (("2020-21", 400), ("2021-22", 396), ("2023-24", 392), ("2024-25", 388))]
        unknown = [row(y, pupils=p) for y, p in (("2020-21", 400), ("2021-22", 396), ("2022-23", None),
                                                 ("2023-24", 392), ("2024-25", 388))]
        no_latest = [row("2020-21", pupils=400), row("2021-22", pupils=370), row("2024-25", pupils=None)]
        # Act / Assert
        for rows in (across_gap, unknown, no_latest):
            self.assertIsNone(series.school_series(rows)["flags"]["falling_rolls"])

    def test_pass_through_fires_when_staff_costs_take_most_of_an_income_rise(self):
        # Arrange: income +60,000 (6%), staff +45,000 (at least 0.7 x 60,000).
        rows = [row("2022-23", total_income=1_000_000, total_staff=800_000),
                row("2023-24", total_income=1_060_000, total_staff=845_000)]
        # Act
        flag = series.school_series(rows)["flags"]["pass_through"]
        # Assert
        self.assertEqual(flag, {"year": "2023-24", "income_rise": 60_000, "staff_rise": 45_000})

    def test_pass_through_quiet_otherwise(self):
        # Arrange: staff took too little of the rise; the rise was under 5%; the year is before 2023-24; a gap year.
        cases = {
            "staff": [row("2023-24", total_income=1_000_000, total_staff=800_000),
                      row("2024-25", total_income=1_100_000, total_staff=860_000)],
            "small": [row("2023-24", total_income=1_000_000, total_staff=800_000),
                      row("2024-25", total_income=1_040_000, total_staff=840_000)],
            "early": [row("2021-22", total_income=1_000_000, total_staff=800_000),
                      row("2022-23", total_income=1_100_000, total_staff=900_000)],
            "gap": [row("2021-22", total_income=1_000_000, total_staff=800_000),
                    row("2023-24", total_income=1_100_000, total_staff=900_000)],
        }
        for name, rows in cases.items():
            # Act / Assert
            self.assertIsNone(series.school_series(rows)["flags"]["pass_through"], name)

    def test_high_send_on_ehcp_share_or_sen_funding_share(self):
        # Arrange
        ehcp = [row("2024-25", ehcp_pct=5.4)]
        at_national = [row("2024-25", ehcp_pct=5.3, sen_funding=50_000)]
        # Act
        by_ehcp = series.school_series(ehcp)["flags"]["high_send"]
        by_share = series.school_series(at_national, sen_share_q3=0.05)["flags"]["high_send"]
        # Assert
        self.assertEqual(by_ehcp, {"ehcp_pct": 5.4, "sen_share": None, "reason": "ehcp"})
        self.assertEqual(by_share, {"ehcp_pct": 5.3, "sen_share": 0.05, "reason": "sen_share"})
        self.assertIsNone(series.school_series(at_national)["flags"]["high_send"])
        self.assertIsNone(series.school_series(at_national, sen_share_q3=0.06)["flags"]["high_send"])

    def test_suspect_values_listed_by_year(self):
        # Arrange: the AAR 2022/23 FSM problem, and a nulled sixth-form column that has nothing to draw.
        rows = [row("2022/23", fsm_pct=646.2, suspect=["fsm_pct"]),
                row("2023/24", sixth_form_pupils=None, suspect=["sixth_form_pupils"])]
        # Act
        s = series.school_series(rows)
        # Assert
        self.assertEqual(s["flags"]["suspect"], {"2022-23": ["fsm_pct"]})

    def test_academy_pupil_premium_not_reported_never_zero(self):
        # Arrange: even a stray 0 in an academy row must not show as £0.
        rows = [row("2022-23", pupil_premium=80_000), row("2023/24", pupil_premium=0)]
        # Act
        s = series.school_series(rows)
        # Assert
        self.assertEqual(s["flags"]["not_reported"]["pupil_premium"], "not reported in academy accounts")
        self.assertEqual(sorted(s["m"]["pupil_premium"]), ["2022-23"])
        self.assertEqual(series.school_series(rows[:1])["flags"]["not_reported"], {})

    def test_conversion_year_comes_whole_from_the_later_return(self):
        # Arrange: a council return to March 2023 and an academy return to August 2023, both labelled 2022-23.
        rows = [row("2022-23", pupils=100, pupil_premium=30_000, total_staff=700_000),
                row("2022/23", pupils=200, total_staff=None)]
        # Act
        s = series.school_series(rows)
        # Assert: one 2022-23, all of it from the academy return.
        self.assertEqual((s["years"], s["source"], s["pupils"]), (["2022-23"], {"2022-23": "AAR"}, {"2022-23": 200.0}))
        self.assertNotIn("pupil_premium", s["m"])
        self.assertNotIn("total_staff", s["m"])
        self.assertEqual(s["m"]["total_income"]["2022-23"]["pp"], 5_000)
        self.assertEqual(s["m"]["total_income"]["2022-23"]["r"], series._pounds(deflator.to_real(1_000_000, "2022/23", "AAR")))


class PtaYearTest(unittest.TestCase):
    def test_return_goes_in_the_school_year_holding_its_period_end(self):
        # Arrange / Act / Assert
        self.assertEqual(series.pta_year("2023-03", "CFR"), "2022-23")
        self.assertEqual(series.pta_year("2023-04", "CFR"), "2023-24")
        self.assertEqual(series.pta_year("2025-08", "CFR"), "2025-26")
        self.assertEqual(series.pta_year("2025-08", "AAR"), "2024-25")
        self.assertEqual(series.pta_year("2025-09", "AAR"), "2025-26")
        self.assertEqual(series.pta_year("2024-12-31", "AAR"), "2024-25")
        self.assertIsNone(series.pta_year("2024", "CFR"))
        self.assertIsNone(series.pta_year(None, "CFR"))
        self.assertIsNone(series.pta_year("2024-13", "CFR"))


class PtaSeriesTest(unittest.TestCase):
    def test_cfr_school_return_and_per_pupil(self):
        # Arrange: £12,000 to March 2023 with 100 pupils that year.
        rows = [row("2022-23", pupils=100), row("2023-24", pupils=120)]
        # Act
        pta = series.school_series(rows, [charity(1056001, [("2023-03", 12_000, 9_000)])])["pta"]
        # Assert
        self.assertEqual(pta, {"2022-23": {"income": 12_000, "spend": 9_000, "income_pp": 120, "spend_pp": 90,
                                           "charity_number": 1056001, "confidence": None}})

    def test_academy_return_uses_the_academic_year(self):
        # Arrange
        rows = [row("2023/24", pupils=300), row("2024/25", pupils=310)]
        # Act
        pta = series.school_series(rows, [charity(7, [("2025-08", 31_000, 20_000)])])["pta"]
        # Assert
        self.assertEqual(list(pta), ["2024-25"])
        self.assertEqual(pta["2024-25"]["income_pp"], 100)

    def test_shared_charity_split_equally(self):
        # Arrange: one charity shared with two other schools.
        rows = [row("2023-24", pupils=100)]
        shared = charity(5, [("2024-03", 30_000, 15_000)], shared_with=["100002", "100003"])
        # Act
        pta = series.school_series(rows, [shared])["pta"]
        # Assert
        self.assertEqual((pta["2023-24"]["income"], pta["2023-24"]["spend"], pta["2023-24"]["income_pp"]), (10_000, 5_000, 100))

    def test_charities_summed_with_lowest_confidence_and_largest_contributor(self):
        # Arrange: a high-confidence match and an LLM match in the same school year; one review-flagged charity.
        rows = [row("2023-24", pupils=200)]
        records = [charity(1, [("2023-08", 4_000, 3_000)], match={"method": "postcode", "confidence": "high"}),
                   charity(2, [("2023-12", 6_000, None)], match={"method": "llm", "evidence": "x", "confidence": "medium"}),
                   charity(1056624, [("2023-08", 307_000, 300_000)], review="independent school's society")]
        # Act
        pta = series.school_series(rows, records)["pta"]
        # Assert
        self.assertEqual(pta["2023-24"], {"income": 10_000, "spend": 3_000, "income_pp": 50, "spend_pp": 15,
                                          "charity_number": 2, "confidence": "medium"})

    def test_year_without_pupils_leaves_per_pupil_out_and_returns_are_never_relabelled(self):
        # Arrange: returns from long before the finance years, and a missing match block.
        rows = [row("2023-24", pupils=200)]
        old = charity(9, [("2005-08", 2_000, 1_000), ("2024-03", 5_000, 4_000)])
        # Act
        pta = series.school_series(rows, [old])["pta"]
        # Assert
        self.assertEqual(list(pta), ["2005-06", "2023-24"])
        self.assertIsNone(pta["2005-06"]["income_pp"])
        self.assertEqual(pta["2023-24"]["income_pp"], 25)

    def test_returns_in_one_school_year_are_summed_and_a_repeat_counts_once(self):
        # Arrange: a change of year end puts two distinct returns in one academy year; one is listed twice.
        rows = [row("2022/23", pupils=100)]
        moved = charity(3, [("2023-03", 1_000, 1_000), ("2023-08", 2_500, 2_000), ("2023-08", 2_500, 2_000)])
        # Act
        pta = series.school_series(rows, [moved])["pta"]
        # Assert
        self.assertEqual((pta["2022-23"]["income"], pta["2022-23"]["spend"]), (3_500, 3_000))
        self.assertEqual(pta["2022-23"]["income_pp"], 35)

    def test_converter_uses_its_own_row_else_the_nearest_years_source(self):
        # Arrange: council-run to March 2021, an academy from September 2021.
        rows = [row("2020-21", pupils=100), row("2021/22", pupils=120)]
        records = [charity(4, [("2021-03", 1_000, 0), ("2022-08", 2_400, 0)]), charity(6, [("2021-06", 500, 0)])]
        # Act
        pta = series.school_series(rows, records)["pta"]
        # Assert: 2021-03 is the CFR row's year, 2022-08 the AAR row's year, 2021-06 is nearest the CFR row.
        self.assertEqual(pta["2020-21"]["income"], 1_000)
        self.assertEqual(pta["2021-22"]["income"], 2_400 + 500)

    def test_no_charities(self):
        # Arrange / Act / Assert
        self.assertEqual(series.school_series([row("2023-24")])["pta"], {})
        self.assertEqual(series.school_series([row("2023-24")], [])["pta"], {})


class HelpersTest(unittest.TestCase):
    def test_sparkline_values(self):
        # Arrange
        rows = [row("2021-22", sen_funding=10_000), row("2022-23", sen_funding=None), row("2023-24", sen_funding=30_000)]
        s = series.school_series(rows)
        # Act
        values = series.sparkline_values(s, "sen_funding")
        cash = series.sparkline_values(s, "sen_funding", basis="v")
        # Assert
        self.assertEqual(values, [("2021-22", 50), ("2023-24", 150)])
        self.assertEqual(cash, [("2021-22", 10_000), ("2023-24", 30_000)])
        self.assertEqual(series.sparkline_values(s, "energy", basis="rpp"), [])
        with self.assertRaises(ValueError):
            series.sparkline_values(s, "sen_funding", basis="total")

    def test_sen_share(self):
        # Arrange / Act / Assert
        self.assertEqual(series.sen_share({"sen_funding": 50_000, "total_income": 1_000_000}), 0.05)
        self.assertIsNone(series.sen_share({"sen_funding": None, "total_income": 1_000_000}))
        self.assertIsNone(series.sen_share({"sen_funding": 5, "total_income": 0}))


class WilliamPattenGoldTest(unittest.TestCase):
    def setUp(self):
        self.gold, self.rows = gold_rows()
        self.s = series.school_series(self.rows)

    def test_cash_figures_match_the_gold_file(self):
        # Arrange
        keys = {"total_income": "total_income", "total_expenditure": "total_expenditure", "revenue_reserve": "revenue_reserve",
                "in_year_balance": "in_year_balance", "sen_funding": "sen_funding", "pupil_premium": "pupil_premium",
                "self_generated_income": "self_generated"}
        # Act / Assert
        self.assertEqual(self.s["years"], sorted(self.gold["years"]))
        for year, data in self.gold["years"].items():
            gold = data["totals"]["pipeline_finance_history"]
            self.assertEqual(self.s["pupils"][year], gold["pupils"])
            for metric, gold_key in keys.items():
                self.assertEqual(self.s["m"][metric][year]["v"], series._pounds(gold[gold_key]), f"{year} {metric}")
        self.assertEqual(self.s["m"]["revenue_reserve"]["2025-26"], {"v": -210901, "pp": -488, "r": -210901, "rpp": -488})

    def test_other_dfe_grants_container_from_the_gold_lines(self):
        # Arrange / Act
        cells = self.s["m"]["other_dfe_grants"]
        # Assert: I18 up to 2024-25 (I18 removed in 2025-26), then I06.
        self.assertEqual(cells["2024-25"]["v"], 200455)
        self.assertEqual(cells["2025-26"]["v"], self.gold["years"]["2025-26"]["lines"]["I06"]["value"])

    def test_ptfa_returns_land_in_the_schools_april_to_march_years(self):
        # Arrange: the PTFA's September-August returns from the gold file.
        ptfa = self.gold["ptfa"]
        history = [(y["period"][-10:-3], y["income"], y["expenditure"]) for y in ptfa["years"].values()]
        # Act
        pta = series.school_series(self.rows, [charity(ptfa["charity_number"], history)])["pta"]
        # Assert: August 2025 sits in April 2025 to March 2026, divided by that year's 432.5 pupils.
        self.assertEqual(pta["2025-26"]["income"], 48547)
        self.assertEqual(pta["2025-26"]["income_pp"], round(48547 / 432.5))
        self.assertEqual(pta["2021-22"]["income"], 12602)

    def test_no_flags_fire_for_william_patten(self):
        # Arrange / Act
        flags = self.s["flags"]
        # Assert: pupils moved within 1%, and the gold rows carry no EHCP share.
        self.assertIsNone(flags["falling_rolls"])
        self.assertIsNone(flags["high_send"])
        self.assertEqual(flags["not_reported"], {})


@unittest.skipUnless(REAL_HISTORY.exists(), "finance_history.jsonl not present")
class RealHistoryTest(unittest.TestCase):
    def test_william_patten_series_from_finance_history(self):
        # Arrange: rows in finance_history.jsonl start with the urn, so a prefix scan finds them quickly.
        with open(REAL_HISTORY, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.startswith('{"urn": "130932"')]
        gold, _ = gold_rows()
        # Act
        s = series.school_series(rows)
        # Assert
        self.assertEqual(s["years"], sorted(gold["years"]))
        for year, data in gold["years"].items():
            for metric in ("total_income", "total_expenditure", "revenue_reserve"):
                expected = data["totals"]["pipeline_finance_history"][metric]
                self.assertEqual(s["m"][metric][year]["v"], series._pounds(expected), f"{year} {metric}")
        self.assertEqual(s["pupils"]["2024-25"], 437.5)
        self.assertEqual(s["m"]["supply_staff"]["2025-26"]["v"], 82434)
        self.assertEqual(s["m"]["educational_supplies"]["2024-25"]["v"], 147325)
        self.assertEqual(s["flags"]["suspect"], {})
        self.assertEqual(json.loads(json.dumps(s)), s)


if __name__ == "__main__":
    unittest.main()
