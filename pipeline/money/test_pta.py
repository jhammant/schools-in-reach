"""Tests for the parents' association matcher; fixtures live in tempfile dirs."""
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.money import pta

CHARITY_JSON = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/charity/publicextract.charity.json")
SITE_DATA = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/site/data")


def school(urn, name, postcode, website=None, status=None):
    return {"urn": urn, "name": name, "postcode": postcode, "website": website, "status": status}


def charity(number, name, postcode=None, web=None, registered="2004-05-19", removed=None, linked=0, income=48547.0):
    return {"registered_charity_number": number, "linked_charity_number": linked, "charity_name": name,
            "charity_registration_status": "Removed" if removed else "Registered",
            "date_of_registration": f"{registered}T00:00:00", "date_of_removal": f"{removed}T00:00:00" if removed else None,
            "latest_income": income, "charity_contact_postcode": postcode, "charity_contact_web": web}


class NormaliseTest(unittest.TestCase):
    def test_strips_punctuation_and_generic_words(self):
        # Arrange
        name = "William Patten Primary School (PTFA)!"
        # Act
        tokens = pta.normalise(name)
        # Assert
        self.assertEqual(tokens, ["william", "patten"])

    def test_ampersand_saint_and_possessive_unify(self):
        # Arrange / Act
        a = pta.normalise("St. Mary's & St Joseph's C of E Primary")
        b = pta.normalise("SAINT MARYS AND SAINT JOSEPHS CHURCH OF ENGLAND SCHOOL PTA")
        # Assert
        self.assertEqual(a, ["mary", "joseph"])
        self.assertEqual(a, b)

    def test_parents_teachers_and_friends_is_generic(self):
        # Arrange / Act
        tokens = pta.normalise("WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION")
        # Assert
        self.assertEqual(tokens, ["william", "patten"])


class PhaseTest(unittest.TestCase):
    def test_phase_words_and_conflicts(self):
        # Arrange / Act
        infant = pta.phase_words("Fairfield Infants and Nursery School")
        junior = pta.phase_words("FRIENDS OF FAIRFIELD ENDOWED JUNIOR SCHOOL")
        # Assert
        self.assertEqual(infant, {"infant", "nursery"})
        self.assertEqual(junior, {"junior"})
        self.assertTrue(pta.phases_conflict(infant, junior))
        self.assertTrue(pta.phases_conflict({"primary"}, {"high"}))
        self.assertFalse(pta.phases_conflict({"primary"}, {"first"}))
        self.assertFalse(pta.phases_conflict({"prep", "high"}, {"primary"}))
        self.assertFalse(pta.phases_conflict(set(), {"junior"}))


