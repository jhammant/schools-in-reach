"""Tests for the school page (pipeline/money/school_page.py).

SERIES and ctx dicts are built by hand from the shared contracts, so these tests run before the
series module (B1) and the builder (B0) land. The William Patten test reads the committed gold file.
"""

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from pipeline.money import deflator, school_page, site, status as health

try:
    from pipeline.money import series as series_module
except ImportError:  # B1's module, not present in every checkout
    series_module = None

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "pipeline/money/data/gold/130932.json"
IFS = json.loads((ROOT / "pipeline/money/data/ifs_context.json").read_text(encoding="utf-8"))
FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk"
ADDED_KEYS = {"other_dfe_grants", "gov_funding_pp", "spend_pp", "gov_vs_spend_gap", "falling_rolls", "pass_through", "high_send",
              "trust_central_spend_pp", "pta_gap", "pta_history", "statutory_override", "deficit_pp", "reserve_median_pp",
              "schools_in_deficit", "ifs_figure"}
ALLOWED_KEYS = set(json.loads((ROOT / "pipeline/money/assets/glossary.json").read_text(encoding="utf-8"))) | ADDED_KEYS
BANNED = ("poor school", "failing", "worst", "bankrupt", "scandal", "no pta", "pension grant")
CFR8 = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
SHARES = {"grant_funding_government": 0.9, "sen_funding": 0.04, "pupil_premium": 0.03, "self_generated_income": 0.06,
          "donations_revenue": 0.004, "donations_capital": 0.001, "facilities_income": 0.01, "catering_income": 0.02,
          "other_dfe_grants": 0.05, "teaching_staff": 0.45, "supply_staff": 0.02, "education_support_staff": 0.2,
          "admin_clerical_staff": 0.05, "premises_staff": 0.02, "catering_staff": 0.02, "other_staff_costs": 0.02,
          "total_staff": 0.8, "premises": 0.05, "energy": 0.02, "occupation": 0.04, "catering": 0.03,
          "educational_supplies": 0.03, "supplies_services": 0.06, "bought_in_services": 0.02}


# ----------------------------------------------------------------- fixtures

def cell(v, pupils, year, source, real=True):
    """One SERIES cell: cash, per pupil, real and real per pupil, each rounded to £1."""
    out = {"v": round(v)}
    if pupils:
        out["pp"] = round(v / pupils)
    if real:
        r = deflator.to_real(v, year, source)
        out["r"] = round(r)
        if pupils:
            out["rpp"] = round(r / pupils)
    return out


def make_series(values, pupils, source, *, real=True, flags=None, pta=None, trust_central=None, suspect=None):
    """A SERIES dict per the shared contract. values = {metric: {year: cash £}}."""
    years = sorted(pupils)
    m = {k: {y: cell(v, pupils.get(y), y, source[y], real) for y, v in by_year.items() if v is not None}
         for k, by_year in values.items()}
    gap = {}
    for y in years:
        g, s = m.get("grant_funding_government", {}).get(y, {}), m.get("total_expenditure", {}).get(y, {})
        gap[y] = {k: v for k, v in (("gov_pp", g.get("pp")), ("spend_pp", s.get("pp")),
                                    ("gov_rpp", g.get("rpp")), ("spend_rpp", s.get("rpp"))) if v is not None}
    f = {"falling_rolls": None, "pass_through": None, "high_send": None, "suspect": suspect or {}, "not_reported": {}}
    f.update(flags or {})
    return {"years": years, "source": dict(source), "pupils": dict(pupils), "m": m, "gap": gap, "pta": pta or {},
            "flags": f, "trust_central_pp": trust_central or {}}


def school_values(years, pupils, *, income_pp=6000, growth=0.03, reserve_pp=300, skip=()):
    """Every SERIES metric for each year, from a per-pupil income growing by `growth` a year."""
    values = {}
    for i, y in enumerate(years):
        income = income_pp * (1 + growth) ** i * pupils[y]
        spend = income * 0.99
        row = {"total_income": income, "total_expenditure": spend, "in_year_balance": income - spend,
               "revenue_reserve": reserve_pp * pupils[y]}
        row.update({k: income * share for k, share in SHARES.items()})
        for k, v in row.items():
            if k not in skip:
                values.setdefault(k, {})[y] = v
    return values


def charity(number=1103834, name="Example PTA", history=(), **extra):
    c = {"charity_number": number, "name": name, "status": "Registered", "registered": "2004-05-19", "removed": None,
         "latest_income": history[-1]["income"] if history else None, "history": list(history),
         "match": {"method": "postcode", "evidence": "tokens example", "confidence": "high"}}
    c.update(extra)
    return c


def returns(*pairs):
    return [{"period_end": pe, "income": inc, "expenditure": exp} for pe, inc, exp in pairs]


