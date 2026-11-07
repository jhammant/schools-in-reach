"""Tests for the PTA website crawler; fixture HTML, a fake transport and a fake clock only, every real network open raises."""
import contextlib
import io
import json
import signal
import socket
import ssl
import tempfile
import threading
import unittest
import urllib.error
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
BANNED = ("poor school", "failing", "worst", "bankrupt", "scandal")


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeWeb:
    """Serves fixtures from a dict and records each request's URL, User-Agent, clock time, timeout and TLS check.

    A fixture is HTML (200), (status, body), (status, body, redirect target), an exception to raise, or a
    callable(verify, timeout) returning one of those.
    """

    def __init__(self, pages, clock=None, on_call=None):
        self.pages, self.clock, self.calls, self.on_call = pages, clock, [], on_call

    def __call__(self, url, headers, timeout, verify=True):
        self.calls.append({"url": url, "ua": headers.get("User-Agent"), "t": self.clock.now if self.clock else None,
                           "timeout": timeout, "verify": verify})
        if self.on_call:
            self.on_call(url)
        body = self.pages.get(url)
        if callable(body):
            body = body(verify=verify, timeout=timeout)
        if isinstance(body, BaseException):
            raise body
        if body is None:
            return 404, url, ""
        if isinstance(body, tuple):
            return (body[0], body[2], body[1]) if len(body) > 2 else (body[0], url, body[1])
        return 200, url, body

    def page_urls(self):
        return [c["url"] for c in self.calls if not c["url"].endswith("/robots.txt")]

    def times(self, host):
        return [c["t"] for c in self.calls if pta_crawl.host_key(c["url"]) == host]


def fetcher(web, clock=None, **kwargs):
    clock = clock or web.clock or FakeClock()
    return pta_crawl.Fetcher(web, pta_crawl.RateLimiter(1.0, clock=clock.time, sleep=clock.sleep), **kwargs)


def page(body, footer="", head=""):
    return f"<html><head><title>School</title>{head}</head><body>{body}<footer>{footer}</footer></body></html>"


def spaced(times, gap):
    return all(b - a >= gap - 1e-9 for a, b in zip(times, times[1:]))


class NoNetworkTest(unittest.TestCase):
    """Any real socket or urlopen in a test is a failure."""

    def setUp(self):
        for target in ("urllib.request.urlopen", "socket.create_connection", "socket.getaddrinfo"):
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
        self.assertEqual((got[0]["where"], got[0]["pta_term"]), ("body", "PTFA"))

    def test_charity_number_phrasings(self):
        # Arrange
        phrasings = ["We're a registered charity (number 1103834) with a committee", "Registered Charity No. 1103834",
                     "Charity Reg. No: 1103834", "registered with the Charity Commission (1103834)",
                     "a registered charity in England and Wales no. 1103834", "Charity number: 1103834",
                     "CIO no. 1103834", "1103834 (registered charity)", "Charity n°: 1103834",
                     "Charity registered in England and Wales number 1103834",
                     "registered with the Charity Commission (no. 1103834)", "Charity Reg. No 1103834"]
        for text in phrasings:
            with self.subTest(text):
                # Act
                got = pta_crawl.extract_candidates(page(f"<p>{text}</p>"), "https://school.example/", pta_page=False)
                # Assert
                self.assertEqual([c["charity_number"] for c in got], [1103834])

    def test_gap_veto_drops_company_phone_and_office_numbers(self):
        # Arrange
        texts = ["Our PTA is a registered charity and company, company no. 1103835",
                 "PTA charity enquiries: tel 1103836", "Registered charity, registered office postcode 1103835"]
        for text in texts:
            with self.subTest(text):
                # Act
                got = pta_crawl.extract_candidates(page(f"<p>{text}</p>"), "https://school.example/pta/")
                # Assert
                self.assertEqual(got, [])

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
        self.assertEqual([(c["charity_number"], c["where"]) for c in got], [(1103834, "footer")])

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
                    "Our PTFA on the charity register</a>"
                    '<a href="https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/1111111">'
                    "Friends of Ashmole</a>")
        # Act
        got = pta_crawl.extract_candidates(html, "https://school.example/")
        # Assert
        self.assertEqual([(c["charity_number"], c["where"]) for c in got], [(1103834, "cc_link"), (1111111, "cc_link")])
        self.assertIn("PTFA", got[0]["evidence"])
        self.assertEqual(got[1]["pta_term"], "Friends")

    def test_script_text_is_read_for_numbers(self):
        # Arrange: a Wix-style page whose words live only in JSON.
        html = page('<script type="application/ld+json">{"description": "The Friends of Ashmole PTA, '
                    'registered charity 1111111"}</script><p>Loading</p>')
        # Act
        got = pta_crawl.extract_candidates(html, "https://ashmole.example/")
        # Assert
        self.assertEqual([(c["charity_number"], c["where"], c["pta_term"]) for c in got], [(1111111, "script", "PTA")])

    def test_pta_wording_must_be_within_400_characters_and_stays_in_the_evidence(self):
        # Arrange
        filler = "The school office is open every weekday morning for any questions. "   # 68 characters
        near = page(f"<p>Our PTA. {filler * 4}Registered charity 1103834.</p>")
        far = page(f"<p>Our PTA. {filler * 7}Registered charity 1103834.</p>")
        # Act
        got_near = pta_crawl.extract_candidates(near, "https://school.example/", pta_page=False)
        got_far = pta_crawl.extract_candidates(far, "https://school.example/", pta_page=False)
        # Assert
        self.assertEqual(got_near[0]["pta_term"], "PTA")
        self.assertIn("Our PTA", got_near[0]["evidence"])
        self.assertLessEqual(len(got_near[0]["evidence"]), 400)
        self.assertIsNone(got_far[0]["pta_term"])


