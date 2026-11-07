"""A school's financial status year by year.

status.assess() judges a school on its latest full year. To draw a timeline we re-run
that judgement as of each full year in turn, using only the rows whose period had
ended by then, so the status for 2021-22 is what the page would have said in 2022.
Reserve per pupil divides by that same year's pupils, never a later count, and is left
out when series.suspect_pupils (or the row) flags that year's pupils.

Every year is judged on the page's one reserve basis (status.reserve_basis of all the
rows). An academy year that doesn't publish the trust-inclusive figure is judged on its
own reserve and its point says basis 'own', so a reader can label it rather than mix the
two; a pooled £0 own reserve reads 'reserve_held_by_trust', never 'tight'.
"""

from __future__ import annotations

from pipeline.money import status as health

try:
    from pipeline.money import series as _series
except ImportError:  # pragma: no cover - series.py ships beside this module
    _series = None


def year_label(row: dict) -> str:
    """"2019-20" for both CFR ("2019-20") and AAR ("2019/20") rows."""
    return str(row["year"]).replace("/", "-")


def status_by_year(rows: list[dict], basis: str | None = None) -> list[dict]:
    """One entry per full year, oldest first:
    {"year", "status", "label", "reserve", "reserve_pp", "pupils", "basis"}."""
    basis = basis or health.reserve_basis(rows)
    odd = _series.suspect_pupils(rows) if _series is not None else {}
    out = []
    for year in health.full_years(rows):
        upto = [r for r in rows if r.get("period_end") and r["period_end"] <= year["period_end"]]
        verdict = health.assess(upto, basis=basis)
        if not verdict:
            continue
        pupils = year.get("pupils") or None
        doubtful = year["period_end"] in odd or "pupils" in (year.get("suspect") or [])
        reserve = verdict["reserve"]
        out.append({
            "year": year_label(year),
            "status": verdict["status"],
            "label": verdict["label"],
            "reserve": reserve,
            "reserve_pp": reserve / pupils if pupils and reserve is not None and not doubtful else None,
            "pupils": pupils,
            "basis": verdict.get("reserve_basis", basis),
        })
    return out
