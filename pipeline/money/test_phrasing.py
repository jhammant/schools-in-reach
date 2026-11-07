"""Tests for phrasing.ratio_words (contract C1) against data/phrasing_cases.json, the table the JS mirrors share."""

import json
import math
import unittest
from pathlib import Path

from pipeline.money import phrasing

CASES = Path(__file__).resolve().parent / "data" / "phrasing_cases.json"
BANDS = ["about the same as", "a little more than", "a little less than", "about a quarter more than", "about a third more than",
         "about half as much again as", "about double", "about two and a half times", "about three-quarters of",
         "about two-thirds of", "about half", "about a third of", "about a quarter of", "under a quarter of"]


def load_cases() -> list[dict]:
    """The shared case table: [{a, b, words}, ...]."""
    with open(CASES, encoding="utf-8") as fh:
        return json.load(fh)


class RatioWordsTableTest(unittest.TestCase):
    def test_every_case_in_the_table(self):
        # Arrange
        cases = load_cases()
        # Act
        got = [phrasing.ratio_words(c["a"], c["b"]) for c in cases]
        # Assert
        for case, words in zip(cases, got):
            self.assertEqual(words, case["words"], case)

    def test_the_table_covers_every_band_and_the_missing_cases(self):
        # Arrange
        cases = load_cases()
        # Act
        words = {c["words"] for c in cases}
        # Assert
        self.assertGreaterEqual(len(cases), 30)
        for band in BANDS:
            self.assertIn(band, words)
        self.assertTrue(any(w and w.endswith(" times") and w[6:-6].isdigit() for w in words))
        self.assertIn(None, words)
        for key in ("a", "b"):
            self.assertTrue(any(c[key] is None for c in cases), key)
            self.assertTrue(any(c[key] == 0 for c in cases), key)
            self.assertTrue(any(isinstance(c[key], (int, float)) and c[key] < 0 for c in cases), key)


class RatioWordsTest(unittest.TestCase):
    def test_band_edges_follow_the_contract(self):
        # Arrange
        edges = {(105, 100): "about the same as", (95, 100): "about the same as", (115, 100): "a little more than",
                 (129, 100): "about a third more than", (142, 100): "about half as much again as", (175, 100): "about double",
                 (225, 100): "about two and a half times", (275, 100): "about 3 times", (85, 100): "a little less than",
                 (71, 100): "about three-quarters of", (58, 100): "about two-thirds of", (42, 100): "about half",
                 (29, 100): "about a third of", (21, 100): "about a quarter of", (20.9, 100): "under a quarter of"}
        # Act
        got = {k: phrasing.ratio_words(*k) for k in edges}
        # Assert
        self.assertEqual(got, edges)

    def test_times_rounds_halves_up_and_never_says_fewer_than_3(self):
        # Act / Assert
        self.assertEqual(phrasing.ratio_words(450, 100), "about 5 times")
        self.assertEqual(phrasing.ratio_words(276, 100), "about 3 times")
        self.assertEqual(phrasing.ratio_words(1240, 100), "about 12 times")

    def test_says_nothing_for_values_that_are_not_positive_numbers(self):
        # Arrange
        bad = [None, 0, -1, "100", True, math.nan, math.inf, [100]]
        # Act
        got = [phrasing.ratio_words(x, 100) for x in bad] + [phrasing.ratio_words(100, x) for x in bad]
        # Assert
        self.assertEqual(got, [None] * (2 * len(bad)))

    def test_reads_before_a_noun_phrase(self):
        # Arrange: William Patten's PTFA, £111 per pupil in 2024-25, against Hackney's median that year.
        words = phrasing.ratio_words(111, 62.46)
        # Act
        line = f"raised {words} Hackney's typical PTA"
        # Assert
        self.assertEqual(line, "raised about double Hackney's typical PTA")

    def test_module_documents_itself(self):
        # Assert
        self.assertIn("C1", phrasing.__doc__)
        self.assertTrue(phrasing.ratio_words.__doc__)


if __name__ == "__main__":
    unittest.main()
