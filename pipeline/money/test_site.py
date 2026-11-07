"""Offline tests for the School Money app shell: site.py, the glossary and (when node is present) app.js."""
import json
import re
import shutil
import subprocess
import sys
import unittest
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pipeline.money import site

REPO = Path(__file__).resolve().parents[2]
# deck.js views a school presentation link may name; governors and review are being added beside school and ptfa,
# and until then deck.js shows the school presentation for them.
DECK_VIEWS = {"school", "ptfa", "governors", "review"}
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
        for landmark in ("<header", '<nav class="main-nav" id="main-nav" aria-label="Main">', '<main id="main"', "<footer", '<a class="skip" href="#main">'):
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



class AudiencePickerTest(unittest.TestCase):
    """The "Show me what matters to a" picker, the panel slot under the header and the head script that restores a choice."""

    def setUp(self):
        # Arrange
        self.html = site.page("t", "d", "/school/100001-example-primary/", "<h1>Body</h1>", [("School Money", "/")])

    def test_picker_wording_chips_and_clear(self):
        # Assert
        self.assertIn("<legend>Show me what matters to a</legend>", self.html)
        chips = re.findall(r'<button type="button" data-audience="([a-z]+)" aria-pressed="(true|false)">', self.html)
        self.assertEqual(chips, [(key, "false") for key, _ in site.AUDIENCES])  # nothing chosen until the reader picks
        self.assertIn('</span><button type="button" class="aud-clear">Clear</button></fieldset>', self.html)
        # its own row under the header's grid, so the search box keeps its width
        self.assertIn('</nav></div><div class="aud-bar"><fieldset class="audience">', self.html)

    def test_panel_slot_follows_the_header_and_assets_load_after_app_css(self):
        # Assert
        self.assertIn('</header><div id="for-you"></div><main id="main"', self.html)
        head = self.html.split("</head>", 1)[0]
        boot, app_css, aud_css = (head.index(x) for x in (site.AUDIENCE_BOOT, 'href="/assets/app.css"', 'href="/assets/audience.css"'))
        self.assertLess(boot, app_css)
        self.assertLess(app_css, aud_css)
        p = parse(self.html)
        self.assertEqual(p.errors, [])
        self.assertEqual(len(set(p.ids)), len(p.ids), "duplicate ids")

    def test_boot_script_knows_every_reader_and_app_js_storage_key(self):
        # Arrange
        js = (site.ASSETS / "app.js").read_text(encoding="utf-8")
        readers = json.loads(re.search(r"var READERS = (\[[^\]]*\]);", js).group(1))
        # Assert
        self.assertEqual(readers, [key for key, _ in site.AUDIENCES])
        self.assertIn('KEY_AUD = "moneyAudience"', js)
        self.assertIn('localStorage.getItem("moneyAudience")', site.AUDIENCE_BOOT)
        self.assertIn("/^(" + "|".join(readers) + ")$/", site.AUDIENCE_BOOT)
        self.assertLess(len(site.AUDIENCE_BOOT), 260)  # every page carries it; school pages are near their size budget

    def test_audience_css_uses_the_design_tokens_and_tags_every_reader(self):
        # Arrange
        css = (site.ASSETS / "audience.css").read_text(encoding="utf-8")
        rules = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        # Assert
        self.assertIn("audience.css", {p.name for p in site.asset_files()})
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rules), "colours come from app.css's tokens")
        for token in ("var(--accent)", "var(--accent-soft)", "var(--accent-ink)", "var(--ink)", "var(--card)"):
            self.assertIn(token, rules)
        for key, _ in site.AUDIENCES:
            self.assertIn(f'html[data-reader="{key}"] .sp-sec[data-readers~="{key}"] > h2::after', rules)
            self.assertIn(f'html[data-reader="{key}"] header.top button[data-audience="{key}"]', rules)
        self.assertIn("html:not(.js) .aud-bar { display: none; }", rules)


def css_rules(name):
    """An asset stylesheet without its comments, whitespace collapsed."""
    css = (site.ASSETS / name).read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", css, flags=re.S))


def media_block(css, query):
    """The text of every @media block for query, concatenated (braces balanced by counting)."""
    out, start = [], 0
    while (i := css.find(f"@media ({query})", start)) != -1:
        j = css.index("{", i) + 1
        depth = 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        out.append(css[i:j])
        start = j
    return " ".join(out)


