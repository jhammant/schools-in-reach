"""A school's money year by year: the SERIES dict behind /data/sx/<urn>.json.

school_series(rows, pta) turns one school's finance_history rows (see
pipeline/dfe/finance_history.py) into cash, per pupil, real and real per pupil
figures for every full year, the parents' association's money in the same school
years, and a few site flags (falling rolls, pass-through grants, high SEND).

Rules the pages rely on:
- Per pupil always divides by the SAME year's pupils from the same return.
- Real terms come only from deflator.to_real: CFR years (April to March) use the
  financial-year index and AAR years (September to August) the academic-year index.
- Missing values are left out, never written as 0. Values the source marks as
  suspect stay in, and are listed in flags['suspect'] so charts can draw them hollow.
- A charity return goes in the school year that contains its period end
  (pta_year), split equally between the schools it is shared with. Every
  distinct return counts, so two returns ending in one school year are summed.
- A conversion year can have a council (CFR) and an academy (AAR) return with
  the same label; the one ending later supplies that whole year.

The flags follow the site's own rules, not the IFS's. Stdlib only.
"""

from __future__ import annotations

import math

from pipeline.money import deflator, status

# (key, glossary key, group), in display order. The glossary key is always the row key.
METRICS = [(key, key, "income") for key in (
    "total_income", "grant_funding_government", "sen_funding", "pupil_premium", "self_generated_income",
    "donations_revenue", "donations_capital", "facilities_income", "catering_income", "other_dfe_grants")]
METRICS += [(key, key, "spend") for key in (
    "total_expenditure", "teaching_staff", "supply_staff", "education_support_staff", "admin_clerical_staff",
    "premises_staff", "catering_staff", "other_staff_costs", "total_staff", "premises", "energy", "occupation",
    "catering", "educational_supplies", "supplies_services", "bought_in_services")]
METRICS += [(key, key, "balance") for key in ("revenue_reserve", "in_year_balance")]

BASES = ("v", "pp", "r", "rpp")
# Older rows carry these under their first names (finance_history.COPY_KEYS).
ALIASES = {"self_generated_income": "self_generated", "total_staff": "total_staff_costs",
           "teaching_staff": "teaching_staff_costs", "education_support_staff": "education_support_staff_costs"}
# Lines academies' accounts returns do not break out, with the words pages must use.
NOT_IN_AAR = {"pupil_premium": "not reported in academy accounts",
              "donations_capital": "not reported in academy accounts"}
CONFIDENCE_ORDER = ["medium", "high"]  # lowest first

# Site rules (not IFS rules); see pipeline/money/data/ifs_context.json questions.falling_rolls / high_send.
FALLING_ROLLS_DROP = 0.05       # pupils down 5% or more over the years shown
FALLING_ROLLS_RUN = 3           # or down in each of the last 3 years
PASS_THROUGH_FROM = "2023-24"   # pension and NI grants grew from here
PASS_THROUGH_INCOME_RISE = 0.05
PASS_THROUGH_STAFF_SHARE = 0.7
EHCP_NATIONAL = 5.3             # IFS p.58: 5.3% of pupils have an EHCP


def _pounds(value):
    """Round to the nearest £1, halves away from zero (Python's round() goes to even)."""
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


def year_label(row: dict) -> str:
    """'2024-25' for both CFR ('2024-25') and AAR ('2024/25') rows."""
    return str(row["year"]).replace("/", "-")


def other_dfe_grants(row: dict):
    """The container line that holds the pension and NI grants, which cannot be separated out.

    CFR: I18 additional grants up to 2024-25, then I06 other government grants (where those grants
    moved in 2025-26). AAR: other DfE revenue grants. None when the row has neither.
    """
    if row.get("other_dfe_grants") is not None:
        return row["other_dfe_grants"]
    if row.get("source") == "AAR":
        return row.get("aar_other_dfe_revenue_grants")
    if row.get("cfr_additional_grants_i18") is not None:
        return row["cfr_additional_grants_i18"]
    if str(row.get("period_end") or "") >= "2026-03":
        return (row.get("lines") or {}).get("I06")
    return None


def value(row: dict, key: str):
    """A metric from a row, using older key names and deriving other_dfe_grants when absent."""
    if key == "other_dfe_grants":
        return other_dfe_grants(row)
    found = row.get(key)
    if found is None and key in ALIASES:
        found = row.get(ALIASES[key])
    return found


def sen_share(row: dict):
    """SEN funding as a share of the year's total income, or None."""
    sen, income = row.get("sen_funding"), row.get("total_income")
    if sen is None or not income or income <= 0:
        return None
    return sen / income


