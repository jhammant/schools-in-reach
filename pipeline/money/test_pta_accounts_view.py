"""Gated publication, safe rendering and an offline build of PTA account notes."""

from html import escape, unescape
import json
import re
from unittest.mock import patch

import pytest

from pipeline.money import area_pages, build_money, pta_accounts_view, school_page, site
from pipeline.money.test_build_money import Balance, full_rows, make_site, school
from pipeline.money.test_school_page import big_school, cfr_school, charity, nearby_contract

SOURCE = "https://register-of-charities.charitycommission.gov.uk/en/charity-search?p_p_resource_id=%2Faccounts-resource&objectiveId=TEST"
DISCLAIMER = ("Read automatically from the accounts the charity filed with the Charity Commission, "
              "so check the original before relying on a figure.")


def account(**overrides):
    record = {"name": "Friends of Example", "urns": ["100001"], "reporting_year": "31 August 2025",
              "source_url": SOURCE, "extracted": True, "coverage": 0.9,
              "facts": {"year_end": "2025-08-31", "total_income": 10_000, "total_spending": 9_000,
                        "how_raised": [{"method": "Summer fair", "amount": 8_000}, {"method": "Disco", "amount": None}],
                        "gift_aid": 750, "given_to_school": 5_000,
                        "paid_for": [{"item": "Library books", "amount": 1_200}, {"item": "Playground", "amount": None}],
                        "platforms": ["easyfundraising", "PTA Events"], "volunteers": None, "notes": None}}
    record.update(overrides)
    return record


def checked_doc(**records):
    return {"spot_check": {"n": 10, "wrong": 0, "checked": "2026-11-15"}, **records}


def plain(html):
    return unescape(re.sub(r"<[^>]*>", "", html))


@pytest.mark.parametrize("spot", [None, {}, {"n": 9, "wrong": 0}, {"n": 10, "wrong": 1},
                                  {"n": 10}, {"n": "10", "wrong": 0}, {"n": True, "wrong": 0},
                                  {"n": 10, "wrong": False}, {"n": 10, "wrong": "0"}])
def test_gate_hides_unchecked_or_failed_accounts(tmp_path, spot):
    # Arrange
    path = tmp_path / "pta_accounts.json"
    doc = {"1234567": account()}
    if spot is not None:
        doc["spot_check"] = spot
    path.write_text(json.dumps(doc), encoding="utf-8")
    before, messages = path.read_bytes(), []
    # Act
    result = pta_accounts_view.load(path, messages.append)
    # Assert
    assert result == {}
    assert messages and "PTA accounts hidden:" in messages[0]
    assert path.read_bytes() == before


@pytest.mark.parametrize("contents, reason", [(None, "missing"), ("{unfinished", "could not be read"), ("[]", "no spot check")])
def test_gate_handles_missing_or_unreadable_input(tmp_path, contents, reason):
    # Arrange
    path = tmp_path / "pta_accounts.json"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")
    messages = []
    # Act
    result = pta_accounts_view.load(path, messages.append)
    # Assert
    assert result == {}
    assert reason in messages[0]
    assert path.exists() == (contents is not None)


def test_gate_publishes_only_extracted_records_with_a_register_source(tmp_path):
    # Arrange
    doc = checked_doc(**{"1234567": account(), "2345678": {"status": "no accounts filed"},
                         "3456789": account(extracted=False), "4567890": account(facts=None),
                         "5678901": account(source_url="javascript:alert(1)"), "metadata": account()})
    path = tmp_path / "pta_accounts.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    before, messages = path.read_bytes(), []
    # Act
    result = pta_accounts_view.load(path, messages.append)
    # Assert
    assert result == {"1234567": doc["1234567"]}
    assert "spot check passed; 1 extracted" in messages[0]
    assert path.read_bytes() == before


@pytest.mark.parametrize("coverage, partial", [(1.0, False), (0.6, False), (0.599, True), (None, True)])
def test_details_coverage_amounts_and_provenance(coverage, partial):
    # Arrange
    record = account(coverage=coverage)
    # Act
    html = school_page.pta_accounts_details(record)
    text = plain(html)
    # Assert
    assert html.startswith('<details class="sp-accounts"><summary>How Friends of Example raised it (31 August 2025 accounts)</summary>')
    assert " open" not in html
    assert ("Some of the ways it raised money:" in text) is partial
    assert "Summer fair" in text and 'data-v="8000"' in html
    assert "Disco (amount not given)" in text
    assert "Gift Aid:" in text and 'data-v="750"' in html
    assert "Given to the school:" in text and 'data-v="5000"' in html
    assert "Library books" in text and 'data-v="1200"' in html
    assert "Playground (amount not given)" in text
    assert "Platforms named in the accounts: easyfundraising, PTA Events." in text
    assert f'href="{escape(SOURCE, quote=True)}"' in html
    assert text.endswith(DISCLAIMER)
    assert "data-pp=" not in html
    assert "whole association" in text


