"""Financial health of one school from its yearly finance rows (see pipeline/dfe/finance_history.py).

Five plain labels, worst first, each with a one-line reason a parent can read:
in_deficit, heading_for_deficit, tight, healthy, large_reserves. A sixth, reserve_held_by_trust,
comes last and is not a judgement: an academy in a multi-academy trust whose own reserve is
exactly £0 and which has no trust-share figure that year, because the trust holds reserves
centrally. It is never read as tight and never counted as a deficit.

One reserve basis per school (reserve_basis): an academy whose latest full year publishes the
reserve including its share of the trust's reserve is judged on that figure ('incl_trust_share');
every other school on its own reserve ('own'). assess(rows, basis=...) judges on a given basis;
a year that lacks it is judged on the academy's own figure, and the result's reserve_basis says so.

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

ORDER = ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves", "reserve_held_by_trust"]
LABELS = {
    "in_deficit": "In deficit",
    "heading_for_deficit": "Heading for deficit",
    "tight": "Tight",
    "healthy": "Healthy",
    "large_reserves": "Large reserves",
    "reserve_held_by_trust": "Reserve held by the trust",
}
# Icons beside every label, so colour is never the only key (charts.STATUS_ICONS and the JS mirrors match).
ICONS = {"in_deficit": "▼", "heading_for_deficit": "↘", "tight": "●", "healthy": "✓", "large_reserves": "▲",
         "reserve_held_by_trust": "◇"}
HELD_BY_TRUST = "reserve_held_by_trust"
HELD_BY_TRUST_REASON = ("Its trust holds reserves centrally, so this academy's own balance is £0; "
                        "the trust's page shows the trust's reserves.")
OWN, INCL_TRUST = "own", "incl_trust_share"
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


def reserve_basis(rows: list[dict]) -> str:
    """'incl_trust_share' when the latest full year carries the reserve including the trust's share, else 'own'.
    Council-run schools are always 'own'."""
    years = full_years(rows)
    if years and years[-1].get("revenue_reserve_incl_trust_share") is not None:
        return INCL_TRUST
    return OWN


def reserve_on_basis(row: dict, basis: str):
    """The row's reserve on one basis, or None when the row doesn't publish it."""
    return row.get("revenue_reserve_incl_trust_share" if basis == INCL_TRUST else "revenue_reserve")


def pooled_own_reserve(row: dict) -> bool:
    """True for an academy in a multi-academy trust whose own reserve is exactly £0: the trust holds it centrally."""
    trust_type = str(row.get("trust_type") or "").strip().lower()
    in_mat = "multi" in trust_type or trust_type == "mat"
    return row.get("source") == "AAR" and in_mat and row.get("revenue_reserve") == 0


def held_by_trust(row: dict) -> bool:
    """True for an academy in a multi-academy trust whose own reserve is exactly £0 and which has no
    trust-share figure that year: the trust holds reserves centrally (pools them), so nothing can be judged."""
    return pooled_own_reserve(row) and row.get("revenue_reserve_incl_trust_share") is None


def reserve_share(row: dict, basis: str | None = None) -> float | None:
    """Reserve as a share of the year's income. Without a basis, academies use the figure including
    their share of the trust's central reserve when the DfE publishes it."""
    reserve = reserve_on_basis(row, basis) if basis else row.get("revenue_reserve_incl_trust_share")
    if reserve is None and basis != INCL_TRUST:
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


def assess(rows: list[dict], basis: str | None = None) -> dict | None:
    """Status for one school. Returns None when there is no usable full-year return. basis defaults to
    reserve_basis(rows); a latest year without a figure on the given basis is judged on its own reserve."""
    years = full_years(rows)
    if not years:
        return None
    latest = years[-1]
    basis = basis or reserve_basis(rows)
    if reserve_on_basis(latest, basis) is None:
        basis = OWN
    reserve = reserve_on_basis(latest, basis)
    share = reserve_share(latest, basis)
    trust_share = basis == INCL_TRUST
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

    held = " including its share of the trust's reserve" if trust_share else ""
    if basis == OWN and held_by_trust(latest):
        status = HELD_BY_TRUST
        reason = HELD_BY_TRUST_REASON
    elif reserve < 0:
        status = "in_deficit"
        if trust_share:  # the academy's own accounts may be in surplus: the trust's share takes it below zero
            reason = f"In deficit by {_money(-reserve)}, {abs(share):.0%} of a year's income, counting its share of the trust's reserve."
        else:
            reason = f"In deficit by {_money(-reserve)}, {abs(share):.0%} of a year's income: it has spent more over the years than it received."
        if streak >= 2:
            reason += f" It has spent more than it received for {streak} years running."
    elif streak >= 2 and runway is not None and runway <= RUNWAY_YEARS:
        status = "heading_for_deficit"
        reason = (f"Has spent more than it received for {streak} years running; at that rate "
                  f"its {_money(reserve)} reserve{held} runs out in about {max(runway, 0.5):.0f} year{'s' if runway >= 1.5 else ''}.")
    elif share < TIGHT_BELOW:
        status = "tight"
        reason = f"Holds {_money(reserve)} in reserve{held}, under 3% of a year's income: little room for surprises."
    elif share >= large_from:
        status = "large_reserves"
        reason = f"Holds {_money(reserve)} in reserve{held}, {share:.0%} of a year's income."
        if streak >= 2:
            reason += f" It has been drawing on it for {streak} years."
    else:
        status = "healthy"
        reason = f"Holds {_money(reserve)} in reserve{held}, {share:.0%} of a year's income."
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
        "trust_share_included": trust_share,
        "reserve_basis": basis,
    }
