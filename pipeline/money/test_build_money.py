"""Offline fixture tests for the Money pages. Never reads or alters the real school data."""
import json
from pathlib import Path
import tempfile
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


if __name__ == "__main__":
    unittest.main()