def test_details_missing_optional_facts_do_not_invent_zeroes():
    # Arrange
    record = account(coverage=None, reporting_year=None, facts={"year_end": "2025-08-31"})
    # Act
    html = school_page.pta_accounts_details(record)
    # Assert
    assert "2025-08-31 accounts" in html
    assert "did not identify how it raised money" in html
    assert "£" not in html
    assert "Gift Aid:" not in html and "Given to the school:" not in html
    assert plain(html).endswith(DISCLAIMER)


def test_details_escape_every_extracted_string():
    # Arrange
    hostile = '<img src=x onerror="alert(1)"> & \'text\''
    record = account(name=hostile, reporting_year=hostile, source_url=SOURCE + '&q=" onclick="alert(1)')
    record["facts"].update(how_raised=[{"method": hostile, "amount": 10}],
                           paid_for=[{"item": hostile, "amount": None}], platforms=[hostile])
    # Act
    html = school_page.pta_accounts_details(record)
    parser = Balance(html)
    # Assert
    assert hostile not in html
    assert html.count(escape(hostile, quote=True)) >= 5
    assert '<img' not in html and ' onclick="' not in html
    assert f'href="{escape(record["source_url"], quote=True)}"' in html
    assert not parser.errors and not parser.stack


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,test", "https://evil.test/a.pdf",
                                 "https://register-of-charities.charitycommission.gov.uk.evil.test/a.pdf", None])
def test_details_reject_unsafe_or_missing_provenance(url):
    # Arrange
    record = account(source_url=url)
    # Act
    html = school_page.pta_accounts_details(record)
    # Assert
    assert html == ""


def test_school_only_shows_accounts_for_its_current_unflagged_associations():
    # Arrange
    charities = [charity(1234567), charity(1234567), charity(2345678), charity(3456789, review="check match")]
    item, ctx = cfr_school(pta=charities)
    ctx["pta_accounts"] = {"1234567": account(), "2345678": account(name="Second association"),
                           "3456789": account(name="Held for review"), "4567890": account(name="Unmatched charity")}
    # Act
    html = school_page.render(item, ctx)["body"]
    # Assert
    assert html.count('<details class="sp-accounts">') == 2
    assert "How Second association raised it" in html
    assert "How Held for review" not in html and "How Unmatched charity" not in html
    section = re.search(r'<section[^>]*id="ptfa".*?</section>', html, re.S).group(0)
    assert section.count('<details class="sp-accounts">') == 2


@pytest.mark.parametrize("text, expected", [
    ("Summer fair", {"Fairs"}), ("Summer Fair", {"Fairs"}), ("summer fete", {"Fairs"}), ("Christmas fête", {"Fairs"}),
    ("School discos", {"Discos"}), ("Cake sale", {"Cake sales"}), ("Bake sales", {"Cake sales"}),
    ("Non-uniform days", {"Non-uniform days"}), ("Mufti day", {"Non-uniform days"}), ("Dress-down day", {"Non-uniform days"}),
    ("Second-hand uniform sales", {"Uniform sales"}), ("Pre-loved uniform shop", {"Uniform sales"}),
    ("Raffles", {"Raffles and lotteries"}), ("School lottery", {"Raffles and lotteries"}), ("100 club", {"Raffles and lotteries"}),
    ("Quiz night", {"Quiz nights"}), ("Quizzes", {"Quiz nights"}), ("GiftAid", {"Gift Aid"}), ("Gift Aid", {"Gift Aid"}),
    ("Matched funding", {"Match funding"}), ("Employer matched giving", {"Match funding"}),
    ("Grants", {"Grants"}), ("Sponsored walk", {"Sponsored events"}), ("EasyFundraising", {"Online shopping platforms"}),
    ("Amazon Smile", {"Online shopping platforms"}), ("Give as you Live", {"Online shopping platforms"}),
    ("PTA Events", set()), ("Kindlink", set()), ("Unfair discounts", set()), (None, set()),
    ("Summer fair and raffle", {"Fairs", "Raffles and lotteries"}),
])
def test_normalise_methods(text, expected):
    # Arrange: phrases from accounts are labels, not arbitrary substring matches.
    # Act
    result = pta_accounts_view.normalise_methods(text)
    # Assert
    assert result == expected


