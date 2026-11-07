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

    def test_pta_counts_the_school_year_holding_the_return_and_hides_reviewed_charities(self):
        # Act: a council-run school's July 2024 return is 2024-25 (April-March); July 2025 is 2025-26.
        result = self.build()
        latest = result["councils"]["204"]["by_year"]["2024-25"]["all"]
        earlier = result["councils"]["204"]["by_year"]["2023-24"]["all"]
        # Assert
        self.assertEqual(latest["pta_schools"], 1)
        self.assertIsNone(latest["pta_pp_median"])     # under five schools with a PTA figure
        self.assertEqual(earlier["pta_schools"], 0)
        self.assertEqual(areas.pta_income_for(self.pta["schools"]["100000"], 2025), 20_000)
        self.assertIsNone(areas.pta_income_for(self.pta["schools"]["100001"], 2025))
        self.assertEqual(set(result["pta"]["by_year"]), {"2024-25", "2025-26"})
        self.assertEqual(result["pta"]["by_year"]["2024-25"]["income"], 10_000)

    def test_s_gains_statuses_government_funding_and_real_terms_medians(self):
        # Act
        latest = self.build()["councils"]["204"]["by_year"]["2024-25"]
        council = latest["council-run"]
        # Assert
        self.assertEqual(set(latest["all"]), set(areas.S_KEYS))
        self.assertEqual(council["statuses"], {"in_deficit": 2, "large_reserves": 4})
        expected_gov = 0.9 * (1_200_000 / 220 + 1_300_000 / 230) / 2   # CFR falls back to grant_funding
        self.assertAlmostEqual(council["gov_pp_median"], expected_gov)
        index = areas.deflator.index("2024-25", "CFR")
        self.assertAlmostEqual(council["gov_rpp_median"], expected_gov * 100 / index)
        spend = ((1_200_000 - 10_000) / 220 + (1_300_000 - 10_000) / 230) / 2
        self.assertAlmostEqual(council["spend_rpp_median"], spend * 100 / index)
        self.assertAlmostEqual(council["reserve_median_rpp"], council["reserve_median_pp"] * 100 / index)
        self.assertEqual(council["pupils"], sum(200 + 10 * i for i in range(6)))

    def test_suspect_values_stay_out_of_every_median(self):
        # Arrange: one school's spending is flagged; a huge value must not move the median.
        for r in self.rows["100005"]:
            r["total_expenditure"] = 99_000_000
            r["suspect"] = ["total_expenditure"]
        # Act
        council = self.build()["councils"]["204"]["by_year"]["2024-25"]["council-run"]
        # Assert: the median of the five clean schools' spending per pupil
        clean = sorted((1_000_000 + 100_000 * i - 10_000) / (200 + 10 * i) for i in range(5))
        self.assertAlmostEqual(council["spend_pp_median"], clean[2])
        self.assertLess(council["spend_rpp_median"], 10_000)

    def test_combined_series_stops_at_the_last_academy_year(self):
        # Arrange: council-run schools file 2025-26 (to March 2026); academies have no 2025/26 accounts yet.
        for i in range(6):
            urn = str(100000 + i)
            self.rows[urn].append(row(urn, "2026-03", 1_000_000, 1_050_000, -10_000 if i < 3 else 20_000, pupils=210))
        # Act
        result = self.build()
        council = result["councils"]["204"]
        # Assert
        self.assertEqual(council["combined_last_year"], "2024-25")
        self.assertIsNone(council["by_year"]["2025-26"]["all"])
        self.assertEqual(council["by_year"]["2025-26"]["council-run"]["in_deficit"], 3)
        self.assertEqual(council["by_year"]["2025-26"]["academy"]["schools"], 0)
        self.assertNotIn("2025-26", council["pupils_by_year"])
        # The DSG denominator carries each academy's 2024-25 roll forward one year.
        self.assertEqual(council["dsg_pupils_by_year"]["2025-26"], 6 * 210 + 1000)
        self.assertAlmostEqual(council["dsg"]["2025-26"]["per_pupil"], -20_000_000 / (6 * 210 + 1000))
        self.assertIsNotNone(result["england"]["by_year"]["2024-25"]["all"])

    def test_trusts_group_academy_returns_with_central_spend(self):
        # Arrange: five more academies so the trust's statistics are shown; rows name the trust and company.
        extra = [school(100010 + i, f"Academy {i}", la_code="204", type="Academy converter", type_group="Academies",
                        trust="Good Trust") for i in range(3)]
        for s in self.schools[6:] + extra:
            urn = str(s["urn"])
            self.rows[urn] = [row(urn, end, 2_000_000, 1_900_000, -5_000 if urn == "100010" else 300_000, source="AAR",
                                  pupils=500, trust="Good Trust", company_number="07000001",
                                  trust_central_spend_per_pupil=central)
                              for end, central in (("2024-08", 0), ("2025-08", 400))]
        # Act
        trusts = self.build(schools=self.schools + extra)["trusts"]
        # Assert
        self.assertEqual(list(trusts), ["good-trust"])
        trust = trusts["good-trust"]
        self.assertEqual((trust["name"], trust["company_number"], trust["path"]), ("Good Trust", "07000001", "/trust/good-trust/"))
        self.assertEqual(trust["central_pp"], {"2024-25": 400})   # 0 means not reported, never £0
        self.assertEqual(trust["schools_by_year"], {"2023-24": 5, "2024-25": 5})
        self.assertEqual(trust["by_year"]["2024-25"]["all"]["in_deficit"], 1)
        self.assertEqual(trust["by_year"]["2024-25"]["council-run"]["schools"], 0)
        self.assertEqual(sum(trust["statuses_latest"].values()), 5)

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


