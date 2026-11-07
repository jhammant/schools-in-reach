"""The build-to-fetch contract (audits C104, C106): every same-site file the shipped JavaScript fetches exists in a build.

A small fixture site is built into a temp dir with pipeline/money/test_build_money's helpers. The paths the scripts
read come from deploy/money/check_site.py, which deploy.sh also runs on the real build: each asset's 'Reads:' header
and every fetch / fetchJSON / getJSON call become globs (data/s/*.json, data/a/council-*.json, ...). Each glob must
match a built file; every data-preview and data-drill target in the built pages must resolve; and no '._*' file may
ship. No network: nothing is fetched, the files are only looked for.
"""

import importlib.util
import re
import sys
import tempfile
import unittest
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("check_site", ROOT / "deploy" / "money" / "check_site.py")
check_site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_site)

# What the scripts are known to read today; the parser must find at least these (it may find more).
EXPECTED = {"data/s/*.json", "data/sx/*.json", "data/a/*.json", "data/a/council-*.json", "data/a/england.json",
            "data/map/measures.json", "data/map/schools.json", "data/map/councils.geojson", "data/map/constituencies.geojson",
            "data/wrapped/context.json", "data/postcodes/*.json", "assets/glossary.json", "data/search.json"}


class FetchContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline.money import build_money
        from pipeline.money.test_build_money import full_rows, make_site, row, school, write_dsg
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        # Arrange: a council with a constituency, an academy in a trust and schools with postcodes and positions, so
        # the build writes every kind of file (school, series, area, map, postcode district, video context).
        schools = [school(100000 + i, f"Peer {i}", constituency="Hackney North and Stoke Newington", postcode="N16 0NX",
                          lat=51.56 + i / 1000, lon=-0.075) for i in range(6)]
        schools.append(school(140001, "Good Academy", type="Academy converter", trust="Good Trust", postcode="E8 1AA", lat=51.55, lon=-0.07))
        rows = [r for i in range(6) for r in full_rows(str(100000 + i), reserve=40_000 + 5_000 * i)]
        rows += [row("140001", end, 2_000_000, 2_100_000, -50_000, source="AAR", trust="Good Trust") for end in ("2024-08", "2025-08")]
        site_dir, history, links, pta = make_site(root, [("204", "Hackney")], {"204": schools}, rows)
        cls.out = root / "site_money"
        build_money.build(site_dir, history, links, pta, out=cls.out, dsg_path=write_dsg(root / "dsg.json"))
        cls.reads = check_site.reads(cls.out / "assets")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_built_scripts_are_the_shipped_ones(self):
        for name in check_site.SCRIPTS:
            with self.subTest(script=name):
                built, shipped = self.out / "assets" / name, ROOT / "pipeline/money/assets" / name
                self.assertEqual(built.read_bytes(), shipped.read_bytes())

    def test_the_parser_finds_every_known_read(self):
        # Assert
        self.assertLessEqual(EXPECTED, set(self.reads), sorted(EXPECTED - set(self.reads)))
        self.assertIn("app.js", self.reads["data/postcodes/*.json"])
        self.assertIn("wrapped.js", self.reads["data/wrapped/context.json"])
        for glob in self.reads:
            self.assertFalse(glob.startswith(("/", "http")), glob)

    def test_every_read_matches_a_built_file(self):
        # Act
        missing = check_site.missing_reads(self.out)
        # Assert
        self.assertEqual(missing, {})
        for glob, scripts in sorted(self.reads.items()):
            with self.subTest(glob=glob, scripts=sorted(scripts)):
                self.assertTrue(any(p.is_file() for p in self.out.glob(glob)))

    def test_every_preview_and_drill_target_in_the_pages_resolves(self):
        # Arrange
        targets = set()
        for page in self.out.rglob("*.html"):
            html = page.read_text(encoding="utf-8")
            for kind, ident in re.findall(r'data-preview="(school|area):([^"]+)"', html):
                targets.add(f"data/{'s' if kind == 'school' else 'a'}/{unescape(ident)}.json")
            for ref in re.findall(r'data-drill="(/data/[^"#]+)', html):
                targets.add(ref.lstrip("/"))
        # Assert
        self.assertTrue(any(t.startswith("data/s/") for t in targets))
        self.assertTrue(any(t.startswith("data/sx/") for t in targets))
        for target in sorted(targets):
            with self.subTest(target=target):
                self.assertTrue((self.out / target).is_file())

    def test_no_apple_double_files(self):
        self.assertEqual(check_site.apple_double(self.out), [])


class ParserTest(unittest.TestCase):
    """check_site's reading of a script, on small made-up scripts."""

    def test_reads_header_paragraph_with_placeholders(self):
        # Arrange
        js = ("/* x.js\n   Reads: /data/s/<urn>.json, /data/a/council-<code>.json (with its 'dsg' block),\n"
              "          /data/sx/<urn>.json#m:<metric>, /assets/glossary.json.\n   Stores: localStorage x (not a read). */\nvar a;")
        # Act / Assert
        self.assertEqual(check_site.header_reads(js), {"data/s/*.json", "data/a/council-*.json", "data/sx/*.json", "assets/glossary.json"})

    def test_fetch_calls_concatenations_helpers_and_fallbacks(self):
        # Arrange
        js = ('function getJSON(rel) { return fetch("/data/" + rel).then(f); }\n'
              'getJSON("sx/" + u + ".json");\n'
              'fetchJSON("/data/postcodes/" + encodeURIComponent(d) + ".json");\n'
              'fetchJSON(urls.measures || "/data/map/measures.json");\n'
              'fetch(url, { credentials: "same-origin" });\n'
              'fetch("https://api.postcodes.io/postcodes/" + encodeURIComponent(full));\n'
              "loadJSON('/data/a/england.json');\n")
        # Act
        globs = check_site.fetch_reads(js)
        # Assert
        self.assertEqual(globs, {"data/sx/*.json", "data/postcodes/*.json", "data/map/measures.json", "data/a/england.json"})


if __name__ == "__main__":
    sys.exit(unittest.main())
