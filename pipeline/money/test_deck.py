"""Tests for deck.py (the /deck/ shell page, its IFS context block and deck_links) and the print rules in
assets/deck.css. Everything runs against a fake env in a temporary directory; nothing touches site_money/."""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from pipeline.money import deck, deflator, site

HERE = Path(__file__).resolve().parent
CLEAN = re.compile(r"^/(?:[a-z0-9-]+/)*$")
LIMIT = 48_000
# Built in pieces so a repository-wide search for these phrases finds only real copy.
BANNED = ["poor" + " school", "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", "no " + "pta", "307" + "k"]
CONTEXT = re.compile(r'<script type="application/json" id="deck-context">(.*?)</script>', re.S)

ITEM = {"urn": 130932, "name": "William Patten Primary School", "la": "204", "la_name": "Hackney", "phase": "primary",
        "status": None, "tags": {"governance": "council-run"}, "rows": [], "pta": []}
AREAS = {"england": {"name": "England", "by_year": {}}, "councils": {"204": {"name": "Hackney", "by_year": {}}}}


def fake_env(out, **extra):
    """The env Wave B passes to write_pages: same path rule, one write per path, 48,000-byte limit."""
    written = {}

    def write(path, html):
        if not CLEAN.match(path):
            raise ValueError(f"not a clean path: {path!r}")
        if path in written:
            raise ValueError(f"written twice: {path}")
        size = len(html.encode("utf-8"))
        if size >= LIMIT:
            raise ValueError(f"{path} is {size} bytes")
        target = Path(out) / path.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        written[path] = html

    env = {"out": Path(out), "write": write, "page": site.page, "items": [ITEM], "areas": AREAS, "today": "2026-11-07"}
    env.update(extra)
    return env, written


def ifs():
    with open(HERE / "data" / "ifs_context.json", encoding="utf-8") as fh:
        return json.load(fh)


class WritePagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env, self.written = fake_env(self.tmp.name)
        self.result = deck.write_pages(self.env)
        self.html = (Path(self.tmp.name) / "deck" / "index.html").read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_one_noindex_page(self):
        # Assert
        self.assertEqual(self.result, [("/deck/", False)])
        self.assertEqual(list(self.written), ["/deck/"])

    def test_page_is_noindex_and_under_budget(self):
        # Assert
        self.assertIn('<meta name="robots" content="noindex,follow">', self.html)
        self.assertLess(len(self.html.encode("utf-8")), LIMIT)
        self.assertIn('<link rel="canonical" href="https://money.schoolsinreach.com/deck/">', self.html)

    def test_crumbs_home_then_presentation(self):
        # Assert
        self.assertRegex(self.html, r'<nav class="crumbs"[^>]*><a href="/">Home</a>.*?<span aria-current="page">Presentation</span>')

    def test_noscript_sentence_and_plain_links(self):
        # Act
        noscript = re.search(r"<noscript>(.*?)</noscript>", self.html, re.S).group(1)
        # Assert
        self.assertIn("built here", noscript)
        self.assertIn('href="/search/"', noscript)
        self.assertIn('href="/council/"', noscript)
        self.assertRegex(self.html, r'<div id="deck-app"[^>]*>.*?href="/search/".*?</div>')

    def test_toolbar_and_empty_slide_container(self):
        # Assert
        for action in ("print", "pptx", "copy", "prev", "next", "full"):
            self.assertIn(f'data-deck="{action}"', self.html)
        self.assertIn("Print / save as PDF", self.html)
        self.assertIn("Download PowerPoint", self.html)
        self.assertIn('id="deck-count"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        label = re.search(r'<div id="deck-app"[^>]*data-real-label="([^"]*)"', self.html).group(1)
        self.assertEqual(label, site.esc(deflator.real_label()))

    def test_assets_load_in_head_and_pptxgenjs_does_not(self):
        # Act
        head = self.html.split("</head>")[0]
        # Assert
        self.assertIn('<link rel="stylesheet" href="/assets/deck.css">', head)
        self.assertIn('<script src="/assets/deck.js" defer></script>', head)
        self.assertNotIn("pptxgen", self.html.lower())

    def test_context_json_parses_with_ifs_pages_and_real_label(self):
        # Arrange
        source = ifs()
        # Act
        raw = CONTEXT.search(self.html).group(1)
        ctx = json.loads(raw)
        # Assert
        self.assertNotIn("<", raw)
        self.assertNotIn("&", raw)
        self.assertEqual(ctx["real_label"], deflator.real_label())
        self.assertEqual(ctx["cite"], source["source"]["short_cite"])
        self.assertEqual(ctx["url"], source["source"]["url"])
        why = ctx["framings"]["why_schools_go_into_deficit"]
        self.assertEqual(why["pages"], source["framings"]["why_schools_go_into_deficit"]["pages"])
        self.assertTrue(why["text"])
        self.assertEqual(ctx["questions"]["in_deficit"][1]["page"], source["questions"]["in_deficit"]["questions"][1]["page"])
        self.assertIn("{name}", ctx["placeholders"])
        staff = next(r for r in ctx["context_lines"]["school"] if r["id"] == "staff_share")
        self.assertEqual(staff["page"], 63)
        self.assertIn("Statutory override", ctx["dsg_note"])

    def test_og_image_is_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            env, _ = fake_env(tmp, og_image="https://money.schoolsinreach.com/assets/og.png")
            # Act
            deck.write_pages(env)
            html = (Path(tmp) / "deck" / "index.html").read_text(encoding="utf-8")
        # Assert
        self.assertIn('content="https://money.schoolsinreach.com/assets/og.png"', html)
        self.assertNotIn("og:image", self.html)

    def test_page_copy_has_no_banned_phrase(self):
        # Act
        low = self.html.lower()
        # Assert
        for word in BANNED:
            self.assertNotIn(word, low, word)


