"""deploy/money: the pre-deploy site check (check_site.py) against temp dirs, and the nginx security headers.

The Content-Security-Policy is checked against what a fixture build actually loads: every external script, stylesheet
and image in the built pages, the libraries the shipped scripts load on demand (PptxGenJS, mp4-muxer, qrcode), the
map tiles and api.postcodes.io. The policy was also exercised in Chromium against a fixture build while it was
written (the map drew its tiles, a presentation downloaded and a video was made, with no violations). It ships because
it is safe: if a page ever needs something the policy cannot allow safely, drop the CSP line from
security-headers.conf (keeping the other headers) rather than ship a policy that breaks a page.

The one inline event handler a build may still carry is the compare finder's onsubmit="return false" (build_money's
render_compare, being removed); the CSP blocks it harmlessly because app.js stops that form submitting itself.
Nothing here starts nginx or touches the network.
"""

import base64
import hashlib
import importlib.util
import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "money"
ASSETS = ROOT / "pipeline" / "money" / "assets"


def load_check_site():
    spec = importlib.util.spec_from_file_location("check_site", DEPLOY / "check_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_site = load_check_site()


def headers_conf():
    """{header: value} from security-headers.conf's add_header lines."""
    text = (DEPLOY / "security-headers.conf").read_text(encoding="utf-8")
    return {k: v.strip('"') for k, v in re.findall(r'^add_header ([\w-]+) (".*?"|\S+) always;$', text, re.M)}


def parse_csp(value):
    """{directive: [sources]}."""
    out = {}
    for part in value.split(";"):
        words = part.split()
        if words:
            out[words[0]] = words[1:]
    return out


def allows(sources, url):
    """Does a CSP source list allow url (an absolute https:, data: or blob: URL)? Host sources match any path; a path
    ending in '/' matches everything under it; any other path matches exactly."""
    u = urlsplit(url)
    for s in sources:
        if s in (f"{u.scheme}:",):
            return True
        if not s.startswith("https://"):
            continue
        su = urlsplit(s)
        if u.scheme != "https" or su.netloc != u.netloc:
            continue
        if su.path in ("", "/") or (su.path.endswith("/") and u.path.startswith(su.path)) or u.path == su.path:
            return True
    return False


def make_site(root, postcodes=2_000, extra=()):
    """A temp site_money with that many postcode district files (N16 and E8 among them) and extra relative files."""
    folder = root / "data" / "postcodes"
    folder.mkdir(parents=True)
    names = ["N16", "E8"] + [f"ZZ{i}" for i in range(max(0, postcodes - 2))]
    for name in names[:postcodes]:
        (folder / f"{name}.json").write_text("{}", encoding="utf-8")
    for rel in extra:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x", encoding="utf-8")
    return root


class PostcodeCheckTest(unittest.TestCase):
    def test_enough_districts_with_n16_and_e8_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            site = make_site(Path(tmp), 2_000)
            # Act / Assert
            self.assertEqual(check_site.postcode_problems(site), [])

    def test_too_few_districts_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            site = make_site(Path(tmp), 1_999)
            # Act
            problems = check_site.postcode_problems(site)
            # Assert
            self.assertEqual(problems, ["only 1,999 postcode district files in data/postcodes/ (need 2,000)"])

    def test_missing_n16_or_e8_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            site = make_site(Path(tmp), 2_100)
            (site / "data/postcodes/E8.json").unlink()
            # Act
            problems = check_site.postcode_problems(site)
            # Assert
            self.assertEqual(problems, ["data/postcodes/ lacks E8.json"])

    def test_no_postcode_folder_fails_both_ways(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Act
            problems = check_site.postcode_problems(Path(tmp))
            # Assert
            self.assertEqual(len(problems), 2)
            self.assertIn("N16.json, E8.json", problems[1])


class SiteCheckTest(unittest.TestCase):
    """check_site.main as deploy.sh runs it: exit 0 for a good site, 1 with every problem listed for a bad one."""

    def run_main(self, site):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check_site.main(["check_site.py", str(site)])
        return code, out.getvalue(), err.getvalue()

    def good_site(self, root):
        reads = sorted(check_site.reads(ASSETS))
        files = [g.replace("*", "x") for g in reads if not g.startswith("data/postcodes/")] + [f"assets/{name}" for name in check_site.SCRIPTS]
        site = make_site(root, 2_000, files)
        for name in check_site.SCRIPTS:
            (site / "assets" / name).write_text((ASSETS / name).read_text(encoding="utf-8"), encoding="utf-8")
        return site

    def test_a_complete_site_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            site = self.good_site(Path(tmp))
            # Act
            code, out, err = self.run_main(site)
            # Assert
            self.assertEqual((code, err), (0, ""))
            self.assertIn("2,000 postcode districts", out)

    def test_apple_double_files_and_a_missing_read_fail_the_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            site = self.good_site(Path(tmp))
            (site / "data/s/._x.json").write_text("junk", encoding="utf-8")
            (site / "data/wrapped/context.json").unlink()
            # Act
            code, _, err = self.run_main(site)
            # Assert
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("Deploy aborted: "))
            self.assertIn("nothing matches /data/wrapped/context.json, which wrapped.js reads", err)
            self.assertIn("1 macOS '._*' files (first: data/s/._x.json)", err)
            self.assertEqual(check_site.apple_double(site), ["data/s/._x.json"])

    def test_wrong_arguments(self):
        # Act
        with redirect_stderr(io.StringIO()):
            code = check_site.main(["check_site.py"])
        # Assert
        self.assertEqual(code, 2)


class DeployScriptTest(unittest.TestCase):
    def test_deploy_runs_the_site_check_before_packing(self):
        # Arrange
        script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
        # Assert
        self.assertIn("set -euo pipefail", script)
        call = script.index('python3 "$HERE/check_site.py" "$REPO/site_money"')
        self.assertLess(script.index("python3 -m pipeline.money.build_money"), call)
        self.assertLess(call, script.index("zstd -q -19"))
        self.assertIn("COPYFILE_DISABLE=1 tar cf -", script)

    def test_dockerfile_installs_the_headers_where_the_template_includes_them(self):
        # Arrange
        docker = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
        template = (DEPLOY / "nginx.conf.template").read_text(encoding="utf-8")
        # Assert
        self.assertIn("COPY security-headers.conf /etc/nginx/snippets/security-headers.conf", docker)
        self.assertIn("include /etc/nginx/snippets/security-headers.conf;", template)


class NginxHeadersTest(unittest.TestCase):
    """add_header is not inherited by a location with its own add_header, so each one must include the headers."""

    def setUp(self):
        self.template = (DEPLOY / "nginx.conf.template").read_text(encoding="utf-8")
        self.headers = headers_conf()

    def test_every_location_that_adds_a_header_includes_the_security_headers(self):
        # Arrange
        lines = [ln.strip() for ln in self.template.splitlines() if ln.strip().startswith("location")]
        # Assert
        self.assertGreaterEqual(len(lines), 8)
        for line in lines:
            if "add_header" in line:
                self.assertIn("include /etc/nginx/snippets/security-headers.conf;", line, line)
        server = self.template.split("server {", 1)[1].split("\n  location", 1)[0]
        self.assertIn("include /etc/nginx/snippets/security-headers.conf;", server)
        self.assertEqual(self.template.count("{"), self.template.count("}"))

    def test_the_fixed_headers(self):
        self.assertEqual(self.headers["Strict-Transport-Security"], "max-age=31536000")
        self.assertEqual(self.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(self.headers["X-Frame-Options"], "$money_frame_options")

    def test_only_the_embed_badge_can_be_framed(self):
        # Arrange
        maps = dict(re.findall(r"map \$uri \$(\w+) \{(.*?)\}", self.template, re.S))
        # Assert
        self.assertIn('default "\'none\'";', maps["money_frame_ancestors"])
        self.assertIn('~^/embed/ "*";', maps["money_frame_ancestors"])
        self.assertIn('default "DENY";', maps["money_frame_options"])
        self.assertIn('~^/embed/ "";', maps["money_frame_options"])  # an empty value: nginx leaves the header out
        self.assertEqual(parse_csp(self.headers["Content-Security-Policy"])["frame-ancestors"], ["$money_frame_ancestors"])

    def test_a_list_page_that_no_longer_exists_redirects_to_the_first_page(self):
        # Arrange
        blocks = re.findall(r"location ~ (\^/\(council\|constituency\|trust\)/[^ ]+) \{(.*?)\n  \}", self.template, re.S)
        rules = {pattern: body for pattern, body in blocks}
        # Act
        index_rule = rules.get("^/(council|constituency|trust)/(\\d+)/?$", "")
        area_rule = rules.get("^/(council|constituency|trust)/([^/]+)/(\\d+)/?$", "")
        # Assert: a missing numbered page goes to its list's first page, an existing one is served, headers still sent
        self.assertIn("if (!-e $request_filename) { return 301 /$1/$is_args$args; }", index_rule)
        self.assertIn("if (!-e $request_filename) { return 301 /$1/$2/$is_args$args; }", area_rule)
        for body in (index_rule, area_rule):
            self.assertIn("try_files $uri $uri/ =404;", body)
            self.assertIn("include /etc/nginx/snippets/security-headers.conf;", body)

    def test_dotfiles_are_refused(self):
        self.assertIn("location ~ /\\. { deny all; }", self.template)
        self.assertLess(self.template.index("location ~ /\\."), self.template.index("location ~* \\.geojson$"))


class ContentSecurityPolicyTest(unittest.TestCase):
    """The CSP allows exactly what a fixture build loads, and nothing that would make it pointless."""

    @classmethod
    def setUpClass(cls):
        from pipeline.money import build_money, site
        from pipeline.money.test_build_money import full_rows, make_site as fixture_site, school, write_dsg
        cls.site = site
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        schools = [school(100000 + i, f"Peer {i}", constituency="Hackney North and Stoke Newington", postcode="N16 0NX",
                          lat=51.56 + i / 1000, lon=-0.075) for i in range(6)]
        rows = [r for i in range(6) for r in full_rows(str(100000 + i), reserve=40_000 + 5_000 * i)]
        site_dir, history, links, pta = fixture_site(root, [("204", "Hackney")], {"204": schools}, rows)
        cls.out = root / "site_money"
        build_money.build(site_dir, history, links, pta, out=cls.out, dsg_path=write_dsg(root / "dsg.json"))
        cls.csp = parse_csp(headers_conf()["Content-Security-Policy"])
        cls.pages = {p: p.read_text(encoding="utf-8") for p in cls.out.rglob("*.html")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_unsafe_script_sources(self):
        # Assert
        for directive, sources in self.csp.items():
            self.assertNotIn("'unsafe-eval'", sources, directive)
            if directive != "style-src":
                self.assertNotIn("'unsafe-inline'", sources, directive)
        self.assertEqual(self.csp["default-src"], ["'self'"])
        self.assertEqual(self.csp["object-src"], ["'none'"])
        self.assertEqual(self.csp["base-uri"], ["'self'"])
        self.assertNotIn("*", self.csp["script-src"])

    def test_every_inline_script_is_hashed_and_no_handler_attribute_needs_one(self):
        # Arrange
        hashes = set()
        handlers = set()
        for html in self.pages.values():
            for attrs, body in re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", html, re.S):
                kind = re.search(r'type="([^"]+)"', attrs)
                if kind and kind.group(1) in ("application/json", "application/ld+json"):
                    continue  # data blocks are never run
                hashes.add("'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode() + "'")
            handlers.update(re.findall(r'\son[a-z]+="[^"]*"', html))
        boot = self.site.AUDIENCE_BOOT.removeprefix("<script>").removesuffix("</script>")
        # Assert
        self.assertTrue(hashes)
        self.assertLessEqual(hashes, set(self.csp["script-src"]))
        self.assertIn("'sha256-" + base64.b64encode(hashlib.sha256(boot.encode()).digest()).decode() + "'", self.csp["script-src"])
        self.assertLessEqual(handlers, {' onsubmit="return false"'}, "app.js makes the compare finder's handler redundant")
        self.assertIn('form.addEventListener("submit", function (e) { e.preventDefault();', (ASSETS / "app.js").read_text(encoding="utf-8"))

    def test_every_external_resource_in_the_built_pages_is_allowed(self):
        # Arrange
        checks = []
        for html in self.pages.values():
            checks += [("script-src", u) for u in re.findall(r'<script[^>]*\bsrc="(https://[^"]+)"', html)]
            for tag in re.findall(r"<link[^>]*>", html):
                href = re.search(r'href="(https://[^"]+)"', tag)
                if href and 'rel="stylesheet"' in tag:
                    checks.append(("style-src", href.group(1)))
                    # Leaflet's stylesheet draws images from beside it (images/layers.png ...)
                    checks.append(("img-src", urljoin(href.group(1), "images/layers.png")))
            checks += [("img-src", u) for u in re.findall(r'<img[^>]*\bsrc="(https://[^"]+)"', html)]
            checks += [("connect-src", u) for u in re.findall(r'data-tiles="(https://[^"]+)"', html)]
        # Assert
        names = {urlsplit(u).path.rsplit("/", 1)[-1] for _, u in checks}
        self.assertLessEqual({"leaflet.min.js", "protomaps-leaflet.js", "leaflet.min.css", "uk.pmtiles"}, names)
        for directive, url in checks:
            with self.subTest(directive=directive, url=url):
                self.assertTrue(allows(self.csp[directive], url))

    def test_every_library_and_service_the_scripts_load_is_allowed(self):
        # Arrange: script URL constants (loaded on demand as <script>) and fetches to other hosts
        checks = []
        for name in ("app.js", "deck.js", "wrapped.js", "map.js", "tools.js", "trend.js"):
            js = (self.out / "assets" / name).read_text(encoding="utf-8")
            checks += [("script-src", u) for u in re.findall(r'_URL = "(https://[^"]+\.js)"', js)]
            checks += [("connect-src", u + "N16%200NX") for u in re.findall(r'fetch\("(https://[^"]+)"', js)]
        # Assert
        names = {urlsplit(u).path.rsplit("/", 1)[-1] for _, u in checks}
        self.assertLessEqual({"pptxgen.bundle.js", "mp4-muxer.js", "qrcode.min.js", "N16%200NX"}, names)
        self.assertIn(("connect-src", "https://api.postcodes.io/postcodes/N16%200NX"), checks)
        for directive, url in checks:
            with self.subTest(directive=directive, url=url):
                self.assertTrue(allows(self.csp[directive], url))

    def test_the_policy_is_pinned_to_the_versions_in_use(self):
        # A library on another version, or another package on the same CDN, is refused.
        self.assertFalse(allows(self.csp["script-src"], "https://cdn.jsdelivr.net/npm/pptxgenjs@3.11.0/dist/pptxgen.bundle.js"))
        self.assertFalse(allows(self.csp["script-src"], "https://cdn.jsdelivr.net/npm/evil@1.0.0/x.js"))
        self.assertFalse(allows(self.csp["connect-src"], "https://example.org/collect"))
        self.assertTrue(allows(self.csp["img-src"], "data:image/gif;base64,R0lGODlh"))
        self.assertTrue(allows(self.csp["media-src"], "blob:https://money.schoolsinreach.com/1"))


if __name__ == "__main__":
    sys.exit(unittest.main())
