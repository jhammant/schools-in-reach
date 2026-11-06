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


if __name__ == "__main__":
    unittest.main()