def make_item(urn="100001", name="Example Primary", *, academy=False, phase="primary", pta=None, status="healthy",
              reserve=150_000, year="2025-26", streak=0, similar=()):
    st = {"status": status, "label": health.LABELS[status], "rank": health.ORDER.index(status),
          "reason": f"Holds £{reserve / 1000:.0f}k in reserve, 5% of a year's income." if reserve >= 0
          else f"In deficit by £{-reserve / 1000:.0f}k, 4% of a year's income: it has spent more over the years than it received.",
          "year": year.replace("-", "/") if academy else year, "source": "AAR" if academy else "CFR", "reserve": reserve,
          "reserve_share": 0.05, "deficit_streak": streak, "runway_years": None, "pupils_change": None, "years": 2,
          "trust_share_included": False}
    council = {"code": "204", "name": "Hackney", "region": "London", "path": "/council/hackney/"}
    return {"urn": urn, "name": name, "council": council,
            "school": {"type": "Academy converter" if academy else "Community school", "phase": phase.title(), "postcode": "E8 1AA",
                       "trust": "Example Trust" if academy else None},
            "path": f"/school/{urn}-{site.slug(name)}/", "site_path": f"/school/{urn}-{site.slug(name)}/",
            "rows": [], "years": [], "latest": {}, "member_of": None, "status": st, "phase": phase, "london": True, "fsm": 20,
            "pta": list(pta or []), "trust": "Example Trust" if academy else None,
            "trust_path": "/trust/example-trust/" if academy else None, "academy": academy,
            "constituency": "Hackney North", "constituency_path": "/constituency/hackney-north/", "similar": list(similar)}


def make_ctx(item, series, **over):
    ctx = {"series": series, "profile": None,
           "timeline": [{"year": y, "status": "healthy", "label": "Healthy", "reserve": 1, "reserve_pp": 1, "pupils": 1}
                        for y in series["years"]],
           "similar": {"total_income": 6100, "total_expenditure": 6000, "teaching_staff": 2700},
           "similar_series": {"total_expenditure": {y: 5900 + 50 * i for i, y in enumerate(series["years"])},
                              "revenue_reserve": {y: 280 for y in series["years"]}},
           "council": None, "england": None, "pta_national": None, "ifs": IFS, "real_label": deflator.real_label(),
           "check_url": f"{FBIT}/school/{item['urn']}", "sir_url": f"https://www.schoolsinreach.com{item['site_path']}"}
    ctx.update(over)
    return ctx


def cfr_school(**item_kw):
    """A council-run primary with 8 CFR years and one current PTA."""
    pupils = {y: 430 - 2 * i for i, y in enumerate(CFR8)}
    series = make_series(school_values(CFR8, pupils), pupils, {y: "CFR" for y in CFR8})
    pta = item_kw.pop("pta", [charity(history=returns(("2023-08", 15_951, 9_339), ("2024-08", 30_000, 28_000), ("2025-08", 48_547, 50_100)),
                                      parta={"count_volunteers": 100, "ar_due_date": "2026-06-30"})])
    item = make_item(pta=pta, **item_kw)
    return item, make_ctx(item, series)


def aar_academy(pta=None, **item_kw):
    """A 2-year academy: trust central spend per pupil, and pupil premium not reported."""
    years = ["2023-24", "2024-25"]
    pupils = {"2023-24": 300, "2024-25": 300}
    series = make_series(school_values(years, pupils, skip=("pupil_premium",)), pupils, {y: "AAR" for y in years},
                         flags={"not_reported": {"pupil_premium": "not reported in academy accounts"}},
                         trust_central={"2023-24": 480, "2024-25": 495})
    if pta is None:
        pta = [charity(history=returns(("2024-08", 9_000, 8_000)))]
    item = make_item(urn="140001", name="Example Academy", academy=True, pta=pta, year="2024-25", **item_kw)
    return item, make_ctx(item, series)


def big_school():
    """8 years, 3 PTAs with 21-year histories and 39 similar schools (the large size budget)."""
    similar = [{"urn": str(110000 + n), "name": f"Similar Primary School Number {n}", "path": f"/school/{110000 + n}-similar/"}
               for n in range(39)]
    ptas = [charity(number=1100000 + n, name=f"Friends of Example Primary {n}",
                    history=returns(*[(f"{2005 + y}-08", 20_000 + 500 * y, 19_000 + 400 * y) for y in range(21)]),
                    parta={"count_volunteers": 40, "ar_due_date": "2026-06-30"}) for n in range(3)]
    item, ctx = cfr_school(pta=ptas, similar=similar)
    ctx["similar"] = {k: 1000 + 37 * n for n, (k, _, group) in enumerate(school_page.METRICS) if group != "balance"}
    ctx["similar_series"] = {k: {y: 900 + 11 * i for i, y in enumerate(CFR8)}
                             for k in ("total_income", "total_expenditure", "grant_funding_government", "revenue_reserve")}
    ctx["pta_national"] = {"by_year": {"2024-25": {"ptas": 9000, "schools": 9400, "income": 1e8, "spend": 9e7, "median_pp": 31}}}
    return item, ctx


