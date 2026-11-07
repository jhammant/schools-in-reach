"""Offline fixture tests for the area dashboards (area_pages.py). No network; no real data."""
import json
from collections import Counter
from pathlib import Path
import re
import tempfile
import unittest

from pipeline.money import area_pages, areas, build_money, deflator, status
from pipeline.money.site import slug
from pipeline.money.test_areas import make_site, row, school

ROOT = Path(__file__).resolve().parents[2]
GLOSSARY = set(json.loads((ROOT / "pipeline/money/assets/glossary.json").read_text(encoding="utf-8")))
# finance-series adds these to glossary.json; pages may use them before that unit merges.
ADDITIONS = {"other_dfe_grants", "gov_funding_pp", "spend_pp", "gov_vs_spend_gap", "falling_rolls", "pass_through", "high_send",
             "trust_central_spend_pp", "pta_gap", "pta_history", "statutory_override", "deficit_pp", "reserve_median_pp",
             "schools_in_deficit", "ifs_figure"}
ALLOWED = GLOSSARY | ADDITIONS
BANNED = ("poor school", "failing", "worst", "bankrupt", "scandal")
MF_SPAN = re.compile(r'<span class="mf[^"]*"[^>]*?data-mf="([^"]+)"[^>]*>.*?</span>', re.S)
COUNCIL = {"code": "204", "name": "Hackney", "region": "London", "path": "/council/hackney/"}
CFR_ENDS = [f"{y}-03" for y in range(2019, 2027)]          # 2018-19 .. 2025-26
AAR_ENDS = [f"{y}-08" for y in range(2019, 2026)]          # 2018/19 .. 2024/25


def charity(number, name, history, **extra):
    return dict({"charity_number": number, "name": name, "status": "Registered",
                 "history": [{"period_end": e, "income": i, "expenditure": i - 500} for e, i in history],
                 "match": {"method": "postcode", "evidence": "test", "confidence": "high"}}, **extra)


def make_item(urn, name, rows, register, pta=None, trust=None):
    years = status.full_years(rows)
    latest = years[-1] if years else None
    return {"urn": str(urn), "name": name, "school": register, "council": COUNCIL, "path": f"/school/{urn}-{slug(name)}/",
            "rows": rows, "years": years, "latest": latest, "member_of": None, "status": status.assess(rows),
            "pta": [c for c in pta or [] if not c.get("review")], "trust": trust,
            "academy": bool(latest and latest["source"] == "AAR"), "constituency": "Hackney North",
            "constituency_path": "/constituency/hackney-north/"}


def school_rows_for(urn, n, academy, trust=None):
    ends = AAR_ENDS if academy else CFR_ENDS
    out = []
    for k, end in enumerate(ends):
        reserve = -60_000 + 3_000 * k if n % 4 == 0 else 80_000 + 1_000 * n
        extra = {"donations_revenue": 1_000 + 10 * n, "grant_funding_government": 1_700_000, "fsm_pct": 20 + n % 15}
        if academy:
            extra.update(trust=trust, company_number="07000001", trust_central_spend_per_pupil=300 + 10 * k)
        if n % 9 == 0 and k == len(ends) - 1:
            extra["suspect"] = ["total_expenditure"]
        out.append(row(str(urn), end, 1_900_000 + 5_000 * k, 1_910_000 + 5_000 * k, reserve, source="AAR" if academy else "CFR",
                       pupils=300 + n + 2 * k, **extra))
    return out


