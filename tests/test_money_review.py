"""Offline regression probes for the harden-builder review."""
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

from pipeline.money import build_money, charts, status
from pipeline.money.test_build_money import full_rows, make_site, row, school


class MoneyReviewTest(unittest.TestCase):
    def test_all_rendered_pages_stay_under_40kb(self):
        # Arrange: a council and a trust with 90 otherwise ordinary academies.
        schools = [school(100000 + n, f"Primary Academy {n}",
                          type="Academy converter", trust="Example Trust")
                   for n in range(90)]
        rows = [r for n in range(90)
                for r in full_rows(str(100000 + n), source="AAR",
                                   years=("2024-08", "2025-08"))]
        with tempfile.TemporaryDirectory() as tmp:
            args = make_site(Path(tmp), [("204", "Hackney")], {"204": schools}, rows)

            # Act
            build_money.build(*args)

            # Assert: the requirement applies to every page, not only schools.
            money = args[0] / "money"
            oversized = {str(p.relative_to(money)): p.stat().st_size
                         for p in money.rglob("*.html") if p.stat().st_size >= 40_000}
            self.assertFalse(oversized, f"Pages exceed the 40 KB budget: {oversized}")

    def test_reported_year_matches_reserve_and_share(self):
        for missing in ({"total_income": 0}, {"revenue_reserve": None}):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                # Arrange: the newest row cannot be assessed, but an older one can.
                rows = [row("100001", "2024-03", 2_000_000, 1_990_000, 100_000),
                        row("100001", "2025-03", 2_000_000, 1_990_000, -50_000,
                            **missing)]
                args = make_site(Path(tmp), [("204", "Hackney")],
                                 {"204": [school(100001, "Mixed Years")]}, rows)

                # Act
                build_money.build(*args)

                # Assert: omitting an unassessable school is allowed; if published,
                # its reserve and share must belong to the year the JSON reports.
                output = args[0] / "money/data/s/100001.json"
                if not output.exists():
                    continue
                data = json.loads(output.read_text(encoding="utf-8"))
                reported = next(r for r in rows
                                if build_money.year_label(r) == data["year"])
                self.assertEqual(data["reserve"], build_money.reserve_of(reported))
                self.assertEqual(data["share"], status.reserve_share(reported))

    def test_negative_comparisons_fit_the_svg(self):
        # Arrange: negative expenditure figures already covered by test_charts.
        rows = [{"label": "Energy", "value": -10, "p25": -30,
                 "median": -20, "p75": -15}]

        # Act
        markup = charts.compare_dots(rows)

        # Assert: a placeholder is allowed, but a rendered graph must be visible.
        if "<svg" not in markup:
            return
        svg = ET.fromstring(markup[markup.index("<svg"):markup.index("</svg>") + 6])
        left, _, width, _ = map(float, svg.attrib["viewBox"].split())
        for dot in svg.findall(".//{*}circle"):
            self.assertGreaterEqual(float(dot.attrib["cx"]), left)
            self.assertLessEqual(float(dot.attrib["cx"]), left + width)
        for band in svg.findall(".//{*}rect[@class='band']"):
            self.assertGreaterEqual(float(band.attrib["x"]), left)
            self.assertLessEqual(float(band.attrib["x"]) + float(band.attrib["width"]),
                                 left + width)

    def test_invalid_urn_cannot_overwrite_files_outside_money(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange: all attempted writes remain inside this disposable fixture.
            urn = "../../../../sentinel"
            args = make_site(Path(tmp), [("204", "Hackney")],
                             {"204": [school(urn, "Escape")]}, full_rows(urn))
            sentinel = args[0] / "sentinel.json"
            sentinel.write_text("leave this file unchanged", encoding="utf-8")

            # Act: rejecting the malformed identifier is a valid fix.
            try:
                build_money.build(*args)
            except ValueError:
                pass

            # Assert
            self.assertEqual(sentinel.read_text(encoding="utf-8"),
                             "leave this file unchanged")
            self.assertFalse((Path(tmp) / "sentinel-escape/index.html").exists())