class Figures(HTMLParser):
    """Money-figure attributes, £ signs outside money figures (ignoring svg/script), and tag balance."""

    VOID = {"br", "img", "input", "meta", "link", "hr", "path", "circle", "line", "rect", "source", "wbr"}

    def __init__(self, html):
        super().__init__()
        self.figures, self.stray, self.stack, self.errors, self.ids, self.hidden = [], [], [], [], [], []
        self.mf_depth = self.skip_depth = 0
        self.feed(html)
        if self.stack:
            self.errors.append(f"unclosed {self.stack}")

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.VOID:
            return
        self.stack.append((tag, "mf" in (a.get("class") or "").split() and "data-mf" in a, tag in ("svg", "script")))
        if self.stack[-1][1]:
            self.mf_depth += 1
            self.figures.append(a)
        if self.stack[-1][2]:
            self.skip_depth += 1
        if a.get("id"):
            self.ids.append(a["id"])
        if "hidden" in a:
            self.hidden.append(a)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            self.errors.append(f"unexpected </{tag}> with {self.stack[-3:]}")
            return
        _, mf, skip = self.stack.pop()
        self.mf_depth -= mf
        self.skip_depth -= skip

    def handle_data(self, data):
        if "£" in data and not self.mf_depth and not self.skip_depth:
            self.stray.append(data.strip())


def figures(body, key=None, year=None):
    return [f for f in Figures(body).figures if (key is None or f["data-mf"] == key) and (year is None or f.get("data-year") == year)]


def every_fixture():
    def with_flag(builder, **flags):
        item, ctx = builder()
        ctx["series"]["flags"].update(flags)
        return item, ctx

    out = {"cfr": cfr_school(), "aar": aar_academy(), "big": big_school(),
           "deficit": cfr_school(status="in_deficit", reserve=-40_000, streak=2),
           "falling": with_flag(cfr_school, falling_rolls={"from": 430.0, "to": 416.0, "change": -0.0326}),
           "pass_through": with_flag(cfr_school, pass_through={"year": "2025-26", "income_rise": 180_000, "staff_rise": 150_000}),
           "high_send": with_flag(cfr_school, high_send={"ehcp_pct": 7.1, "sen_share": None, "reason": "ehcp"}),
           "no_pta": cfr_school(pta=[]),
           "historical": cfr_school(pta=[charity(history=returns(("2014-08", 9_000, 8_000), ("2016-08", 7_000, 7_500)))]),
           "shared": cfr_school(pta=[charity(history=returns(("2024-08", 30_000, 27_000)), shared_with=["100002", "100003"])]),
           "llm": cfr_school(pta=[charity(history=returns(("2024-08", 12_000, 11_000)),
                                          match={"method": "llm", "evidence": "model", "confidence": "medium"})]),
           "secondary": cfr_school(phase="secondary", status="tight", reserve=20_000)}
    return out


# ----------------------------------------------------------------- tests

class RequiredMarkersTest(unittest.TestCase):
    def test_every_year_has_income_spending_and_reserve_figures_with_the_source(self):
        for name, (item, ctx) in (("cfr", cfr_school()), ("aar", aar_academy())):
            with self.subTest(name):
                # Arrange
                series = ctx["series"]

                # Act
                body = school_page.render(item, ctx)["body"]

                # Assert
                for y in series["years"]:
                    for key in ("total_income", "total_expenditure", "revenue_reserve"):
                        found = figures(body, key, y)
                        cell_ = series["m"][key][y]
                        self.assertTrue(any(f.get("data-src") == ctx["check_url"] and f["data-v"] == str(cell_["v"])
                                            and f.get("data-pp") == str(cell_["pp"]) for f in found), (key, y, found))

    def test_pta_figures_use_the_pta_year_and_that_years_pupils(self):
        # Arrange: £12,000 to March 2023 when the school had 100 pupils; 300 pupils later.
        years = ["2022-23", "2024-25"]
        pupils = {"2022-23": 100, "2024-25": 300}
        series = make_series(school_values(years, pupils), pupils, {y: "CFR" for y in years})
        item = make_item(pta=[charity(history=returns(("2023-03", 12_000, 9_000), ("2025-03", 30_000, 29_000)))], year="2024-25")
        ctx = make_ctx(item, series)

        # Act
        body = school_page.render(item, ctx)["body"]
        old = [f for f in figures(body, "pta_income") if f["data-v"] == "12000"]

        # Assert
        self.assertTrue(old)
        self.assertTrue(all(f["data-pp"] == "120" and f["data-year"] == "2022-23" for f in old), old)
        self.assertTrue(all(f["data-year"] in ("2022-23", "2024-25") for f in figures(body, "pta_income")))

    def test_pta_rows_name_the_charitys_own_year_end(self):
        # Arrange: a council-run school; the association's year to August 2025 sits in 2025-26 (April to March)
        item, ctx = cfr_school()

        # Act
        body = school_page.render(item, ctx)["body"]

        # Assert
        self.assertIn('2025-26<br><small class="muted">year to August 2025</small>', body)
        self.assertIn('2024-25<br><small class="muted">year to August 2024</small>', body)

    def test_pta_year_rule_for_academies_and_council_run_schools(self):
        # Act / Assert
        self.assertEqual(school_page.pta_year("2023-03", "CFR"), "2022-23")
        self.assertEqual(school_page.pta_year("2025-08", "CFR"), "2025-26")
        self.assertEqual(school_page.pta_year("2025-08", "AAR"), "2024-25")

    def test_series_pta_figures_are_used_when_the_series_has_them(self):
        # Arrange: the series says 2024-25's share is £4,000 with 200 pupils.
        item, ctx = aar_academy()
        ctx["series"]["pupils"]["2024-25"] = 200
        ctx["series"]["pta"] = {"2024-25": {"income": 4_000, "spend": 3_000, "income_pp": 20, "spend_pp": 15,
                                            "charity_number": 1103834, "confidence": "high"}}

        # Act
        body = school_page.render(item, ctx)["body"]

        # Assert
        income = [f for f in figures(body, "pta_income") if f["data-v"] == "4000"]
        self.assertTrue(income and all(f["data-pp"] == "20" and f["data-year"] == "2024-25" for f in income), income)
        self.assertTrue(any(f["data-v"] == "3000" and f["data-pp"] == "15" for f in figures(body, "pta_spending")))


