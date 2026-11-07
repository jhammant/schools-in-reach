"""Offline regressions for the area review; no external data is required."""

import json
from pathlib import Path
import tempfile
import unittest

from pipeline.money import areas
from pipeline.money.build_money import school_rows
from pipeline.money.test_areas import lsoa_feature, make_site, row, school, square


class AreasReviewTest(unittest.TestCase):
    def test_conversion_year_keeps_financial_return_fields_together(self):
        # Arrange: both complete returns map to the display year 2024-25.
        maintained = row("100001", "2025-03", 1_000_000, 1_100_000,
                         -50_000, pupils=100)
        academy = row("140001", "2025-08", 2_000_000, 1_900_000,
                      100_000, source="AAR", pupils=200)
        history = {"100001": [maintained], "140001": [academy]}
        rows = school_rows("140001", history, {"140001": ["100001"]})

        # Act
        entries = areas.school_years(rows, [])

        # Assert: a timeline point must use the source and pupils of its return.
        expected = {
            -50_000: ("CFR", 100, -500, 10_000, 11_000, 9_000),
            100_000: ("AAR", 200, 500, 10_000, 9_500, 9_000),
        }
        self.assertTrue(entries)
        for entry in entries:
            self.assertEqual(
                (entry["source"], entry["pupils"], entry["reserve_pp"],
                 entry["income_pp"], entry["spend_pp"], entry["grant_pp"]),
                expected[entry["reserve"]],
            )

    def test_catchment_excludes_own_lsoa_when_centroid_is_outside(self):
        # Arrange: the school is inside the southern edge of its large LSOA;
        # only a neighbouring LSOA's centroid is within 0.1 miles of the school.
        with tempfile.TemporaryDirectory() as tmp:
            schools = [school("100001", "At the edge", lsoa="own")]
            admissions = {"primary": {"100001": {
                "years": {"2025": {"max_distance": 0.1}}
            }}}
            data = make_site(Path(tmp), schools, admissions=admissions)
            own = lsoa_feature("own", 51.5545, -0.06, 10, 10, 90, 80)
            own["geometry"] = square(51.5545, -0.06, half=0.005)
            near = lsoa_feature("near", 51.549, -0.06, 2, 2, 20, 30)
            near["geometry"] = square(51.549, -0.06, half=0.0004)
            far = lsoa_feature("far", 51.6, -0.06, 1, 1, 10, 10)
            (data / "la/204/lsoa.geojson").write_text(json.dumps({
                "type": "FeatureCollection", "features": [own, near, far],
            }), encoding="utf-8")

            # Act
            result = areas.school_profile(
                schools[0], "204", data, ctx=areas.Context(data)
            )["area"]["catchment"]

            # Assert
            self.assertIsNotNone(result)
            self.assertEqual(result["lsoas"], 1)
            self.assertEqual(result["imd_decile"], 2)
            self.assertEqual(result["pct_level4_plus"], 20)

    def test_catchment_uses_polygon_centroid_not_vertex_density(self):
        # Arrange: the second LSOA is a rectangle centred 1.33 km north,
        # outside the 0.5-mile (0.80 km) radius. Extra collinear vertices on
        # its southern boundary do not move the rectangle's centroid.
        with tempfile.TemporaryDirectory() as tmp:
            schools = [school("100001", "Near a long LSOA", lsoa="own")]
            admissions = {"primary": {"100001": {
                "years": {"2025": {"max_distance": 0.5}}
            }}}
            data = make_site(Path(tmp), schools, admissions=admissions)
            own = lsoa_feature("own", 51.55, -0.06, 2, 2, 20, 30)
            outside = lsoa_feature("outside", 51.562, -0.06, 10, 10, 90, 80)
            west, east, south, north = -0.061, -0.059, 51.552, 51.572
            ring = [[west + (east - west) * i / 20, south] for i in range(21)]
            ring += [[east, north], [west, north], [west, south]]
            outside["geometry"] = {"type": "Polygon", "coordinates": [ring]}
            far = lsoa_feature("far", 51.6, -0.06, 1, 1, 10, 10)
            (data / "la/204/lsoa.geojson").write_text(json.dumps({
                "type": "FeatureCollection", "features": [own, outside, far],
            }), encoding="utf-8")

            # Act
            result = areas.school_profile(
                schools[0], "204", data, ctx=areas.Context(data)
            )["area"]["catchment"]

            # Assert
            self.assertIsNotNone(result)
            self.assertEqual(result["lsoas"], 1)
            self.assertEqual(result["imd_decile"], 2)

    def test_catchment_includes_nearby_lsoa_across_council_boundary(self):
        # Arrange: one eligible centroid on either side of a council boundary.
        with tempfile.TemporaryDirectory() as tmp:
            schools = [school("100001", "At the council border", lsoa="own")]
            admissions = {"primary": {"100001": {
                "years": {"2025": {"max_distance": 0.1}}
            }}}
            data = make_site(Path(tmp), schools, admissions=admissions)
            (data / "england/las.json").write_text(json.dumps({"las": [
                {"la_code": "204", "name": "Hackney", "region": "London"},
                {"la_code": "205", "name": "Islington", "region": "London"},
            ]}), encoding="utf-8")
            own = lsoa_feature("own", 51.55, -0.06, 2, 2, 20, 30)
            own["geometry"] = square(51.55, -0.06, half=0.0003)
            far = lsoa_feature("far", 51.6, -0.06, 1, 1, 10, 10)
            near = lsoa_feature("near", 51.5508, -0.06, 10, 10, 90, 80)
            near["geometry"] = square(51.5508, -0.06, half=0.0003)
            (data / "la/205").mkdir()
            (data / "la/205/schools.json").write_text(
                json.dumps({"schools": []}), encoding="utf-8"
            )
            for code, features in (("204", [own, far]), ("205", [near])):
                (data / "la" / code / "lsoa.geojson").write_text(json.dumps({
                    "type": "FeatureCollection", "features": features,
                }), encoding="utf-8")

            # Act
            result = areas.school_profile(
                schools[0], "204", data, ctx=areas.Context(data)
            )["area"]["catchment"]

            # Assert: council borders are not part of the distance criterion.
            self.assertIsNotNone(result)
            self.assertEqual(result["lsoas"], 2)
            self.assertEqual(result["imd_decile"], 6)


if __name__ == "__main__":
    unittest.main()
