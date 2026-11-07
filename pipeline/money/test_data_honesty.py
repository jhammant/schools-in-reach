"""Data honesty on the school page (fix wave 1): one reserve basis per academy page, the 'reserve held by the trust'
status, federations' pupil counts, the first line under a red badge, spending rows that match their definitions,
phone layouts, comparisons in words, the report link and Charity Commission links.

Rows go through the real series.py, status.py and timeline.py, then school_page.render, so the headline, the yearly
table, the chart and the timeline are checked against each other. Offline; fixtures only.
"""

import json
import re
import types
import unittest
from html import unescape
from pathlib import Path

from pipeline.money import school_page, series, site, status as health, timeline
from pipeline.money.test_school_page import (Figures, aar_academy, big_school, cfr_school, make_ctx, make_item,
                                             nearby_contract, nearby_school, section)
from pipeline.money.test_series import MAT, academy_rows, federation_rows, gold_rows, row

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "pipeline/money/assets"
GLOSSARY = json.loads((ASSETS / "glossary.json").read_text(encoding="utf-8"))
CHARITY_1103834 = ("https://register-of-charities.charitycommission.gov.uk/charity-search?p_p_id=uk_gov_ccew_onereg_charitydetails_web_portlet_"
                   "CharityDetailsPortlet&p_p_lifecycle=0&p_p_state=maximized&p_p_mode=view&_uk_gov_ccew_onereg_charitydetails_web_portlet_"
                   "CharityDetailsPortlet_regId=1103834&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_subId=0")
BANNED = ("poor school", "failing", "worst", "bankrupt", "scandal", "no pta", "high-needs balance", "schools budget balance")


def page_from_rows(rows, *, academy=False, name="Example Academy", urn="140001", **item_extra):
    """item and ctx for rows, through the real series, status and timeline: what build_money hands the page."""
    item = make_item(urn=urn, name=name, academy=academy, pta=[])
    item.update(rows=rows, status=health.assess(rows), **item_extra)
    ctx = make_ctx(item, series.school_series(rows), timeline=timeline.status_by_year(rows))
    ctx["similar_series"] = None
    return item, ctx


def figures_in(html, key=None, year=None):
    return [f for f in Figures(html).figures if (key is None or f["data-mf"] == key) and (year is None or f.get("data-year") == year)]


def text_of(html):
    """The words a reader sees: tags and charts out, entities decoded, spaces collapsed."""
    text = unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<svg.*?</svg>", "", html, flags=re.S)))
    return re.sub(r"\s+([,.:;)])", r"\1", " ".join(text.split()))


class StubPhrasing:
    """A stand-in for comparisons-stories' phrasing module (contract C1)."""

    def __init__(self, words="about a quarter more than"):
        self.words, self.calls = words, []

    def ratio_words(self, a, b):
        self.calls.append((a, b))
        return self.words if a and b else None


class PhrasingPatch(unittest.TestCase):
    def use_phrasing(self, module):
        saved = school_page.phrasing
        school_page.phrasing = module
        self.addCleanup(setattr, school_page, "phrasing", saved)


# ----------------------------------------------------------------- 1. one reserve basis per academy page

