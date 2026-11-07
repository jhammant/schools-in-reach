"""Regression for a user-visible explanation that contradicts the real classifier."""
import json
from pathlib import Path

from pipeline.money import status


def test_heading_explanation_does_not_require_three_deficit_years():
    # Arrange: two full years of overspending, with a two-year runway.
    rows = [
        {
            "year": year,
            "period_end": end,
            "period_months": 12,
            "source": "CFR",
            "phase": "primary",
            "total_income": 1_000_000,
            "in_year_balance": -20_000,
            "revenue_reserve": reserve,
        }
        for year, end, reserve in (
            ("2023-24", "2024-03", 60_000),
            ("2024-25", "2025-03", 40_000),
        )
    ]
    glossary = json.loads(
        (Path(__file__).resolve().parents[1] / "pipeline/money/assets/glossary.json").read_text()
    )

    # Act: use the production classifier, whose rule the glossary explains.
    assessment = status.assess(rows)
    explanation = glossary["status_heading_for_deficit"]["how"]

    # Assert: this school is flagged after two years, not three.
    assert assessment["status"] == "heading_for_deficit"
    assert assessment["deficit_streak"] == 2
    assert assessment["runway_years"] == 2.0
    assert "each of the last three years" not in explanation.lower(), (
        "The UI says three consecutive overspending years are required, but the "
        f"classifier flags this school after two: {explanation}"
    )
