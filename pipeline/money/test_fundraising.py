"""Fundraising discovery contracts, honest figures, static fallbacks and byte budgets."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pipeline.money import build_money, fundraising, school_page, series, site
from pipeline.money.test_build_money import make_site, row, school
from pipeline.money.test_school_page import big_school, cfr_school


def association(income=12_000, **over):
    return dict({"charity_number": "1234567", "name": "Friends of Example", "status": "Registered",
                 "history": [{"period_end": "2025-03-31", "income": income, "expenditure": 9000}]}, **over)


def model(root, **over):
    schools = [school(100000 + i, f"Example School {i}", lat=51.55 + i * .001, lon=-.06,
                      phase="Secondary" if i == 11 else "Primary") for i in range(12)]
    rows = [row(str(100000 + i), "2025-03-31", 1_800_000, 1_750_000, 90_000,
                phase="secondary" if i == 11 else "primary", **over) for i in range(12)]
    charities = {str(100000 + i): [association()] for i in range(1, 12)}
    paths = make_site(root, [("204", "Hackney")], {"204": schools}, rows, charities)
    councils, items, _ = build_money.build_model(*paths)
    return paths, councils, items


class FundraisingTest(unittest.TestCase):
    def test_latest_keeps_federation_and_suspect_pupil_counts_out_of_per_pupil_figures(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            _, _, items = model(Path(tmp))
            item = items[1]
            # Act
            normal = fundraising.latest(item)
            item["rows"][0]["federated"] = "Lead school"
            federation = fundraising.latest(item)
            item["rows"][0].pop("federated")
            item["rows"][0]["suspect"] = ["pupils"]
            suspect = fundraising.latest(item)
        # Assert
        self.assertEqual((normal["income"], normal["pp"], normal["year"]), (12000, 40, "2024-25"))
        self.assertEqual((federation["income"], federation["pp"]), (12000, None))
        self.assertEqual((suspect["income"], suspect["pp"]), (12000, None))

    def test_registered_only_shared_income_zero_and_missing_year_keep_their_meaning(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            _, _, items = model(Path(tmp))
            item = items[1]
            item["pta"] = [association(shared_with=["100002"], match={"confidence": "medium"}),
                           association(800_000, review=True), association(50_000, status="Removed")]
            # Act
            shared = fundraising.latest(item)
            item["pta"] = [association(0)]
            zero = fundraising.latest(item)
            item["pta"] = [association(history=[])]
            missing = fundraising.latest(item)
            item["pta"] = [association(status="Removed")]
            removed = fundraising.latest(item)
        # Assert
        self.assertEqual((shared["income"], shared["pp"], shared["flags"]), (6000, 20, 3))
        self.assertEqual((zero["income"], zero["pp"]), (0, 0))
        self.assertEqual((missing["income"], missing["pp"], missing["year"]), (None, None, None))
        self.assertIsNone(removed)

    def test_new_data_shape_medians_and_size_with_8750_associations_and_24800_schools(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            _, _, items = model(Path(tmp))
            area_doc = {"pta": {"year": "2024-25", "by_year": {"2024-25": {"median_pp": 31.4}}},
                        "councils": {"204": {"by_year": {"2024-25": {"all": {"pta_pp_median": 76.1}}}}}}
            # Act
            doc = fundraising.build_data(items, area_doc)
            sample = doc["rows"][0]
            large = dict(doc, rows=[list(sample[:-1]) + [[4200, 12, 10]] for _ in range(8750)],
                         pupils={str(100000 + i): 1234.5 for i in range(24800)})
            encoded = fundraising.encode(large)
        # Assert
        self.assertEqual(doc["columns"], fundraising.COLUMNS)
        self.assertEqual(doc["v"], 2)
        self.assertEqual(len(doc["rows"]), 11)
        self.assertEqual(doc["england"], 31)
        self.assertEqual(doc["councils"]["204"], ["Hackney", "London", 76])
        self.assertEqual(len(sample), len(doc["columns"]))
        self.assertLess(len(encoded.encode()), fundraising.DATA_BUDGET)
        self.assertNotIn("name", doc["columns"])
        self.assertIn("100000", doc["pupils"], "pupils also cover schools without an association")

    def test_latest_change_matches_series_and_keeps_the_original_income_fields(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            _, _, items = model(Path(tmp))
            item = items[1]
            current = item["rows"][0]
            previous = dict(current, period_end="2024-03-31", year="2023-24", pupils=200)
            item["rows"] = [previous, current]
            item["pta"] = [association(history=[{"period_end": "2024-08", "income": 35000, "expenditure": 1},
                                                {"period_end": "2025-08", "income": 39200, "expenditure": 1}])]
            # Act
            latest = fundraising.latest(item, latest_complete="2024-25")
            change = series.pta_changes(item["pta"], item["rows"], series.pta_pupils(item["rows"]))["2024-25"]
            partial = fundraising.latest(item, latest_complete="2023-24")
        # Assert
        self.assertEqual(latest["change"], [4200, 12, -44])
        self.assertEqual(latest["change"], [change[k] for k in ("value", "pct", "pp")])
        self.assertEqual(partial["change"], 4)
        self.assertEqual({k: v for k, v in partial.items() if k != "change"}, {k: v for k, v in latest.items() if k != "change"})

    def test_school_size_does_not_fall_back_from_an_unreliable_latest_count(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            _, _, items = model(Path(tmp))
            item = items[0]
            item["rows"].insert(0, dict(item["rows"][0], period_end="2024-03-31", year="2023-24", pupils=200))
            for fields in ({"suspect": ["pupils"]}, {"federated": "Lead school"}, {"pupils": None}):
                original = dict(item["rows"][-1])
                item["rows"][-1].update(fields)
                # Act
                count = fundraising.school_size(item)
                # Assert
                self.assertIsNone(count)
                item["rows"][-1] = original

    def test_search_adds_only_seven_bytes_per_school(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            _, councils, items = model(Path(tmp))
            # Act
            index = build_money.search_index(councils, items, {})
        original = [{k: v for k, v in r.items() if k != "ph"} for r in index]
        def encode(value):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        # Assert
        self.assertEqual(len(encode(index)) - len(encode(original)), 7 * len(items))
        self.assertEqual([r["ph"] for r in index if r["t"] == "school"], [1] * 11 + [2])
        self.assertEqual(fundraising.phase_code("All-through"), 4)

    def test_nearest_registered_associations_are_selected_before_the_eight_school_limit(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            _, _, items = model(Path(tmp))
            items[1]["pta"] = []  # nearest school has none; still get eight fundraisers
            # Act
            fundraising.build_data(items, {})
            build_money.add_nearby_fundraising(items)
            nearby = items[0]["nearby_fundraising"]
        # Assert
        self.assertEqual(len(nearby), 8)
        self.assertEqual([r["name"] for r in nearby], [f"Example School {i}" for i in range(2, 10)])
        self.assertEqual([r["mi"] for r in nearby], sorted(r["mi"] for r in nearby))
        self.assertTrue(all(r["pp"] == 40 and r["income"] == 12000 for r in nearby))
        self.assertEqual(items[-1]["nearby_fundraising"], [], "other phase is not mixed in")

    def test_nearby_excludes_self_distant_and_unlocated_schools(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            _, _, items = model(Path(tmp))
            items[2]["lat"] = 55
            items[3]["lat"] = None
            # Act
            fundraising.build_data(items, {})
            build_money.add_nearby_fundraising(items)
        # Assert
        names = [r["name"] for r in items[1]["nearby_fundraising"]]
        self.assertNotIn("Example School 1", names)
        self.assertNotIn("Example School 2", names)
        self.assertNotIn("Example School 3", names)
        self.assertEqual(items[3]["nearby_fundraising"], [])

    def test_full_fixture_build_writes_the_lazy_file_and_passes_nearby_to_school_pages(self):
        # Arrange
        with TemporaryDirectory() as tmp:
            paths, _, _ = model(Path(tmp))
            out = Path(tmp) / "money"
            # Act
            build_money.build(*paths, out=out, dsg_path=Path(tmp) / "missing-dsg.json")
            doc = json.loads((out / "data/fundraising.json").read_text())
            page = (out / "school/100000-example-school-0/index.html").read_text()
            search = (out / "search/index.html").read_text()
        # Assert
        self.assertEqual(len(doc["rows"]), 11)
        self.assertIn("What parents raise at schools nearby", page)
        self.assertIn('/school/100001-example-school-1/#ptfa', page)
        self.assertIn("browse by council", search.lower())
        self.assertIn('href="/council/"', search)

    def test_ptfa_finder_is_before_the_static_lists_and_links_the_guide(self):
        # Arrange
        from pipeline.money.test_area_pages import Fixture
        fixture = Fixture()
        try:
            # Act
            html = fixture.pages()["ptfa"]["intro"]
        finally:
            fixture.tmp.cleanup()
        # Assert
        self.assertLess(html.index('id="fundraising-finder"'), html.index("The biggest fundraisers"))
        self.assertIn('href="/guides/ptfa/"', html)
        self.assertIn("How to raise more: Gift Aid, match funding and more", html)
        self.assertIn("<noscript>", html)

    def test_nearby_fundraising_shows_with_and_without_an_association_and_fits_big_page(self):
        # Arrange
        neighbours = [{"name": f"Nearby School {i}", "p": f"/school/{100100+i}-nearby/", "mi": .2 + i,
                       "income": 12000, "pp": 40 if i else None, "year": "2024-25", "flags": 0} for i in range(8)]
        for item, ctx in [cfr_school(pta=[]), cfr_school(), big_school()]:
            ctx["nearby_fundraising"] = neighbours
            # Act
            result = school_page.render(item, ctx)
            html = site.page(result["title"], result["description"], item["path"], result["body"], [])
            # Assert
            self.assertIn("What parents raise at schools nearby", html)
            self.assertEqual(html.count('class="nearby-fundraising"'), 1)
            self.assertEqual(html.count("#ptfa\">Nearby School"), 8)
            self.assertIn("£12,000", html)
            self.assertIn("£40 per pupil", html)
            self.assertIn("per pupil unavailable", html)
            self.assertIn('/ptfa/?council=204#fundraising-finder', html)
            self.assertLess(len(html.encode()), build_money.SCHOOL_PAGE_BUDGET)
