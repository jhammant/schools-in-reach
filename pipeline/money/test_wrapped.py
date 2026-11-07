"""Offline tests for the 30-second videos (pipeline/money/wrapped.py): the /video/ shell, the per-school stubs,
context.json, headline() and wrapped_links(). Fixtures are built here; the reference school comes from the
committed gold file pipeline/money/data/gold/130932.json."""
import json
import re
import tempfile
import time
import unittest
from html.parser import HTMLParser
from pathlib import Path

from pipeline.money import deflator, site, status as health, wrapped

REPO = Path(__file__).resolve().parents[2]
GOLD = json.loads((REPO / "pipeline/money/data/gold/130932.json").read_text(encoding="utf-8"))
CLEAN = re.compile(r"^/(?:[a-z0-9-]+/)*$")
# Built from fragments so this file never contains the phrases it guards against.
BANNED = [" ".join(["poor", "school"]), "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", " ".join(["no", "PTA"]), "30" + "7k"]
LONG_NAME = ('St Mary & St John\'s "Federated" Church of England Voluntary Aided Primary School & Nursery '
             'with Children\'s Centre, Hackney')[:120].ljust(120, "x")


def gold_rows():
    """Finance rows in build_model's shape, one per gold CFR year."""
    rows = []
    for year, block in sorted(GOLD["years"].items()):
        f = block["totals"]["pipeline_finance_history"]
        rows.append({"year": year, "period_end": f"20{year[-2:]}-03-31", "period_months": 12, "source": "CFR", "phase": "primary",
                     "total_income": f["total_income"], "total_expenditure": f["total_expenditure"],
                     "in_year_balance": f["in_year_balance"], "revenue_reserve": f["revenue_reserve"],
                     "grant_funding": f["grant_funding"], "pupils": f["pupils"]})
    return rows


def gold_item(**over):
    rows = gold_rows()
    item = {"urn": GOLD["urn"], "name": GOLD["name"], "path": "/school/130932-william-patten-primary-school/",
            "council": {"code": "204", "name": "Hackney"}, "school": {"lat": 51.56, "lon": -0.07}, "rows": rows,
            "status": health.assess(rows), "phase": "primary", "academy": False, "pta": []}
    item.update(over)
    return item


def plain_item(urn, name, status_value="healthy", pupils=300.0):
    return {"urn": urn, "name": name, "council": {"code": "204", "name": "Hackney"}, "rows": [], "status": status_value, "pupils": pupils}


class FakeEnv:
    """The env B0 passes to write_pages, writing into a temp dir with the core's checks. to_disk=False keeps
    pages in memory (same checks), so the speed test times write_pages rather than the shared disk."""

    def __init__(self, tmp, items, og_image=None, to_disk=True):
        self.out = Path(tmp)
        self.to_disk = to_disk
        self.pages = {}
        self.env = {"out": self.out, "write": self.write, "page": site.page, "items": items,
                    "areas": {"england": {"name": "England"}, "councils": {}}, "today": "2026-11-07"}
        if og_image:
            self.env["og_image"] = og_image

    def write(self, path, html):
        if not CLEAN.match(path):
            raise ValueError(f"unclean path {path!r}")
        if path in self.pages:
            raise ValueError(f"written twice: {path}")
        if len(html.encode("utf-8")) >= 48_000:
            raise ValueError(f"too big: {path}")
        self.pages[path] = html
        if not self.to_disk:
            return
        target = self.out / path.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")


class Head(HTMLParser):
    """Collects <title>, <meta>, <link rel=canonical>, scripts, <main> attributes and noscript links."""

    def __init__(self):
        super().__init__()
        self.meta, self.links, self.scripts, self.main, self.title = {}, [], [], {}, ""
        self._in_title = self._in_noscript = False
        self.noscript_links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and ("name" in a or "property" in a):
            self.meta[a.get("name") or a.get("property")] = a.get("content")
        elif tag == "link":
            self.links.append(a)
        elif tag == "script" and a.get("src"):
            self.scripts.append(a)
        elif tag == "main":
            self.main = a
        elif tag == "noscript":
            self._in_noscript = True
        elif tag == "a" and self._in_noscript:
            self.noscript_links.append(a.get("href"))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "noscript":
            self._in_noscript = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def parse(html):
    p = Head()
    p.feed(html)
    return p


class WritePagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.items = [gold_item(), plain_item("100001", "No Return Primary", status_value=None),
                      plain_item("100002", LONG_NAME, status_value="tight"), plain_item("100003", "Plain Key School", status_value="healthy")]
        self.fake = FakeEnv(self.tmp.name, self.items)

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_every_page_in_write_order_hub_indexable_stubs_noindex(self):
        # Act
        result = wrapped.write_pages(self.fake.env)
        # Assert: the Videos hub is a page people should find; each school's stub is a share target only
        self.assertEqual(result[0], ("/video/", True))
        self.assertEqual([p for p, _ in result], list(self.fake.pages))
        self.assertTrue(all(flag is False for _, flag in result[1:]))
        self.assertEqual(len(result), 4)

    def test_videos_hub_has_the_app_and_a_search_that_goes_to_the_video(self):
        # Act
        wrapped.write_pages(self.fake.env)
        html = self.fake.pages["/video/"]
        head = parse(html)
        # Assert
        self.assertNotEqual(head.meta.get("robots"), "noindex,follow")
        self.assertIn('id="wrapped-app"', html)
        self.assertIn('data-mode="school"', html)
        self.assertIn(f'data-real-label="{site.esc(deflator.real_label())}"', html)
        self.assertIn("Your school in 30 seconds", html)
        self.assertIn('action="/search/"', html)
        self.assertIn('data-go="video/"', html)  # app.js sends a school pick straight to its video
        self.assertIn('<span aria-current="page">Videos</span>', html)
        self.assertNotIn("Wrapped", html)
        self.assertIn('<a href="/">Home</a>', html)
        self.assertTrue(any(s["src"] == "/assets/wrapped.js" for s in head.scripts))
        self.assertIn("<noscript>", html)

    def test_stubs_only_for_schools_with_a_status(self):
        # Act
        result = dict(wrapped.write_pages(self.fake.env))
        # Assert
        self.assertIn("/school/130932-william-patten-primary-school/video/", result)
        self.assertIn(site.page_path("school", "100003", "Plain Key School") + "video/", result)
        self.assertFalse(any("100001" in p for p in result))
        self.assertTrue((self.fake.out / "school/130932-william-patten-primary-school/video/index.html").exists())

    def test_every_stub_is_small_noindex_canonical_and_shareable(self):
        # Act
        result = wrapped.write_pages(self.fake.env)
        # Assert
        stubs = [p for p, _ in result if p != "/video/"]
        self.assertEqual(len(stubs), 3)
        for item in (i for i in self.items if wrapped.school_view(i)["status"]):
            view = wrapped.school_view(item)
            path = view["path"] + "video/"
            html = self.fake.pages[path]
            head = parse(html)
            self.assertLessEqual(len(html.encode("utf-8")), wrapped.STUB_LIMIT, path)
            self.assertNotIn('class="top"', html, "the stub is hand-built, not env['page']")
            self.assertEqual(head.title, f"{item['name']} in 30 seconds")
            self.assertEqual(head.meta["robots"], "noindex,follow")
            self.assertEqual(head.meta["description"], wrapped.headline(item))
            self.assertEqual(head.meta["og:title"], f"{item['name']} in 30 seconds")
            self.assertEqual(head.meta["og:description"], wrapped.headline(item))
            self.assertIn(item["name"], head.meta["og:description"])
            self.assertEqual(head.meta["og:url"], site.BASE_MONEY + path)
            self.assertEqual(head.meta["og:type"], "website")
            self.assertEqual(head.meta["og:site_name"], site.SITE_NAME)
            self.assertEqual(head.meta["twitter:card"], "summary")
            self.assertNotIn("og:image", head.meta)
            canon = [l["href"] for l in head.links if l.get("rel") == "canonical"]
            self.assertEqual(canon, [site.BASE_MONEY + view["path"]])
            self.assertEqual([s["src"] for s in head.scripts], ["/assets/wrapped.js"])
            self.assertIn("defer", head.scripts[0])
            sheets = [l["href"] for l in head.links if l.get("rel") == "stylesheet"]
            self.assertEqual(sheets, ["/assets/app.css", "/assets/wrapped.css"])
            self.assertEqual(head.main.get("id"), "wrapped-app")
            self.assertEqual(head.main.get("data-urn"), view["urn"])
            self.assertEqual(head.main.get("data-mode"), "school")
            self.assertEqual(head.main.get("data-name"), item["name"])
            self.assertEqual(head.main.get("data-path"), view["path"])
            self.assertEqual(head.noscript_links, [view["path"]])

    def test_long_name_with_ampersand_and_quotes_stays_under_the_limit(self):
        # Arrange
        item = plain_item("100002", LONG_NAME, status_value="tight")
        # Act
        html = wrapped.stub_html(item, og_image="https://money.schoolsinreach.com/assets/og.png")
        # Assert
        self.assertEqual(len(LONG_NAME), 120)
        self.assertLessEqual(len(html.encode("utf-8")), 3072)
        self.assertIn("&amp;", html)
        self.assertIn("&quot;", html)
        self.assertNotIn('"Federated"', html)
        self.assertEqual(parse(html).meta["og:title"], f"{LONG_NAME} in 30 seconds")

    def test_og_image_only_when_the_env_has_one(self):
        # Arrange
        fake = FakeEnv(self.tmp.name + "/og", [gold_item()], og_image="https://money.schoolsinreach.com/assets/og.png")
        # Act
        wrapped.write_pages(fake.env)
        # Assert
        head = parse(fake.pages["/school/130932-william-patten-primary-school/video/"])
        self.assertEqual(head.meta["og:image"], "https://money.schoolsinreach.com/assets/og.png")

    def test_context_json_parses_with_ifs_page_numbers(self):
        # Act
        wrapped.write_pages(self.fake.env)
        raw = (self.fake.out / "data/wrapped/context.json").read_text(encoding="utf-8")
        ctx = json.loads(raw)
        # Assert
        self.assertNotIn("\n", raw)
        self.assertNotIn('": ', raw)
        self.assertEqual(ctx["real_label"], deflator.real_label())
        self.assertEqual(ctx["base_url"], site.BASE_MONEY)
        self.assertTrue(ctx["ifs"]["cite"].startswith("IFS"))
        self.assertTrue(ctx["ifs"]["url"].startswith("https://ifs.org.uk/"))
        self.assertIn("over 80%", ctx["staff"]["line"]["text"])
        self.assertEqual(ctx["staff"]["line"]["page"], 63)
        self.assertEqual(ctx["staff"]["framing"]["pages"], [62, 63])
        self.assertEqual(set(ctx["what_helps"]), set(health.ORDER))
        for key, block in ctx["what_helps"].items():
            self.assertTrue(block["text"].startswith("What helps:"), key)
            self.assertTrue(block["framing"]["pages"], key)
            self.assertTrue(block["questions"], key)
        self.assertTrue(ctx["national_lines"])
        self.assertTrue(all(isinstance(l["page"], int) for l in ctx["national_lines"]))
        override = [l for l in ctx["council_lines"] if l["id"] == "high_needs_deficits"][0]
        self.assertIn("statutory override", override["text"])
        self.assertEqual(override["page"], 61)
        self.assertIn("£5,000", ctx["pta"]["register_note"])
        self.assertEqual(ctx["pta"]["not_found"], "No registered parents' association found")
        self.assertEqual(ctx["generated"], "2026-11-07")


