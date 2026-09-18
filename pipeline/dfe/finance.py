"""School finance from FBIT downloads: CFR (maintained schools) and AAR (academies).

CFR covers the financial year April-March; AAR covers the academy year
September-August. Categories are harmonised using the FBIT workbook's own
derived totals so maintained and academy figures line up.
"""

from __future__ import annotations

from pathlib import Path

import xlsx
from values import CRYPTIC_KEYS, num, per

FINANCE_LABELS = {
    "source": "CFR = LA maintained school return; AAR = academy accounts return",
    "federated_return": "Set when finances are reported as one return for a federation of schools",
    "period_months": "Months covered by the return",
    "pupils": "Pupils (FTE for academies)",
    "teachers_fte": "Teachers (FTE)",
    "total_income": "Total income (£)",
    "total_expenditure": "Total expenditure (£)",
    "in_year_balance": "In-year balance: income minus expenditure (£)",
    "revenue_reserve": "Revenue reserve carried forward (£)",
    "revenue_reserve_incl_trust_share": "Revenue reserve incl. share of trust central reserve (£)",
    "income_per_pupil": "Income per pupil (£)",
    "expenditure_per_pupil": "Expenditure per pupil (£)",
    "income": "Income by source (£)",
    "expenditure": "Spending by category (£)",
    "per_pupil": "Spending by category per pupil (£)",
    "grant_funding": "Grant funding",
    "self_generated": "Self-generated income (lettings, catering, donations ...)",
    "sen_funding": "SEN funding",
    "pupil_premium": "Pupil premium",
    "teaching_staff": "Teaching staff",
    "supply_staff": "Supply teachers (incl. agency and insurance)",
    "education_support_staff": "Education support staff (e.g. teaching assistants)",
    "admin_clerical_staff": "Administrative and clerical staff",
    "premises_staff": "Premises staff",
    "catering_staff": "Catering staff",
    "other_staff_costs": "Other staff costs (development, indirect, insurance)",
    "total_staff": "Total staff costs",
    "premises": "Premises (maintenance, cleaning, premises staff)",
    "energy": "Energy",
    "occupation": "Occupation (utilities, rates, insurance, catering)",
    "catering": "Catering (staff and supplies)",
    "educational_supplies": "Educational supplies (learning resources, ICT, exam fees)",
    "supplies_services": "Supplies and services",
    "bought_in_services": "Bought-in professional services",
}

EXPENDITURE_KEYS = [
    "teaching_staff", "supply_staff", "education_support_staff", "admin_clerical_staff",
    "premises_staff", "catering_staff", "other_staff_costs", "total_staff", "premises",
    "energy", "occupation", "catering", "educational_supplies", "supplies_services",
    "bought_in_services",
]

CFR_MAP = {
    "total_income": "Total Income: I01:I18 - E30",
    "total_expenditure": "Total Expenditure: (E01:E29 + E31 + E32)",
    "in_year_balance": "In-year Balance: Total Income (I01:I18 - E30) - Total Expenditure (E01:E29 + E31 + E32)",
    "revenue_reserve": "Revenue Reserve: B01 + B02 + B06",
    "grant_funding": "Grant Funding: (I01:I07) + I15 + I16 + I18a/b/c/d",
    "self_generated": "Self Generated Funding: (I08a/b:I13) + I17",
    "sen_funding": "I03 SEN funding",
    "pupil_premium": "I05 Pupil premium",
    "teaching_staff": "Teaching Staff E01",
    "supply_staff": "Supply Staff: E02 + E10 + E26",
    "education_support_staff": "Education support staff: E03",
    "admin_clerical_staff": "E05 Administrative and clerical staff",
    "premises_staff": "E04 Premises staff",
    "catering_staff": "E06 Catering staff",
    "other_staff_costs": "Other Staff Costs: (E07:E09) + E11",
    "total_staff": "Staff Total: (E01:E03) + E05 + (E07: E11) + E26",
    "premises": "Premises: (E12:E14) + E04 + E28b",
    "energy": "E16 Energy",
    "occupation": "Occupation: E06 + (E15:E18) + E23 + E25",
    "catering": "Catering Expenses: E06 + E25",
    "educational_supplies": "Educational Supplies: (E19:E21)",
    "supplies_services": "Supplies and Services: (E19:E22) + (E27:E28b)",
    "bought_in_services": "Brought in Professional Services: (E27 + E28a)",
}