class LinksTest(NoNetworkTest):
    def test_finds_friends_and_pta_links_same_site_first(self):
        # Arrange
        html = page('<a href="/about/">About us</a><a href="/fundraising/">Fundraising</a>'
                    '<a href="/parents/pta/">PTA</a><a href="https://www.school.example/friends-of-x">Friends of X School</a>'
                    '<a href="https://www.facebook.com/xpta">PTA on Facebook</a><a href="/docs/minutes.pdf">PTA minutes</a>'
                    '<a href="https://xptfa.example/events/">Our own website</a><a href="#top">PTA</a>')
        # Act
        links = pta_crawl.pta_links(html, "https://school.example/")
        # Assert: the fundraising hub is dropped because the homepage has PTA links.
        self.assertEqual([(link.url, link.kind) for link in links], [
            ("https://school.example/parents/pta/", "pta"), ("https://www.school.example/friends-of-x", "pta"),
            ("https://xptfa.example/", "offsite_home")])

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
        # Assert: the PTA's own host is fetched at its front page.
        self.assertEqual([link.url for link in links], ["https://williampattenptfa.example/"])

    def test_never_fetch_lists(self):
        # Arrange
        cases = {"https://school.example/term-dates.ics": "file", "https://school.example/documents.asp?id=3": "document",
                 "https://school.example/attachments/download.aspx?id=9": "document",
                 "https://register-of-charities.charitycommission.gov.uk/charity-details/?regid=1103834": "register",
                 "https://www.facebook.com/xpta": "no_follow", "https://www.parentpay.com/": "no_follow",
                 "https://bit.ly/abc": "no_follow", "https://drive.google.com/x": "no_follow",
                 "https://sites.google.com/view/xpta": None, "https://www.pta-events.co.uk/williampatten/": None,
                 "https://xpta.wixsite.com/home": None, "ftp://school.example/": "scheme"}
        html = page('<a href="mailto:pta@school.example">PTA</a><a href="tel:01234">PTA</a>'
                    '<a href="javascript:void(0)">PTA</a><a href="/pta/">PTA</a>')
        # Act
        got = {url: pta_crawl.never_fetch(url) for url in cases}
        links = pta_crawl.pta_links(html, "https://school.example/")
        # Assert
        self.assertEqual(got, cases)
        self.assertEqual([link.url for link in links], ["https://school.example/pta/"])

    def test_hub_only_when_the_homepage_has_no_pta_link(self):
        # Arrange
        hub_only = page('<a href="/parents/">Parents</a><a href="/news/">News</a>')
        with_pta = page('<a href="/parents/">Parents</a><a href="/ptfa/">PTFA</a>')
        # Act
        got_hub = pta_crawl.pta_links(hub_only, "https://school.example/")
        got_pta = pta_crawl.pta_links(with_pta, "https://school.example/")
        # Assert
        self.assertEqual([(link.url, link.kind) for link in got_hub], [("https://school.example/parents/", "hub")])
        self.assertEqual([link.kind for link in got_pta], ["pta"])

    def test_pta_page_links_sub_pages_and_the_pta_website(self):
        # Arrange
        html = page('<a href="/pta/events/">PTA events</a><a href="/pta/committee/">Our PTA committee</a>'
                    '<a href="https://hollyparkfriends.example/">Visit our website</a>')
        # Act
        links = pta_crawl.link_candidates(html, "https://school.example/pta/", "pta", 1)
        # Assert: events sink below the committee page.
        ordered = sorted(links)
        self.assertEqual([(link.url, link.kind, link.depth) for link in ordered], [
            ("https://hollyparkfriends.example/", "offsite_home", 1),
            ("https://school.example/pta/committee/", "pta_sub", 2),
            ("https://school.example/pta/events/", "pta_sub", 2)])

    def test_offsite_pta_site_about_pages(self):
        # Arrange
        html = page('<a href="/shop/">Shop</a><a href="/contact-us/">Get in touch</a>'
                    '<a href="/index.php?event=your-organisation">Who we are</a>')
        # Act
        links = pta_crawl.link_candidates(html, "https://xptfa.example/", "offsite_home", 1, "school.example", {"xptfa.example"})
        # Assert
        self.assertEqual(sorted(link.kind for link in links), ["offsite_about", "offsite_about"])
        self.assertNotIn("https://xptfa.example/shop/", [link.url for link in links])


