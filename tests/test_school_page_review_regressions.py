"""Offline repros for the school-page unit's rendering contract."""

import json
import re
from html import unescape
from pathlib import Path

import pytest

from pipeline.money import school_page
from pipeline.money.test_school_page import (
    aar_academy,
    cfr_school,
    charity,
    figures,
)


def section(body, ident):
    match = re.search(
        rf'<section\b[^>]*\bid="{re.escape(ident)}"[^>]*>(.*?)</section>',
        body,
        re.S,
    )
    assert match, f"Missing section {ident}"
    return match.group(1)


def test_historical_funding_summary_uses_its_own_years_similar_median():
    # Arrange: the newest spending is suspect, so the summary uses the previous year.
    item, ctx = cfr_school()
    previous, latest = ctx["series"]["years"][-2:]
    ctx["series"]["flags"]["suspect"] = {latest: ["total_expenditure"]}
    ctx["similar"]["total_expenditure"] = 9000
    medians = {previous: 5000, latest: 9000}
    ctx["similar_series"]["total_expenditure"] = medians

    # Act
    funding = section(school_page.render(item, ctx)["body"], "funding")
    spending = figures(funding, "total_expenditure")

    # Assert: either omit the comparison or use the median for the figure's year.
    wrong = [f for f in spending if "data-cmp-similar" in f
             and float(f["data-cmp-similar"]) != medians[f["data-year"]]]
    assert not wrong, f"An older spending figure is compared with a newer cohort: {wrong}"


def test_questions_preserve_the_trust_inclusive_reserve_key():
    # Arrange: the school owns 90k and has a further 310k share of the trust reserve.
    item, ctx = aar_academy(status="large_reserves", reserve=400000)
    item["status"]["trust_share_included"] = True
    latest = ctx["series"]["years"][-1]
    own_reserve = ctx["series"]["m"]["revenue_reserve"][latest]["v"]

    # Act
    body = school_page.render(item, ctx)["body"]
    questions = section(body, "questions")
    reserves = [f for f in figures(questions) if "reserve" in f["data-mf"]]

    # Assert: the same glossary key must never identify two different reserve bases.
    wrong = [f for f in figures(body, "revenue_reserve", latest)
             if float(f["data-v"]) != own_reserve]
    assert not wrong, f"Trust-inclusive money is labelled as the school's own reserve: {wrong}"
    assert any(f["data-mf"] == "revenue_reserve_incl_trust_share"
               and float(f["data-v"]) == 400000 for f in reserves)


@pytest.mark.parametrize("surface", ["status", "questions", "zero_donations", "trust_central"])
def test_suspect_figures_stay_marked_on_every_surface(surface):
    # Arrange: each value is explicitly flagged suspect by the SERIES contract.
    if surface == "trust_central":
        item, ctx = aar_academy()
        latest = ctx["series"]["years"][-1]
        ctx["series"]["flags"]["suspect"] = {latest: ["trust_central_spend_per_pupil"]}
        ident, metric = "trust-central", "trust_central_spend_pp"
    else:
        item, ctx = cfr_school(status="tight" if surface == "questions" else "healthy")
        latest = ctx["series"]["years"][-1]
        if surface == "zero_donations":
            metric = "donations_revenue"
            ctx["series"]["m"][metric][latest] = {"v": 0, "pp": 0, "r": 0, "rpp": 0}
            ident = "income"
        else:
            metric = "revenue_reserve"
            item["status"]["reserve"] = ctx["series"]["m"][metric][latest]["v"]
            ident = surface
        ctx["series"]["flags"]["suspect"] = {latest: [metric]}

    # Act
    rendered = section(school_page.render(item, ctx)["body"], ident)
    values = figures(rendered, metric, latest)

    # Assert: displaying the flagged value is allowed only with its suspect styling.
    assert values
    assert all("suspect" in f["class"].split() for f in values), values


