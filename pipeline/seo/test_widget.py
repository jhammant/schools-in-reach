"""Widget contracts and generator integration; all builds use temporary fixtures."""
import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

from pipeline.seo import build_pages as seo
from pipeline.seo import test_build_pages as fixtures

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"


class WidgetTest(unittest.TestCase):
    def test_agent_registry_schema(self):
        agents = json.loads((SITE / "agents.json").read_text())
        self.assertIsInstance(agents, list)
        self.assertTrue(agents)
        ids = set()
        hostname = r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
        for agent in agents:
            self.assertRegex(agent["id"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
            self.assertNotIn(agent["id"], ids)
            ids.add(agent["id"])
            self.assertIsInstance(agent["name"], str)
            self.assertTrue(agent["name"].strip())
            self.assertIn(agent["status"], ("active", "trial", "cancelled"))
            self.assertIsInstance(agent["domains"], list)
            self.assertTrue(agent["domains"])
            for domain in agent["domains"]:
                self.assertIsNotNone(re.fullmatch(hostname, domain), domain)

    def fixture(self):
        fixture = fixtures.BuildTest("test_quality_gate_and_closed_exclusion")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        return fixture

    def test_generated_slugs_match_every_school_path_and_exclude_closed(self):
        fixture = self.fixture()
        maps = sorted((fixture.site / "embed/slugs").glob("*.json"))
        self.assertEqual([p.stem for p in maps], ["999"])  # one small map per council, not one national file
        slugs = {k: v for p in maps for k, v in json.loads(p.read_text()).items()}
        self.assertEqual(len(slugs), fixture.summary["schools"])
        self.assertFalse((fixture.site / "embed/slugs.json").exists())
        self.assertNotIn("100003", slugs)
        for urn, slug in slugs.items():
            self.assertTrue((fixture.site / f"school/{urn}-{slug}/index.html").is_file())
        self.assertEqual(slugs["100001"], "st-wyn-and-mary-s-school")

    def test_rebuild_preserves_embed_source_and_replaces_slug_map(self):
        fixture = self.fixture()
        source = fixture.site / "embed/index.html"
        source.write_text("widget source")
        fixture.write("data/la/999/schools.json", {"schools": [{**fixture.school, "name": "Renamed School"}]})
        seo.build(fixture.site)
        self.assertEqual(source.read_text(), "widget source")
        self.assertEqual(json.loads((fixture.site / "embed/slugs/999.json").read_text()), {"100001": "renamed-school"})

    def test_agents_in_sitemap_and_generated_navigation(self):
        fixture = self.fixture()
        urls = [n.text for n in ET.parse(fixture.site / "sitemaps/pages.xml").findall("{*}url/{*}loc")]
        self.assertIn(seo.BASE + "/agents/", urls)
        self.assertEqual(fixture.path(100001).read_text().count('href="/agents/"'), 2)

    def test_sales_metadata_and_valid_product_offer(self):
        path = SITE / "agents/index.html"
        page = fixtures.Page(path)
        self.assertIn("<title>School finder widget for estate agents | Schools in Reach</title>", path.read_text())
        self.assertEqual(page.canonical, seo.BASE + "/agents/")
        self.assertTrue(page.meta["description"])
        product = next(s for s in page.schemas if s["@type"] == "Product")
        offer = product["offers"]
        self.assertEqual(offer["@type"], "Offer")
        self.assertEqual(offer["price"], "29.00")
        self.assertEqual(offer["priceCurrency"], "GBP")
        self.assertEqual(offer["priceSpecification"]["unitText"], "branch per month")
        self.assertIn('href="#pricing"', path.read_text())

    def test_agents_footer_and_static_analytics_excludes_embed(self):
        html = (SITE / "agents/index.html").read_text()
        self.assertIn(seo.LABS_FOOTER, html)
        self.assertIn('<script type="module" src="/js/page-analytics.js"></script>', html)
        self.assertNotIn("nofollow", html)
        for path in ("embed/index.html", "js/embed.js"):
            text = (SITE / path).read_text()
            self.assertNotIn("analytics.js", text)
            self.assertNotIn("initAnalytics", text)

    def test_loader_size_and_safe_dom_construction(self):
        script = (SITE / "widget.js").read_bytes()
        self.assertLess(len(script), 3000)
        self.assertNotRegex(script.decode(), r"\beval\s*\(|\binnerHTML\b|document\.write")
        self.assertNotIn("innerHTML", (SITE / "js/embed.js").read_text())
        self.assertIn('event.origin !== frame.origin', script.decode())
        self.assertIn('api.frames.get(event.source)', script.decode())

    def test_embed_credit_and_no_map_or_blocking_frame_headers(self):
        html = (SITE / "embed/index.html").read_text()
        self.assertIn('School data by Schools in Reach', html)
        self.assertIn('target="_blank" rel="noopener"', html)
        self.assertNotIn("nofollow", html)
        self.assertNotIn("leaflet", html.lower())
        nginx = (ROOT / "deploy/railway/nginx.conf.template").read_text()
        directives = "\n".join(line for line in nginx.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotRegex(directives.lower(), "x-frame-options|frame-ancestors|access-control-allow-origin")
        self.assertIn('public, max-age=300', directives)


if __name__ == "__main__":
    unittest.main()
