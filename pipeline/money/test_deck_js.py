"""Runs the node suite for assets/deck.js (test_deck_js.mjs) from pytest, handing it the IFS context that
deck.py writes into the /deck/ page through DECK_CONTEXT_FILE (a JSON file in a temporary directory)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pipeline.money import deck

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DeckJsTest(unittest.TestCase):
    def test_node_suite_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            context = Path(tmp) / "deck_context.json"
            context.write_text(json.dumps(deck.deck_context(), ensure_ascii=False), encoding="utf-8")
            env = {**os.environ, "DECK_CONTEXT_FILE": str(context)}
            # Act
            proc = subprocess.run(["node", "--test", "--test-reporter=tap", str(REPO / "pipeline/money/test_deck_js.mjs")],
                                  capture_output=True, text=True, timeout=120, cwd=REPO, env=env)
        # Assert
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
        self.assertRegex(proc.stdout, r"# fail 0")


if __name__ == "__main__":
    sys.exit(unittest.main())
