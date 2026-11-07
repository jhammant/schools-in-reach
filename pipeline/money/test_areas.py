"""Offline fixture tests for area aggregates and school profiles, plus one real-data check."""
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.money import areas

REAL_HISTORY = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/dfe/finance_history.jsonl")
REAL_SITE_DATA = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/site/data")


def row(urn, end, income, spend, reserve, source="CFR", pupils=300, **extra):
    year = f"{int(end[:4]) - 1}-{end[2:4]}" if source == "CFR" else f"{int(end[:4]) - 1}/{end[2:4]}"
    r = {"urn": urn, "year": year, "period_end": end, "source": source, "la": 204, "laestab": f"204{urn[-4:]}",
         "phase": "primary", "period_months": 12, "pupils": pupils, "total_income": income, "total_expenditure": spend,
         "in_year_balance": income - spend, "revenue_reserve": reserve, "grant_funding": income * 0.9}
    r.update(extra)
    return r


def school(urn, name, lsoa="E01000001", fsm=20, **extra):
    s = {"urn": urn, "name": name, "phase": "Primary", "type": "Community school", "type_group": "Local authority maintained schools",
         "town": "London", "postcode": "E8 1AA", "fsm_pct": fsm, "laestab": f"204{str(urn)[-4:]}", "lat": 51.55, "lon": -0.06,
         "lsoa": lsoa, "msoa": "E02000001", "constituency": "Hackney North", "gender": "Mixed", "sixth_form": False,
         "admissions_policy": "Non-selective", "religious_character": "Does not apply"}
    s.update(extra)
    return s


def square(lat, lon, half=0.001):
    return {"type": "Polygon", "coordinates": [[[lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half],
                                               [lon - half, lat + half], [lon - half, lat - half]]]}


def lsoa_feature(code, lat, lon, imd, idaci, level4, owned):
    return {"type": "Feature", "geometry": square(lat, lon),
            "properties": {"lsoa21cd": code, "imd_decile": imd, "idaci_decile": idaci, "income_decile": imd,
                           "pct_level4_plus": level4, "pct_owned": owned, "pct_social_rented": 100 - owned,
                           "pct_households_not_deprived": 50.0}}


