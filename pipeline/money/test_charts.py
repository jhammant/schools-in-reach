"""Offline tests for the inline SVG charts: odd inputs must give a string, never an exception."""
import unittest
from xml.etree import ElementTree as ET

from pipeline.money import charts


def years(values, income=None, spend=None):
    out = []
    for i, v in enumerate(values):
        out.append({"year": f"20{20 + i}-{21 + i}", "reserve": v,
                    "income": v if income is None else income[i], "spend": v if spend is None else spend[i]})
    return out


def parses(svg):
    """True when every <svg> in the markup is well-formed XML."""
    start = 0
    while True:
        a = svg.find("<svg", start)
        if a == -1:
            return True
        b = svg.index("</svg>", a) + len("</svg>")
        ET.fromstring(svg[a:b].replace("&nbsp;", " "))
        start = b


CASES = {
    "single": [120_000],
    "all_negative": [-50_000, -80_000, -120_000],
    "all_zero": [0, 0, 0],
    "with_none": [None, 30_000, None, -5_000],
    "all_none": [None, None],
    "empty": [],
}


class ChartsTest(unittest.TestCase):
    def check(self, svg):
        self.assertIsInstance(svg, str)
        if svg:
            self.assertTrue(parses(svg), svg[:200])

    def test_reserve_bars_odd_inputs(self):
        for name, values in CASES.items():
            with self.subTest(name):
                # Arrange
                pts = years(values)
                # Act
                svg = charts.reserve_bars(pts)
                # Assert
                self.check(svg)
                self.assertNotIn("nan", svg.lower().replace("financial", ""))

    def test_income_spend_lines_odd_inputs(self):
        for name, values in CASES.items():
            with self.subTest(name):
                svg = charts.income_spend_lines(years(values))
                self.check(svg)
        # All-zero with two points is the classic flat line: no division by zero.
        self.check(charts.income_spend_lines(years([0, 0])))
        self.check(charts.income_spend_lines(years([-100, -100], income=[-100, -100], spend=[-100, -100])))

    def test_count_bars_odd_inputs(self):
        for name, series in {
            "single": [("2024-25", 3, 10)],
            "all_zero": [("2023-24", 0, 10), ("2024-25", 0, 12)],
            "zero_denominator": [("2023-24", 0, 0), ("2024-25", 1, 0)],
            "negative": [("2023-24", -1, 10), ("2024-25", -2, 10)],
            "none": [("2023-24", None, 10), ("2024-25", 1, None)],
            "empty": [],
        }.items():
            with self.subTest(name):
                self.check(charts.count_bars(series))

    def test_compare_dots_odd_inputs(self):
        row = {"label": "Teachers", "value": 3000, "p25": 2500, "median": 2800, "p75": 3100}
        for name, rows in {
            "single": [row],
            "all_negative": [dict(row, value=-10, p25=-30, median=-20, p75=-15)],
            "all_zero": [dict(row, value=0, p25=0, median=0, p75=0)],
            "none_band": [dict(row, p25=None, p75=None)],
            "none_value": [dict(row, value=None)],
            "empty": [],
        }.items():
            with self.subTest(name):
                self.check(charts.compare_dots(rows))

    def test_compare_dots_keep_negative_values_inside_the_chart(self):
        # Arrange: a rebate year, every figure below zero.
        rows = [{"label": "Energy", "value": -10, "p25": -30, "median": -20, "p75": -15}]
        # Act
        svg = charts.compare_dots(rows)
        # Assert: dot, band and median all sit within the viewBox, and a zero axis is drawn.
        root = ET.fromstring(svg[svg.index("<svg"):svg.index("</svg>") + 6])
        left, _, width, _ = map(float, root.attrib["viewBox"].split())
        dot = root.find(".//{*}circle")
        self.assertTrue(left <= float(dot.attrib["cx"]) <= left + width, dot.attrib["cx"])
        band = root.find(".//{*}rect[@class='band']")
        self.assertGreaterEqual(float(band.attrib["x"]), left)
        self.assertLessEqual(float(band.attrib["x"]) + float(band.attrib["width"]), left + width)
        self.assertEqual(len(root.findall(".//{*}line[@class='axis']")), 1)

    def test_status_bar_odd_inputs(self):
        for name, counts in {
            "single": {"healthy": 1},
            "all_zero": {s: 0 for s in charts.STATUS_ORDER},
            "none_values": {"healthy": None, "tight": 2},
            "empty": {},
        }.items():
            with self.subTest(name):
                html = charts.status_bar(counts)
                self.assertIsInstance(html, str)
        self.assertEqual(charts.status_bar({}, total=None), "")
        self.assertIn("statusbar", charts.status_bar({"healthy": 2}, total=0))

    def test_ticks_with_lo_equal_hi_or_reversed(self):
        self.assertEqual(charts._ticks(5, 5), [5])
        self.assertTrue(charts._ticks(0, 0))
        self.assertTrue(charts._ticks(10, -10))
        self.assertTrue(charts._ticks(-10, 10))
        self.assertTrue(charts._ticks(0.1, 0.3))


