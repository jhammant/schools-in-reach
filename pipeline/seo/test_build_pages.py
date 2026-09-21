"""Offline fixture tests. Never read or alter the real school data."""
from copy import deepcopy
from html.parser import HTMLParser
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from pipeline.seo import build_pages as seo


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.meta, self.links, self.schemas = {}, [], []
        self.canonical = None
        self.in_json = False
        self.json_text = ""
        self.feed(Path(path).read_text())

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            self.meta[a.get("name", a.get("property"))] = a.get("content")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a["href"]
        if tag == "a":
            self.links.append(a.get("href"))
        if tag == "script" and a.get("type") == "application/ld+json":
            self.in_json, self.json_text = True, ""

    def handle_data(self, text):
        if self.in_json:
            self.json_text += text

    def handle_endtag(self, tag):
        if tag == "script" and self.in_json:
            self.schemas.extend(json.loads(self.json_text))
            self.in_json = False


class HelpersTest(unittest.TestCase):
    def test_slug_diacritics_ampersand_and_punctuation(self):
        self.assertEqual(seo.slug("Ysgol Ŵyn & Éire / St. Mary's"), "ysgol-wyn-and-eire-st-mary-s")

    def test_slug_length_and_trim(self):
        value = seo.slug("Long & " * 40)
        self.assertLessEqual(len(value), 80)
        self.assertFalse(value.startswith("-") or value.endswith("-"))
        self.assertRegex(value, r"^[a-z0-9-]+$")

    def test_title_length_rule(self):
        self.assertEqual(seo.school_title("Oak"), "Oak admissions, catchment & Ofsted | Schools in Reach")
        self.assertEqual(seo.school_title("St Andrew's Primary School"), "St Andrew's Primary School admissions, catchment & Ofsted")
        self.assertEqual(seo.shorten("First second third", 14), "First second…")
        long = seo.school_title("The exceptionally long school name " * 8)
        self.assertLessEqual(len(long), 70)
        self.assertTrue(long.endswith("…"))
        self.assertEqual(seo.shorten("X" * 100, 70), "…")

    def test_no_empty_or_metadata_only_quality_signals(self):
        self.assertFalse(seo.has_admissions({"years": {"2026": {"notes": ["No data"]}}}))
        self.assertEqual(seo.ofsted_facts({"latest": {"kind": "graded", "overall_effectiveness": "Not judged"}})[0], "")
        self.assertFalse(seo.has_admissions({"years": {"2026": {"max_distance": None}}}))
        self.assertTrue(seo.has_admissions({"years": {"2026": {"total_offers": 0}}}))

    def test_date_uses_data_dates_not_clock(self):
        self.assertEqual(seo.data_date({"generated": "2026-09-17T12:00:00Z", "data_as_at": {"state": "2026-08-31"}}), "2026-09-17")
        self.assertEqual(seo.data_date({"data_as_at": "2026-08-31"}), "2026-08-31")

    def test_report_card_has_no_invented_overall_grade(self):
        label, day, rows = seo.ofsted_facts({"latest": {"kind": "report_card", "date": "2026-03-01", "report_card": {"inclusion": "Expected standard"}}})
        self.assertEqual((label, day, rows), ("Report card: Expected standard in its graded area", "1 March 2026", [("Inclusion", "Expected standard")]))

    def test_area_grades_are_summarised_not_labelled_published(self):
        same = seo.ofsted_facts({"latest": {"date": "2025-01-22", "judgements": {"quality_of_education": "Outstanding", "leadership_and_management": "Outstanding", "safeguarding_effective": True}}})
        self.assertEqual(same[:2], ("Outstanding in all 2 graded areas", "22 January 2025"))
        mixed = seo.ofsted_facts({"latest": {"kind": "report_card", "report_card": {"inclusion": "Strong standard", "achievement": "Needs attention", "safeguarding_standards": "Met"}}})
        self.assertEqual(mixed[0], "Report card: Strong standard in 1 area, Needs attention in 1 area")

    def test_open_band_cutoffs_read_as_all_offered(self):
        year = {"max_distance": {"A": 350.7, "B": 0.62}}
        self.assertEqual(seo.distance_text(year), ["A: All offered", "B: 0.62 mi"])
        self.assertFalse(seo.is_open_band(3.0))
        self.assertTrue(seo.is_open_band(3.15))

    def test_non_http_sources_not_executable(self):
        self.assertEqual(seo.safe_url("javascript:alert(1)"), "")
        self.assertEqual(seo.safe_url("https://example.org"), "https://example.org")

    def test_nearby_distance_and_missing_coordinates(self):
        school = {"lat": 51, "lon": 0}
        self.assertLess(seo.proximity(school, {"lat": 51.01, "lon": 0}), seo.proximity(school, {"lat": 52, "lon": 0}))
        self.assertEqual(seo.proximity(school, {}), float("inf"))