def make_site(root, schools, characteristics=None, admissions=None):
    """A one-council site under root with register, characteristics, three LSOAs and admissions."""
    data = root / "site/data"
    (data / "england").mkdir(parents=True, exist_ok=True)
    (data / "la/204").mkdir(parents=True, exist_ok=True)
    (data / "england/las.json").write_text(json.dumps({"las": [{"la_code": "204", "name": "Hackney", "region": "London"}]}), encoding="utf-8")
    (data / "la/204/schools.json").write_text(json.dumps({"schools": schools}), encoding="utf-8")
    (data / "la/204/characteristics.json").write_text(json.dumps({"schools": characteristics or {}}), encoding="utf-8")
    # Near (same spot), close (about 0.5 km north) and far (about 5 km north).
    features = [lsoa_feature("E01000001", 51.55, -0.06, 8, 9, 70.0, 60.0),
                lsoa_feature("E01000002", 51.5545, -0.06, 4, 3, 50.0, 30.0),
                lsoa_feature("E01000003", 51.595, -0.06, 1, 1, 30.0, 10.0)]
    (data / "la/204/lsoa.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    (data / "la/204/admissions.json").write_text(json.dumps(admissions or {"primary": {}, "secondary": {}}), encoding="utf-8")
    return data


class SchoolProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        # Ten schools with FSM rising 5..50, spread over the three LSOAs so band has a national spread.
        lsoas = ["E01000001", "E01000001", "E01000001", "E01000002", "E01000002", "E01000002", "E01000002", "E01000003", "E01000003", "E01000003"]
        lat = {"E01000001": 51.55, "E01000002": 51.5545, "E01000003": 51.595}
        self.schools = [school(100000 + i, f"School {i}", lsoa=lsoas[i], fsm=5 + 5 * i, lat=lat[lsoas[i]]) for i in range(10)]
        self.schools[1].update({"type": "Academy converter", "type_group": "Academies", "trust": "Good Trust", "admissions_policy": "Selective",
                                "religious_character": "Church of England", "sixth_form": True, "gender": "Girls"})
        self.schools[2].update({"type": "Free schools", "type_group": "Free Schools", "trust": "Good Trust", "admissions_policy": "Partially selective"})
        self.schools[3].update({"type": "Other independent school", "type_group": "Independent schools", "religious_ethos": "Muslim",
                                "trust": "Lone Trust", "fsm_pct": None})
        self.schools[9].update({"religious_character": "None"})
        characteristics = {"100000": {"fsm": {"eligible_pct": 8.5}}}
        admissions = {"primary": {"100000": {"years": {"2024": {"max_distance": 0.6}, "2025": {"max_distance": None}}},
                                  "100001": {"years": {"2025": {"max_distance": 9.0}}},
                                  "100002": {"years": {"2025": {"max_distance": {"A": 0.5, "B": 1.0}}}}},
                      "secondary": {"100004": {"years": {"2025": {"max_distance": 0.1}}}}}
        self.data = make_site(root, self.schools, characteristics, admissions)
        msoa = root / "msoa_income.json"
        msoa.write_text(json.dumps({"E02000001": 41000}), encoding="utf-8")
        self.ctx = areas.Context(self.data, msoa_income_path=msoa)

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self, i):
        return areas.school_profile(self.schools[i], "204", self.data, ctx=self.ctx)

    def test_tags_follow_type_trust_admissions_and_faith(self):
        # Act
        council, academy, free, independent, plain = self.profile(0), self.profile(1), self.profile(2), self.profile(3), self.profile(9)
        # Assert
        self.assertEqual(council["tags"], {"governance": "council-run", "trust": None, "trust_size": None, "admissions": "non-selective",
                                           "faith": None, "phase": "Primary", "gender": "Mixed", "sixth_form": False})
        self.assertEqual(academy["tags"]["governance"], "academy")
        self.assertEqual(academy["tags"]["trust_size"], "multi")
        self.assertEqual(academy["tags"]["admissions"], "grammar")
        self.assertEqual(academy["tags"]["faith"], "Church of England")
        self.assertTrue(academy["tags"]["sixth_form"])
        self.assertEqual(academy["tags"]["gender"], "Girls")
        self.assertEqual(free["tags"]["governance"], "free school")
        self.assertEqual(free["tags"]["admissions"], "partially selective")
        self.assertEqual(independent["tags"]["governance"], "independent")
        self.assertEqual(independent["tags"]["trust_size"], "single")
        self.assertEqual(independent["tags"]["faith"], "Muslim")
        self.assertIsNone(plain["tags"]["faith"])

    def test_intake_prefers_characteristics_then_register(self):
        # Act
        first, second = self.profile(0), self.profile(1)
        # Assert
        self.assertEqual(first["intake"]["fsm_pct"], 8.5)         # characteristics.json wins
        self.assertEqual(second["intake"]["fsm_pct"], 10)         # register fsm_pct
        self.assertIsNone(self.profile(3)["intake"]["fsm_pct"])
        # medians over the nine schools with a figure: 8.5, 10, 15, 25, 30, 35, 40, 45, 50
        self.assertEqual(first["intake"]["fsm_pct_council"], 30)
        self.assertEqual(first["intake"]["fsm_pct_england"], 30)

    def test_area_comes_from_the_schools_lsoa_and_msoa(self):
        # Act
        area = self.profile(0)["area"]
        # Assert
        self.assertEqual(area["lsoa"], "E01000001")
        self.assertEqual(area["imd_decile"], 8)
        self.assertEqual(area["idaci_decile"], 9)
        self.assertEqual(area["pct_level4_plus"], 70.0)
        self.assertEqual(area["pct_owned"], 60.0)
        self.assertEqual(area["pct_social_rented"], 40.0)
        self.assertEqual(area["pct_households_not_deprived"], 50.0)
        self.assertEqual(area["msoa_income"], 41000)
        missing = areas.school_profile(school(100099, "Nowhere", lsoa="E01009999", msoa="E02009999"), "204", self.data, ctx=self.ctx)
        self.assertIsNone(missing["area"]["imd_decile"])
        self.assertIsNone(missing["area"]["msoa_income"])

    def test_catchment_averages_lsoas_within_the_last_distance_offered(self):
        # Act
        near = self.profile(0)["area"]["catchment"]     # 0.6 miles: own LSOA plus the one 0.5 km away
        everyone = self.profile(1)["area"]["catchment"]  # 9 miles: everyone offered, no catchment
        banded = self.profile(2)["area"]["catchment"]    # banded distances are skipped
        tiny = self.profile(4)["area"]["catchment"]      # 0.1 miles: own LSOA only
        # Assert
        self.assertEqual(near["lsoas"], 2)
        self.assertEqual(near["distance_miles"], 0.6)
        self.assertEqual(near["imd_decile"], 6.0)
        self.assertEqual(near["idaci_decile"], 6.0)
        self.assertEqual(near["pct_level4_plus"], 60.0)
        self.assertIsNone(everyone)
        self.assertIsNone(banded)
        self.assertEqual(tiny["lsoas"], 1)
        self.assertEqual(tiny["imd_decile"], 4.0)

    def test_band_runs_from_least_to_most_disadvantaged(self):
        # Act
        bands = [self.profile(i)["band"] for i in range(10)]
        # Assert
        self.assertEqual(bands[0], 1)       # lowest FSM in the least deprived LSOA
        self.assertEqual(bands[9], 5)       # highest FSM in the most deprived LSOA
        self.assertIsNone(bands[3])         # no FSM figure
        self.assertEqual(sorted(b for b in bands if b), [1, 2, 2, 3, 3, 4, 4, 5, 5])   # nine schools in five cuts
        self.assertEqual([b for b in bands if b], sorted(b for b in bands if b))       # FSM and deprivation rise together here

    def test_profile_without_a_context_uses_the_shared_cache(self):
        # Act
        profile = areas.school_profile(self.schools[0], "204", self.data)
        # Assert
        self.assertEqual(profile["tags"]["governance"], "council-run")
        self.assertEqual(profile["area"]["lsoa"], "E01000001")
        self.assertIn(profile["band"], (1, 2, 3, 4, 5, None))


class BuildAreasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.schools = [school(100000 + i, f"School {i}", la_code="204") for i in range(8)]
        for s in self.schools[6:]:
            s.update({"type": "Academy converter", "type_group": "Academies", "trust": "Good Trust"})
        self.data = make_site(root, self.schools)
        self.rows = {}
        for i in range(6):
            urn = str(100000 + i)
            reserve = -100_000 if i < 2 else 50_000 * i
            self.rows[urn] = [row(urn, end, 1_000_000 + 100_000 * i, 1_000_000 + 100_000 * i - 10_000, reserve, pupils=200 + 10 * i,
                                  donations_revenue=2_000 * (i + 1))
                              for end in ("2024-03", "2025-03")]
        for i in range(6, 8):
            urn = str(100000 + i)
            self.rows[urn] = [row(urn, end, 2_000_000, 1_900_000, 300_000, source="AAR", pupils=500) for end in ("2024-08", "2025-08")]
        self.pta = {"schools": {"100000": [{"charity_number": 1, "name": "Friends of School 0", "status": "Registered",
                                            "history": [{"period_end": "2025-07", "income": 20_000}, {"period_end": "2024-07", "income": 10_000}]}],
                                "100001": [{"charity_number": 2, "name": "Hidden", "review": "independent?",
                                            "history": [{"period_end": "2025-07", "income": 999_999}]}]}}
        self.dsg = {"las": {"204": {"name": "Hackney", "values": {"2024-25": -16_000_000, "2025-26": -20_000_000}}},
                    "england": {"2024-25": -3_000_000_000}}
        self.constituencies = root / "constituencies.json"
        self.constituencies.write_text(json.dumps({"Hackney North": "E14000001"}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, schools=None, constituencies_path=None):
        return areas.build_areas(self.rows, schools or self.schools, self.pta, self.dsg, self.data,
                                 constituencies_path=constituencies_path or Path(self.tmp.name) / "missing.json")

    def test_splits_counts_and_medians(self):
        # Act
        result = self.build()
        # Assert
        council = result["councils"]["204"]
        self.assertEqual(council["name"], "Hackney")
        self.assertEqual(council["schools_by_year"], {"2023-24": 8, "2024-25": 8})
        self.assertEqual(council["pupils_by_year"]["2024-25"], sum(200 + 10 * i for i in range(6)) + 1000)
        latest = council["by_year"]["2024-25"]
        self.assertEqual(latest["all"]["schools"], 8)
        self.assertEqual(latest["all"]["in_deficit"], 2)
        self.assertEqual(latest["all"]["in_deficit_pct"], 25.0)
        self.assertEqual(latest["all"]["heading"], 0)
        self.assertEqual(latest["all"]["deficit_total"], -200_000)
        self.assertAlmostEqual(latest["all"]["deficit_pp"], -200_000 / 410)
        self.assertEqual(latest["council-run"]["schools"], 6)
        self.assertEqual(latest["council-run"]["in_deficit"], 2)
        self.assertAlmostEqual(latest["council-run"]["income_pp_median"], (1_200_000 / 220 + 1_300_000 / 230) / 2)
        self.assertAlmostEqual(latest["council-run"]["grant_pp_median"], 0.9 * (1_200_000 / 220 + 1_300_000 / 230) / 2)
        self.assertAlmostEqual(latest["council-run"]["donations_pp_median"], (6_000 / 220 + 8_000 / 230) / 2)
        self.assertEqual(council["statuses_latest"]["in_deficit"], 2)
        self.assertEqual(sum(council["statuses_latest"].values()), 8)
        self.assertEqual(set(latest["all"]), set(areas.S_KEYS))

    def test_fewer_than_five_schools_withholds_everything_but_the_count(self):
        # Act
        academy = self.build()["councils"]["204"]["by_year"]["2024-25"]["academy"]
        # Assert
        self.assertEqual(academy["schools"], 2)
        self.assertIsNone(academy["in_deficit"])
        self.assertIsNone(academy["reserve_median_pp"])
        self.assertIsNone(academy["income_pp_median"])

    def test_pta_counts_the_period_ending_that_year_and_hides_reviewed_charities(self):
        # Act
        latest = self.build()["councils"]["204"]["by_year"]["2024-25"]["all"]
        earlier = self.build()["councils"]["204"]["by_year"]["2023-24"]["all"]
        # Assert
        self.assertEqual(latest["pta_schools"], 1)
        self.assertIsNone(latest["pta_pp_median"])     # under five schools with a PTA figure
        self.assertEqual(earlier["pta_schools"], 1)
        self.assertEqual(areas.pta_income_for(self.pta["schools"]["100000"], 2025), 20_000)
        self.assertIsNone(areas.pta_income_for(self.pta["schools"]["100001"], 2025))

    def test_dsg_per_pupil_uses_that_years_pupils(self):
        # Act
        result = self.build()
        # Assert
        council = result["councils"]["204"]
        self.assertEqual(council["dsg"]["2024-25"]["balance"], -16_000_000)
        self.assertAlmostEqual(council["dsg"]["2024-25"]["per_pupil"], -16_000_000 / council["pupils_by_year"]["2024-25"])
        self.assertEqual(council["dsg"]["2025-26"], {"balance": -20_000_000, "per_pupil": None})
        england = result["england"]
        self.assertEqual(england["dsg"]["2024-25"]["balance"], -3_000_000_000)
        self.assertEqual(result["regions"]["London"]["dsg"], {})

    def test_england_and_region_sum_their_councils(self):
        # Act
        result = self.build()
        # Assert
        england, london, council = result["england"], result["regions"]["London"], result["councils"]["204"]
        self.assertEqual(england["name"], "England")
        self.assertEqual(england["pupils_by_year"], council["pupils_by_year"])
        self.assertEqual(london["by_year"]["2024-25"]["all"], council["by_year"]["2024-25"]["all"])
        self.assertEqual(england["by_year"]["2024-25"]["all"]["in_deficit"], 2)

    def test_constituencies_use_names_or_mapped_codes(self):
        # Act
        by_name = self.build()["constituencies"]
        by_code = self.build(constituencies_path=self.constituencies)["constituencies"]
        # Assert
        self.assertEqual(list(by_name), ["Hackney North"])
        self.assertEqual(list(by_code), ["E14000001"])
        self.assertEqual(by_code["E14000001"]["name"], "Hackney North")
        self.assertEqual(by_code["E14000001"]["schools_by_year"]["2024-25"], 8)

    def test_schools_without_rows_are_skipped(self):
        # Arrange
        extra = self.schools + [school(100999, "Silent", la_code="204")]
        # Act
        result = self.build(schools=extra)
        # Assert
        self.assertEqual(result["councils"]["204"]["schools_by_year"]["2024-25"], 8)


class LoaderTest(unittest.TestCase):
    def test_msoa_income_accepts_both_shapes(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            flat, nested, missing = Path(tmp) / "flat.json", Path(tmp) / "nested.json", Path(tmp) / "missing.json"
            flat.write_text(json.dumps({"E02000001": 41000}), encoding="utf-8")
            nested.write_text(json.dumps({"source": {}, "msoa": {"E02000001": {"net_income_ahc": 39000.4, "total_annual_income": 60000}}}), encoding="utf-8")
            # Act / Assert
            self.assertEqual(areas.load_msoa_income(flat), {"E02000001": 41000})
            self.assertEqual(areas.load_msoa_income(nested), {"E02000001": 39000})
            self.assertEqual(areas.load_msoa_income(missing), {})

    def test_constituency_codes_accept_both_shapes(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            by_code = Path(tmp) / "c.json"
            by_code.write_text(json.dumps({"E14000001": {"name": "Hackney North", "region": "London"}}), encoding="utf-8")
            by_name = Path(tmp) / "n.json"
            by_name.write_text(json.dumps({"Hackney North": "E14000001"}), encoding="utf-8")
            # Act / Assert
            self.assertEqual(areas.load_constituency_codes(by_code), {"Hackney North": "E14000001"})
            self.assertEqual(areas.load_constituency_codes(by_name), {"Hackney North": "E14000001"})
            self.assertEqual(areas.load_constituency_codes(Path(tmp) / "none.json"), {})

    def test_latest_distance_and_year_helpers(self):
        self.assertEqual(areas.latest_distance({"2024": 1.2, "2025": None}), 1.2)
        self.assertIsNone(areas.latest_distance({"2025": 7.5}))
        self.assertIsNone(areas.latest_distance({"2025": {"A": 1.0}}))
        self.assertEqual(areas.end_year_of("2024-25"), 2025)
        self.assertEqual(areas.end_year_of("2019-20"), 2020)
        self.assertEqual(areas.governance({"type": "Free schools"}), "free school")
        self.assertEqual(areas.council_of({"laestab": "2043614"}), "204")
        self.assertEqual(areas.council_of({}, [{"la": 204}]), "204")


@unittest.skipUnless(REAL_HISTORY.exists() and REAL_SITE_DATA.exists(), "real finance history and site data not present")
class RealDataTest(unittest.TestCase):
    def test_hackney_and_england_figures(self):
        # Arrange
        from pipeline.money.build_money import load_history, load_predecessors, school_rows
        by_urn = load_history(REAL_HISTORY)
        pred = load_predecessors(areas.DEFAULT_LINKS)
        schools, rows = [], {}
        for code in areas.load_las(REAL_SITE_DATA):
            for s in areas.load_register(REAL_SITE_DATA, code):
                r = school_rows(str(s["urn"]), by_urn, pred)
                if r:
                    schools.append(dict(s, la_code=code))
                    rows[str(s["urn"])] = r
        dsg = areas.load_json(areas.DSG_PATH, {})
        # Act
        result = areas.build_areas(rows, schools, areas.load_json(areas.DEFAULT_PTA, {}), dsg, REAL_SITE_DATA)
        # Assert
        hackney = result["councils"]["204"]
        self.assertAlmostEqual(hackney["dsg"]["2025-26"]["balance"], -16_200_000, delta=500_000)
        self.assertGreaterEqual(sum(hackney["statuses_latest"].values()), 55)
        pct = result["england"]["by_year"]["2025-26"]["council-run"]["in_deficit_pct"]
        self.assertTrue(15 <= pct <= 25, pct)


if __name__ == "__main__":
    unittest.main()
