"""Runs the map.js node suite (test_map_js.mjs) and scans map.js and map.css statically.

Run: python3 -m pytest -q pipeline/money/test_map_js.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "pipeline/money/assets"
# Built from pieces so this file never contains the phrases it checks for.
BANNED = ["poor" + " school", "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", "no" + " pta", "307" + "k"]
TOKENS = ["--paper", "--card", "--card-2", "--line", "--line-strong", "--ink", "--ink-2", "--ink-3", "--accent", "--accent-ink",
          "--accent-soft", "--critical", "--serious", "--warning", "--good", "--plenty", "--c1", "--c2", "--c3", "--c4", "--band",
          "--grid", "--radius", "--radius-s", "--shadow", "--font", "--tap", "--measure"]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MapJsTest(unittest.TestCase):
    def test_node_suite_passes(self):
        # Act
        proc = subprocess.run(["node", "--test", "--test-reporter=tap", str(REPO / "pipeline/money/test_map_js.mjs")],
                              cwd=REPO, capture_output=True, text=True, timeout=120)
        # Assert
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
        self.assertIn("# fail 0", proc.stdout)


class MapAssetsStaticTest(unittest.TestCase):
    def test_no_banned_words_in_map_js_or_css(self):
        # Arrange
        texts = {p.name: p.read_text(encoding="utf-8").lower() for p in (ASSETS / "map.js", ASSETS / "map.css")}
        # Act
        found = [(name, w) for name, text in texts.items() for w in BANNED if w in text]
        # Assert
        self.assertEqual(found, [])

    def test_css_uses_tokens_only_and_never_redefines_the_palette(self):
        # Arrange
        css = (ASSETS / "map.css").read_text(encoding="utf-8")
        # Act
        defined = re.findall(r"(--[a-z0-9-]+)\s*:", css)
        used = set(re.findall(r"var\((--[a-z0-9-]+)\)", css))
        colours = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", css)
        # Assert
        self.assertEqual(defined, [])
        self.assertEqual(used - set(TOKENS), set())
        self.assertEqual(colours, [])
        self.assertIn("var(--tap)", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("max-height: 60vh", css)
        self.assertIn("min(70vh, 640px)", css)

    def test_js_builds_no_html_from_data(self):
        # Arrange
        js = (ASSETS / "map.js").read_text(encoding="utf-8")
        # Act
        inner = re.findall(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write", js)
        # Assert
        self.assertEqual(inner, [])
        self.assertIn("root.MoneyMap = API", js)
        self.assertIn('if (typeof document === "undefined") return;', js)
        self.assertIn('flavor: isDark() ? "dark" : "light"', js)
        self.assertIn("zoomSnap: 0.5, minZoom: 6", js)
        self.assertIn("maxBounds: [[49.5, -9], [61, 2.2]]", js)
        self.assertIn("history.replaceState", js)


if __name__ == "__main__":
    sys.exit(unittest.main())