class BuildTest(unittest.TestCase):
    def write(self, relative, value):
        path = self.site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        (self.site / "index.html").write_text('<meta name="google-adsense-account" content="ca-pub-test">')
        self.source = {"title": "Register & census", "url": "https://example.org/data?a=1&b=2", "licence": "Open Government Licence v3.0"}
        self.base = {"generated": "2026-09-17", "sources": [self.source]}
        self.school = {"urn": 100001, "name": "St Ŵyn & Mary's <School>", "phase": "Secondary", "type": "Academy converter", "age_low": 11, "age_high": 18, "lat": 51.5, "lon": -0.1, "town": "Test Town", "postcode": "TE1 1ST"}
        schools = [self.school,
                   {"urn": 100002, "name": "Only Census Primary", "phase": "Primary", "pupils": 42},
                   {"urn": 100003, "name": "Closed School", "status": "Closed"},
                   {"urn": 100004, "name": "Admissions And Results", "phase": "Secondary"},
                   {"urn": 100005, "name": "Metadata Only", "phase": "Middle deemed secondary"}]
        self.write("data/england/las.json", {**self.base, "las": [{"la_code": "999", "name": "Test & Vale", "region": "London"}]})
        self.write("data/la/999/schools.json", {**self.base, "schools": schools})
        self.write("data/la/999/admissions.json", {**self.base, "secondary": {
            "100001": {"years": {"2026": {"max_distance": {"A": 0.84, "B": 1.26}, "groups": ["A", "B"], "pan": 100, "applications": 230, "total_offers": 100}}},
            "100004": {"years": {"2026": {"max_distance": 0.5, "pan": 120}}},
            "100005": {"years": {"2026": {"notes": ["Nothing published"]}}}}})
        self.write("data/la/999/ofsted.json", {**self.base, "schools": {"100001": {"latest": {"kind": "graded", "date": "2025-01-01", "judgements": {"overall_effectiveness": "Good"}}}, "100005": {"latest": {"kind": "graded", "overall_effectiveness": "Not judged"}}}})
        self.write("data/la/999/league_tables.json", {**self.base, "rows": [{"urn": 100004, "ks4_p8": 0.25, "ks4_p8_year": "2023/24", "ks4_year": "2024/25", "ks4_a8": 51.2}, {"urn": 100005, "ks4_year": "2024/25", "ks4_cohort": 20}]})
        self.summary = seo.build(self.site, sitemap_limit=1)

    def path(self, urn):
        return next((self.site / "school").glob(f"{urn}-*/index.html"))

    def test_quality_gate_and_closed_exclusion(self):
        self.assertEqual((self.summary["schools"], self.summary["indexable"], self.summary["noindexed"], self.summary["closed_skipped"]), (4, 2, 2, 1))
        self.assertNotIn("robots", Page(self.path(100001)).meta)
        self.assertEqual(Page(self.path(100002)).meta["robots"], "noindex,follow")
        self.assertEqual(Page(self.path(100005)).meta["robots"], "noindex,follow")
        self.assertFalse(list((self.site / "school").glob("100003-*")))

    def test_html_escaping_and_canonical(self):
        text = self.path(100001).read_text()
        self.assertIn("St Ŵyn &amp; Mary&#x27;s &lt;School&gt;", text)
        self.assertNotIn("<School>", text)
        page = Page(self.path(100001))
        self.assertEqual(page.canonical, seo.BASE + "/school/100001-st-wyn-and-mary-s-school/")
        self.assertIn("/#school=100001&la=999&tab=admissions", page.links)
        self.assertEqual(page.meta["google-adsense-account"], "ca-pub-test")
        self.assertNotIn("run by Test", text)

    def test_json_ld_parses_and_types_match(self):
        page = Page(self.path(100001))
        self.assertEqual([s["@type"] for s in page.schemas], ["BreadcrumbList", "HighSchool"])
        self.assertEqual(page.schemas[1]["name"], self.school["name"])
        self.assertEqual(page.schemas[1]["address"]["@type"], "PostalAddress")
        self.assertEqual(page.schemas[1]["geo"]["latitude"], 51.5)
        self.assertEqual(Page(self.path(100002)).schemas[1]["@type"], "ElementarySchool")
        self.assertEqual(Page(self.path(100005)).schemas[1]["@type"], "MiddleSchool")

    def test_descriptions_140_to_160_and_unique(self):
        descriptions = [Page(p).meta["description"] for p in (self.site / "school").glob("*/index.html")]
        self.assertEqual(len(descriptions), len(set(descriptions)))
        self.assertTrue(all(140 <= len(d) <= 160 for d in descriptions), descriptions)

    def test_sitemap_index_splitting_dates_and_quality(self):
        index = ET.parse(self.site / "sitemap.xml").getroot()
        self.assertEqual(index.tag, f"{{{seo.NS}}}sitemapindex")
        self.assertEqual(len(index), 3)
        urls = []
        for entry in index:
            url = entry.find("{*}loc").text
            root = ET.parse(self.site / url.removeprefix(seo.BASE + "/")).getroot()
            self.assertEqual(root.tag, f"{{{seo.NS}}}urlset")
            urls += [n.text for n in root.findall("{*}url/{*}loc")]
            self.assertTrue(all(n.text == "2026-09-17" for n in root.findall("{*}url/{*}lastmod")))
            if "schools-" in url:
                self.assertEqual(len(root), 1)
        self.assertEqual(len(urls), 8)
        self.assertTrue(any("100001-" in u for u in urls))
        self.assertFalse(any("100002-" in u or "100005-" in u for u in urls))

    def test_council_links_all_open_schools(self):
        page = Page(self.site / "council/test-and-vale/index.html")
        for urn in (100001, 100002, 100004, 100005):
            self.assertIn("/" + str(self.path(urn).relative_to(self.site).parent) + "/", page.links)
        self.assertIn("/council/", page.links)
        text = (self.site / "council/test-and-vale/index.html").read_text()
        self.assertIn("31 October", text)
        self.assertIn("15 January", text)

    def test_admissions_bands_units_and_results_vintage(self):
        text = self.path(100001).read_text()
        self.assertIn("A: 0.84 mi", text)
        self.assertIn("B: 1.26 mi", text)
        self.assertIn("0.84 to 1.26 miles", text)
        results = self.path(100004).read_text()
        self.assertIn("2023/24", results)
        self.assertIn("2024/25", results)
        self.assertNotIn(">null<", results)

    def test_scotland_wording_and_no_english_deadlines(self):
        self.write("data/uk/scotland_las.json", {**self.base, "las": [{"la_code": "S12000041", "name": "Angus", "nation": "Scotland"}]})
        self.write("data/la/S12000041/schools.json", {**self.base, "schools": [{"urn": 25300126, "name": "Angus Primary", "phase": "Primary", "pupils": 10}]})
        seo.build(self.site)
        school = self.path(25300126).read_text()
        council = (self.site / "council/angus/index.html").read_text()
        self.assertIn("catchment areas", school)
        self.assertIn("Education Scotland", school)
        self.assertNotIn("31 October", council)
        self.assertIn("See this school on the map", school)

    def test_rerun_removes_stale_pages_and_keeps_data_unchanged(self):
        files = {p: p.read_bytes() for p in (self.site / "data").rglob("*.json")}
        stale = self.site / "school/stale/index.html"
        stale.parent.mkdir()
        stale.write_text("old")
        seo.build(self.site)
        self.assertFalse(stale.exists())
        self.assertTrue(all(p.read_bytes() == content for p, content in files.items()))

    def test_failure_keeps_previous_generated_pages(self):
        before = self.path(100001).read_bytes()
        (self.site / "data/la/999/schools.json").write_text("invalid json")
        with self.assertRaises(ValueError):
            seo.build(self.site)
        self.assertEqual(self.path(100001).read_bytes(), before)

    def test_script_closing_name_safe_inside_json_ld(self):
        school = deepcopy(self.school)
        school["name"] = '</script><script>alert("test")</script>'
        self.write("data/la/999/schools.json", {**self.base, "schools": [school]})
        seo.build(self.site)
        page = Page(self.path(100001))
        self.assertEqual(page.schemas[1]["name"], school["name"])
        self.assertNotIn('<script>alert', self.path(100001).read_text())


