"""Offline fixture tests for the Money pages. Never reads or alters the real school data."""
import json
from pathlib import Path
import tempfile
import time
import unittest

from pipeline.money import build_money


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
    schools: {code: [school dicts]}; rows: list of finance rows (SHARED FORMAT 1)."""
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


class BuildMoneyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.site = root / "site"
        (self.site / "data/england").mkdir(parents=True)
        (self.site / "data/la/204").mkdir(parents=True)
        (self.site / "index.html").write_text('<html><head><meta property="og:image" content="/og.png"></head></html>', encoding="utf-8")
        (self.site / "data/england/las.json").write_text(json.dumps({"las": [{"la_code": "204", "name": "Hackney", "region": "London"}]}), encoding="utf-8")
        schools = [{"urn": 100000 + i, "name": f"School {i}", "phase": "Primary", "type": "Community school", "town": "London",
                    "postcode": f"E8 {i}AA", "fsm_pct": 20 + i % 10} for i in range(14)]
        schools.append({"urn": 140001, "name": "Converted Academy", "phase": "Primary", "type": "Academy converter", "town": "London", "postcode": "E5 1AA", "trust": "Good Trust"})
        schools.append({"urn": 100099, "name": "Closed School", "status": "Closed", "phase": "Primary"})
        (self.site / "data/la/204/schools.json").write_text(json.dumps({"schools": schools}), encoding="utf-8")
        rows = []
        for i in range(14):
            urn = str(100000 + i)
            reserve = -200_000 if i == 0 else 40_000 * i
            for n, end in enumerate(("2023-03", "2024-03", "2025-03")):
                rows.append(row(urn, end, 2_000_000, 2_050_000 if i == 0 else 1_990_000, reserve + (2 - n) * 50_000 if i == 0 else reserve))
        # Pre-conversion years under the old URN, then academy years under the new one.
        rows.append(row("100500", "2022-03", 2_000_000, 2_100_000, -50_000))
        rows.append(row("140001", "2024-08", 2_100_000, 2_000_000, 50_000, source="AAR", trust="Good Trust"))
        rows.append(row("140001", "2025-08", 2_100_000, 2_000_000, 150_000, source="AAR", trust="Good Trust", revenue_reserve_incl_trust_share=180_000))
        self.history = root / "history.jsonl"
        self.history.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        self.links = root / "links.csv"
        self.links.write_text('"URN","LinkURN","LinkName","LinkType","LinkEstablishedDate"\n140001,100500,"Old School","Predecessor","01-09-2022"\n'
                              '140001,100777,"Other","Predecessor - merged","01-09-2022"\n', encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self):
        return build_money.build(self.site, self.history, self.links, Path(self.tmp.name) / "missing-pta.json")

    def test_builds_national_council_school_and_trust_pages(self):
        # Act
        summary = self.build()
        # Assert
        money = self.site / "money"
        self.assertEqual(summary["with_status"], 15)
        for page in ("index.html", "council/hackney/index.html", "compare/index.html", "about/index.html",
                     "trust/index.html", "trust/good-trust/index.html", "school/100000-school-0/index.html"):
            self.assertTrue((money / page).is_file(), page)
        self.assertFalse(any("closed" in p.name for p in (money / "school").iterdir()))

    def test_deficit_school_is_named_with_reason_and_source_link(self):
        self.build()
        html = (self.site / "money/school/100000-school-0/index.html").read_text(encoding="utf-8")
        self.assertIn("In deficit", html)
        self.assertIn("£200k", html)
        self.assertIn("financial-benchmarking-and-insights-tool.education.gov.uk/school/100000", html)
        national = (self.site / "money/index.html").read_text(encoding="utf-8")
        self.assertIn("Biggest deficits", national)
        self.assertIn("School 0", national)

    def test_academy_history_follows_plain_predecessor_link_only(self):
        self.build()
        data = json.loads((self.site / "money/data/s/140001.json").read_text(encoding="utf-8"))
        self.assertEqual([y[0] for y in data["years"]], ["2021-22", "2023-24", "2024-25"])
        self.assertEqual(data["reserve"], 180_000)
        html = (self.site / "money/school/140001-converted-academy/index.html").read_text(encoding="utf-8")
        self.assertIn("before it became an academy", html)
        self.assertIn("Good Trust", html)

    def test_similar_schools_and_compare_data(self):
        self.build()
        data = json.loads((self.site / "money/data/s/100005.json").read_text(encoding="utf-8"))
        self.assertIn("teaching_staff", data["similar"])
        index = json.loads((self.site / "money/data/index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index), 15)
        status = json.loads((self.site / "money/data/status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["100000"]["status"], "in_deficit")

    def test_sitemap_lists_indexable_pages(self):
        self.build()
        sitemap = (self.site / "money/sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://www.schoolsinreach.com/money/council/hackney/", sitemap)
        self.assertIn("/money/school/100000-school-0/", sitemap)


class HardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, councils, schools, rows, pta=None):
        site, history, links, pta_path = make_site(self.root, councils, schools, rows, pta)
        summary = build_money.build(site, history, links, pta_path)
        return site / "money", summary

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
            self.assertIn(f'href="/money/trust/{p}/"', index)
            html = self.read(money, "trust", p)
            self.assertIn("academy finances", html)
        for i in range(4):
            html = self.read(money, "school", f"14000{i}-academy-{i}")
            link = [p for p in pages if f'href="/money/trust/{p}/"' in html]
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
        late = self.read(money, "school", "100001-opened-late")
        self.assertIn("No full-year finance return", late)
        member = self.read(money, "school", "100002-member")
        self.assertIn("part of a federation", member)
        self.assertIn("the lead school", member)
        self.assertNotIn('href=""', member)
        self.assertNotIn("None", member.split("<main>")[1].split("<footer")[0])

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
        schools = [school(100001, name), school(140001, f"Academy {bad}", type="Academy converter", trust=trust)]
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
        sitemap = (money / "sitemap.xml").read_text(encoding="utf-8")
        self.assertNotIn("<script", sitemap)
        index = json.loads((money / "data/index.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(r[1] for r in index), sorted([name, f"Academy {bad}"]))
        self.assertEqual(index[0][3], council)
        data = json.loads((money / "data/s/100001.json").read_text(encoding="utf-8"))
        self.assertEqual(data["name"], name)
        self.assertEqual(data["council"], council)
        status = json.loads((money / "data/status.json").read_text(encoding="utf-8"))
        self.assertIn("100001", status)
        school_html = (money / "school" / next(p.name for p in (money / "school").iterdir() if p.name.startswith("100001")) / "index.html").read_text(encoding="utf-8")
        self.assertIn("Friends of &lt;script&gt;", school_html)
        self.assertIn("St Mary&#x27;s &lt;script&gt;", school_html)

    def test_big_school_page_stays_under_40kb(self):
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
        self.assertLess(size, 40_000, size)
        self.assertIn("Money raised by parents", (page / "index.html").read_text(encoding="utf-8"))

    def test_six_thousand_schools_build_in_under_a_minute(self):
        # Arrange: 20 councils, 300 schools each, 5 years each, a few trusts and one PTA in ten.
        councils, schools, rows, pta = [], {}, [], {}
        for c in range(20):
            code = str(300 + c)
            councils.append((code, f"Council {c}"))
            schools[code] = []
            for n in range(300):
                urn = 100000 + c * 300 + n
                academy = n % 3 == 0
                extra = {"type": "Academy converter", "trust": f"Trust {n % 40}"} if academy else {}
                schools[code].append(school(urn, f"School {urn}", la=int(code), fsm_pct=n % 60, phase="Secondary" if n % 5 == 0 else "Primary", **extra))
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
        self.assertEqual(sum(1 for p in (money / "school").iterdir()), 6000)
        self.assertEqual(sum(1 for p in (money / "data/s").iterdir()), 6000)
        self.assertEqual(summary["councils"], 20)
        self.assertLess(elapsed, 60, f"build took {elapsed:.1f}s")


if __name__ == "__main__":
    unittest.main()
