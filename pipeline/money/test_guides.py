"""Offline tests for the guides, the tool pages and the embeddable badges (pipeline/money/guides.py)."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from pipeline.money import guides, site
from pipeline.money import status as health

REPO = Path(__file__).resolve().parents[2]
MONEY = REPO / "pipeline/money"
GOLD = MONEY / "data/gold/130932.json"
CLEAN_PATH = re.compile(r"^/(?:[a-z0-9-]+/)*$")
PAGE_LIMIT = 48_000
SLUGS = ["falling-rolls", "governors", "parents", "ptfa", "pupils", "school-leaders", "send-and-high-needs"]
TOOLS = ["/tools/budget-check/", "/tools/pta-planner/", "/tools/embed/"]
# Spelled in pieces so this file never trips a site-wide scan for the same words.
BANNED = ["po" + "or school", "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", "no " + "pta", "307" + "k"]
LONG_NAME = ("The Very Long Named Church of England & Roman Catholic Joint Voluntary Aided "
             "Primary School and Nursery, St Mary's \"Upper\" Site")[:120]


def fake_env(out: Path, items):
    """The env the core hands to write_pages: same path rule, write-once and size limit as the real writer."""
    seen = set()

    def write(path, html):
        if not CLEAN_PATH.match(path):
            raise ValueError(f"not a clean path: {path!r}")
        if path in seen:
            raise ValueError(f"written twice: {path}")
        if len(html.encode("utf-8")) >= PAGE_LIMIT:
            raise ValueError(f"{path} is {len(html.encode('utf-8'))} bytes")
        seen.add(path)
        target = out / path.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")

    return {"out": out, "write": write, "page": site.page, "items": items,
            "areas": {"england": {"name": "England"}, "councils": {}}, "today": "2026-11-07"}


def gold_rows():
    """The reference school's finance rows, built from the committed gold file."""
    data = json.loads(GOLD.read_text(encoding="utf-8"))
    rows = []
    for year, block in sorted(data["years"].items()):
        fin = block["totals"]["pipeline_finance_history"]
        rows.append({"year": year, "period_end": f"{int(year[:4]) + 1}-03-31", "period_months": 12, "source": "CFR", "phase": "primary",
                     **{k: fin[k] for k in ("total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "grant_funding", "pupils")}})
    return data, rows


def make_items():
    data, rows = gold_rows()
    gold = {"urn": data["urn"], "name": data["name"], "la": "204", "la_name": "Hackney", "phase": "primary",
            "status": health.assess(rows), "rows": rows, "pta": []}
    long_rows = [dict(r, total_income=2_000_000, revenue_reserve=168_000, pupils=210) for r in rows[-1:]]
    long = {"urn": 100001, "name": LONG_NAME, "council": {"code": "204", "name": "Hackney"}, "status": health.assess(long_rows), "rows": long_rows}
    plain = {"urn": "100002", "name": "Plain Status School", "status": "healthy", "rows": []}
    none = {"urn": "100003", "name": "No Status School", "status": None, "rows": []}
    return [gold, long, plain, none]


def read(out: Path, path: str) -> str:
    return (out / path.strip("/") / "index.html").read_text(encoding="utf-8")


class FrontMatterTest(unittest.TestCase):
    def test_parses_keys_and_sources(self):
        # Arrange
        text = ("---\ntitle: A: guide\ndescription: Short.\naudience: parents\nslug: x\nlast_reviewed: 2026-11-07\nsources:\n"
                "- One | https://www.gov.uk/a | p. 3\n- Two | https://ifs.org.uk/b | detail | with bar\n---\n\n## Body\n")
        # Act
        meta, body = guides.parse_front_matter(text)
        # Assert
        self.assertEqual(meta["title"], "A: guide")
        self.assertEqual(meta["last_reviewed"], "2026-11-07")
        self.assertEqual(meta["sources"][0], {"title": "One", "url": "https://www.gov.uk/a", "detail": "p. 3"})
        self.assertEqual(meta["sources"][1]["detail"], "detail | with bar")
        self.assertEqual(body, "## Body\n")

    def test_malformed_blocks_raise(self):
        # Arrange
        bad = ["no front matter", "---\ntitle: x\n", "---\nnot a pair\n---\n", "---\nsources:\n- only | two\n---\n", "---\nsources: inline\n---\n"]
        for text in bad:
            # Act / Assert
            with self.assertRaises(ValueError, msg=text):
                guides.parse_front_matter(text)


class MarkdownTest(unittest.TestCase):
    def test_escapes_everything(self):
        # Act
        html = guides.render_markdown('A <script>alert("x")</script> & **<b>bold</b>**\n')
        # Assert
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp;", html)
        self.assertIn("<strong>&lt;b&gt;bold&lt;/b&gt;</strong>", html)

    def test_links_allow_https_and_site_paths_only(self):
        # Act
        html = guides.render_markdown("[gov](https://www.gov.uk/x?a=1&b=2) and [here](/guides/ptfa/#gift-aid)\n")
        # Assert
        self.assertIn('<a href="https://www.gov.uk/x?a=1&amp;b=2">gov</a>', html)
        self.assertIn('<a href="/guides/ptfa/#gift-aid">here</a>', html)
        for url in ("javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x", "//evil.example/", "/\\evil.example", "mailto:a@b.c"):
            with self.assertRaises(ValueError, msg=url):
                guides.render_markdown(f"[x]({url})\n")

    def test_lists_headings_and_notes(self):
        # Arrange
        text = "## Money & you\n\n### Detail\n\n- one\n- two\n  more\n\n1. first\n2. second\n\n> A note\n> continues\n\nPara\n"
        # Act
        html = guides.render_markdown(text)
        # Assert
        self.assertIn('<h2 id="money-and-you">Money &amp; you</h2>', html)
        self.assertIn('<h3 id="detail">Detail</h3>', html)
        self.assertIn("<ul><li>one</li><li>two more</li></ul>", html)
        self.assertIn("<ol><li>first</li><li>second</li></ol>", html)
        self.assertIn('<div class="note" role="note"><p>A note continues</p></div>', html)
        self.assertIn("<p>Para</p>", html)

    def test_other_heading_levels_raise(self):
        # Act / Assert
        for text in ("# Title\n", "#### Deep\n"):
            with self.assertRaises(ValueError):
                guides.render_markdown(text)


class PlaceholderTest(unittest.TestCase):
    def setUp(self):
        self.ifs, self.dsg = guides.load_ifs(), guides.load_dsg()

    def test_ifs_framing_comes_with_its_pages(self):
        # Act
        text = guides.expand_placeholders("{{ifs:framings.why_schools_go_into_deficit}}", self.ifs, self.dsg)
        # Assert
        self.assertTrue(text.startswith(self.ifs["framings"]["why_schools_go_into_deficit"]["text"]))
        self.assertTrue(text.endswith("(IFS 2026 report, pp. 62–63)"))

    def test_dsg_note_is_the_statutory_override_note(self):
        # Act
        text = guides.expand_placeholders("{{ dsg:override_note }}", self.ifs, self.dsg)
        # Assert
        self.assertTrue(text.startswith("Statutory override"))
        self.assertIn("High Needs Stability Grant", text)
        self.assertIn(text, self.dsg["source"]["notes"])

    def test_unknown_or_unclosed_placeholders_raise(self):
        # Act / Assert
        for text in ("{{ifs:framings.nope}}", "{{dsg:other}}", "{{anything}}", "{{ifs:framings.real_terms"):
            with self.assertRaises(ValueError, msg=text):
                guides.expand_placeholders(text, self.ifs, self.dsg)

    def test_pages_label(self):
        # Act / Assert
        self.assertEqual(guides.pages_label([82]), "p. 82")
        self.assertEqual(guides.pages_label([63, 62]), "pp. 62–63")
        self.assertEqual(guides.pages_label([46, 58, 61, 63]), "pp. 46, 58, 61, 63")


class GuideFilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guides = {g["slug"]: g for g in guides.load_guides()}
        cls.dsg = guides.load_dsg()

    def test_every_guide_is_present_and_complete(self):
        # Assert
        self.assertEqual(sorted(self.guides), SLUGS)
        for slug, g in self.guides.items():
            self.assertTrue(g["title"] and g["description"], slug)
            self.assertEqual(g["last_reviewed"], "2026-11-07", slug)
            self.assertTrue(any(s["url"].startswith("https://") for s in g["sources"]), slug)
            self.assertTrue(all(s["title"] and s["detail"] for s in g["sources"]), slug)

    def test_guides_cite_official_pages_only(self):
        # Arrange
        official = ("https://ifs.org.uk/", "https://www.gov.uk/", "https://www.legislation.gov.uk/", "https://financial-benchmarking-and-insights-tool.education.gov.uk/",
                    "https://register-of-charities.charitycommission.gov.uk/", "https://explore-education-statistics.service.gov.uk/")
        # Act
        urls = [s["url"] for g in self.guides.values() for s in g["sources"]]
        urls += [u for g in self.guides.values() for u in re.findall(r'href="(https?://[^"]+)"', g["html"])]
        # Assert
        self.assertEqual([u for u in urls if not u.startswith(official)], [])

    def test_ifs_citing_guides_show_page_numbers(self):
        # Arrange
        citing = [g for g in self.guides.values() if any("ifs.org.uk" in s["url"] for s in g["sources"])]
        # Assert
        self.assertGreaterEqual(len(citing), 6)
        for g in citing:
            ifs_source = next(s for s in g["sources"] if "ifs.org.uk" in s["url"])
            self.assertRegex(ifs_source["detail"], r"pp?\. \d", g["slug"])
            self.assertRegex(g["html"], r"IFS 2026 report, pp?\. \d", g["slug"])

    def test_framings_named_in_the_brief_are_used(self):
        # Assert
        self.assertIn("{{ifs:framings.one_deficit_year}}", (MONEY / "data/guides/parents.md").read_text(encoding="utf-8"))
        self.assertIn("{{ifs:framings.send_pressure}}", (MONEY / "data/guides/send-and-high-needs.md").read_text(encoding="utf-8"))
        self.assertIn("{{ifs:framings.falling_rolls}}", (MONEY / "data/guides/falling-rolls.md").read_text(encoding="utf-8"))

    def test_send_guide_contains_the_dsg_override_note(self):
        # Arrange
        note = guides.dsg_override_note(self.dsg)
        # Assert
        self.assertIn(site.esc(note), self.guides["send-and-high-needs"]["html"])
        self.assertIn("High Needs Stability Grant", self.guides["send-and-high-needs"]["html"])

    def test_ptfa_guide_covers_registration_gift_aid_and_the_overlap(self):
        # Arrange
        html = self.guides["ptfa"]["html"]
        # Assert
        self.assertIn("£5,000", html)
        self.assertIn("Gift Aid", html)
        self.assertIn("25p for every £1", html)
        self.assertIn("small donations scheme", html)
        self.assertIn("raffle", html)
        self.assertIn("No registered parents&#x27; association found", html)
        self.assertIn("Never add the two together", html)
        self.assertIn("never adds them up", html)

    def test_pupils_guide_keeps_sentences_short(self):
        # Arrange
        body = re.sub(r"\([^)]*\)", "", self.guides["pupils"]["body"])
        # Act
        sentences = [s for s in re.split(r"[.!?]\s", body) if s.strip()]
        # Assert
        self.assertLessEqual(max(len(s.split()) for s in sentences), 25)


class WritePagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.items = make_items()
        cls.written = guides.write_pages(fake_env(cls.out, cls.items))
        cls.gold, _ = gold_rows()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_writes_every_page_in_order_with_indexability(self):
        # Arrange
        expected = (["/guides/"] + [f"/guides/{s}/" for s in SLUGS] + ["/tools/"] + TOOLS
                    + ["/embed/130932/", "/embed/100001/", "/embed/100002/"])
        # Assert
        self.assertEqual([p for p, _ in self.written], expected)
        self.assertTrue(all(flag for p, flag in self.written if not p.startswith("/embed/")))
        self.assertFalse(any(flag for p, flag in self.written if p.startswith("/embed/")))
        self.assertFalse((self.out / "embed/100003").exists())
        for path, _ in self.written:
            self.assertTrue((self.out / path.strip("/") / "index.html").exists(), path)

    def test_every_page_is_under_the_size_limit_and_uses_the_shell(self):
        for path, indexable in self.written:
            html = read(self.out, path)
            self.assertLess(len(html.encode("utf-8")), PAGE_LIMIT, path)
            if indexable:
                self.assertIn('<link rel="stylesheet" href="/assets/guides.css">', html, path)
                self.assertIn('<nav class="crumbs"', html, path)
                self.assertNotIn('name="robots"', html, path)

    def test_index_groups_guides_by_audience(self):
        # Act
        html = read(self.out, "/guides/")
        # Assert
        for heading in ("For parents and carers", "For governors", "For PTFA and PTA committees", "For school leaders", "For pupils", "For everyone"):
            self.assertIn(heading, html)
        for slug in SLUGS:
            self.assertIn(f'href="/guides/{slug}/"', html)
        self.assertLess(html.index("For parents and carers"), html.index("For everyone"))

    def test_guide_pages_have_article_lead_sources_and_review_date(self):
        for g in guides.load_guides():
            # Act
            html = read(self.out, g["path"])
            # Assert
            self.assertIn(f"<h1>{site.esc(g['title'])}</h1>", html)
            self.assertIn(f'<p class="lead">{site.esc(g["description"])}</p>', html)
            self.assertIn('<h2 id="guide-sources">Sources</h2>', html)
            for source in g["sources"]:
                self.assertIn(f'<a href="{site.esc(source["url"])}" rel="noopener">{site.esc(source["title"])}</a>, {site.esc(source["detail"])}', html)
            self.assertIn("Last reviewed <time datetime=\"2026-11-07\">7 November 2026</time>", html)

    def test_tool_pages_explain_themselves_and_work_without_js(self):
        for path in TOOLS:
            # Act
            html = read(self.out, path)
            context = json.loads(re.search(r'<script type="application/json" id="tools-context">(.*?)</script>', html).group(1))
            # Assert
            self.assertIn("Nothing is sent anywhere.", html, path)
            self.assertRegex(html, r'<noscript><p class="note">[^<]*<a href="https://financial-benchmarking-and-insights-tool\.education\.gov\.uk/"', path)
            self.assertIn('<script src="/assets/tools.js" defer></script>', html, path)
            self.assertIn(f'data-tool="{path.split("/")[2]}" hidden', html, path)
            self.assertIn("pp. 62–63", context["ifs"]["framings"]["why_schools_go_into_deficit"]["pages"])
        self.assertIn('id="bc-out" aria-live="polite"', read(self.out, "/tools/budget-check/"))
        self.assertIn('<label for="pp-gift">', read(self.out, "/tools/pta-planner/"))
        self.assertIn('<textarea id="em-code"', read(self.out, "/tools/embed/"))

    def test_embed_badge_for_the_reference_school(self):
        # Arrange
        latest = self.gold["years"]["2025-26"]["totals"]["pipeline_finance_history"]
        per_pupil = guides._exact(latest["revenue_reserve"] / latest["pupils"])
        # Act
        html = read(self.out, "/embed/130932/")
        # Assert
        self.assertLessEqual(len(html.encode("utf-8")), 2048)
        self.assertIn('<meta name="robots" content="noindex">', html)
        self.assertIn('<span class="badge s-in_deficit"><span aria-hidden="true">▼</span> In deficit</span>', html)
        self.assertIn(f"<b>{per_pupil}</b> reserve per pupil", html)
        self.assertIn(f"{guides._exact(latest['revenue_reserve'])} in total · 2025-26, DfE CFR return", html)
        self.assertIn('href="https://money.schoolsinreach.com/school/130932-william-patten-primary-school/" target="_blank" rel="noopener"', html)
        self.assertIn('<span class="n">William Patten Primary School</span><span class="s"> on School Money</span>', html)
        self.assertNotIn("<script", html)
        self.assertIn('href="/assets/app.css"', html)
        self.assertIn('href="/assets/guides.css"', html)

    def test_embed_for_a_long_name_stays_small_and_escaped(self):
        # Act
        html = read(self.out, "/embed/100001/")
        # Assert
        self.assertEqual(len(LONG_NAME), 120)
        self.assertLessEqual(len(html.encode("utf-8")), 2048)
        self.assertIn(site.esc(LONG_NAME), html)
        self.assertIn('<span aria-hidden="true">▲</span> Large reserves', html)
        self.assertIn(f"<b>{guides._exact(168_000 / 210)}</b> reserve per pupil", html)

    def test_embed_with_a_plain_status_string(self):
        # Act
        html = read(self.out, "/embed/100002/")
        # Assert
        self.assertIn('<span aria-hidden="true">✓</span> Healthy', html)
        self.assertIn("Figures are on the school's page.", html)
        self.assertIn('href="https://money.schoolsinreach.com/school/100002-plain-status-school/"', html)

    def test_no_banned_words_in_pages_or_sources(self):
        # Arrange
        texts = {path: read(self.out, path) for path, _ in self.written}
        for file in [MONEY / "guides.py", MONEY / "assets/tools.js", MONEY / "assets/guides.css", *sorted((MONEY / "data/guides").glob("*.md"))]:
            texts[str(file.relative_to(REPO))] = file.read_text(encoding="utf-8")
        # Act
        hits = [(name, word) for name, text in texts.items() for word in BANNED if word in text.lower()]
        # Assert
        self.assertEqual(hits, [])


class SchoolViewTest(unittest.TestCase):
    def test_reads_status_shapes_and_falls_back_for_path_and_pupils(self):
        # Arrange
        _, rows = gold_rows()
        item = {"urn": 130932, "name": "William Patten Primary School", "status": health.assess(rows), "rows": rows}
        # Act
        view = guides.school_view(item)
        # Assert
        self.assertEqual(view["urn"], "130932")
        self.assertEqual(view["path"], site.page_path("school", "130932", "William Patten Primary School"))
        self.assertEqual(view["pupils"], rows[-1]["pupils"])
        self.assertEqual(view["status"]["reserve"], rows[-1]["revenue_reserve"])
        self.assertIsNone(guides.school_view({"urn": 1, "name": "x", "status": "not-a-status"})["status"])
        self.assertEqual(guides.school_view({"urn": 1, "name": "x", "status": "tight", "path": "/school/1-x/"})["path"], "/school/1-x/")


if __name__ == "__main__":
    unittest.main()