class IterJsonArrayTest(unittest.TestCase):
    def test_objects_spanning_chunk_boundaries(self):
        # Arrange
        objs = [{"n": i, "name": "x" * (i % 7), "nested": {"a": [1, 2, {"b": "]}[,"}]}} for i in range(50)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "array.json"
            path.write_text("﻿[" + "\n,".join(json.dumps(o) for o in objs) + "\n]\n", encoding="utf-8")
            # Act
            got = list(pta.iter_json_array(path, chunk_size=7))
        # Assert
        self.assertEqual(got, objs)

    def test_strings_with_brackets_and_quotes(self):
        # Arrange
        objs = [{"charity_name": 'FRIENDS OF "THE" [SCHOOL], {PTA}'}, {"charity_name": "a\\b]"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "array.json"
            path.write_text(json.dumps(objs), encoding="utf-8")
            # Act
            got = list(pta.iter_json_array(path, chunk_size=3))
        # Assert
        self.assertEqual(got, objs)

    def test_empty_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "array.json"
            path.write_text("[ ]", encoding="utf-8")
            self.assertEqual(list(pta.iter_json_array(path, chunk_size=1)), [])


class MatchTest(unittest.TestCase):
    def test_postcode_match(self):
        # Arrange
        schools = [school(130932, "William Patten Primary School", "N16 0NX")]
        charities = [charity(1103834, "WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION", "N160NX")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(rejections, [])
        self.assertEqual(list(matches), ["130932"])
        got = matches["130932"][0]
        self.assertEqual(got["charity_number"], 1103834)
        self.assertEqual(got["match"], {"method": "postcode", "evidence": "tokens william,patten; postcode N160NX"})
        self.assertEqual(got["registered"], "2004-05-19")
        self.assertIsNone(got["removed"])
        self.assertEqual(got["status"], "Registered")

    def test_sector_match_when_tokens_unique_in_district(self):
        # Arrange
        schools = [school(1, "William Patten Primary School", "N16 0NX"), school(2, "Grasmere Primary School", "N16 0AB")]
        charities = [charity(10, "FRIENDS OF WILLIAM PATTEN SCHOOL", "N16 0PX")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(rejections, [])
        self.assertEqual(matches["1"][0]["match"]["method"], "sector")
        self.assertIn("sector N160", matches["1"][0]["match"]["evidence"])

    def test_sector_only_is_not_enough_for_another_district(self):
        # Arrange
        schools = [school(1, "William Patten Primary School", "N16 0NX")]
        charities = [charity(10, "WILLIAM PATTEN PTA", "N17 0NX")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(matches, {})
        self.assertEqual(rejections, [])

    def test_website_match(self):
        # Arrange
        schools = [school(1, "William Patten Primary School", "N16 0NX", "http://www.williampatten.hackney.sch.uk/")]
        charities = [charity(10, "WILLIAM PATTEN PTA", None, "https://williampatten.hackney.sch.uk/pta")]
        # Act
        matches, _ = pta.match(schools, charities)
        # Assert
        self.assertEqual(matches["1"][0]["match"]["method"], "website")

    def test_rejects_when_two_schools_in_district_share_tokens(self):
        # Arrange
        schools = [school(1, "William Patten Infant School", "N16 0NX"), school(2, "William Patten Junior School", "N16 0NY")]
        charities = [charity(10, "WILLIAM PATTEN PTA", "N16 0NX")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(matches, {})
        self.assertEqual(len(rejections), 1)
        self.assertEqual(rejections[0]["charity_number"], 10)
        self.assertEqual(sorted(rejections[0]["schools"]), ["William Patten Infant School", "William Patten Junior School"])

    def test_rejects_non_parent_charity(self):
        # Arrange
        schools = [school(1, "William Patten Primary School", "N16 0NX")]
        charities = [charity(10, "WILLIAM PATTEN HOUSING TRUST", "N16 0NX"), charity(11, "FRIENDS OF WILLIAM PATTEN", "N16 0NX")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(matches, {})
        self.assertEqual(rejections, [])

    def test_school_tokens_must_all_appear(self):
        # Arrange
        schools = [school(1, "William Patten Primary School", "N16 0NX")]
        charities = [charity(10, "PATTEN PTA", "N16 0NX"), charity(11, "WILLIAM PATTEN PTA", "N16 0NX", linked=3)]
        # Act
        matches, _ = pta.match(schools, charities)
        # Assert
        self.assertEqual(matches, {})

    def test_skips_closed_schools(self):
        # Arrange
        schools = [school(1, "William Patten Primary School", "N16 0NX", status="Closed")]
        charities = [charity(10, "WILLIAM PATTEN PTA", "N16 0NX")]
        # Act
        matches, _ = pta.match(schools, charities)
        # Assert
        self.assertEqual(matches, {})

    def test_rejects_phase_conflict(self):
        # Arrange: an infant school must not get the junior school's friends, nor a primary a high school's.
        schools = [school(1, "Gomer Infant School", "PO12 2RP"), school(2, "Haslingden Primary School", "BB4 4BJ")]
        charities = [charity(10, "FRIENDS OF GOMER JUNIOR SCHOOL", "PO12 2RP"),
                     charity(11, "HASLINGDEN HIGH SCHOOL PARENTS TEACHERS AND FRIENDS ASSOCIATION", "BB4 4BJ")]
        # Act
        matches, _ = pta.match(schools, charities)
        # Assert
        self.assertEqual(matches, {})

    def test_rejects_other_parent_groups_at_the_school(self):
        # Arrange
        schools = [school(1, "Pyrford Primary School", "GU22 8SX"), school(2, "Chapel Allerton Primary School", "LS7 3PD")]
        charities = [charity(10, "PYRFORD GUIDE AND SCOUT PARENTS ASSOCIATION", "GU22 8SX"),
                     charity(11, "PYRFORD PARENT AND TODDLER GROUP PTA", "GU22 8SX"),
                     charity(12, "CHAPEL ALLERTON PRIMARY SCHOOL PARENT STAFF ASSOCIATION", "LS7 3PD")]
        # Act
        matches, _ = pta.match(schools, charities)
        # Assert
        self.assertEqual(list(matches), ["2"])

    def test_sector_match_allows_only_the_schools_own_place_names(self):
        # Arrange
        schools = [dict(school(1, "Woking College", "GU22 8BL"), town="Woking"),
                   dict(school(2, "Upland Primary School", "DA7 4DG"), town="Bexleyheath")]
        charities = [charity(10, "ST JOHN THE BAPTIST SCHOOL (WOKING) PARENT TEACHER ASSOCIATION", "GU22 8AA"),
                     charity(11, "UPLAND PRIMARY PARENTS ASSOCIATION (BEXLEYHEATH)", "DA7 4AA")]
        # Act
        matches, _ = pta.match(schools, charities)
        # Assert
        self.assertEqual(list(matches), ["2"])
        self.assertEqual(matches["2"][0]["match"]["method"], "sector")

    def test_phase_word_settles_infant_junior_tie(self):
        # Arrange
        schools = [school(1, "Mill Rythe Infant School", "PO11 0PA"), school(2, "Mill Rythe Junior School", "PO11 0PA")]
        charities = [charity(10, "MILL RYTHE JUNIOR SCHOOL PARENT/TEACHER ASSOCIATION", "PO11 0PA"),
                     charity(11, "MILL RYTHE SCHOOLS PTA", "PO11 0PA")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(list(matches), ["2"])
        self.assertEqual(matches["2"][0]["match"]["evidence"], "tokens mill,rythe; postcode PO110PA; phase junior rules out 1")
        self.assertEqual([r["charity_number"] for r in rejections], [11])

    def test_more_specific_school_wins_at_the_same_postcode(self):
        # Arrange
        schools = [school(1, "Bournemouth School", "BH8 9UJ"), school(2, "Bournemouth School for Girls", "BH8 9UJ")]
        charities = [charity(10, "BOURNEMOUTH SCHOOL FOR GIRLS PARENTS-SCHOOL ASSOCIATION", "BH8 9UJ"),
                     charity(11, "BOURNEMOUTH SCHOOL PARENTS ASSOCIATION", "BH8 9UJ")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(rejections, [])
        self.assertEqual([c["charity_number"] for c in matches["2"]], [10])
        self.assertEqual([c["charity_number"] for c in matches["1"]], [11])

    def test_newest_first_and_history_attached(self):
        # Arrange
        schools = [school(1, "William Patten Primary School", "N16 0NX")]
        charities = [charity(10, "WILLIAM PATTEN PTA", "N16 0NX", registered="1995-01-01", removed="2004-01-01"),
                     charity(11, "WILLIAM PATTEN PTFA", "N16 0NX", registered="2004-05-19")]
        returns = [
            {"registered_charity_number": 11, "fin_period_end_date": "2023-08-31T00:00:00", "total_gross_income": 100.0,
             "total_gross_expenditure": 90.0, "suppression_ind": False},
            {"registered_charity_number": 11, "fin_period_end_date": "2024-08-31T00:00:00", "total_gross_income": 200.0,
             "total_gross_expenditure": 150.0, "suppression_ind": True},
            {"registered_charity_number": 99, "fin_period_end_date": "2024-08-31T00:00:00", "total_gross_income": 5.0,
             "total_gross_expenditure": 5.0, "suppression_ind": False},
        ]
        # Act
        matches, _ = pta.match(schools, charities)
        pta.attach_history(matches, iter(returns))
        # Assert
        got = matches["1"]
        self.assertEqual([c["charity_number"] for c in got], [11, 10])
        self.assertEqual(got[0]["status"], "Registered")
        self.assertEqual(got[1]["status"], "Removed")
        self.assertEqual(got[1]["removed"], "2004-01-01")
        self.assertEqual(got[0]["history"], [{"period_end": "2024-08", "income": None, "expenditure": None},
                                             {"period_end": "2023-08", "income": 100.0, "expenditure": 90.0}])
        self.assertEqual(got[1]["history"], [])


class MainTest(unittest.TestCase):
    def test_writes_shared_format(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "la" / "204").mkdir(parents=True)
            (tmp / "la" / "204" / "schools.json").write_text(json.dumps(
                {"schools": [school(130932, "William Patten Primary School", "N16 0NX")]}), encoding="utf-8")
            (tmp / "charity").mkdir()
            (tmp / "charity" / "publicextract.charity.json").write_text("﻿" + json.dumps(
                [charity(1103834, "WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION", "N16 0NX"),
                 charity(1, "WILLIAM PATTEN HOUSING TRUST", "N16 0NX")]), encoding="utf-8")
            (tmp / "charity" / "publicextract.charity_annual_return_history.json").write_text(json.dumps(
                [{"registered_charity_number": 1103834, "fin_period_end_date": "2025-08-31T00:00:00",
                  "total_gross_income": 48547.0, "total_gross_expenditure": 50100.0, "suppression_ind": False}]), encoding="utf-8")
            out, rep = tmp / "out" / "pta.json", tmp / "REPORT.md"
            # Act
            pta.main(["--charity-dir", str(tmp / "charity"), "--site-data", str(tmp), "--out", str(out), "--report", str(rep)])
            data = json.loads(out.read_text(encoding="utf-8"))
            text = rep.read_text(encoding="utf-8")
        # Assert
        self.assertEqual(data["licence"], "Open Government Licence v3.0 (Charity Commission register)")
        self.assertEqual(sorted(data), ["generated", "licence", "schools", "source"])
        self.assertEqual(data["schools"]["130932"][0]["history"], [{"period_end": "2025-08", "income": 48547.0, "expenditure": 50100.0}])
        self.assertEqual(sorted(data["schools"]["130932"][0]),
                         ["charity_number", "history", "latest_income", "match", "name", "registered", "removed", "status"])
        self.assertIn("| William Patten Primary School | WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION (1103834) | postcode |", text)
        self.assertIn("Candidate charities (main, parents' association by name): 1", text)


@unittest.skipUnless(CHARITY_JSON.exists() and SITE_DATA.exists(), "real charity register and site data not present")
class RealDataTest(unittest.TestCase):
    def test_william_patten_ptfa_is_found(self):
        # Arrange
        schools = [s for s in pta.load_schools(SITE_DATA) if str(s["urn"]) == "130932"]
        self.assertEqual(len(schools), 1)
        candidates = (c for c in pta.iter_candidates(CHARITY_JSON) if "PATTEN" in (c.get("charity_name") or ""))
        # Act
        matches, _ = pta.match(schools, candidates)
        # Assert
        got = {c["charity_number"]: c for c in matches.get("130932", [])}
        self.assertIn(1103834, got)
        self.assertIn(got[1103834]["match"]["method"], ("postcode", "sector"))


if __name__ == "__main__":
    unittest.main()



class ExclusionTest(unittest.TestCase):
    def test_pre_schools_and_clubs_are_not_parents_associations(self):
        # Arrange / Act / Assert
        for name in ("HATFIELD HEATH PRE-SCHOOL ASSOCIATION", "ACORN PLAYGROUP PARENTS ASSOCIATION", "OAK AFTER SCHOOL CLUB FRIENDS"):
            self.assertFalse(pta.is_parent_association(name), name)
        self.assertTrue(pta.is_parent_association("CANVEY ISLAND INFANT SCHOOL AND NURSERY PARENT, TEACHER AND FRIENDS ASSOCIATION"))

    def test_large_income_is_flagged_for_review(self):
        rec = pta._charity_record({"registered_charity_number": 1, "charity_name": "FRIENDS OF X SCHOOL", "latest_income": 900_000,
                                   "charity_registration_status": "Registered"}, "postcode", "same postcode")
        self.assertIn("review", rec)
        small = pta._charity_record({"registered_charity_number": 2, "charity_name": "X PTA", "latest_income": 9_000,
                                     "charity_registration_status": "Registered"}, "postcode", "same postcode")
        self.assertNotIn("review", small)

    def test_independent_schools_are_not_loaded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "england").mkdir()
            (root / "la/999").mkdir(parents=True)
            (root / "england/las.json").write_text(json.dumps({"las": [{"la_code": "999", "name": "Testshire"}]}), encoding="utf-8")
            (root / "la/999/schools.json").write_text(json.dumps({"schools": [
                {"urn": 1, "name": "State Primary", "type_group": "Academies"},
                {"urn": 2, "name": "The German School", "type_group": "Independent schools"}]}), encoding="utf-8")
            self.assertEqual([s["urn"] for s in pta.load_schools(root)], [1])
