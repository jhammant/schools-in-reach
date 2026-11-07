"""Tests for pipeline/money/map_page.py (unit C1, the map explorer).

Run: python3 -m pytest -q pipeline/money/test_map_page.py
Fixtures are built here or generated into tempfile dirs; the real boundary files are read only, when present.
"""

from __future__ import annotations

import inspect
import json
import math
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from pipeline.money import map_page as M
from pipeline.money import site
from pipeline.money import status as health

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "pipeline/money/data/gold/130932.json"
PATH_RE = re.compile(r"^/(?:[a-z0-9-]+/)*$")
LIMIT = 48_000
# Built from pieces so this file never contains the phrases it checks for.
BANNED = ["poor" + " school", "fail" + "ing", "wor" + "st", "bank" + "rupt", "scan" + "dal", "no" + " pta", "307" + "k"]
SOURCES = [Path(M.__file__), REPO / "pipeline/money/assets/map.js", REPO / "pipeline/money/assets/map.css"]


def S(**values):
    """One by_year split, every S key None unless given (None is 'withheld', never 0)."""
    keys = ["schools", "in_deficit", "in_deficit_pct", "heading", "deficit_total", "deficit_pp", "reserve_median_pp",
            "income_pp_median", "spend_pp_median", "grant_pp_median", "pta_pp_median", "pta_schools", "donations_pp_median"]
    out = {k: None for k in keys}
    out.update(values)
    return out


def area(name, by_year=None, pupils=None, dsg=None, **extra):
    doc = {"name": name, "pupils_by_year": pupils or {}, "schools_by_year": {},
           "by_year": {y: {"all": s, "council-run": s, "academy": S()} for y, s in (by_year or {}).items()},
           "dsg": dsg or {}, "statuses_latest": {}}
    doc.update(extra)
    return doc


def make_areas():
    return {
        "england": area("England", {"2017-18": S(in_deficit_pct=9.0), "2024-25": S(in_deficit_pct=11.04, schools=20000, in_deficit=2208),
                                    "2025-26": S(in_deficit_pct=12.4, deficit_pp=-498.6, reserve_median_pp=402.4, grant_pp_median=7012.4)},
                        pupils={"2025-26": 7_543_210.25}, dsg={"2025-26": {"balance": -6.4e9, "per_pupil": -848.7}}),
        "councils": {
            "204": area("Hackney", {"2017-18": S(in_deficit_pct=30.0),
                                    "2024-25": S(in_deficit_pct=None, schools=4),
                                    "2025-26": S(in_deficit_pct=18.18, schools=55, in_deficit=10, deficit_pp=-612.49, reserve_median_pp=-15.5,
                                                 grant_pp_median=7400.6, spend_pp_median=8100.4, pta_pp_median=21.6)},
                        pupils={"2025-26": 25432.5}, dsg={"2024-25": {"balance": -2.0e7, "per_pupil": -790.2}, "2025-26": {"balance": None, "per_pupil": None}}),
            "201": area("City of London", {"2025-26": S(schools=1)}),
            "202": area("Camden", {"2025-26": S(in_deficit_pct=8.0, grant_pp_median=6900.0, gov_pp_median=7050.0, pta_median_pp=40.0, fsm_pct=21.0)},
                        fsm_pct_by_year={"2025-26": 99.0}),
        },
        "constituencies": {
            "E14001272": area("Hackney North and Stoke Newington", {"2025-26": S(in_deficit_pct=20.0)},
                              dsg={"2025-26": {"balance": -1.0, "per_pupil": -5.0}}, fsm_pct_by_year={"2025-26": 31.25}),
        },
        "regions": {"London": area("London")},
        "trusts": {},
    }


def ring(cx, cy, r, n):
    pts = [[round(cx + r * math.cos(2 * math.pi * i / n), 6), round(cy + r * math.sin(2 * math.pi * i / n), 6)] for i in range(n)]
    return pts + [list(pts[0])]


def write_geojson(folder, name, features):
    path = Path(folder) / name
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


def feature(props, geometry):
    return {"type": "Feature", "properties": props, "geometry": geometry}


