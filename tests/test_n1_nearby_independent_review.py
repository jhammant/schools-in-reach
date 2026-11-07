"""Offline regression probes for N1's nearby figures and school-page fallbacks."""

from html import unescape
import re

import pytest

from pipeline.money import build_money, school_page
from pipeline.money.test_build_money import make_site, row, school
from pipeline.money.test_school_page import cfr_school, figures, nearby_school, section


def build_model(tmp_path, register, rows, pta):
    args = make_site(tmp_path, [("204", "Hackney")], {"204": register}, rows, pta)
    _, items, _ = build_money.build_model(*args)
    return {item["urn"]: item for item in items}


def charity(income, end="2025-03"):
    return [{"charity_number": 1_000_000 + income, "name": "Friends of the School", "status": "Registered",
             "match": {"method": "postcode", "confidence": "high"},
             "history": [{"period_end": end, "income": income}]}]


@pytest.mark.parametrize("suspect_urn", ["100001", "100003"])
def test_pta_omits_suspect_denominators_from_values_ranks_and_medians(tmp_path, suspect_urn):
    # Arrange: three PTA figures, one based on an explicitly suspect pupil roll.
    register = [school(100001 + n, f"Primary {n}", lat=51.56 + n * .001, lon=-.075)
                for n in range(3)]
    rows = [row(str(s["urn"]), "2025-03", 2_000_000, 1_900_000, 100_000,
                pupils=300, suspect=["pupils"] if str(s["urn"]) == suspect_urn else [])
            for s in register]
    pta = {str(s["urn"]): charity(30_000 + n * 30_000) for n, s in enumerate(register)}

    # Act
    nearby = build_model(tmp_path, register, rows, pta)["100001"]["nearby"]
    invalid = next(r for r in [nearby["self"]] + nearby["schools"] if r["urn"] == suspect_urn)

    # Assert: only two clean PTA values remain, below the median/rank threshold.
    assert "pta_pp" not in invalid, "PTA per pupil must not use a pupil roll flagged suspect"
    assert "pta_pp" not in nearby["medians"]
    assert "pta_pp" not in nearby["rank"]


def test_conversion_year_pta_uses_the_same_selected_return_as_other_figures(tmp_path):
    # Arrange: the linked predecessor and academy share a label; the later AAR
    # return supplies the whole year's figures, including its 300 pupils.
    register = [school(140001, "Converted Primary", type="Academy converter", lat=51.56, lon=-.075),
                school(100002, "Neighbour Two", lat=51.561, lon=-.075),
                school(100003, "Neighbour Three", lat=51.562, lon=-.075)]
    rows = [row("100099", "2025-03", 1_000_000, 950_000, 50_000, pupils=100),
            row("140001", "2025-08", 2_000_000, 1_900_000, 100_000, pupils=300, source="AAR"),
            row("100002", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=300),
            row("100003", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=300)]
    pta = {"140001": charity(30_000, "2025-08"), "100002": charity(60_000), "100003": charity(75_000)}
    args = make_site(tmp_path, [("204", "Hackney")], {"204": register}, rows, pta)
    args[2].write_text("URN,LinkURN,LinkType\n140001,100099,Predecessor\n", encoding="utf-8")

    # Act
    _, items, _ = build_money.build_model(*args)
    nearby = next(i for i in items if i["urn"] == "140001")["nearby"]

    # Assert: using the predecessor's 100 pupils triples PTA pp and reverses rank.
    assert nearby["year"] == nearby["self"]["pta_year"] == "2024-25"
    assert nearby["self"]["pupils"] == 300
    assert nearby["self"]["pta_pp"] == 100
    assert nearby["rank"]["pta_pp"] == {"rank": 3, "of": 3}
    assert nearby["medians"]["pta_pp"] == 200


def test_nearby_academy_reserve_preserves_the_trust_inclusive_glossary_key(tmp_path):
    # Arrange: the academy has 90k of its own and 300k in its trust share.
    register = [school(100001, "Home Primary", lat=51.56, lon=-.075),
                school(140002, "Nearby Academy", type="Academy converter", lat=51.561, lon=-.075)]
    rows = [row("100001", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=300),
            row("140002", "2025-08", 2_000_000, 1_900_000, 90_000, pupils=300,
                source="AAR", revenue_reserve_incl_trust_share=390_000)]
    nearby = build_model(tmp_path, register, rows, {})["100001"]["nearby"]
    item, ctx = cfr_school()
    ctx["nearby"] = nearby

    # Act
    markup = section(school_page.render(item, ctx)["body"], "nearby")
    academy_row = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", markup, re.S)
                       if "Nearby Academy" in r)
    reserves = [f for f in figures(academy_row) if "reserve" in f["data-mf"]]

    # Assert: its tooltip must explain trust-inclusive money, not own reserves.
    assert reserves
    assert float(reserves[0]["data-pp"]) == 1_300
    assert reserves[0]["data-mf"] == "revenue_reserve_incl_trust_share"


def test_lighter_sections_keep_disclosures_for_the_ranks_they_retain():
    # Arrange: a mixed CFR/AAR cohort with a medium-confidence PTA in the rank.
    item, ctx = nearby_school()

    # Act: use the same renderer bodies consumed by school_page_html's fallback.
    result = school_page.render(item, ctx)
    bodies = [result["body"]] + result.get("lighter", [])

    # Assert: a smaller table must not turn qualified figures into unqualified ranks.
    # Omitting a comparison entirely is also an acceptable final size fallback.
    for body in bodies:
        nearby = unescape(section(body, "nearby") or "")
        if not nearby:
            continue
        if "association income per pupil" in nearby:
            assert "matched with lower confidence" in nearby
        assert "April to March" in nearby and "September to August" in nearby
        assert "doubtful" in nearby or "suspect" in nearby


def test_nearby_per_pupil_columns_show_per_pupil_as_the_primary_figure():
    # Arrange
    item, ctx = nearby_school()

    # Act
    markup = section(school_page.render(item, ctx)["body"], "nearby")
    self_row = re.search(r'<tr class="nb-self">(.*?)</tr>', markup, re.S).group(1)
    spending = re.search(r'<span\b[^>]*data-mf="total_expenditure"[^>]*>(.*?)</span>', self_row, re.S).group(1)
    main_text = unescape(re.sub(r"<small\b[^>]*>.*?</small>", "", spending, flags=re.S)).strip()

    # Assert: the heading says spending per pupil, so the main value is 7,000,
    # with the total accompanying it, as required by the shared contract.
    assert "£7,000" in main_text, f"Spending per pupil currently headlines a total: {main_text}"
