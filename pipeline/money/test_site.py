"""Offline tests for the School Money app shell: site.py, the glossary and (when node is present) app.js."""
import json
import re
import shutil
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

from pipeline.money import site

REPO = Path(__file__).resolve().parents[2]
VOID = {"meta", "link", "br", "hr", "img", "input", "path", "circle", "rect", "line", "source", "wbr"}

NATIONAL_FIXTURE = (
    '<section class="tiles">'
    + site.money_figure("total_income", 52_000_000_000, 8_100_000, "2024-25")
    + site.money_figure("grant_funding", 50_000_000_000, 8_100_000, "2024-25")
    + site.money_figure("total_expenditure", 51_500_000_000, 8_100_000, "2024-25")
    + site.money_figure("revenue_reserve", 4_200_000_000, 8_100_000, "2024-25")
    + site.money_figure("in_year_balance", 500_000_000, 8_100_000, "2024-25", signed=True)
    + site.money_figure("dsg_balance", -3_400_000_000, 8_100_000, "2024-25", signed=True)
    + site.money_figure("pta_income", 120_000_000, 8_100_000, "2024-25")
    + site.money_figure("deficit_total", -900_000_000, None, "2024-25")
    + '<span class="mf" data-mf="in_deficit_pct" data-v="12.4" data-year="2024-25">12.4%</span>'
    + "</section>"
)