class ValidateTest(unittest.TestCase):
    def candidate(self, number, evidence="Our PTA, registered charity"):
        return {"charity_number": number, "evidence": evidence, "context_url": "https://school.example/pta/"}

    def test_keeps_only_register_confirmed_parents_associations(self):
        # Arrange: an unknown number, the NSPCC beside PTA wording, and the national PTA body.
        candidates = [self.candidate(n) for n in (1103834, 999999, 216401, 1072833)]
        # Act
        got = pta_crawl.validate(candidates, REGISTRY, "William Patten Primary School")
        # Assert
        self.assertEqual([{k: hit[k] for k in ("charity_number", "source_url", "evidence")} for hit in got],
                         [{"charity_number": 1103834, "source_url": "https://school.example/pta/",
                           "evidence": "Our PTA, registered charity"}])
        self.assertEqual((got[0]["meta"]["pa_tier"], got[0]["meta"]["agrees"]), ("strict", ["name:patten,william"]))

    def test_page_wording_rescues_a_friends_name_but_not_a_trust(self):
        # Arrange
        candidates = [self.candidate(1111111, "Friends of Ashmole: charity 1111111"),
                      self.candidate(1111112, "Our PTA works with the Ashmole Academy Trust 1111112")]
        # Act
        got = pta_crawl.validate(candidates, REGISTRY, "Ashmole Academy")
        # Assert
        self.assertEqual([c["charity_number"] for c in got], [1111111])
        self.assertEqual(got[0]["meta"]["pa_tier"], "web")

    def test_rejects_phase_clash_and_other_schools_on_a_shared_site(self):
        # Arrange
        candidates = [self.candidate(1111113), self.candidate(1103834)]
        # Act
        infant = pta_crawl.validate(candidates, REGISTRY, "Mill Rythe Infant School", shared=True)
        junior = pta_crawl.validate(candidates, REGISTRY, "Mill Rythe Junior School", shared=True)
        # Assert
        self.assertEqual(infant, [])
        self.assertEqual([c["charity_number"] for c in junior], [1111113])

    def test_another_schools_pta_goes_to_review(self):
        # Arrange: Grasmere's PTA named in William Patten's homepage news, then on its PTA page.
        on_home = dict(self.candidate(1111114), pta_page=False)
        on_pta_page = dict(self.candidate(1111114), pta_page=True)
        own_and_other = [on_pta_page, self.candidate(1103834)]
        # Act
        got = [pta_crawl.classify(c, REGISTRY, "William Patten Primary School") for c in ([on_home], [on_pta_page], own_and_other)]
        # Assert
        self.assertEqual([[c["charity_number"] for c in v.accepted] for v in got], [[], [], [1103834]])
        self.assertEqual([[(c["charity_number"], c["reason"]) for c in v.review] for v in got],
                         [[(1111114, "no_agreement")]] * 3)

    def test_friends_wording_alone_does_not_rescue_an_unrelated_charity(self):
        # Arrange
        candidates = [dict(self.candidate(1111116, "Friends of the Earth, charity 1111116"), pta_page=True)]
        # Act
        got = pta_crawl.classify(candidates, REGISTRY, "William Patten Primary School")
        # Assert
        self.assertEqual((got.accepted, got.review), ([], []))
        self.assertEqual(got.rejects[0]["reason"], "not_pa_like")

    def test_pta_wording_must_be_near(self):
        # Arrange: the extractor found no PTA wording within 400 characters.
        candidates = [dict(self.candidate(1111111, "Registered charity 1111111"), pta_term=None)]
        # Act
        got = pta_crawl.classify(candidates, REGISTRY, "Ashmole Primary School")
        # Assert
        self.assertEqual(got.rejects[0]["reason"], "no_pta_term_near")

    def test_name_tiers(self):
        # Arrange
        activities = "The association raises funds through events to buy equipment for pupils at the school, run by parents."
        names = {"HOLLY PARK PRIMARY SCHOOL PTA": "strict", "FRIENDS OF BOUSFIELD": "web",
                 "FRIENDS OF COLHAM MANOR": "web", "REIGATE PRIORY SCHOOL FAMILIES & STAFF ASSOCIATION": "web",
                 "FRIENDS OF ST MARY'S CHURCH": None, "THE OAKS SCHOOL FUND SOCIETY": None, "FRIENDS OF THE EARTH LIMITED": None,
                 "NATIONAL CONFEDERATION OF PARENT TEACHER ASSOCIATIONS": None, "HILLSIDE SCHOOL MUSIC SOCIETY": None}
        # Act
        got = {name: pta_crawl.charity_tier(name) for name in names}
        broad = pta_crawl.charity_tier("THE OAKS SCHOOL SUPPORTERS COMMITTEE", activities)
        # Assert
        self.assertEqual(got, names)
        self.assertEqual(broad, "broad")

    def test_agreement_by_postcode_or_domain_and_none_for_review(self):
        # Arrange: three Families & Staff Associations whose names share nothing with the school.
        charity = lambda postcode=None, web=None: pta_crawl.Charity(  # noqa: E731
            "HILLTOP FAMILIES & STAFF ASSOCIATION", "Registered", None, "web", postcode, web)
        registry = {1200001: charity(postcode="AB12CD"), 1200002: charity(web="hilltopfsa.example"), 1200003: charity()}
        school = {"name": "Oak Tree Primary School", "postcode": "AB1 2CD"}
        candidates = [self.candidate(n, "Families & Staff Association, registered charity") for n in registry]
        # Act
        got = pta_crawl.classify(candidates, registry, school, domains={"oaktree.example", "hilltopfsa.example"})
        # Assert
        self.assertEqual([(c["charity_number"], c["meta"]["agrees"]) for c in got.accepted],
                         [(1200001, ["postcode"]), (1200002, ["domain"])])
        self.assertEqual([c["charity_number"] for c in got.review], [1200003])

    def test_removed_charities_are_flagged_not_dropped(self):
        # Arrange
        registry = {1103834: pta_crawl.Charity(PTFA, "Removed", "2019-04-01", "strict", None, None)}
        # Act
        got = pta_crawl.validate([self.candidate(1103834)], registry, "William Patten Primary School")
        # Assert
        self.assertEqual((got[0]["meta"]["cc_status"], got[0]["meta"]["cc_removed"]), ("Removed", "2019-04-01"))


