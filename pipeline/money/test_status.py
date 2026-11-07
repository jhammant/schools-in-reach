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


MAT = "Multi Academy Trust (MAT)"


def academy(end, reserve, incl=None, *, income=1_000_000, balance=10_000, trust_type=MAT, **extra):
    """One AAR full year in a multi-academy trust; incl is the reserve including its share of the trust's reserve."""
    row = year(end, income, income - balance, reserve, source="AAR", trust_type=trust_type, **extra)
    if incl is not None:
        row["revenue_reserve_incl_trust_share"] = incl
    return row


class ReserveBasisTest(unittest.TestCase):
    """One reserve basis per school (C3) and the 'reserve held by the trust' status (C4)."""

    def test_council_run_school_is_always_own_basis(self):
        # Arrange
        rows = [year("2025-03", 3_000_000, 2_990_000, 200_000)]
        # Act
        result = status.assess(rows)
        # Assert
        self.assertEqual(status.reserve_basis(rows), "own")
        self.assertEqual(result["reserve_basis"], "own")
        self.assertFalse(result["trust_share_included"])

    def test_latest_trust_share_sets_the_basis_and_the_reason_says_so(self):
        # Arrange: Lubavitch-like, own accounts in surplus, the trust share below zero
        rows = [academy("2024-08", 0), academy("2025-08", 274_000, -284_662)]
        # Act
        result = status.assess(rows)
        # Assert
        self.assertEqual(status.reserve_basis(rows), "incl_trust_share")
        self.assertEqual(result["status"], "in_deficit")
        self.assertEqual(result["reserve"], -284_662)
        self.assertIn("counting its share of the trust's reserve", result["reason"])
        self.assertNotIn("spent more over the years than it received", result["reason"])

    def test_healthy_on_the_trust_basis_names_the_share(self):
        rows = [academy("2025-08", 0, 60_000)]
        result = status.assess(rows)
        self.assertEqual(result["status"], "healthy")
        self.assertIn("in reserve including its share of the trust's reserve", result["reason"])

    def test_pooled_own_zero_is_held_by_the_trust_never_tight(self):
        # Arrange: Mossbourne 2023-24, own reserve £0, no trust-inclusive figure that year
        rows = [academy("2023-08", 0, balance=533_000), academy("2024-08", 0, balance=-479_000)]
        # Act
        result = status.assess(rows)
        # Assert
        self.assertEqual(result["status"], "reserve_held_by_trust")
        self.assertEqual(result["label"], "Reserve held by the trust")
        self.assertEqual(result["rank"], 5)
        self.assertEqual(result["reason"], status.HELD_BY_TRUST_REASON)
        self.assertNotIn("Tight", result["reason"])
        self.assertTrue(status.held_by_trust(rows[-1]))

    def test_zero_in_a_single_academy_trust_or_council_school_is_still_tight(self):
        sat = [academy("2025-08", 0, trust_type="Single Academy Trust (SAT)")]
        council = [year("2025-03", 1_000_000, 990_000, 0)]
        self.assertEqual(status.assess(sat)["status"], "tight")
        self.assertEqual(status.assess(council)["status"], "tight")

    def test_own_zero_beside_a_trust_share_is_judged_on_the_share(self):
        rows = [academy("2025-08", 0, 287_581, income=3_668_000)]
        result = status.assess(rows)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["reserve"], 287_581)
        self.assertTrue(status.pooled_own_reserve(rows[0]))
        self.assertFalse(status.held_by_trust(rows[0]))

    def test_explicit_basis_and_fallback_to_own(self):
        # Arrange
        rows = [academy("2025-08", 90_000, 120_000)]
        older = [academy("2024-08", 50_000)]
        # Act
        own = status.assess(rows, basis="own")
        fallback = status.assess(older, basis="incl_trust_share")
        # Assert
        self.assertEqual((own["reserve"], own["reserve_basis"]), (90_000, "own"))
        self.assertEqual((fallback["reserve"], fallback["reserve_basis"]), (50_000, "own"))
        self.assertEqual(status.reserve_on_basis(older[0], "incl_trust_share"), None)

    def test_order_labels_and_icons_cover_the_new_status_last(self):
        self.assertEqual(status.ORDER[-1], "reserve_held_by_trust")
        self.assertEqual(set(status.ORDER), set(status.LABELS))
        self.assertEqual(set(status.ORDER), set(status.ICONS))
        self.assertEqual(status.ICONS["reserve_held_by_trust"], "◇")


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