class TrendMarkupTest(unittest.TestCase):
    def setUp(self):
        item, ctx = cfr_school()
        self.body = school_page.render(item, ctx)["body"]
        section = self.body[self.body.index('id="funding"'):]
        self.funding = section[:section.index("</section>")]

    def test_toggles_and_default_visibility(self):
        # Assert
        self.assertIn('class="trend"', self.funding)
        for attr in ('data-basis-toggle="cash" aria-pressed="true"', 'data-basis-toggle="real" aria-pressed="false"',
                     'data-unit-toggle="pp" aria-pressed="true"', 'data-unit-toggle="total" aria-pressed="false"'):
            self.assertIn(attr, self.funding)
        self.assertIn('<div data-unit="pp">', self.funding)
        self.assertIn('<div data-unit="total" hidden>', self.funding)

    def test_real_groups_are_hidden_and_cash_groups_show(self):
        # Assert
        self.assertEqual(self.funding.count('data-basis="real" display="none"'), self.funding.count('data-basis="real"'))
        self.assertGreaterEqual(self.funding.count('data-basis="real"'), 2)
        self.assertNotRegex(self.funding, r'data-basis="cash"[^>]*display')
        self.assertIn('role="img"', self.funding)
        self.assertRegex(self.funding, r"<svg[^>]*role=\"img\"[^>]*><title>[^<]+</title><desc>[^<]+</desc>")

    def test_caveats_and_real_terms_caption(self):
        # Assert
        self.assertIn("not strictly comparable", self.funding)
        self.assertIn("I07", self.funding)
        self.assertIn(deflator.real_label(), self.funding)

    def test_both_sources_get_the_financial_and_academic_year_note(self):
        # Arrange: a converter with CFR years before AAR ones.
        years = ["2022-23", "2023-24", "2024-25"]
        pupils = {y: 300 for y in years}
        source = {"2022-23": "CFR", "2023-24": "AAR", "2024-25": "AAR"}
        item = make_item(academy=True, year="2024-25")
        ctx = make_ctx(item, make_series(school_values(years, pupils), pupils, source))

        # Act
        body = school_page.render(item, ctx)["body"]

        # Assert
        self.assertIn("CFR years run April to March and AAR years September to August", body)

    def test_no_real_toggles_without_a_deflator_caption(self):
        # Arrange
        item, ctx = cfr_school()
        ctx["real_label"] = None

        # Act
        body = school_page.render(item, ctx)["body"]

        # Assert
        self.assertNotIn("data-basis-toggle", body)
        self.assertNotIn('data-basis="real"', body)
        self.assertIn('data-unit-toggle="total"', body)