class OneReserveBasisTest(unittest.TestCase):
    """Mossbourne-like: own reserves, two pooled £0 years, then a trust-inclusive latest year."""

    @classmethod
    def setUpClass(cls):
        cls.rows = academy_rows()
        cls.item, cls.ctx = page_from_rows(cls.rows, academy=True)
        cls.body = school_page.render(cls.item, cls.ctx)["body"]

    def test_headline_table_and_series_agree_on_the_trust_inclusive_figure(self):
        # Arrange
        latest = self.ctx["series"]["years"][-1]
        headline = self.item["status"]["reserve"]
        # Act
        status_figs = figures_in(section(self.body, "status"), "revenue_reserve_incl_trust_share", latest)
        table = re.search(r'<table class="sp-years">.*?</table>', section(self.body, "reserve"), re.S).group(0)
        latest_row = re.search(rf'<tr><th scope="row">{latest}</th>.*?</tr>', table, re.S).group(0)
        # Assert
        self.assertEqual(headline, 3_087_254)
        self.assertEqual(self.ctx["series"]["m"]["revenue_reserve"][latest]["v"], headline)
        self.assertEqual([float(f["data-v"]) for f in status_figs], [headline])
        self.assertEqual([float(f["data-v"]) for f in figures_in(latest_row, "revenue_reserve_incl_trust_share")], [headline])
        self.assertEqual([float(f["data-v"]) for f in figures_in(latest_row, "revenue_reserve")], [0])

    def test_the_own_figure_is_never_labelled_with_the_trust_key_or_mixed_into_the_trust_column(self):
        # Act
        reserve = section(self.body, "reserve")
        own = figures_in(reserve, "revenue_reserve")
        incl = figures_in(reserve, "revenue_reserve_incl_trust_share")
        # Assert
        self.assertEqual({f["data-year"] for f in incl}, {"2024-25"})
        self.assertEqual({f["data-year"] for f in own}, set(self.ctx["series"]["years"]))
        self.assertEqual(reserve.count("not published on this basis"), 5)
        self.assertIn("Academy's own reserve", unescape(reserve))
        self.assertEqual(reserve.count("held by the trust</small>"), 3)

    def test_chart_names_the_trust_share_and_draws_the_own_reserve_as_its_own_line(self):
        # Act
        reserve = section(self.body, "reserve")
        desc = re.search(r"<desc>(.*?)</desc>", reserve, re.S).group(1)
        # Assert
        self.assertIn("including its share of the trust&#x27;s reserve", desc)
        self.assertIn("2024-25: £2k", desc)
        self.assertIn("The academy&#x27;s own reserve per pupil", desc)
        self.assertIn('class="direct"', reserve)
        self.assertRegex(reserve, r'<text class="direct"[^>]*>Incl\. trust</text>')
        self.assertRegex(reserve, r'<text class="direct"[^>]*>Own</text>')

    def test_timeline_keeps_the_two_bases_apart_and_never_says_tight(self):
        # Act
        status = unescape(section(self.body, "status"))
        main, earlier = status.split("Earlier years, on the academy's own reserve")
        # Assert
        self.assertIn("Status by year, including its share of the trust's reserve", main)
        self.assertEqual(main.count('class="badge s-large_reserves small"'), 1)
        self.assertEqual(earlier.count('class="badge s-reserve_held_by_trust small"'), 2)
        self.assertNotIn("s-tight", status)
        self.assertIn("not the same measure as the status above", earlier)

    def test_latest_timeline_point_matches_the_headline(self):
        points = self.ctx["timeline"]
        self.assertEqual(points[-1]["status"], self.item["status"]["status"])
        self.assertEqual(points[-1]["reserve"], self.item["status"]["reserve"])
        self.assertEqual(points[-1]["basis"], self.ctx["series"]["reserve_basis"])


class PooledTrustAcademyTest(unittest.TestCase):
    def test_own_zero_in_a_pooling_trust_reads_held_by_the_trust_not_tight(self):
        # Arrange: Mossbourne before 2024-25, own £0 and no trust-inclusive figure
        rows = academy_rows()[:-1]
        item, ctx = page_from_rows(rows, academy=True)
        # Act
        body = school_page.render(item, ctx)["body"]
        status = section(body, "status")
        # Assert
        self.assertEqual(item["status"]["status"], "reserve_held_by_trust")
        self.assertIn('class="badge s-reserve_held_by_trust large"', status)
        self.assertIn("◇", status)
        self.assertNotIn("Tight", text_of(status))
        self.assertIn("Its trust holds reserves centrally, so this academy's own balance is £0;", text_of(status))
        self.assertIn('<a href="/trust/example-trust/">Example Trust</a> keeps this academy', status)
        self.assertIn(school_page.REPORT_LINK, status)

    def test_latest_series_reserve_equals_the_headline_for_every_fixture(self):
        fixtures = {"trust basis": academy_rows(), "pooled": academy_rows()[:-1], "council": gold_rows()[1],
                    "lubavitch": [row("2022/23", revenue_reserve=0, trust_type=MAT),
                                  row("2023/24", revenue_reserve=0, trust_type=MAT),
                                  row("2024/25", revenue_reserve=274_000, revenue_reserve_incl_trust_share=-284_662, trust_type=MAT)]}
        for name, rows in fixtures.items():
            with self.subTest(name):
                sx, st = series.school_series(rows), health.assess(rows)
                self.assertEqual(sx["m"]["revenue_reserve"][sx["years"][-1]]["v"], round(st["reserve"]))


