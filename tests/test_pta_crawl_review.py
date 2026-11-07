"""Offline regression cases for the A6 crawler review; no real sockets are used."""

import contextlib
import io
import json
import socket
import tempfile
import unittest
import urllib.request
import urllib.response
from email.message import Message
from pathlib import Path
from unittest import mock

from pipeline.money import pta_crawl


REGISTRY = {
    1103834: "WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION",
    1111114: "GRASMERE PRIMARY SCHOOL PTA",
    1111111: "FRIENDS OF ASHMOLE",
}


class Clock:
    def __init__(self, first_oversleep=0):
        self.now = 0.0
        self.first_oversleep = first_oversleep

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds + self.first_oversleep
        self.first_oversleep = 0


class Web:
    def __init__(self, pages, clock=None):
        self.pages = pages
        self.clock = clock or Clock()
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, self.clock.now))
        value = self.pages.get(url, (404, ""))
        status, body = value if isinstance(value, tuple) else (200, value)
        return status, url, body

    def fetcher(self):
        limiter = pta_crawl.RateLimiter(1.0, clock=self.clock.time, sleep=self.clock.sleep)
        return pta_crawl.Fetcher(self, limiter)


def school(urn=130932, name="William Patten Primary School", website="https://williampatten.example/"):
    return {"urn": urn, "name": name, "website": website, "type_group": "Local authority maintained schools"}


def write_input(root, schools):
    (root / "england").mkdir()
    (root / "la/999").mkdir(parents=True)
    (root / "england/las.json").write_text(json.dumps({
        "las": [{"la_code": "999", "name": "Testshire"}],
    }), encoding="utf-8")
    (root / "la/999/schools.json").write_text(json.dumps({"schools": schools}), encoding="utf-8")
    (root / "charity").mkdir()
    (root / "charity/publicextract.charity.json").write_text(json.dumps([
        {"registered_charity_number": number, "linked_charity_number": 0, "charity_name": name}
        for number, name in REGISTRY.items()
    ]), encoding="utf-8")


def run_main(root, web, *extra):
    out = root / "money/pta_crawl.json"
    with contextlib.redirect_stdout(io.StringIO()):
        pta_crawl.main([
            "--site-data", str(root), "--charity-dir", str(root / "charity"),
            "--out", str(out), "--workers", "1", *extra,
        ], fetcher=web.fetcher())
    return json.loads(out.read_text(encoding="utf-8"))


