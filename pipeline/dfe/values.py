"""Value parsing and section assembly helpers shared by the DfE builders."""

from __future__ import annotations

import csv
import re
from pathlib import Path

# Codes DfE uses instead of numbers (performance tables and EES).
SUPPRESSION_CODES = {
    "SUPP", "NE", "NA", "LOWCOV", "NP", "NEW", "SP", "RE", "DNS", "NR",
    "x", "c", "z", "u", "low", "LOW", ":", "~", "..", "n/a", "n/s", "NULL",
}

_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def parse(raw) -> tuple[float | int | None, str | None]:
    """Return (number or None, suppression code or None)."""
    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return None, None
    if isinstance(raw, (int, float)):
        return raw, None
    text = str(raw).strip()
    if text == "":
        return None, None
    if text in SUPPRESSION_CODES or text.upper() in SUPPRESSION_CODES:
        return None, text
    cleaned = text.replace(",", "").replace("£", "")
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    if _NUMBER.match(cleaned):
        value = float(cleaned)
        return (int(value) if value.is_integer() and "." not in cleaned else value), None
    return None, text  # unexpected token, treat as not available


def _round(value, digits: int | None):
    if value is None or digits is None:
        return value
    return int(round(value)) if digits == 0 else round(value, digits)


def num(raw, digits: int | None = None):
    value, _ = parse(raw)
    return _round(value, digits)


def text(raw) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if value == "" or value in SUPPRESSION_CODES:
        return None
    return value


def pct(part, whole, digits: int = 1):
    if part is None or whole in (None, 0):
        return None
    return round(100.0 * part / whole, digits)


def per(total, count, digits: int = 0):
    if total is None or count in (None, 0):
        return None
    value = total / count
    return int(round(value)) if digits == 0 else round(value, digits)


# Per-school files only carry labels for measures whose meaning is not obvious
# from the key; benchmarks.json carries the full label maps for every section.
CRYPTIC_KEYS = {
    # KS2
    "rwm_expected_pct", "rwm_higher_pct", "gps_expected_pct", "gps_scaled_score",
    "reading_scaled_score", "maths_scaled_score", "writing_greater_depth_pct",
    "rwm_expected_3yr_pct", "disadvantaged_pct", "latest_progress",
    # KS4
    "attainment8", "progress8", "progress8_ci_lower", "progress8_ci_upper",
    "eng_maths_5plus_pct", "eng_maths_4plus_pct", "ebacc_entry_pct", "ebacc_aps",
    "ebacc_5plus_pct", "latest_progress8",
    # KS5
    "alevel_aps", "best3_aps", "aab_2facilitating_pct", "alevel_value_added",
    "alevel_progress_band", "applied_general_aps", "tech_level_aps",
    "english_progress", "maths_progress", "alevel_retention_pct",
    # census / absence
    "fsm_pct", "fsm_ever6_pct", "eal_pct", "sen_support_pct", "ehcp_pct",
    "overall_absence_pct", "persistent_absence_pct",
    # finance
    "source", "in_year_balance", "revenue_reserve", "revenue_reserve_incl_trust_share",
    "supply_staff", "education_support_staff", "other_staff_costs", "premises",
    "occupation", "educational_supplies", "supplies_services", "bought_in_services",
    "self_generated", "federated_return",
    # workforce
    "pupil_teacher_ratio", "pupil_adult_ratio", "teachers_without_qts_fte",
    "other_support_staff_fte", "turnover_pct", "left_state_sector_pct",
    "days_per_teacher", "days_per_absent_teacher",
    # destinations
    "sustained_pct", "not_sustained_pct", "unknown_pct", "other_education_pct",
    "degree_level_pct", "top_third_hei_pct", "higher_technical_pct", "progressed_pct",
}


class Section:
    """Collects one section's fields, noting which came from suppression codes."""

    def __init__(self, **header):
        self.data: dict = {k: v for k, v in header.items() if v is not None}
        self.suppressed: list[str] = []

    def num(self, key: str, raw, digits: int | None = None, not_published: bool = False):
        value, code = parse(raw)
        value = _round(value, digits)
        self.data[key] = value
        if code and not not_published:
            self.suppressed.append(key)
        return value

    def text(self, key: str, raw, not_published: bool = False):
        value = text(raw)
        self.data[key] = value
        if not not_published and value is None and raw not in (None, "") and str(raw).strip() in SUPPRESSION_CODES:
            self.suppressed.append(key)
        return value

    def set(self, key: str, value):
        self.data[key] = value

    def has_values(self, keys) -> bool:
        return any(self.data.get(k) is not None for k in keys)

    def out(self, labels: dict | None = None) -> dict:
        result = dict(self.data)
        if labels:
            present = set(result)
            for value in result.values():
                if isinstance(value, dict):
                    present.update(value)
            result["labels"] = {k: v for k, v in labels.items() if k in present and k in CRYPTIC_KEYS}
        if self.suppressed:
            result["_suppressed"] = sorted(set(self.suppressed))
        return result


def read_csv(path: Path, encoding: str = "utf-8-sig") -> list[dict]:
    """Read a CSV with upper-cased header names (DfE casing is inconsistent)."""
    with open(path, encoding=encoding, errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = [h.strip().upper() for h in next(reader)]
        return [dict(zip(header, row)) for row in reader]


def year_label(code: str) -> str:
    """'2024-2025' or '202425' -> '2024/25'."""
    digits = re.sub(r"\D", "", code)
    if len(digits) == 8:
        return f"{digits[:4]}/{digits[6:]}"
    if len(digits) == 6:
        return f"{digits[:4]}/{digits[4:]}"
    return code


def prev_year(label: str, n: int = 1) -> str:
    start = int(label[:4]) - n
    return f"{start}/{str(start + 1)[2:]}"