class FallbackChartTest(unittest.TestCase):
    def test_trend_fallback_follows_the_chart_contract(self):
        # Arrange
        years = ["2021-22", "2022-23", "2023-24", "2024-25"]
        lines = [{"label": "Funding", "values": {"2021-22": 5000, "2022-23": None, "2023-24": 5400, "2024-25": 5600},
                  "style": "solid", "emph": True, "basis": "cash"},
                 {"label": "Funding", "values": {y: 6000 for y in years}, "style": "dashed", "emph": False, "basis": "real"},
                 {"label": "Similar", "values": {y: 5200 for y in years}, "style": "dashed", "emph": False, "basis": None}]

        # Act
        svg = school_page._trend_fallback(lines, years=years, title="T", desc="D", suspect=("2023-24",), partial=("2024-25",))

        # Assert
        self.assertRegex(svg, r'^<svg[^>]*role="img"><title>T</title><desc>D</desc>')
        self.assertIn('<g data-basis="cash">', svg)
        self.assertIn('<g data-basis="real" display="none">', svg)
        self.assertIn("<g><path", svg)
        self.assertIn("hollow", svg)
        self.assertIn("dashed", svg)
        self.assertEqual(svg.count(">Funding</text>"), 2)
        self.assertEqual(svg.count(">Similar</text>"), 1)
        cash = svg[svg.index('<g data-basis="cash">'):svg.index("</g>")]
        paths = re.findall(r'<path class="([^"]*)" d="([^"]*)"', cash)
        # Only 2023-24 -> 2024-25 is joined (dashed, into the partial year); the None in 2022-23 leaves a gap.
        self.assertEqual(sum(d.count("L") for _, d in paths), 1, paths)
        self.assertTrue(all("dashed" in cls for cls, d in paths if "L" in d), paths)

    def test_sparkline_fallback_is_small_and_labelled(self):
        # Arrange
        values = [(f"20{10 + n}-{11 + n}", 4000 + 37.3 * n) for n in range(8)]

        # Act
        svg = school_page._spark_fallback(values, label="Teachers per pupil, 2010-11 to 2017-18")

        # Assert
        self.assertLessEqual(len(svg.encode("utf-8")), 400)
        self.assertIn('role="img"', svg)
        self.assertIn('aria-label="Teachers per pupil, 2010-11 to 2017-18"', svg)


class ReadingOrderTest(unittest.TestCase):
    def test_sections_read_in_order_without_javascript(self):
        # Arrange
        item, ctx = cfr_school()
        ctx["series"]["flags"]["pass_through"] = {"year": "2025-26", "income_rise": 180_000, "staff_rise": 150_000}
        ctx["profile"] = {"tags": {"governance": "Council-run", "phase": "Primary", "gender": "Mixed"},
                          "intake": {"fsm_pct": 20.0, "fsm_pct_council": 30.0, "fsm_pct_england": 25.0},
                          "area": {"imd_decile": 3}, "band": 3}

        # Act
        page = Figures(school_page.render(item, ctx)["body"])

        # Assert
        order = ["status", "funding", "reserve", "income", "spending", "pupils", "pass-through", "ptfa", "intake",
                 "split", "context", "questions", "check"]
        sections = [i for i in page.ids if i in order]
        self.assertEqual(sections, order)
        self.assertIn("20% of pupils eligible for free school meals (median school: council 30%, England 25%)",
                      school_page.render(item, ctx)["body"])
        self.assertEqual([h.get("data-unit") for h in page.hidden], ["total"], "only the total-unit charts start hidden")
        self.assertFalse(page.errors, page.errors)

    def test_academy_sections_include_trust_central_spend(self):
        # Arrange
        item, ctx = aar_academy()

        # Act
        page = Figures(school_page.render(item, ctx)["body"])

        # Assert
        self.assertLess(page.ids.index("pupils"), page.ids.index("trust-central"))
        self.assertLess(page.ids.index("trust-central"), page.ids.index("ptfa"))
        self.assertFalse(page.errors, page.errors)


class CopyRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {name: school_page.render(item, ctx) for name, (item, ctx) in every_fixture().items()}

    def test_every_pound_sits_in_an_allowed_money_figure(self):
        for name, page in self.pages.items():
            with self.subTest(name):
                # Act
                parsed = Figures(page["body"])

                # Assert
                self.assertFalse(parsed.stray, parsed.stray[:5])
                self.assertFalse(parsed.errors, parsed.errors)
                keys = {f["data-mf"] for f in parsed.figures}
                self.assertLessEqual(keys, ALLOWED_KEYS, keys - ALLOWED_KEYS)

    def test_banned_and_misleading_words_never_appear(self):
        for name, page in self.pages.items():
            with self.subTest(name):
                # Act
                text = " ".join((page["title"], page["description"], page["body"])).lower()

                # Assert
                for word in BANNED:
                    self.assertNotIn(word, text)

    def test_ifs_comparators_are_7000_and_7800_never_8400(self):
        for name, value in (("cfr", "7000"), ("secondary", "7800")):
            with self.subTest(name):
                # Act: the comparator sits under "Where it goes".
                body = self.pages[name]["body"]
                spending = body[body.index('id="spending"'):]
                spending = spending[:spending.index("</section>")]
                ifs = [f["data-v"] for f in figures(spending, "ifs_figure")]

                # Assert
                self.assertIn(value, ifs)
                self.assertNotIn("7800" if value == "7000" else "7000", ifs)
                self.assertRegex(spending, r'data-mf="spend_pp"[^>]*data-year="2025-26"')
        for page in self.pages.values():
            self.assertNotIn("8,400", page["body"])
            self.assertNotIn("8400", [f["data-v"] for f in figures(page["body"], "ifs_figure")])

    def test_ifs_amounts_keep_their_exact_text(self):
        # Act
        spans = re.findall(r'<span class="mf" data-mf="ifs_figure" data-v="(\d+)" data-year="2025-26">([^<]+)</span>', self.pages["aar"]["body"])

        # Assert
        self.assertIn(("510", "£510"), spans)
        self.assertIn(("7000", "£7,000"), spans)

    def test_title_description_and_indexing(self):
        for name, page in self.pages.items():
            with self.subTest(name):
                # Assert
                self.assertLessEqual(len(page["title"]), 70)
                self.assertLessEqual(len(page["description"]), 160)
                self.assertNotIn("<", page["title"] + page["description"])
                self.assertIs(page["indexable"], True)

    def test_deficit_is_named_with_reasons_and_what_helps(self):
        # Act
        body = self.pages["deficit"]["body"]

        # Assert
        self.assertIn("Why schools go into deficit", body)
        self.assertIn("What helps", body)
        self.assertIn('data-mf="deficit_total"', body)