class DeploymentTest(unittest.TestCase):
    """Run the actual deploy script with local stubs; never invoke Railway or rsync."""
    def test_failed_generator_prevents_staging(self):
        self.check_deploy(generator_exit=1, sitemap=False)

    def test_small_payload_prevents_staging_even_with_sitemap(self):
        self.check_deploy(generator_exit=0, sitemap=True)

    def test_missing_sitemap_prevents_staging(self):
        self.check_deploy(generator_exit=0, sitemap=False, school_count=10_000)

    def check_deploy(self, generator_exit, sitemap, school_count=1):
        source = Path(__file__).resolve().parents[2] / "deploy/railway/deploy.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "deploy/railway/deploy.sh"
            target.parent.mkdir(parents=True)
            target.write_text(source.read_text())
            site = root / "site"
            for i in range(school_count):
                school = site / "school" / str(i)
                school.mkdir(parents=True)
                (school / "index.html").write_text("example")
            if sitemap:
                (site / "sitemaps").mkdir()
                seo.write_sitemap(site / "sitemaps/pages.xml", [("/", "2026-09-17")])
                seo.write_sitemap(site / "sitemap.xml", [("/sitemaps/pages.xml", "2026-09-17")], index=True)
            binaries = root / "bin"
            binaries.mkdir()
            marker = root / "staged"
            python = binaries / "python3"
            python.write_text('#!/bin/sh\ncase "$1" in */build_pages.py) exit ' + str(generator_exit) + ';; esac\nexec "' + sys.executable + '" "$@"\n')
            python.chmod(0o755)
            for name in ("rsync", "railway"):
                stub = binaries / name
                stub.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 0\n')
                stub.chmod(0o755)
            environment = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"])
            result = subprocess.run(["bash", str(target)], env=environment, text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Deploy aborted", result.stderr)
            self.assertFalse(marker.exists(), "Staging or deployment ran despite invalid SEO output")


if __name__ == "__main__":
    unittest.main()