class PtaTest(unittest.TestCase):
    """The national PTA block: year rule, shared split, review and hold-back, bands, tags and rankings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.schools = [school(100000 + i, f"School {i}", la_code="204", band=1 + i % 5) for i in range(10)]
        for s in self.schools[5:]:
            s.update({"type": "Academy converter", "type_group": "Academies"})
        self.schools[9]["admissions_policy"] = "Selective"
        self.schools.append(school(102092, "Highgate Primary School", la_code="204", band=1))
        self.data = make_site(root, self.schools)
        self.rows = {}
        for i, s in enumerate(self.schools):
            urn = str(s["urn"])
            academy = s.get("type_group") == "Academies"
            ends = ("2024-08", "2025-08") if academy else ("2024-03", "2025-03")
            self.rows[urn] = [row(urn, end, 1_000_000, 990_000, 50_000, source="AAR" if academy else "CFR",
                                  pupils=100 * (n + 1)) for n, end in enumerate(ends)]

        def charity(number, name, history, **extra):
            return dict({"charity_number": number, "name": name, "status": "Registered",
                         "history": [{"period_end": e, "income": i, "expenditure": i - 1_000} for e, i in history],
                         "match": {"method": "postcode", "evidence": "test", "confidence": "high"}}, **extra)

        schools = {str(100000 + i): [charity(2000 + i, f"Friends of School {i}", [("2024-07", 10_000 * (i + 1))])]
                   for i in range(10)}
        # An infant/junior pair sharing one association: split equally.
        schools["100000"] = [charity(3000, "Shared PTA", [("2024-07", 30_000)], shared_with=["100001"])]
        schools["100001"] = [charity(3000, "Shared PTA", [("2024-07", 30_000)], shared_with=["100000"])]
        # A lower-confidence (LLM) match.
        schools["100004"][0]["match"] = {"method": "llm", "evidence": "test", "confidence": "medium"}
        # A Highgate-style mismatch (an independent school's charity on a state primary), flagged for review.
        schools["102092"] = [charity(1056624, "Friends of Highgate School Society", [("2024-07", 307_000)],
                                     review="matched an independent school's charity")]
        # An unflagged charity over the hold-back limit.
        schools["100008"].append(charity(4000, "Big Foundation", [("2024-07", 900_000)]))
        self.pta = {"schools": schools}
        self.result = areas.build_areas(self.rows, self.schools, self.pta, {}, self.data,
                                        constituencies_path=root / "missing.json")["pta"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_pta_year_follows_the_schools_own_year(self):
        # Assert: the shared contract examples, through series.pta_year when present and the local copy.
        for fn in (areas.pta_year, areas.local_pta_year):
            self.assertEqual(fn("2023-03", "CFR"), "2022-23")
            self.assertEqual(fn("2025-08", "CFR"), "2025-26")
            self.assertEqual(fn("2025-08", "AAR"), "2024-25")
            self.assertEqual(fn("2024-09", "AAR"), "2024-25")
        years = [row("1", "2024-03", 1, 1, 1), row("1", "2025-08", 1, 1, 1, source="AAR")]
        self.assertEqual(areas.return_source("2025-07", years), "AAR")   # inside the academy's own year
        self.assertEqual(areas.return_source("2024-02", years), "CFR")
        self.assertEqual(areas.return_source("2027-01", years), "AAR")   # nearest return

    def test_by_year_splits_shared_charities_and_skips_held_ones(self):
        # Assert: July 2024 is 2024-25 for council-run schools and 2023-24 for academies.
        by_year = self.result["by_year"]
        self.assertEqual(set(by_year), {"2023-24", "2024-25"})
        council_run = by_year["2024-25"]
        self.assertEqual(council_run["schools"], 5)
        self.assertEqual(council_run["ptas"], 4)            # the shared charity once
        self.assertEqual(council_run["income"], 30_000 + 30_000 + 40_000 + 50_000)
        self.assertEqual(by_year["2023-24"]["income"], sum(10_000 * (i + 1) for i in range(5, 10)))
        self.assertEqual(self.result["held"], [{"charity_number": 4000, "name": "Big Foundation", "income": 900_000}])

    def test_per_pupil_uses_that_years_pupils(self):
        # Assert: council-run 2024-25 has 200 pupils; academies' 2023-24 (to August 2024) has 100.
        top = {t["urn"]: t for t in self.result["top"]}
        self.assertEqual(top["100000"]["income"], 15_000)
        self.assertEqual(top["100000"]["pp"], 75)
        self.assertEqual((top["100005"]["year_end"], top["100005"]["pupils"], top["100005"]["pp"]), ("2023-24", 100, 600))

    def test_top_is_recomputed_and_never_ranks_a_flagged_mismatch(self):
        # Assert
        numbers = [t["charity_number"] for t in self.result["top"]]
        self.assertNotIn(1056624, numbers)
        self.assertNotIn(4000, numbers)
        self.assertNotIn("102092", [t["urn"] for t in self.result["top"]])
        self.assertEqual(self.result["top"][0]["urn"], "100009")
        self.assertEqual(self.result["top"][0]["income"], 100_000)
        self.assertEqual({t["urn"]: t["confidence"] for t in self.result["top"]}["100004"], "medium")

    def test_bands_and_tags_use_each_schools_latest_return(self):
        # Assert
        self.assertEqual(self.result["window"], ["2023-24", "2024-25"])
        self.assertEqual(sum(b["schools"] for b in self.result["by_band"].values()), 10)
        self.assertIsNone(self.result["by_band"]["1"]["median_pp"])   # two schools: withheld
        governance = self.result["by_tag"]["governance"]
        self.assertEqual((governance["council-run"]["schools"], governance["academy"]["schools"]), (5, 5))
        self.assertEqual(governance["academy"]["median_pp"], 800)
        self.assertEqual(self.result["by_tag"]["admissions"]["grammar"]["schools"], 1)

    def test_a_partial_later_year_never_replaces_a_return_inside_the_window(self):
        # Arrange: ten schools have 2024-25 returns; one has also filed for 2025-26, still being filed.
        def slot(income):
            return {"income": income, "spend": None, "by_charity": {1: income}, "names": {1: "PTA"},
                    "confidence": "high", "pupils": 100}

        records = []
        for i in range(10):
            years = {"2024-25": slot(10_000.0)}
            if i == 0:
                years["2025-26"] = slot(400_000.0)
            records.append({"urn": str(i), "name": f"School {i}", "council": "204", "council_name": "Hackney",
                            "band": 1, "tags": {y: {"governance": "council-run"} for y in years}, "years": years})
        # Act
        result = areas.build_pta(records)
        # Assert: the partial year is counted by year but never in the window's comparisons.
        self.assertEqual(result["window"], ["2023-24", "2024-25"])
        self.assertEqual(result["by_year"]["2025-26"]["income"], 400_000)
        self.assertEqual({t["year_end"] for t in result["top"]}, {"2024-25"})
        self.assertEqual(result["by_band"]["1"]["mean_pp"], 100)


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
    """One build of the real areas (about 35 s), checked several ways."""

    @classmethod
    def setUpClass(cls):
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
        cls.pta = areas.load_json(areas.DEFAULT_PTA, {})
        cls.result = areas.build_areas(rows, schools, cls.pta, areas.load_json(areas.DSG_PATH, {}), REAL_SITE_DATA)

    def test_hackney_and_england_dsg_come_from_la_dsg(self):
        # Assert
        hackney = self.result["councils"]["204"]
        self.assertEqual(hackney["dsg"]["2025-26"]["balance"], -16_249_115)
        self.assertEqual(self.result["england"]["dsg"]["2025-26"]["balance"], -6_401_975_573)
        self.assertGreaterEqual(sum(hackney["statuses_latest"].values()), 55)

    def test_about_a_fifth_of_council_run_schools_in_deficit_in_2025_26(self):
        # Assert
        latest = self.result["england"]["by_year"]["2025-26"]
        self.assertTrue(15 <= latest["council-run"]["in_deficit_pct"] <= 25, latest["council-run"]["in_deficit_pct"])
        self.assertIsNone(latest["all"])          # academies' 2025/26 accounts are not published yet

    def test_pta_rankings_never_include_review_flagged_charities(self):
        # Arrange
        flagged = {c["charity_number"] for charities in (self.pta.get("schools") or {}).values()
                   for c in charities if c.get("review")}
        # Assert
        top = self.result["pta"]["top"]
        self.assertTrue(top)
        self.assertFalse(flagged & {t["charity_number"] for t in top})
        self.assertNotIn(("102092", 1056624), {(t["urn"], t["charity_number"]) for t in top})
        self.assertTrue(all(t["income"] <= areas.HOLD_ABOVE for t in top))


if __name__ == "__main__":
    unittest.main()
