"""Independent Wave B regression repros; fixture HTTP, fake clocks, no network or sleeping."""

import contextlib
import io
import json
import socket
import time
import urllib.request

import pytest

from pipeline.money import pta_crawl
from pipeline.money import test_pta_crawl as fixtures


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Real network or sleep used by an offline review test")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(time, "sleep", forbidden)


def school(urn=130932, name="William Patten Primary School", website="https://williampatten.example/"):
    return {"urn": urn, "name": name, "website": website,
            "type_group": "Local authority maintained schools"}


def run_main(root, pages, *extra):
    clock = fixtures.FakeClock()
    web = fixtures.FakeWeb(pages, clock)
    out = root / "money/pta_crawl.json"
    with contextlib.redirect_stdout(io.StringIO()):
        result = pta_crawl.main([
            "--site-data", str(root), "--charity-dir", str(root / "charity"),
            "--out", str(out), "--workers", "1", *extra,
        ], fetcher=fixtures.fetcher(web, clock))
    assert result == 0
    return json.loads(out.read_text(encoding="utf-8")), web


def test_resume_recovers_new_result_after_partial_journal_tail(tmp_path):
    # Arrange: a crash interrupted the next JSON row after one completed school.
    fixtures.write_fixture(tmp_path, [school()])
    out = tmp_path / "money/pta_crawl.json"
    journal = pta_crawl.Journal(pta_crawl.journal_path(out))
    journal.append({"urn": "100001", "outcome": "no_pta", "pass": "main",
                    "crawl_version": pta_crawl.CRAWL_VERSION, "hits": [], "review": []})
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write('{"urn": "130932", "outcome": ')

    # Act: the resumed school successfully finds and journals its PTA.
    output, web = run_main(tmp_path, {
        "https://williampatten.example/": "<p>Our PTFA, registered charity 1103834.</p>",
    }, "--resume")

    # Assert: both the previous result and the new complete row survive rebuilding.
    assert web.page_urls() == ["https://williampatten.example/"]
    assert [hit["charity_number"] for hit in output["schools"].get("130932", [])] == [1103834]
    assert set(journal.latest()) == {"100001", "130932"}


def test_google_sites_pta_link_is_crawled(tmp_path):
    # Arrange: a normal Google Sites URL needs multiple path components.
    fixtures.write_fixture(tmp_path, [school()])
    pta_url = "https://sites.google.com/view/williampattenpta/home"
    pages = {
        "https://williampatten.example/": '<a href="/pta/">PTFA</a>',
        "https://williampatten.example/pta/": f'<a href="{pta_url}">Visit our PTFA website</a>',
        pta_url: "<p>William Patten PTFA, registered charity 1103834.</p>",
    }

    # Act
    output, web = run_main(tmp_path, pages)

    # Assert: allowed PTA platform mini-sites must actually be discovered and fetched.
    assert [hit["charity_number"] for hit in output["schools"].get("130932", [])] == [1103834], web.calls
    assert pta_url in web.page_urls()


def test_resume_retries_transient_meta_refresh_target(tmp_path):
    # Arrange: the register homepage is a short redirect stub, whose target is briefly unavailable.
    fixtures.write_fixture(tmp_path, [school()])
    stub = '<html><head><meta http-equiv="refresh" content="0; url=/home/"></head><body></body></html>'
    run_main(tmp_path, {
        "https://williampatten.example/": stub,
        "https://williampatten.example/home/": (503, ""),
    })

    # Act: the same target recovers before --resume.
    output, web = run_main(tmp_path, {
        "https://williampatten.example/": stub,
        "https://williampatten.example/home/": '<a href="/pta/">PTFA</a>',
        "https://williampatten.example/pta/": "<p>Our PTFA, registered charity 1103834.</p>",
    }, "--resume")

    # Assert: a failed refresh must not become a permanent completed no-PTA result.
    assert [hit["charity_number"] for hit in output["schools"].get("130932", [])] == [1103834], web.calls


def test_case_sensitive_query_homepages_are_distinct(tmp_path):
    # Arrange: query identifiers are case-sensitive, like opaque IDs used by a shared CMS.
    william = "https://schools.example/index.php?school=Ab12"
    grasmere = "https://schools.example/index.php?school=ab12"
    fixtures.write_fixture(tmp_path, [school(website=william), school(100001, "Grasmere Primary School", grasmere)])

    # Act
    output, web = run_main(tmp_path, {
        william: "<p>William Patten PTFA, registered charity 1103834.</p>",
        grasmere: "<p>Grasmere Primary School PTA, registered charity 1111114.</p>",
    })

    # Assert: both real pages must be fetched and each school gets its own charity.
    assert {urn: [hit["charity_number"] for hit in hits] for urn, hits in output["schools"].items()} == {
        "130932": [1103834], "100001": [1111114],
    }, web.calls


@pytest.mark.parametrize("url", [
    "https://www.facebook.com/williampattenpta",
    "https://school.example/docs/pta.pdf",
])
def test_never_fetch_rules_apply_to_start_url(tmp_path, url):
    # Arrange: an input website points straight at a forbidden host or document.
    fixtures.write_fixture(tmp_path, [school(website=url)])

    # Act
    _, web = run_main(tmp_path, {url: "<p>Our PTFA</p>"})

    # Assert: the never-fetch rules also apply before the first page request.
    assert url not in web.page_urls(), web.calls


def test_robots_redirect_target_obeys_destination_robots():
    # Arrange: robots.txt redirects to a different origin's explicitly disallowed path.
    clock = fixtures.FakeClock()
    target = "https://private.example/secret"
    web = fixtures.FakeWeb({
        "https://school.example/robots.txt": (302, "", target),
        "https://private.example/robots.txt": "User-agent: *\nDisallow: /secret\n",
        target: "User-agent: *\nDisallow:\n",
        "https://school.example/": "<p>School</p>",
    }, clock)
    crawler = fixtures.fetcher(web, clock)

    # Act
    crawler.get("https://school.example/")

    # Assert: every redirected non-robots URL must pass its destination's permission check.
    assert target not in web.page_urls(), web.calls


def test_slow_lane_honours_delays_longer_than_ten_minutes(tmp_path):
    # Arrange: section 6 requires the production slow lane to honour the full delay;
    # the measured sample includes a host requesting 12,000 seconds.
    fixtures.write_fixture(tmp_path, [school()])
    delay = 12000

    # Act: the fake clock advances instantly; no real sleep is used.
    output, web = run_main(tmp_path, {
        "https://williampatten.example/robots.txt": f"User-agent: *\nCrawl-delay: {delay}\n",
        "https://williampatten.example/": "<p>Our PTFA, registered charity 1103834.</p>",
    })

    # Assert: a long delay is deferred and honoured, not stored as a permanent refusal.
    assert [hit["charity_number"] for hit in output["schools"].get("130932", [])] == [1103834]
    times = web.times("williampatten.example")
    assert len(times) == 2
    assert times[1] - times[0] >= delay
