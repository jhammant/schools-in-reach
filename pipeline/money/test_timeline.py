"""Offline tests for the year-by-year status timeline."""
import unittest

from pipeline.money import timeline


def row(urn, end, income, spend, reserve, source="CFR", pupils=300, **extra):
    year = f"{int(end[:4]) - 1}-{end[2:4]}" if source == "CFR" else f"{int(end[:4]) - 1}/{end[2:4]}"
    r = {"urn": urn, "year": year, "period_end": end, "source": source, "la": 204, "phase": "primary",
         "period_months": 12, "pupils": pupils, "total_income": income, "total_expenditure": spend,
         "in_year_balance": income - spend, "revenue_reserve": reserve}
    r.update(extra)
    return r


class StatusByYearTest(unittest.TestCase):
    def test_three_years_give_three_entries_oldest_first(self):
        # Arrange: healthy, then overspending into a tight year, then into deficit
        rows = [row("1", "2025-03", 2_000_000, 2_150_000, -50_000),
                row("1", "2023-03", 2_000_000, 1_900_000, 200_000),
                row("1", "2024-03", 2_000_000, 2_100_000, 100_000, pupils=250)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual([p["year"] for p in points], ["2022-23", "2023-24", "2024-25"])
        self.assertEqual([p["status"] for p in points], ["large_reserves", "healthy", "in_deficit"])
        self.assertEqual(points[1]["reserve"], 100_000)
        self.assertEqual(points[1]["reserve_pp"], 400)   # that year's 250 pupils, not a later count
        self.assertEqual(points[1]["pupils"], 250)
        self.assertEqual(points[2]["label"], "In deficit")

    def test_status_as_of_each_year_ignores_later_rows(self):
        # Arrange: two years of overspending with a small reserve make the latest year "heading"
        rows = [row("1", "2023-03", 2_000_000, 2_000_000, 300_000),
                row("1", "2024-03", 2_000_000, 2_100_000, 200_000),
                row("1", "2025-03", 2_000_000, 2_100_000, 100_000)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual(points[0]["status"], "large_reserves")
        self.assertEqual(points[-1]["status"], "heading_for_deficit")

    def test_academy_years_use_dash_labels_and_trust_share(self):
        # Arrange
        rows = [row("1", "2024-08", 2_000_000, 1_950_000, 50_000, source="AAR"),
                row("1", "2025-08", 2_000_000, 1_950_000, 90_000, source="AAR", revenue_reserve_incl_trust_share=120_000, pupils=400)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual([p["year"] for p in points], ["2023-24", "2024-25"])
        self.assertEqual(points[-1]["reserve"], 120_000)
        self.assertEqual(points[-1]["reserve_pp"], 300)

    def test_part_year_and_missing_rows_are_skipped(self):
        # Arrange
        rows = [row("1", "2024-03", 2_000_000, 1_900_000, 100_000, period_months=7),
                row("1", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=None)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual(len(points), 1)
        self.assertIsNone(points[0]["reserve_pp"])
        self.assertEqual(timeline.status_by_year([]), [])


class OneBasisTest(unittest.TestCase):
    """Every year on the page's one reserve basis; a pooled £0 is never 'tight'."""

    def test_pooled_years_are_held_by_the_trust_and_the_latest_uses_the_share(self):
        # Arrange: Mossbourne-like, own £4.2m, then £0 pooled twice, then a trust-inclusive £3.1m
        mat = {"trust_type": "Multi Academy Trust (MAT)"}
        rows = [row("1", "2022-08", 13_000_000, 11_600_000, 4_237_000, source="AAR", **mat),
                row("1", "2023-08", 14_000_000, 13_400_000, 0, source="AAR", **mat),
                row("1", "2024-08", 14_500_000, 15_000_000, 0, source="AAR", **mat),
                row("1", "2025-08", 15_000_000, 13_500_000, 0, source="AAR", revenue_reserve_incl_trust_share=3_087_254, **mat)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual([p["status"] for p in points], ["large_reserves", "reserve_held_by_trust", "reserve_held_by_trust", "large_reserves"])
        self.assertNotIn("tight", [p["status"] for p in points])
        self.assertEqual([p["basis"] for p in points], ["own", "own", "own", "incl_trust_share"])
        self.assertEqual(points[-1]["reserve"], 3_087_254)

    def test_explicit_own_basis_is_used_in_every_year(self):
        rows = [row("1", "2025-08", 2_000_000, 1_950_000, 90_000, source="AAR", revenue_reserve_incl_trust_share=120_000)]
        points = timeline.status_by_year(rows, basis="own")
        self.assertEqual((points[0]["reserve"], points[0]["basis"]), (90_000, "own"))

    def test_reserve_per_pupil_is_left_out_when_the_pupils_do_not_match(self):
        # Arrange: a federation lead's year with one school's pupils
        rows = [row("1", f"{y}-03", 11_000_000, 10_900_000, 1_500_000, pupils=1_550) for y in (2019, 2020, 2021, 2024)]
        rows.append(row("1", "2022-03", 12_500_000, 12_560_000, 1_580_000, pupils=437))
        # Act
        points = {p["year"]: p for p in timeline.status_by_year(rows)}
        # Assert
        self.assertIsNone(points["2021-22"]["reserve_pp"])
        self.assertEqual(points["2021-22"]["pupils"], 437)
        self.assertIsNotNone(points["2023-24"]["reserve_pp"])


if __name__ == "__main__":
    unittest.main()
