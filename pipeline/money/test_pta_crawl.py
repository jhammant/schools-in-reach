"""Tests for the PTA website crawler; fixture HTML only, every real network open raises."""
import contextlib
import io
import json
import socket
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from pipeline.money import pta_crawl

CHARITY_JSON = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/charity/publicextract.charity.json")

PTFA = "WILLIAM PATTEN PARENTS TEACHERS & FRIENDS ASSOCIATION"
REGISTRY = {1103834: PTFA, 216401: "NATIONAL SOCIETY FOR THE PREVENTION OF CRUELTY TO CHILDREN",
            1072833: "NATIONAL CONFEDERATION OF PARENT TEACHER ASSOCIATIONS", 1111111: "FRIENDS OF ASHMOLE",
            1111112: "ASHMOLE ACADEMY TRUST", 1111113: "FRIENDS OF MILL RYTHE JUNIOR SCHOOL", 512345: "X SCHOOL PTA",
            1103835: "Y SCHOOL PTA", 1103836: "Z SCHOOL PTA", 1111114: "GRASMERE PRIMARY SCHOOL PTA",
            1111115: "HOLLY PARK PRIMARY SCHOOL PTA", 1111116: "FRIENDS OF THE EARTH LIMITED"}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeWeb:
    """Serves fixture HTML from a dict and records each request's URL, User-Agent and clock time."""

    def __init__(self, pages, clock=None):
        self.pages, self.clock, self.calls = pages, clock, []

    def __call__(self, url, headers, timeout):
        self.calls.append({"url": url, "ua": headers.get("User-Agent"), "t": self.clock.now if self.clock else None})
        body = self.pages.get(url)
        if body is None:
            return 404, url, ""
        return (body[0], url, body[1]) if isinstance(body, tuple) else (200, url, body)

    def page_urls(self):
        return [c["url"] for c in self.calls if not c["url"].endswith("/robots.txt")]


def fetcher(web, clock=None):
    clock = clock or FakeClock()
    return pta_crawl.Fetcher(web, pta_crawl.RateLimiter(1.0, clock=clock.time, sleep=clock.sleep))


def page(body, footer=""):
    return f"<html><head><title>School</title></head><body>{body}<footer>{footer}</footer></body></html>"


class NoNetworkTest(unittest.TestCase):
    """Any real socket or urlopen in a test is a failure."""

    def setUp(self):
        for target in ("urllib.request.urlopen", "socket.create_connection"):
            patcher = mock.patch(target, side_effect=AssertionError(f"network used: {target}"))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network used: connect"))
        patcher.start()
        self.addCleanup(patcher.stop)