class CrawlerReviewTest(unittest.TestCase):
    def setUp(self):
        self.real_urlopen = urllib.request.urlopen
        for target in ("urllib.request.urlopen", "socket.create_connection"):
            patcher = mock.patch(target, side_effect=AssertionError(f"Real network forbidden: {target}"))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("Real socket forbidden"))
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextlib.contextmanager
    def http_responses(self, responses, clock, calls):
        def http_open(handler, request):
            url = request.full_url
            calls.append((url, clock.now))
            status, fields, body = responses.get(url, (404, {}, ""))
            headers = Message()
            headers["Content-Type"] = "text/html; charset=utf-8"
            for key, value in fields.items():
                headers[key] = value
            response = urllib.response.addinfourl(io.BytesIO(body.encode()), headers, url, status)
            response.msg = "Fixture response"
            return response

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        # Intercept the transport below redirect processing. This also works
        # if the crawler constructs an opener with a custom redirect policy.
        with mock.patch.object(urllib.request.HTTPHandler, "http_open", http_open), \
                mock.patch.object(urllib.request, "_opener", opener), \
                mock.patch.object(urllib.request, "urlopen", self.real_urlopen):
            yield

    def test_redirect_target_is_checked_against_robots(self):
        # Arrange: preserve urllib's real redirect processor, replacing only
        # its HTTP handler with in-memory HTTP responses.
        clock = Clock()
        calls = []
        responses = {
            "http://school.example/robots.txt": (200, {}, "User-agent: *\nDisallow: /private\n"),
            "http://school.example/": (302, {"Location": "/private"}, ""),
            "http://school.example/private": (200, {}, "<p>Private page</p>"),
        }

        limiter = pta_crawl.RateLimiter(1.0, clock=clock.time, sleep=clock.sleep)
        fetcher = pta_crawl.Fetcher(limiter=limiter)

        # Act
        with self.http_responses(responses, clock, calls):
            result = fetcher.get("http://school.example/")

        # Assert: following the redirect must not fetch the disallowed URL.
        self.assertIn("http://school.example/", [url for url, _ in calls])
        self.assertNotIn("http://school.example/private", [url for url, _ in calls], calls)
        self.assertNotEqual(result.status, "ok")

    def test_allowed_redirect_is_rate_limited(self):
        # Arrange: an ordinary homepage redirect remains a useful fetch, but
        # must not issue two requests to the same host at the same instant.
        clock = Clock()
        calls = []
        responses = {
            "http://school.example/robots.txt": (200, {}, "User-agent: *\nDisallow:\n"),
            "http://school.example/": (302, {"Location": "/home"}, ""),
            "http://school.example/home": (200, {}, "<p>School homepage</p>"),
        }
        limiter = pta_crawl.RateLimiter(1.0, clock=clock.time, sleep=clock.sleep)
        fetcher = pta_crawl.Fetcher(limiter=limiter)

        # Act
        with self.http_responses(responses, clock, calls):
            result = fetcher.get("http://school.example/")

        # Assert
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.url, "http://school.example/home")
        times = [time for _, time in calls]
        self.assertTrue(all(b - a >= 1.0 for a, b in zip(times, times[1:])), calls)

    def test_rejected_homepage_charity_does_not_stop_crawl(self):
        # Arrange: a news item names another school's PTA. The actual PTA is
        # available on a directly linked page within the six-page budget.
        web = Web({
            "https://williampatten.example/": (
                "<p>Grasmere Primary School PTA: registered charity 1111114.</p>"
                '<a href="/pta/">Our PTA</a>'
            ),
            "https://williampatten.example/pta/": "<p>Our PTFA: registered charity 1103834.</p>",
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_input(root, [school()])

            # Act
            output = run_main(root, web)

        # Assert
        numbers = [hit["charity_number"] for hit in output["schools"].get("130932", [])]
        self.assertEqual(numbers, [1103834], web.calls)

    def test_resume_retries_failed_pta_child_page(self):
        # Arrange: only the PTA page has a transient failure on the first run.
        first = Web({
            "https://williampatten.example/": '<a href="/pta/">PTA</a>',
            "https://williampatten.example/pta/": (503, ""),
        })
        recovered = Web({
            "https://williampatten.example/": '<a href="/pta/">PTA</a>',
            "https://williampatten.example/pta/": "<p>Our PTFA: registered charity 1103834.</p>",
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_input(root, [school()])
            run_main(root, first)

            # Act
            output = run_main(root, recovered, "--resume")

        # Assert: a failed child fetch is not a completed no-PTA result.
        numbers = [hit["charity_number"] for hit in output["schools"].get("130932", [])]
        self.assertEqual(numbers, [1103834], recovered.calls)

    def test_rate_limit_uses_actual_wakeup_time(self):
        # Arrange: one normal scheduling delay makes the first sleep wake
        # 250 ms late; later sleeps wake exactly on time.
        clock = Clock(first_oversleep=0.25)
        web = Web({
            "https://school.example/robots.txt": "User-agent: *\nDisallow:\n",
            "https://school.example/": "<p>School</p>",
            "https://school.example/pta/": "<p>PTA</p>",
        }, clock)
        fetcher = web.fetcher()

        # Act
        fetcher.get("https://school.example/")
        fetcher.get("https://school.example/pta/")

        # Assert: these are transport times, not the limiter's planned slots.
        self.assertEqual(len(web.calls), 3)
        times = [time for _, time in web.calls]
        self.assertTrue(all(b - a >= 1.0 for a, b in zip(times, times[1:])), web.calls)

    def test_distinct_query_homepages_are_both_crawled(self):
        # Arrange: a shared host serves two distinct school homepages by query.
        first = "https://schools.example/index.php?school=william-patten"
        second = "https://schools.example/index.php?school=grasmere"
        web = Web({
            first: "<p>William Patten PTFA: registered charity 1103834.</p>",
            second: "<p>Grasmere Primary School PTA: registered charity 1111114.</p>",
        })
        schools = [school(website=first), school(100001, "Grasmere Primary School", second)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_input(root, schools)

            # Act
            output = run_main(root, web)

        # Assert
        self.assertEqual({urn: [hit["charity_number"] for hit in hits]
                          for urn, hits in output["schools"].items()},
                         {"130932": [1103834], "100001": [1111114]}, web.calls)

    def test_evidence_retains_pta_wording_within_120_characters(self):
        # Arrange: the charity name needs the explicitly supported evidence
        # fallback. Its PTA wording is 103 characters from the bare number.
        text = "PTA " + "Our volunteers support events throughout the year. " * 2 + "1111111"
        web = Web({"https://ashmole.example/": "<p>" + text + "</p>"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_input(root, [school(100001, "Ashmole Primary School", "https://ashmole.example/")])

            # Act
            output = run_main(root, web)

        # Assert: the 90-character snippet must not erase qualifying evidence.
        numbers = [hit["charity_number"] for hit in output["schools"].get("100001", [])]
        self.assertEqual(numbers, [1111111])

    def test_two_argument_validate_accepts_pta_evidence(self):
        # Arrange: this is the public validate(candidates, registry) contract.
        candidates = [{
            "charity_number": 1111111,
            "evidence": "Friends of Ashmole is our PTA, registered charity 1111111",
            "context_url": "https://ashmole.example/pta/",
        }]

        # Act
        accepted = pta_crawl.validate(candidates, REGISTRY)

        # Assert
        self.assertEqual([hit["charity_number"] for hit in accepted], [1111111])