class DeckLinksTest(unittest.TestCase):
    def test_three_packs_in_order_with_their_names(self):
        # Act
        html = deck.deck_links("130932")
        links = re.findall(r'<a href="([^"]*)">([^<]*)</a>', html)
        # Assert
        self.assertTrue(html.startswith('<p class="deck-links">') and html.endswith("</p>"))
        self.assertEqual(links, [
            ("/deck/?urn=130932&amp;view=governors", "Governors' finance pack"),
            ("/deck/?urn=130932&amp;view=ptfa", "PTFA pack"),
            ("/deck/?urn=130932&amp;view=review", "School review pack"),
        ])

    def test_escapes_a_hostile_urn(self):
        # Act
        html = deck.deck_links('1"><script>x</script>&')
        # Assert
        hrefs = re.findall(r'href="([^"]*)"', html)
        self.assertNotIn("<script>", html)
        self.assertEqual(len(hrefs), 3)
        for href, view in zip(hrefs, ("governors", "ptfa", "review")):
            self.assertTrue(href.startswith("/deck/?urn=1%22%3E%3Cscript%3E"), href)
            self.assertTrue(href.endswith("&amp;view=" + view), href)
            self.assertNotRegex(href, r"[<>\"]")

    def test_page_names_the_three_packs(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            env, _ = fake_env(tmp)
            # Act
            deck.write_pages(env)
            html = (Path(tmp) / "deck" / "index.html").read_text(encoding="utf-8")
        # Assert
        lead = re.search(r'<p class="lead deck-intro">(.*?)</p>', html, re.S).group(1)
        for name in ("governors&#x27; finance pack", "PTFA pack", "school review pack"):
            self.assertIn(name, lead)


class DeckCssTest(unittest.TestCase):
    def setUp(self):
        self.css = (HERE / "assets" / "deck.css").read_text(encoding="utf-8")
        start = self.css.index("@media print")
        self.print = self.css[start:]

    def test_page_is_landscape_16_by_9_with_no_margin(self):
        # Act
        rule = re.search(r"@page\s*{([^}]*)}", self.print).group(1)
        size = re.search(r"size:\s*([^;]+);", rule).group(1).strip()
        # Assert
        dims = re.findall(r"([\d.]+)in", size)
        landscape = "landscape" in size or (len(dims) == 2 and float(dims[0]) > float(dims[1]))
        self.assertTrue(landscape, size)
        self.assertRegex(rule, r"margin:\s*0\s*;")

    def test_each_slide_is_one_page_and_the_last_ends_cleanly(self):
        # Act
        slide = re.search(r"^\s*\.deck \.slide\s*{([^}]*)}", self.print, re.M).group(1)
        last = re.search(r"\.slide:last-child\s*{([^}]*)}", self.print).group(1)
        # Assert
        self.assertIn("break-after: page", slide)
        self.assertIn("page-break-after: always", slide)
        self.assertIn("break-inside: avoid", slide)
        self.assertIn("print-color-adjust: exact", slide)
        self.assertIn("break-after: auto", last)

    def test_site_chrome_is_hidden_in_print(self):
        # Act
        hidden = next(r for r in re.findall(r"([^{}]+){([^}]*)}", self.print) if "display: none" in r[1])[0]
        # Assert
        for selector in ("header.top", "footer", "nav.crumbs", ".deck-toolbar", ".pinbar"):
            self.assertIn(selector, hidden)

    def test_slides_are_16_by_9_on_screen(self):
        # Assert
        self.assertIn("aspect-ratio: 16 / 9", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_print_page_is_a4_landscape(self):
        # Act
        rule = re.search(r"@page\s*{([^}]*)}", self.print).group(1)
        # Assert
        self.assertRegex(rule, r"size:\s*A4 landscape;")

    def test_each_pack_has_one_accent_on_the_deck_container(self):
        # Act
        screen = self.css[: self.css.index("@media print")]
        accents = {pack: re.search(r"\.deck\.pack-" + pack + r"\s*{([^}]*)}", screen).group(1) for pack in ("governors", "ptfa", "review")}
        # Assert
        for pack, body in accents.items():
            self.assertRegex(body, r"--pack:\s*#[0-9a-f]{6};", pack)
            self.assertIn("--pack-soft:", body)
        colours = {re.search(r"--pack:\s*(#[0-9a-f]{6})", body).group(1) for body in accents.values()}
        self.assertEqual(len(colours), 3, "three different accents")
        self.assertIn('.deck[class*="pack-"] .slide', screen)
        # The packs print in their light colours too.
        for pack in accents:
            self.assertRegex(self.print, r"\.deck\.pack-" + pack + r"\s*{[^}]*--pack:")

    def test_ratings_show_icon_and_word_and_status_colours_keep_their_meaning(self):
        # Assert: one rule per tone, each tied to its status token
        for tone in ("critical", "serious", "warning", "good", "plenty"):
            self.assertRegex(self.css, r"\.rag\.tone-" + tone + r"\s*{[^}]*border-color:\s*var\(--" + tone + r"\)")
            self.assertRegex(self.css, r"\.rag\.tone-" + tone + r" \.rag-icon\s*{\s*color:\s*var\(--" + tone + r"\)")

    def test_editable_fields_look_editable_on_screen_and_print_plain(self):
        # Assert
        self.assertIn(".slide .slide-notes:empty::before", self.css)
        self.assertRegex(self.print, r"\.slide \[contenteditable\]\s*{[^}]*outline:\s*0")
        self.assertRegex(self.print, r"\.slide \.slide-notes:empty, \.action-tools, \.action-bar, \.deck-row-btn\s*{\s*display:\s*none")


class SourceFilesTest(unittest.TestCase):
    FILES = ["deck.py", "assets/deck.js", "assets/deck.css"]

    def test_no_banned_phrase_in_unit_sources(self):
        for name in self.FILES:
            # Act
            text = (HERE / name).read_text(encoding="utf-8").lower()
            # Assert
            for word in BANNED:
                self.assertNotIn(word, text, f"{word!r} in {name}")

    def test_pptxgenjs_pinned_once_with_its_hash(self):
        # Act
        js = (HERE / "assets" / "deck.js").read_text(encoding="utf-8")
        # Assert
        self.assertEqual(js.count("https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js"), 1)
        self.assertRegex(js, r'PPTX_SRI = "sha384-[A-Za-z0-9+/]{64}"')

    def test_deck_never_imports_build_money(self):
        # Act
        src = (HERE / "deck.py").read_text(encoding="utf-8")
        # Assert
        self.assertNotRegex(src, r"import\s+build_money|from\s+pipeline\.money\s+import[^\n]*build_money|pipeline\.money\.build_money")


if __name__ == "__main__":
    sys.exit(unittest.main())
