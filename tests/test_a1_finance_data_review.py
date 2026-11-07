"""Portable regression cases for the A1 finance-data independent review."""

import pytest

from pipeline.dfe import finance_history as fh
from pipeline.dfe.test_finance_history import make_xlsx


def _aar(tmp_path, extra_headers, extra_values):
    header = [
        "URN", "LA", "Overall Phase", "Period covered by return", "No Pupils",
        "Total Income", "Total Expenditure", "Revenue Reserve",
    ]
    values = [140001, 204, "Primary", 12, 300, 1_000_000, 900_000, 100_000]
    return make_xlsx(
        tmp_path / "AAR_2024-25_download.xlsx",
        [("Academies", [header + extra_headers, values + extra_values])],
    )


def test_aar_uncoded_detail_uses_label_slug(tmp_path):
    # Arrange: detail labels are present, but this export has no code row.
    path = _aar(
        tmp_path,
        ["Teaching staff", "Income from catering", "Educational Consultancy"],
        [600_000, 25_000, 12_000],
    )

    # Act: exercise the real XLSX reader and canonical-row construction.
    rows, _ = fh.read_workbook(path)

    # Assert: uncoded detail must survive under the specified label slugs.
    assert rows[0]["lines"] == {
        "teaching_staff": 600_000,
        "income_from_catering": 25_000,
        "educational_consultancy": 12_000,
    }


@pytest.mark.parametrize(
    ("extra_headers", "extra_values", "derived_key"),
    [
        (
            ["Total Grant Funding", "Non-Government", "Academies"],
            [800_000, "SUPP", 20_000],
            "grant_funding_government",
        ),
        (
            ["Total Grant Funding", "Non-Government", "Academies"],
            [800_000, 30_000, "SUPP"],
            "grant_funding_government",
        ),
        (
            ["Income from rentals and lettings", "Income from facilities and services - other"],
            [5_000, "SUPP"],
            "facilities_income",
        ),
    ],
    ids=["non_government_suppressed", "academy_income_suppressed", "facilities_suppressed"],
)
def test_suppressed_inputs_do_not_become_zero_in_income_derivations(
    tmp_path, extra_headers, extra_values, derived_key,
):
    # Arrange: SUPP is an unavailable value, not a reported zero (values.num).
    path = _aar(tmp_path, extra_headers, extra_values)

    # Act
    rows, _ = fh.read_workbook(path)

    # Assert: neither a sum nor a subtraction is known with a suppressed operand.
    assert rows[0][derived_key] is None


def test_cfr_label_fallback_covers_requested_codes():
    # Arrange: these are all the code ranges explicitly required by the brief.
    codes = [f"I{i:02d}" for i in range(1, 19)]
    codes += [f"I18{suffix}" for suffix in "abcd"]
    codes += [f"E{i:02d}" for i in range(1, 33)]
    codes += [f"B{i:02d}" for i in range(1, 8)]
    codes += [f"OB{i:02d}" for i in range(1, 4)]

    # Act: public labels must be usable without first reading source workbooks.
    missing = [code for code in codes if not fh.LINE_LABELS.get(code)]

    # Assert
    assert not missing, f"Missing public CFR fallback labels: {missing}"
