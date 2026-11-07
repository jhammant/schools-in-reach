"""Runs the node tests for assets/tools.js (MoneyTools) with 40 status cases worked out by status.py, so the
JS port is checked against the Python it copies, and scans tools.js for any network call other than a
same-site fetch of a /data/ path. Offline; node is optional (skipped without it)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pipeline.money import site
from pipeline.money import status as health

REPO = Path(__file__).resolve().parents[2]
TOOLS_JS = REPO / "pipeline/money/assets/tools.js"
SUITE = REPO / "pipeline/money/test_tools_js.mjs"
INCOME = 3_000_000


def row(end, *, income=INCOME, balance=0, reserve=200_000, **extra):
    """One full-year finance row ending end ('2025-03'), labelled with its financial year ('2024-25')."""
    start = int(end[:4]) - 1
    data = {"period_end": end, "year": f"{start}-{str(start + 1)[2:]}", "source": "CFR", "period_months": 12,
            "phase": "primary", "pupils": 400, "total_income": income, "total_expenditure": income - balance,
            "in_year_balance": balance, "revenue_reserve": reserve}
    data.update(extra)
    return data


def build_cases():
    """(name, rows) pairs covering every status, each boundary and every row the assessment must skip."""
    overspend = [row("2024-03", balance=-100_000, reserve=400_000), row("2025-03", balance=-100_000)]
    return [
        ("healthy", [row("2025-03", reserve=200_000)]),
        ("tight", [row("2025-03", reserve=60_000)]),
        ("large reserves", [row("2025-03", reserve=300_000)]),
        ("in deficit, streak 1", [row("2025-03", balance=-100_000, reserve=-150_000)]),
        ("in deficit, streak 2", [row("2024-03", balance=-100_000, reserve=50_000), row("2025-03", balance=-200_000, reserve=-150_000)]),
        ("in deficit, streak 3", [row("2023-03", balance=-50_000, reserve=100_000), row("2024-03", balance=-100_000, reserve=0),
                                  row("2025-03", balance=-100_000, reserve=-100_000)]),
        ("heading for deficit", [row("2023-03", balance=100_000, reserve=500_000), row("2024-03", balance=-150_000, reserve=350_000),
                                 row("2025-03", balance=-200_000, reserve=150_000)]),
        ("share exactly 3% is healthy", [row("2025-03", reserve=90_000)]),
        ("share just under 3% is tight", [row("2025-03", reserve=89_999)]),
        ("share just over 3% is healthy", [row("2025-03", reserve=90_001)]),
        ("exactly 8% primary is large", [row("2025-03", reserve=240_000)]),
        ("just under 8% primary is healthy", [row("2025-03", reserve=239_999)]),
        ("exactly 5% secondary is large", [row("2025-03", income=6_000_000, reserve=300_000, phase="secondary")]),
        ("5% primary is healthy", [row("2025-03", income=6_000_000, reserve=300_000)]),
        ("just under 5% secondary is healthy", [row("2025-03", income=6_000_000, reserve=299_999, phase="secondary")]),
        ("runway exactly 3.0 counts", [overspend[0], dict(overspend[1], revenue_reserve=300_000)]),
        ("runway just over 3.0 does not", [overspend[0], dict(overspend[1], revenue_reserve=300_003)]),
        ("runway 2.5 rounds half to even", [overspend[0], dict(overspend[1], revenue_reserve=250_000)]),
        ("runway 0.4 shows the 0.5 floor", [overspend[0], dict(overspend[1], revenue_reserve=40_000)]),
        ("runway 1.5 is plural", [overspend[0], dict(overspend[1], revenue_reserve=150_000)]),
        ("one overspend only", [row("2024-03", balance=50_000, reserve=250_000), row("2025-03", balance=-50_000, reserve=200_000)]),
        ("healthy, two overspends, watch the trend", [row("2024-03", balance=-10_000, reserve=210_000), row("2025-03", balance=-10_000, reserve=200_000)]),
        ("large, drawing on it", [row("2024-03", balance=-10_000, reserve=410_000), row("2025-03", balance=-10_000, reserve=400_000)]),
        ("negative reserve, 2.5% rounds to 2%", [row("2025-03", balance=-75_000, reserve=-75_000)]),
        ("deficit of £2.5k rounds to £2k", [row("2025-03", balance=-2_500, reserve=-2_500)]),
        ("£1.25m rounds to £1.2m and 12.5% to 12%", [row("2025-03", income=10_000_000, reserve=1_250_000)]),
        ("reserve under £1,000", [row("2025-03", reserve=500)]),
        ("reserve exactly zero", [row("2025-03", reserve=0)]),
        ("academy with trust share above zero", [row("2025-08", reserve=-20_000, source="AAR", revenue_reserve_incl_trust_share=150_000)]),
        ("academy with trust share below zero", [row("2025-08", reserve=50_000, source="AAR", revenue_reserve_incl_trust_share=-30_000)]),
        ("did_not_supply rows are skipped", [row("2024-03", reserve=200_000), row("2025-03", reserve=-500_000, did_not_supply=True)]),
        ("6-month rows are skipped", [row("2024-03", reserve=200_000), row("2025-03", reserve=-100_000, period_months=6)]),
        ("duplicated period_end keeps the later row", [row("2025-03", reserve=60_000), row("2025-03", reserve=300_000)]),
        ("missing pupils everywhere", [row("2024-03", pupils=None), row("2025-03", pupils=None)]),
        ("missing pupils in the first year", [row("2023-03", pupils=None), row("2024-03", pupils=400), row("2025-03", pupils=380)]),
        ("no rows", []),
        ("no usable rows", [row("2025-03", period_months=6), {"period_end": "2024-03", "did_not_supply": True},
                            row("2023-03", income=0), row("2022-03", reserve=None)]),
        ("rows out of order", [row("2025-03", balance=-30_000, reserve=170_000), row("2023-03", balance=20_000, reserve=220_000),
                               row("2024-03", balance=-20_000, reserve=200_000)]),
        ("long history averages the last three years", [row(f"{y}-03", balance=-300_000 if y < 2023 else -50_000, reserve=600_000,
                                                            pupils=450 - 10 * (y - 2020)) for y in range(2020, 2026)]),
        ("no phase and no in-year balance", [row("2024-03", phase=None, in_year_balance=None, reserve=280_000),
                                             row("2025-03", phase=None, in_year_balance=None, reserve=270_000)]),
    ]


class StatusCasesTest(unittest.TestCase):
    def test_cases_cover_every_status_and_the_none_result(self):
        # Arrange
        cases = build_cases()
        # Act
        results = [health.assess(rows) for _, rows in cases]
        # Assert
        self.assertEqual(len(cases), 40)
        self.assertEqual({r["status"] for r in results if r}, set(health.ORDER))
        self.assertGreaterEqual(sum(r is None for r in results), 2)
        self.assertIn("about 0 year.", next(r["reason"] for (n, _), r in zip(cases, results) if n.startswith("runway 0.4")))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ToolsJsNodeTest(unittest.TestCase):
    def test_node_suite_passes_with_python_status_cases(self):
        # Arrange
        cases = build_cases()
        payload = {"cases": [{"name": n, "rows": rows} for n, rows in cases],
                   "expected": [health.assess(rows) for _, rows in cases]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status_cases.json"
            path.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
            env = dict(os.environ, MONEY_STATUS_CASES=str(path))
            # Act
            proc = subprocess.run(["node", "--test", "--test-reporter=tap", str(SUITE)], cwd=REPO, env=env,
                                  capture_output=True, text=True, timeout=120)
        # Assert
        self.assertEqual(proc.returncode, 0, proc.stdout[-4000:] + proc.stderr[-2000:])
        self.assertIn("# fail 0", proc.stdout)
        self.assertNotIn("# skipped", proc.stdout.replace("# skipped 0", ""))


class ToolsJsStaticTest(unittest.TestCase):
    def setUp(self):
        self.source = TOOLS_JS.read_text(encoding="utf-8")

    def test_no_network_api_other_than_fetch(self):
        # Arrange
        banned = ["XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "importScripts", "import("]
        # Act
        found = [word for word in banned if word in self.source]
        # Assert
        self.assertEqual(found, [])

    def test_every_fetch_call_requests_a_data_path(self):
        # Arrange
        calls = [m.end() for m in re.finditer(r"\bfetch\s*\(", self.source)]
        # Act
        bad = [self.source[i:i + 40] for i in calls if not re.match(r"\s*(['\"])/data/", self.source[i:])]
        # Assert
        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(bad, [])

    def test_only_known_urls_appear_and_none_is_requested(self):
        # Arrange
        allowed = {site.BASE_MONEY, "https://financial-benchmarking-and-insights-tool.education.gov.uk/",
                   "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/", "http://www.w3.org/2000/svg"}
        # Act
        urls = set(re.findall(r"https?://[^\s\"'<>)]+", self.source))
        # Assert
        self.assertEqual(urls - allowed, set())
        self.assertIn(f'var BASE = "{site.BASE_MONEY}";', self.source)

    def test_no_html_built_from_strings(self):
        # Act / Assert
        self.assertNotIn("innerHTML", self.source)
        self.assertNotIn("insertAdjacentHTML", self.source)
        self.assertNotIn("document.write", self.source)


if __name__ == "__main__":
    unittest.main()