def pta_year(period_end, source: str = "CFR"):
    """School year label holding a charity return that ends in `period_end` ('YYYY-MM' or 'YYYY-MM-DD').

    CFR schools' years run April Y to March Y+1, so 2023-03 -> '2022-23' and 2025-08 -> '2025-26'.
    AAR schools' years run September Y to August Y+1, so 2025-08 -> '2024-25'. None for a bad date.
    """
    text = str(period_end or "")
    try:
        year, month = int(text[:4]), int(text[5:7])
    except ValueError:
        return None
    if len(text) < 7 or text[4] != "-" or not 1 <= month <= 12:
        return None
    first_month = 9 if str(source).upper() == "AAR" else 4
    start = year if month >= first_month else year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _cell(amount, row: dict, pupils):
    cell = {"v": _pounds(amount)}
    if pupils:
        cell["pp"] = _pounds(amount / pupils)
    try:
        real = deflator.to_real(amount, row["year"], row.get("source") or "CFR")
    except KeyError:
        real = None
    if real is not None:
        cell["r"] = _pounds(real)
        if pupils:
            cell["rpp"] = _pounds(real / pupils)
    return cell


def _previous_label(label: str) -> str:
    start = int(label[:4]) - 1
    return f"{start}-{str(start + 1)[2:]}"


def _falling_rolls(years: list[str], pupils: dict):
    """Down 5% from the first year with pupils to the latest year, or down in each of the last 3 years.

    The latest year needs its own count, and the run needs 4 back-to-back years, each with a count.
    """
    if not years or not pupils.get(years[-1]):
        return None
    counts = [pupils[y] for y in years if pupils.get(y)]
    if len(counts) < 2:
        return None
    change = counts[-1] / counts[0] - 1
    run = [years[-1]]
    while len(run) <= FALLING_ROLLS_RUN and pupils.get(_previous_label(run[0])):
        run.insert(0, _previous_label(run[0]))
    recent = [pupils[y] for y in run]
    falling_run = len(recent) == FALLING_ROLLS_RUN + 1 and all(b < a for a, b in zip(recent, recent[1:]))
    if change <= -FALLING_ROLLS_DROP + 1e-9 or falling_run:
        return {"from": counts[0], "to": counts[-1], "change": round(change, 4)}
    return None


def _pass_through(full: list[dict]):
    if len(full) < 2:
        return None
    latest, before = full[-1], full[-2]
    label = year_label(latest)
    if label < PASS_THROUGH_FROM or year_label(before) != _previous_label(label):
        return None
    income, income_before = value(latest, "total_income"), value(before, "total_income")
    staff, staff_before = value(latest, "total_staff"), value(before, "total_staff")
    if None in (income, income_before, staff, staff_before) or income_before <= 0:
        return None
    income_rise, staff_rise = income - income_before, staff - staff_before
    if income_rise >= PASS_THROUGH_INCOME_RISE * income_before and staff_rise >= PASS_THROUGH_STAFF_SHARE * income_rise:
        return {"year": label, "income_rise": _pounds(income_rise), "staff_rise": _pounds(staff_rise)}
    return None


def _high_send(latest: dict, sen_share_q3):
    ehcp = latest.get("ehcp_pct")
    if ehcp is not None and "ehcp_pct" in (latest.get("suspect") or []):
        ehcp = None
    share = sen_share(latest)
    if ehcp is not None and ehcp > EHCP_NATIONAL:
        reason = "ehcp"
    elif share is not None and sen_share_q3 is not None and share >= sen_share_q3:
        reason = "sen_share"
    else:
        return None
    return {"ehcp_pct": ehcp, "sen_share": round(share, 4) if share is not None else None, "reason": reason}


def _confidence(record: dict):
    match = record.get("match") if isinstance(record.get("match"), dict) else {}
    if match.get("method") == "llm":
        return "medium"
    found = match.get("confidence")
    return found if found in CONFIDENCE_ORDER else None


def _school_source(period_end: str, rows: list[dict]) -> str:
    """The school's sector for a charity return: its own row for that year, else its nearest year's row."""
    dated = sorted((r for r in rows if r.get("period_end") and r.get("source") in ("CFR", "AAR")),
                   key=lambda r: r["period_end"])
    if not dated:
        return "CFR"
    for r in dated:
        if year_label(r) == pta_year(period_end, r["source"]):
            return r["source"]

    def months(text):
        return int(text[:4]) * 12 + int(text[5:7])
    target = months(period_end)
    nearest = min(dated, key=lambda r: (abs(months(r["period_end"]) - target), r["period_end"]))
    return nearest["source"]


