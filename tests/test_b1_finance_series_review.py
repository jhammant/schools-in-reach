"""Portable regressions for the finance-series independent review."""

import pytest

from pipeline.dfe import finance_history
from pipeline.dfe.test_finance_history import make_xlsx
from pipeline.money import series


def finance_row(year, source="CFR", **values):
    """A valid full-year return with enough fields for the public series API."""
    end = int(year[:4]) + 1
    row = {
        "urn": "100001",
        "year": year,
        "source": source,
        "period_end": f"{end}-{'08' if source == 'AAR' else '03'}",
        "period_months": 12,
        "did_not_supply": False,
        "pupils": 200,
        "total_income": 1_000_000,
        "total_expenditure": 950_000,
        "total_staff": 800_000,
        "revenue_reserve": 50_000,
    }
    row.update(values)
    return row


@pytest.mark.parametrize("source", ["CFR", "AAR"])
def test_distinct_pta_returns_in_same_school_year_are_summed(source):
    # Arrange: distinct returns around a change of year end, not duplicate
    # filings. Each return's period end falls within this school's 2023-24 year.
    school = finance_row("2023/24" if source == "AAR" else "2023-24", source)
    charities = [{
        "charity_number": 123456,
        "history": [
            {"period_end": "2023-09", "income": 5_000, "expenditure": 3_000},
            {"period_end": "2024-03", "income": 7_000, "expenditure": 4_000},
        ],
    }]

    # Act
    result = series.school_series([school], charities)["pta"]["2023-24"]

    # Assert: neither filed return disappears when both map to the same label.
    assert (result["income"], result["spend"]) == (12_000, 7_000)
    assert (result["income_pp"], result["spend_pp"]) == (60, 35)


@pytest.mark.parametrize("gap_kind", ["absent_year", "unknown_pupils", "missing_latest"])
def test_falling_rolls_does_not_treat_missing_years_as_consecutive_falls(gap_kind):
    # Arrange: none of these histories establishes the documented trigger.
    if gap_kind == "absent_year":
        rows = [finance_row(y, pupils=p) for y, p in (
            ("2020-21", 400), ("2021-22", 396),
            ("2023-24", 392), ("2024-25", 388),
        )]
    elif gap_kind == "unknown_pupils":
        rows = [finance_row(y, pupils=p) for y, p in (
            ("2020-21", 400), ("2021-22", 396), ("2022-23", None),
            ("2023-24", 392), ("2024-25", 388),
        )]
    else:
        rows = [finance_row(y, pupils=p) for y, p in (
            ("2020-21", 400), ("2021-22", 370), ("2024-25", None),
        )]

    # Act
    result = series.school_series(rows)

    # Assert: a sub-5% fall needs three consecutive, observed annual falls;
    # no current fall can be calculated when the latest pupil count is absent.
    assert result["flags"]["falling_rolls"] is None


def test_uncoded_aar_supply_lines_are_used(tmp_path):
    # Arrange: exports without a benchmarking code row are supported by
    # line_columns; these three detail lines are preserved as label slugs.
    header = [
        "URN", "LA", "Overall Phase", "Period covered by return", "No Pupils",
        "Total Income", "Total Expenditure", "Revenue Reserve",
        "Supply Staff Costs", "Supply teaching staff", "Agency supply teaching staff",
        "Supply teacher insurance",
    ]
    values = [140001, 204, "Primary", 12, 200, 1_000_000, 950_000, 50_000,
              1_000, 600, 300, 100]
    path = make_xlsx(tmp_path / "AAR_2024-25_download.xlsx", [("Academies", [header, values])])

    # Act
    rows, _ = finance_history.read_workbook(path)

    # Assert: all the operands are known even though their keys are slugs.
    assert (rows[0]["supply_staff"], rows[0]["supply_insurance"]) == (900, 100)


@pytest.mark.parametrize("admin, aggregate", [(0, None), ("SUPP", 7_000)])
def test_educational_supplies_uses_known_non_admin_lines(tmp_path, admin, aggregate):
    # Arrange: administration software is excluded from the requested total.
    # Every included line is known, even if the column is absent or E20D is suppressed.
    header = [
        "URN", "LA", "Overall Phase", "Period covered by return", "No Pupils",
        "Total Income", "Total Expenditure", "Revenue Reserve",
        "Educational Supplies: (E19:E21)",
        "E19 Learning resources (not ICT equipment)",
        "E20A Connectivity", "E20B Onsite servers", "E20C IT learning resources",
        "E20D Administration software and systems", "E20E Laptops, desktops and tablets",
        "E20F Other hardware", "E20G IT support", "E21 Exam fees",
    ]
    values = [100001, 204, "Primary", 12, 200, 1_000_000, 950_000, 50_000,
              aggregate, 5_000, 100, 0, 0, admin, 400, 0, 0, 500]
    path = make_xlsx(tmp_path / "CFR_2024-25_Full_Data_Workbook.xlsx", [("CFR Data", [header, values])])

    # Act
    rows, _ = finance_history.read_workbook(path)

    # Assert: E19 + all the non-admin E20 parts + E21 = 6,000 in both cases.
    assert rows[0]["educational_supplies"] == 6_000


def test_cfr_and_aar_with_same_display_year_do_not_mix_metric_sources():
    # Arrange: this occurs for academy conversions, including URN 148866 in
    # the real cache. Whichever return is selected must supply the whole year.
    cfr = finance_row("2022-23", pupils=100, pupil_premium=30_000, sen_funding=40_000)
    aar = finance_row("2022/23", "AAR", pupils=200, pupil_premium=None, sen_funding=None)

    # Act
    result = series.school_series([cfr, aar])

    # Assert: the year is represented once and contains only that source's values.
    selected = {"CFR": cfr, "AAR": aar}[result["source"]["2022-23"]]
    for metric in ("pupil_premium", "sen_funding"):
        if selected[metric] is None:
            assert "2022-23" not in result["m"].get(metric, {}), (
                "The academy year must not inherit CFR values (or divide them by academy pupils)."
            )
        else:
            assert result["m"][metric]["2022-23"]["pp"] == selected[metric] / selected["pupils"]
    assert result["years"] == ["2022-23"]
