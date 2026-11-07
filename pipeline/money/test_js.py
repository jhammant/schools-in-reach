"""Runs the node suites for the School Money front end from pytest: trend.js, app.js, and the review
suites for the app shell and the map. Skipped when node is not installed."""

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUITES = [
    "pipeline/money/test_trend.mjs",
    "pipeline/money/test_app_js.mjs",
    "tests/money_shell_review.test.mjs",
    "tests/test_map_review.mjs",
]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class NodeSuitesTest(unittest.TestCase):
    def test_node_suites_pass(self):
        for suite in SUITES:
            with self.subTest(suite=suite):
                # Arrange
                path = REPO / suite
                self.assertTrue(path.is_file(), suite)
                # Act
                proc = subprocess.run(["node", "--test", "--test-reporter=tap", str(path)],
                                      capture_output=True, text=True, timeout=120, cwd=REPO)
                # Assert
                self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
                self.assertRegex(proc.stdout, r"# fail 0")


if __name__ == "__main__":
    sys.exit(unittest.main())
