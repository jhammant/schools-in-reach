"""Tests for the parents' association matcher; fixtures live in tempfile dirs."""
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.money import pta

CHARITY_JSON = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/charity/publicextract.charity.json")
SITE_DATA = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/site/data")
PTA_JSON = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/money/pta.json")


def school(urn, name, postcode, website=None, status=None, **extra):
    return {"urn": urn, "name": name, "postcode": postcode, "website": website, "status": status, **extra}


def charity(number, name, postcode=None, web=None, registered="2004-05-19", removed=None, linked=0, income=48547.0,
            email=None, address=()):
    rec = {"registered_charity_number": number, "linked_charity_number": linked, "charity_name": name,
           "charity_registration_status": "Removed" if removed else "Registered",
           "date_of_registration": f"{registered}T00:00:00", "date_of_removal": f"{removed}T00:00:00" if removed else None,
           "latest_income": income, "charity_contact_postcode": postcode, "charity_contact_web": web, "charity_contact_email": email}
    for i, line in enumerate(address, 1):
        rec[f"charity_contact_address{i}"] = line
    return rec


HANTS = {"850": "Hampshire"}


def pass2(schools, charities, areas=None, objects=None, preds=None, councils=HANTS, matched_urns=frozenset()):
    """Run pass 2 on every charity given, with la_code/council filled in from councils."""
    for s in schools:
        s.setdefault("la_code", next(iter(councils)))
        s.setdefault("council", councils[s["la_code"]])
    unmatched = {c["registered_charity_number"] for c in charities}
    return pta.match_pass2(schools, charities, unmatched, areas or {}, objects or {}, preds or {}, councils=councils,
                           matched_urns=matched_urns)


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

    def test_high_never_meets_grammar(self):
        # G7: 'Sutton High School PSA' must not land on Sutton Grammar.
        self.assertTrue(pta.conflict({"grammar"}, {"high"}))
        self.assertTrue(pta.conflict({"high"}, {"grammar"}))
        self.assertFalse(pta.conflict({"high", "grammar"}, {"high"}))
        self.assertFalse(pta.conflict({"primary"}, {"primary"}))


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
        self.assertEqual(got["match"], {"method": "postcode", "evidence": "tokens william,patten; postcode N160NX", "confidence": "high"})
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

    def test_independent_school_blocks_but_is_never_matched(self):
        # Arrange (G1): Highgate School is independent; its Friends must not fall onto Highgate Primary via the sector rule.
        schools = [school(1, "Highgate School", "N6 4AY", type_group="Independent schools"),
                   school(2, "Highgate Primary School", "N6 5AB")]
        charities = [charity(10, "FRIENDS OF HIGHGATE SCHOOL SOCIETY", "N6 4AY")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(matches, {})
        self.assertEqual([r["reason"] for r in rejections], ["belongs to an independent school"])

    def test_exact_postcode_match_survives_an_independent_namesake_in_the_district(self):
        # Arrange: a charity at the state school's own address is fine even with Sevenoaks School nearby.
        schools = [school(1, "Sevenoaks Primary School", "TN13 3AA"), school(2, "Sevenoaks School", "TN13 1HU", type_group="Independent schools")]
        charities = [charity(10, "SEVENOAKS PRIMARY SCHOOL PTA", "TN13 3AA")]
        # Act
        matches, rejections = pta.match(schools, charities)
        # Assert
        self.assertEqual(list(matches), ["1"])
        self.assertEqual(rejections, [])


class Pass2Test(unittest.TestCase):
    def test_postcode_exact_name_the_other_way_round(self):
        # Arrange (rule f): the charity is at the school's address and uses a shorter name than the school.
        schools = [school(1, "Pool-in-Wharfedale CE Primary School", "LS21 1LG"), school(2, "Otley All Saints Primary", "LS21 1LG")]
        charities = [charity(10, "POOL C OF E SCHOOL PTA", "LS21 1LG")]
        # Act
        matches, ambiguous = pass2(schools, charities)
        # Assert
        self.assertEqual(list(matches), ["1"])
        got = matches["1"][0]
        self.assertEqual(got["match"], {"method": "postcode-exact", "evidence": "postcode-exact LS211LG", "confidence": "high"})
        self.assertEqual(ambiguous, [])

    def test_domain_match_and_webmail_rejected(self):
        # Arrange (rule d)
        schools = [school(1, "St John's CE Primary School", "DA5 1AA", "http://www.stjohns-bexley.org.uk/")]
        charities = [charity(10, "ST JOHNS PTA", email="pta@stjohns-bexley.org.uk"),
                     charity(11, "ST JOHNS PTFA", email="stjohnsptfa@gmail.com"),
                     charity(12, "BEXLEY MUSIC CENTRE PARENTS ASSOCIATION", email="info@stjohns-bexley.org.uk")]
        # Act
        matches, _ = pass2(schools, charities)
        # Assert
        self.assertEqual([c["charity_number"] for c in matches["1"]], [10])
        self.assertEqual(matches["1"][0]["match"]["method"], "domain")
        self.assertEqual(matches["1"][0]["match"]["evidence"], "domain stjohns-bexley.org.uk (email)")
        self.assertIsNone(pta.email_domain("stjohnsptfa@gmail.com"))
        self.assertIsNone(pta.email_domain("x@hotmail.co.uk"))
        self.assertEqual(pta.email_domain("Pta@WWW.Stjohns-Bexley.org.uk"), "stjohns-bexley.org.uk")

    def test_predecessor_match_via_cp1252_links_csv(self):
        # Arrange (rule c): the charity names the school's former name, read from a GIAS links.csv saved in cp1252.
        with tempfile.TemporaryDirectory() as tmp:
            links = Path(tmp) / "links.csv"
            links.write_bytes(('"URN","LinkURN","LinkName","LinkType","LinkEstablishedDate"\n'
                               '1,900,"Newnham Middle School","Predecessor","01-09-2016"\n'
                               '900,901,"Pilgrim Lower School – Bedford","Predecessor - merged","01-09-2005"\n'
                               '2,800,"Rhyl Community Primary School","Successor - merged","31-08-2021"\n').encode("cp1252"))
            # Act
            preds = pta.load_predecessors(links)
        schools = [school(1, "Castle Newnham School", "MK41 9DT", phase="Primary"), school(2, "Grasmere Primary", "MK41 9AA")]
        charities = [charity(10, "NEWNHAM MIDDLE SCHOOL PTA", removed="2017-03-01"), charity(11, "CASTLE NEWNHAM PTA", removed="2017-03-01")]
        matches, _ = pass2(schools, charities, areas={10: ["Bedford"], 11: ["Bedford"]}, preds=preds, councils={"822": "Bedford"})
        # Assert
        self.assertEqual(preds, {"1": ["Newnham Middle School", "Pilgrim Lower School – Bedford"], "900": ["Pilgrim Lower School – Bedford"]})
        self.assertEqual(sorted(c["charity_number"] for c in matches["1"]), [10, 11])
        by_number = {c["charity_number"]: c["match"] for c in matches["1"]}
        self.assertEqual(by_number[10], {"method": "predecessor", "evidence": "predecessor 'Newnham Middle School' unique in council area", "confidence": "high"})
        self.assertEqual(by_number[11]["method"], "council-unique")

    def test_council_unique_match_and_council_name_mapping(self):
        # Arrange (rule a): a removed charity has no address; its council area and unique name place it.
        schools = [school(1, "Woodlea Primary School", "GU33 7AA"), school(2, "Grasmere Primary School", "GU33 7AB")]
        charities = [charity(10, "FRIENDS OF WOODLEA PRIMARY SCHOOL", removed="2015-01-01"),
                     charity(11, "FRIENDS OF LIPHOOK SCHOOL", removed="2015-01-01")]
        # Act
        matches, ambiguous = pass2(schools, charities, areas={10: ["Hampshire"], 11: ["Hampshire"]})
        # Assert
        self.assertEqual(list(matches), ["1"])
        self.assertEqual(matches["1"][0]["match"], {"method": "council-unique", "evidence": "council-unique in Hampshire", "confidence": "high"})
        self.assertEqual(ambiguous, [])
        councils = {"940": "Westmorland and Furness", "942": "Cumberland", "884": "Herefordshire, County of", "801": "Bristol, City of", "204": "Hackney"}
        self.assertEqual(pta.council_codes("Cumbria", councils), ["940", "942"])
        self.assertEqual(pta.council_codes("Herefordshire", councils), ["884"])
        self.assertEqual(pta.council_codes("City of Bristol", councils), ["801"])
        self.assertEqual(pta.council_codes("Hackney", councils), ["204"])
        self.assertEqual(pta.council_codes("Cardiff", councils), [])

    def test_council_unique_rejects_a_namesake_and_exports_several_fit(self):
        # Arrange
        schools = [school(1, "Darrick Wood Infant & Nursery School", "BR6 8ER", town="Orpington", phase="Primary"),
                   school(2, "Darrick Wood Junior School", "BR6 8EQ", town="Orpington", phase="Primary"),
                   school(3, "Darrick Wood School", "BR6 8ER", town="Orpington", phase="Secondary")]
        charities = [charity(10, "DARRICK WOOD SCHOOL PARENTS AND STAFF ASSOCIATION", removed="2001-01-01",
                             address=("Darrick Wood School", "Lovibonds Avenue", "Orpington", "Kent"))]
        # Act
        matches, ambiguous = pass2(schools, charities, areas={10: ["Bromley"]}, councils={"305": "Bromley"})
        # Assert
        self.assertEqual(matches, {})
        self.assertEqual(len(ambiguous), 1)
        row = ambiguous[0]
        self.assertEqual(row["kind"], "several_fit")
        self.assertEqual(sorted(row), ["address", "also_fits_independent", "area", "area_of_benefit", "candidates", "charity_name",
                                       "charity_number", "kind", "latest_income", "objects", "postcode", "recent_returns", "removed",
                                       "status", "town"])
        self.assertEqual(row["area"], ["Bromley"])
        self.assertEqual(row["town"], "Orpington")
        self.assertEqual(row["removed"], "2001-01-01")
        self.assertEqual([c["urn"] for c in row["candidates"]], ["1", "2", "3"])
        self.assertEqual(sorted(row["candidates"][0]), ["already_matched", "name", "phase", "postcode", "predecessor_names", "town", "urn"])
        self.assertEqual(row["candidates"][2]["phase"], "Secondary")

    def test_girls_school_pta_needs_a_girls_school(self):
        # Arrange: Alderley Edge School for Girls (independent, not in the register) must not fall onto the mixed primary;
        # Invicta Grammar's PTA keeps its match because the register says Invicta is a girls' school.
        schools = [school(1, "Alderley Edge Community Primary School", "SK9 7UZ", gender="Mixed"),
                   school(2, "Invicta Grammar School", "ME14 5DS", gender="Girls", phase="Secondary")]
        charities = [charity(10, "ALDERLEY EDGE SCHOOL FOR GIRLS PARENTS AND FRIENDS' ASSOCIATION", "SK9 7UZ"),
                     charity(11, "FRIENDS OF INVICTA GRAMMAR SCHOOL FOR GIRLS", "ME14 5DS")]
        objects = {10: ("TO ADVANCE THE EDUCATION OF THE PUPILS OF ALDERLEY EDGE SCHOOL FOR GIRLS", "")}
        # Act
        pass1, _ = pta.match(schools, charities)
        matches, _ = pass2(schools, charities, objects=objects)
        # Assert
        self.assertEqual(list(pass1), ["2"])
        self.assertEqual(list(matches), ["2"])

    def test_gias_phase_settles_a_tie(self):
        # Arrange (G8): 'X Primary PTA' against X Primary and the secondary X Academy.
        schools = [school(1, "Wyvern Primary School", "SO50 1AA", phase="Primary"), school(2, "Wyvern Academy", "SO50 1AB", phase="Secondary")]
        charities = [charity(10, "WYVERN PRIMARY PTA", removed="2012-01-01")]
        # Act
        matches, _ = pass2(schools, charities, areas={10: ["Hampshire"]})
        # Assert
        self.assertEqual(list(matches), ["1"])

    def test_objects_name_the_school(self):
        # Arrange (rule b): the charity name says nothing distinctive; the objects name Costock school.
        schools = [school(1, "Costock CofE Primary School", "LE12 6XA"), school(2, "Rempstone Primary", "LE12 6RH")]
        charities = [charity(10, "FRIENDS OF THE SCHOOL", removed="2009-01-01")]
        objects = {10: ("TO ADVANCE THE EDUCATION OF THE PUPILS AT COSTOCK CHURCH OF ENGLAND PRIMARY SCHOOL BY PROVIDING FACILITIES.", "COSTOCK")}
        # Act
        matches, _ = pass2(schools, charities, areas={10: ["Nottinghamshire"]}, objects=objects, councils={"891": "Nottinghamshire"})
        # Assert
        self.assertEqual(list(matches), ["1"])
        self.assertEqual(matches["1"][0]["match"]["method"], "objects")
        self.assertIn("objects name 'costock", matches["1"][0]["match"]["evidence"])

    def test_objects_tell_farnborough_grange_from_grange_infant(self):
        # Arrange (rule b vs a, G5): the name alone fits Grange Infant; the objects say Farnborough Grange. Rules disagree: no match.
        schools = [school(1, "Grange Infant School", "PO13 0AA", town="Gosport", phase="Primary"),
                   school(2, "Farnborough Grange Infant School", "GU14 8AA", town="Farnborough", phase="Primary")]
        charities = [charity(10, "GRANGE INFANT SCHOOL PTA", removed="2011-01-01")]
        objects = {10: ("TO ADVANCE THE EDUCATION OF PUPILS AT FARNBOROUGH GRANGE INFANT SCHOOL.", "THE CATCHMENT AREA OF FARNBOROUGH GRANGE INFANT SCHOOL")}
        # Act
        matches, ambiguous = pass2(schools, charities, areas={10: ["Hampshire"]}, objects=objects)
        # Assert
        self.assertEqual(matches, {})
        self.assertEqual([(r["kind"], [c["urn"] for c in r["candidates"]]) for r in ambiguous], [("single_fit_blocked", ["1"])])

    def test_address_town_match(self):
        # Arrange (rule e): no area, different postcode, but the address names the school's town.
        schools = [school(1, "South Tawton Primary School", "EX20 2JX", town="Okehampton"), school(2, "Okehampton Primary", "EX20 1AA", town="Okehampton"),
                   school(3, "South Tawton Primary School", "NE65 0AA", town="Morpeth", la_code="929", council="Northumberland")]
        charities = [charity(10, "SOUTH TAWTON PARENT TEACHER ASSOCIATION", "EX20 2TA", address=("The School", "South Zeal", "Okehampton", "Devon"))]
        # Act
        matches, _ = pass2(schools, charities, councils={"878": "Devon", "929": "Northumberland"})
        # Assert
        self.assertEqual(list(matches), ["1"])
        self.assertEqual(matches["1"][0]["match"], {"method": "address-town", "evidence": "address-town 'Okehampton' unique in Devon", "confidence": "high"})

    def test_activity_words_reject_but_place_names_survive(self):
        # Arrange (G3): a music society is not a PTA; 'Holmes Chapel' and 'Rugby High' are places.
        schools = [school(1, "Hymers College", "HU3 1LW"), school(2, "Holmes Chapel Primary School", "CW4 7DX"),
                   school(3, "Rugby High School", "CV22 7RE", phase="Secondary")]
        charities = [charity(10, "FRIENDS OF HYMERS COLLEGE MUSIC SOCIETY", "HU3 1LW"),
                     charity(11, "HOLMES CHAPEL PRIMARY SCHOOL PTA", "CW4 7DX"),
                     charity(12, "RUGBY HIGH SCHOOL PARENTS ASSOCIATION", "CV22 7RE")]
        # Act
        matches, _ = pass2(schools, charities)
        # Assert
        self.assertEqual(sorted(matches), ["2", "3"])
        self.assertEqual(pta.out_of_scope_words("FRIENDS OF HYMERS COLLEGE MUSIC SOCIETY", pta._school_record(schools[0])), {"music"})
        self.assertEqual(pta.out_of_scope_words("HOLMES CHAPEL PRIMARY SCHOOL PTA", pta._school_record(schools[1])), set())

    def test_saint_only_held_until_the_postcode_agrees(self):
        # Arrange (G4): a bare saint's name unique in the council is not enough on its own.
        schools = [school(1, "St Peter's CE Primary School", "CH60 0AA", town="Heswall"), school(2, "Grasmere Primary", "CH60 0AB")]
        held = [charity(10, "FRIENDS OF ST PETERS SCHOOL", removed="2014-01-01")]
        released = [charity(10, "FRIENDS OF ST PETERS SCHOOL", "CH60 0AA")]
        # Act
        matches_held, ambiguous = pass2(schools, held, areas={10: ["Wirral"]}, councils={"344": "Wirral"})
        matches_released, _ = pass2(schools, released, areas={10: ["Wirral"]}, councils={"344": "Wirral"})
        # Assert
        self.assertEqual(matches_held, {})
        self.assertEqual([(r["kind"], [c["urn"] for c in r["candidates"]]) for r in ambiguous], [("flagged_single_fit", ["1"])])
        self.assertEqual(matches_released["1"][0]["match"], {"method": "postcode-exact", "confidence": "high",
                                                             "evidence": "postcode-exact CH600AA; council-unique in Wirral"})

    def test_shared_infant_junior_pta_goes_to_both(self):
        # Arrange: one PTA for the infant and junior schools on a shared site, found by postcode and by council name.
        schools = [school(1, "Widcombe Infant School", "BA2 4LA", town="Bath"), school(2, "Widcombe Junior School", "BA2 4LB", town="Bath"),
                   school(3, "Bathwick St Mary Primary School", "BA2 6AA", town="Bath"), school(4, "Kingswood Prep", "BA1 1AA", town="Bath", type_group="Independent schools")]
        charities = [charity(10, "WIDCOMBE SCHOOLS PTA", "BA2 4LA"), charity(11, "FRIENDS OF WIDCOMBE SCHOOLS", removed="2008-01-01"),
                     charity(12, "WIDCOMBE JUNIOR SCHOOL PTA", "BA2 4LB")]
        # Act
        matches, _ = pass2(schools, charities, areas={11: ["Bath and North East Somerset"]}, councils={"800": "Bath and North East Somerset"})
        # Assert
        self.assertEqual([c["charity_number"] for c in matches["1"]], [10, 11])
        self.assertEqual([c["charity_number"] for c in matches["2"]], [10, 11, 12])
        self.assertEqual(matches["1"][0]["shared_with"], ["2"])
        self.assertEqual(matches["2"][0]["shared_with"], ["1"])
        self.assertEqual(matches["2"][1]["match"]["method"], "council-unique")
        self.assertNotIn("shared_with", matches["2"][2])

    def test_independent_target_and_predating_charity_rejected(self):
        # Arrange (G1, G2)
        schools = [school(1, "Felsted School", "CM6 3LL", type_group="Independent schools"), school(2, "Felsted Primary School", "CM6 3EW"),
                   school(3, "Newtown Free School", "CM6 3ZZ", open_date="2012-09-01")]
        charities = [charity(10, "FRIENDS OF FELSTED SCHOOL", "CM6 3LL"), charity(11, "NEWTOWN SCHOOL PTA", removed="2005-06-01")]
        # Act
        matches, _ = pass2(schools, charities, areas={10: ["Essex"], 11: ["Essex"]}, councils={"881": "Essex"})
        # Assert
        self.assertEqual(matches, {})

    def test_report_lists_pass2_rules(self):
        # Arrange
        matches = {"1": [dict(pta._charity_record(charity(10, "POOL PTA"), "postcode-exact", "postcode-exact LS211LG; council-unique in Leeds"))]}
        # Act
        text = pta.report(matches, [], {"candidates": 3, "ambiguous": 2, "ambiguous_kinds": {"several_fit": 2}, "llm": 1, "crawl": 0},
                          {"1": "Pool School"}, 1, 2.0)
        # Assert
        self.assertIn("- By method: postcode-exact 1", text)
        self.assertIn("council-unique 1, postcode-exact 1", text)
        self.assertIn("Ambiguous charities exported for adjudication: 2 (several_fit 2)", text)
        self.assertIn("## 1 random `postcode-exact` matches for review", text)


class PartATest(unittest.TestCase):
    def test_latest_part_a_row_is_attached(self):
        # Arrange
        matches = {"1": [pta._charity_record(charity(10, "X PTA"), "postcode", "e")], "2": [pta._charity_record(charity(11, "Y PTA"), "postcode", "e")]}
        rows = [{"registered_charity_number": 10, "fin_period_end_date": "2023-08-31T00:00:00", "count_volunteers": 12,
                 "charity_raises_funds_from_public": True, "charity_has_trading_subsidiary": False, "ar_due_date": "2024-06-30T00:00:00"},
                {"registered_charity_number": 10, "fin_period_end_date": "2024-08-31T00:00:00", "count_volunteers": 15,
                 "charity_raises_funds_from_public": True, "charity_has_trading_subsidiary": None, "ar_due_date": "2025-06-30T00:00:00"},
                {"registered_charity_number": 99, "fin_period_end_date": "2024-08-31T00:00:00", "count_volunteers": 1}]
        # Act
        covered = pta.attach_parta(matches, iter(rows))
        # Assert
        self.assertEqual(covered, 1)
        self.assertEqual(matches["1"][0]["parta"], {"count_volunteers": 15, "raises_funds_from_public": True, "trading_subsidiary": None,
                                                    "ar_due_date": "2025-06-30", "fin_period_end": "2024-08-31"})
        self.assertNotIn("parta", matches["2"][0])


class MergeTest(unittest.TestCase):
    def test_llm_answers_merge_once_with_medium_confidence(self):
        # Arrange
        matches = {"2": [pta._charity_record(charity(12, "Z PTA"), "postcode", "e")]}
        by_number = {10: charity(10, "FRIENDS OF WOODLEA SCHOOL"), 11: charity(11, "GRASMERE PTA"), 12: charity(12, "Z PTA"), 13: charity(13, "Q PTA")}
        llm = {"answers": {"10": {"urn": "1", "confidence": 0.95, "reason": "Woodlea", "name_consistent": True, "accepted": True},
                           "11": {"urn": "1", "confidence": 0.5, "reason": "x", "name_consistent": True, "accepted": False},
                           "12": {"urn": "1", "confidence": 0.99, "reason": "already placed", "name_consistent": True, "accepted": True},
                           "13": {"urn": "77", "confidence": 0.99, "reason": "unknown school", "name_consistent": True, "accepted": True}}}
        # Act
        added = pta.merge_llm(matches, llm, by_number, {"1", "2"})
        # Assert
        self.assertEqual(added, 1)
        self.assertEqual([c["charity_number"] for c in matches["1"]], [10])
        self.assertEqual(matches["1"][0]["match"], {"method": "llm", "evidence": "Woodlea", "confidence": "medium"})
        self.assertEqual([c["charity_number"] for c in matches["2"]], [12])

    def test_crawl_hits_merge_when_the_charity_reads_as_a_pta(self):
        # Arrange
        matches = {"2": [pta._charity_record(charity(12, "Z PTA"), "postcode", "e")]}
        by_number = {10: charity(10, "WILLIAM PATTEN SCHOOL FUND"), 11: charity(11, "PATTEN EDUCATIONAL TRUST"),
                     12: charity(12, "Z PTA"), 13: charity(13, "GRASMERE PTFA"), 14: charity(14, "LINKED PTA", linked=2)}
        crawl = {"schools": {"1": [{"charity_number": 10, "source_url": "https://wp.sch.uk/pta", "evidence": "Our PTA is registered charity 10"},
                                   {"charity_number": 11, "source_url": "https://wp.sch.uk/about", "evidence": "registered charity 11"},
                                   {"charity_number": 12, "source_url": "https://wp.sch.uk/pta", "evidence": "PTA charity 12"},
                                   {"charity_number": 13, "source_url": "https://wp.sch.uk/pta", "evidence": "charity 13"},
                                   {"charity_number": 14, "source_url": "https://wp.sch.uk/pta", "evidence": "PTA charity 14"}],
                             "9": [{"charity_number": 13, "source_url": "https://other", "evidence": "PTA"}]}}
        # Act
        added = pta.merge_crawl(matches, crawl, by_number, {"1", "2"})
        # Assert
        self.assertEqual(added, 2)
        got = {c["charity_number"]: c["match"] for c in matches["1"]}
        self.assertEqual(sorted(got), [10, 13])
        self.assertEqual(got[10], {"method": "website-crawl", "evidence": "https://wp.sch.uk/pta", "confidence": "high"})
        self.assertEqual([c["charity_number"] for c in matches["2"]], [12])
        self.assertNotIn("9", matches)


class MainTest(unittest.TestCase):
    def test_writes_shared_format(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "england").mkdir()
            (tmp / "england/las.json").write_text(json.dumps({"las": [{"la_code": "204", "name": "Hackney"}]}), encoding="utf-8")
            (tmp / "la" / "204").mkdir(parents=True)
            (tmp / "la" / "204" / "schools.json").write_text(json.dumps(
                {"schools": [school(130932, "William Patten Primary School", "N16 0NX", town="London", phase="Primary"),
                             school(100269, "Grasmere Primary School", "N16 0AA", town="London", phase="Primary"),
                             school(100000, "Hackney Free and Parochial CofE Secondary School", "E9 6NR", phase="Secondary"),
                             school(100001, "Shoreditch Prep", "N1 6AA", type_group="Independent schools")]}), encoding="utf-8")
            (tmp / "charity").mkdir()
            (tmp / "charity" / "publicextract.charity.json").write_text("﻿" + json.dumps(
                [charity(1103834, "WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION", "N16 0NX"),
                 charity(1, "WILLIAM PATTEN HOUSING TRUST", "N16 0NX"),
                 charity(2, "FRIENDS OF GRASMERE SCHOOL", removed="2012-01-01"),
                 charity(3, "FRIENDS OF PAROCHIAL SCHOOL", removed="2012-01-01"),
                 charity(4, "HACKNEY FREE SCHOOL FUND", "E9 6NR")]), encoding="utf-8")
            (tmp / "charity" / "publicextract.charity_annual_return_history.json").write_text(json.dumps(
                [{"registered_charity_number": 1103834, "fin_period_end_date": "2025-08-31T00:00:00",
                  "total_gross_income": 48547.0, "total_gross_expenditure": 50100.0, "suppression_ind": False}]), encoding="utf-8")
            (tmp / "charity" / "publicextract.charity_area_of_operation.json").write_text(json.dumps(
                [{"registered_charity_number": 2, "linked_charity_number": 0, "geographic_area_type": "Local Authority", "geographic_area_description": "Hackney"},
                 {"registered_charity_number": 3, "linked_charity_number": 0, "geographic_area_type": "Local Authority", "geographic_area_description": "Hackney"}]), encoding="utf-8")
            (tmp / "charity" / "publicextract.charity_governing_document.json").write_text(json.dumps(
                [{"registered_charity_number": 2, "linked_charity_number": 0, "charitable_objects": "FOR PUPILS AT GRASMERE SCHOOL", "area_of_benefit": "HACKNEY"}]), encoding="utf-8")
            (tmp / "charity" / "publicextract.charity_annual_return_parta.json").write_text(json.dumps(
                [{"registered_charity_number": 1103834, "fin_period_end_date": "2025-08-31T00:00:00", "count_volunteers": 20,
                  "charity_raises_funds_from_public": True, "charity_has_trading_subsidiary": False, "ar_due_date": "2026-06-30T00:00:00"}]), encoding="utf-8")
            (tmp / "crawl.json").write_text(json.dumps({"generated": "2026-11-07", "user_agent": "x", "schools": {
                "100000": [{"charity_number": 4, "source_url": "https://hfps.sch.uk/pta", "evidence": "PTA registered charity 4"}]}}), encoding="utf-8")
            out, rep, amb = tmp / "out" / "pta.json", tmp / "REPORT.md", tmp / "out" / "ambiguous.jsonl"
            # Act
            pta.main(["--charity-dir", str(tmp / "charity"), "--site-data", str(tmp), "--out", str(out), "--report", str(rep),
                      "--ambiguous", str(amb), "--links", str(tmp / "missing.csv"), "--llm", str(tmp / "missing.json"), "--crawl", str(tmp / "crawl.json")])
            data = json.loads(out.read_text(encoding="utf-8"))
            text = rep.read_text(encoding="utf-8")
            ambiguous = [json.loads(l) for l in amb.read_text(encoding="utf-8").splitlines()]
        # Assert
        self.assertEqual(data["licence"], "Open Government Licence v3.0 (Charity Commission register)")
        self.assertEqual(sorted(data), ["generated", "licence", "schools", "source"])
        self.assertEqual(sorted(data["schools"]), ["100000", "100269", "130932"])
        patten = data["schools"]["130932"][0]
        self.assertEqual(patten["history"], [{"period_end": "2025-08", "income": 48547.0, "expenditure": 50100.0}])
        self.assertEqual(sorted(patten), ["charity_number", "history", "latest_income", "match", "name", "parta", "registered", "removed", "status"])
        self.assertEqual(patten["parta"]["count_volunteers"], 20)
        self.assertEqual(data["schools"]["100269"][0]["match"]["method"], "council-unique")
        self.assertEqual(data["schools"]["100269"][0]["match"]["evidence"], "council-unique in Hackney; objects name 'grasmere school'")
        self.assertEqual(data["schools"]["100000"][0]["match"]["method"], "website-crawl")
        self.assertEqual([r["charity_number"] for r in ambiguous], [3])
        self.assertEqual(ambiguous[0]["kind"], "partial_name")
        self.assertEqual(ambiguous[0]["recent_returns"], 0)
        self.assertIn("| William Patten Primary School | WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION (1103834) | tokens william,patten; postcode N160NX |", text)
        self.assertIn("Candidate charities (main, parents' association by name): 3", text)
        self.assertIn("from the website crawl: 1", text)


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

    def test_independent_schools_are_not_loaded_unless_asked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "england").mkdir()
            (root / "la/999").mkdir(parents=True)
            (root / "england/las.json").write_text(json.dumps({"las": [{"la_code": "999", "name": "Testshire"}]}), encoding="utf-8")
            (root / "la/999/schools.json").write_text(json.dumps({"schools": [
                {"urn": 1, "name": "State Primary", "type_group": "Academies"},
                {"urn": 2, "name": "The German School", "type_group": "Independent schools"}]}), encoding="utf-8")
            self.assertEqual([s["urn"] for s in pta.load_schools(root)], [1])
            everyone = pta.load_schools(root, all_schools=True)
            self.assertEqual([(s["urn"], pta.is_state_funded(s), s["la_code"], s["council"]) for s in everyone],
                             [(1, True, "999", "Testshire"), (2, False, "999", "Testshire")])


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


@unittest.skipUnless(PTA_JSON.exists() and SITE_DATA.exists(), "real pta.json not present")
class RealOutputTest(unittest.TestCase):
    def test_pta_json_covers_william_patten_and_nine_thousand_state_schools(self):
        # Arrange
        data = json.loads(PTA_JSON.read_text(encoding="utf-8"))
        state = {str(s["urn"]) for s in pta.load_schools(SITE_DATA)}
        # Act
        patten = {c["charity_number"] for c in data["schools"].get("130932", [])}
        covered = set(data["schools"]) & state
        # Assert
        self.assertIn(1103834, patten)
        self.assertGreaterEqual(len(covered), 9000)
        self.assertEqual(set(data["schools"]) - state, set(), "pta.json names schools that are not state-funded")


if __name__ == "__main__":
    unittest.main()