class HeadlineTest(unittest.TestCase):
    def test_gold_school_headline(self):
        # Act
        line = wrapped.headline(gold_item())
        # Assert
        self.assertEqual(line, "William Patten Primary School: 432.5 pupils and £8,297 government funding per pupil in 2025-26 (DfE)")
        latest = GOLD["years"]["2025-26"]["totals"]["pipeline_finance_history"]
        self.assertIn(f"£{round(latest['grant_funding'] / latest['pupils']):,}", line)

    def test_never_leads_with_a_deficit(self):
        # Act
        line = wrapped.headline(gold_item())
        # Assert
        self.assertEqual(wrapped.school_view(gold_item())["status"]["key"], "in_deficit")
        self.assertNotIn("deficit", line.lower())
        self.assertNotIn("-£", line)

    def test_falls_back_to_pupils_then_name(self):
        # Arrange
        rows = gold_rows()
        rows[-1] = dict(rows[-1], grant_funding=None)
        no_grant = gold_item(rows=rows)
        pupils_only = plain_item("100009", "Small Rural School", status_value={"status": "healthy", "year": "2024-25"}, pupils=48.25)
        bare = plain_item("100010", "Brand New Free School", pupils=None)
        # Act / Assert
        self.assertEqual(wrapped.headline(no_grant), "William Patten Primary School: 432.5 pupils in 2025-26 (DfE)")
        self.assertEqual(wrapped.headline(pupils_only), "Small Rural School: 48.3 pupils in 2024-25 (DfE)")
        self.assertEqual(wrapped.headline(bare), "Brand New Free School: its year in money, from published figures")

    def test_fmt_pupils_rounds_to_one_place(self):
        self.assertEqual(wrapped.fmt_pupils(432.5), "432.5")
        self.assertEqual(wrapped.fmt_pupils(435), "435")
        self.assertEqual(wrapped.fmt_pupils(1204.46), "1,204.5")