class ExtractTest(NoNetworkTest):
    def test_registered_charity_number_near_ptfa(self):
        # Arrange
        html = page("<h1>Our PTFA</h1><p>The PTFA runs the summer fair. Registered charity no. 1103834</p>")
        # Act
        got = pta_crawl.extract_candidates(html, "https://school.example/pta/")
        # Assert
        self.assertEqual([c["charity_number"] for c in got], [1103834])
        self.assertIn("Registered charity no. 1103834", got[0]["evidence"])
        self.assertEqual(got[0]["context_url"], "https://school.example/pta/")

    def test_charity_number_phrasings(self):
        # Arrange
        phrasings = ["We're a registered charity (number 1103834) with a committee", "Registered Charity No. 1103834",
                     "Charity Reg. No: 1103834", "registered with the Charity Commission (1103834)",
                     "a registered charity in England and Wales no. 1103834", "Charity number: 1103834"]
        for text in phrasings:
            with self.subTest(text):
                # Act
                got = pta_crawl.extract_candidates(page(f"<p>{text}</p>"), "https://school.example/", pta_page=False)
                # Assert
                self.assertEqual([c["charity_number"] for c in got], [1103834])

    def test_evidence_leaves_out_emails_and_phone_numbers(self):
        # Arrange
        html = page("<p>Email jo.bloggs@gmail.com or call 07700 900123. The PTA is registered charity 1103834.</p>")
        # Act
        got = pta_crawl.extract_candidates(html, "https://school.example/pta/")
        # Assert
        self.assertEqual(got[0]["evidence"], "Email [email] or call [phone]. The PTA is registered charity 1103834.")

    def test_registered_charity_number_in_footer(self):
        # Arrange
        html = page("<p>Welcome to our school.</p>" * 30, footer="William Patten PTFA &middot; Registered Charity No. 1103834")
        # Act
        footer = pta_crawl.footer_text(html)
        got = pta_crawl.extract_candidates(html, "https://school.example/")
        # Assert
        self.assertIn("Registered Charity No. 1103834", footer)
        self.assertEqual([c["charity_number"] for c in got], [1103834])

    def test_bare_number_beside_pta_wording(self):
        # Arrange
        html = page("<p>Friends of William Patten (1103834) run the cake sale every term.</p>")
        # Act
        got = pta_crawl.extract_candidates(html, "https://school.example/")
        # Assert
        self.assertEqual([c["charity_number"] for c in got], [1103834])

    def test_bare_footer_number_counts_only_on_a_pta_page(self):
        # Arrange
        html = page("<p>Our PTA</p>" + "<p>News and events from around the school this week.</p>" * 10,
                    footer="&copy; 2025 | 1103834")
        # Act
        on_pta_page = pta_crawl.extract_candidates(html, "https://school.example/pta/")
        on_homepage = pta_crawl.extract_candidates(html, "https://school.example/", pta_page=False)
        # Assert
        self.assertEqual([c["charity_number"] for c in on_pta_page], [1103834])
        self.assertEqual(on_homepage, [])

    def test_rejects_urn_phone_company_and_distant_numbers(self):
        # Arrange: PTA wording sits beside a phone number, an Ofsted URN and a company number; a real
        # charity number appears only far from any PTA wording.
        filler = "Term dates, uniform, lunches and the school day are all explained below. " * 4
        html = page("<p>Contact the PTA on 01234 512345. Ofsted URN: 130932. Company number 1103835.</p>"
                    f"<p>{filler}</p><p>Our partner 1103836 helps with reading.</p>")
        # Act
        got = pta_crawl.extract_candidates(html, "https://school.example/", pta_page=False)
        # Assert
        self.assertEqual(got, [])

    def test_link_to_the_charity_register(self):
        # Arrange
        html = page('<a href="https://register-of-charities.charitycommission.gov.uk/charity-details/?regid=1103834&amp;subid=0">'
                    "Our PTFA on the charity register</a>")
        # Act
        got = pta_crawl.extract_candidates(html, "https://school.example/")
        # Assert
        self.assertEqual([c["charity_number"] for c in got], [1103834])
        self.assertIn("PTFA", got[0]["evidence"])