# ----------------------------------------------------------------- 2. federations

class FederationTest(unittest.TestCase):
    def test_lead_school_says_the_figures_cover_the_federation_and_greys_the_odd_years(self):
        # Arrange: Grazebrook-like
        rows = federation_rows()
        item, ctx = page_from_rows(rows, name="Example Primary", urn="100258")
        item["school"]["federation"] = "New Wave Federation"
        # Act
        body = school_page.render(item, ctx)["body"]
        reserve = section(body, "reserve")
        odd = re.search(r'<tr><th scope="row">2021-22</th>.*?</tr>', reserve, re.S).group(0)
        # Assert
        self.assertIn("These figures cover the whole New Wave Federation: 1,749.5 pupils across its schools.", unescape(body))
        self.assertEqual(ctx["series"]["flags"]["suspect"], {"2021-22": ["pupils"], "2022-23": ["pupils"]})
        self.assertTrue(figures_in(odd, "total_expenditure"))
        self.assertFalse([f for f in figures_in(odd) if "data-pp" in f], odd)
        self.assertIn("doesn't match the money", unescape(odd))
        self.assertIn("No per-pupil figure is shown for 2021-22 and 2022-23", unescape(reserve))

    def test_unnamed_federation_and_a_school_on_its_own(self):
        rows = federation_rows()
        fed_item, fed_ctx = page_from_rows(rows, name="Example Primary")
        solo_item, solo_ctx = cfr_school()
        self.assertIn("These figures cover the whole federation:", unescape(school_page.render(fed_item, fed_ctx)["body"]))
        self.assertNotIn("sp-fed", school_page.render(solo_item, solo_ctx)["body"])

    def test_nearby_federation_entries_are_labelled_and_their_totals_never_read_as_one_schools(self):
        # Arrange
        item, ctx = nearby_school()
        ctx["nearby"]["schools"][0]["federation"] = "New Wave Federation"
        ctx["nearby"]["schools"][1]["federation"] = ""
        # Act
        nearby = section(school_page.render(item, ctx)["body"], "nearby")
        alpha = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", nearby, re.S) if "Alpha Primary" in r)
        spending = re.findall(r"<td>(.*?)</td>", alpha, re.S)[2]
        # Assert
        self.assertIn("figures for the whole New Wave Federation", alpha)
        self.assertIn("federation total", spending)
        self.assertNotIn("k total<", spending)
        self.assertIn("figures for the whole federation", nearby)
        self.assertIn("combined return covers all its schools", unescape(nearby))


# ----------------------------------------------------------------- 3. the first line under a red badge

class FirstLineUnderRedBadgeTest(unittest.TestCase):
    """William Patten's real CFR years (the gold file): in deficit after a reserve of £543,908 in 2019-20."""

    @classmethod
    def setUpClass(cls):
        gold, rows = gold_rows()
        cls.item, cls.ctx = page_from_rows(rows, name=gold["name"], urn=gold["urn"])
        cls.status = section(school_page.render(cls.item, cls.ctx)["body"], "status")

    def test_definition_then_what_changed_then_the_ifs_context(self):
        # Act
        paragraphs = re.findall(r'<p class="([^"]*)"', self.status)
        order = [self.status.index(marker) for marker in ('class="lead"', 'class="sp-define"', 'class="sp-changed"', "Why schools go into deficit")]
        # Assert
        self.assertEqual(self.item["status"]["status"], "in_deficit")
        self.assertEqual(paragraphs[:4], ["status-line", "lead", "sp-define", "sp-changed"])
        self.assertEqual(order, sorted(order))
        self.assertGreater(self.status.index("staffing is the only big thing left to cut"), self.status.index('class="sp-changed"'))

    def test_the_headline_figure_opens_the_schools_own_deficit_definition(self):
        lead = re.search(r'<p class="lead">(.*?)</p>', self.status, re.S).group(1)
        fig = figures_in(lead)[0]
        self.assertEqual(fig["data-mf"], "school_deficit")
        self.assertEqual(float(fig["data-v"]), 210_901)
        self.assertIn("savings have gone below zero", GLOSSARY["school_deficit"]["plain"])
        self.assertNotIn("area", GLOSSARY["school_deficit"]["plain"])

    def test_what_changed_comes_from_the_schools_own_figures(self):
        changed = text_of(re.search(r'<p class="sp-changed">(.*?)</p>', self.status, re.S).group(1))
        self.assertIn("The reserve fell from £544k", changed)
        self.assertIn("in 2019-20 to -£211k", changed)
        self.assertIn("as spending per pupil rose faster than income per pupil", changed)

    def test_heading_for_deficit_and_an_academy_get_their_own_definitions(self):
        heading = school_page.deficit_definition({"status": {"status": "heading_for_deficit"}}, None)
        item, ctx = page_from_rows(academy_rows()[:-1] + [row("2024/25", revenue_reserve=274_000, trust_type=MAT,
                                                              revenue_reserve_incl_trust_share=-284_662)], academy=True)
        body = school_page.render(item, ctx)["body"]
        self.assertIn("It is a warning, not a debt", heading)
        self.assertIn("Counting its share of its trust&#x27;s reserve, this academy&#x27;s balance is below zero", body)
        self.assertNotIn('class="sp-changed"', body)  # the only earlier years are on the other basis