class AccessorTest(unittest.TestCase):
    def test_school_view_reads_every_contract_shape(self):
        # Arrange
        item = {"urn": 130932, "name": "A & B School", "council": {"code": "204", "name": "Hackney"}, "school": {"lat": 51.5, "lon": -0.1},
                "academy": True, "status": "nonsense", "pta": [{"name": "Keep"}, {"name": "Drop", "review": "low"}]}
        # Act
        view = wrapped.school_view(item)
        # Assert
        self.assertEqual(view["urn"], "130932")
        self.assertEqual(view["path"], "/school/130932-a-and-b-school/")
        self.assertEqual((view["la"], view["la_name"]), ("204", "Hackney"))
        self.assertEqual(view["governance"], "academy")
        self.assertEqual((view["lat"], view["lon"]), (51.5, -0.1))
        self.assertIsNone(view["status"])
        self.assertEqual([c["name"] for c in view["pta"]], ["Keep"])
        self.assertEqual(wrapped.school_view(dict(item, status="tight"))["status"]["label"], "Tight")
        self.assertEqual(wrapped.school_view(dict(item, tags={"governance": "free school"}))["governance"], "free school")


class LinksTest(unittest.TestCase):
    def test_wrapped_links_escape_and_link_both_modes(self):
        # Arrange
        item = plain_item("100004", 'Tom & Jerry\'s "Best" <School>')
        # Act
        html = wrapped.wrapped_links(item)
        # Assert
        stub = site.page_path("school", "100004", item["name"]) + "video/"
        self.assertIn(f'href="{stub}"', html)
        self.assertIn(f'href="{stub}?mode=ptfa"', html)
        self.assertIn("in 30 seconds", html)
        self.assertNotIn("Wrapped", html)
        self.assertIn("Tom &amp; Jerry&#x27;s &quot;Best&quot; &lt;School&gt;", html)
        self.assertNotIn("<School>", html)

    def test_watch_button_names_what_you_get(self):
        # Arrange
        item = plain_item("100004", "Plain Key School")
        stub = site.page_path("school", "100004", item["name"]) + "video/"
        # Act
        school, ptfa = wrapped.watch_button(item), wrapped.watch_button(item, "ptfa")
        # Assert
        self.assertIn(f'href="{stub}"', school)
        self.assertIn("Watch in 30 seconds", school)
        self.assertIn(f'href="{stub}?mode=ptfa"', ptfa)
        self.assertIn("PTFA in 30 seconds", ptfa)


class CopyTest(unittest.TestCase):
    def test_no_banned_words_in_sources_or_written_pages(self):
        # Arrange
        texts = {name: (REPO / "pipeline/money" / name).read_text(encoding="utf-8")
                 for name in ("wrapped.py", "assets/wrapped.js", "assets/wrapped.css")}
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeEnv(tmp, [gold_item(), plain_item("100002", LONG_NAME, status_value="tight")])
            # Act
            wrapped.write_pages(fake.env)
            texts.update(fake.pages)
            texts["context.json"] = (Path(tmp) / "data/wrapped/context.json").read_text(encoding="utf-8")
        texts["links"] = wrapped.wrapped_links(gold_item())
        texts["headline"] = wrapped.headline(gold_item())
        # Assert
        for name, text in texts.items():
            for word in BANNED:
                self.assertNotIn(word.lower(), text.lower(), f"{word!r} in {name}")


class SpeedTest(unittest.TestCase):
    def test_two_thousand_schools_in_under_ten_seconds(self):
        # Arrange
        rows = gold_rows()
        state = health.assess(rows)
        items = [{"urn": str(200000 + i), "name": f"Fake School {i} & Nursery", "council": {"code": "204", "name": "Hackney"},
                  "rows": rows, "status": state} for i in range(2000)]
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeEnv(tmp, items, to_disk=False)
            # Act
            started = time.perf_counter()
            result = wrapped.write_pages(fake.env)
            took = time.perf_counter() - started
        # Assert
        self.assertEqual(len(result), 2001)
        self.assertEqual(len(fake.pages), 2001)
        self.assertTrue(all(len(h.encode("utf-8")) <= wrapped.STUB_LIMIT for p, h in fake.pages.items() if p != "/video/"))
        self.assertLess(took, 10.0)


if __name__ == "__main__":
    unittest.main()