class ValidateTest(unittest.TestCase):
    def candidate(self, number, evidence="Our PTA, registered charity"):
        return {"charity_number": number, "evidence": evidence, "context_url": "https://school.example/pta/"}

    def test_keeps_only_register_confirmed_parents_associations(self):
        # Arrange: an unknown number, the NSPCC beside PTA wording, and the national PTA body.
        candidates = [self.candidate(n) for n in (1103834, 999999, 216401, 1072833)]
        # Act
        got = pta_crawl.validate(candidates, REGISTRY, "William Patten Primary School")
        # Assert
        self.assertEqual(got, [{"charity_number": 1103834, "source_url": "https://school.example/pta/",
                                "evidence": "Our PTA, registered charity"}])

    def test_page_wording_rescues_a_friends_name_but_not_a_trust(self):
        # Arrange
        candidates = [self.candidate(1111111, "Friends of Ashmole: charity 1111111"),
                      self.candidate(1111112, "Our PTA works with the Ashmole Academy Trust 1111112")]
        # Act
        got = pta_crawl.validate(candidates, REGISTRY, "Ashmole Academy")
        # Assert
        self.assertEqual([c["charity_number"] for c in got], [1111111])

    def test_rejects_phase_clash_and_other_schools_on_a_shared_site(self):
        # Arrange
        candidates = [self.candidate(1111113), self.candidate(1103834)]
        # Act
        infant = pta_crawl.validate(candidates, REGISTRY, "Mill Rythe Infant School", shared=True)
        junior = pta_crawl.validate(candidates, REGISTRY, "Mill Rythe Junior School", shared=True)
        # Assert
        self.assertEqual(infant, [])
        self.assertEqual([c["charity_number"] for c in junior], [1111113])

    def test_another_schools_pta_needs_a_pta_page_and_no_rival(self):
        # Arrange: Grasmere's PTA named in William Patten's homepage news, then on its PTA page.
        on_home = dict(self.candidate(1111114), pta_page=False)
        on_pta_page = dict(self.candidate(1111114), pta_page=True)
        two_others = [on_pta_page, dict(self.candidate(1111115), pta_page=True)]
        own_and_other = [on_pta_page, self.candidate(1103834)]
        # Act
        got = [pta_crawl.validate(c, REGISTRY, "William Patten Primary School")
               for c in ([on_home], [on_pta_page], two_others, own_and_other)]
        # Assert
        self.assertEqual([[c["charity_number"] for c in g] for g in got], [[], [1111114], [], [1103834]])

    def test_friends_wording_alone_does_not_rescue_an_unrelated_charity(self):
        # Arrange
        candidates = [dict(self.candidate(1111116, "Friends of the Earth, charity 1111116"), pta_page=True)]
        # Act
        got = pta_crawl.validate(candidates, REGISTRY, "William Patten Primary School")
        # Assert
        self.assertEqual(got, [])


class PtaLinksTest(NoNetworkTest):
    def test_finds_friends_and_pta_links_same_site_first(self):
        # Arrange
        html = page('<a href="/about/">About us</a><a href="/fundraising/">Fundraising</a>'
                    '<a href="/parents/pta/">PTA</a><a href="https://www.school.example/friends-of-x">Friends of X School</a>'
                    '<a href="https://www.facebook.com/xpta">PTA on Facebook</a><a href="/docs/minutes.pdf">PTA minutes</a>'
                    '<a href="https://xptfa.example/">Our own website</a><a href="#top">PTA</a>')
        # Act
        links = pta_crawl.pta_links(html, "https://school.example/")
        # Assert
        self.assertEqual([(link.url, link.offsite) for link in links], [
            ("https://school.example/parents/pta/", False), ("https://www.school.example/friends-of-x", False),
            ("https://school.example/fundraising/", False), ("https://xptfa.example/", True)])

    def test_friends_of_offsite_only_when_it_names_the_school(self):
        # Arrange
        html = page('<a href="https://foe.example/">Friends of the Earth</a>'
                    '<a href="https://fowp.example/">Friends of William Patten</a>'
                    '<a href="https://fogs.example/">Friends of Grasmere School</a>')
        # Act
        links = pta_crawl.pta_links(html, "https://williampatten.example/")
        # Assert
        self.assertEqual([link.url for link in links], ["https://fowp.example/", "https://fogs.example/"])

    def test_pta_wording_into_a_platform_page_is_not_a_pta_site(self):
        # Arrange
        html = page('<a href="https://donate.example/wp-2025-26-donations?preview=1">The PTFA campaign is live. Donate here</a>'
                    '<a href="https://tickets.example/events/123">PTA quiz night tickets</a>'
                    '<a href="https://williampattenptfa.example/events/2025/quiz">Quiz night</a>')
        # Act
        links = pta_crawl.pta_links(html, "https://williampatten.example/")
        # Assert
        self.assertEqual([link.url for link in links], ["https://williampattenptfa.example/events/2025/quiz"])