class SizeBudgetTest(unittest.TestCase):
    def test_two_year_academy_with_one_pta(self):
        # Arrange
        item, ctx = aar_academy()

        # Act
        page = school_page.render(item, ctx)
        html = site.page(page["title"], page["description"], item["path"], page["body"], [("School Money", "/"), (item["name"], item["path"])],
                         extra_head=school_page.EXTRA_HEAD)

        # Assert
        self.assertLessEqual(len(page["body"].encode("utf-8")), 32_000)
        self.assertLess(len(html.encode("utf-8")), 40_000)

    def test_eight_years_three_ptas_and_39_similar_schools(self):
        # Arrange
        item, ctx = big_school()

        # Act
        page = school_page.render(item, ctx)
        html = site.page(page["title"], page["description"], item["path"], page["body"], [("School Money", "/"), (item["name"], item["path"])],
                         extra_head=school_page.EXTRA_HEAD)

        # Assert
        self.assertLessEqual(len(page["body"].encode("utf-8")), 56_000)
        self.assertLess(len(html.encode("utf-8")), 64_000)


class OptionalContextTest(unittest.TestCase):
    def test_page_is_complete_when_optional_ctx_values_are_none(self):
        # Arrange
        item, ctx = cfr_school()
        bare = {"series": ctx["series"], "ifs": IFS, "check_url": ctx["check_url"], "profile": None, "timeline": None,
                "similar": None, "similar_series": None, "council": None, "england": None, "pta_national": None,
                "real_label": None, "sir_url": None}

        # Act
        page = school_page.render(item, bare)
        parsed = Figures(page["body"])

        # Assert
        self.assertIn(ctx["check_url"], page["body"])
        self.assertNotIn("None", page["body"])
        self.assertFalse(parsed.stray)
        self.assertFalse(parsed.errors, parsed.errors)
        self.assertTrue(figures(page["body"], "revenue_reserve", "2025-26"))

    def test_an_empty_series_still_renders_an_honest_page(self):
        # Arrange
        item, _ = cfr_school()

        # Act
        page = school_page.render(item, {"series": {}, "ifs": {}, "check_url": f"{FBIT}/school/100001"})

        # Assert
        self.assertIn("Example Primary", page["body"])
        self.assertFalse(Figures(page["body"]).errors)

    def test_federation_members_and_schools_without_a_status_are_not_indexed(self):
        # Arrange
        item, ctx = cfr_school()
        member = dict(item, member_of={"lead_laestab": "2041234"})
        unassessed = dict(item, status=None)

        # Act / Assert
        self.assertFalse(school_page.render(member, ctx)["indexable"])
        self.assertIn("federation", school_page.render(member, ctx)["body"])
        self.assertFalse(school_page.render(unassessed, ctx)["indexable"])


class AcademyTest(unittest.TestCase):
    def setUp(self):
        item, ctx = aar_academy()
        self.body = school_page.render(item, ctx)["body"]

    def test_pupil_premium_is_not_reported_never_zero(self):
        # Assert
        self.assertIn("not reported in academy accounts", self.body.lower())
        self.assertFalse(figures(self.body, "pupil_premium"))

    def test_trust_central_spend_by_year_beside_the_ifs_510(self):
        # Act
        central = figures(self.body, "trust_central_spend_pp")

        # Assert
        self.assertEqual({(f["data-year"], f["data-v"]) for f in central}, {("2023-24", "480"), ("2024-25", "495")})
        self.assertIn('data-v="510"', self.body)
        self.assertIn("exclude the trust's central spending", self.body.replace("&#x27;", "'"))