YEARS = ["2021-22", "2022-23", "2023-24", "2024-25"]


def trend(**over):
    """A two-basis chart: school cash and real lines, plus an always-visible similar-schools line."""
    lines = [
        {"label": "This school", "values": {"2021-22": 5_000, "2022-23": None, "2023-24": 5_600, "2024-25": 6_000},
         "style": "solid", "emph": True, "basis": "cash"},
        {"label": "This school", "values": {"2021-22": 6_100, "2023-24": 6_050, "2024-25": 6_000}, "style": "solid",
         "emph": True, "basis": "real"},
        {"label": "Similar schools", "values": {y: 5_400 for y in YEARS}, "style": "dashed", "emph": False, "basis": None},
    ]
    lines = over.pop("lines", lines)
    kw = {"years": YEARS, "title": "Income per pupil", "desc": "Income per pupil each year, 2021-22 to 2024-25."}
    kw.update(over)
    return charts.trend_chart(lines, **kw)


def svg_root(markup):
    return ET.fromstring(markup[markup.index("<svg"):markup.index("</svg>") + 6])


class TrendChartTest(unittest.TestCase):
    def test_chart_is_an_image_with_title_and_desc(self):
        # Act
        root = svg_root(trend())
        # Assert
        self.assertEqual(root.attrib["role"], "img")
        self.assertEqual(root[0].tag.split("}")[-1], "title")
        self.assertEqual(root[0].text, "Income per pupil")
        self.assertEqual(root[1].tag.split("}")[-1], "desc")

    def test_none_value_leaves_a_gap(self):
        # Act
        root = svg_root(trend())
        cash = root.find(".//{*}g[@data-basis='cash']")
        path = cash.find("{*}path").attrib["d"]
        # Assert: 2021-22 is not joined to 2023-24; markers sit only on the lone 2021-22 point and the line's end.
        self.assertEqual(path.count("M"), 1)
        self.assertEqual(sorted(float(c.attrib["cx"]) for c in cash.findall("{*}circle")), [52.0, 376.0])

    def test_chart_stays_lean_with_two_bases_and_eight_years(self):
        # Arrange: what a school dashboard draws several times per page.
        years = [f"{y}-{(y + 1) % 100:02d}" for y in range(2018, 2026)]
        lines = [{"label": label, "values": {y: 5_000 + 137.3 * i + 300 * k for i, y in enumerate(years)}, "basis": basis, "emph": k == 0}
                 for k, (label, basis) in enumerate([("This school", "cash"), ("This school", "real"), ("Similar schools", "cash"), ("Similar schools", "real")])]
        # Act
        markup = charts.trend_chart(lines, years=years, title="Income per pupil", desc="Income per pupil, 2018-19 to 2025-26")
        # Assert
        self.assertLess(len(markup.encode("utf-8")), 3_500)
        self.assertNotRegex(markup, r'(?:cx|cy|x|y)="\d+\.\d')

    def test_suspect_years_get_hollow_markers(self):
        # Act
        root = svg_root(trend(suspect=["2023-24"]))
        cash = root.find(".//{*}g[@data-basis='cash']")
        hollow = [c for c in cash.findall("{*}circle") if "hollow" in c.attrib["class"]]
        # Assert
        self.assertEqual(len(hollow), 1)
        self.assertIn("2023-24", hollow[0].find("{*}title").text)
        self.assertIn("fill:var(--paper", hollow[0].attrib["style"])

    def test_segments_into_partial_years_are_dashed(self):
        # Act
        root = svg_root(trend(partial=["2024-25"]))
        cash = root.find(".//{*}g[@data-basis='cash']")
        partial = next(p for p in cash.findall("{*}path") if "partial" in p.attrib["class"].split())
        # Assert
        self.assertIsNotNone(partial)
        self.assertIn("stroke-dasharray", partial.attrib)
        self.assertEqual(partial.attrib["d"].count("M"), 1)

    def test_every_line_is_labelled_at_its_end(self):
        # Act
        root = svg_root(trend())
        labels = [t.text for t in root.iter() if t.tag.split("}")[-1] == "text" and t.attrib.get("class") == "direct"]
        # Assert: one label per line (cash, real and the always-visible line); a label keeps its colour in both bases.
        self.assertEqual(sorted(labels), ["Similar schools", "This school", "This school"])
        classes = {g.attrib["data-basis"]: g.find("{*}path").attrib["class"].split() for g in root.iter() if "data-basis" in g.attrib}
        self.assertIn("s1", classes["cash"])
        self.assertIn("s1", classes["real"])

    def test_bases_sit_in_groups_with_real_hidden_by_default(self):
        # Act
        root = svg_root(trend())
        groups = {g.attrib["data-basis"]: g for g in root.iter() if "data-basis" in g.attrib}
        # Assert
        self.assertEqual(set(groups), {"cash", "real"})
        self.assertNotIn("display", groups["cash"].attrib)
        self.assertEqual(groups["real"].attrib["display"], "none")
        top_level = [c for c in root if c.tag.split("}")[-1] == "path" and c.attrib["class"].startswith("line")]
        self.assertEqual(len(top_level), 1, "the basis-None line is always visible, outside the groups")

    def test_units_change_the_axis_format(self):
        # Arrange
        lines = [{"label": "Pupils", "values": {"2023-24": 410, "2024-25": 395}, "basis": None}]
        # Act
        pupils = trend(lines=lines, unit="pupils")
        share = trend(lines=[dict(lines[0], values={"2023-24": 4.5, "2024-25": 6.0})], unit="%")
        # Assert
        self.assertNotIn("£", pupils)
        self.assertNotIn("£", share)
        self.assertIn("%</text>", share)

    def test_text_is_escaped_and_odd_inputs_still_parse(self):
        # Arrange
        bad = "<script>alert('x')</script> & Co"
        cases = {"escaped": trend(title=bad, desc=bad, lines=[{"label": bad, "values": {"2024-25": 1}, "basis": "cash"}]),
                 "empty": trend(lines=[]), "all_none": trend(lines=[{"label": "x", "values": {y: None for y in YEARS}}]),
                 "no_years": trend(years=[]), "negative": trend(lines=[{"label": "Reserve", "values": {"2023-24": -50_000, "2024-25": 20_000}}]),
                 "one_line_empty": trend(lines=[{"label": "Empty", "values": {y: None for y in YEARS}, "basis": "cash"},
                                                {"label": "Full", "values": {y: 1_000 for y in YEARS}, "basis": "cash"}]),
                 "single_year": trend(years=["2024-25"], lines=[{"label": "One", "values": {"2024-25": 5}}])}
        for name, markup in cases.items():
            with self.subTest(name):
                # Act
                root = svg_root(markup)
                # Assert
                self.assertEqual(root.attrib["role"], "img")
                self.assertNotIn("<script>", markup)
                self.assertNotIn("nan", markup.lower())


class SparklineTest(unittest.TestCase):
    def test_sparkline_is_small_labelled_and_escaped(self):
        # Arrange
        values = [(f"{2010 + i}-{11 + i}", 4_000 + 123.456 * i) for i in range(16)]
        for label in ("Income per pupil, 2010-11 to 2025-26", "<b>" + "x" * 600 + "</b>"):
            with self.subTest(label=label[:20]):
                # Act
                svg = charts.sparkline(values, label=label)
                root = svg_root(svg)
                # Assert
                self.assertLessEqual(len(svg.encode("utf-8")), 400)
                self.assertEqual(root.attrib["role"], "img")
                self.assertTrue(root.attrib["aria-label"])
                self.assertNotIn("<b>", svg)

    def test_sparkline_gaps_and_empty_input(self):
        # Act
        svg = charts.sparkline([("a", 1), ("b", None), ("c", 3), ("d", 2)], label="Reserve")
        # Assert
        self.assertEqual(svg_root(svg).find("{*}path").attrib["d"].count("M"), 2)
        self.assertEqual(charts.sparkline([], label="x"), "")
        self.assertEqual(charts.sparkline([("a", None)], label="x"), "")


if __name__ == "__main__":
    unittest.main()
