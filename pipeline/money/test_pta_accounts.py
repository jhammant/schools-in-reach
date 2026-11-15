"""Offline tests for the existing accounts reader's selection, coverage and table parsing."""

import json
from pathlib import Path
import re
from unittest.mock import patch

import pytest

from pipeline.money import pta_accounts

FIXTURE = Path(__file__).with_name("fixtures") / "pta_accounts_register.html"


@pytest.mark.parametrize("facts, expected", [
    ({}, None),
    ({"total_income": None, "how_raised": [{"amount": 50}]}, None),
    ({"total_income": "100", "how_raised": [{"amount": 50}]}, None),
    ({"total_income": 0, "how_raised": [{"amount": 50}]}, None),
    ({"total_income": -1, "how_raised": [{"amount": 50}]}, None),
    ({"total_income": 100, "how_raised": []}, None),
    ({"total_income": 100, "how_raised": [{"amount": None}, {"amount": "50"}]}, None),
    ({"total_income": 100, "how_raised": [{"amount": 30}, {"amount": 20}, {"amount": None}, "unknown"]}, 0.5),
    ({"total_income": 3, "how_raised": [{"amount": 2}]}, 0.667),
    ({"total_income": 100, "how_raised": [{"amount": 100}]}, 1.0),
    ({"total_income": 100, "how_raised": [{"amount": 120}]}, 1.2),
    ({"total_income": 1, "how_raised": [{"amount": 100}]}, 9.99),
])
def test_coverage(facts, expected):
    # Arrange: known and unknown amounts must not be estimated.
    original = json.dumps(facts)
    # Act
    actual = pta_accounts.coverage(facts)
    # Assert
    assert actual == expected
    assert json.dumps(facts) == original


def test_top_associations_ranks_distinct_registered_charities_and_keeps_shared_urns(tmp_path):
    # Arrange
    def charity(number, income, status="Registered"):
        return {"charity_number": number, "name": f"Friends {number}", "status": status, "latest_income": income}

    path = tmp_path / "pta.json"
    path.write_text(json.dumps({"schools": {
        "100001": [charity(1, 50_000), charity(2, 150_000), charity(3, 600_000), charity(4, 300_000, "Removed")],
        "100002": [charity(2, 150_000), charity(5, None), charity(6, 0), charity(7, 500_000)],
    }}), encoding="utf-8")
    # Act
    with patch.object(pta_accounts, "PTA", path):
        result = pta_accounts.top_associations(2)
        all_results = pta_accounts.top_associations(20)
    # Assert
    assert [r["charity_number"] for r in result] == [7, 2]
    assert result[1]["urns"] == ["100001", "100002"]
    assert result[1]["name"] == "Friends 2"
    assert [r["charity_number"] for r in all_results] == [7, 2, 1]


def test_top_associations_without_pta_file(tmp_path):
    # Arrange
    path = tmp_path / "missing.json"
    # Act
    with patch.object(pta_accounts, "PTA", path):
        result = pta_accounts.top_associations(10)
    # Assert
    assert result == []


def test_newest_accounts_skips_overdue_not_required_and_other_documents():
    # Arrange
    table = FIXTURE.read_bytes()
    # Act
    with patch.object(pta_accounts, "fetch", return_value=table) as fetch:
        url, year = pta_accounts.newest_accounts_url(12345)
    # Assert
    fetch.assert_called_once_with(pta_accounts.SITE + "/en/charity-search/-/charity-details/12345/accounts-and-annual-returns")
    assert year == "31 August 2024"
    assert url == pta_accounts.SITE + "/en/charity-search?p_p_resource_id=%2Faccounts-resource&objectiveId=A2024"


def test_newest_accounts_without_download():
    # Arrange: retain the table's overdue and not-required rows, remove downloads.
    table = re.sub(r"<a\b.*?</a>", "", FIXTURE.read_text(encoding="utf-8"), flags=re.S).encode()
    # Act
    with patch.object(pta_accounts, "fetch", return_value=table):
        result = pta_accounts.newest_accounts_url(12345)
    # Assert
    assert result == (None, None)