class CrawlTest(NoNetworkTest):
    def test_stays_within_six_pages_and_the_kind_caps(self):
        # Arrange: ten PTA links, each PTA page with two sub-pages and a link to the PTA's own site.
        pta_page = page('<a href="sub-a/">PTA committee</a><a href="sub-b/">PTA constitution</a>'
                        '<a href="https://xptfa.example/">Visit our website</a>')
        web = FakeWeb({"https://school.example/": page("".join(f'<a href="/page-{i}/">PTA page {i}</a>' for i in range(10))),
                       **{f"https://school.example/page-{i}/": pta_page for i in range(10)},
                       "https://xptfa.example/": page('<a href="/about/">About us</a><a href="/contact/">Contact</a>')})
        # Act
        site = pta_crawl.crawl_site("https://school.example/", fetcher(web))
        # Assert
        kinds = [p["kind"] for p in site.trail]
        self.assertEqual((site.status, site.pages, len(web.page_urls())), ("ok", 6, 6))
        self.assertEqual(web.page_urls()[0], "https://school.example/")
        self.assertEqual(kinds, ["home", "pta", "pta", "pta", "offsite_home", "offsite_about"])

    def test_follows_the_school_pta_page_to_the_pta_site(self):
        # Arrange
        web = FakeWeb({
            "https://school.example/": page('<a href="/parents/ptfa/">PTFA</a>'),
            "https://school.example/parents/ptfa/": page('<a href="https://williampattenptfa.example/events">Visit our PTFA site</a>'),
            "https://williampattenptfa.example/": page('<a href="/about-us/">About us</a><a href="/shop/">Shop</a>'),
            "https://williampattenptfa.example/about-us/": page("<p>We are a registered charity, number 1103834.</p>"),
        })
        # Act
        site = pta_crawl.crawl_site("https://school.example/", fetcher(web))
        # Assert
        self.assertEqual(site.pages, 4)
        self.assertEqual([(c["charity_number"], c["context_url"]) for c in site.candidates],
                         [(1103834, "https://williampattenptfa.example/about-us/")])
        self.assertEqual(site.domains, {"school.example", "williampattenptfa.example"})

    def test_hub_page_is_used_when_home_has_no_pta_link(self):
        # Arrange
        web = FakeWeb({"https://school.example/": page('<a href="/parents/">Parents</a>'),
                       "https://school.example/parents/": page('<a href="/parents/friends/">Friends of the School</a>'),
                       "https://school.example/parents/friends/": page("<p>Friends of the School, registered charity 1103834</p>")})
        # Act
        site = pta_crawl.crawl_site("https://school.example/", fetcher(web))
        # Assert
        self.assertEqual([p["kind"] for p in site.trail], ["home", "hub", "pta"])
        self.assertEqual([c["charity_number"] for c in site.candidates], [1103834])

    def test_stops_once_a_number_validates(self):
        # Arrange
        web = FakeWeb({"https://williampatten.example/": page('<p>Our PTFA, registered charity 1103834</p><a href="/pta/">PTA</a>')})
        school = {"urn": 130932, "name": "William Patten Primary School", "website": "https://williampatten.example/"}
        # Act
        lines = pta_crawl.crawl_group([school], fetcher(web), REGISTRY)
        # Assert
        self.assertEqual(web.page_urls(), ["https://williampatten.example/"])
        self.assertEqual((lines[0]["outcome"], [h["charity_number"] for h in lines[0]["hits"]]), ("hit", [1103834]))

    def test_meta_refresh_and_nofollow(self):
        # Arrange
        web = FakeWeb({"https://a.example/": page("", head='<meta http-equiv="refresh" content="0; url=/home/">'),
                       "https://a.example/home/": page('<a href="/pta/">PTA</a>'),
                       "https://b.example/": page('<a href="/pta/">PTA</a>', head='<meta name="robots" content="noindex, nofollow">')})
        crawler = fetcher(web)
        # Act
        refreshed = pta_crawl.crawl_site("https://a.example/", crawler)
        nofollow = pta_crawl.crawl_site("https://b.example/", crawler)
        # Assert
        self.assertEqual([p["kind"] for p in refreshed.trail], ["home", "home_refresh", "pta"])
        self.assertEqual([p["url"] for p in nofollow.trail], ["https://b.example/"])

    def test_robots_disallow_is_honoured(self):
        # Arrange
        web = FakeWeb({
            "https://school.example/robots.txt": "User-agent: *\nDisallow: /parents/\n",
            "https://school.example/": page('<a href="/parents/pta/">PTA</a><a href="/friends/">Friends of the School</a>'),
            "https://closed.example/robots.txt": "User-agent: SchoolsInReach-research\nDisallow: /\n",
        })
        crawler = fetcher(web)
        # Act
        open_site = pta_crawl.crawl_site("https://school.example/", crawler)
        closed = pta_crawl.crawl_site("https://closed.example/", crawler)
        # Assert
        self.assertEqual(open_site.status, "ok")
        self.assertEqual(web.page_urls(), ["https://school.example/", "https://school.example/friends/"])
        self.assertEqual(closed.status, "robots")
        self.assertEqual([c["url"] for c in web.calls if "closed" in c["url"]], ["https://closed.example/robots.txt"])
        self.assertEqual(crawler.stats["robots"], 2)

    def test_robots_answers(self):
        # Arrange: crawl_spec §6's table, one host per row.
        answers = {"forbidden": (403, ""), "unauthorised": (401, ""), "waf": (202, '<meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/">'),
                   "failing": (503, ""), "missing": (404, ""), "soft404": "<html><body>Page not found</body></html>",
                   "teapot": (418, "")}
        web = FakeWeb({f"https://{h}.example/robots.txt": a for h, a in answers.items()}
                      | {f"https://{h}.example/": page("<p>Welcome</p>") for h in answers})
        crawler = fetcher(web)
        # Act
        got = {h: pta_crawl.crawl_site(f"https://{h}.example/", crawler).status for h in answers}
        # Assert
        self.assertEqual(got, {"forbidden": "robots", "unauthorised": "robots", "waf": "robots", "failing": "error",
                               "missing": "ok", "soft404": "ok", "teapot": "ok"})

    def test_unreachable_robots_is_a_failure_not_a_block(self):
        # Arrange
        web = FakeWeb({"https://down.example/robots.txt": (503, "")})
        # Act
        site = pta_crawl.crawl_site("https://down.example/", fetcher(web))
        # Assert
        self.assertEqual((site.pages, site.status), (1, "error"))
        self.assertEqual(web.page_urls(), [])

    def test_challenge_pages_are_refusals(self):
        # Arrange
        web = FakeWeb({"https://cf.example/": "<html><title>Just a moment...</title></html>",
                       "https://waf.example/": (403, "<h1>Access denied</h1> Sucuri Website Firewall")})
        crawler = fetcher(web)
        # Act
        got = [pta_crawl.crawl_site(f"https://{h}.example/", crawler) for h in ("cf", "waf")]
        # Assert
        self.assertEqual([(s.status, s.trail[0]["err"]) for s in got], [("blocked", "challenge_200"), ("blocked", "challenge_403")])
        self.assertEqual(crawler.stats["blocked"], 2)

    def test_tls_and_www_fallbacks(self):
        # Arrange: one homepage fails its certificate check, another does not resolve without www.
        cert = urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))
        unverified = lambda html: lambda verify, timeout: cert if verify else html  # noqa: E731
        web = FakeWeb({"https://tls.example/robots.txt": unverified((404, "")),
                       "https://tls.example/": unverified(page('<a href="/pta/">PTA</a>')),
                       "https://tls.example/pta/": unverified(page("<p>PTA</p>")),
                       "https://dns.example/robots.txt": urllib.error.URLError(socket.gaierror(8, "nodename nor servname")),
                       "https://dns.example/": urllib.error.URLError(socket.gaierror(8, "nodename nor servname")),
                       "https://www.dns.example/": page("<p>Welcome</p>")})
        crawler = fetcher(web)
        # Act
        tls = pta_crawl.crawl_site("https://tls.example/", crawler)
        dns = pta_crawl.crawl_site("https://dns.example/", crawler)
        # Assert
        self.assertEqual((tls.status, tls.tls_unverified), ("ok", True))
        self.assertEqual([(p["kind"], p["err"]) for p in tls.trail], [("home", "tls_cert"), ("home_retry", None), ("pta", None)])
        self.assertEqual([c["verify"] for c in web.calls if c["url"] == "https://tls.example/pta/"], [False])
        self.assertEqual([(p["url"], p["err"]) for p in dns.trail],
                         [("https://dns.example/", "dns"), ("https://www.dns.example/", None)])
        self.assertEqual(dns.status, "ok")

    def test_redirect_hops_are_robots_checked_and_paced_per_host(self):
        # Arrange
        clock = FakeClock()
        web = FakeWeb({"https://a.example/": (301, "", "https://b.example/home"),
                       "https://b.example/robots.txt": "User-agent: *\nDisallow: /home\n",
                       "https://c.example/": (302, "", "https://d.example/"),
                       "https://d.example/": page("<p>Welcome</p>")}, clock)
        crawler = fetcher(web)
        # Act
        blocked = crawler.get("https://a.example/")
        moved = crawler.get("https://c.example/")
        # Assert
        self.assertEqual((blocked.status, blocked.url, blocked.err), ("robots", "https://b.example/home", "robots_disallow"))
        self.assertNotIn("https://b.example/home", web.page_urls())
        self.assertEqual((moved.status, moved.url), ("ok", "https://d.example/"))
        self.assertIn("https://d.example/robots.txt", [c["url"] for c in web.calls])
        self.assertTrue(spaced(web.times("d.example"), 1.0), web.calls)

    def test_robots_redirects_are_followed_only_where_allowed(self):
        # Arrange: one robots.txt moves to an allowed page on a rules host, two others redirect to each other.
        clock = FakeClock()
        web = FakeWeb({"http://a.example/robots.txt": (301, "", "https://a.example/robots.txt"),
                       "https://a.example/robots.txt": (302, "", "https://rules.example/a.txt"),
                       "https://rules.example/robots.txt": "User-agent: *\nDisallow: /private\n",
                       "https://rules.example/a.txt": "User-agent: *\nDisallow: /staff\n",
                       "https://loop1.example/robots.txt": (302, "", "https://loop2.example/rules"),
                       "https://loop2.example/robots.txt": (302, "", "https://loop1.example/rules")}, clock)
        crawler = fetcher(web)
        # Act
        moved = crawler.robots("http://a.example/")
        looped = crawler.robots("https://loop1.example/")
        # Assert: a's rules come from the allowed page; the loop ends in a refusal without fetching either page.
        self.assertEqual(moved.verdict, "rules")
        self.assertFalse(crawler.allowed("http://a.example/staff"))
        self.assertTrue(crawler.allowed("http://a.example/pta/"))
        self.assertEqual(looped.verdict, "deny")
        self.assertEqual([u for u in web.page_urls() if "loop" in u], [])
        self.assertTrue(spaced(web.times("rules.example"), 1.0), web.calls)

    def test_crawl_delay_is_honoured_from_the_robots_request(self):
        # Arrange
        clock = FakeClock()
        web = FakeWeb({"https://slow.example/robots.txt": "User-agent: *\nCrawl-delay: 10\n",
                       "https://slow.example/": page('<a href="/pta/">PTA</a>')}, clock)
        # Act
        pta_crawl.crawl_site("https://slow.example/", fetcher(web))
        # Assert
        times = web.times("slow.example")
        self.assertEqual(len(times), 3)
        self.assertTrue(spaced(times, 10.0), times)

    def test_long_crawl_delay_goes_to_the_slow_lane(self):
        # Arrange
        clock = FakeClock()
        web = FakeWeb({"https://nettl.example/robots.txt": "User-agent: *\nCrawl-delay: 300\n",
                       "https://nettl.example/": page('<a href="/pta/">PTA</a>'),
                       "https://sleepy.example/robots.txt": "User-agent: *\nCrawl-delay: 12000\n",
                       "https://sleepy.example/": page("<p>Welcome</p>")}, clock)
        crawler = fetcher(web)
        # Act
        main_pass = pta_crawl.crawl_site("https://nettl.example/", crawler)
        slow_lane = pta_crawl.crawl_site("https://nettl.example/", crawler, slow=True)
        sleepy_main = pta_crawl.crawl_site("https://sleepy.example/", crawler)
        sleepy_slow = pta_crawl.crawl_site("https://sleepy.example/", crawler, slow=True)
        # Assert
        self.assertEqual((main_pass.status, main_pass.trail[0]["err"]), ("slow", "crawl_delay_300s"))
        self.assertEqual((slow_lane.status, [p["kind"] for p in slow_lane.trail]), ("ok", ["home", "pta"]))
        self.assertTrue(spaced(web.times("nettl.example"), 300.0), web.times("nettl.example"))
        # However long the delay, the slow lane honours it in full rather than refusing the host.
        self.assertEqual((sleepy_main.status, sleepy_main.trail[0]["err"]), ("slow", "crawl_delay_12000s"))
        self.assertEqual(sleepy_slow.status, "ok")
        self.assertTrue(spaced(web.times("sleepy.example"), 12000.0), web.times("sleepy.example"))

    def test_slow_lane_wait_gives_up_when_stopping(self):
        # Arrange
        clock = FakeClock()
        web = FakeWeb({"https://nettl.example/robots.txt": "User-agent: *\nCrawl-delay: 300\n"}, clock)
        crawler = fetcher(web)
        crawler.robots("https://nettl.example/")
        crawler.stop.set()
        # Act / Assert
        with self.assertRaises(pta_crawl.Stopped):
            crawler.get("https://nettl.example/", slow=True)
        self.assertEqual(web.page_urls(), [])

    def test_child_failures_that_may_pass_mark_the_crawl_incomplete(self):
        # Arrange
        flaky = FakeWeb({"https://a.example/": page('<a href="/pta/">PTA</a>'), "https://a.example/pta/": (503, "")})
        gone = FakeWeb({"https://a.example/": page('<a href="/pta/">PTA</a>')})
        # Act
        got = [pta_crawl.crawl_site("https://a.example/", fetcher(web)).incomplete for web in (flaky, gone)]
        # Assert
        self.assertEqual(got, [True, False])

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
            self.assertTrue(spaced(times, 1.0), times)
        self.assertEqual(len(by_host["school.example"]), 4)   # robots.txt, home, /pta/, /friends/

    def test_rate_limiter_spaces_one_host_only(self):
        # Arrange
        clock = FakeClock()
        limiter = pta_crawl.RateLimiter(1.0, clock=clock.time, sleep=clock.sleep)
        # Act
        times = [limiter.wait("a.example"), limiter.wait("a.example"), limiter.wait("b.example"), limiter.wait("a.example")]
        # Assert
        self.assertEqual(times, [0.0, 1.0, 1.0, 2.0])

    def test_per_ip_limit_across_hosts(self):
        # Arrange: two school sites on one platform IP.
        clock = FakeClock()
        web = FakeWeb({"https://a.example/": page("<p>A</p>"), "https://b.example/": page("<p>B</p>")}, clock)
        crawler = fetcher(web, resolve=lambda host: "192.0.2.10")
        # Act
        crawler.get("https://a.example/")
        crawler.get("https://b.example/")
        # Assert: robots a, home a, robots b (held 0.5 s by the IP), home b (held by its host).
        self.assertEqual([c["t"] for c in web.calls], [0.0, 1.0, 1.5, 2.5])

    def test_user_agent_is_sent(self):
        # Arrange
        web = FakeWeb({"https://school.example/": page('<a href="/pta/">PTA</a>')})
        # Act
        pta_crawl.crawl_site("https://school.example/", fetcher(web))
        # Assert
        self.assertEqual({c["ua"] for c in web.calls}, {pta_crawl.USER_AGENT})
        self.assertEqual(len(web.calls), 3)

    def test_real_transport_sends_user_agent_and_hands_back_redirects(self):
        # Arrange
        seen = []

        class Response(io.BytesIO):
            status = 200
            headers = mock.Mock(get=lambda key, default=None: "text/html; charset=utf-8",
                                get_content_charset=lambda: "utf-8")

            def geturl(self):
                return "https://school.example/"

        class Opener:
            def open(self, request, timeout):
                seen.append((request.full_url, request.get_header("User-agent"), timeout))
                if request.full_url.endswith("/old"):
                    raise urllib.error.HTTPError(request.full_url, 301, "Moved", {"Location": "/new"}, io.BytesIO(b""))
                return Response("<p>Our PTA</p>".encode("utf-8"))

        # Act
        with mock.patch.dict(pta_crawl._OPENERS, {True: Opener()}):
            got = pta_crawl.Fetcher().fetch("https://school.example/", pta_crawl.Fetcher().headers, 10)
            moved = pta_crawl.http_get("https://school.example/old", {"User-Agent": pta_crawl.USER_AGENT}, 10)
        # Assert
        self.assertEqual(seen[0], ("https://school.example/", pta_crawl.USER_AGENT, 10))
        self.assertEqual(got, (200, "https://school.example/", "<p>Our PTA</p>"))
        self.assertEqual(moved, (301, "https://school.example/new", ""))