# AAR header row 2 (descriptive names); some are duplicated so we index by position lookup.
AAR_MAP = {
    "total_income": "Total Income",
    "total_expenditure": "Total Expenditure",
    "in_year_balance": "In year balance",
    "revenue_reserve": "Revenue Reserve",
    "revenue_reserve_incl_trust_share": "RR + share of CS RR distributed on proportional per pupil basis",
    "grant_funding": "Total Grant Funding",
    "self_generated": "Total Self Generated Funding",
    "sen_funding": "SEN funding",
    "teaching_staff": "Teaching staff",
    "supply_staff": "Supply Staff Costs",
    "education_support_staff": "Education support staff",
    "admin_clerical_staff": "Administrative and clerical staff",
    "premises_staff": "Premises staff",
    "catering_staff": "Catering staff",
    "other_staff_costs": "Other Staff Costs",
    "total_staff": "Total Staff Costs",
    "premises": "Premises Costs",
    "energy": "Energy",
    "occupation": "Occupation Costs",
    "catering": "Catering Expenses",
    "educational_supplies": "Total Costs of Educational Supplies",
    "supplies_services": "Total Costs of Supplies and Services",
    "bought_in_services": "Costs of Brought in Professional Services",
}
MONEY_KEYS = [k for k in AAR_MAP]


def _phase(value) -> str:
    v = (value or "").strip().lower()
    if v.startswith("primary") or v == "infant" or v == "junior":
        return "primary"
    if v.startswith("secondary"):
        return "secondary"
    if v.startswith("special"):
        return "special"
    if v.startswith("nursery"):
        return "nursery"
    if "pupil referral" in v or "alternative" in v:
        return "alternative_provision"
    if "all-through" in v or "all through" in v:
        return "all_through"
    if "16" in v:
        return "post16"
    return v or "other"


def _int_str(value) -> str | None:
    n = num(value)
    return str(int(n)) if n is not None else None


def _read_cfr(path: Path) -> tuple[list[dict], dict[str, dict]]:
    """Returns (returning schools, {urn: member-school info} for federation members
    whose finances are reported in the lead school's combined return)."""
    rows = xlsx.iter_rows(path, "CFR Data")
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    out = []
    members: dict[str, dict] = {}
    for row in rows:
        rec = dict(zip(header, row))
        urn = _int_str(rec.get("URN"))
        if urn is None:
            continue
        federated = (rec.get("Federated submission") or "").strip()
        if rec.get("Did Not Supply flag") == "Y":
            lead = _int_str(rec.get("Lead school in federation"))
            if federated == "Non returning school" and lead and lead != "0":
                members[urn] = {
                    "lead_laestab": lead,
                    "name": rec.get("School Name"),
                    "pupils": num(rec.get("No pupils")),
                }
            continue
        item = {
            "urn": urn,
            "laestab": _int_str(rec.get("LAEstab")),
            "name": rec.get("School Name"),
            "federated": federated,
            "la": num(rec.get("LA")),
            "source": "CFR",
            "phase": _phase(rec.get("Overall Phase")),
            "period_months": num(rec.get("Period covered by return")),
            "pupils": num(rec.get("No pupils")),
            "teachers_fte": num(rec.get("FTE Number of teachers")),
        }
        for key, col in CFR_MAP.items():
            item[key] = num(rec.get(col))
        out.append(item)
    return out, members


def _read_aar(path: Path) -> list[dict]:
    rows = xlsx.iter_rows(path, "Academies")
    next(rows)  # code row (BAI010 ...)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    index: dict[str, int] = {}
    for i, name in enumerate(header):
        index.setdefault(name, i)
    missing = [col for col in AAR_MAP.values() if col not in index]
    if missing:
        raise RuntimeError(f"AAR workbook missing columns: {missing}")
    out = []
    for row in rows:
        def get(col):
            i = index.get(col)
            return row[i] if i is not None and i < len(row) else None
        urn = _int_str(get("URN"))
        if urn is None:
            continue
        item = {
            "urn": urn,
            "la": num(get("LA")),
            "source": "AAR",
            "phase": _phase(get("Overall Phase")),
            "period_months": num(get("Period covered by return")),
            "pupils": num(get("Number of pupils in academy (FTE) plus dual subsidiary registrations")),
            "teachers_fte": num(get("Number of teachers in academy (FTE)")),
            "trust": (get("Trust or Company Name") or None),
            "trust_type": (get("MAT SAT or Central Services") or None),
            "date_joined": get("Date joined or opened if in period"),
        }
        for key, col in AAR_MAP.items():
            item[key] = num(get(col))
        out.append(item)
    return out


def _merge_academy_rows(rows: list[dict]) -> dict:
    """An academy that changed trust mid-year has one row per trust: sum the money."""
    if len(rows) == 1:
        return rows[0]
    rows = sorted(rows, key=lambda r: (r.get("date_joined") or 0))
    merged = dict(rows[-1])  # latest trust for descriptive fields
    for key in MONEY_KEYS:
        values = [r[key] for r in rows if r.get(key) is not None]
        merged[key] = sum(values) if values else None
    merged["period_months"] = sum(r.get("period_months") or 0 for r in rows) or None
    return merged


