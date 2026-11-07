"""A school's financial status year by year.

status.assess() judges a school on its latest full year. To draw a timeline we re-run
that judgement as of each full year in turn, using only the rows whose period had
ended by then, so the status for 2021-22 is what the page would have said in 2022.
Reserve per pupil divides by that same year's pupils, never a later count.
"""

from __future__ import annotations

from pipeline.money import status as health


def year_label(row: dict) -> str:
    """"2019-20" for both CFR ("2019-20") and AAR ("2019/20") rows."""
    return str(row["year"]).replace("/", "-")


def status_by_year(rows: list[dict]) -> list[dict]:
    """One entry per full year, oldest first:
    {"year", "status", "label", "reserve", "reserve_pp", "pupils"}."""
    out = []
    for year in health.full_years(rows):
        upto = [r for r in rows if r.get("period_end") and r["period_end"] <= year["period_end"]]
        verdict = health.assess(upto)
        if not verdict:
            continue
        pupils = year.get("pupils") or None
        reserve = verdict["reserve"]
        out.append({
            "year": year_label(year),
            "status": verdict["status"],
            "label": verdict["label"],
            "reserve": reserve,
            "reserve_pp": reserve / pupils if pupils and reserve is not None else None,
            "pupils": pupils,
        })
    return out