class CrawlTest(NoNetworkTest):
    def test_stays_within_six_pages(self):
        # Arrange
        links = "".join(f'<a href="/pta-{i}/">PTA page {i}</a>' for i in range(10))
        web = FakeWeb({"https://school.example/": page(links)})
        # Act
        _, pages, status = pta_crawl.crawl_site("https://school.example/", fetcher(web))
        # Assert
        self.assertEqual(status, "ok")
        self.assertEqual(pages, 6)
        self.assertEqual(len(web.page_urls()), 6)
        self.assertEqual(web.page_urls()[0], "https://school.example/")

    def test_follows_the_school_pta_page_to_the_pta_site(self):
        # Arrange
        web = FakeWeb({
            "https://school.example/": page('<a href="/parents/ptfa/">PTFA</a>'),
            "https://school.example/parents/ptfa/": page('<a href="https://williampattenptfa.example/events">Visit our PTFA site</a>'),
            "https://williampattenptfa.example/": page('<a href="/about-us/">About us</a><a href="/shop/">Shop</a>'),
            "https://williampattenptfa.example/about-us/": page("<p>We are a registered charity, number 1103834.</p>"),
        })
        # Act
        candidates, pages, _ = pta_crawl.crawl_site("https://school.example/", fetcher(web))
        # Assert
        self.assertEqual(pages, 4)
        self.assertEqual([(c["charity_number"], c["context_url"]) for c in candidates],
                         [(1103834, "https://williampattenptfa.example/about-us/")])

    def test_robots_disallow_is_honoured(self):
        # Arrange
        web = FakeWeb({
            "https://school.example/robots.txt": "User-agent: *\nDisallow: /parents/\n",
            "https://school.example/": page('<a href="/parents/pta/">PTA</a><a href="/friends/">Friends of the School</a>'),
            "https://closed.example/robots.txt": "User-agent: SchoolsInReach-research\nDisallow: /\n",
        })
        crawler = fetcher(web)
        # Act
        _, _, status = pta_crawl.crawl_site("https://school.example/", crawler)
        _, pages, blocked = pta_crawl.crawl_site("https://closed.example/", crawler)
        # Assert
        self.assertEqual(status, "ok")
        self.assertEqual(web.page_urls(), ["https://school.example/", "https://school.example/friends/"])
        self.assertEqual(blocked, "robots")
        self.assertEqual([c["url"] for c in web.calls if "closed" in c["url"]], ["https://closed.example/robots.txt"])
        self.assertEqual(crawler.stats["robots"], 2)

    def test_unreachable_robots_is_a_failure_not_a_block(self):
        # Arrange
        web = FakeWeb({"https://down.example/robots.txt": (503, "")})
        # Act
        _, pages, status = pta_crawl.crawl_site("https://down.example/", fetcher(web))
        # Assert
        self.assertEqual((pages, status), (1, "error"))
        self.assertEqual(web.page_urls(), [])

    def test_one_request_per_second_per_host(self):
        # Arrange
        clock = FakeClock()
        web = FakeWeb({"https://school.example/": page('<a href="/pta/">PTA</a><a href="/friends/">Friends of</a>'
                                                        '<a href="https://xpta.example/">PTA site</a>')}, clock)
        # Act
        pta_crawl.crawl_site("https://school.example/", fetcher(web, clock))
        # Assert
        by_host = {}
        for call in web.calls:
            by_host.setdefault(pta_crawl.host_key(call["url"]), []).append(call["t"])
        self.assertEqual(sorted(by_host), ["school.example", "xpta.example"])
        for times in by_host.values():
            self.assertTrue(all(b - a >= 1.0 for a, b in zip(times, times[1:])), times)
        self.assertEqual(len(by_host["school.example"]), 4)   # robots.txt, home, /pta/, /friends/

    def test_rate_limiter_spaces_one_host_only(self):
        # Arrange
        clock = FakeClock()
        limiter = pta_crawl.RateLimiter(1.0, clock=clock.time, sleep=clock.sleep)
        # Act
        times = [limiter.wait("a.example"), limiter.wait("a.example"), limiter.wait("b.example"), limiter.wait("a.example")]
        # Assert
        self.assertEqual(times, [0.0, 1.0, 1.0, 2.0])

    def test_user_agent_is_sent(self):
        # Arrange
        web = FakeWeb({"https://school.example/": page('<a href="/pta/">PTA</a>')})
        # Act
        pta_crawl.crawl_site("https://school.example/", fetcher(web))
        # Assert
        self.assertEqual({c["ua"] for c in web.calls}, {pta_crawl.USER_AGENT})
        self.assertEqual(len(web.calls), 3)

    def test_real_transport_sends_user_agent(self):
        # Arrange
        seen = []

        class Response(io.BytesIO):
            status = 200
            headers = mock.Mock(get=lambda key, default=None: "text/html; charset=utf-8",
                                get_content_charset=lambda: "utf-8")

            def geturl(self):
                return "https://school.example/"

        def urlopen(request, timeout):
            seen.append((request.get_header("User-agent"), timeout))
            return Response("<p>Our PTA</p>".encode("utf-8"))

        # Act
        with mock.patch.object(urllib.request, "urlopen", urlopen):
            got = pta_crawl.Fetcher().fetch("https://school.example/", pta_crawl.Fetcher().headers, 10)
        # Assert
        self.assertEqual(seen, [(pta_crawl.USER_AGENT, 10)])
        self.assertEqual(got, (200, "https://school.example/", "<p>Our PTA</p>"))


