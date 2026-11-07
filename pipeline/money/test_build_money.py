"""Offline fixture tests for the School Money site build. Never reads or alters the real school data."""
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import types
import unittest
import xml.etree.ElementTree as ET

from pipeline.money import build_money

ROOT = Path(__file__).resolve().parents[2]
BASE_MONEY = "https://money.schoolsinreach.com"
# A fixed copy of SHARED 'GLOSSARY KEYS': the only keys a page may put in data-mf.
GLOSSARY_KEYS = {
    "total_income", "grant_funding", "grant_funding_government", "sen_funding", "pupil_premium", "self_generated_income", "donations",
    "donations_revenue", "donations_capital", "lettings_income", "facilities_income", "catering_income", "teacher_pension_ni_grants",
    "non_government_grants", "total_expenditure", "teaching_staff", "supply_staff", "education_support_staff", "admin_clerical_staff",
    "premises_staff", "catering_staff", "other_staff_costs", "total_staff", "premises", "energy", "occupation", "catering",
    "educational_supplies", "supplies_services", "bought_in_services", "revenue_reserve", "revenue_reserve_incl_trust_share",
    "reserve_committed", "reserve_uncommitted", "reserve_share", "in_year_balance", "per_pupil", "real_terms", "pupils", "fsm_pct",
    "ehcp_pct", "dsg_balance", "dsg_per_pupil", "deficit_total", "in_deficit_pct", "pta_income", "pta_spending", "pta_per_pupil",
    "trust_central_spend", "cfr_line", "aar_line", "status_in_deficit", "status_heading_for_deficit", "status_tight", "status_healthy",
    "status_large_reserves", "band",
}
# SHARED: B1 adds these glossary keys; pages may use them before B1's glossary.json merges.
GLOSSARY_KEYS |= {
    "other_dfe_grants", "gov_funding_pp", "spend_pp", "gov_vs_spend_gap", "falling_rolls", "pass_through", "high_send",
    "trust_central_spend_pp", "pta_gap", "pta_history", "statutory_override", "deficit_pp", "reserve_median_pp", "schools_in_deficit", "ifs_figure",
}
# The other units' modules (B1 series, B2 school page, B3 area pages): fixture tests of the fallback
# markup set them to None, so they stay true after those units merge.
OTHER_UNITS = ("series", "school_page", "area_pages")
BANNED = re.compile(r"poor school|failing|worst|bankrupt|scandal", re.I)
SCHOOL_JSON_KEYS = {
    "urn", "name", "path", "council", "status", "label", "reason", "year", "academy", "trust", "trust_path", "pupils", "income", "income_pp",
    "spend", "spend_pp", "reserve", "reserve_pp", "share", "balance", "balance_pp", "streak", "pupils_change", "years", "pp", "similar",
    "income_lines", "lines", "pta", "check",
}
MF_SPAN = re.compile(r'<span class="mf[^"]*"[^>]*?data-mf="([^"]+)"[^>]*>.*?</span>', re.S)
VOID = {"meta", "link", "input", "br", "img", "hr", "path", "circle", "rect", "line", "polyline", "use", "source"}


def row(urn, end, income, spend, reserve, source="CFR", pupils=300, **extra):
    year = f"{int(end[:4]) - 1}-{end[2:4]}" if source == "CFR" else f"{int(end[:4]) - 1}/{end[2:4]}"
    r = {"urn": urn, "year": year, "period_end": end, "source": source, "la": 204, "laestab": f"204{urn[-4:]}",
         "phase": "primary", "period_months": 12, "pupils": pupils, "total_income": income, "total_expenditure": spend,
         "in_year_balance": income - spend, "revenue_reserve": reserve, "teaching_staff": income * 0.5,
         "education_support_staff": income * 0.2, "premises": income * 0.05, "energy": income * 0.02, "grant_funding": income * 0.95}
    r.update(extra)
    return r


def school(urn, name, la=204, **extra):
    s = {"urn": urn, "name": name, "phase": "Primary", "type": "Community school", "town": "London",
         "postcode": "E8 1AA", "fsm_pct": 20, "laestab": f"{la}{str(urn)[-4:]}"}
    s.update(extra)
    return s


def make_site(root, councils, schools, rows, pta=None):
    """Write a register, history file and optional pta.json under root. councils: [(code, name)];
    schools: {code: [school dicts]}; rows: list of finance rows (SHARED 'FINANCE ROWS')."""
    site = root / "site"
    (site / "data/england").mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text('<html><head><meta property="og:image" content="/og.png"></head></html>', encoding="utf-8")
    (site / "data/england/las.json").write_text(json.dumps({"las": [{"la_code": c, "name": n, "region": "London"} for c, n in councils]}), encoding="utf-8")
    for code, items in schools.items():
        (site / "data/la" / str(code)).mkdir(parents=True, exist_ok=True)
        (site / "data/la" / str(code) / "schools.json").write_text(json.dumps({"schools": items}), encoding="utf-8")
    history = root / "history.jsonl"
    history.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    pta_path = root / "pta.json"
    if pta is not None:
        pta_path.write_text(json.dumps({"generated": "2026-11-06", "source": "test", "licence": "OGL", "schools": pta}), encoding="utf-8")
    return site, history, root / "missing-links.csv", pta_path


def full_rows(urn, reserve=100_000, years=("2023-03", "2024-03", "2025-03"), **extra):
    return [row(urn, end, 2_000_000, 1_990_000, reserve, **extra) for end in years]


def write_dsg(path, code="204", name="Hackney"):
    path.write_text(json.dumps({
        "source": {"title": "DfE DSG outturn", "url": "https://explore-education-statistics.service.gov.uk/"},
        "las": {code: {"name": name, "values": {"2022-23": -17_062_018, "2023-24": -19_080_140, "2024-25": -16_493_653}}},
        "england": {"2022-23": -1_168_833_480, "2023-24": -1_768_767_297, "2024-25": -3_596_295_748},
        "former_las": {}, "interventions": {"safety_valve": [code], "delivering_better_value": []}}), encoding="utf-8")
    return path


class Balance(HTMLParser):
    """Checks that non-void elements open and close in order (a HeadMetadata-like parser)."""

    def __init__(self, text):
        super().__init__()
        self.stack, self.errors, self.canonical = [], [], None
        self.feed(text)
        if self.stack:
            self.errors.append(f"unclosed {self.stack}")

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs) if tag not in VOID else None
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> closes {self.stack[-1] if self.stack else 'nothing'}")
        else:
            self.stack.pop()


def body_text(html):
    """The page body without head, scripts and SVG charts (charts.py prints its own axis labels)."""
    body = html.split("<main", 1)[1]
    body = re.sub(r"<svg.*?</svg>", "", body, flags=re.S)
    return re.sub(r"<script.*?</script>", "", body, flags=re.S)


def without_other_units(test):
    """setUp helper: the core's own fallback renderers and no extensions (map, deck, Wrapped, guides have
    their own tests, and ExtensionTest builds with them), whatever has merged; restored on cleanup."""
    saved = {name: getattr(build_money, name) for name in OTHER_UNITS + ("EXTENSIONS",)}
    for name in OTHER_UNITS:
        setattr(build_money, name, None)
    build_money.EXTENSIONS = ()
    test.addCleanup(lambda: [setattr(build_money, k, v) for k, v in saved.items()])


