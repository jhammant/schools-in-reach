"""Financial health of one school from its yearly finance rows (see pipeline/dfe/finance_history.py).

Five plain labels, worst first, each with a one-line reason a parent can read:
in_deficit, heading_for_deficit, tight, healthy, large_reserves.

Thresholds follow DfE and council practice: reserves are judged as a share of a
year's income, the DfE's old "excessive balance" limits were 8% (primary/special)
and 5% (secondary), and many councils' schemes for financing schools claw back
surpluses above those levels. A school is "heading for deficit" when it has spent
more than it received for at least two years running and, at its recent rate, its
reserve would run out within about three years.

Boundaries: "tight" is a reserve share strictly below 3% (exactly 3% is healthy);
"large_reserves" is 8% (5% secondary) or more, so exactly 8% counts; "heading for
deficit" needs a runway of 3.0 years or less, so exactly three years counts.
"""

from __future__ import annotations

ORDER = ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves"]
LABELS = {
    "in_deficit": "In deficit",
    "heading_for_deficit": "Heading for deficit",
    "tight": "Tight",
    "healthy": "Healthy",
    "large_reserves": "Large reserves",
}
TIGHT_BELOW = 0.03          # reserve under 3% of a year's income
LARGE_FROM = {"secondary": 0.05, "default": 0.08}
RUNWAY_YEARS = 3.0


def _money(value) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sign}£{value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"{sign}£{value / 1_000:.0f}k"
    return f"{sign}£{value:.0f}"


def full_years(rows: list[dict]) -> list[dict]:
    """Full-year returns with the figures we need, oldest first, one per year. The page
    builder uses the same list, so the year a page reports is the year that was assessed."""
    usable = [r for r in rows if not r.get("did_not_supply")
              and r.get("period_months") == 12
              and r.get("total_income") and r.get("revenue_reserve") is not None]
    by_end = {r["period_end"]: r for r in usable}
    return [by_end[k] for k in sorted(by_end)]


def reserve_share(row: dict) -> float | None:
    """Reserve as a share of the year's income. Academies use the figure including
    their share of the trust's central reserve when the DfE publishes it."""
    reserve = row.get("revenue_reserve_incl_trust_share")
    if reserve is None:
        reserve = row.get("revenue_reserve")
    income = row.get("total_income")
    if reserve is None or not income:
        return None
    return reserve / income


def deficit_streak(years: list[dict]) -> int:
    streak = 0
    for row in reversed(years):
        if (row.get("in_year_balance") or 0) < 0:
            streak += 1
        else:
            break
    return streak


def assess(rows: list[dict]) -> dict | None:
    """Status for one school. Returns None when there is no usable full-year return."""
    years = full_years(rows)
    if not years:
        return None
    latest = years[-1]
    share = reserve_share(latest)
    reserve = latest.get("revenue_reserve_incl_trust_share")
    if reserve is None:
        reserve = latest["revenue_reserve"]
    streak = deficit_streak(years)
    phase = latest.get("phase") or "default"
    large_from = LARGE_FROM.get(phase, LARGE_FROM["default"])
    pupils_change = None
    first_with_pupils = next((r for r in years if r.get("pupils")), None)
    if first_with_pupils and latest.get("pupils") and first_with_pupils is not latest:
        pupils_change = latest["pupils"] / first_with_pupils["pupils"] - 1

    recent = years[-3:]
    avg_overspend = -sum(r.get("in_year_balance") or 0 for r in recent) / len(recent)
    runway = reserve / avg_overspend if reserve > 0 and avg_overspend > 0 else None

    if reserve < 0:
        status = "in_deficit"
        reason = f"In deficit by {_money(-reserve)}, {abs(share):.0%} of a year's income: it has spent more over the years than it received."
        if streak >= 2:
            reason += f" It has spent more than it received for {streak} years running."
    elif streak >= 2 and runway is not None and runway <= RUNWAY_YEARS:
        status = "heading_for_deficit"
        reason = (f"Has spent more than it received for {streak} years running; at that rate "
                  f"its {_money(reserve)} reserve runs out in about {max(runway, 0.5):.0f} year{'s' if runway >= 1.5 else ''}.")
    elif share < TIGHT_BELOW:
        status = "tight"
        reason = f"Holds {_money(reserve)} in reserve, under 3% of a year's income: little room for surprises."
    elif share >= large_from:
        status = "large_reserves"
        reason = f"Holds {_money(reserve)} in reserve, {share:.0%} of a year's income."
        if streak >= 2:
            reason += f" It has been drawing on it for {streak} years."
    else:
        status = "healthy"
        reason = f"Holds {_money(reserve)} in reserve, {share:.0%} of a year's income."
        if streak >= 2:
            reason += f" It has spent more than it received for {streak} years, so watch the trend."
    return {
        "status": status,
        "label": LABELS[status],
        "rank": ORDER.index(status),
        "reason": reason,
        "year": latest["year"],
        "source": latest["source"],
        "reserve": reserve,
        "reserve_share": share,
        "deficit_streak": streak,
        "runway_years": runway,
        "pupils_change": pupils_change,
        "years": len(years),
        "trust_share_included": latest.get("revenue_reserve_incl_trust_share") is not None,
    }
