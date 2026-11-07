"""GDP deflator for showing school money in today's prices.

Source: HM Treasury, "GDP deflators at market prices, and money GDP", October
2026 (Budget) edition, published 29 October 2026 (outturn to 2025-26 from the
ONS Quarterly National Accounts of 30 September 2026, forecasts from the OBR
Economic and Fiscal Outlook of 28 October 2026). Open Government Licence v3.0.
The index is stored in pipeline/money/data/gdp_deflator.json, rebased so
BASE_YEAR = 100.

CFR rows (council-run schools, April-March) use the financial-year index; AAR
rows (academies, September-August) use the academic-year index, which is the
pupil-weighted blend of the two financial years each academic year straddles.

Stdlib only.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "gdp_deflator.json"
BASE_YEAR = "2025-26"
SOURCE_LABEL = "HM Treasury GDP deflator, October 2026"


@lru_cache(maxsize=1)
def load() -> dict:
    """The deflator file: source, base_year, financial_years {"2019-20": 78.3}, academic_years {"2019/20": 80.0}."""
    with open(DATA, encoding="utf-8") as fh:
        return json.load(fh)


def _financial_spelling(year_label: str) -> str:
    return str(year_label).strip().replace("/", "-")


def _academic_spelling(year_label: str) -> str:
    return str(year_label).strip().replace("-", "/")


def index(year_label: str, source: str = "CFR") -> float:
    """Deflator index (BASE_YEAR = 100) for a year, in either '2019-20' or '2019/20' spelling.

    source "CFR" (or anything but "AAR") reads the financial-year table; "AAR" the academic-year table.
    Raises KeyError when the year is outside the file.
    """
    data = load()
    if str(source).upper() == "AAR":
        table, key = data["academic_years"], _academic_spelling(year_label)
    else:
        table, key = data["financial_years"], _financial_spelling(year_label)
    if key not in table:
        raise KeyError(f"no {source} deflator for {year_label!r}")
    return float(table[key])


def to_real(value, year_label: str, source: str = "CFR"):
    """A cash figure from `year_label` restated in BASE_YEAR prices (None in, None out)."""
    if value is None:
        return None
    return value * 100.0 / index(year_label, source)


def real_label() -> str:
    """Caption for figures produced by to_real()."""
    return f"in {BASE_YEAR} prices ({SOURCE_LABEL})"
