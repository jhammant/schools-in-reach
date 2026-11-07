"""Offline reproductions for the areas-dashboards unit review."""

from copy import deepcopy
from html import unescape
import re
import unittest
from unittest.mock import patch

from pipeline.money import area_pages, areas
from pipeline.money.test_area_pages import Fixture, charity, make_item
from pipeline.money.test_areas import row, school


class DashboardReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = Fixture()

    @classmethod
    def tearDownClass(cls):
        cls.fx.tmp.cleanup()

    def test_council_keeps_every_required_measure_within_size_limit(self):
        # Arrange: the unit's ordinary council fixture has data for all measures.
        area = self.fx.doc["councils"]["204"]
        expected = {
            "Share of schools in deficit",
            "Government funding and spending per pupil",
            "Median reserve per pupil",
            "Deficits per pupil, in schools in deficit",
            "Council high-needs (DSG) balance",
            "Median parents' association income per pupil",
            "Pupils eligible for free school meals (median school)",
            "Pupils in schools with a full-year return",
        }

        # Act: use the fallback explicitly so the repro is independent of B0.
        with patch.object(area_pages.charts, "trend_chart", None, create=True):
            result = area_pages.render_area(
                "council", "204", area, self.fx.items, self.fx.ctx
            )

        # Assert: satisfying the byte budget must not silently remove measures.
        captions = {
            unescape(text)
            for text in re.findall(r"<figcaption>(.*?)</figcaption>", result["intro"])
        }
        self.assertEqual(expected - captions, set())
        self.assertLessEqual(len((result["intro"] + result["outro"]).encode()), 22_000)

    def test_funding_and_pupil_charts_include_region_and_england(self):
        # Arrange: capture the public chart contract, with unlimited space.
        area = self.fx.doc["councils"]["204"]
        others = area_pages.comparators("council", area, self.fx.ctx, self.fx.items)
        calls = {}

        def capture(lines, **options):
            calls[options["title"]] = lines
            return "<svg></svg>"

        # Act
        with patch.object(area_pages.charts, "trend_chart", capture, create=True):
            area_pages.dashboard_charts(
                "council", "Hackney", area, others, self.fx.ctx, 1_000_000
            )

        # Assert: each measure must compare the area with both reference areas.
        missing = []
        for measure in (
            "Government funding and spending per pupil",
            "Pupils in schools with a full-year return",
        ):
            lines = calls[measure + ", Hackney"]
            for reference in ("London", "England"):
                if not any(reference in line["label"] for line in lines):
                    missing.append((measure, reference))
        self.assertEqual(missing, [])

    def test_trust_ifs_benchmark_keeps_its_actual_observation_year(self):
        # Arrange: a new trust has no 2023-24 observation, only a 2024-25 one.
        trust = deepcopy(self.fx.doc["trusts"]["example-trust"])
        trust["central_pp"] = {"2024-25": 400}

        # Act
        result = area_pages.render_trust(trust, self.fx.trust_items, self.fx.ctx)
        paragraphs = re.findall(r"<p\b[^>]*>.*?</p>", result["intro"], flags=re.S)
        benchmark = next(p for p in paragraphs if 'data-mf="ifs_figure"' in p and "£510" in p)
        prose = unescape(re.sub(r"<[^>]*>", "", benchmark)).replace("–", "-")

        # Assert: the IFS £510 observation is for 2023-24, not the trust's year.
        self.assertIn("£510", prose)
        self.assertIn("2023-24", prose)

    def test_debts_includes_prior_year_academy_deficits(self):
        # Arrange: distinct values make the academy history distinguishable
        # from council-run history in the same row.
        doc = deepcopy(self.fx.doc)
        academy = doc["councils"]["204"]["by_year"]["2023-24"]["academy"]
        academy["deficit_total"] = -987_654
        academy["deficit_pp"] = -987_654 / 10_000

        # Act
        result = area_pages.render_debts(doc, dict(self.fx.ctx, areas=doc))
        cells = "".join(cell for cells in result["table"]["rows"] for cell in cells)

        # Assert: the older academy deficit must be available by council/year.
        figures = re.findall(r'<span[^>]*data-mf="deficit_total"[^>]*>', cells)
        self.assertTrue(
            any('data-v="987654"' in f and 'data-year="2023-24"' in f for f in figures),
            "The council row omits the 2023-24 academy deficit",
        )


class PtaWindowReviewTest(unittest.TestCase):
    def test_partial_year_does_not_replace_returns_inside_reported_window(self):
        # Arrange: ten PTAs have filed 2024-25; only one has filed 2025-26.
        records, items = [], []
        for n in range(10):
            urn = str(100000 + n)
            history = [("2025-03", 10_000)]
            if n == 0:
                history.insert(0, ("2026-03", 400_000))
            rows = [
                row(urn, end, 1_000_000, 990_000, 50_000, pupils=100)
                for end in ("2025-03", "2026-03")
            ]
            register = school(urn, "Primary " + str(n), band=1)
            charities = [charity(1100000 + n, "Friends " + str(n), history)]
            entries = areas.school_years(rows, charities)
            records.append(areas.pta_record(
                register, "204", {"name": "Hackney"}, rows, entries, charities, None
            ))
            items.append(make_item(urn, register["name"], rows, register, charities))

        # Act
        pta = areas.build_pta(records)
        page = area_pages.render_ptfa({"pta": pta}, items, {})
        totals = [
            tag for tag in re.findall(r'<span[^>]*>', "".join(page["table"]["rows"][0]))
            if 'data-mf="pta_income"' in tag
        ]

        # Assert: the incomplete year remains in by_year, but the published
        # comparison window must also govern rankings, averages and councils.
        self.assertEqual(pta["window"], ["2023-24", "2024-25"])
        self.assertEqual(pta["by_year"]["2025-26"]["income"], 400_000)
        violations = []
        if any(t["year_end"] > pta["window"][1] for t in pta["top"]):
            violations.append("ranking includes a return after its window")
        if pta["by_band"]["1"]["mean_pp"] != 100:
            violations.append("band average includes a return after its window")
        if not any('data-v="100000"' in tag for tag in totals):
            violations.append("council total includes a return after its window")
        self.assertEqual(violations, [])


class SuspectReserveReviewTest(unittest.TestCase):
    def test_trust_share_flag_is_not_plotted_as_a_clean_reserve(self):
        # Arrange: the trust-inclusive reserve is flagged, not the raw reserve.
        rows = [
            row("140001", "2024-08", 1_000_000, 990_000, 10_000,
                source="AAR", pupils=100, revenue_reserve_incl_trust_share=20_000),
            row("140001", "2025-08", 1_000_000, 990_000, 10_000,
                source="AAR", pupils=100, revenue_reserve_incl_trust_share=99_000_000,
                suspect=["revenue_reserve_incl_trust_share"]),
        ]
        captured = []

        def capture(values, **options):
            captured.extend(values)
            return "<svg></svg>"

        # Act: the sparkline contract has no parameter for suspect styling.
        with patch.object(area_pages.charts, "sparkline", capture, create=True):
            result = area_pages.reserve_spark({"years": rows})

        # Assert: a suspect trust-inclusive reserve must be excluded from the
        # unmarked series, just as suspect raw reserves already are.
        flagged_value_drawn = ("2024-25", 990_000) in captured
        marked_suspect = re.search(r'class="[^"]*\b(?:suspect|hollow|muted)\b', result)
        self.assertTrue(not flagged_value_drawn or marked_suspect)


if __name__ == "__main__":
    unittest.main()