class Balance(HTMLParser):
    """Tracks open tags; a well-formed document ends with an empty stack."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> with stack {self.stack[-3:]}")
            return
        self.stack.pop()


def parse(html):
    p = Balance()
    p.feed(html)
    p.close()
    return p


def attr(html, tag_snippet, name):
    m = re.search(tag_snippet + r'[^>]*\s' + name + r'="([^"]*)"', html)
    return m.group(1) if m else None


class PageTest(unittest.TestCase):
    def setUp(self):
        # Arrange
        self.crumbs = [("School Money", "/"), ("Hackney", "/council/hackney/"), ("William Patten <Primary>", "/school/130932-william-patten-primary-school/")]
        self.html = site.page("William Patten <Primary> & money", 'Reserve "tight" & falling', "/school/130932-william-patten-primary-school/",
                              "<h1>Body</h1>", self.crumbs)

    def test_document_is_balanced_and_has_landmarks(self):
        # Act
        p = parse(self.html)
        # Assert
        self.assertEqual(p.errors, [])
        self.assertEqual(p.stack, [])
        self.assertIn("main", p.ids)
        self.assertIn("q", p.ids)
        self.assertEqual(len(set(p.ids)), len(p.ids), "duplicate ids")
        for landmark in ("<header", '<nav class="main-nav" aria-label="Main">', '<main id="main"', "<footer", '<a class="skip" href="#main">'):
            self.assertIn(landmark, self.html)

    def test_head_metadata(self):
        url = site.BASE_MONEY + "/school/130932-william-patten-primary-school/"
        self.assertIn(f'<link rel="canonical" href="{url}">', self.html)
        self.assertIn(f'<meta property="og:url" content="{url}">', self.html)
        self.assertIn('<meta property="og:title" content="William Patten &lt;Primary&gt; &amp; money">', self.html)
        self.assertIn('<meta name="twitter:card" content="summary">', self.html)
        self.assertIn('<title>William Patten &lt;Primary&gt; &amp; money</title>', self.html)
        self.assertIn('<meta name="description" content="Reserve &quot;tight&quot; &amp; falling">', self.html)
        self.assertNotIn('<meta name="robots"', self.html)
        self.assertIn('<link rel="stylesheet" href="/assets/app.css">', self.html)
        self.assertIn('<script src="/assets/app.js" defer></script>', self.html)
        self.assertIn('<html lang="en-GB"', self.html)

    def test_no_raw_angle_brackets_from_data(self):
        # The title, description and crumb names carry '<' and must never reach the page unescaped.
        self.assertNotIn("<Primary>", self.html)
        ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.html, re.S).group(1)
        self.assertNotIn("<", ld)
        data = json.loads(ld)
        self.assertEqual(data[0]["@type"], "BreadcrumbList")
        self.assertEqual(data[0]["itemListElement"][-1]["name"], "William Patten <Primary>")
        self.assertEqual(data[0]["itemListElement"][0]["item"], site.BASE_MONEY + "/")

    def test_nav_search_audience_footer(self):
        for label, href in site.NAV:
            self.assertIn(f'href="{href}"', self.html)
            self.assertIn(f">{label}", self.html)
        self.assertIn('<span class="count" data-pin-count>0</span>', self.html)
        self.assertIn('<input id="q" name="q" type="search"', self.html)
        self.assertIn('<form class="search" role="search" action="/search/">', self.html)
        for aud in ("parent", "governor", "ptfa", "leader", "pupil"):
            self.assertIn(f'data-audience="{aud}"', self.html)
        self.assertIn('<fieldset class="audience">', self.html)
        for source in ("Financial Benchmarking", "Get Information about Schools", "Charity Commission", "GDP deflators", "IFS, Annual report"):
            self.assertIn(source, self.html)
        self.assertIn('href="/about/#sources"', self.html)
        self.assertIn('href="/about/#licences"', self.html)
        self.assertIn('href="/about/">How the figures are worked out</a>', self.html)
        self.assertIn(f'<a href="{site.BASE_SIR}">Schools in Reach</a>', self.html)
        self.assertIn(f'<a class="tagline" href="{site.BASE_SIR}">by Schools in Reach</a>', self.html)
        self.assertIn('<span aria-current="page">William Patten &lt;Primary&gt;</span>', self.html)
        self.assertIn('<a href="/council/hackney/">Hackney</a>', self.html)

    def test_noindex_and_og_image(self):
        # Act
        html = site.page("t", "d", "/compare/", "", [("School Money", "/"), ("Compare", "/compare/")], indexable=False,
                         og_image="https://money.schoolsinreach.com/assets/og.png", extra_head='<meta name="x" content="y">')
        # Assert
        self.assertIn('<meta name="robots" content="noindex,follow">', html)
        self.assertIn('<meta property="og:image" content="https://money.schoolsinreach.com/assets/og.png">', html)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', html)
        self.assertIn('<meta name="x" content="y">', html)
        self.assertIn('<a href="/compare/" aria-current="page">Compare', html)
        self.assertEqual(parse(html).errors, [])

    def test_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            site.page("t", "d", "school/1/", "", [("School Money", "/")])


class MoneyFigureTest(unittest.TestCase):
    def test_total_and_per_pupil(self):
        # Act
        html = site.money_figure("total_income", 1_234_567, 300, "2024-25", src="https://example.org/x", cmp_similar=4000.4, cmp_england=4100)
        # Assert
        self.assertIn('class="mf"', html)
        self.assertIn('data-mf="total_income"', html)
        self.assertIn('data-v="1234567"', html)
        self.assertIn('data-pp="4115"', html)
        self.assertIn('data-year="2024-25"', html)
        self.assertIn('data-src="https://example.org/x"', html)
        self.assertIn('data-cmp-similar="4000"', html)
        self.assertIn('data-cmp-england="4100"', html)
        self.assertIn("£1.2m", html)
        self.assertIn("<small>£4,115 per pupil</small>", html)
        self.assertEqual(parse(html).errors, [])

    def test_without_pupils_omits_pp(self):
        for pupils in (None, 0):
            html = site.money_figure("deficit_total", -950_000, pupils, "2023-24", label="Deficits <all>", drill="#drill-1", cls="big")
            self.assertNotIn("data-pp", html)
            self.assertNotIn("per pupil", html)
            self.assertIn('class="mf big"', html)
            self.assertIn('data-label="Deficits &lt;all&gt;"', html)
            self.assertIn('data-drill="#drill-1"', html)
            self.assertIn("-£950k", html)

    def test_none_value_and_signed(self):
        self.assertIn('data-v=""', site.money_figure("revenue_reserve", None, 100, "2024-25"))
        self.assertIn("—", site.money_figure("revenue_reserve", None, 100, "2024-25"))
        signed = site.money_figure("in_year_balance", 25_000, 100, "2024-25", signed=True)
        self.assertIn("+£25k", signed)
        self.assertIn("+£250 per pupil", signed)
        self.assertIn('data-signed="1"', signed)


class PinButtonTest(unittest.TestCase):
    def test_json_payload_round_trips(self):
        # Act
        html = site.pin_button("school", 130932, "William Patten's \"Primary\" & Nursery <School>")
        # Assert
        m = re.search(r"data-pin='([^']*)'", html)
        self.assertIsNotNone(m)
        payload = json.loads(__import__("html").unescape(m.group(1)))
        self.assertEqual(payload["type"], "school")
        self.assertEqual(payload["id"], "130932")
        self.assertEqual(payload["name"], "William Patten's \"Primary\" & Nursery <School>")
        self.assertEqual(payload["p"], "/school/130932-william-patten-s-primary-and-nursery-school/")
        self.assertIn('aria-pressed="false"', html)
        self.assertEqual(parse(html).errors, [])

    def test_area_paths(self):
        self.assertEqual(json.loads(__import__("html").unescape(re.search(r"data-pin='([^']*)'", site.pin_button("area", "council-204", "Hackney")).group(1)))["p"], "/council/hackney/")
        self.assertEqual(site.page_path("area", "england", "England"), "/")
        self.assertEqual(site.page_path("area", "region-london", "London"), "/areas/london/")
        self.assertEqual(site.page_path("area", "constituency-hackney-north", "Hackney North"), "/constituency/hackney-north/")
        override = site.pin_button("area", "council-204", "Hackney", path="/x/")
        self.assertEqual(json.loads(__import__("html").unescape(re.search(r"data-pin='([^']*)'", override).group(1)))["p"], "/x/")


class GlossaryTest(unittest.TestCase):
    SHARED_KEYS = """total_income grant_funding grant_funding_government sen_funding pupil_premium self_generated_income donations
    donations_revenue donations_capital lettings_income facilities_income catering_income teacher_pension_ni_grants non_government_grants
    total_expenditure teaching_staff supply_staff education_support_staff admin_clerical_staff premises_staff catering_staff other_staff_costs
    total_staff premises energy occupation catering educational_supplies supplies_services bought_in_services revenue_reserve
    revenue_reserve_incl_trust_share reserve_committed reserve_uncommitted reserve_share in_year_balance per_pupil real_terms pupils fsm_pct
    ehcp_pct dsg_balance dsg_per_pupil deficit_total in_deficit_pct pta_income pta_spending pta_per_pupil trust_central_spend cfr_line aar_line
    status_in_deficit status_heading_for_deficit status_tight status_healthy status_large_reserves band""".split()

    def setUp(self):
        with open(site.ASSETS / "glossary.json", encoding="utf-8") as fh:
            self.glossary = json.load(fh)

    def test_every_shared_key_present_and_complete(self):
        entries = {k: v for k, v in self.glossary.items() if not k.startswith("_")}
        self.assertEqual(sorted(set(self.SHARED_KEYS) - set(entries)), [])
        for key, entry in entries.items():
            for field in ("label", "plain", "how", "source"):
                self.assertIsInstance(entry.get(field), str, f"{key}.{field}")
                self.assertTrue(entry[field].strip(), f"{key}.{field} empty")
            self.assertTrue(entry["plain"].endswith("."), f"{key}.plain should be a sentence")

    def test_ifs_paths_resolve(self):
        with open(REPO / "pipeline/money/data/ifs_context.json", encoding="utf-8") as fh:
            ifs = json.load(fh)
        for key, entry in self.glossary.items():
            if key.startswith("_") or "ifs" not in entry:
                continue
            node = ifs
            for part in entry["ifs"].split("."):
                self.assertIn(part, node, f"{key}.ifs = {entry['ifs']}")
                node = node[part]

    def test_national_fixture_keys_are_in_glossary(self):
        keys = re.findall(r'data-mf="([^"]+)"', NATIONAL_FIXTURE)
        self.assertGreaterEqual(len(keys), 9)
        for key in keys:
            self.assertIn(key, self.glossary, key)
        self.assertEqual(parse(NATIONAL_FIXTURE).errors, [])


class AssetsTest(unittest.TestCase):
    def test_asset_files(self):
        names = {p.name for p in site.asset_files()}
        self.assertTrue({"app.css", "app.js", "glossary.json"} <= names, names)
        for p in site.asset_files():
            self.assertTrue(p.is_file())
            self.assertTrue(p.is_relative_to(site.ASSETS))

    def test_css_defines_tokens_and_chart_classes(self):
        css = (site.ASSETS / "app.css").read_text(encoding="utf-8")
        for token in ("--critical", "--serious", "--warning", "--good", "--plenty", "--accent", "--paper", "--ink"):
            self.assertIn(token + ":", css)
        self.assertIn("prefers-color-scheme: dark", css)
        for cls in (".chart .grid", ".chart .axis", ".chart .tick", ".chart .bar.pos", ".chart .bar.neg", ".chart .line.s1",
                    ".chart .line.s2", ".chart .dot", ".chart .band", ".chart .median", ".chart .hit", ".chart .mark",
                    ".badge.s-in_deficit", ".badge.s-large_reserves", "table[data-sortable] th", ":focus-visible", ".skip"):
            self.assertIn(cls, css)
        self.assertIn("tabular-nums", css)
        self.assertIn("72rem", css)

    def test_js_sets_global_and_guards_dom(self):
        js = (site.ASSETS / "app.js").read_text(encoding="utf-8")
        self.assertIn('"use strict"', js)
        self.assertIn("root.MoneyApp = API", js)
        self.assertIn('typeof document === "undefined"', js)
        self.assertNotIn("innerHTML", js)
        for key in ("moneyPinned", "moneyAudience", "/data/search.json", "/assets/glossary.json", "/data/s/", "/data/a/", "/data/postcodes/"):
            self.assertIn(key, js)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AppJsTest(unittest.TestCase):
    def test_node_suite_passes(self):
        # Act
        proc = subprocess.run(["node", "--test", "--test-reporter=tap", str(REPO / "pipeline/money/test_app_js.mjs")], capture_output=True, text=True, timeout=120, cwd=REPO)
        # Assert
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
        self.assertRegex(proc.stdout, r"# fail 0")


if __name__ == "__main__":
    sys.exit(unittest.main())
