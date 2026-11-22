"""The house promo slot's copy of the shared picker, the saved feed and the deploy-time refresh.

Offline: the refresh is tested against file:// URLs, never hammantlabs.com.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.seo import build_pages as seo
from pipeline.seo import refresh_house_offers as refresh

SNAPSHOT = Path(seo.__file__).with_name("house_offers.json")
FEED = json.loads(SNAPSHOT.read_text(encoding="utf-8"))


class SharedPickerTest(unittest.TestCase):
    """Answers that hammantlabs-sites tests/promo_vectors.json also pins for the browser loader."""

    def test_hash_matches_the_shared_vectors(self):
        for key, expected in (("", 2872998923), ("a", 444641715), ("foobar", 202221276), ("/école/", 1983954245)):
            self.assertEqual(seo.house_promo.stable_hash(key), expected, key)

    def test_picks_match_the_shared_vectors(self):
        cases = [
            ("/school/100000/a/", [], "termminder-term-dates"),
            ("/council/hackney/", [], "binminder-reminders"),
            ("/school/100000/a/", ["termminder"], "binminder-reminders"),
        ]
        for key, exclude, expected in cases:
            # Act
            chosen = seo.house_promo.pick(FEED, "schoolsinreach", seo.PROMO_TAGS, key, exclude, today="2026-11-22")

            # Assert
            self.assertEqual(chosen["id"], expected, key)


class SavedFeedTest(unittest.TestCase):
    def test_the_committed_snapshot_is_valid_and_has_offers_for_this_site(self):
        # Act
        errors = refresh.check(FEED)

        # Assert
        self.assertEqual(errors, [])
        placed = sorted(o["id"] for o in FEED["offers"] if "schoolsinreach" in o["show_on"])
        self.assertEqual(placed, ["binminder-reminders", "termminder-term-dates"])

    def test_the_first_good_copy_wins_and_bad_copies_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            # Arrange
            bad, good = Path(directory) / "bad.json", Path(directory) / "good.json"
            bad.write_text("{not json")
            good.write_text(json.dumps(FEED))

            # Act / Assert
            self.assertEqual(seo.load_house_offers((bad, good)), FEED)
            self.assertEqual(seo.load_house_offers((Path(directory) / "missing.json", good)), FEED)
            self.assertIsNone(seo.load_house_offers((bad, Path(directory) / "missing.json")))


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache" / "house_offers.json"

    def serve(self, feed):
        path = self.root / "live.json"
        path.write_text(feed if isinstance(feed, str) else json.dumps(feed))
        return path.as_uri()

    def test_saves_a_valid_live_feed(self):
        # Act
        placed = refresh.refresh(self.serve(FEED), self.cache)

        # Assert
        self.assertEqual(json.loads(self.cache.read_text()), FEED)
        self.assertIn("binminder-reminders", placed)

    def test_keeps_the_saved_copy_when_the_live_feed_is_wrong(self):
        # Arrange
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text("saved")
        unsafe = copy.deepcopy(FEED)
        next(o for o in unsafe["offers"] if o["id"] == "binminder-reminders")["links"]["schoolsinreach"] = "http://example.com/"
        no_site = copy.deepcopy(FEED)
        del no_site["sites"]["schoolsinreach"]
        for offer in no_site["offers"]:
            offer["show_on"] = [s for s in offer["show_on"] if s != "schoolsinreach"]
            offer["links"].pop("schoolsinreach", None)

        for feed in ("<html>not json</html>", unsafe, no_site):
            with self.subTest(feed=str(feed)[:30]):
                # Act / Assert
                with self.assertRaises(ValueError):
                    refresh.refresh(self.serve(feed), self.cache)
                self.assertEqual(self.cache.read_text(), "saved")


if __name__ == "__main__":
    unittest.main()
