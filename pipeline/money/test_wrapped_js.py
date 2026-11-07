"""Runs the node suite for assets/wrapped.js (test_wrapped_js.mjs), handing it the real context.json that
wrapped.context_doc() builds, through WRAPPED_CTX naming a file in a temp dir."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pipeline.money import wrapped

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WrappedJsTest(unittest.TestCase):
    def test_node_suite_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            ctx = Path(tmp) / "context.json"
            ctx.write_text(json.dumps(wrapped.context_doc("2026-11-07"), ensure_ascii=False), encoding="utf-8")
            env = dict(os.environ, WRAPPED_CTX=str(ctx))
            # Act
            proc = subprocess.run(["node", "--test", "--test-reporter=tap", str(REPO / "pipeline/money/test_wrapped_js.mjs")],
                                  cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
        # Assert
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
        self.assertRegex(proc.stdout, r"# fail 0")


if __name__ == "__main__":
    unittest.main()
