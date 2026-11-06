"""Offline tests for the five-step financial health status."""
import unittest

from pipeline.money import status


def year(end, income, spend, reserve, **extra):
    row = {"period_end": end, "year": end, "source": "CFR", "period_months": 12, "phase": "primary",
           "pupils": 400, "total_income": income, "total_expenditure": spend,
           "in_year_balance": income - spend, "revenue_reserve": reserve}
    row.update(extra)
    return row


class AssessTest(unittest.TestCase):
    def test_negative_reserve_is_in_deficit(self):
        # Arrange
        rows = [year("2024-03", 3_000_000, 3_100_000, 50_000), year("2025-03", 3_000_000, 3_200_000, -150_000)]
        # Act
        result = status.assess(rows)
        # Assert
        self.assertEqual(result["status"], "in_deficit")
        self.assertIn("£150k", result["reason"])
        self.assertIn("2 years running", result["reason"])

    def test_two_overspends_with_short_runway_is_heading_for_deficit(self):
        rows = [year("2023-03", 3_000_000, 2_900_000, 500_000),
                year("2024-03", 3_000_000, 3_150_000, 350_000),
                year("2025-03", 3_000_000, 3_200_000, 150_000)]
        result = status.assess(rows)
        self.assertEqual(result["status"], "heading_for_deficit")
        self.assertLessEqual(result["runway_years"], 3)

    def test_long_runway_overspend_is_not_heading_for_deficit(self):
        rows = [year("2024-03", 3_000_000, 3_010_000, 400_000), year("2025-03", 3_000_000, 3_010_000, 390_000)]
        result = status.assess(rows)
        self.assertEqual(result["status"], "large_reserves")
        self.assertIn("drawing on it for 2 years", result["reason"])

    def test_small_reserve_is_tight(self):
        result = status.assess([year("2025-03", 3_000_000, 2_990_000, 60_000)])
        self.assertEqual(result["status"], "tight")

    def test_secondary_uses_lower_large_reserve_threshold(self):
        rows = [year("2025-03", 6_000_000, 5_900_000, 360_000, phase="secondary")]
        self.assertEqual(status.assess(rows)["status"], "large_reserves")
        rows[0]["phase"] = "primary"
        self.assertEqual(status.assess(rows)["status"], "healthy")

    def test_academy_uses_reserve_including_trust_share(self):
        rows = [year("2025-08", 3_000_000, 3_000_000, -20_000, source="AAR", revenue_reserve_incl_trust_share=150_000)]
        result = status.assess(rows)
        self.assertEqual(result["status"], "healthy")
        self.assertTrue(result["trust_share_included"])

    def test_part_year_and_member_rows_are_ignored(self):
        rows = [year("2025-03", 1_000_000, 900_000, 100_000, period_months=7),
                {"period_end": "2025-03", "did_not_supply": True}]
        self.assertIsNone(status.assess(rows))

    def test_pupil_change_spans_first_to_latest_year(self):
        rows = [year("2019-03", 3_000_000, 3_000_000, 300_000, pupils=420),
                year("2025-03", 3_000_000, 3_000_000, 300_000, pupils=315)]
        self.assertAlmostEqual(status.assess(rows)["pupils_change"], -0.25)


if __name__ == "__main__":
    unittest.main()


class BoundaryTest(unittest.TestCase):
    """Exact thresholds: tight is strictly below 3%; large is 8% (5% secondary) or more; runway 3.0 counts."""

    def test_exactly_three_percent_is_healthy_not_tight(self):
        # Arrange: 90k reserve on 3m income is exactly 3%.
        rows = [year("2025-03", 3_000_000, 2_990_000, 90_000)]
        # Act / Assert
        self.assertEqual(status.assess(rows)["status"], "healthy")
        rows[0]["revenue_reserve"] = 89_999
        self.assertEqual(status.assess(rows)["status"], "tight")

    def test_exactly_eight_percent_primary_is_large(self):
        rows = [year("2025-03", 3_000_000, 2_990_000, 240_000)]
        self.assertEqual(status.assess(rows)["status"], "large_reserves")
        rows[0]["revenue_reserve"] = 239_999
        self.assertEqual(status.assess(rows)["status"], "healthy")

    def test_exactly_five_percent_secondary_is_large(self):
        rows = [year("2025-03", 6_000_000, 5_990_000, 300_000, phase="secondary")]
        self.assertEqual(status.assess(rows)["status"], "large_reserves")
        rows[0]["revenue_reserve"] = 299_999
        self.assertEqual(status.assess(rows)["status"], "healthy")

    def test_runway_of_exactly_three_years_is_heading_for_deficit(self):
        # Three years of -100k overspend and a 300k reserve: runway exactly 3.0.
        rows = [year("2023-03", 3_000_000, 3_100_000, 500_000),
                year("2024-03", 3_000_000, 3_100_000, 400_000),
                year("2025-03", 3_000_000, 3_100_000, 300_000)]
        result = status.assess(rows)
        self.assertEqual(result["runway_years"], 3.0)
        self.assertEqual(result["status"], "heading_for_deficit")
        rows[2]["revenue_reserve"] = 300_001
        self.assertEqual(status.assess(rows)["status"], "large_reserves")

    def test_docstring_states_the_boundary_rule(self):
        doc = status.__doc__
        self.assertIn("3%", doc)
        self.assertIn("or more", doc)