# ----------------------------------------------------------------- 4. spending rows

class SpendingRowsTest(unittest.TestCase):
    def test_overlapping_subtotals_are_marked_and_the_table_says_why_rows_add_up_to_more(self):
        # Act
        spending = section(school_page.render(*cfr_school())["body"], "spending")
        # Assert
        for key, words in school_page.OVERLAPS.items():
            self.assertIn(f'<small class="sp-overlap">{site.esc(words)}</small>', spending, key)
        self.assertIn("Occupation costs", spending)
        self.assertNotIn("Rates, water and other building costs", spending)
        self.assertIn("so the rows add up to more than total spending", spending)

    def test_every_spending_definition_names_its_lines_and_fbit(self):
        for key, _, group in series.METRICS:
            if group != "spend" or key == "total_expenditure":
                continue
            with self.subTest(key):
                entry = GLOSSARY[key]
                self.assertRegex(entry["source"], r"E\d", key)
                self.assertTrue("FBIT" in entry["how"] or "benchmarking" in entry["how"], entry["how"])
        self.assertIn("E06", GLOSSARY["occupation"]["source"])
        self.assertIn("leaves out premises staff (E04) and catering staff (E06)", GLOSSARY["total_staff"]["how"])
        self.assertIn("B06", GLOSSARY["revenue_reserve"]["source"])

    def test_the_check_section_explains_fbit_apportioning_only_for_academies(self):
        academy = text_of(section(school_page.render(*aar_academy())["body"], "check"))
        council = text_of(section(school_page.render(*cfr_school())["body"], "check"))
        self.assertIn("apportions the trust's central income and spending into each academy's figures and this page does not", academy)
        self.assertNotIn("apportions", council)


# ----------------------------------------------------------------- 5. phones

class PhoneLayoutTest(unittest.TestCase):
    def test_pta_and_year_cells_carry_their_labels(self):
        # Act
        body = school_page.render(*cfr_school())["body"]
        pta = re.search(r'<table class="sp-pta">.*?</table>', body, re.S).group(0)
        years = re.search(r'<table class="sp-years">.*?</table>', body, re.S).group(0)
        # Assert
        self.assertEqual(pta.count('<td data-label="Raised">'), pta.count("<tr>") - 1)
        self.assertEqual(pta.count('<td data-label="Spent">'), pta.count("<tr>") - 1)
        self.assertIn('<td data-label="Pupils">', years)
        self.assertIn('<td data-label="In-year balance">', years)
        self.assertIn('<div class="sp-scroll"><table class="sp-years">', body)
        self.assertIn('<div class="sp-scroll"><table class="sp-rows">', body)

    def test_css_stacks_the_tables_at_600px_and_labels_each_cell(self):
        # Arrange
        css = (ASSETS / "school.css").read_text(encoding="utf-8")
        phone = css[css.index("@media (max-width: 600px)"):]
        # Assert
        self.assertRegex(phone, r"\.sp-pta, \.sp-pta tbody \{ display: block")
        self.assertRegex(phone, r"\.sp-pta tr \{ display: grid")
        self.assertIn('.sp-pta td:nth-child(2)::before { content: "Raised"; }', phone)
        self.assertIn('.sp-pta td:nth-child(3)::before { content: "Spent"; }', phone)
        self.assertIn(".sp-years td[data-label]::before, .sp-pta td[data-label]::before { content: attr(data-label); }", phone)
        self.assertIn(".sp-scroll { max-width: 100%; overflow-x: auto;", css)
        self.assertIn("overflow-wrap: anywhere", css)

    def test_nearby_table_scrolls_inside_its_own_box(self):
        css = (ASSETS / "nearby.css").read_text(encoding="utf-8")
        body = school_page.render(*nearby_school())["body"]
        self.assertIn(".nb-scroll { max-width: 100%; overflow-x: auto;", css)
        self.assertIn('<div class="nb-scroll"><table class="nb-table">', body)

    def test_held_badge_is_neutral_grey_with_fallbacks(self):
        css = (ASSETS / "school.css").read_text(encoding="utf-8")
        self.assertIn(".badge.s-reserve_held_by_trust { border-color: var(--held, #6b7280);", css)