def contrast(a, b):
    """WCAG contrast ratio of two #rrggbb colours."""
    def lum(h):
        r, g, b_ = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b_)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class PhoneHeaderTest(unittest.TestCase):
    """The nav behind a Menu button on a phone (audit C50): markup from site.page, rules from app.css."""

    def setUp(self):
        # Arrange
        self.school = site.page("t", "d", "/school/100001-example-primary/", "<h1>Body</h1>", [("School Money", "/")])
        self.home = site.page("t", "d", "/", "<h1>Body</h1>", [("School Money", "/")])
        self.css = css_rules("app.css")

    def test_menu_button_is_a_disclosure_for_the_nav(self):
        # Assert
        self.assertIn('<button type="button" class="menu-toggle" aria-expanded="false" aria-controls="main-nav">Menu</button>'
                      '<nav class="main-nav" id="main-nav" aria-label="Main">', self.school)
        self.assertLess(self.school.index('<form class="search"'), self.school.index("menu-toggle"),
                        "Menu sits just before the nav, so Tab goes from it into the opened menu")
        self.assertIn('<header class="top"><div class="wrap">', self.school)
        self.assertIn('<header class="top home"><div class="wrap">', self.home)
        self.assertEqual(parse(self.home).errors, [])

    def test_header_search_is_a_combobox(self):
        self.assertIn('<input id="q" name="q" type="search" placeholder="School, council, trust or postcode" autocomplete="off" '
                      'role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="q-list">', self.school)

    def test_menu_rules_show_the_nav_without_javascript_and_hide_it_behind_the_button_on_a_phone(self):
        # Arrange
        phone = media_block(self.css, "max-width: 600px")
        outside = self.css.replace(phone, "")
        # Assert: hidden everywhere by default (so no JavaScript, no button) and only ever shown under html.js on a phone
        self.assertIn(".menu-toggle { display: none;", outside)
        self.assertNotIn("+ nav.main-nav", outside, "only a phone ever hides the nav")
        self.assertIn("html.js .menu-toggle { display: inline-flex; }", phone)
        self.assertIn('html.js .menu-toggle[aria-expanded="false"] + nav.main-nav { display: none; }', phone)
        self.assertIn("header.top.home form.search { display: none; }", phone)
        self.assertIn('grid-template-areas: "brand menu" "tag tag" "search search" "nav nav"', phone)

    def test_sort_controls_replace_clipped_header_buttons_on_a_phone(self):
        # Arrange
        phone = media_block(self.css, "max-width: 600px")
        # Assert
        self.assertIn(".sort-controls { display: none;", self.css)
        self.assertIn(".sort-controls.for-responsive { display: flex; }", phone)
        self.assertIn("table.responsive thead button.sort { display: none; }", phone)
        self.assertIn("table.responsive thead .th-label { display: inline; }", phone)
        self.assertIn(".th-label { display: none; }", self.css)

    def test_focus_stays_visible(self):
        # Assert: a global ring, and no rule takes an outline away unless it is a mouse focus (:not(:focus-visible))
        self.assertIn(":focus-visible { outline: 3px solid var(--accent);", self.css)
        for rule in re.findall(r"[^{}]*\{[^}]*outline: (?:none|0)[^}]*\}", self.css):
            self.assertIn(":not(:focus-visible)", rule)
        self.assertIn(".statusbar .seg:focus-visible { outline: 3px solid var(--ink);", self.css)
        self.assertIn("table[data-sortable] th button.sort:focus-visible", self.css)

    def test_picker_is_compact_on_a_phone(self):
        # Arrange
        phone = media_block(css_rules("audience.css"), "max-width: 600px")
        # Assert
        self.assertIn("header.top fieldset.audience button { min-height: 36px;", phone)


class HeldByTrustStatusTest(unittest.TestCase):
    """Contract C4: a neutral grey for 'Reserve held by the trust', light and dark, readable, with its classes."""

    def test_tokens_and_classes(self):
        # Arrange
        css = css_rules("app.css")
        dark = media_block(css, "prefers-color-scheme: dark")
        tokens = {}
        for scope, text in (("light", css.replace(dark, "")), ("dark", dark)):
            tokens[scope] = {k: re.search(rf"--{k}: (#[0-9a-f]{{6}})", text).group(1) for k in ("held", "held-soft", "held-text", "paper", "card")}
        # Assert
        for scope, t in tokens.items():
            with self.subTest(scope=scope):
                self.assertGreaterEqual(contrast(t["held-text"], t["held-soft"]), 4.5)
                self.assertGreaterEqual(contrast(t["held-text"], t["card"]), 4.5)
                self.assertGreaterEqual(contrast(t["held"], t["paper"]), 3.0)
        self.assertIn(".badge.s-reserve_held_by_trust { border-color: var(--held); background: var(--held-soft); color: var(--held-text); }", css)
        self.assertIn(".s-reserve_held_by_trust > span[aria-hidden] { color: var(--held-text); }", css)
        self.assertIn(".seg.s-reserve_held_by_trust { background: var(--held); }", css)

    def test_app_js_knows_the_label_and_icon(self):
        js = (site.ASSETS / "app.js").read_text(encoding="utf-8")
        self.assertIn('reserve_held_by_trust: "Reserve held by the trust"', js)
        self.assertIn('reserve_held_by_trust: "◇"', js)


EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
ENTITY = re.compile(r"\b(?:Ltd|Limited|LLP|plc|CIC)\b")


class CorrectionsAndPrivacyTest(unittest.TestCase):
    """Contract C6: the about page's corrections and privacy sections, and the report link in the footer."""

    def setUp(self):
        self.saved = site.CONTACT_EMAIL

    def tearDown(self):
        site.CONTACT_EMAIL = self.saved

    def test_contact_email_is_unset(self):
        self.assertIsNone(site.CONTACT_EMAIL)

    def test_corrections_without_an_address_say_where_to_correct_at_source_and_that_one_is_coming(self):
        # Arrange
        site.CONTACT_EMAIL = None
        # Act
        html = site.corrections_html()
        # Assert
        self.assertTrue(html.startswith('<h2 id="corrections">'))
        for needle in ("Department for Education", "council", "trust", "Charity Commission", "A direct corrections address is coming",
                       "Dedicated Schools Grant balance (all four blocks)"):
            self.assertIn(needle, html)
        self.assertNotIn("mailto:", html)
        self.assertIsNone(EMAIL.search(html))
        self.assertEqual(parse(html).errors, [])

    def test_corrections_and_privacy_offer_the_address_once_it_is_set(self):
        # Arrange
        site.CONTACT_EMAIL = "corrections@example.org"
        # Act
        corrections, privacy = site.corrections_html(), site.privacy_html()
        # Assert
        self.assertIn('<a href="mailto:corrections@example.org">corrections@example.org</a>', corrections)
        self.assertNotIn("is coming", corrections)
        self.assertIn('<a href="mailto:corrections@example.org">corrections@example.org</a>', privacy)

    def test_privacy_says_what_is_stored_and_what_leaves_the_site(self):
        # Arrange
        site.CONTACT_EMAIL = None
        # Act
        html = site.privacy_html()
        # Assert
        self.assertTrue(html.startswith('<h2 id="privacy">'))
        for needle in ("localStorage", "on this device", "api.postcodes.io", "IP address", "logs", "No personal details"):
            self.assertIn(needle, html)
        self.assertNotIn("None", html)
        self.assertNotIn("mailto:", html)
        self.assertEqual(parse(html).errors, [])

    def test_footer_has_the_report_link_and_privacy(self):
        # Act
        html = site.page("t", "d", "/about/", "<h1>About</h1>", [("School Money", "/")])
        footer = html.split("<footer>", 1)[1]
        # Assert
        self.assertEqual(site.REPORT_LINK, '<a class="report-link" href="/about/#corrections">Report an error or add context</a>')
        self.assertIn(site.REPORT_LINK, footer)
        self.assertIn('<a href="/about/#privacy">Privacy</a>', footer)
        self.assertIn(".report-link {", css_rules("app.css"))

    def test_no_personal_address_or_legal_entity_anywhere_in_the_shell(self):
        # Arrange
        site.CONTACT_EMAIL = None
        html = site.page("t", "d", "/", "<h1>x</h1>", [("School Money", "/")]) + site.corrections_html() + site.privacy_html()
        # Assert
        self.assertIsNone(EMAIL.search(html))
        self.assertIsNone(ENTITY.search(html))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AudienceBootScriptTest(unittest.TestCase):
    """site.AUDIENCE_BOOT run under node against a stub <html> and localStorage."""

    def run_boot(self, storage):
        script = site.AUDIENCE_BOOT.removeprefix("<script>").removesuffix("</script>")
        harness = ("const attrs = {}, classes = [];"
                   "globalThis.document = {documentElement: {classList: {add: c => classes.push(c)}, setAttribute: (k, v) => { attrs[k] = v; }}};"
                   f"const stored = {json.dumps(storage)};"
                   "globalThis.localStorage = {getItem: k => { if (stored === 'THROW') throw new Error('blocked'); return stored[k] ?? null; }};"
                   f"{script};console.log(JSON.stringify({{attrs, classes}}));")
        proc = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_saved_reader_is_restored_before_first_paint(self):
        # Act / Assert
        self.assertEqual(self.run_boot({"moneyAudience": '"governor"'}), {"attrs": {"data-reader": "governor"}, "classes": ["js"]})

    def test_nothing_saved_cleared_or_unknown_sets_no_reader(self):
        for storage in ({}, {"moneyAudience": "null"}, {"moneyAudience": '"teacher"'}, {"moneyAudience": "{not json"}, "THROW"):
            with self.subTest(storage=storage):
                # Act / Assert
                self.assertEqual(self.run_boot(storage), {"attrs": {}, "classes": ["js"]})


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AudienceLinksResolveTest(unittest.TestCase):
    """Every link the panel offers, for every reader, resolves on a fixture site built with every real unit."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pipeline.money import build_money
        from pipeline.money.test_build_money import full_rows, make_site, row, school
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        schools = [school(100000 + i, f"Peer {i}", constituency="Hackney North and Stoke Newington") for i in range(8)]
        schools.append(school(140001, "Good Academy", type="Academy converter", trust="Good Trust"))
        rows = [r for i in range(8) for r in full_rows(str(100000 + i), reserve=40_000 + 5_000 * i)]
        rows += [row("140001", end, 2_000_000, 2_100_000, -50_000, source="AAR", trust="Good Trust") for end in ("2024-08", "2025-08")]
        site_dir, history, links, pta = make_site(root, [("204", "Hackney")], {"204": schools}, rows)
        cls.out = root / "site_money"
        summary = build_money.build(site_dir, history, links, pta, out=cls.out, dsg_path=root / "no-dsg.json")
        assert summary["skipped_extensions"] == [], summary["skipped_extensions"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def page(self, path):
        """What app.js reads from a built page: its path, the ids in <main> and the first pin in <main>."""
        html = (self.out / path.lstrip("/") / "index.html").read_text(encoding="utf-8")
        main = html.split('<main id="main"', 1)[1]
        ids = re.findall(r'\sid="([^"]+)"', main)
        if "<table data-sortable" in main and not path.startswith("/school/"):
            ids.append("schools")  # app.js gives the schools table this id on council, constituency and trust pages
        pin = re.search(r"data-pin='([^']+)'", main)
        return {"path": path, "sections": ids, "pin": json.loads(unescape(pin.group(1))) if pin else None}

    def links(self, pages):
        script = ("require(process.argv[1]); const M = globalThis.MoneyApp;"
                  "const out = JSON.parse(process.argv[2]).map(pg => { const page = Object.assign(M.pageOf(pg.path), {sections: pg.sections});"
                  " if (pg.pin && pg.pin.type === 'area' && (page.kind === 'council' || page.kind === 'constituency')) page.areaId = pg.pin.id;"
                  " return [pg.path, M.READERS.map(r => [r, M.audienceLinks(r, page)])]; });"
                  "console.log(JSON.stringify(out));")
        proc = subprocess.run(["node", "-e", script, str(site.ASSETS / "app.js"), json.dumps(pages)], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def resolves(self, href, sections):
        parts = urlsplit(href)
        if not parts.path:
            return parts.fragment in sections
        if not (self.out / parts.path.lstrip("/") / "index.html").is_file():
            return False
        query = parse_qs(parts.query)
        if "urn" in query:
            return (self.out / "data/s" / f"{query['urn'][0]}.json").is_file() and query.get("view", ["school"])[0] in DECK_VIEWS
        if "area" in query:
            return (self.out / "data/a" / f"{query['area'][0]}.json").is_file()
        return True

    def test_every_panel_link_resolves(self):
        # Arrange
        paths = ["/school/100001-peer-1/", "/school/140001-good-academy/", "/council/hackney/",
                 "/constituency/hackney-north-and-stoke-newington/", "/trust/good-trust/", "/", "/guides/governors/", "/tools/", "/map/"]
        pages = [self.page(p) for p in paths]
        # Act
        results = self.links(pages)
        # Assert
        for (path, per_reader), page in zip(results, pages):
            for reader, links in per_reader:
                with self.subTest(path=path, reader=reader):
                    self.assertTrue(3 <= len(links) <= 5, links)
                    bad = [link["href"] for link in links if not self.resolves(link["href"], page["sections"])]
                    self.assertEqual(bad, [])
        school_links = dict(results[0][1])
        self.assertIn("/school/100001-peer-1/video/?mode=ptfa", [link["href"] for link in school_links["ptfa"]])
        council_links = dict(results[2][1])
        self.assertIn("/deck/?area=council-204", [link["href"] for link in council_links["governor"]])


if __name__ == "__main__":
    sys.exit(unittest.main())