ITEMS = [
    {"urn": 100001, "name": "Alpha Primary", "phase": "primary", "status": {"status": "in_deficit", "label": "In deficit"},
     "lat": 51.5501234, "lon": -0.0612345, "tags": {"governance": "council-run"}},
    {"urn": "100002", "name": "Beta Academy", "phase": "All-through", "status": "healthy", "academy": True,
     "school": {"lat": 51.6, "lon": -0.1}},
    {"urn": 100003, "name": "Gamma School", "phase": "nursery", "status": None, "lat": 52.0, "lon": 0.1},
    {"urn": 100004, "name": "Delta School (no coordinates)", "phase": "secondary", "status": "tight"},
    {"urn": 100005, "name": "Epsilon & Co", "phase": "something new", "status": "unknown_key", "lat": 53.0, "lon": -1.0,
     "tags": {"governance": "free school"}},
]


def fake_env(out, items=None, areas=None):
    """The env contract: write enforces the path regex, one write per path and the 48,000-byte limit."""
    written = {}

    def write(path, html):
        if not PATH_RE.match(path):
            raise ValueError(f"bad path {path!r}")
        if path in written:
            raise ValueError(f"{path} written twice")
        if len(html.encode("utf-8")) >= LIMIT:
            raise ValueError(f"{path} is {len(html.encode('utf-8'))} bytes")
        target = Path(out).joinpath(*[p for p in path.split("/") if p], "index.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        written[path] = html

    env = {"out": Path(out), "write": write, "page": site.page, "items": ITEMS if items is None else items,
           "areas": make_areas() if areas is None else areas, "today": "2026-11-07"}
    return env, written


def boundary_fixtures(folder):
    councils = write_geojson(folder, "councils.geojson", [
        feature({"la_code": "204", "name": "Hackney", "extra": 1}, {"type": "Polygon", "coordinates": [ring(-0.06, 51.55, 0.03, 40)]}),
        feature({"la_code": "202", "name": "Camden"}, {"type": "MultiPolygon", "coordinates": [[ring(-0.16, 51.55, 0.03, 30)]]}),
    ])
    constituencies = write_geojson(folder, "constituencies.geojson", [
        feature({"code": "E14001272", "name": "Hackney North and Stoke Newington"},
                {"type": "Polygon", "coordinates": [ring(-0.07, 51.56, 0.02, 400)]}),
    ])
    return councils, constituencies


def gold_item():
    """An item for William Patten Primary School built from the committed reference file."""
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    rows = []
    for year, doc in gold["years"].items():
        t = doc["totals"]["pipeline_finance_history"]
        rows.append({"year": year, "period_end": f"20{year[-2:]}-03-31", "period_months": 12, "source": "CFR", "phase": "primary",
                     **{k: t[k] for k in ("total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "grant_funding", "pupils")}})
    item = {"urn": int(gold["urn"]), "name": gold["name"], "phase": gold["phase"], "la": str(gold["la"]["code"]),
            "status": health.assess(rows), "rows": rows, "lat": 51.5592, "lon": -0.0663}
    return gold, item


# ----------------------------------------------------------------- geometry

class SimplifyTest(unittest.TestCase):
    def test_simplify_ring_keeps_closure_and_endpoints_and_removes_points(self):
        # Arrange
        points = ring(0, 52, 0.1, 360)
        # Act
        out = M.simplify_ring(points, 0.001)
        # Assert
        self.assertEqual(out[0], points[0])
        self.assertEqual(out[-1], points[-1])
        self.assertEqual(out[0], out[-1])
        self.assertLess(len(out), len(points))
        self.assertGreaterEqual(len(out), 4)

    def test_simplify_ring_never_goes_below_four_positions(self):
        # Arrange: a thin sliver that Douglas-Peucker would reduce to a line
        points = [[0, 0], [1, 0.00001], [2, 0], [1, -0.00001], [0, 0]]
        # Act
        out = M.simplify_ring(points, 0.5)
        # Assert
        self.assertEqual(len(out), 4)
        self.assertEqual(out[0], out[-1])

    def test_simplify_ring_closes_an_open_ring(self):
        # Arrange
        points = ring(0, 0, 1, 50)[:-1]
        # Act
        out = M.simplify_ring(points, 0.05)
        # Assert
        self.assertEqual(out[0], out[-1])

    def test_douglas_peucker_is_iterative(self):
        # Arrange
        body = inspect.getsource(M._significance).split("\n", 1)[1]
        points = ring(0, 0, 1, 100_000)
        # Act
        out = M.simplify_ring(points, 1e-4)
        # Assert
        self.assertNotIn("_significance(", body)
        self.assertIn("stack", body)
        self.assertGreaterEqual(len(out), 4)
        self.assertLess(len(out), 1000)

    def test_round_geometry_gives_at_most_four_decimals_and_no_repeats(self):
        # Arrange
        geom = {"type": "Polygon", "coordinates": [[[0.123456, 51.000001], [0.123459, 51.000004], [0.2, 51.1], [0.3, 51.0], [0.123456, 51.000001]]]}
        # Act
        out = M.round_geometry(geom)
        # Assert
        coords = out["coordinates"][0]
        for x, y in coords:
            for v in (x, y):
                self.assertLessEqual(len(repr(v).split(".")[1]) if "." in repr(v) else 0, 4)
        self.assertTrue(all(a != b for a, b in zip(coords, coords[1:])))
        self.assertEqual(coords[0], coords[-1])

    def test_collapsed_parts_are_dropped_but_the_largest_part_stays(self):
        # Arrange
        big, tiny = ring(0, 0, 1, 200), [[5, 5], [5.0001, 5], [5.00005, 5.00001], [5, 5]]
        multi = {"type": "MultiPolygon", "coordinates": [[tiny], [big]]}
        only_tiny = {"type": "MultiPolygon", "coordinates": [[tiny], [[[9, 9], [9.00001, 9], [9, 9.000001], [9, 9]]]]}
        # Act
        out = M.simplify_geometry(multi, 0.01)
        kept = M.simplify_geometry(only_tiny, 0.5)
        # Assert
        self.assertEqual(out["type"], "Polygon")
        self.assertGreaterEqual(len(out["coordinates"][0]), 4)
        self.assertEqual(kept["type"], "Polygon")
        self.assertEqual(kept["coordinates"][0][0], tiny[0])

    def test_build_geojson_reduces_properties_and_honours_the_budget(self):
        # Arrange
        feats = [feature({"code": f"E{i}", "name": f"Place {i}", "extra": "x"}, {"type": "Polygon", "coordinates": [ring(i, 52, 0.2, 2000)]})
                 for i in range(3)]
        plain = M.build_geojson(feats, "constituency-", "code", 10**9, False)
        budget = len(plain.encode("utf-8")) // 4
        # Act
        small = M.build_geojson(feats, "constituency-", "code", budget, True)
        # Assert
        doc = json.loads(small)
        self.assertLessEqual(len(small.encode("utf-8")), budget)
        self.assertEqual(doc["features"][0]["properties"], {"id": "constituency-E0", "code": "E0", "name": "Place 0"})
        self.assertEqual(len(doc["features"]), 3)
        with self.assertRaises(ValueError):
            M.build_geojson(feats, "council-", "code", budget, False)


@unittest.skipUnless(M.resolve(M.COUNCILS_SRC), "council boundaries not present")
class RealCouncilsTest(unittest.TestCase):
    def test_councils_geojson_fits_450k_with_153_features(self):
        # Arrange
        src = json.loads(M.resolve(M.COUNCILS_SRC).read_text(encoding="utf-8"))
        start = time.monotonic()
        # Act
        text = M.build_geojson(src["features"], "council-", "la_code", M.COUNCILS_BUDGET, False)
        # Assert
        doc = json.loads(text)
        self.assertLess(time.monotonic() - start, 60)
        self.assertLessEqual(len(text.encode("utf-8")), 450_000)
        self.assertEqual(len(doc["features"]), 153)
        props = doc["features"][0]["properties"]
        self.assertEqual(set(props), {"id", "code", "name"})
        self.assertEqual(props["id"], "council-" + props["code"])


@unittest.skipUnless(M.resolve(M.CONSTITUENCIES_SRC), "constituency boundaries not present")
class RealConstituenciesTest(unittest.TestCase):
    def test_constituencies_geojson_fits_1_5mb_with_all_543(self):
        # Arrange
        src = json.loads(M.resolve(M.CONSTITUENCIES_SRC).read_text(encoding="utf-8"))
        start = time.monotonic()
        # Act
        text = M.build_geojson(src["features"], "constituency-", "code", M.CONSTITUENCIES_BUDGET, True)
        # Assert
        doc = json.loads(text)
        self.assertLess(time.monotonic() - start, 60)
        self.assertLessEqual(len(text.encode("utf-8")), 1_500_000)
        self.assertEqual(len(doc["features"]), 543)
        codes = [f["properties"]["code"] for f in doc["features"]]
        self.assertEqual(len(set(codes)), 543)
        for f in doc["features"]:
            geom = f["geometry"]
            polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            self.assertTrue(polys, f["properties"]["code"])
            for poly in polys:
                self.assertGreaterEqual(len(poly[0]), 4)
                self.assertEqual(poly[0][0], poly[0][-1])


# ----------------------------------------------------------------- measures

class BuildMeasuresTest(unittest.TestCase):
    def test_none_is_omitted_never_zero(self):
        # Arrange
        areas = make_areas()
        # Act
        doc = M.build_measures(areas)
        # Assert
        hackney = doc["council"]["council-204"]["m"]
        self.assertEqual(hackney["pct_in_deficit"], {"2025-26": 18.2})
        self.assertNotIn("2024-25", hackney["pct_in_deficit"])
        self.assertNotIn(0, [v for series in hackney.values() for v in series.values()])

    def test_an_area_with_no_values_is_still_listed(self):
        # Arrange
        areas = make_areas()
        # Act
        doc = M.build_measures(areas)
        # Assert
        self.assertEqual(doc["council"]["council-201"]["name"], "City of London")
        self.assertEqual(doc["council"]["council-201"]["m"], {})
        self.assertEqual(doc["council"]["council-201"]["p"], "/council/city-of-london/")

    def test_constituency_links_use_the_page_path_not_the_ons_code(self):
        # Arrange: areas.json keys constituencies by ONS code; their pages are named after the constituency
        areas = make_areas()
        paths = {"Hackney North and Stoke Newington": "/constituency/hackney-north-and-stoke-newington/"}
        # Act
        doc = M.build_measures(areas, paths)
        # Assert
        self.assertEqual(doc["constituency"]["constituency-E14001272"]["p"], "/constituency/hackney-north-and-stoke-newington/")

    def test_the_map_opens_on_the_latest_year_england_has_figures_for(self):
        # Arrange: 2025-26 has council-run returns only, so the combined measure stops at 2024-25
        measures = {"years": ["2023-24", "2024-25", "2025-26"],
                    "england": {M.DEFAULT_MEASURE: {"2023-24": 12.7, "2024-25": 14.3}, "dsg_pp": {"2025-26": -848}}}
        # Act / Assert
        self.assertEqual(M.default_year(measures), "2024-25")
        self.assertEqual(M.default_year({"years": ["2024-25"]}), "2024-25")

    def test_years_before_2018_19_are_dropped(self):
        # Arrange
        areas = make_areas()
        # Act
        doc = M.build_measures(areas)
        # Assert
        self.assertEqual(doc["years"], ["2024-25", "2025-26"])
        self.assertNotIn("2017-18", doc["england"]["pct_in_deficit"])
        self.assertNotIn("2017-18", doc["council"]["council-204"]["m"].get("pct_in_deficit", {}))

    def test_aliases_first_found_wins(self):
        # Arrange
        areas = make_areas()
        # Act
        doc = M.build_measures(areas)
        # Assert
        camden, hackney = doc["council"]["council-202"]["m"], doc["council"]["council-204"]["m"]
        self.assertEqual(camden["gov_pp_median"], {"2025-26": 7050})
        self.assertEqual(hackney["gov_pp_median"], {"2025-26": 7401})
        self.assertEqual(camden["pta_median_pp"], {"2025-26": 40})
        self.assertEqual(hackney["pta_median_pp"], {"2025-26": 22})
        self.assertEqual(camden["fsm_pct"], {"2025-26": 21})
        self.assertEqual(doc["constituency"]["constituency-E14001272"]["m"]["fsm_pct"], {"2025-26": 31.2})

    def test_dsg_only_for_councils_and_england(self):
        # Arrange
        areas = make_areas()
        # Act
        doc = M.build_measures(areas)
        # Assert
        self.assertEqual(doc["england"]["dsg_pp"], {"2025-26": -849})
        self.assertEqual(doc["council"]["council-204"]["m"]["dsg_pp"], {"2024-25": -790})
        self.assertNotIn("dsg_pp", doc["constituency"]["constituency-E14001272"]["m"])
        self.assertEqual(doc["measures"]["dsg_pp"]["levels"], ["england", "council"])

    def test_rounding_and_meta(self):
        # Arrange
        areas = make_areas()
        # Act
        doc = M.build_measures(areas)
        # Assert
        self.assertEqual(doc["england"]["pupils"], {"2025-26": 7543210.2})
        self.assertEqual(doc["council"]["council-204"]["m"]["deficit_pp"], {"2025-26": -612})
        self.assertIsInstance(doc["council"]["council-204"]["m"]["deficit_pp"]["2025-26"], int)
        for key, meta in doc["measures"].items():
            self.assertEqual(set(meta), {"label", "unit", "signed", "scale", "source", "levels"}, key)
            self.assertIn(meta["unit"], ("pct", "gbp_pp", "pupils"))
            self.assertIn(meta["scale"], ("sequential", "diverging"))
        self.assertEqual(doc["measures"]["reserve_median_pp"]["scale"], "diverging")
        self.assertTrue(doc["measures"]["deficit_pp"]["signed"])

    def test_wrapper_and_missing_blocks_are_tolerated(self):
        # Arrange
        areas = make_areas()
        # Act
        wrapped = M.build_measures({"generated": "2026-11-07", "areas": areas})
        empty = M.build_measures({})
        none = M.build_measures(None)
        partial = M.build_measures({"england": None, "councils": {"999": None}})
        # Assert
        self.assertEqual(wrapped, M.build_measures(areas))
        self.assertEqual((empty["years"], empty["council"], empty["constituency"], empty["england"]), ([], {}, {}, {}))
        self.assertEqual(none, empty)
        self.assertEqual(partial["council"]["council-999"], {"name": "999", "p": "/council/999/", "m": {}})


# ----------------------------------------------------------------- schools

class BuildSchoolsTest(unittest.TestCase):
    def test_rows_skip_items_without_coordinates_and_codes_match_the_key(self):
        # Arrange
        items = ITEMS
        # Act
        doc = M.build_schools(items)
        # Assert
        key = doc["key"]
        self.assertEqual(key["status"], health.ORDER)
        self.assertEqual(key["fields"], ["urn", "lat", "lon", "status", "phase", "governance", "name"])
        rows = {r[0]: r for r in doc["rows"]}
        self.assertNotIn(100004, rows)
        self.assertEqual(rows[100001][:3], [100001, 51.5501, -0.0612])
        decoded = {urn: (key["status"][r[3]] if r[3] >= 0 else None, key["phase"][r[4]], key["governance"][r[5]]) for urn, r in rows.items()}
        self.assertEqual(decoded[100001], ("in_deficit", "primary", "council-run"))
        self.assertEqual(decoded[100002], ("healthy", "all_through", "academy"))
        self.assertEqual(decoded[100003], (None, "nursery", "council-run"))
        self.assertEqual(decoded[100005], (None, "other", "free school"))
        self.assertEqual(rows[100005][6], "Epsilon & Co")

    def test_over_budget_raises_rather_than_trimming(self):
        # Arrange
        items = ITEMS
        # Act / Assert
        with mock.patch.object(M, "SCHOOLS_BUDGET", 50):
            with self.assertRaises(ValueError):
                M.build_schools(items)

    def test_reference_school_status_and_pupils_come_from_the_gold_file(self):
        # Arrange
        gold, item = gold_item()
        latest = gold["years"]["2025-26"]["totals"]["pipeline_finance_history"]
        # Act
        read = M.read_item(dict(item, pupils=None))
        doc = M.build_schools([item])
        # Assert
        self.assertEqual(read["pupils"], latest["pupils"])
        self.assertEqual(item["status"]["reserve"], latest["revenue_reserve"])
        self.assertEqual(read["status"], "in_deficit")
        self.assertEqual(read["path"], site.page_path("school", gold["urn"], gold["name"]))
        self.assertEqual(doc["rows"][0][3], health.ORDER.index("in_deficit"))
        self.assertEqual(doc["rows"][0][0], int(gold["urn"]))


# ----------------------------------------------------------------- pages

class WritePagesTest(unittest.TestCase):
    def build(self, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        councils, constituencies = boundary_fixtures(tmp.name)
        env, written = fake_env(Path(tmp.name) / "out", **{k: v for k, v in kw.items() if k in ("items", "areas")})
        paths = {"councils_path": kw.get("councils_path", councils), "constituencies_path": kw.get("constituencies_path", constituencies)}
        result = M.write_pages(env, **paths)
        return Path(tmp.name) / "out", written, result

    def test_return_value_and_data_files(self):
        # Arrange / Act
        out, written, result = self.build()
        # Assert
        self.assertEqual(result, [("/map/", True), ("/map/constituencies/", True)])
        self.assertEqual(list(written), ["/map/", "/map/constituencies/"])
        for name in ("councils.geojson", "constituencies.geojson", "measures.json", "schools.json"):
            text = (out / "data/map" / name).read_text(encoding="utf-8")
            self.assertEqual(text, json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False), name)
        measures = json.loads((out / "data/map/measures.json").read_text(encoding="utf-8"))
        self.assertEqual(measures["generated"], "2026-11-07")
        councils = json.loads((out / "data/map/councils.geojson").read_text(encoding="utf-8"))
        self.assertEqual([f["properties"] for f in councils["features"]],
                         [{"id": "council-204", "code": "204", "name": "Hackney"}, {"id": "council-202", "code": "202", "name": "Camden"}])

    def test_map_page_has_controls_map_table_and_no_js_view(self):
        # Arrange / Act
        _, written, _ = self.build()
        html = written["/map/"]
        # Assert
        self.assertIn("<noscript>", html)
        self.assertRegex(html, r"<noscript>.*The map needs JavaScript.*lists every council.*href=\"/council/\".*</noscript>")
        self.assertIn('<table data-sortable id="mx-table"', html)
        self.assertIn('<select id="mx-measure" name="m">', html)
        self.assertIn('<option value="pct_in_deficit" selected>', html)
        self.assertIn('type="range" id="mx-year"', html)
        self.assertIn('<output id="mx-year-out" for="mx-year">2025-26</output>', html)
        self.assertIn('name="g" value="council" checked', html)
        self.assertIn('name="phase" value="primary" checked', html)
        self.assertIn('role="combobox"', html)
        self.assertIn('aria-controls="mx-q-list"', html)
        self.assertIn('role="listbox"', html)
        self.assertIn('data-tiles="https://tiles.schoolsinreach.com/tiles/uk.pmtiles"', html)
        self.assertIn('data-default-measure="pct_in_deficit"', html)
        self.assertIn('data-default-year="2025-26"', html)
        self.assertIn('data-years="[&quot;2024-25&quot;,&quot;2025-26&quot;]"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertRegex(html, r'<div id="mx-card"[^>]*role="dialog" aria-modal="false"[^>]*hidden>')
        self.assertIn('class="mx-close"', html)
        self.assertIn("England: 12.4%", html)
        self.assertIn('<a href="/council/hackney/">Hackney</a></th><td data-sort="18.2">18.2%</td>', html)
        self.assertIn('href="/map/constituencies/"', html)
        self.assertIn('<a href="/">Home</a> <span aria-hidden="true">›</span> <span aria-current="page">Map</span>', html)

    def test_libraries_are_pinned_once_with_verified_integrity(self):
        # Arrange / Act
        _, written, _ = self.build()
        html, source = written["/map/"], Path(M.__file__).read_text(encoding="utf-8")
        # Assert
        for url, sri in ((M.LEAFLET_CSS, M.LEAFLET_CSS_SRI), (M.LEAFLET_JS, M.LEAFLET_JS_SRI), (M.PROTOMAPS_JS, M.PROTOMAPS_JS_SRI)):
            self.assertEqual(html.count(url), 1, url)
            self.assertEqual(source.count(url), 1, url)
            self.assertIn(f'integrity="{sri}" crossorigin="anonymous"', html)
        self.assertIn('<link rel="stylesheet" href="/assets/map.css">', html)
        self.assertIn('<script src="/assets/map.js" defer></script>', html)
        self.assertLess(html.index(M.LEAFLET_JS), html.index("/assets/map.js"))
        self.assertLess(html.index(M.PROTOMAPS_JS), html.index("/assets/map.js"))

    def test_deficits_are_named_with_reasons_and_what_helps(self):
        # Arrange
        ifs = json.loads((REPO / "pipeline/money/data/ifs_context.json").read_text(encoding="utf-8"))
        why = ifs["framings"]["why_schools_go_into_deficit"]
        # Act
        _, written, _ = self.build()
        # Assert
        for path, html in written.items():
            self.assertIn(site.esc(why["text"]), html, path)
            self.assertIn("p.62–63", html, path)
            self.assertIn("What helps", html, path)

    def test_context_block_is_safe_json(self):
        # Arrange / Act
        _, written, _ = self.build()
        block = re.search(r'<script type="application/json" id="mx-context">(.*?)</script>', written["/map/"], re.S).group(1)
        # Assert
        self.assertNotIn("<", block)
        self.assertNotIn("&", block)
        ctx = json.loads(block)
        self.assertEqual(ctx["defaults"], {"m": "pct_in_deficit", "y": "2025-26", "g": "council"})
        self.assertEqual(ctx["data"]["council"], "/data/map/councils.geojson")
        self.assertIn("Statutory override", ctx["dsg_note"])
        self.assertIn("£5,000", ctx["pta_note"])
        self.assertEqual(ctx["measures"]["pct_in_deficit"]["key"], "pct_in_deficit")

    def test_missing_council_boundaries_are_said_in_words(self):
        # Arrange / Act
        out, written, _ = self.build(councils_path=Path("/nonexistent/councils.geojson"))
        # Assert
        self.assertFalse((out / "data/map/councils.geojson").exists())
        self.assertIn("Council boundaries aren't available", written["/map/"])
        self.assertIn('"council":null', re.search(r'id="mx-context">(.*?)</script>', written["/map/"]).group(1))

    def test_empty_inputs_still_write_both_pages(self):
        # Arrange / Act
        out, written, result = self.build(items=[], areas={})
        # Assert
        self.assertEqual([p for p, _ in result], ["/map/", "/map/constituencies/"])
        self.assertIn("Figures for this year aren't published yet.", written["/map/"])
        self.assertEqual(json.loads((out / "data/map/schools.json").read_text(encoding="utf-8"))["rows"], [])

    def test_all_543_constituencies_fit_the_page_budget(self):
        # Arrange: real names, the widest value on every row
        names = json.loads((REPO / "pipeline/money/data/constituencies_2024.json").read_text(encoding="utf-8"))
        areas = {"england": area("England", {"2025-26": S(in_deficit_pct=12.4)}),
                 "constituencies": {code: area(v["name"], {"2025-26": S(in_deficit_pct=100.0)}) for code, v in names.items()},
                 "councils": {str(200 + i): area(f"Kingston {i} upon Thames", {"2025-26": S(in_deficit_pct=100.0)}) for i in range(153)}}
        # Act
        _, written, _ = self.build(areas=areas)
        # Assert
        self.assertEqual(written["/map/constituencies/"].count("<tr><th>"), len(names))
        for path, html in written.items():
            self.assertLess(len(html.encode("utf-8")), LIMIT, path)

    def test_no_banned_words_in_pages_data_or_sources(self):
        # Arrange
        out, written, _ = self.build()
        texts = list(written.values()) + [p.read_text(encoding="utf-8") for p in (out / "data/map").iterdir()]
        texts += [p.read_text(encoding="utf-8") for p in SOURCES]
        # Act
        found = [(word, i) for i, text in enumerate(texts) for word in BANNED if word in text.lower()]
        # Assert
        self.assertEqual(found, [])

    def test_og_image_is_optional(self):
        # Arrange
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        councils, constituencies = boundary_fixtures(tmp.name)
        env, written = fake_env(Path(tmp.name) / "out")
        env["og_image"] = "https://money.schoolsinreach.com/og/map.png"
        # Act
        M.write_pages(env, councils_path=councils, constituencies_path=constituencies)
        # Assert
        self.assertIn('property="og:image" content="https://money.schoolsinreach.com/og/map.png"', written["/map/"])


if __name__ == "__main__":
    unittest.main()