# ----------------------------------------------------------------- 6. comparisons in words

class ComparisonWordsTest(PhrasingPatch):
    META = {"year": "2025-26", "peers": 39, "method": "Same phase, size band and free-school-meals band."}

    def test_similar_schools_sentence_with_phrasing_and_similar_meta(self):
        # Arrange
        stub = StubPhrasing()
        self.use_phrasing(stub)
        item, ctx = cfr_school(similar=[{"urn": "100009", "name": "Nine Primary", "path": "/school/100009-nine/"}])
        ctx["similar_meta"] = dict(self.META)
        # Act
        body = school_page.render(item, ctx)["body"]
        line = text_of(re.search(r'<p class="sp-similar-line">.*?</p>', body, re.S).group(0))
        # Assert
        self.assertIn("Per pupil, this school spends about a quarter more than the median for School Money's similar schools "
                      "(39 schools, 2025-26)", line)
        self.assertIn("against £6,000", line)
        self.assertIn("Similar schools (39 schools, 2025-26): median per pupil", body)
        self.assertIn("School Money&#x27;s similar schools (39 schools, 2025-26): the closest", body)
        self.assertNotIn("DfE similar schools", body)
        self.assertIn((ctx["series"]["m"]["total_expenditure"]["2025-26"]["pp"], 6000), stub.calls)

    def test_plain_wording_without_phrasing_or_similar_meta(self):
        for module, meta in ((None, self.META), (StubPhrasing(), None), (StubPhrasing(words=None), self.META)):
            with self.subTest(module=bool(module), meta=bool(meta)):
                # Arrange
                self.use_phrasing(module)
                item, ctx = cfr_school()
                if meta:
                    ctx["similar_meta"] = dict(meta)
                # Act
                body = school_page.render(item, ctx)["body"]
                # Assert
                self.assertNotIn("sp-similar-line", body)
                if not meta:
                    self.assertIn("Similar schools (median per pupil)", body)

    def test_nearby_and_pta_sentences_use_ratio_words_for_the_same_year(self):
        # Arrange
        self.use_phrasing(StubPhrasing("about double"))
        item, ctx = nearby_school()
        ctx["pta_national"] = {"by_year": {"2024-25": {"median_pp": 31}}}
        # Act
        body = school_page.render(item, ctx)["body"]
        nearby, pta = text_of(section(body, "nearby")), text_of(section(body, "ptfa"))
        # Assert
        self.assertIn("Per pupil, this school spends about double the median of the 8 nearest primary schools (2024-25): "
                      "£7,000 against £6,950.", nearby)
        self.assertIn("This school's parents' association raised about double that in the same school year", pta)

    def test_no_comparison_sentences_without_the_module(self):
        self.use_phrasing(None)
        body = school_page.render(*nearby_school())["body"]
        self.assertNotIn("nb-ratio", body)
        self.assertNotIn("raised about", body)


# ----------------------------------------------------------------- 8. links, labels and the size budget