def _section(item: dict, year: str, federation: dict | None = None) -> dict:
    pupils = item.get("pupils")
    out = {
        "year": year,
        "source": item["source"],
        "federated_return": federation,
        "period": "April 2024 to March 2025" if item["source"] == "CFR" else "September 2024 to August 2025",
        "period_months": item.get("period_months"),
        "trust": item.get("trust"),
        "pupils": pupils,
        "teachers_fte": item.get("teachers_fte"),
        "total_income": item.get("total_income"),
        "total_expenditure": item.get("total_expenditure"),
        "in_year_balance": item.get("in_year_balance"),
        "revenue_reserve": item.get("revenue_reserve"),
        "revenue_reserve_incl_trust_share": item.get("revenue_reserve_incl_trust_share"),
        "income_per_pupil": per(item.get("total_income"), pupils),
        "expenditure_per_pupil": per(item.get("total_expenditure"), pupils),
        "income": {k: item.get(k) for k in ("grant_funding", "self_generated", "sen_funding", "pupil_premium") if item.get(k) is not None},
        "expenditure": {k: item.get(k) for k in EXPENDITURE_KEYS},
        "per_pupil": {k: per(item.get(k), pupils) for k in EXPENDITURE_KEYS},
    }
    out = {k: v for k, v in out.items() if v is not None}
    present = set(out) | set(out["expenditure"]) | set(out.get("income", {}))
    out["labels"] = {k: v for k, v in FINANCE_LABELS.items() if k in present and k in CRYPTIC_KEYS}
    return out


def build_finance(cfr_path: Path, aar_path: Path, register_urns: set[str]):
    cfr, members = _read_cfr(cfr_path)
    aar = _read_aar(aar_path)

    academies: dict[str, list[dict]] = {}
    for item in aar:
        academies.setdefault(item["urn"], []).append(item)
    academy_items = {urn: _merge_academy_rows(rows) for urn, rows in academies.items()}
    cfr_items = {item["urn"]: item for item in cfr}

    by_laestab = {item["laestab"]: item for item in cfr if item.get("laestab")}
    federation_members: dict[str, list[dict]] = {}
    for urn, info in members.items():
        federation_members.setdefault(info["lead_laestab"], []).append({"urn": int(urn), "name": info["name"]})

    per_school = {}
    for urn in register_urns:
        if urn in academy_items:
            per_school[urn] = _section(academy_items[urn], "2024/25")
        elif urn in cfr_items:
            item = cfr_items[urn]
            federation = None
            if item.get("federated") == "Lead school":
                federation = {
                    "role": "lead school",
                    "note": "Figures are the combined return for all schools in the federation",
                    "member_schools": sorted(federation_members.get(item["laestab"], []), key=lambda m: m["name"] or ""),
                }
            per_school[urn] = _section(item, "2024-25", federation)
        elif urn in members and members[urn]["lead_laestab"] in by_laestab:
            lead = by_laestab[members[urn]["lead_laestab"]]
            federation = {
                "role": "member school",
                "note": "This school does not submit its own return; figures are the federation's combined return made by the lead school",
                "lead_school": {"urn": int(lead["urn"]), "name": lead["name"]},
                "school_pupils": members[urn]["pupils"],
            }
            per_school[urn] = _section(lead, "2024-25", federation)

    # Benchmarks: pupil-weighted means (sum of £ / sum of pupils) by phase,
    # full-year returns only, CFR and AAR combined, per LA and England-wide.
    groups: dict[tuple, dict] = {}
    for item in list(cfr_items.values()) + list(academy_items.values()):
        pupils = item.get("pupils")
        if not pupils or item.get("period_months") != 12 or item.get("total_expenditure") is None:
            continue
        areas = [("england", None)]
        la = item.get("la")
        if la is not None:
            areas.append(("la", str(int(la))))
        for kind, code in areas:
            for phase in (item["phase"], "all"):
                g = groups.setdefault((kind, code, phase), {"schools": 0, "pupils": 0.0, "sums": {}})
                g["schools"] += 1
                g["pupils"] += pupils
                for key in ["total_income", "total_expenditure"] + EXPENDITURE_KEYS:
                    if item.get(key) is not None:
                        g["sums"][key] = g["sums"].get(key, 0.0) + item[key]
    bench = {
        "year": "CFR 2024-25 (April-March) and AAR 2024/25 (September-August)",
        "method": "Pupil-weighted mean per pupil (total £ / total pupils) over full-year returns, maintained schools and academies combined",
        "labels": {k: FINANCE_LABELS[k] for k in ["income_per_pupil", "expenditure_per_pupil"] + EXPENDITURE_KEYS},
        "la": {},
        "england": {},
    }
    for (kind, code, phase), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2])):
        entry = {"schools": g["schools"]}
        entry["income_per_pupil"] = per(g["sums"].get("total_income"), g["pupils"])
        entry["expenditure_per_pupil"] = per(g["sums"].get("total_expenditure"), g["pupils"])
        entry["per_pupil"] = {k: per(g["sums"].get(k), g["pupils"]) for k in EXPENDITURE_KEYS}
        if kind == "england":
            bench["england"][phase] = entry
        else:
            bench["la"].setdefault(code, {})[phase] = entry
    stats = {"cfr_rows": len(cfr), "aar_rows": len(aar)}
    return per_school, bench, stats