def _pta(pta, rows: list[dict], pupils: dict) -> dict:
    """Parents' association income and spending per school year, summed over its charities."""
    totals: dict[str, dict] = {}
    for record in pta or []:
        if not isinstance(record, dict) or record.get("review"):
            continue
        share = 1 / (1 + len(record.get("shared_with") or []))
        confidence = _confidence(record)
        returns: dict[str, dict] = {}
        for entry in record.get("history") or []:
            if not isinstance(entry, dict):
                continue
            if pta_year(entry.get("period_end"), "CFR") is None or (
                    entry.get("income") is None and entry.get("expenditure") is None):
                continue
            returns[str(entry["period_end"])] = entry  # a return listed twice counts once
        for end, entry in returns.items():
            label = pta_year(end, _school_source(end, rows))
            slot = totals.setdefault(label, {"income": None, "spend": None, "by_charity": {}, "confidence": []})
            income = entry.get("income") * share if entry.get("income") is not None else None
            spend = entry.get("expenditure") * share if entry.get("expenditure") is not None else None
            if income is not None:
                slot["income"] = (slot["income"] or 0) + income
            if spend is not None:
                slot["spend"] = (slot["spend"] or 0) + spend
            number = record.get("charity_number")
            slot["by_charity"][number] = slot["by_charity"].get(number, 0) + (income or 0)
            if confidence:
                slot["confidence"].append(confidence)
    out = {}
    for label in sorted(totals):
        slot = totals[label]
        count = pupils.get(label)
        item = {"income": _pounds(slot["income"]) if slot["income"] is not None else None,
                "spend": _pounds(slot["spend"]) if slot["spend"] is not None else None,
                "income_pp": _pounds(slot["income"] / count) if count and slot["income"] is not None else None,
                "spend_pp": _pounds(slot["spend"] / count) if count and slot["spend"] is not None else None,
                "charity_number": max(slot["by_charity"].items(), key=lambda kv: (kv[1], str(kv[0] or "")))[0],
                "confidence": min(slot["confidence"], key=CONFIDENCE_ORDER.index) if slot["confidence"] else None}
        out[label] = item
    return out


def _pupils_any_year(rows: list[dict]) -> dict:
    """Pupils per year label from every row (a 12-month return wins), for years outside the full years."""
    out: dict[str, float] = {}
    for r in sorted(rows, key=lambda r: (r.get("period_months") == 12, r.get("period_end") or "")):
        if r.get("pupils") and r.get("year"):
            out[year_label(r)] = float(r["pupils"])
    return out


def _one_per_year(full: list[dict]) -> list[dict]:
    """One return per year label, oldest first: where a CFR and an AAR return share a label (a conversion
    year), the one ending later is the school's own for that year and supplies all of it."""
    by_label = {year_label(r): r for r in full}  # full is oldest first, so the later return wins
    return [by_label[label] for label in sorted(by_label)]


def school_series(rows: list[dict], pta=None, *, sen_share_q3=None) -> dict:
    """The SERIES dict for one school: years, source, pupils, m, gap, pta, flags and trust_central_pp."""
    full = _one_per_year(status.full_years(rows))
    years = [year_label(r) for r in full]
    source = {year_label(r): r["source"] for r in full}
    pupils = {year_label(r): float(r["pupils"]) for r in full if r.get("pupils")}
    m: dict[str, dict] = {}
    suspect: dict[str, list] = {}
    trust_central: dict[str, int] = {}
    for row in full:
        label = year_label(row)
        for key, _, _ in METRICS:
            if row.get("source") == "AAR" and key in NOT_IN_AAR:
                continue
            amount = value(row, key)
            if amount is not None:
                m.setdefault(key, {})[label] = _cell(amount, row, pupils.get(label))
        flagged = [k for k in row.get("suspect") or [] if value(row, k) is not None]
        if flagged:
            suspect[label] = flagged
        if row.get("trust_central_spend_per_pupil") is not None:
            trust_central[label] = _pounds(row["trust_central_spend_per_pupil"])

    gap: dict[str, dict] = {}
    for label in years:
        gov = m.get("grant_funding_government", {}).get(label, {})
        spend = m.get("total_expenditure", {}).get(label, {})
        entry = {name: cell[basis] for name, cell, basis in (
            ("gov_pp", gov, "pp"), ("spend_pp", spend, "pp"), ("gov_rpp", gov, "rpp"), ("spend_rpp", spend, "rpp"))
            if basis in cell}
        if entry:
            gap[label] = entry

    pta_pupils = {**_pupils_any_year(rows), **pupils}
    not_reported = {k: why for k, why in NOT_IN_AAR.items() if any(r.get("source") == "AAR" for r in full)}
    return {
        "years": years,
        "source": source,
        "pupils": pupils,
        "m": m,
        "gap": gap,
        "pta": _pta(pta, rows, pta_pupils),
        "flags": {
            "falling_rolls": _falling_rolls(years, pupils),
            "pass_through": _pass_through(full),
            "high_send": _high_send(full[-1], sen_share_q3) if full else None,
            "suspect": suspect,
            "not_reported": not_reported,
        },
        "trust_central_pp": trust_central,
    }


def sparkline_values(series: dict, metric: str, basis: str = "pp") -> list[tuple]:
    """[(year, value)] for one metric on one basis (v, pp, r or rpp), oldest first, skipping gaps."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}, not {basis!r}")
    cells = (series.get("m") or {}).get(metric) or {}
    return [(year, cells[year][basis]) for year in series.get("years") or [] if basis in cells.get(year, {})]
