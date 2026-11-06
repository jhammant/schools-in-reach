"""Offline regression cases for the PTA matching review."""

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.money import pta


def school(urn, name, postcode):
    return {"urn": urn, "name": name, "postcode": postcode, "phase": "Primary"}


def charity(number, name, postcode):
    return {
        "registered_charity_number": number,
        "linked_charity_number": 0,
        "charity_name": name,
        "charity_registration_status": "Registered",
        "date_of_registration": "2020-01-01T00:00:00",
        "charity_contact_postcode": postcode,
        "latest_income": 1000,
    }


class PtaReviewTest(unittest.TestCase):
    def test_phase_word_cannot_resolve_an_unknown_competitor(self):
        # Arrange: both schools are primary, share a postcode and have the same
        # distinctive tokens. Only one happens to say "Primary" in its name.
        schools = [
            school(1, "Ash Primary School", "N16 0NX"),
            school(2, "Ash Academy", "N16 0NX"),
        ]
        charities = [charity(10, "ASH PRIMARY SCHOOL PTA", "N16 0NX")]

        # Act
        matches, rejections = pta.match(schools, charities)

        # Assert: missing phase words do not prove that school 2 is ineligible.
        self.assertEqual(matches, {}, "An unresolved district-token tie must not attribute money to either school")
        self.assertIn(10, [r["charity_number"] for r in rejections])

    def test_sector_uniqueness_rejection_is_recorded(self):
        # Arrange: the contact is in school 1's sector, but the school's tokens
        # are shared by another school in the same outward postcode district.
        schools = [
            school(1, "Willow Infant School", "N16 0NX"),
            school(2, "Willow Junior School", "N16 1NX"),
        ]
        charities = [charity(10, "WILLOW SCHOOL PTA", "N16 0ZZ")]

        # Act
        matches, rejections = pta.match(schools, charities)

        # Assert: ambiguity must appear in the review report's source data.
        self.assertEqual(matches, {})
        self.assertIn(10, [r["charity_number"] for r in rejections], "Sector-only ambiguities are silently lost")

    def test_main_only_matches_english_councils(self):
        # Arrange: site/data/la contains multiple nations, while england/las
        # identifies the English councils that this pipeline is meant to use.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "data"
            (site / "england").mkdir(parents=True)
            (site / "england/las.json").write_text(json.dumps({
                "las": [{"la_code": "204", "name": "Hackney"}],
            }), encoding="utf-8")
            for code, name, nation, record in [
                ("204", "Hackney", "England", school(1, "Willow Primary School", "N16 0NX")),
                ("666", "Powys", "Wales", school(2, "Bryn Primary School", "SA9 2PT")),
            ]:
                council = site / "la" / code
                council.mkdir(parents=True)
                (council / "schools.json").write_text(json.dumps({
                    "la": {"code": code, "name": name, "nation": nation},
                    "schools": [record],
                }), encoding="utf-8")
            charity_dir = root / "charities"
            charity_dir.mkdir()
            (charity_dir / "publicextract.charity.json").write_text(json.dumps([
                charity(10, "WILLOW PRIMARY SCHOOL PTA", "N16 0NX"),
                charity(20, "BRYN PRIMARY SCHOOL PTA", "SA9 2PT"),
            ]), encoding="utf-8")
            (charity_dir / "publicextract.charity_annual_return_history.json").write_text("[]", encoding="utf-8")
            output, report = root / "out/pta.json", root / "REPORT.md"

            # Act
            pta.main([
                "--site-data", str(site), "--charity-dir", str(charity_dir),
                "--out", str(output), "--report", str(report),
            ])
            result = json.loads(output.read_text(encoding="utf-8"))

        # Assert
        self.assertEqual(set(result["schools"]), {"1"}, "Non-English councils must not enter the English PTA output")