def write_fixture(root, schools):
    (root / "england").mkdir(parents=True)
    (root / "la/999").mkdir(parents=True)
    (root / "england/las.json").write_text(json.dumps({"las": [{"la_code": "999", "name": "Testshire"}]}), encoding="utf-8")
    (root / "la/999/schools.json").write_text(json.dumps({"schools": schools}), encoding="utf-8")
    (root / "charity").mkdir()
    (root / "charity/publicextract.charity.json").write_text("﻿" + json.dumps(
        [{"registered_charity_number": n, "linked_charity_number": 0, "charity_name": name} for n, name in REGISTRY.items()]),
        encoding="utf-8")


SCHOOLS = [
    {"urn": 130932, "name": "William Patten Primary School", "website": "https://williampatten.example", "laestab": "9992000"},
    {"urn": 100001, "name": "Grasmere Primary School", "website": "grasmere.example", "laestab": "9992001"},
    {"urn": 100002, "name": "The German School", "website": "https://german.example", "type_group": "Independent schools"},
    {"urn": 100003, "name": "Old Closed School", "website": "https://closed.example", "status": "Closed"},
    {"urn": 100004, "name": "No Website Primary School"},
    {"urn": 100005, "name": "Holly Park Primary School", "website": "https://hollypark.example/", "laestab": "9992002"},
]
WEB = {
    "https://williampatten.example/": page('<a href="/pta/">PTFA</a>'),
    "https://williampatten.example/pta/": page("<p>The PTFA: registered charity no. 1103834</p>"),
    "http://grasmere.example/": page("<p>Welcome</p>"),
    "https://hollypark.example/": page("<p>Welcome</p>"),
}