class Fixture:
    """A 90-school council (eight CFR years), a 90-academy trust (seven AAR years) and the areas doc."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.council_items, self.trust_items, registers, rows_by_urn, pta = [], [], [], {}, {}
        for n in range(90):
            urn, name = 100000 + n, f"Primary {n:03d}"
            reg = school(urn, name, la_code="204", band=1 + n % 5)
            if n % 7 == 0:
                reg["religious_character"] = "Church of England"
            rows = school_rows_for(urn, n, academy=False)
            charities = []
            if n % 3 == 0:
                charities = [charity(1_100_000 + n, f"Friends of {name}", [(f"{y}-07", 8_000 + 100 * n) for y in range(2019, 2026)])]
            elif n == 1:
                charities = [charity(1_200_001, "Old PTA", [("2016-07", 4_000), ("2017-07", 3_000)], removed="2018-02-01")]
            elif n == 2:
                charities = [charity(1_200_002, "Recent PTA", [("2025-07", 60_000)],
                                     match={"method": "llm", "evidence": "test", "confidence": "medium"})]
            pta[str(urn)] = charities
            self.council_items.append(make_item(urn, name, rows, reg, charities))
            registers.append(reg)
            rows_by_urn[str(urn)] = rows
        for n in range(90):
            urn, name = 140000 + n, f"Academy {n:03d}"
            reg = school(urn, name, la_code="204", type="Academy converter", type_group="Academies", trust="Example Trust",
                         band=1 + n % 5, admissions_policy="Selective" if n % 10 == 0 else "Non-selective")
            rows = school_rows_for(urn, n, academy=True, trust="Example Trust")
            charities = [charity(1_300_000 + n, f"Friends of {name}", [(f"{y}-07", 20_000 + 50 * n) for y in range(2019, 2025)])]
            pta[str(urn)] = charities
            self.trust_items.append(make_item(urn, name, rows, reg, charities, trust="Example Trust"))
            registers.append(reg)
            rows_by_urn[str(urn)] = rows
        # A Highgate-style mismatch: flagged for review, so it is never shown or ranked.
        pta["100005"] = [charity(1056624, "Friends of Highgate School Society", [("2024-07", 307_000)],
                                 review="independent school's charity")]
        self.council_items[5]["pta"] = []
        pta["100008"] = [charity(4_000_000, "Very Large Foundation", [("2024-07", 750_000)])]
        self.council_items[8]["pta"] = pta["100008"]
        data = make_site(root, registers)
        self.dsg = json.loads((ROOT / "pipeline/money/data/la_dsg.json").read_text(encoding="utf-8"))
        self.doc = areas.build_areas(rows_by_urn, registers, {"schools": pta}, self.dsg, data,
                                     constituencies_path=root / "missing.json")
        self.items = self.council_items + self.trust_items
        self.ctx = {"ifs": json.loads((ROOT / "pipeline/money/data/ifs_context.json").read_text(encoding="utf-8")),
                    "dsg": self.dsg, "real_label": deflator.real_label(), "areas": self.doc,
                    "paths": {"council": {"204": "/council/hackney/"}, "region": {"London": "/areas/london/"},
                              "constituency": {}, "trust": {"Example Trust": "/trust/example-trust/"}}}

    def pages(self):
        doc, ctx = self.doc, self.ctx
        trust = dict(doc["trusts"]["example-trust"], name="Example Trust", path="/trust/example-trust/")
        return {
            "england": area_pages.render_area("england", "england", doc["england"], self.items, ctx),
            "region": area_pages.render_area("region", "London", doc["regions"]["London"], self.items, ctx),
            "council": area_pages.render_area("council", "204", doc["councils"]["204"], self.items, ctx),
            "constituency": area_pages.render_area("constituency", "Hackney North", doc["constituencies"]["Hackney North"],
                                                   self.items, ctx),
            "league": area_pages.render_council_league({"204": dict(doc["councils"]["204"], code="204", name="Hackney",
                                                                    path="/council/hackney/", region="London")}, ctx),
            "trust": area_pages.render_trust(trust, self.trust_items, ctx),
            "trusts": area_pages.render_trust_index(doc["trusts"], ctx),
            "debts": area_pages.render_debts(doc, ctx),
            "ptfa": area_pages.render_ptfa(doc, self.items, ctx),
        }


def html_of(result):
    """Page 1 as build_money lays it out: intro, filters, the sortable table, outro."""
    table = result["table"]
    body = table.get("filters") or "" if table else ""
    if table:
        body += build_money.sortable(table["headers"], table["rows"])
    return result["intro"] + body + result["outro"]


def visible(html):
    html = re.sub(r"<svg.*?</svg>", "", html, flags=re.S)
    return re.sub(r"<script.*?</script>", "", html, flags=re.S)


class AreaPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = Fixture()
        cls.pages = cls.fx.pages()

    @classmethod
    def tearDownClass(cls):
        cls.fx.tmp.cleanup()

    def test_every_renderer_returns_the_contract_keys(self):
        for name, result in self.pages.items():
            with self.subTest(page=name):
                # Assert
                self.assertEqual(set(result), {"title", "description", "intro", "table", "outro", "indexable"})
                self.assertNotIn("<", result["title"] + result["description"])
                self.assertTrue(result["title"].endswith(" | School Money") and len(result["title"]) <= 70, result["title"])
                self.assertLessEqual(len(result["description"]), 160)
                self.assertTrue(result["intro"].startswith("<h1>"), result["intro"][:40])
                self.assertIsInstance(result["indexable"], bool)
                table = result["table"]
                self.assertIsNotNone(table)
                self.assertTrue({"headers", "rows", "caption"} <= set(table))
                self.assertTrue(all("<" not in h for h in table["headers"] + [table["caption"]]))
                self.assertTrue(all(len(r) == len(table["headers"]) for r in table["rows"]))

    def test_school_tables_carry_the_table_dom_markers(self):
        # Arrange
        table = self.pages["council"]["table"]
        # Assert
        first = table["rows"][0][0]
        tags = re.search(r'<span data-tags="([^"]+)">', first).group(1).split()
        self.assertEqual([t.split(":")[0] for t in tags], ["governance", "phase", "admissions", "faith"])
        self.assertRegex(first, r'<a href="/school/\d+-[a-z0-9-]+/" data-preview="school:\d+">')
        self.assertEqual(table["headers"][:2], ["School", "Status"])
        self.assertIn("PTA per pupil", table["headers"])
        for cells in table["rows"]:
            for cell in cells[1:8]:
                self.assertTrue(cell.startswith("<span data-sort="), cell[:60])
        filters = table["filters"]
        self.assertIn('<div class="table-filters" data-filters>', filters)
        self.assertIn('data-filter="governance:academy" aria-pressed="false"', filters)
        self.assertIn('data-filter="governance:council-run" aria-pressed="false"', filters)
        self.assertIn('data-filter="faith:church-of-england"', filters)
        self.assertIn('data-filter="admissions:grammar"', filters)
        self.assertNotIn("data-filter", self.pages["league"]["intro"])

    def test_governance_tag_follows_the_latest_return(self):
        # Arrange: register says academy, but the only returns are council-run (CFR).
        item = dict(self.fx.council_items[3], school=dict(self.fx.council_items[3]["school"], type="Academy converter"))
        # Act
        tags, _ = area_pages.item_tags(item)
        # Assert
        self.assertIn("governance:council-run", tags.split())

    def test_each_school_is_one_row_named_once(self):
        for page, items in (("council", self.fx.items), ("trust", self.fx.trust_items)):
            with self.subTest(page=page):
                rows = self.pages[page]["table"]["rows"]
                urns = [re.search(r'data-preview="school:(\d+)"', r[0]).group(1) for r in rows]
                # Assert
                self.assertEqual(Counter(urns), Counter(i["urn"] for i in items))
                names = {i["urn"]: i["name"] for i in items}
                for urn, cells in zip(urns, rows):
                    self.assertEqual("".join(cells).count(names[urn]), 1, urn)

    def test_size_limits(self):
        for name, result in self.pages.items():
            with self.subTest(page=name):
                # Assert
                text = len(result["intro"].encode("utf-8")) + len(result["outro"].encode("utf-8"))
                self.assertLessEqual(text, 22_000)
                if name in ("council", "constituency", "trust"):
                    biggest = max(sum(len(c.encode("utf-8")) for c in r) for r in result["table"]["rows"])
                    self.assertLessEqual(biggest, 2_500)
        self.assertEqual(len(self.pages["council"]["table"]["rows"]), 180)
        self.assertEqual(len(self.pages["trust"]["table"]["rows"]), 90)

    def test_no_rendered_copy_uses_banned_words(self):
        for name, result in self.pages.items():
            with self.subTest(page=name):
                # Assert
                text = (result["title"] + result["description"] + html_of(result)).lower()
                for word in BANNED:
                    self.assertNotIn(word, text)
                self.assertNotIn("no pta", text)

    def test_every_pound_sits_in_an_allowed_money_figure(self):
        checked = 0
        for name, result in self.pages.items():
            with self.subTest(page=name):
                text = visible(html_of(result))
                # Assert
                for key in MF_SPAN.findall(text):
                    self.assertIn(key, ALLOWED)
                    checked += 1
                bare = MF_SPAN.sub("", text)
                self.assertNotIn("£", bare, bare[max(bare.find("£") - 120, 0):bare.find("£") + 60])
                for attrs in re.findall(r'<span class="mf[^"]*"([^>]*)>', text):
                    self.assertRegex(attrs, r'data-v="-?[0-9.]*"')
        self.assertGreater(checked, 500)

    def test_ifs_figures_keep_their_text_and_context(self):
        # Arrange
        council, trust, debts = (html_of(self.pages[k]) for k in ("council", "trust", "debts"))
        # Assert: IFS amounts keep their exact text in an ifs_figure span in 2025-26 prices.
        for value, text in (("7000", "£7,000"), ("7800", "£7,800")):
            self.assertIn(f'<span class="mf" data-mf="ifs_figure" data-v="{value}" data-year="2025-26">{text}</span>', council)
        self.assertIn('<span class="mf" data-mf="ifs_figure" data-v="510" data-year="2025-26">£510</span>', trust)
        self.assertIn("2023-24", trust)
        for page, html in self.pages.items():
            whole = html_of(html)
            self.assertNotIn("£8,400", whole, page)
            for m in re.finditer(r"£14 billion", whole):
                self.assertIn("High Needs Stability Grant", whole[m.end():m.end() + 900], page)
        self.assertIn("£14 billion", debts)
        self.assertIn("statutory override", debts.lower())

    def test_sector_year_and_comparability_notes(self):
        for name in ("england", "region", "council", "constituency"):
            with self.subTest(page=name):
                html = html_of(self.pages[name])
                # Assert
                self.assertIn("not strictly comparable", html)
                self.assertIn("April to March", html)
                self.assertIn("September to August", html)
                self.assertIn("council-run schools only", html)
                self.assertIn("2024-25", html)

    def test_trend_dom_markers(self):
        # Arrange
        intro = self.pages["council"]["intro"]
        # Assert
        self.assertIn('class="trend', intro)
        self.assertIn('data-basis-toggle="cash" aria-pressed="true"', intro)
        self.assertIn('data-basis-toggle="real" aria-pressed="false"', intro)
        self.assertRegex(intro, r"""<g data-basis=["']real["'][^>]*display=["']none["']""")
        self.assertRegex(intro, r"""<g data-basis=["']cash["']""")
        self.assertIn('data-unit-toggle="pp"', intro)
        self.assertRegex(intro, r'data-unit="total" hidden')
        for svg in re.findall(r"<svg[^>]*trend[^>]*>.*?</svg>", intro, flags=re.S):
            self.assertIn('role="img"', svg)
            self.assertIn("<title>", svg)
            self.assertIn("<desc>", svg)

    def test_fallback_charts_follow_the_contract(self):
        # Act
        svg = area_pages.fallback_trend([{"label": "A", "values": {"2019-20": 1, "2020-21": None, "2021-22": 3}, "basis": "cash"},
                                         {"label": "B", "values": {"2019-20": 2, "2021-22": 2}, "basis": "real", "style": "dashed"}],
                                        years=["2019-20", "2020-21", "2021-22"], title="T", desc="D", suspect=("2021-22",),
                                        partial=("2021-22",))
        spark = area_pages.fallback_sparkline([(f"20{y}", y * 10 - 150) for y in range(18, 26)], label="Reserve per pupil")
        # Assert
        self.assertIn('role="img"><title>T</title><desc>D</desc>', svg)
        self.assertIn('<g data-basis="real" display="none">', svg)
        self.assertIn('class="hollow"', svg)
        self.assertIn('>A</text>', svg)
        self.assertLessEqual(len(spark.encode("utf-8")), 400)
        self.assertIn('role="img" aria-label="Reserve per pupil"', spark)

    def test_pta_cells_use_the_return_year_and_its_pupils(self):
        # Arrange: £12,000 to March 2023 with 100 pupils that year; 300 pupils by 2024-25.
        rows = [row("100500", "2023-03", 600_000, 590_000, 50_000, pupils=100),
                row("100500", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=300)]
        item = make_item(100500, "Example Primary", rows, school(100500, "Example Primary"),
                         [charity(1234567, "Example PTA", [("2023-03", 12_000)])])
        # Act
        cells, _ = area_pages.school_cells(item)
        # Assert
        income = re.search(r'<span class="mf" data-mf="pta_income"[^>]*>', cells[5]).group(0)
        self.assertIn('data-v="12000"', income)
        self.assertIn('data-pp="120"', income)
        self.assertIn('data-year="2022-23"', income)

    def test_pta_wording(self):
        # Arrange
        council = self.pages["council"]
        cells = {re.search(r'school:(\d+)', r[0]).group(1): r for r in council["table"]["rows"]}
        ptfa = html_of(self.pages["ptfa"])
        # Assert
        self.assertIn("No registered parents&#x27; association found", cells["100004"][5])
        self.assertIn("Had a registered PTA until 2018", cells["100001"][5])
        self.assertIn("matched with lower confidence", cells["100002"][5])
        self.assertIn("Held for review", cells["100008"][5])
        self.assertIn("No registered parents&#x27; association found", cells["100005"][5])
        self.assertIn("need not register", council["intro"])
        self.assertIn('data-mf="pta_income" data-v="5000">£5,000</span>', council["intro"])
        self.assertIn("never added together", ptfa)
        self.assertIn("need not register", ptfa)
        self.assertIn("matched with lower confidence", ptfa)
        self.assertNotIn("Highgate", ptfa)
        self.assertNotIn("1056624", ptfa)
        self.assertIn("Very Large Foundation", ptfa)          # held for review, by name only
        self.assertNotIn("school:100008", ptfa)

    def test_ptfa_ranks_from_the_areas_doc(self):
        # Arrange
        pta = self.fx.doc["pta"]
        intro = self.pages["ptfa"]["intro"]
        # Assert
        self.assertTrue(pta["top"])
        self.assertIn(f'school:{pta["top"][0]["urn"]}', intro)
        self.assertIn("The gap by intake", intro)
        self.assertIn("Grammar", intro)
        self.assertEqual(len(self.pages["ptfa"]["table"]["rows"]), 1)

    def test_debts_lists_dsg_flags_and_council_context(self):
        # Arrange
        debts = self.pages["debts"]
        row_html = "".join(debts["table"]["rows"][0])
        # Assert
        self.assertIn("Delivering better value", row_html)       # Hackney is in la_dsg.json's DBV list
        self.assertIn('data-mf="dsg_balance"', row_html)
        self.assertIn("High Needs Stability Grant", debts["intro"])
        council_lines = [line["text"][:40] for line in self.fx.ctx["ifs"]["context_lines"]["council"]
                         if line.get("use_when") == "always"]
        for start in council_lines:
            self.assertIn(start.split("£")[0].replace("'", "&#x27;")[:25], debts["intro"])
        self.assertTrue(any("Council-run deficits" in h for h in debts["table"]["headers"]))
        self.assertTrue(any("Academy deficits" in h for h in debts["table"]["headers"]))

    def test_headline_tiles(self):
        # Act
        html = area_pages.headline(self.fx.doc["councils"]["204"])
        # Assert
        self.assertTrue(html.startswith('<div class="tiles headline">'))
        self.assertIn("Schools in deficit, 2024-25", html)
        self.assertIn("Council-run schools in deficit, 2025-26", html)
        self.assertIn('data-mf="dsg_balance"', html)
        self.assertEqual(area_pages.headline({}), "")

    def test_renderers_survive_a_thin_context(self):
        # Arrange: no areas doc, no deflator caption, no IFS pack, no DSG file.
        ctx = {"ifs": {}, "dsg": None, "real_label": None, "areas": None, "paths": None}
        area = self.fx.doc["councils"]["204"]
        # Act
        results = [area_pages.render_area("council", "204", area, self.fx.council_items, ctx),
                   area_pages.render_area("england", "england", {}, [], ctx),
                   area_pages.render_council_league({}, ctx), area_pages.render_trust({}, [], ctx),
                   area_pages.render_trust_index({}, ctx), area_pages.render_debts({}, ctx),
                   area_pages.render_ptfa({}, [], ctx)]
        # Assert
        for result in results:
            self.assertEqual(set(result), {"title", "description", "intro", "table", "outro", "indexable"})
            self.assertNotIn("data-basis-toggle", result["intro"])
            self.assertNotIn('data-basis="real"', result["intro"])
        self.assertIsNotNone(results[0]["table"])
        self.assertFalse(results[1]["indexable"])
        self.assertIn("High Needs Stability Grant", area_pages.hnsg_note(None))


if __name__ == "__main__":
    unittest.main()