def test_ptfa_counts_mentions_once_per_charity_with_all_extracted_records_as_denominator():
    # Arrange: a shared charity and duplicate methods still count once; an unknown method stays in N.
    records = {"1": account(urns=["100001", "100002"]), "2": account(), "3": account(facts={"how_raised": [{"method": "Car parking"}]})}
    records["1"]["facts"]["how_raised"] += [{"method": "SUMMER FETE"}, {"method": "Gift Aid"}, {"method": "easyfundraising"}]
    records["2"]["facts"].update(how_raised=[{"method": "summer fair"}, {"method": "Uniform sales"}], gift_aid=0, platforms=[])
    # Act
    result = area_pages.render_ptfa({}, [], {"pta_accounts": records})
    text = plain(result["intro"])
    # Assert
    assert "How the biggest fundraisers raise money" in text
    assert "Fairs: 2 of 3 associations" in text
    assert "Discos: 1 of 3 associations" in text
    assert "Gift Aid: 1 of 3 associations" in text
    assert "Online shopping platforms: 1 of 3 associations" in text
    assert "Uniform sales: 1 of 3 associations" in text
    assert "selected sample, not all associations" in text
    assert "do not show which methods raised the most money" in text
    assert '/guides/ptfa/' in result["intro"]
    assert len(result["intro"].encode()) < area_pages.PAGE_TEXT_BUDGET


def test_ptfa_without_gated_accounts_omits_the_section():
    # Arrange
    ctx = {}
    # Act
    result = area_pages.render_ptfa({}, [], ctx)
    # Assert
    assert "How the biggest fundraisers raise money" not in result["intro"]


def test_big_school_with_three_accounts_and_nearby_stays_within_budget():
    # Arrange: the extractor asks for up to ten income and ten spending lines per charity.
    item, ctx = big_school()
    ctx["nearby"] = nearby_contract()
    records = {}
    for c in item["pta"]:
        record = account(name=c["name"])
        record["facts"]["how_raised"] = [{"method": f"Summer fair and raffle number {i}", "amount": 1000 + i} for i in range(10)]
        record["facts"]["paid_for"] = [{"item": f"Books and playground equipment {i}", "amount": 1000 + i} for i in range(10)]
        records[str(c["charity_number"])] = record
    ctx["pta_accounts"] = records
    # Act
    result = school_page.render(item, ctx)
    pages = [site.page(result["title"], result["description"], item["path"], body, [],
                       extra_head=school_page.EXTRA_HEAD) for body in [result["body"]] + result["lighter"]]
    # Assert
    assert any(build_money.page_bytes(html) < build_money.SCHOOL_PAGE_BUDGET for html in pages)
    assert all(html.count('<details class="sp-accounts">') == 3 for html in pages)


@pytest.mark.parametrize("spot, visible", [("missing", False), (None, False), ({"n": 10, "wrong": 1}, False),
                                          ({"n": 10, "wrong": 0}, True)])
def test_build_threads_only_gated_accounts_to_school_and_ptfa_pages(tmp_path, spot, visible):
    # Arrange
    pta = {"100001": [charity(1234567)], "100002": [charity(1234567)]}
    source, history, links, pta_path = make_site(tmp_path, [("204", "Hackney")],
                                              {"204": [school(100001, "Example Primary"), school(100002, "New Primary")]},
                                              full_rows("100001"), pta)
    accounts_path = tmp_path / "pta_accounts.json"
    doc = {"1234567": account(), "2345678": {"status": "no accounts filed"}}
    if isinstance(spot, dict):
        doc["spot_check"] = spot
    if spot != "missing":
        accounts_path.write_text(json.dumps(doc), encoding="utf-8")
    before = accounts_path.read_bytes() if accounts_path.exists() else None
    out = tmp_path / "money"
    # Act
    with patch("sys.argv", ["build_money", "--site-dir", str(source), "--history", str(history), "--links", str(links),
                            "--pta", str(pta_path), "--pta-accounts", str(accounts_path), "--out", str(out)]):
        build_money.main()
    school_pages = [path.read_text(encoding="utf-8") for path in (out / "school").glob("*/index.html")]
    ptfa_html = (out / "ptfa/index.html").read_text(encoding="utf-8")
    # Assert
    assert len(school_pages) == 2
    for html in school_pages:
        assert ('<details class="sp-accounts">' in html) is visible
        assert build_money.page_bytes(html) < build_money.SCHOOL_PAGE_BUDGET
    assert ("How the biggest fundraisers raise money" in ptfa_html) is visible
    assert (accounts_path.read_bytes() if accounts_path.exists() else None) == before
    assert "Summer fair" not in (out / "data/search.json").read_text(encoding="utf-8")
    for html in school_pages + [ptfa_html]:
        parser = Balance(html)
        assert not parser.errors and not parser.stack
