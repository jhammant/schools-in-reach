"""Checks on the hand-written pages in site/: search and share tags, the icon and what loads analytics."""
from html.parser import HTMLParser
import json
from pathlib import Path
import struct
import unittest

SITE = Path(__file__).resolve().parents[2] / "site"
BASE = "https://www.schoolsinreach.com"
PAGES = {"index.html": "/", "about.html": "/about.html", "apply.html": "/apply.html", "faq.html": "/faq.html",
         "privacy.html": "/privacy.html", "agents/index.html": "/agents/"}
# js/app.js starts analytics on the map; js/page-analytics.js on pages without map state.
MEASURED = {"index.html": "js/app.js", "agents/index.html": "/js/page-analytics.js"}


class Head(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.meta, self.links, self.scripts, self.schemas = {}, {}, [], []
        self.in_json = False
        self.feed(Path(path).read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            self.meta[a.get("name", a.get("property"))] = a.get("content")
        if tag == "link":
            self.links[a.get("rel")] = a.get("href")
        if tag == "script" and a.get("type") == "application/ld+json":
            self.in_json, self.json_text = True, ""
        elif tag == "script" and a.get("src"):
            self.scripts.append(a["src"])

    def handle_data(self, text):
        if self.in_json:
            self.json_text += text

    def handle_endtag(self, tag):
        if tag == "script" and self.in_json:
            self.schemas.extend(json.loads(self.json_text))
            self.in_json = False


class StaticPagesTest(unittest.TestCase):
    def test_every_page_has_canonical_share_tags_and_icon(self):
        for name, path in PAGES.items():
            with self.subTest(page=name):
                # Arrange
                url = BASE + path
                # Act
                head = Head(SITE / name)
                # Assert
                self.assertEqual(head.links["canonical"], url)
                self.assertEqual(head.meta["og:url"], url)
                self.assertTrue(head.meta["description"])
                self.assertEqual(head.meta["og:description"], head.meta["description"])
                self.assertEqual(head.meta["twitter:description"], head.meta["description"])
                self.assertEqual(head.meta["og:title"], head.meta["twitter:title"])
                self.assertEqual(head.meta["og:image"], BASE + "/og.png")
                self.assertEqual(head.meta["twitter:image"], BASE + "/og.png")
                self.assertEqual(head.meta["twitter:card"], "summary_large_image")
                self.assertTrue((SITE / head.links["icon"].lstrip("/")).is_file())

    def test_share_image_is_a_1200_by_630_png(self):
        # Arrange
        data = (SITE / "og.png").read_bytes()
        # Act
        width, height = struct.unpack(">II", data[16:24])
        # Assert
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual((width, height), (1200, 630))
        self.assertEqual((Head(SITE / "index.html").meta["og:image:width"], Head(SITE / "index.html").meta["og:image:height"]), ("1200", "630"))

    def test_icon_files_exist_for_browsers_that_ask_for_them(self):
        # Arrange / Act
        svg = (SITE / "favicon.svg").read_text(encoding="utf-8")
        ico = (SITE / "favicon.ico").read_bytes()
        # Assert
        self.assertIn("<svg", svg)
        self.assertEqual(ico[:4], b"\x00\x00\x01\x00")

    def test_home_page_describes_the_site_and_its_publisher(self):
        # Arrange / Act
        head = Head(SITE / "index.html")
        by_type = {s["@type"]: s for s in head.schemas}
        # Assert
        self.assertEqual(set(by_type), {"WebSite", "Organization"})
        self.assertEqual(by_type["WebSite"]["url"], BASE + "/")
        self.assertEqual(by_type["WebSite"]["description"], head.meta["description"])
        self.assertEqual(by_type["WebSite"]["publisher"]["@id"], by_type["Organization"]["@id"])
        self.assertTrue((SITE / by_type["Organization"]["logo"].removeprefix(BASE + "/")).is_file())
        # Nothing the site cannot back up: no ratings, reviews or prices.
        self.assertFalse({"aggregateRating", "review", "offers"} & (set(by_type["WebSite"]) | set(by_type["Organization"])))

    def test_analytics_loads_on_content_pages_and_never_on_the_embed(self):
        for name, script in MEASURED.items():
            with self.subTest(page=name):
                # Arrange / Act
                scripts = Head(SITE / name).scripts
                # Assert
                self.assertEqual(scripts.count(script), 1)
        # The embed's URL carries a postcode, so it must stay unmeasured.
        embed = (SITE / "embed/index.html").read_text(encoding="utf-8")
        self.assertNotIn("page-analytics.js", embed)
        self.assertNotIn("analytics.js", (SITE / "js/embed.js").read_text(encoding="utf-8"))

    def test_robots_allows_crawling_and_names_the_sitemap(self):
        # Arrange / Act
        robots = (SITE / "robots.txt").read_text(encoding="utf-8")
        # Assert
        self.assertIn("Allow: /", robots)
        self.assertNotIn("Disallow: /\n", robots)
        self.assertIn(f"Sitemap: {BASE}/sitemap.xml", robots)


if __name__ == "__main__":
    unittest.main()