class RobotsCacheTest(NoNetworkTest):
    def test_robots_answers_are_reused_for_a_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            cache = Path(tmp) / "robots.jsonl"
            pages = {"https://school.example/robots.txt": "User-agent: *\nCrawl-delay: 2\n",
                     "https://down.example/robots.txt": (503, ""), "https://school.example/": "<p>Hi</p>"}
            runs = []
            for now in (1000.0, 2000.0, 1000.0 + 25 * 3600):
                web = FakeWeb(pages)
                crawler = fetcher(web, wall=lambda now=now: now)
                crawler.attach_robots_cache(cache)
                # Act
                crawler.get("https://school.example/")
                crawler.get("https://down.example/")
                runs.append([c["url"] for c in web.calls if c["url"].endswith("robots.txt")])
            rows = [json.loads(line) for line in cache.read_text(encoding="utf-8").splitlines()]
        # Assert: the 5xx is never kept; a day-old answer is fetched again and replaces the old row.
        self.assertEqual(runs, [["https://school.example/robots.txt", "https://down.example/robots.txt"],
                                ["https://down.example/robots.txt"],
                                ["https://school.example/robots.txt", "https://down.example/robots.txt"]])
        self.assertEqual([(r["origin"], r["crawl_delay"]) for r in rows], [("https://school.example", 2.0)])


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
    def run_main(self, root, *args, web=None, crawler=None):
        web = web or FakeWeb(WEB)
        out = root / "money/pta_crawl.json"
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            pta_crawl.main(["--site-data", str(root), "--charity-dir", str(root / "charity"), "--out", str(out),
                            "--workers", "2", *args], fetcher=crawler or fetcher(web))
        return web, out, printed.getvalue()

    def read(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def test_output_matches_the_shared_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            # Act
            web, out, printed = self.run_main(root)
            data, state = self.read(out), self.read(pta_crawl.state_path(out))
            leftovers = [p.name for p in out.parent.iterdir() if p.name.endswith(".tmp")]
        # Assert
        self.assertEqual(sorted(data), ["generated", "meta", "schools", "user_agent"])
        self.assertEqual(data["user_agent"], pta_crawl.USER_AGENT)
        self.assertEqual(list(data["schools"]), ["130932"])
        hit = data["schools"]["130932"][0]
        self.assertLessEqual({"charity_number", "evidence", "source_url"}, set(hit))
        self.assertEqual((hit["charity_number"], hit["source_url"]), (1103834, "https://williampatten.example/pta/"))
        self.assertEqual(data["meta"]["outcomes"], {"hit": 1, "no_pta": 2})
        self.assertEqual(state["no_pta"], ["100001", "100005"])
        self.assertFalse({"german.example", "closed.example"} & {pta_crawl.host_key(u) for u in web.page_urls()})
        self.assertIn("1 with a PTA number", printed)
        self.assertEqual(leftovers, [])

    def test_merge_reads_the_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            _, out, _ = self.run_main(root)
            charities = {1103834: {"registered_charity_number": 1103834, "linked_charity_number": 0, "charity_name": PTFA}}
            matches = {}
            # Act
            added = pta_crawl.pta.merge_crawl(matches, self.read(out), charities, {"130932"})
        # Assert
        self.assertEqual(added, 1)
        self.assertEqual(matches["130932"][0]["match"]["method"], "website-crawl")

    def test_numbers_that_do_not_agree_go_to_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange: William Patten's homepage carries news of Grasmere's PTA, and nothing of its own.
            root = Path(tmp)
            write_fixture(root, SCHOOLS[:1])
            web = FakeWeb({"https://williampatten.example/": page("<p>Well done to Grasmere Primary School PTA, "
                                                                  "registered charity 1111114.</p>")})
            # Act
            _, out, _ = self.run_main(root, web=web)
            data, review, state = self.read(out), self.read(pta_crawl.review_path(out)), self.read(pta_crawl.state_path(out))
        # Assert
        self.assertEqual(data["schools"], {})
        self.assertEqual([(h["charity_number"], h["reason"]) for h in review["schools"]["130932"]], [(1111114, "no_agreement")])
        self.assertIn("never merged", review["note"])
        self.assertEqual(state["review"], ["130932"])
        self.assertFalse(any(word in review["note"].lower() for word in BANNED))

    def test_limit_stops_early(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            # Act
            web, out, _ = self.run_main(root, "--limit", "1")
            data = self.read(out)
        # Assert
        self.assertEqual({pta_crawl.host_key(u) for u in web.page_urls()}, {"williampatten.example"})
        self.assertEqual(list(data["schools"]), ["130932"])

    def test_resume_skips_done_urns_from_an_older_crawler(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange: outputs of the first crawler, which kept no journal.
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            out = root / "money/pta_crawl.json"
            out.parent.mkdir()
            earlier = {"charity_number": 1103834, "source_url": "https://williampatten.example/pta/", "evidence": "PTFA"}
            out.write_text(json.dumps({"generated": "x", "user_agent": "x", "schools": {"130932": [earlier]}}), encoding="utf-8")
            pta_crawl.state_path(out).write_text(json.dumps({"no_pta": ["100001"]}), encoding="utf-8")
            # Act
            web, out, _ = self.run_main(root, "--resume")
            data, state = self.read(out), self.read(pta_crawl.state_path(out))
        # Assert
        self.assertEqual(web.page_urls(), ["https://hollypark.example/"])
        self.assertEqual(data["schools"], {"130932": [earlier]})
        self.assertEqual(state["no_pta"], ["100001", "100005"])

    def test_outputs_are_rebuilt_from_the_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            _, out, _ = self.run_main(root)
            first = self.read(out)["schools"]
            out.unlink()
            # Act
            web, out, _ = self.run_main(root, "--resume")
            lines = pta_crawl.journal_path(out).read_text(encoding="utf-8").splitlines()
            rebuilt = self.read(out)["schools"]
        # Assert
        self.assertEqual(web.calls, [])
        self.assertEqual(rebuilt, first)
        self.assertEqual(sorted(json.loads(line)["urn"] for line in lines), ["100001", "100005", "130932"])
        self.assertEqual({json.loads(line)["pass"] for line in lines}, {"main"})

    def test_never_fetched_websites_are_skipped_for_good(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange: two register websites that are themselves on the never-fetch lists.
            root = Path(tmp)
            write_fixture(root, [
                {"urn": 100006, "name": "Facebook Primary School", "website": "https://www.facebook.com/fbprimary"},
                {"urn": 100007, "name": "Leaflet Primary School", "website": "https://leaflet.example/docs/home.pdf"}])
            # Act
            web, out, printed = self.run_main(root)
            data, state = self.read(out), self.read(pta_crawl.state_path(out))
            again, _, _ = self.run_main(root, "--resume")
        # Assert: nothing requested, robots.txt included, and --resume does not come back to them.
        self.assertEqual((web.calls, again.calls), ([], []))
        self.assertEqual(data["meta"]["outcomes"], {"skipped": 2})
        self.assertEqual((state["skipped"], state["failed"]), (["100006", "100007"], []))
        self.assertIn("2 with a website never fetched", printed)

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

    def test_only_unmatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange: pta.json matches William Patten; Holly Park's only record is held for review.
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            matched = root / "pta.json"
            matched.write_text(json.dumps({"schools": {"130932": [{"charity_number": 1103834}],
                                                       "100005": [{"charity_number": 1111115, "review": "check"}]}}),
                               encoding="utf-8")
            # Act
            web, _, _ = self.run_main(root, "--only-unmatched", str(matched))
        # Assert
        self.assertEqual(sorted(web.page_urls()), ["http://grasmere.example/", "https://hollypark.example/"])

    def test_stop_drains_then_resume_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange: the stop arrives during the first school's homepage request.
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            web = FakeWeb(WEB)
            crawler = fetcher(web)
            web.on_call = lambda url: crawler.stop.set()
            # Act
            _, out, printed = self.run_main(root, "--workers", "1", web=web, crawler=crawler)
            journalled = pta_crawl.journal_path(out).read_text(encoding="utf-8").splitlines()
            finish, out, _ = self.run_main(root, "--resume")
            state, found = self.read(pta_crawl.state_path(out)), self.read(out)["schools"]
        # Assert: one school finished and was journalled; the other two waited for --resume.
        self.assertIn("stopped:", printed)
        self.assertEqual(len(journalled), 1)
        self.assertEqual(len({pta_crawl.host_key(u) for u in web.page_urls()}), 1)
        self.assertEqual(len({pta_crawl.host_key(u) for u in finish.page_urls()}), 2)
        self.assertEqual(state["no_pta"], ["100001", "100005"])
        self.assertEqual(list(found), ["130932"])

    def test_signals_ask_for_a_drain_then_stop(self):
        # Arrange
        stop, said = threading.Event(), []
        before = signal.getsignal(signal.SIGTERM)
        restore = pta_crawl._on_signals(stop, said.append)
        try:
            # Act
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            # Assert
            self.assertTrue(stop.is_set())
            self.assertIn("finishing the ones in flight", said[0])
            with self.assertRaises(KeyboardInterrupt):
                signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        finally:
            restore()
        self.assertIs(signal.getsignal(signal.SIGTERM), before)

    def test_homepage_timeout_is_retried_once_with_a_longer_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS[:1])
            slow_home = lambda verify, timeout: page('<a href="/pta/">PTFA</a>') if timeout >= 20 else TimeoutError("timed out")  # noqa: E731
            web = FakeWeb(dict(WEB, **{"https://williampatten.example/": slow_home}))
            # Act
            _, out, _ = self.run_main(root, web=web)
            lines = [json.loads(line) for line in pta_crawl.journal_path(out).read_text(encoding="utf-8").splitlines()]
            found = self.read(out)["schools"]
        # Assert
        self.assertEqual([(line["pass"], line["outcome"]) for line in lines], [("main", "error"), ("retry", "hit")])
        self.assertEqual([c["timeout"] for c in web.calls if c["url"] == "https://williampatten.example/"], [10, 20])
        self.assertEqual(list(found), ["130932"])

    def test_long_crawl_delay_schools_finish_in_the_slow_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Arrange
            root = Path(tmp)
            write_fixture(root, SCHOOLS)
            clock = FakeClock()
            web = FakeWeb(dict(WEB, **{"https://hollypark.example/robots.txt": "User-agent: *\nCrawl-delay: 120\n"}), clock)
            # Act
            _, out, _ = self.run_main(root, "--workers", "1", web=web, crawler=fetcher(web, clock))
            lines = [json.loads(line) for line in pta_crawl.journal_path(out).read_text(encoding="utf-8").splitlines()]
            state = self.read(pta_crawl.state_path(out))
        # Assert
        holly = [(line["pass"], line["outcome"]) for line in lines if line["urn"] == "100005"]
        self.assertEqual(holly, [("main", "slow"), ("slow", "no_pta")])
        self.assertTrue(spaced(web.times("hollypark.example"), 120.0), web.times("hollypark.example"))
        self.assertEqual(state["no_pta"], ["100001", "100005"])

    def test_order_is_shuffled_and_workers_capped(self):
        # Arrange
        schools = [{"urn": n} for n in range(30)]
        # Act
        once, again = pta_crawl.crawl_order(schools), pta_crawl.crawl_order(schools)
        # Assert
        self.assertEqual(once, again)
        self.assertNotEqual(once, schools)
        self.assertEqual(sorted(s["urn"] for s in once), list(range(30)))
        self.assertEqual([sum(pta_crawl._pool_sizes(w)) for w in (1, 6, 24, 100)], [1, 6, 24, 24])
        self.assertEqual(pta_crawl._pool_sizes(24), (20, 4))


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


class TwoSchoolSiteTest(NoNetworkTest):
    def test_shared_site_crawls_until_each_school_has_its_own_pta(self):
        # Arrange: a federation site naming both schools' PTAs on different pages.
        web = FakeWeb({"https://millrythe.example/": page('<a href="/infant-pta/">Infant PTA</a><a href="/junior-pta/">Junior PTA</a>'),
                       "https://millrythe.example/infant-pta/": page("<p>Friends of Mill Rythe Infant School, registered charity 1111117</p>"),
                       "https://millrythe.example/junior-pta/": page("<p>Friends of Mill Rythe Junior School, registered charity 1111113</p>")})
        registry = {**REGISTRY, 1111117: "FRIENDS OF MILL RYTHE INFANT SCHOOL"}
        schools = [{"urn": 1, "name": "Mill Rythe Infant School", "website": "https://millrythe.example/"},
                   {"urn": 2, "name": "Mill Rythe Junior School", "website": "https://millrythe.example/"}]
        shared = {pta_crawl.site_key("https://millrythe.example/"): 2}
        # Act
        lines = pta_crawl.crawl_group(schools, fetcher(web), registry, shared)
        # Assert: each keeps its own PTA, and a partner's accepted PTA is not sent to review.
        self.assertEqual([[h["charity_number"] for h in line["hits"]] for line in lines], [[1111117], [1111113]])
        self.assertEqual([line["review"] for line in lines], [[], []])


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
        self.assertEqual(got[0]["meta"]["pa_tier"], "strict")


if __name__ == "__main__":
    unittest.main()