class LinesTest(unittest.TestCase):
    def test_donations_say_zero_recorded_or_not_reported(self):
        # Arrange
        item, ctx = cfr_school()
        ctx["series"]["m"]["donations_revenue"]["2025-26"] = {"v": 0, "pp": 0, "r": 0, "rpp": 0}
        missing_item, missing_ctx = cfr_school()
        del missing_ctx["series"]["m"]["donations_revenue"]

        # Act
        zero = school_page.render(item, ctx)["body"]
        missing = school_page.render(missing_item, missing_ctx)["body"]

        # Assert
        self.assertRegex(zero, r'data-mf="donations_revenue" data-v="0" data-pp="0"[^>]*>£0 <small>£0 per pupil</small></span> recorded')
        self.assertIn("Not reported in 2025-26", missing)

    def test_other_dfe_grants_carries_the_pass_through_framing(self):
        # Arrange
        item, ctx = cfr_school()

        # Act
        body = school_page.render(item, ctx)["body"]

        # Assert
        self.assertTrue(figures(body, "other_dfe_grants"))
        self.assertIn("pass straight through", body.lower().replace("passed", "pass") + IFS["framings"]["pass_through_grants"]["title"].lower())
        self.assertIn("cannot be separated out", body)

    def test_other_dfe_grants_is_derived_from_the_rows_when_the_series_lacks_it(self):
        # Arrange
        item, ctx = cfr_school()
        del ctx["series"]["m"]["other_dfe_grants"]
        item["rows"] = [{"year": "2025-26", "source": "CFR", "cfr_additional_grants_i18": 99_000}]

        # Act
        found = figures(school_page.render(item, ctx)["body"], "other_dfe_grants", "2025-26")

        # Assert
        self.assertTrue(found and found[0]["data-v"] == "99000", found)

    def test_suspect_values_are_greyed_hollow_and_left_out_of_comparisons(self):
        # Arrange
        item, ctx = cfr_school()
        ctx["series"]["flags"]["suspect"] = {"2025-26": ["total_expenditure"]}

        # Act
        body = school_page.render(item, ctx)["body"]
        spend = figures(body, "total_expenditure", "2025-26")

        # Assert
        self.assertTrue(spend and all("suspect" in f["class"] for f in spend))
        self.assertFalse([f for f in spend if "data-cmp-similar" in f])
        self.assertIn("hollow", body)

    def test_spending_shows_staff_share_beside_the_ifs_80_percent(self):
        # Act
        body = school_page.render(*cfr_school())["body"]

        # Assert
        self.assertRegex(body, r"Staff costs were \d+% of this school")
        self.assertIn("over 80%", body)


class FlagsTest(unittest.TestCase):
    def setUp(self):
        self.fixtures = every_fixture()

    def render(self, name):
        return school_page.render(*self.fixtures[name])["body"]

    def test_falling_rolls(self):
        # Act
        body = self.render("falling")

        # Assert
        self.assertIn("Pupil numbers fell from 430.0 to 416.0", body)
        self.assertIn("fewer pupils means less money", body)

    def test_pupils_are_shown_to_one_decimal_place(self):
        # Act
        body = self.render("cfr")

        # Assert
        self.assertIn("</span> 430.0</li>", body)

    def test_pass_through(self):
        # Act
        body = self.render("pass_through")
        rises = figures(body, "pass_through", "2025-26")

        # Assert
        self.assertEqual(sorted(f["data-v"] for f in rises), ["150000", "180000"])
        self.assertIn('id="pass-through"', body)

    def test_high_send_questions_put_the_dsg_note_beside_the_14bn(self):
        # Act
        body = self.render("high_send")

        # Assert
        self.assertIn("first <span", body)
        self.assertIn("High Needs Stability Grant", body)
        at = body.index("£14 billion")
        self.assertIn("High Needs Stability Grant", body[at:at + 1200])

    def test_questions_are_capped_filled_and_escaped(self):
        # Arrange
        item, ctx = cfr_school(name="St Mary & St John <Primary>", status="large_reserves", reserve=400_000)
        ctx["series"]["flags"]["falling_rolls"] = {"from": 430.0, "to": 400.0, "change": -0.07}

        # Act
        body = school_page.render(item, ctx)["body"]
        section = body[body.index('id="questions"'):]
        section = section[:section.index("</section>")]

        # Assert
        self.assertLessEqual(section.count("<li>"), 8)
        self.assertNotIn("{", section)
        self.assertIn("St Mary &amp; St John &lt;Primary&gt;", section)
        self.assertNotIn("<Primary>", body)
        self.assertTrue(re.search(r'data-mf="revenue_reserve"[^>]*>£400k', section))


class PtaWordingTest(unittest.TestCase):
    def setUp(self):
        self.fixtures = every_fixture()

    def render(self, name):
        return school_page.render(*self.fixtures[name])["body"].replace("&#x27;", "'")

    def test_no_registered_association(self):
        # Act
        body = self.render("no_pta")

        # Assert
        self.assertIn("No registered parents' association found", body)
        self.assertIn('<span class="mf" data-mf="pta_gap" data-v="5000">£5,000</span> or less', body)

    def test_historical_association(self):
        # Assert
        self.assertIn("Had a registered PTA until 2016", self.render("historical"))

    def test_shared_association_is_split_equally(self):
        # Act
        body = self.render("shared")

        # Assert
        self.assertIn("Shared with 2 schools, split equally", body)
        self.assertTrue(figures(body, "pta_income") and all(f["data-v"] == "10000" for f in figures(body, "pta_income")))

    def test_llm_match_is_lower_confidence(self):
        # Assert
        self.assertIn("matched with lower confidence", self.render("llm"))

    def test_part_a_overlap_and_national_median(self):
        # Act
        body = self.render("big")

        # Assert
        self.assertIn("40 volunteers", body)
        self.assertIn("Annual return due 30 June 2026", body)
        self.assertIn("never added together", body)
        self.assertTrue(figures(body, "pta_per_pupil", "2024-25"))
        self.assertIn('<a href="https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/1100000">', body)

    def test_review_flagged_charities_are_held_back(self):
        # Arrange
        item, ctx = cfr_school(pta=[charity(history=returns(("2024-08", 307_000, 300_000)), review="independent school")])

        # Act
        body = school_page.render(item, ctx)["body"].replace("&#x27;", "'")

        # Assert
        self.assertIn("No registered parents' association found", body)
        self.assertFalse([f for f in figures(body) if f["data-v"] in ("307000", "300000")])