class MainTest(NoNetworkTest):
    def run_main(self, root, *args, web=None):
        web = web or FakeWeb(WEB)
        out = root / "money/pta_crawl.json"
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            pta_crawl.main(["--site-data", str(root), "--charity-dir", str(root / "charity"), "--out", str(out),
                            "--workers", "2", *args], fetcher=fetcher(web))
        return web, out, printed.getvalue()

    def test_output_matches_the_shared_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            # Act
            web, out, printed = self.run_main(root)
            data = json.loads(out.read_text(encoding="utf-8"))
            state = json.loads(pta_crawl.state_path(out).read_text(encoding="utf-8"))
        # Assert
        self.assertEqual(sorted(data), ["generated", "schools", "user_agent"])
        self.assertEqual(data["user_agent"], pta_crawl.USER_AGENT)
        self.assertEqual(list(data["schools"]), ["130932"])
        self.assertEqual(sorted(data["schools"]["130932"][0]), ["charity_number", "evidence", "source_url"])
        self.assertEqual(data["schools"]["130932"][0]["charity_number"], 1103834)
        self.assertEqual(data["schools"]["130932"][0]["source_url"], "https://williampatten.example/pta/")
        self.assertEqual(state["no_pta"], ["100001", "100005"])
        self.assertFalse({"german.example", "closed.example"} & {pta_crawl.host_key(u) for u in web.page_urls()})
        self.assertIn("1 with a PTA number", printed)

    def test_limit_stops_early(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            # Act
            web, out, _ = self.run_main(root, "--limit", "1")
            data = json.loads(out.read_text(encoding="utf-8"))
        # Assert
        self.assertEqual({pta_crawl.host_key(u) for u in web.page_urls()}, {"williampatten.example"})
        self.assertEqual(list(data["schools"]), ["130932"])

    def test_resume_skips_done_urns(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            out = root / "money/pta_crawl.json"
            out.parent.mkdir()
            earlier = {"charity_number": 1103834, "source_url": "https://williampatten.example/pta/", "evidence": "PTFA"}
            out.write_text(json.dumps({"generated": "x", "user_agent": "x", "schools": {"130932": [earlier]}}), encoding="utf-8")
            pta_crawl.state_path(out).write_text(json.dumps({"no_pta": ["100001"]}), encoding="utf-8")
            # Act
            web, out, _ = self.run_main(root, "--resume")
            data = json.loads(out.read_text(encoding="utf-8"))
            state = json.loads(pta_crawl.state_path(out).read_text(encoding="utf-8"))
        # Assert
        self.assertEqual(web.page_urls(), ["https://hollypark.example/"])
        self.assertEqual(data["schools"], {"130932": [earlier]})
        self.assertEqual(state["no_pta"], ["100001", "100005"])

    def test_urns_and_council_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            # Act
            by_urn, _, _ = self.run_main(root, "--urns", "100005")
            other_council, _, _ = self.run_main(root, "--la", "204")
        # Assert
        self.assertEqual(by_urn.page_urls(), ["https://hollypark.example/"])
        self.assertEqual(other_council.calls, [])


class WidespreadTest(unittest.TestCase):
    def test_numbers_on_many_schools_sites_are_held(self):
        # Arrange
        hit = lambda n: {"charity_number": n, "source_url": "u", "evidence": "e"}  # noqa: E731
        found = {str(urn): [hit(1072834)] for urn in range(5)}
        found["0"].append(hit(1103834))
        # Act
        kept, held = pta_crawl.split_widespread(found, limit=4)
        # Assert
        self.assertEqual(kept, {"0": [hit(1103834)]})
        self.assertEqual(sorted(held), ["0", "1", "2", "3", "4"])


@unittest.skipUnless(CHARITY_JSON.exists(), "real charity register not present")
class RealDataTest(unittest.TestCase):
    def test_william_patten_ptfa_validates_against_the_register(self):
        # Arrange
        registry = pta_crawl.load_registry(CHARITY_JSON)
        candidates = [{"charity_number": 1103834, "evidence": "PTFA registered charity 1103834", "context_url": "u"}]
        # Act
        got = pta_crawl.validate(candidates, registry, "William Patten Primary School")
        # Assert
        self.assertEqual([c["charity_number"] for c in got], [1103834])


if __name__ == "__main__":
    unittest.main()