@pytest.mark.parametrize("latest_value", [0, None])
def test_donation_history_survives_a_zero_or_missing_latest_return(latest_value):
    # Arrange: seven years of reported donations precede a zero or missing value.
    item, ctx = cfr_school()
    latest = ctx["series"]["years"][-1]
    donations = ctx["series"]["m"]["donations_revenue"]
    ctx["similar"]["donations_revenue"] = 55
    if latest_value is None:
        donations.pop(latest)
    else:
        donations[latest] = {"v": 0, "pp": 0, "r": 0, "rpp": 0}

    # Act
    income = section(school_page.render(item, ctx)["body"], "income")
    rows = re.findall(r"<tr\b[^>]*>.*?</tr>", income, re.S)
    row = next(r for r in rows if "Donations (day-to-day)" in r)

    # Assert: honest latest-year copy must not erase the known historical trend.
    assert '<svg' in row and 'role="img"' in row, row
    if latest_value == 0:
        assert "-100%" in row
        assert any(f.get("data-pp") == "0" for f in figures(row, "donations_revenue", latest))
    assert any(float(f["data-v"]) == 55 for f in figures(row, "per_pupil")), row


def test_missing_charity_history_does_not_assert_that_the_pta_ended():
    # Arrange: a registered charity has no downloaded historical return records.
    item, ctx = cfr_school(pta=[charity(
        name="Newly Registered PTA", registered="2026-03-01", history=[], latest_income=15000,
    )])

    # Act
    pta = unescape(section(school_page.render(item, ctx)["body"], "ptfa"))

    # Assert: missing history is not evidence of a historical/defunct association.
    assert "Newly Registered PTA" in pta
    assert "Had a registered PTA until" not in pta, pta


def test_fallback_other_dfe_grants_uses_the_2025_cfr_i06_line(monkeypatch):
    # Arrange: the committed gold return has I06 and no I18 in 2025-26.
    gold_path = Path(__file__).resolve().parents[1] / "pipeline/money/data/gold/130932.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    latest = "2025-26"
    entry = gold["years"][latest]
    expected = entry["lines"]["I06"]["value"]
    item, ctx = cfr_school(urn="130932", name=gold["name"])
    ctx["series"]["m"].pop("other_dfe_grants")
    item["rows"] = [{
        "year": latest, "source": "CFR", "period_months": 12,
        "cfr_additional_grants_i18": None,
        "lines": {k: v["value"] for k, v in entry["lines"].items()},
    }]
    monkeypatch.setattr(school_page, "_series", None)

    # Act
    body = school_page.render(item, ctx)["body"]
    grants = figures(section(body, "income"), "other_dfe_grants", latest)

    # Assert: the fallback must not describe a recorded 96,016 as unreported.
    assert any(float(f["data-v"]) == expected for f in grants), grants


def test_always_applicable_ifs_staff_context_survives_missing_school_staff_total():
    # Arrange: school totals are present, but the optional staff breakdown is missing.
    item, ctx = cfr_school()
    ctx["series"]["m"].pop("total_staff")
    staff_line = next(ln for ln in ctx["ifs"]["context_lines"]["school"] if ln["id"] == "staff_share")
    assert staff_line["use_when"] == "always"

    # Act
    body = unescape(school_page.render(item, ctx)["body"])

    # Assert: missing school data must not remove the independently known IFS fact.
    assert staff_line["text"] in body


def test_national_pta_context_is_shown_without_a_registered_school_pta():
    # Arrange: national context is available even though no association is matched.
    item, ctx = cfr_school(pta=[])
    ctx["pta_national"] = {"by_year": {"2024-25": {"median_pp": 31}}}

    # Act
    pta = section(school_page.render(item, ctx)["body"], "ptfa")
    national = figures(pta, "pta_per_pupil", "2024-25")

    # Assert
    assert any(float(f["data-v"]) == 31 for f in national), pta
