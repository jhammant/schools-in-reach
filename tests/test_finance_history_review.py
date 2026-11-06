"""Portable regression repros for the finance-history independent review."""

from datetime import date

from pipeline.dfe import finance_history as fh
from pipeline.dfe.test_finance_history import make_xlsx
from pipeline.money.build_money import reserve_of


def test_distributed_whole_trust_reserve_is_not_added_to_school_reserve(tmp_path):
    # Arrange: the 2021-22 through 2023-24 allocation includes academy reserves.
    # A single-academy trust with no central reserve has exactly this school's
    # reserve available, not twice that amount.
    header = [
        "URN", "LA", "Overall Phase", "Period covered by return", "No Pupils",
        "Total Income", "Total Expenditure", "Revenue Reserve",
        "Share of Revenue Reserve, distributed on per pupil basis", "MAT/SAT",
    ]
    codes = [None] * 8 + [
        "(CS RR+ Sum of Acad RR / total pupils in Trust * Pupils in Acad)"
    ]
    data = [
        140001, 204, "Primary", 12, 300, 2000000, 1950000, 150000,
        150000, "Single Academy Trust (SAT)",
    ]
    path = make_xlsx(
        tmp_path / "AAR_2023-24_download.xlsx",
        [("Academies", [codes, header, data])],
    )

    # Act: use the public reader and the actual downstream reserve selector.
    rows, _ = fh.read_workbook(path)

    # Assert: retaining an absent combined value or using the existing total
    # allocation is safe here; adding the school reserve a second time is not.
    assert reserve_of(rows[0]) == 150000


def test_latest_trust_is_selected_with_mixed_excel_and_text_join_dates(tmp_path):
    # Arrange: Excel exports can contain both serial-number and textual dates.
    header = [
        "URN", "LA", "Overall Phase", "Period covered by return", "No Pupils",
        "Total Income", "Total Expenditure", "Revenue Reserve",
        "Trust or Company Name", "Date joined or opened if in period",
    ]
    new_joined = (date(2024, 3, 1) - date(1899, 12, 30)).days
    earlier = [140001, 204, "Primary", 6, 300, 1000000, 950000, 100000,
               "Old Trust", "01/09/2023"]
    later = [140001, 204, "Primary", 6, 310, 1100000, 1000000, 150000,
             "New Trust", new_joined]
    path = make_xlsx(
        tmp_path / "AAR_2023-24_download.xlsx",
        [("Academies", [header, earlier, later])],
    )

    # Act
    rows, _ = fh.read_workbook(path)

    # Assert
    assert len(rows) == 1
    assert rows[0]["total_income"] == 2100000
    assert rows[0]["trust"] == "New Trust"
    assert rows[0]["pupils"] == 310


def test_code_row_can_resolve_a_trailing_blank_descriptive_cell(tmp_path):
    # Arrange: xlsx.iter_rows omits unpopulated trailing cells, so this header
    # is shorter than the code row even though BAB030 identifies the reserve.
    header = [
        "URN", "LA", "Overall Phase", "Period covered by return", "No Pupils",
        "Total Income", "Total Expenditure", None,
    ]
    codes = [None] * 7 + ["BAB030"]
    data = [140001, 204, "Primary", 12, 300, 2000000, 1950000, 150000]
    path = make_xlsx(
        tmp_path / "AAR_2023-24_download.xlsx",
        [("Academies", [codes, header, data])],
    )

    # Act
    rows, info = fh.read_workbook(path)

    # Assert
    assert rows[0]["revenue_reserve"] == 150000
    assert "BAB030" in info["mapping"]["revenue_reserve"]