class LinksAndWordingTest(PhrasingPatch):
    def test_report_link_sits_beside_the_headline_badge(self):
        status = section(school_page.render(*cfr_school())["body"], "status")
        line = re.search(r'<p class="status-line">(.*?)</p>', status, re.S).group(1)
        self.assertEqual(school_page.REPORT_LINK, '<a class="report-link" href="/about/#corrections">Report an error or add context</a>')
        self.assertTrue(line.startswith('<span class="badge s-healthy large">'))
        self.assertIn("</span> " + school_page.REPORT_LINK, line)

    def test_charity_links_use_the_register_page_with_the_number_mid_url(self):
        body = school_page.render(*cfr_school())["body"]
        self.assertEqual(school_page.charity_url(1103834), CHARITY_1103834)
        self.assertIn(f'<a href="{site.esc(CHARITY_1103834)}">', body)
        self.assertNotIn("charity-details/", body)

    def test_glossary_has_the_new_keys_and_the_dsg_names(self):
        for key in ("school_deficit", "status_reserve_held_by_trust"):
            for field in ("label", "plain", "how", "source"):
                self.assertTrue(GLOSSARY[key][field].strip(), (key, field))
        self.assertEqual(GLOSSARY["status_reserve_held_by_trust"]["label"], "Reserve held by the trust")
        self.assertEqual(GLOSSARY["dsg_balance"]["label"], "Dedicated Schools Grant balance (all four blocks)")
        self.assertEqual(GLOSSARY["dsg_per_pupil"]["label"], "Dedicated Schools Grant balance (all four blocks) per pupil")
        self.assertIn("pupils at the council's schools on this site in the same year", GLOSSARY["dsg_per_pupil"]["how"])
        self.assertIn("provisional", GLOSSARY["dsg_balance"]["how"])
        self.assertNotIn("high-needs balance", json.dumps(GLOSSARY).lower())

    def test_a_rise_in_pupils_is_never_called_a_fall(self):
        # Arrange: Parkhill-like, up overall but down in each of the last three years
        item, ctx = cfr_school()
        ctx["series"]["flags"]["falling_rolls"] = {"from": 362.0, "to": 442.0, "change": 0.221,
                                                   "run": {"from_year": "2021-22", "from": 470.0, "to": 442.0, "years": 3}}
        # Act
        pupils = text_of(section(school_page.render(item, ctx)["body"], "pupils"))
        # Assert
        self.assertNotIn("fell from 362.0 to 442.0", pupils)
        self.assertIn("Pupil numbers fell in each of the last 3 years, from 470.0 in 2021-22 to 442.0, "
                      "though over all the years shown they rose from 362.0.", pupils)

    def test_new_copy_avoids_banned_and_misleading_words(self):
        self.use_phrasing(StubPhrasing())
        pages = [page_from_rows(academy_rows(), academy=True), page_from_rows(academy_rows()[:-1], academy=True),
                 page_from_rows(federation_rows(), name="Example Primary"), page_from_rows(gold_rows()[1], name="William Patten")]
        for item, ctx in pages:
            with self.subTest(item["status"]["status"]):
                page = school_page.render(item, ctx)
                text = " ".join((page["title"], page["description"], page["body"])).lower()
                for word in BANNED:
                    self.assertNotIn(word, text)
                parsed = Figures(page["body"])
                self.assertFalse(parsed.stray, parsed.stray[:3])
                self.assertFalse(parsed.errors, parsed.errors)

    def test_rich_william_patten_like_page_with_full_nearby_fits_the_school_page_budget(self):
        # Arrange: 8 years, 3 long-running PTAs, 39 similar schools, the full nearby section, comparisons on
        from pipeline.money.build_money import SCHOOL_PAGE_BUDGET  # read only
        self.use_phrasing(StubPhrasing())
        item, ctx = big_school()
        ctx["nearby"] = nearby_contract()
        ctx["similar_meta"] = {"year": "2025-26", "peers": 39, "method": "Same phase, size band and free-school-meals band."}
        # Act
        page = school_page.render(item, ctx)
        html = site.page(page["title"], page["description"], item["path"], page["body"],
                         [("School Money", "/"), (item["name"], item["path"])], extra_head=school_page.EXTRA_HEAD)
        # Assert
        self.assertIsNotNone(section(page["body"], "nearby"))
        self.assertIn("nb-chart", page["body"])  # the full level, not a lighter one
        self.assertLess(len(html.encode("utf-8")), SCHOOL_PAGE_BUDGET)


if __name__ == "__main__":
    unittest.main()