class BuildMoneyTest(unittest.TestCase):
    def setUp(self):
        without_other_units(self)
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.site = root / "site"
        self.out = root / "site_money"
        (self.site / "data/england").mkdir(parents=True)
        (self.site / "data/la/204").mkdir(parents=True)
        (self.site / "index.html").write_text('<html><head><meta property="og:image" content="/og.png"></head></html>', encoding="utf-8")
        (self.site / "data/england/las.json").write_text(json.dumps({"las": [{"la_code": "204", "name": "Hackney", "region": "London"}]}), encoding="utf-8")
        schools = [{"urn": 100000 + i, "name": f"School {i}", "phase": "Primary", "type": "Community school", "town": "London",
                    "postcode": f"E8 {i}AA", "fsm_pct": 20 + i % 10, "constituency": "Hackney North and Stoke Newington" if i < 7 else "Hackney South and Shoreditch"}
                   for i in range(14)]
        schools.append({"urn": 140001, "name": "Converted Academy", "phase": "Primary", "type": "Academy converter", "town": "London", "postcode": "E5 1AA", "trust": "Good Trust"})
        schools.append({"urn": 100099, "name": "Closed School", "status": "Closed", "phase": "Primary"})
        (self.site / "data/la/204/schools.json").write_text(json.dumps({"schools": schools}), encoding="utf-8")
        rows = []
        for i in range(14):
            urn = str(100000 + i)
            reserve = -200_000 if i == 0 else 40_000 * i
            for n, end in enumerate(("2023-03", "2024-03", "2025-03")):
                rows.append(row(urn, end, 2_000_000, 2_050_000 if i == 0 else 1_990_000, reserve + (2 - n) * 50_000 if i == 0 else reserve,
                                lines={"I01": 1_900_000, "E01": 1_000_000}, donations_revenue=12_000, self_generated=100_000))
        # Pre-conversion years under the old URN, then academy years under the new one.
        rows.append(row("100500", "2022-03", 2_000_000, 2_100_000, -50_000))
        rows.append(row("140001", "2024-08", 2_100_000, 2_000_000, 50_000, source="AAR", trust="Good Trust"))
        rows.append(row("140001", "2025-08", 2_100_000, 2_000_000, 150_000, source="AAR", trust="Good Trust", revenue_reserve_incl_trust_share=180_000))
        self.history = root / "history.jsonl"
        self.history.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        self.links = root / "links.csv"
        self.links.write_text('"URN","LinkURN","LinkName","LinkType","LinkEstablishedDate"\n140001,100500,"Old School","Predecessor","01-09-2022"\n'
                              '140001,100777,"Other","Predecessor - merged","01-09-2022"\n', encoding="utf-8")
        self.pta = root / "pta.json"
        self.pta.write_text(json.dumps({"schools": {"100001": [{"charity_number": 1234567, "name": "Friends of School 1", "status": "Registered",
                                                                 "registered": "2010-01-01", "removed": None, "latest_income": 12_000,
                                                                 "history": [{"period_end": "2025-03", "income": 12_000, "expenditure": 11_000}],
                                                                 "match": {"method": "postcode", "evidence": "E8 1AA"}}]}}), encoding="utf-8")
        self.dsg = write_dsg(root / "dsg.json")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, **kw):
        kw.setdefault("out", self.out)
        kw.setdefault("dsg_path", self.dsg)
        return build_money.build(self.site, self.history, self.links, self.pta, **kw)

    def read(self, *parts):
        return (self.out.joinpath(*parts) / "index.html").read_text(encoding="utf-8")

    def test_output_lands_under_out_with_clean_paths(self):
        # Act
        summary = self.build()
        # Assert
        self.assertEqual(summary["with_status"], 15)
        self.assertEqual(summary["out"], str(self.out.resolve()))
        for page in ("index.html", "council/index.html", "council/hackney/index.html", "compare/index.html", "about/index.html",
                     "trust/index.html", "trust/good-trust/index.html", "school/100000-school-0/index.html",
                     "constituency/hackney-north-and-stoke-newington/index.html", "constituency/hackney-south-and-shoreditch/index.html",
                     "areas/index.html", "areas/london/index.html", "map/index.html", "ptfa/index.html", "debts/index.html", "guides/index.html",
                     "search/index.html", "404.html", "robots.txt", "sitemap.xml", "data/search.json", "data/status.json",
                     "data/s/100000.json", "data/a/england.json", "data/a/council-204.json", "data/a/region-london.json",
                     "data/a/constituency-hackney-north-and-stoke-newington.json"):
            self.assertTrue((self.out / page).is_file(), page)
        self.assertFalse((self.out / "money").exists())
        self.assertFalse((self.site / "money").exists())
        self.assertFalse(any("closed" in p.name for p in (self.out / "school").iterdir()))
        html = self.read("school", "100000-school-0")
        self.assertNotIn("/money/", html)
        self.assertIn('href="/council/hackney/"', html)

    def test_every_page_is_balanced_with_a_canonical_on_the_money_host(self):
        self.build()
        pages = list(self.out.rglob("*.html"))
        self.assertGreater(len(pages), 20)
        for page in pages:
            html = page.read_text(encoding="utf-8")
            parsed = Balance(html)
            self.assertEqual(parsed.errors, [], page)
            self.assertTrue(parsed.canonical and parsed.canonical.startswith(BASE_MONEY + "/"), (page, parsed.canonical))
            self.assertIn('href="/assets/app.css"', html)
            self.assertIn('src="/assets/app.js"', html)
            self.assertIn('id="q"', html)
            self.assertIn("data-pin-count", html)
        stub = self.read("search")
        self.assertIn("noindex", stub)
        self.assertNotIn("noindex", self.read("council", "hackney"))

    def test_every_pound_amount_sits_in_a_glossary_money_figure(self):
        self.build()
        checked = 0
        for page in self.out.rglob("*.html"):
            text = body_text(page.read_text(encoding="utf-8"))
            for key in MF_SPAN.findall(text):
                self.assertIn(key, GLOSSARY_KEYS, page)
                checked += 1
            bare = MF_SPAN.sub("", text)
            self.assertNotIn("£", bare, (page, bare[max(bare.find("£") - 120, 0):bare.find("£") + 60]))
        self.assertGreater(checked, 100)

    def test_school_tiles_carry_per_pupil_year_source_and_drill(self):
        self.build()
        html = self.read("school", "100000-school-0")
        tiles = html.split('<div class="tiles">', 1)[1].split("</div></div></div>", 1)[0]
        figures = re.findall(r'<span class="mf"([^>]*)>', tiles)
        self.assertGreaterEqual(len(figures), 4)
        for attrs in figures:
            a = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', attrs))
            self.assertEqual(a["year"], "2024-25", attrs)
            self.assertEqual(int(a["pp"]), round(float(a["v"]) / 300), attrs)
            self.assertEqual(a["src"], "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/100000")
        self.assertIn('data-mf="total_income"', tiles)
        self.assertIn('data-drill="#drill-income"', tiles)
        self.assertIn('data-drill="#drill-spend"', tiles)
        self.assertIn('data-cmp-similar=', tiles)
        drill = json.loads(html.split('<script type="application/json" id="drill-income">', 1)[1].split("</script>", 1)[0])
        self.assertEqual(set(drill), {"title", "year", "rows", "series", "src"})
        self.assertEqual(drill["rows"][0]["key"], "grant_funding")
        self.assertEqual([s["y"] for s in drill["series"]], ["2022-23", "2023-24", "2024-25"])
        self.assertIn("data-pin='{&quot;type&quot;:&quot;school&quot;,&quot;id&quot;:&quot;100000&quot;", html)
        self.assertIn('data-preview="school:', self.read("council", "hackney"))
        self.assertIn("data-pin='{&quot;type&quot;:&quot;area&quot;,&quot;id&quot;:&quot;council-204&quot;", self.read("council", "hackney"))

    def test_deficit_school_is_named_with_reason_and_source_link(self):
        self.build()
        html = self.read("school", "100000-school-0")
        self.assertIn("In deficit", html)
        self.assertIn("£200k", html)
        self.assertIn('data-mf="deficit_total" data-v="200000"', html)
        self.assertIn("financial-benchmarking-and-insights-tool.education.gov.uk/school/100000", html)
        national = self.read()
        self.assertIn("Biggest deficits", national)
        self.assertIn("School 0", national)
        self.assertIn('data-mf="dsg_balance"', national)

    def test_academy_history_follows_plain_predecessor_link_only(self):
        self.build()
        data = json.loads((self.out / "data/s/140001.json").read_text(encoding="utf-8"))
        self.assertEqual([y["y"] for y in data["years"]], ["2021-22", "2023-24", "2024-25"])
        self.assertEqual(data["reserve"], 180_000)
        html = self.read("school", "140001-converted-academy")
        self.assertIn("before it became an academy", html)
        self.assertIn("Good Trust", html)
        self.assertIn('data-mf="revenue_reserve_incl_trust_share"', html)

    def test_school_json_has_the_shared_keys(self):
        self.build()
        data = json.loads((self.out / "data/s/100001.json").read_text(encoding="utf-8"))
        self.assertTrue(SCHOOL_JSON_KEYS <= set(data), SCHOOL_JSON_KEYS - set(data))
        self.assertEqual(data["council"], {"code": "204", "name": "Hackney", "path": "/council/hackney/"})
        self.assertEqual(data["path"], "/school/100001-school-1/")
        self.assertEqual((data["income"], data["income_pp"], data["reserve_pp"]), (2_000_000, 6667, 133))
        self.assertEqual(set(data["years"][0]), {"y", "income", "spend", "balance", "reserve", "pupils", "status"})
        self.assertEqual(data["income_lines"], {"grant_funding": 1_900_000, "self_generated_income": 100_000, "donations_revenue": 12_000})
        self.assertEqual(data["lines"], {"I01": 1_900_000, "E01": 1_000_000})
        self.assertEqual(data["pta"][0]["charity_number"], 1234567)
        self.assertIn("teaching_staff", data["similar"])
        if build_money.areas is None:
            self.assertNotIn("tags", data)  # tags come only from areas.school_profile
        else:
            self.assertIsInstance(data["tags"], dict)
        raw = (self.out / "data/s/100001.json").read_text(encoding="utf-8")
        self.assertIn('"income":2000000,"income_pp":6667', raw)  # compact separators, whole pounds

    def test_area_json_search_index_and_status_paths(self):
        self.build()
        area = json.loads((self.out / "data/a/council-204.json").read_text(encoding="utf-8"))
        self.assertEqual((area["id"], area["type"], area["name"], area["path"]), ("council-204", "council", "Hackney", "/council/hackney/"))
        latest = area["by_year"]["2024-25"]["all"]
        # A deficit total is negative, in areas.py and in the reduced statistics alike.
        self.assertEqual((latest["schools"], latest["in_deficit"], latest["deficit_total"]), (15, 1, -200_000))
        self.assertEqual(round(latest["income_pp_median"]), 6667)
        self.assertEqual(area["dsg"]["2024-25"]["balance"], -16_493_653)
        self.assertEqual(round(area["dsg"]["2024-25"]["per_pupil"]), round(-16_493_653 / 4500))
        england = json.loads((self.out / "data/a/england.json").read_text(encoding="utf-8"))
        self.assertEqual(england["path"], "/")
        search = json.loads((self.out / "data/search.json").read_text(encoding="utf-8"))
        kinds = {e["t"] for e in search}
        self.assertEqual(kinds, {"school", "council", "constituency", "trust"})
        for e in search:
            self.assertEqual(set(e), {"t", "id", "name", "sub", "status", "p"})
            self.assertTrue(e["p"].startswith("/") and e["p"].endswith("/") and "/money/" not in e["p"], e)
        by_id = {(e["t"], e["id"]): e for e in search}
        self.assertEqual(by_id[("school", "100000")]["status"], "in_deficit")
        self.assertEqual(by_id[("council", "204")]["p"], "/council/hackney/")
        self.assertEqual(by_id[("trust", "good-trust")]["p"], "/trust/good-trust/")
        self.assertEqual(by_id[("constituency", "hackney-south-and-shoreditch")]["p"], "/constituency/hackney-south-and-shoreditch/")
        status = json.loads((self.out / "data/status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["100000"], {"status": "in_deficit", "label": "In deficit", "path": "/school/100000-school-0/"})
        self.assertFalse((self.out / "data/index.json").exists())

    def test_council_page_shows_dsg_with_that_years_pupils_and_flags(self):
        self.build()
        html = self.read("council", "hackney")
        self.assertIn('id="dsg"', html)
        self.assertIn('data-mf="dsg_balance" data-v="-16493653" data-pp="-3665" data-year="2024-25"', html)
        self.assertIn("safety valve", html)
        self.assertIn("-£16.5m", html)
        # Without a DSG file the section is simply absent.
        self.build(dsg_path=Path(self.tmp.name) / "no-such-dsg.json")
        self.assertNotIn('id="dsg"', self.read("council", "hackney"))

    def test_constituency_stub_lists_schools_with_badges(self):
        self.build()
        html = self.read("constituency", "hackney-north-and-stoke-newington")
        self.assertEqual(html.count('data-preview="school:'), 7)
        self.assertIn("In deficit", html)
        self.assertIn('href="/school/100000-school-0/"', html)
        self.assertIn("constituency-hackney-north-and-stoke-newington", html)
        self.assertIn('href="/constituency/hackney-north-and-stoke-newington/"', self.read("school", "100000-school-0"))

    def test_sitemap_robots_and_404(self):
        summary = self.build()
        index = ET.parse(self.out / "sitemap.xml").getroot()
        maps = [n.text for n in index.findall("{*}sitemap/{*}loc")]
        self.assertEqual(maps, [BASE_MONEY + "/sitemaps/pages-1.xml"])
        locs = [n.text for n in ET.parse(self.out / "sitemaps/pages-1.xml").getroot().findall("{*}url/{*}loc")]
        self.assertEqual(len(locs), summary["pages"])
        self.assertIn(BASE_MONEY + "/", locs)
        self.assertIn(BASE_MONEY + "/council/hackney/", locs)
        self.assertIn(BASE_MONEY + "/school/100000-school-0/", locs)
        self.assertNotIn(BASE_MONEY + "/search/", locs)
        for loc in locs:
            self.assertTrue(loc.startswith(BASE_MONEY + "/"), loc)
            self.assertTrue((self.out / loc.removeprefix(BASE_MONEY + "/") / "index.html").is_file(), loc)
        robots = (self.out / "robots.txt").read_text(encoding="utf-8")
        self.assertIn(f"Sitemap: {BASE_MONEY}/sitemap.xml", robots)
        missing = (self.out / "404.html").read_text(encoding="utf-8")
        self.assertIn("Page not found", missing)
        self.assertIn("noindex", missing)

    def test_about_has_sources_licences_deflator_and_ifs(self):
        self.build()
        html = self.read("about")
        for anchor in ('id="sources"', 'id="licences"', 'id="method"', 'id="real-terms"'):
            self.assertIn(anchor, html)
        self.assertIn("GDP deflator", html)
        self.assertIn("Open Government Licence", html)
        self.assertIn("Annual report on education spending in England", html)

    def test_fallback_shell_is_used_when_site_module_is_missing(self):
        # Arrange
        saved = build_money.shell
        build_money.shell = None
        try:
            # Act
            self.build()
        finally:
            build_money.shell = saved
        # Assert: the fallback document still meets the contract.
        html = self.read("school", "100001-school-1")
        for needle in ("<!doctype html>", f'<link rel="canonical" href="{BASE_MONEY}/school/100001-school-1/">', 'property="og:title"',
                       'id="q"', "Find a school", "Compare", "/assets/app.css", "/assets/app.js", "<main", "<footer", 'data-mf="total_income"'):
            self.assertIn(needle, html)
        self.assertEqual(Balance(html).errors, [])
        self.assertTrue((self.out / "assets").is_dir())

    def test_lazy_modules_are_optional_and_used_when_present(self):
        saved = (build_money.areas, build_money.timeline, build_money.deflator)
        try:
            # Arrange / Act 1: none of the optional modules.
            build_money.areas = build_money.timeline = build_money.deflator = None
            self.build()
            data = json.loads((self.out / "data/s/100001.json").read_text(encoding="utf-8"))
            html = self.read("school", "100001-school-1")
            # Assert 1
            for key in ("tags", "band", "area", "timeline"):
                self.assertNotIn(key, data)
            self.assertNotIn("2025-26 prices", html)
            self.assertNotIn('data-mf="real_terms"', html)
            # Arrange / Act 2: stand-ins with the SHARED signatures.
            build_money.areas = types.SimpleNamespace(
                school_profile=lambda s, code, root: {"tags": {"governance": "council-run", "trust": None, "trust_size": None, "admissions": "non-selective",
                                                               "faith": None, "phase": "Primary", "gender": "Mixed", "sixth_form": False},
                                                      "intake": {"fsm_pct": 21.0, "fsm_pct_council": 30.0, "fsm_pct_england": 25.0},
                                                      "area": {"lsoa": "E01000001", "imd_decile": 3}, "band": 4},
                build_areas=lambda rows, schools, pta, dsg, root: {"england": {"name": "England", "by_year": {"2024-25": {"all": {"schools": len(schools)}}}, "dsg": {}, "statuses_latest": {}},
                                                                    "regions": {}, "councils": {"204": {"name": "Hackney", "by_year": {}, "dsg": {"2024-25": {"balance": -1, "per_pupil": None}}}},
                                                                    "constituencies": {"E14000001": {"name": "Hackney South and Shoreditch", "by_year": {"x": 1}}}})
            build_money.timeline = types.SimpleNamespace(status_by_year=lambda rows: [{"year": "2024-25", "status": "tight", "label": "Tight", "reserve": 40_000, "reserve_pp": 133, "pupils": 300}])
            build_money.deflator = types.SimpleNamespace(to_real=lambda v, y, src: v * 1.1, real_label=lambda: "in 2025-26 prices (test deflator)")
            self.build()
            data = json.loads((self.out / "data/s/100001.json").read_text(encoding="utf-8"))
            html = self.read("school", "100001-school-1")
            # Assert 2
            self.assertEqual(data["band"], 4)
            self.assertEqual(data["tags"]["governance"], "council-run")
            self.assertEqual(data["years"][-1]["status"], "tight")
            self.assertEqual(data["timeline"][0]["year"], "2024-25")
            self.assertIn("Intake band", html)
            self.assertIn("non-selective", html)
            self.assertIn("Status by year", html)
            self.assertIn('data-mf="real_terms" data-v="44000"', html)
            self.assertIn("in 2025-26 prices (test deflator)", html)
            england = json.loads((self.out / "data/a/england.json").read_text(encoding="utf-8"))
            self.assertEqual(england["by_year"]["2024-25"]["all"]["schools"], 15)
            council = json.loads((self.out / "data/a/council-204.json").read_text(encoding="utf-8"))
            self.assertEqual(council["dsg"]["2024-25"]["balance"], -1)
            constituency = json.loads((self.out / "data/a/constituency-hackney-south-and-shoreditch.json").read_text(encoding="utf-8"))
            self.assertEqual(constituency["by_year"], {"x": 1})
            self.assertEqual(constituency["path"], "/constituency/hackney-south-and-shoreditch/")
        finally:
            build_money.areas, build_money.timeline, build_money.deflator = saved


class HardeningTest(unittest.TestCase):
    def setUp(self):
        without_other_units(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, councils, schools, rows, pta=None):
        site, history, links, pta_path = make_site(self.root, councils, schools, rows, pta)
        summary = build_money.build(site, history, links, pta_path, out=self.root / "site_money", dsg_path=self.root / "no-dsg.json")
        return self.root / "site_money", summary

    def read(self, money, *parts):
        return (money.joinpath(*parts) / "index.html").read_text(encoding="utf-8")

    def test_trust_names_with_the_same_slug_get_distinct_pages(self):
        # Arrange: three trusts whose names slugify alike, and one whose slug is empty.
        names = ["Harris Federation", "Harris Federation.", "Hárris Féderation", "???"]
        schools = [school(140000 + i, f"Academy {i}", type="Academy converter", trust=t) for i, t in enumerate(names)]
        rows = [r for i, t in enumerate(names) for r in full_rows(str(140000 + i), source="AAR", trust=t, years=("2024-08", "2025-08"))]
        # Act
        money, summary = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert
        self.assertEqual(summary["trusts"], 4)
        index = self.read(money, "trust")
        pages = sorted(p.name for p in (money / "trust").iterdir() if p.is_dir())
        self.assertEqual(len(pages), 4, pages)
        self.assertNotIn("school", pages)
        for p in pages:
            self.assertIn(f'href="/trust/{p}/"', index)
            html = self.read(money, "trust", p)
            self.assertIn("academy finances", html)
        for i in range(4):
            html = self.read(money, "school", f"14000{i}-academy-{i}")
            link = [p for p in pages if f'href="/trust/{p}/"' in html]
            self.assertEqual(len(link), 1, (i, link))
        # Stable across builds: same names give the same paths.
        money2, _ = self.build([("204", "Hackney")], {"204": schools}, rows)
        self.assertEqual(pages, sorted(p.name for p in (money2 / "trust").iterdir() if p.is_dir()))

    def test_duplicate_council_path_raises(self):
        schools = {"204": [school(100001, "A", 204)], "205": [school(100002, "B", 205)]}
        rows = full_rows("100001") + full_rows("100002", la=205)
        with self.assertRaises(ValueError):
            self.build([("204", "Hackney"), ("205", "Hackney")], schools, rows)

    def test_duplicate_school_path_raises(self):
        schools = {"204": [school(100001, "A", 204)], "205": [school(100001, "A", 205)]}
        with self.assertRaises(ValueError):
            self.build([("204", "Hackney"), ("205", "Islington")], schools, full_rows("100001"))

    def test_zero_and_missing_figures_do_not_crash(self):
        # Arrange: 14 healthy peers so compare medians run, plus schools with pupils 0/None,
        # income 0/None and missing breakdown keys in their latest year.
        schools, rows = [], []
        for i in range(14):
            schools.append(school(100000 + i, f"Peer {i}", fsm_pct=20 + i))
            rows += full_rows(str(100000 + i), reserve=50_000 + 10_000 * i)
        odd = {"100100": {"pupils": 0}, "100101": {"pupils": None}, "100102": {"total_income": 0},
               "100103": {"total_income": None}, "100104": {"teaching_staff": None, "education_support_staff": None, "premises": None, "energy": None}}
        for urn, extra in odd.items():
            schools.append(school(int(urn), f"Odd {urn}"))
            rows += full_rows(urn)[:2] + [row(urn, "2025-03", 2_000_000, 1_990_000, 100_000, **extra)]
        # Every breakdown key absent entirely.
        schools.append(school(100105, "Bare"))
        for end in ("2024-03", "2025-03"):
            rows.append({"urn": "100105", "year": "2024-25", "period_end": end, "source": "CFR", "la": 204, "laestab": "2040105",
                         "phase": "primary", "period_months": 12, "pupils": 200, "total_income": 1_000_000, "total_expenditure": 990_000,
                         "in_year_balance": 10_000, "revenue_reserve": 60_000})
        # Act
        money, summary = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert
        self.assertEqual(summary["schools"], 20)
        for urn in list(odd) + ["100105"]:
            page = next(p for p in (money / "school").iterdir() if p.name.startswith(urn))
            html = (page / "index.html").read_text(encoding="utf-8")
            self.assertIn("school finances", html)
            self.assertNotIn("ZeroDivision", html)
            data_path = money / "data/s" / f"{urn}.json"
            if data_path.exists():
                data = json.loads(data_path.read_text(encoding="utf-8"))
                self.assertNotIn("teaching_staff", data["pp"]) if urn in ("100100", "100101", "100104", "100105") else None
        self.assertIn("Peer 0", self.read(money, "council", "hackney"))

    def test_similar_schools_without_figures_are_skipped(self):
        # Arrange: 20 peers; in their latest year peers 10-13 have no reserve, 14-15 no pupils, 16-17 no breakdown.
        schools, rows = [], []
        for i in range(20):
            schools.append(school(100000 + i, f"Peer {i}", fsm_pct=20 + i))
            extra = {"revenue_reserve": None} if 10 <= i < 14 else {"pupils": None} if 14 <= i < 16 else {"teaching_staff": None} if 16 <= i < 18 else {}
            rows += full_rows(str(100000 + i), reserve=50_000 + 10_000 * i)[:2]
            rows.append(row(str(100000 + i), "2025-03", 2_000_000, 1_990_000, 50_000 + 10_000 * i, **extra))
        # Act
        money, _ = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert
        html = self.read(money, "school", "100005-peer-5")
        self.assertIn("Compared with similar schools", html)
        self.assertEqual(json.loads((money / "data/s/100005.json").read_text(encoding="utf-8"))["urn"], "100005")

    def test_council_and_country_with_no_assessed_schools(self):
        # Arrange: one part-year school and one federation member, nothing else.
        schools = [school(100001, "Opened Late"), school(100002, "Member")]
        rows = [row("100001", "2025-03", 900_000, 850_000, 50_000, period_months=7),
                {"urn": "100002", "year": "2024-25", "period_end": "2025-03", "source": "CFR", "la": 204, "laestab": "2040002",
                 "phase": "primary", "period_months": 12, "pupils": None, "total_income": None, "total_expenditure": None,
                 "in_year_balance": None, "revenue_reserve": None, "did_not_supply": True, "lead_laestab": "2049999"}]
        # Act
        money, summary = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert
        self.assertEqual(summary["with_status"], 0)
        self.assertTrue((money / "index.html").is_file())
        self.assertTrue((money / "council/hackney/index.html").is_file())
        self.assertIn("Hackney", self.read(money, "council", "hackney"))
        self.assertEqual(json.loads((money / "data/status.json").read_text(encoding="utf-8")), {})
        self.assertEqual(json.loads((money / "data/search.json").read_text(encoding="utf-8"))[0]["status"], None)
        late = self.read(money, "school", "100001-opened-late")
        self.assertIn("No full-year finance return", late)
        member = self.read(money, "school", "100002-member")
        self.assertIn("part of a federation", member)
        self.assertIn("the lead school", member)
        self.assertNotIn('href=""', member)
        self.assertNotIn("None", member.split("<main")[1].split("<footer")[0])

    def test_part_year_rows_after_full_years_keep_the_status(self):
        schools = [school(100001, "Changed Trust")]
        rows = full_rows("100001")[:2] + [row("100001", "2025-03", 900_000, 850_000, 50_000, period_months=7)]
        money, summary = self.build([("204", "Hackney")], {"204": schools}, rows)
        self.assertEqual(summary["with_status"], 1)
        self.assertIn("2023-24", self.read(money, "school", "100001-changed-trust"))

    def test_names_are_escaped_everywhere(self):
        # Arrange
        bad = "<script>alert('x')</script> & \"Co\" <b>"
        name = f"St Mary's {bad}"
        trust = f"Trust {bad}"
        council = f"Hackney {bad}"
        charity = f"Friends of {bad}"
        constituency = f"Seat {bad}"
        schools = [school(100001, name, constituency=constituency), school(140001, f"Academy {bad}", type="Academy converter", trust=trust)]
        rows = full_rows("100001") + full_rows("140001", source="AAR", trust=trust, years=("2024-08", "2025-08"))
        pta = {"100001": [{"charity_number": 1234567, "name": charity, "status": "Registered", "registered": "2010-01-01", "removed": None,
                           "latest_income": 12_000, "history": [{"period_end": "2025-03", "income": 12_000, "expenditure": 11_000}],
                           "match": {"method": "postcode", "evidence": "E8 1AA"}}]}
        # Act
        money, _ = self.build([("204", council)], {"204": schools}, rows, pta)
        # Assert
        pages = list(money.rglob("*.html"))
        self.assertGreater(len(pages), 4)
        for page in pages:
            html = page.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert", html, page)
            self.assertNotRegex(html, r"<b>(?!£)", page)
            self.assertNotIn('"Co"', html, page)
            for block in html.split('<script type="application/ld+json">')[1:]:
                ld = block.split("</script>")[0]
                self.assertNotIn("</script", ld)
                self.assertNotIn("<", ld)
                json.loads(ld)
            for block in html.split('<script type="application/json"')[1:]:
                inline = block.split(">", 1)[1].split("</script>")[0]
                self.assertNotIn("<", inline)
                json.loads(inline)
        for xml in [money / "sitemap.xml"] + list((money / "sitemaps").iterdir()):
            self.assertNotIn("<script", xml.read_text(encoding="utf-8"))
        search = json.loads((money / "data/search.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(e["name"] for e in search if e["t"] == "school"), sorted([name, f"Academy {bad}"]))
        self.assertEqual(next(e for e in search if e["t"] == "council")["name"], council)
        data = json.loads((money / "data/s/100001.json").read_text(encoding="utf-8"))
        self.assertEqual(data["name"], name)
        self.assertEqual(data["council"]["name"], council)
        status = json.loads((money / "data/status.json").read_text(encoding="utf-8"))
        self.assertIn("100001", status)
        school_html = (money / "school" / next(p.name for p in (money / "school").iterdir() if p.name.startswith("100001")) / "index.html").read_text(encoding="utf-8")
        self.assertIn("Friends of &lt;script&gt;", school_html)
        self.assertIn("St Mary&#x27;s &lt;script&gt;", school_html)
        self.assertIn("&quot;type&quot;:&quot;school&quot;", school_html)

    def test_big_school_page_stays_under_budget(self):
        # Arrange: 8 years, 30+ similar schools, 3 charities with long histories, long names.
        long = "The Very Long Name of a Church of England Voluntary Aided Primary School and Nursery Federation " * 2
        years = tuple(f"{y}-03" for y in range(2018, 2026))
        schools, rows = [school(100000, long.strip())], full_rows("100000", years=years)
        for i in range(1, 40):
            schools.append(school(100000 + i, f"{long.strip()} {i}", fsm_pct=20 + i % 10))
            rows += full_rows(str(100000 + i), reserve=50_000 + 1_000 * i, years=years)
        hist = [{"period_end": f"{y}-03", "income": 10_000 + y, "expenditure": 9_000 + y} for y in range(2005, 2026)]
        pta = {"100000": [{"charity_number": 1000000 + n, "name": f"Friends of {long.strip()} {n}", "status": "Registered", "registered": f"20{n:02d}-01-01",
                           "removed": None, "latest_income": 20_000, "history": hist, "match": {"method": "postcode", "evidence": "E8 1AA"}} for n in range(3)]}
        # Act
        money, _ = self.build([("204", "Hackney")], {"204": schools}, rows, pta)
        # Assert
        page = next(p for p in (money / "school").iterdir() if p.name.startswith("100000-"))
        size = len((page / "index.html").read_bytes())
        # School pages have their own budget; the body bound for a dashboard this size is 56,000 bytes.
        self.assertLess(size, build_money.SCHOOL_PAGE_BUDGET - 8_000, size)
        self.assertIn("Money raised by parents", (page / "index.html").read_text(encoding="utf-8"))

    def test_every_page_stays_under_budget_with_a_big_council_and_trust(self):
        # Arrange: one council and one trust with 90 academies, more than one page of table rows.
        schools = [school(100000 + n, f"Primary Academy {n}", type="Academy converter", trust="Example Trust") for n in range(90)]
        rows = [r for n in range(90) for r in full_rows(str(100000 + n), source="AAR", years=("2024-08", "2025-08"))]
        # Act
        money, summary = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert: every page is under budget, the table continues on numbered pages, and every school is listed once.
        oversized = {str(p.relative_to(money)): p.stat().st_size for p in money.rglob("*.html") if p.stat().st_size >= build_money.PAGE_BUDGET - 4_000}
        self.assertEqual(oversized, {})
        council = self.read(money, "council", "hackney")
        self.assertIn('href="/council/hackney/2/"', council)
        self.assertIn("Page 1 of", council)
        numbered = sorted(p.name for p in (money / "council/hackney").iterdir() if p.is_dir())
        listed = sum(self.read(money, "council", "hackney", *rest).count("Primary Academy") for rest in [[]] + [[n] for n in numbered])
        self.assertEqual(listed, 90)
        self.assertIn("Back to the summary", self.read(money, "trust", "example-trust", "2"))
        sitemap = (money / "sitemaps/pages-1.xml").read_text(encoding="utf-8")
        self.assertIn("/council/hackney/2/", sitemap)
        self.assertIn("/council/</loc>", sitemap)
        self.assertEqual(summary["pages"], sitemap.count("<loc>"))

    def test_reported_year_matches_the_assessed_figures(self):
        for missing in ({"total_income": 0}, {"revenue_reserve": None}):
            with self.subTest(missing=missing):
                # Arrange: the newest return cannot be assessed, an older one can.
                rows = [row("100001", "2024-03", 2_000_000, 1_990_000, 100_000),
                        row("100001", "2025-03", 2_000_000, 1_990_000, -50_000, **missing)]
                # Act
                money, _ = self.build([("204", "Hackney")], {"204": [school(100001, "Mixed Years")]}, rows)
                # Assert: the JSON and page report the assessed year and its own reserve, and say a newer return exists.
                data = json.loads((money / "data/s/100001.json").read_text(encoding="utf-8"))
                self.assertEqual((data["year"], data["reserve"], data["share"]), ("2023-24", 100_000, 0.05))
                html = self.read(money, "school", "100001-mixed-years")
                self.assertIn("Latest full year 2023-24", html)
                self.assertIn("A 2024-25 return is published too", html)

    def test_urn_that_is_not_a_number_is_rejected_before_any_write(self):
        # Arrange: a URN that would climb out of the output directory.
        urn = "../../../../sentinel"
        site, history, links, pta_path = make_site(self.root, [("204", "Hackney")], {"204": [school(urn, "Escape")]}, full_rows(urn))
        sentinel = site / "sentinel.json"
        sentinel.write_text("untouched", encoding="utf-8")
        # Act / Assert
        with self.assertRaises(ValueError):
            build_money.build(site, history, links, pta_path, out=self.root / "site_money")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "untouched")
        self.assertFalse((self.root / "sentinel-escape").exists())
        self.assertFalse((self.root / "site_money").exists())
        self.assertEqual([p for p in self.root.iterdir() if p.name.startswith(".site_money-build")], [])

    def test_six_thousand_schools_build_in_under_a_minute(self):
        # Arrange: 20 councils, 300 schools each, 5 years each, a few trusts, 40 constituencies and one PTA in ten.
        councils, schools, rows, pta = [], {}, [], {}
        for c in range(20):
            code = str(300 + c)
            councils.append((code, f"Council {c}"))
            schools[code] = []
            for n in range(300):
                urn = 100000 + c * 300 + n
                academy = n % 3 == 0
                extra = {"type": "Academy converter", "trust": f"Trust {n % 40}"} if academy else {}
                schools[code].append(school(urn, f"School {urn}", la=int(code), fsm_pct=n % 60, phase="Secondary" if n % 5 == 0 else "Primary",
                                            constituency=f"Seat {c * 2 + n % 2}", **extra))
                reserve = (n % 7 - 2) * 40_000
                for k, end in enumerate(("2021", "2022", "2023", "2024", "2025")):
                    src = "AAR" if academy else "CFR"
                    end = f"{end}-08" if academy else f"{end}-03"
                    r = row(str(urn), end, 2_000_000 + n * 1000, 2_000_000 + (n % 4) * 20_000, reserve + (4 - k) * 10_000,
                            source=src, pupils=150 + n * 3, la=int(code), phase="secondary" if n % 5 == 0 else "primary", **({"trust": extra["trust"]} if academy else {}))
                    rows.append(r)
                if n % 10 == 0:
                    pta[str(urn)] = [{"charity_number": 1100000 + urn, "name": f"Friends of School {urn}", "status": "Registered", "registered": "2010-01-01",
                                      "removed": None, "latest_income": 5_000, "history": [{"period_end": "2025-03", "income": 5_000, "expenditure": 4_000}],
                                      "match": {"method": "postcode", "evidence": "E8 1AA"}}]
        # Act
        started = time.perf_counter()
        money, summary = self.build(councils, schools, rows, pta)
        elapsed = time.perf_counter() - started
        # Assert
        self.assertEqual(summary["schools"], 6000)
        self.assertEqual(summary["constituencies"], 40)
        self.assertEqual(sum(1 for p in (money / "school").iterdir()), 6000)
        self.assertEqual(sum(1 for p in (money / "data/s").iterdir()), 6000)
        self.assertEqual(sum(1 for p in (money / "data/a").iterdir()), 1 + 1 + 20 + 40)
        self.assertEqual(summary["councils"], 20)
        self.assertLess(elapsed, 60, f"build took {elapsed:.1f}s")


CTX_KEYS = {"series", "profile", "timeline", "similar", "similar_series", "council", "england", "pta_national", "ifs", "real_label",
            "check_url", "sir_url"}
SERIES_KEYS = {"years", "source", "pupils", "m", "gap", "pta", "flags", "trust_central_pp"}


def area(name, **extra):
    """An area A as areas.build_areas returns it (SHARED 'AREAS.JSON')."""
    a = {"name": name, "pupils_by_year": {"2024-25": 4200.0}, "schools_by_year": {"2024-25": 14}, "by_year": {}, "dsg": {},
         "statuses_latest": {"healthy": 10, "in_deficit": 2, "tight": 2}}
    a.update(extra)
    return a


def fake_areas(trust="Good Trust", constituency="Hackney North and Stoke Newington"):
    """A stand-in areas module with the SHARED signatures and a document carrying trusts and pta."""
    doc = {"england": area("England"), "regions": {"London": area("London")}, "councils": {"204": area("Hackney")},
           "constituencies": {"E14000720": area(constituency)},
           "trusts": {"good-trust": area(trust, company_number="01234567", central_pp={"2024-25": 510})},
           "pta": {"by_year": {}, "by_band": {}, "by_tag": {}, "top": []}}
    return types.SimpleNamespace(
        school_profile=lambda s, code, root: {"tags": {"governance": "council-run", "phase": "Primary"}, "intake": {}, "area": {}, "band": None},
        build_areas=lambda rows, schools, pta, dsg, root: doc), doc


class FakeAreaPages:
    """area_pages with the SHARED signatures: every renderer records its call and returns the SHARED
    result shape. Table cells are padded so a fixture council needs several pages."""

    def __init__(self, intro_bytes=6_000, pad=2_300):
        self.calls, self.intro_bytes, self.pad = [], intro_bytes, pad

    def result(self, kind, name, rows, headers=("School", "Status")):
        intro = f'<h1>{build_money.esc(name)} money</h1><p class="lead">INTRO-{kind}</p><p>{"i" * self.intro_bytes}</p>'
        return {"title": f"{name} school money | School Money", "description": f"{name}: school finances.", "intro": intro,
                "table": {"headers": list(headers), "rows": rows, "caption": f"Every row for {name}",
                          "filters": '<div class="table-filters" data-filters><button type="button" data-filter="phase:primary" aria-pressed="false">Primary</button></div>'},
                "outro": f"<p>OUTRO-{kind}</p>", "indexable": True}

    def school_rows(self, items):
        return [[f'<span data-tags="phase:primary"></span><a href="{i["path"]}" data-preview="school:{i["urn"]}">{build_money.esc(i["name"])}</a>',
                 "p" * self.pad] for i in items]

    def render_area(self, kind, area_id, a, items, ctx):
        self.calls.append(("area", kind, area_id, ctx))
        rows = self.school_rows(items) if kind in ("council", "constituency") else [[f'<a href="{p}">{c}</a>', "-"] for c, p in ctx["paths"]["council"].items()]
        return self.result(kind, a["name"], rows)

    def render_council_league(self, council_areas, ctx):
        self.calls.append(("league", council_areas))
        return self.result("league", "Councils", [[f'<a href="{a["path"]}">{a["name"]}</a>', a["code"]] for a in council_areas.values()])

    def render_trust(self, trust_area, items, ctx):
        self.calls.append(("trust", trust_area))
        return self.result("trust", trust_area["name"], self.school_rows(items))

    def render_trust_index(self, trust_areas, ctx):
        self.calls.append(("trusts", trust_areas))
        return self.result("trusts", "Academy trusts", [[f'<a href="{a["path"]}">{a["name"]}</a>', "-"] for a in trust_areas.values()])

    def render_debts(self, areas_doc, ctx):
        self.calls.append(("debts",))
        return dict(self.result("debts", "Debts", []), table=None)

    def render_ptfa(self, areas_doc, items, ctx):
        self.calls.append(("ptfa", len(items)))
        return self.result("ptfa", "PTFA", self.school_rows([i for i in items if i["status"]]))

    @staticmethod
    def headline(a):
        return f'<div class="tiles" data-headline="{build_money.esc(a["name"])}">HEADLINE</div>'


class FakeSchoolPage:
    """school_page with the SHARED signature; records each ctx and returns a body of `body_bytes`."""
    EXTRA_HEAD = build_money.SCHOOL_HEAD

    def __init__(self, body_bytes=2_000, indexable=True):
        self.ctxs, self.body_bytes, self.indexable = {}, body_bytes, indexable

    def render(self, item, ctx):
        self.ctxs[item["urn"]] = ctx
        body = f'<h1>{build_money.esc(item["name"])}: money</h1><p>{"b" * self.body_bytes}</p>'
        return {"title": f"{item['name']} | School Money", "description": "A school's money.", "body": body, "indexable": self.indexable}


def fake_series():
    """series with the SHARED signatures, backed by the builder's own contract-following fallback."""
    return types.SimpleNamespace(school_series=build_money.local_series, METRICS=build_money.METRICS, pta_year=build_money.local_pta_year,
                                 sen_share=lambda r: (r or {}).get("sen_funding", 0) / r["total_income"] if r and r.get("total_income") else None,
                                 sparkline_values=lambda sx, metric, basis="pp": [])


class WaveBTest(unittest.TestCase):
    def setUp(self):
        without_other_units(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def patch(self, **modules):
        for name, value in modules.items():
            saved = getattr(build_money, name)
            setattr(build_money, name, value)
            self.addCleanup(setattr, build_money, name, saved)

    def build(self, councils, schools, rows, pta=None, **kw):
        site, history, links, pta_path = make_site(self.root, councils, schools, rows, pta)
        out = kw.pop("out", self.root / "site_money")
        summary = build_money.build(site, history, links, pta_path, out=out, dsg_path=self.root / "no-dsg.json")
        return out, summary

    def read(self, money, *parts):
        return (money.joinpath(*parts) / "index.html").read_text(encoding="utf-8")

    def sitemap(self, money):
        return (money / "sitemaps/pages-1.xml").read_text(encoding="utf-8")

    def peers(self, n=14, **extra):
        schools = [school(100000 + i, f"Peer {i}", fsm_pct=20 + i % 5, constituency="Hackney North and Stoke Newington") for i in range(n)]
        rows = [r for i in range(n) for r in full_rows(str(100000 + i), reserve=40_000 + 5_000 * i, **extra)]
        return schools, rows

    # ------------------------------------------------------------ every school gets a page

    def test_every_open_school_gets_a_page_but_colleges_and_universities_do_not(self):
        # Arrange: a school with returns, an independent school, a new school with no return, and three colleges.
        schools = [school(100001, "With Returns"),
                   school(100002, "Independent Prep", type="Other independent school", type_group="Independent schools", lat=51.5, lon=-0.05),
                   school(100003, "New Free School", type="Free schools", type_group="Free Schools"),
                   school(100004, "City College", type="Further education", type_group="Colleges"),
                   school(100005, "University", type="Higher education institutions", type_group="Universities"),
                   school(100006, "Sixth Form Centre", type="Sixth form centres", type_group="Colleges")]
        # Act
        money, summary = self.build([("204", "Hackney")], {"204": schools}, full_rows("100001"))
        # Assert
        self.assertEqual(summary["schools"], 3)
        pages = sorted(p.name for p in (money / "school").iterdir())
        self.assertEqual(pages, ["100001-with-returns", "100002-independent-prep", "100003-new-free-school"])
        independent = self.read(money, "school", "100002-independent-prep")
        self.assertIn("Independent schools don&#x27;t publish accounts to the DfE", independent)
        self.assertIn('content="noindex,follow"', independent)
        fresh = self.read(money, "school", "100003-new-free-school")
        self.assertIn("No full-year finance return", fresh)
        self.assertIn('content="noindex,follow"', fresh)
        sitemap = self.sitemap(money)
        self.assertIn("/school/100001-with-returns/", sitemap)
        self.assertNotIn("/school/100002-", sitemap)
        self.assertNotIn("/school/100003-", sitemap)
        self.assertEqual(sorted(p.name for p in (money / "data/s").iterdir()), ["100001.json"])
        search = {e["id"] for e in json.loads((money / "data/search.json").read_text(encoding="utf-8")) if e["t"] == "school"}
        self.assertEqual(search, {"100001", "100002", "100003"})
        self.assertIn("or independent schools, which don", self.read(money, "council", "hackney"))

    def test_model_items_keep_their_keys_and_gain_the_wave_b_ones(self):
        # Arrange
        schools = [school(100001, "Has Coordinates", lat=51.55, lon=-0.06), school(100002, "Nothing Yet")]
        site, history, links, pta_path = make_site(self.root, [("204", "Hackney")], {"204": schools}, full_rows("100001", pupils=312.5))
        expected = {"urn", "name", "school", "council", "path", "site_path", "rows", "years", "latest", "member_of", "status", "phase", "london",
                    "fsm", "pta", "trust", "trust_path", "academy", "constituency", "constituency_path", "similar",
                    "la", "la_name", "tags", "pupils", "lat", "lon"}
        for areas_module, tags in ((None, {}), (fake_areas()[0], {"governance": "council-run", "phase": "Primary"})):
            with self.subTest(areas=bool(areas_module)):
                self.patch(areas=areas_module)
                # Act
                _, items, _ = build_money.build_model(site, history, links, pta_path)
                # Assert
                first, second = items
                self.assertTrue(expected <= set(first), expected - set(first))
                self.assertEqual((first["la"], first["la_name"], first["pupils"], first["lat"], first["lon"]), ("204", "Hackney", 312.5, 51.55, -0.06))
                self.assertEqual(first["tags"], tags)
                self.assertEqual((second["rows"], second["status"], second["pupils"], second["lat"]), ([], None, None, None))

    # ------------------------------------------------------------ SERIES files

    def test_series_files_are_compact_bounded_and_keep_the_core_lines(self):
        # Arrange: 8 years with every line, 3 charities with 21-year histories, long names.
        years = tuple(f"{y}-03" for y in range(2018, 2026))
        detail = {k: 123_456.789 for k, _, _ in build_money.METRICS if k not in ("total_income", "total_expenditure", "revenue_reserve", "in_year_balance")}
        schools, rows = self.peers()
        schools.append(school(100099, "Big History " * 6))
        rows += [row("100099", end, 2_345_678, 2_300_000, 123_456, pupils=412.5, **detail) for end in years]
        hist = [{"period_end": f"{y}-08", "income": 21_000 + y, "expenditure": 20_000 + y} for y in range(2005, 2026)]
        pta = {"100099": [{"charity_number": 1100000 + n, "name": f"Friends {n}", "history": hist, "match": {"confidence": "high"}} for n in range(3)]}
        # Act
        money, _ = self.build([("204", "Hackney")], {"204": schools}, rows, pta)
        # Assert
        files = sorted((money / "data/sx").iterdir())
        self.assertEqual(len(files), 15)
        for f in files:
            self.assertLessEqual(f.stat().st_size, build_money.SX_BUDGET, f.name)
        raw = (money / "data/sx/100099.json").read_text(encoding="utf-8")
        doc = json.loads(raw)
        self.assertNotIn(": ", raw)
        self.assertEqual(set(doc), SERIES_KEYS)
        self.assertEqual(len(doc["years"]), 8)
        self.assertTrue(build_money.SX_CORE <= set(doc["m"]), build_money.SX_CORE - set(doc["m"]))
        self.assertEqual(doc["m"]["total_income"]["2024-25"]["pp"], round(2_345_678 / 412.5))
        self.assertEqual(doc["pupils"]["2024-25"], 412.5)

    def test_series_json_drops_detail_lines_before_the_core_ones(self):
        # Arrange
        cell = {f"20{y}-{y + 1}": {"v": 1_234_567, "pp": 4_115, "r": 1_334_567, "rpp": 4_448} for y in range(10, 25)}
        doc = {"years": [], "source": {}, "pupils": {}, "m": {k: dict(cell) for k, _, _ in build_money.METRICS}, "gap": {}, "pta": {},
               "flags": {}, "trust_central_pp": {}}
        doc["m"]["catering_income"] = {}
        # Act
        text = build_money.series_json(doc)
        kept = json.loads(text)["m"]
        light = json.loads(build_money.series_json(doc, limit=len(build_money.series_json(doc, limit=10**6)) - 1))["m"]
        # Assert
        self.assertLessEqual(len(text.encode("utf-8")), build_money.SX_BUDGET)
        self.assertNotIn("catering_income", kept)
        self.assertTrue(build_money.SX_CORE <= set(kept))
        self.assertNotIn("bought_in_services", kept, "whole detail lines go, from the end of METRICS")
        self.assertIn("teaching_staff", kept)
        self.assertEqual(set(kept["total_income"]["2024-25"]), {"v", "pp", "rpp"}, "real totals go before any line")
        self.assertEqual(set(kept["teaching_staff"]["2024-25"]), {"v", "pp", "rpp"})
        self.assertEqual(set(light), {k for k, _, _ in build_money.METRICS} - {"catering_income"}, "a small overshoot drops no line")
        self.assertIn("r", light["total_income"]["2024-25"], "core lines lose 'r' only after the detail lines")
        self.assertEqual(doc["m"]["teaching_staff"]["2024-25"]["r"], 1_334_567, "the caller's dict is untouched")
        with self.assertRaises(ValueError):
            build_money.series_json(doc, limit=500)

    def test_local_series_follows_the_shared_contract(self):
        # Arrange: two CFR years, then an academy year; a suspect value; a shared and a held-back charity.
        rows = [row("140001", "2023-03", 2_000_000, 1_950_000, 50_000, pupils=400, pupil_premium=80_000, cfr_additional_grants_i18=30_000,
                    grant_funding_government=1_800_000),
                row("140001", "2024-03", 2_100_000, 2_050_000, 60_000, pupils=380, pupil_premium=82_000, suspect=["energy"]),
                row("140001", "2025-08", 2_200_000, 2_150_000, 70_000, source="AAR", pupils=360, pupil_premium=0,
                    aar_other_dfe_revenue_grants=40_000, trust_central_spend_per_pupil=510.4)]
        pta = [{"charity_number": 1, "history": [{"period_end": "2023-03", "income": 12_000, "expenditure": 9_000},
                                                  {"period_end": "2025-08", "income": 9_000, "expenditure": 8_000}],
                "shared_with": ["140002"], "match": {"confidence": "high"}},
               {"charity_number": 2, "history": [{"period_end": "2025-08", "income": 50_000, "expenditure": 1}], "review": "independent school"},
               {"charity_number": 3, "history": [{"period_end": "2025-07", "income": 3_000}], "match": {"method": "llm", "confidence": "medium"}}]
        # Act
        sx = build_money.local_series(rows, pta)
        # Assert
        self.assertEqual(set(sx), SERIES_KEYS)
        self.assertEqual(sx["years"], ["2022-23", "2023-24", "2024-25"])
        self.assertEqual(sx["source"], {"2022-23": "CFR", "2023-24": "CFR", "2024-25": "AAR"})
        self.assertEqual(sx["m"]["total_income"]["2022-23"]["v"], 2_000_000)
        self.assertEqual(sx["m"]["total_income"]["2022-23"]["pp"], 5_000)
        self.assertNotIn("2024-25", sx["m"]["pupil_premium"], "academy pupil premium is not reported, never £0")
        self.assertEqual(sx["flags"]["not_reported"], {"pupil_premium": "not reported in academy accounts"})
        self.assertEqual(sx["m"]["other_dfe_grants"]["2022-23"]["v"], 30_000)
        self.assertEqual(sx["m"]["other_dfe_grants"]["2024-25"]["v"], 40_000)
        self.assertEqual(sx["flags"]["suspect"], {"2023-24": ["energy"]})
        self.assertEqual(sx["trust_central_pp"], {"2024-25": 510})
        self.assertEqual(sx["gap"]["2022-23"]["spend_pp"], round(1_950_000 / 400))
        self.assertEqual(sx["gap"]["2022-23"]["gov_pp"], round(1_800_000 / 400))
        self.assertNotIn("2023-24", sx["gap"], "no government funding figure that year")
        # PTA: the CFR school's 2023-03 return is 2022-23, split in two, per pupil on 2022-23's roll;
        # the academy's 2025-08 and 2025-07 returns are 2024-25, the LLM match lowers the confidence.
        self.assertEqual(sx["pta"]["2022-23"], {"income": 6_000, "spend": 4_500, "income_pp": 15, "spend_pp": 11, "charity_number": 1, "confidence": "high"})
        self.assertEqual(sx["pta"]["2024-25"]["income"], 4_500 + 3_000)
        self.assertEqual(sx["pta"]["2024-25"]["income_pp"], round(7_500 / 360))
        self.assertEqual((sx["pta"]["2024-25"]["charity_number"], sx["pta"]["2024-25"]["confidence"]), (1, "medium"))
        json.dumps(sx)

    def test_pta_year_rule_uses_the_schools_own_source_for_that_year(self):
        # Arrange
        cfr = [row("1", "2023-03", 1, 1, 1), row("1", "2024-03", 1, 1, 1)]
        aar = [row("2", "2024-08", 1, 1, 1, source="AAR"), row("2", "2025-08", 1, 1, 1, source="AAR")]
        # Act / Assert
        self.assertEqual(build_money.local_pta_year("2023-03", "CFR"), "2022-23")
        self.assertEqual(build_money.local_pta_year("2025-08", "CFR"), "2025-26")
        self.assertEqual(build_money.local_pta_year("2025-08", "AAR"), "2024-25")
        self.assertEqual(build_money.local_pta_year("2025-09", "AAR"), "2025-26")
        self.assertEqual(build_money.pta_year_label("2023-03", cfr), "2022-23")
        self.assertEqual(build_money.pta_year_label("2025-08", aar), "2024-25")
        self.assertEqual(build_money.pta_year_label("2019-12", aar), "2019-20", "no row that year: the nearest year's source (AAR)")
        self.assertEqual(build_money.pta_year_label("2030-03", cfr), "2029-30")
        self.assertEqual(build_money.year_pupils(cfr, "2022-23"), 300)
        self.assertIsNone(build_money.year_pupils(cfr, "2019-20"))

    # ------------------------------------------------------------ school dashboard

    def test_school_dashboards_get_the_shared_ctx_and_their_own_budget(self):
        # Arrange: most peers' teaching figures are flagged suspect, so their huge values must not reach a median.
        schools, rows = self.peers()
        for r in rows:
            if r["urn"] in {str(100000 + i) for i in range(2, 10)}:
                r.update(teaching_staff=99_000_000, suspect=["teaching_staff"])
        fake = FakeSchoolPage(body_bytes=50_000, indexable=False)
        self.patch(series=fake_series(), school_page=fake)
        # Act
        money, summary = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert: the ctx keys, URLs and medians follow the SHARED contract.
        ctx = fake.ctxs["100000"]
        self.assertEqual(set(ctx), CTX_KEYS)
        self.assertEqual(set(ctx["series"]), SERIES_KEYS)
        self.assertEqual(ctx["check_url"], "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/100000")
        self.assertEqual(ctx["sir_url"], "https://www.schoolsinreach.com/school/100000-peer-0/")
        self.assertEqual(ctx["similar"]["teaching_staff"], round(1_000_000 / 300))
        self.assertEqual(ctx["similar"]["total_income"], round(2_000_000 / 300))
        self.assertEqual(set(ctx["similar_series"]), {"total_income", "total_expenditure", "grant_funding_government", "revenue_reserve"})
        self.assertEqual(sorted(ctx["similar_series"]["total_income"]), ["2022-23", "2023-24", "2024-25"])
        self.assertIsInstance(ctx["timeline"], list)
        self.assertEqual(ctx["ifs"], build_money.load_ifs())
        self.assertTrue(ctx["ifs"])
        # The page is wrapped with the dashboard's head and its own indexable flag, under the school budget.
        html = self.read(money, "school", "100000-peer-0")
        self.assertIn(build_money.SCHOOL_HEAD, html)
        self.assertIn('content="noindex,follow"', html)
        self.assertGreater(len(html.encode("utf-8")), build_money.PAGE_BUDGET)
        self.assertNotIn("/school/100000-peer-0/", self.sitemap(money))
        self.assertTrue((money / "data/sx/100000.json").is_file())
        self.assertGreater(summary["school_page_median"], 50_000)
        self.assertGreaterEqual(summary["school_page_max"], summary["school_page_median"])
        # At the school budget the build fails loudly.
        self.patch(school_page=FakeSchoolPage(body_bytes=build_money.SCHOOL_PAGE_BUDGET))
        with self.assertRaisesRegex(ValueError, "Page too large"):
            self.build([("204", "Hackney")], {"204": schools}, rows)

    def test_without_series_the_fallback_school_page_is_used(self):
        # Arrange: the dashboard alone, with no SERIES module, is not enough.
        schools, rows = self.peers()
        fake = FakeSchoolPage()
        self.patch(school_page=fake)
        # Act
        money, _ = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert
        self.assertEqual(fake.ctxs, {})
        self.assertIn("Show the figures as a table", self.read(money, "school", "100000-peer-0"))
        self.assertTrue((money / "data/sx/100000.json").is_file(), "the local SERIES still feeds drills")

    # ------------------------------------------------------------ area dashboards

    def test_area_dashboards_are_paged_against_their_real_frame(self):
        # Arrange: a council of 30 schools (12 academies in one trust) and dashboards with big rows and intros.
        schools, rows = self.peers(18)
        for i in range(12):
            schools.append(school(140000 + i, f"Academy {i}", type="Academy converter", trust="Good Trust",
                                  constituency="Hackney North and Stoke Newington"))
            rows += full_rows(str(140000 + i), source="AAR", trust="Good Trust", years=("2024-08", "2025-08"))
        areas_module, doc = fake_areas()
        pages = FakeAreaPages()
        self.patch(areas=areas_module, area_pages=pages)
        # Act
        money, _ = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert: every dashboard path, with the stubs they replace gone.
        for path in ("england", "areas", "areas/london", "council", "council/hackney", "constituency/hackney-north-and-stoke-newington",
                     "trust", "trust/good-trust", "debts", "ptfa"):
            html = self.read(money, *path.split("/"))
            self.assertIn(build_money.AREA_HEAD if path != "areas" else "/assets/areas.css", html, path)
            self.assertNotIn("noindex", html, path)
        home = self.read(money)
        self.assertIn('data-headline="England"', home)
        for who, path, _ in build_money.AUDIENCE_LINKS:
            self.assertIn(f'href="{path}"', home)
        self.assertIn('id="find"', home)
        # The ctx carries every page path; trusts are matched by name and given their path.
        kinds = {c[1] for c in pages.calls if c[0] == "area"}
        self.assertEqual(kinds, {"england", "region", "council", "constituency"})
        ctx = next(c[3] for c in pages.calls if c[0] == "area")
        self.assertEqual(set(ctx), {"ifs", "dsg", "real_label", "areas", "paths"})
        self.assertEqual(ctx["paths"]["council"], {"204": "/council/hackney/"})
        self.assertEqual(ctx["paths"]["region"], {"London": "/areas/london/"})
        self.assertEqual(ctx["paths"]["constituency"], {"E14000720": "/constituency/hackney-north-and-stoke-newington/"})
        self.assertEqual(ctx["paths"]["trust"], {"Good Trust": "/trust/good-trust/"})
        trust = next(c[1] for c in pages.calls if c[0] == "trust")
        self.assertEqual((trust["name"], trust["path"], trust["company_number"]), ("Good Trust", "/trust/good-trust/", "01234567"))
        league = next(c[1] for c in pages.calls if c[0] == "league")
        self.assertEqual({k: (v["code"], v["name"], v["path"], v["region"]) for k, v in league.items()},
                         {"204": ("204", "Hackney", "/council/hackney/", "London")})
        # Paging: intro and outro on page 1 only; later pages get the title, a way back, filters, the table and the pager.
        council_pages = ["council/hackney"] + [f"council/hackney/{p.name}" for p in sorted((money / "council/hackney").iterdir()) if p.is_dir()]
        self.assertGreater(len(council_pages), 2)
        listed = Counter()
        for n, path in enumerate(council_pages, 1):
            html = self.read(money, *path.split("/"))
            self.assertLess(len(html.encode("utf-8")), build_money.AREA_PAGE_TARGET, path)
            self.assertEqual("INTRO-council" in html, n == 1, path)
            self.assertEqual("OUTRO-council" in html, n == 1, path)
            self.assertIn("data-filters", html)
            self.assertIn(f"Page {n} of {len(council_pages)}", html)
            self.assertIn("<caption>Every row for Hackney</caption>", html)
            if n > 1:
                self.assertIn("<h1>Hackney school money</h1>", html)
                self.assertIn('href="/council/hackney/">Back to the summary</a>', html)
            listed.update(re.findall(r'data-preview="school:(\d+)"', html))
        self.assertEqual(set(listed), {i["urn"] for i in map(lambda s: {"urn": str(s["urn"])}, schools)})
        self.assertEqual(set(listed.values()), {1}, "each school sits in exactly one row")
        # Every non-school page stays under the target.
        for page in money.rglob("*.html"):
            if "school" not in page.relative_to(money).parts[:1]:
                self.assertLess(page.stat().st_size, build_money.AREA_PAGE_TARGET, page)
        self.assertNotIn("Plain-English guides", self.read(money, "ptfa"))

    def test_paged_keeps_one_row_per_page_when_the_frame_is_already_big(self):
        # Arrange
        rows = [[f"<b>{n}</b>", "x" * 3_000] for n in range(5)]

        def frame(n, total, table_html, big="y" * 39_000):
            return "T", "D", [("School Money", "/")], (big if n == 1 else "") + table_html

        # Act
        pages = build_money.paged("/council/x/", ["A", "B"], rows, frame, None)
        # Assert: page 1 cannot fit a row under the target, so it carries one; the rest fill to the target.
        bodies = [html for _, html in pages]
        self.assertEqual(sum(b.count("<b>") for b in bodies), 5)
        self.assertEqual(bodies[0].count("<b>"), 1)
        for html in bodies[1:]:
            self.assertLess(len(html.encode("utf-8")), build_money.AREA_PAGE_TARGET)
        self.assertEqual([p for p, _ in pages][:2], ["/council/x/", "/council/x/2/"])

    # ------------------------------------------------------------ extensions

    def fake_extension(self, name, write_pages):
        module = types.ModuleType(f"pipeline.money.{name}")
        module.write_pages = write_pages
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        self.patch(EXTENSIONS=(name, "not_a_module_here"))

    def test_extensions_write_through_the_core_writer_and_join_the_sitemap(self):
        # Arrange
        seen = {}

        def write_pages(env):
            seen.update(env)
            env["write"]("/map/", env["page"]("Map", "A map.", "/map/", "<h1>Real map</h1>", [("School Money", "/"), ("Map", "/map/")]))
            env["write"]("/fake/", env["page"]("Fake", "Hidden.", "/fake/", "<h1>Fake</h1>", [("School Money", "/")], indexable=False))
            (Path(env["out"]) / "data/fake.json").write_text("{}", encoding="utf-8")
            return [("/map/", True), ("/fake/", False)]

        self.fake_extension("fake_ext", write_pages)
        schools, rows = self.peers()
        # Act
        money, summary = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert
        self.assertTrue({"out", "write", "page", "items", "areas", "today"} <= set(seen))
        self.assertEqual(len(seen["items"]), 14)
        self.assertIn("england", seen["areas"])
        self.assertIn("Real map", self.read(money, "map"), "the /map/ stub gives way to the extension's page")
        self.assertTrue((money / "data/fake.json").is_file())
        sitemap = self.sitemap(money)
        self.assertIn("/map/</loc>", sitemap)
        self.assertNotIn("/fake/", sitemap)
        self.assertEqual(summary["pages"], sitemap.count("<loc>"))
        self.assertEqual(len(summary["skipped_extensions"]), 1)
        self.assertIn("not_a_module_here", summary["skipped_extensions"][0])

    def test_a_failing_extension_fails_the_build_and_leaves_no_output(self):
        for name, write_pages in (("boom", lambda env: 1 / 0), ("clash", lambda env: env["write"]("/about/", "<html></html>"))):
            with self.subTest(name):
                # Arrange
                self.fake_extension(name, write_pages)
                schools, rows = self.peers()
                out = self.root / f"out-{name}"
                # Act / Assert
                with self.assertRaises((ZeroDivisionError, ValueError)):
                    self.build([("204", "Hackney")], {"204": schools}, rows, out=out)
                self.assertFalse(out.exists())
                self.assertEqual([p for p in self.root.iterdir() if p.name.startswith(".site_money-build")], [])

    def test_the_real_wave_c_extensions_build_on_a_fixture(self):
        # Arrange: the real map, deck, Wrapped and guides modules.
        self.patch(EXTENSIONS=("map_page", "deck", "wrapped", "guides"))
        schools, rows = self.peers()
        # Act
        money, summary = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert
        self.assertEqual(summary["skipped_extensions"], [])
        for path in ("map", "deck", "wrapped", "guides", "tools", "school/100000-peer-0/wrapped"):
            self.assertTrue((money / path / "index.html").is_file(), path)
        self.assertNotIn("A map of every school's financial status is coming", self.read(money, "map"))
        sitemap = self.sitemap(money)
        for path in ("/map/", "/guides/", "/tools/"):
            self.assertIn(f"{BASE_MONEY}{path}</loc>", sitemap)
        self.assertNotIn("/deck/", sitemap)
        for page in money.rglob("*.html"):
            self.assertEqual(Balance(page.read_text(encoding="utf-8")).errors, [], page)

    # ------------------------------------------------------------ copy and safety

    def test_no_page_uses_harsh_words_and_pupils_show_to_one_decimal(self):
        # Arrange: a deficit school beside healthy peers, a trust and a constituency.
        schools, rows = self.peers()
        schools.append(school(140001, "Academy", type="Academy converter", trust="Good Trust"))
        rows += [row("140001", end, 2_000_000, 2_200_000, -150_000, source="AAR", trust="Good Trust", pupils=287.5) for end in ("2024-08", "2025-08")]
        # Act
        money, _ = self.build([("204", "Hackney")], {"204": schools}, rows)
        # Assert
        for page in money.rglob("*.html"):
            match = BANNED.search(body_text(page.read_text(encoding="utf-8")))
            self.assertIsNone(match, (page, match and match.group(0)))
        self.assertIn("287.5", self.read(money, "school", "140001-academy"))

    def test_fallback_pta_copy_follows_the_wording_rules(self):
        # Arrange: a shared LLM-matched charity with recent returns, and one with no income since 2016.
        schools = [school(100001, "Infant School"), school(100002, "Old PTA School")]
        rows = full_rows("100001") + full_rows("100002")
        pta = {"100001": [{"charity_number": 1111111, "name": "Friends of the Infant and Junior Schools", "status": "Registered",
                           "history": [{"period_end": "2024-03", "income": 20_000, "expenditure": 18_000},
                                       {"period_end": "2025-03", "income": 24_000, "expenditure": 20_000}],
                           "shared_with": ["100003"], "match": {"method": "llm", "confidence": "medium"}}],
               "100002": [{"charity_number": 2222222, "name": "Old Friends", "status": "Removed", "history_status": "historical",
                           "last_income_year": 2016, "history": [{"period_end": "2016-08", "income": 4_000, "expenditure": 3_000}]}]}
        # Act
        money, _ = self.build([("204", "Hackney")], {"204": schools}, rows, pta)
        shared, old = self.read(money, "school", "100001-infant-school"), self.read(money, "school", "100002-old-pta-school")
        # Assert
        self.assertIn('data-mf="pta_income" data-v="12000" data-pp="40" data-year="2024-25"', shared)
        self.assertIn("matched with lower confidence", shared)
        self.assertIn("its equal share", shared)
        self.assertIn("never added together", shared)
        self.assertIn("Had a registered PTA until 2016", old)
        for html in (shared, old):
            self.assertNotRegex(body_text(html), r"(?i)\bno PTA\b")

    def test_output_symlink_is_refused_before_anything_is_deleted(self):
        # Arrange
        target = self.root / "elsewhere"
        target.mkdir()
        (target / "keep.txt").write_text("keep", encoding="utf-8")
        link = self.root / "site_money"
        link.symlink_to(target, target_is_directory=True)
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.build([("204", "Hackney")], {"204": [school(100001, "A")]}, full_rows("100001"), out=link)
        self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "keep")


REAL = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
REAL_HISTORY = REAL / "pipeline/.cache/dfe/finance_history.jsonl"
REAL_PTA = REAL / "pipeline/.cache/money/pta.json"


@unittest.skipUnless(REAL_HISTORY.exists(), "real finance history not present")
class RealSeriesTest(unittest.TestCase):
    def test_real_long_histories_fit_the_series_budget_with_every_line(self):
        # Arrange: the largest SERIES on real data (URN 110578, per finance-series) and two ordinary schools.
        urns = {"110578", "100000", "130932"}
        needles = [f'"urn": "{u}"' for u in urns]
        rows = {u: [] for u in urns}
        with open(REAL_HISTORY, encoding="utf-8") as f:
            for line in f:
                if any(n in line[:40] for n in needles):
                    r = json.loads(line)
                    rows[str(r["urn"])].append(r)
        pta = json.loads(REAL_PTA.read_text(encoding="utf-8")).get("schools", {}) if REAL_PTA.exists() else {}
        for urn, own in rows.items():
            if not own:
                continue
            with self.subTest(urn=urn):
                item = {"rows": own, "pta": [c for c in pta.get(urn, []) if not c.get("review")]}
                # Act
                doc = build_money.school_series(item)
                text = build_money.series_json(doc)
                kept = json.loads(text)
                # Assert
                self.assertLessEqual(len(text.encode("utf-8")), build_money.SX_BUDGET)
                self.assertTrue(build_money.SX_CORE & set(doc["m"]) <= set(kept["m"]))
                dropped = {k for k, v in doc["m"].items() if v} - set(kept["m"])
                # Only the very largest histories lose a detail line, and then just one or two.
                self.assertLessEqual(len(dropped), 2 if urn == "110578" else 0, dropped)


class HelpersTest(unittest.TestCase):
    def test_pupils_by_year_carries_a_missing_latest_year_forward(self):
        # Arrange: a council school with 2024-25 and 2025-26 returns, an academy whose latest is 2024-25.
        council_school = {"years": [row("1", "2025-03", 1, 1, 1, pupils=200), row("1", "2026-03", 1, 1, 1, pupils=210)]}
        academy = {"years": [row("2", "2024-08", 1, 1, 1, source="AAR", pupils=900), row("2", "2025-08", 1, 1, 1, source="AAR", pupils=950)]}
        # Act
        totals = build_money.pupils_by_year([council_school, academy])
        # Assert: 2025-26 counts the academy's 2024-25 roll; 2023-24 is the academy alone.
        self.assertEqual(totals, {"2023-24": 900, "2024-25": 1150, "2025-26": 1160})


class DeployFilesTest(unittest.TestCase):
    """The nginx templates and deploy script are read as text; nothing is run."""

    def test_www_template_redirects_old_money_paths_to_the_money_host(self):
        text = (ROOT / "deploy/railway/nginx.conf.template").read_text(encoding="utf-8")
        self.assertIn("return 301 https://money.schoolsinreach.com/$1", text)
        self.assertIn("location = /money ", text)
        self.assertNotIn("rewrite ^/$ /money/", text)
        self.assertNotIn("location /money/ ", text)
        self.assertIn("location /school/", text)

    def test_money_template_serves_a_static_site_with_revalidated_assets(self):
        text = (ROOT / "deploy/money/nginx.conf.template").read_text(encoding="utf-8")
        self.assertIn("listen ${PORT};", text)
        self.assertIn("absolute_redirect off;", text)
        self.assertIn("error_page 404 /404.html;", text)
        # Asset URLs are unversioned, so a year-long immutable cache would pin stale JS/CSS after a deploy.
        self.assertIn("location /assets/ { add_header Cache-Control \"public, max-age=300, stale-while-revalidate=86400\"", text)
        self.assertNotIn("max-age=31536000", text)
        self.assertIn("location /data/ { add_header Cache-Control \"public, max-age=3600\"", text)
        self.assertIn("try_files $uri $uri/ =404;", text)
        self.assertIn("location = /health", text)
        self.assertIn("gzip_types", text)
        self.assertEqual(text.count("{"), text.count("}"))

    def test_deploy_script_and_dockerfile_target_the_school_money_service(self):
        script = (ROOT / "deploy/money/deploy.sh").read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", script)
        self.assertIn("python3 -m pipeline.money.build_money", script)
        self.assertIn("--service school-money", script)
        self.assertIn("20_000", script)
        self.assertIn("zstd -q -19 --long=30", script)
        self.assertIn("140000000", script)
        docker = (ROOT / "deploy/money/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM nginx:1.27-alpine", docker)
        # The archive is unpacked with the same window it was packed with, in a stage of its own.
        self.assertIn("zstd -d --long=30", docker)
        self.assertIn("COPY --from=site /site /usr/share/nginx/html", docker)
        www = (ROOT / "deploy/railway/deploy.sh").read_text(encoding="utf-8")
        self.assertNotIn("build_money", www.split("\n# School Money is a separate service")[-1].split("\n", 2)[-1])
        self.assertNotIn("Money payload", www)


if __name__ == "__main__":
    unittest.main()
