"""Offline fixture tests for the School Money site build. Never reads or alters the real school data."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
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


class BuildMoneyTest(unittest.TestCase):
    def setUp(self):
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
        stub = self.read("map")
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
        self.assertNotIn("tags", data)  # areas.py absent in this test run or monkeypatched away below
        raw = (self.out / "data/s/100001.json").read_text(encoding="utf-8")
        self.assertIn('"income":2000000,"income_pp":6667', raw)  # compact separators, whole pounds

    def test_area_json_search_index_and_status_paths(self):
        self.build()
        area = json.loads((self.out / "data/a/council-204.json").read_text(encoding="utf-8"))
        self.assertEqual((area["id"], area["type"], area["name"], area["path"]), ("council-204", "council", "Hackney", "/council/hackney/"))
        latest = area["by_year"]["2024-25"]["all"]
        self.assertEqual((latest["schools"], latest["in_deficit"], latest["deficit_total"]), (15, 1, 200_000))
        self.assertEqual(latest["income_pp_median"], 6667)
        self.assertEqual(area["dsg"]["2024-25"]["balance"], -16_493_653)
        self.assertEqual(area["dsg"]["2024-25"]["per_pupil"], round(-16_493_653 / 4500))
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
        self.assertNotIn(BASE_MONEY + "/map/", locs)
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
            self.assertNotIn("<b>", html, page)
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
        self.assertLess(size, 36_000, size)  # headroom under PAGE_BUDGET for the app shell's header and footer
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

    def test_money_template_serves_a_static_site_with_long_lived_assets(self):
        text = (ROOT / "deploy/money/nginx.conf.template").read_text(encoding="utf-8")
        self.assertIn("listen ${PORT};", text)
        self.assertIn("absolute_redirect off;", text)
        self.assertIn("error_page 404 /404.html;", text)
        self.assertIn("max-age=31536000, immutable", text)
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
        docker = (ROOT / "deploy/money/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM nginx:1.27-alpine", docker)
        www = (ROOT / "deploy/railway/deploy.sh").read_text(encoding="utf-8")
        self.assertNotIn("build_money", www.split("\n# School Money is a separate service")[-1].split("\n", 2)[-1])
        self.assertNotIn("Money payload", www)


if __name__ == "__main__":
    unittest.main()