class ShareLinksTest(unittest.TestCase):
    def test_present_and_share_row_links_decks_and_the_30_second_video(self):
        # Act
        body = school_page.render(*cfr_school())["body"]

        # Assert
        self.assertIn("Present and share", body)
        self.assertIn("view=school", body)
        self.assertIn("video/", body)

    def test_the_video_is_one_tap_from_the_top_of_the_page_and_the_ptfa_section(self):
        # Act
        page = school_page.render(*cfr_school())["body"]
        start = page.index('<p class="status-line">')
        status_line = page[start:page.index("</p>", start)]
        ptfa = page[page.index('id="ptfa"'):]

        # Assert
        self.assertIn("Watch in 30 seconds", status_line)
        self.assertIn('class="watch"', status_line)
        self.assertIn("PTFA in 30 seconds", ptfa)


def gold_series():
    """SERIES from the gold file's per-year pipeline_finance_history totals: cash v, pp = v / that year's pupils."""
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    pupils, values = {}, {}
    for year, entry in gold["years"].items():
        totals = entry["totals"]["pipeline_finance_history"]
        pupils[year] = totals["pupils"]
        for key in ("total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "sen_funding", "pupil_premium"):
            if totals.get(key) is not None:
                values.setdefault(key, {})[year] = totals[key]
        values.setdefault("grant_funding_government", {})[year] = totals["grant_funding"]
    return gold, make_series(values, pupils, {y: "CFR" for y in pupils}), pupils


@unittest.skipUnless(GOLD.exists(), "gold file missing")
class WilliamPattenGoldTest(unittest.TestCase):
    def test_every_rendered_income_spending_reserve_and_balance_figure_equals_gold(self):
        # Arrange
        gold, series, pupils = gold_series()
        item = make_item(urn="130932", name=gold["name"], status="in_deficit", reserve=-210_901, streak=1, year="2025-26",
                         pta=[charity(history=returns(("2024-08", 47_000, 46_000), ("2025-08", 48_547, 50_100)))])
        ctx = make_ctx(item, series)

        # Act
        body = school_page.render(item, ctx)["body"]
        found = [f for f in Figures(body).figures if f["data-mf"] in ("total_income", "total_expenditure", "revenue_reserve", "in_year_balance")]

        # Assert
        self.assertGreaterEqual(len(found), 4 * len(gold["years"]))
        for f in found:
            totals = gold["years"][f["data-year"]]["totals"]["pipeline_finance_history"]
            gold_v = totals[f["data-mf"]]
            self.assertEqual(f["data-v"], str(round(gold_v)), f)
            self.assertLessEqual(abs(int(f["data-pp"]) - gold_v / totals["pupils"]), 0.5 + 1 / totals["pupils"], f)
        self.assertIn("437.5", body)

    @unittest.skipUnless(series_module is not None and hasattr(series_module, "school_series"), "series.py not present")
    def test_school_series_on_gold_rows_matches_gold(self):
        # Arrange
        gold = json.loads(GOLD.read_text(encoding="utf-8"))
        rows = []
        for year, entry in gold["years"].items():
            t = entry["totals"]["pipeline_finance_history"]
            rows.append({"urn": "130932", "year": year, "period_end": f"20{year[-2:]}-03", "source": "CFR", "period_months": 12,
                         "pupils": t["pupils"], "did_not_supply": False, "total_income": t["total_income"],
                         "total_expenditure": t["total_expenditure"], "in_year_balance": t["in_year_balance"],
                         "revenue_reserve": t["revenue_reserve"], "grant_funding": t["grant_funding"],
                         "grant_funding_government": t["grant_funding"], "lines": {}})

        # Act
        series = series_module.school_series(rows)

        # Assert
        for year, entry in gold["years"].items():
            t = entry["totals"]["pipeline_finance_history"]
            for key in ("total_income", "total_expenditure", "revenue_reserve", "in_year_balance"):
                self.assertEqual(series["m"][key][year]["v"], round(t[key]), (key, year))
                self.assertEqual(series["m"][key][year]["pp"], round(t[key] / t["pupils"]), (key, year))


if __name__ == "__main__":
    unittest.main()
