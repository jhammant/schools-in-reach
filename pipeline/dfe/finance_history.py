"""Eight years of school finance history from the DfE FBIT workbooks.

Reads every CFR_<yyyy-yy>_Full_Data_Workbook.xlsx (council-run schools,
April-March) and AAR_<yyyy-yy>_download.xlsx (academies, September-August) in
the cache directory and writes one JSON row per school per year, in the shape
pipeline/money/build_money.py consumes (finance_history.jsonl).

Column layouts drift from year to year, so each canonical key has an ordered
list of header aliases (exact labels first, looser regexes last). A workbook
that cannot supply a required key fails loudly with every header it contains.

Besides the headline keys each row carries:
- lines: {code: value} line-level detail. CFR codes are the DfE CFR codes
  (I01..I18 incl. I18a-d, E01..E32 incl. E20A-G, B01..B07, OB01..OB03); AAR
  keys are the lowercased 2024-25 benchmarking codes (bai010, bae150 ...) with
  older BNCH codes translated, or a slug of the label for composite columns.
- adjusted: keys whose source values were harmonised (CFR 2018-19 and 2019-20
  totals had E30 direct revenue financing removed).
- suspect: keys whose source values are known to be bad (fsm_pct above 100;
  a sixth-form column that is zero for every school).
- trust_central_*: the trust's central-services return joined on company number.

Stdlib only; reuses pipeline/dfe/xlsx.py and pipeline/dfe/values.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from xml.etree.ElementTree import iterparse

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _p in (str(_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pipeline.dfe import finance, xlsx  # noqa: E402
from pipeline.dfe.values import num  # noqa: E402

CACHE_DEFAULT = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/dfe/fbit")
OUT_DEFAULT = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/dfe/finance_history.jsonl")
REPORT_DEFAULT = _HERE / "REPORT_finance_history.md"

HEADER_SEARCH_ROWS = 15
FILENAME = re.compile(r"^(CFR|AAR)_(\d{4})-(\d{2})")

REQUIRED = ["urn", "la", "phase", "period_months", "pupils", "total_income", "total_expenditure", "revenue_reserve"]
INCOME_KEYS = ["grant_funding", "self_generated", "sen_funding", "pupil_premium"]
# Detailed income keys added in wave A (null when a workbook lacks the column).
DETAIL_INCOME_KEYS = ["donations_revenue", "donations_capital", "facilities_income", "lettings_income",
                      "community_facilities_income", "catering_income", "teacher_pension_ni_grants",
                      "cfr_additional_grants_i18", "aar_other_dfe_revenue_grants", "non_government_grants",
                      "income_from_academies"]
# Keys that copy another key's value (same column, second name), per SHARED 'FINANCE ROWS'.
COPY_KEYS = {"self_generated_income": "self_generated", "total_staff_costs": "total_staff",
             "teaching_staff_costs": "teaching_staff", "education_support_staff_costs": "education_support_staff"}
TRUST_CENTRAL_KEYS = ["trust_central_spend_per_pupil", "trust_central_total_expenditure", "trust_central_pupils"]
# Every money field a row carries; all None for federation members that did not supply a return.
MONEY_KEYS = (["total_income", "total_expenditure", "in_year_balance", "revenue_reserve",
               "revenue_reserve_incl_trust_share"] + INCOME_KEYS + finance.EXPENDITURE_KEYS
              + DETAIL_INCOME_KEYS + ["grant_funding_government"] + list(COPY_KEYS))
# Columns read for their own sake but not written out.
INTERNAL_KEYS = ["e30", "trust_reserve_share", "whole_trust_reserve_share", "date_joined", "facilities_other_income"]
EXCEL_EPOCH_ORDINAL = 693594  # date(1899, 12, 30).toordinal(): Excel serial day 0

# Known data problems per (source, year) that the report should repeat.
KNOWN_ISSUES = {
    ("AAR", "2022/23"): "fsm_pct is suspect for the whole workbook: academy median 16.3% against 20.3% (2021/22) and "
                        "22.1% (2023/24), with values up to 646.2; rows above 100 carry 'fsm_pct' in suspect",
    ("CFR", "2025-26"): "I18 additional grants line removed; those grants now appear in I06 Other government grants, "
                        "so cfr_additional_grants_i18 is null and I06 is not comparable with earlier years",
}


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text).replace("_x000D_", " ")).strip() if text is not None else ""


def exact(label: str) -> str:
    """Alias that matches one real header label (case-insensitive, whitespace-normalised)."""
    return re.escape(_norm(label))


# Ordered aliases per canonical key; the first alias that matches a header wins.
# Exact real labels seen in the 2018-19 .. 2025-26 workbooks come first, regexes last.
CFR_ALIASES: dict[str, list[str]] = {
    "urn": [exact("URN")],
    "la": [exact("LA")],
    "laestab": [exact("LAEstab"), exact("LAEsteb")],
    "name": [exact("School Name")],
    "phase": [exact("Overall Phase")],
    "period_months": [exact("Period covered by return"), exact("Period covered by return (months)"),
                      r"period covered by return.*"],
    "pupils": [exact("No pupils"), exact("No pupils (including dual registrations)"),
               exact("Full time equivalent number of pupils in school"), r"no\.? ?pupils.*", r"number of pupils in school.*"],
    "teachers_fte": [exact("FTE Number of teachers"), exact("No Teachers"), r"(fte )?number of teachers.*"],
    "fsm_pct": [exact("% of pupils eligible for FSM")],
    "ehcp_pct": [exact("% of pupils with EHCP"), exact("% of pupils with an EHCP"), exact("% of pupils with SEN Statement"),
                 r"% of pupils with (an )?ehcp.*", r"% of pupils with (a )?sen statement.*"],
    "sixth_form_pupils": [exact("Number of pupils in 6th form"), exact("No of pupils in 6th form"),
                          r"(no|number) of pupils in (6th|sixth) form.*"],
    "did_not_supply": [exact("Did Not Supply flag")],
    "federated": [exact("Federated submission"), exact("Federation"), exact("Federated submission (Y/LAEstab/N)"),
                  exact("Federation Y/S/N"), r"federat(ed submission|ion).*"],
    "lead_laestab": [exact("Lead school in federation")],
    "total_income": [exact("Total Income: I01:I18 - E30"), exact("Total Income: I01:I17 - E30"), exact("Total Income"),
                     r"total income: i01:i1[78] - e30"],
    "total_expenditure": [exact("Total Expenditure: (E01:E29 + E31 + E32)"), exact("Total Expenditure"),
                          r"total expenditure: \(e01:e29 \+ e31 \+ e32\).*"],
    "in_year_balance": [exact("In-year Balance: Total Income (I01:I18 - E30) - Total Expenditure (E01:E29 + E31 + E32)"),
                        exact("In-year Balance: Total Income (I01:I17 - E30) - Total Expenditure (E01:E29 + E31 + E32)"),
                        exact("In-year Balance: Total Income (I01 to I18) minus Total Expenditure (E01 to E32)"),
                        r"in-year balance.*"],
    "revenue_reserve": [exact("Revenue Reserve: B01 + B02 + B06"), exact("Revenue Reserve: B01 plus B02 plus B06"),
                        r"revenue reserve.*"],
    "e30": [exact("E30 Direct revenue financing (revenue contributions to capital)"), r"e30 direct revenue financing.*"],
    "grant_funding": [exact("Grant Funding: (I01:I07) + I15 + I16 + I18a/b/c/d"), exact("Grant Funding: (I01:I07) + I15 + I16"),
                      exact("Grant Funding"), r"grant funding:.*"],
    "self_generated": [exact("Self Generated Funding: (I08a/b:I13) + I17"), exact("Self Generated Funding"),
                       r"self generated funding:.*"],
    "sen_funding": [exact("I03 SEN funding")],
    "pupil_premium": [exact("I05 Pupil premium")],
    "donations_revenue": [exact("I13 Donations and/or private funds"), r"i13 donations.*"],
    "donations_capital": [exact("CI03 Voluntary or private income"), r"ci03 voluntary.*"],
    "facilities_income": [exact("I08a/b Total income from facilities and services"), exact("I08 Income from facilities and services"),
                          r"i08(a/b)? (total )?income from facilities and services.*"],
    "lettings_income": [exact("I08a Income from lettings"), r"i08a income from (rentals and )?lettings.*"],
    "community_facilities_income": [exact("I17 Community focused school facilities income"), r"i17 community focus+ed school facilities income.*"],
    "catering_income": [exact("I09 Income from catering"), r"i09 income from catering.*"],
    "teacher_pension_ni_grants": [r"i\d{2}[a-d]? (teachers'? pension|teachers'? pay|national insurance).*grant.*",
                                  r".*teachers'? pension (employer contributions? )?grant.*", r".*(tpecg|tpag|national insurance contributions grant).*"],
    "cfr_additional_grants_i18": [exact("I18 Total additional grant for schools"), exact("I18 Additional grant for schools"),
                                  r"i18 (total )?additional grants? for schools.*"],
    "teaching_staff": [exact("Teaching Staff E01"), exact("Teaching Staff: E01"), exact("E01 Teaching Staff")],
    "supply_staff": [exact("Supply Staff: E02 + E10 + E26"), exact("Supply Staff"), r"supply staff:.*"],
    "education_support_staff": [exact("Education support staff: E03"), exact("E03 Education support staff")],
    "admin_clerical_staff": [exact("E05 Administrative and clerical staff")],
    "premises_staff": [exact("E04 Premises staff")],
    "catering_staff": [exact("E06 Catering staff")],
    "other_staff_costs": [exact("Other Staff Costs: (E07:E09) + E11"), exact("Other Staff Costs"), r"other staff costs:.*"],
    "total_staff": [exact("Staff Total: (E01:E03) + E05 + (E07: E11) + E26"), exact("Staff Total"), r"staff total:.*"],
    "premises": [exact("Premises: (E12:E14) + E04 + E28b"), exact("Premises"), r"premises:.*"],
    "energy": [exact("E16 Energy")],
    "occupation": [exact("Occupation: E06 + (E15:E18) + E23 + E25"), exact("Occupation"), r"occupation:.*"],
    "catering": [exact("Catering Expenses: E06 + E25"), exact("Catering Exp"), r"catering exp(enses)?:.*"],
    "educational_supplies": [exact("Educational Supplies: (E19:E21)"), exact("Educational Supplies: (E19:E20C) + (E20E:E21)"),
                             exact("Educational Supplies"), r"educational supplies:.*"],
    "supplies_services": [exact("Supplies and Services: (E19:E22) + (E27:E28b)"), exact("Supplies and Services"),
                          r"supplies and services:.*"],
    "bought_in_services": [exact("Brought in Professional Services: (E27 + E28a)"), exact("Brought in Professional Sevices: (E27 + E28a)"),
                           exact("Brought in Professional Sevices"), r"brought in professional se(r)?vices.*"],
}

AAR_ALIASES: dict[str, list[str]] = {
    "urn": [exact("URN")],
    "la": [exact("LA")],
    "laestab": [exact("LAEstab"), exact("LAEsteb")],
    "name": [exact("School Name")],
    "phase": [exact("Overall Phase")],
    "period_months": [exact("Period covered by return"), r"period covered by return.*"],
    "pupils": [exact("Number of pupils in academy (FTE) plus dual subsidiary registrations"),
               exact("Number of pupils in academy (FTE)"), exact("No Pupils"), r"number of pupils in academy.*"],
    "teachers_fte": [exact("Number of teachers in academy (FTE)"), exact("No Teachers"), r"number of teachers in academy.*"],
    "fsm_pct": [exact("% of pupils eligible for FSM")],
    "ehcp_pct": [exact("% of pupils with EHCP"), exact("% of pupils with an EHCP"), exact("% of pupils with SEN Statement"),
                 r"% of pupils with (an )?ehcp.*", r"% of pupils with (a )?sen statement.*"],
    "sixth_form_pupils": [exact("No of pupils in 6th form"), exact("Number of pupils in 6th form"),
                          r"(no|number) of pupils in (6th|sixth) form.*"],
    "trust": [exact("Trust or Company Name"), exact("Company Name")],
    "trust_type": [exact("MAT SAT or Central Services"), exact("MAT/SAT")],
    "company_number": [exact("Company Number"), r"company (registration )?number"],
    "date_joined": [exact("Date joined or opened if in period"), exact("Date joined if in period"), r"date joined.*"],
    "total_income": [exact("Total Income")],
    "total_expenditure": [exact("Total Expenditure")],
    "in_year_balance": [exact("In year balance"), exact("In Year Balance"), r"in[- ]year balance"],
    "revenue_reserve": [exact("Revenue Reserve"), exact("Revenue reserve")],
    "revenue_reserve_incl_trust_share": [exact("RR + share of CS RR distributed on proportional per pupil basis"),
                                         r"rr \+ share of cs rr.*"],
    # Central-services reserve only (2024-25): added to the school's own reserve when the combined column is absent.
    "trust_reserve_share": [
        exact("Share of Central Services Revenue Reserve, distributed on per pupil basis, at end of period based on time spent in trust"),
        r"share of central services revenue reserve, distributed.*"],
    # 2018-19 .. 2023-24: the WHOLE trust's reserve (central services plus every academy's own reserve) spread
    # per pupil. It already contains this school's reserve, so it is never added to revenue_reserve; it is read
    # only so the report can say why revenue_reserve_incl_trust_share is null for those years.
    "whole_trust_reserve_share": [
        exact("Share of Revenue Reserve, distributed on per pupil basis"),
        exact("Distributed Revenue Reserve.on pp basis"),
        r"share of revenue reserve, distributed.*", r"distributed revenue reserve.*"],
    # 'Total Grant Funding' includes government non-grant income, income from other academies and
    # non-government income; grant_funding_government strips the last two (see read_workbook).
    "grant_funding": [exact("Total Grant Funding"), exact("Grant Funding")],
    "self_generated": [exact("Total Self Generated Funding"), exact("Self Generated Funding")],
    "sen_funding": [exact("SEN funding"), exact("SEN")],
    "pupil_premium": [],  # academies' returns do not break out pupil premium
    "donations_revenue": [exact("Donations and/or voluntary funds"), r"donations and/?or voluntary funds.*"],
    "donations_capital": [],  # the AAR download carries revenue donations only
    "facilities_income": [exact("All income from facilities and services"), exact("Income from facilities and services"),
                          r"(all )?income from facilities and services"],
    "lettings_income": [exact("Income from rentals and lettings"), r"income from (rentals and )?lettings"],
    "facilities_other_income": [exact("Income from facilities and services - other"), r"(other )?income from facilities and services -? ?other"],
    "community_facilities_income": [],  # no community-focused line in the academies return
    "catering_income": [exact("Income from catering")],
    "teacher_pension_ni_grants": [r".*teachers'? pension (employer contributions? )?grant.*", r".*(tpecg|tpag|national insurance contributions grant).*"],
    "cfr_additional_grants_i18": [],
    "aar_other_dfe_revenue_grants": [exact("Other DfE Revenue Grants"), exact("Other DfE/ESFA Revenue Grants"),
                                     exact("Other DfE/EFA Revenue Grants"), r"other dfe(/e?s?fa)? revenue grants"],
    "non_government_grants": [exact("Non-Government"), exact("Non- Government"), r"non-? ?government( income)?"],
    "income_from_academies": [exact("Academies"), r"(income from )?academies"],
    "teaching_staff": [exact("Teaching staff")],
    "supply_staff": [exact("Supply Staff Costs"), exact("Supply Staff")],
    "education_support_staff": [exact("Education support staff")],
    "admin_clerical_staff": [exact("Administrative and clerical staff")],
    "premises_staff": [exact("Premises staff")],
    "catering_staff": [exact("Catering staff")],
    "other_staff_costs": [exact("Other Staff Costs")],
    "total_staff": [exact("Total Staff Costs"), exact("Staff Total")],
    "premises": [exact("Premises Costs"), exact("Premises")],
    "energy": [exact("Energy")],
    "occupation": [exact("Occupation Costs"), exact("Occupation")],
    "catering": [exact("Catering Expenses"), exact("Catering Exp")],
    "educational_supplies": [exact("Total Costs of Educational Supplies"), exact("Educational Supplies")],
    "supplies_services": [exact("Total Costs of Supplies and Services"), exact("Supplies and Services")],
    "bought_in_services": [exact("Costs of Brought in Professional Services"), exact("Brought in Professional Services"),
                           exact("Brought in Professional Sevices")],
}

# AAR workbooks carry a code row (BAI010 ...) above the descriptive header. Some
# cells in either row are formula notes rather than names; these identify columns
# by that note or by the code when the descriptive label is no use.
AAR_NOTE_ALIASES: dict[str, list[str]] = {
    "in_year_balance": [r"=?\s*total income\s*-\s*total expenditure"],
    "revenue_reserve": [exact("BAB030")],
    "revenue_reserve_incl_trust_share": [r"rr \+ \(cs rr \*.*"],
    "trust_reserve_share": [r"share of central services revenue reserve, distributed.*"],
    "whole_trust_reserve_share": [r"multiply trust total pp share of rr.*",
                                  r"\(?cs rr\s*\+\s*sum of acad rr.*"],
    "lettings_income": [exact("BAI100")],
    "facilities_other_income": [exact("BAI101")],
}

ALIASES = {"CFR": CFR_ALIASES, "AAR": AAR_ALIASES}
NOTE_ALIASES = {"CFR": {}, "AAR": AAR_NOTE_ALIASES}

# Central-services sheet of the AAR workbooks: one row per trust, joined to academies on company number.
CENTRAL_ALIASES: dict[str, list[str]] = {
    "company_number": [exact("Company Number"), r"company (registration )?number"],
    "trust_central_total_expenditure": [exact("Total Expenditure")],
    "trust_central_pupils": [exact("Total number of Pupils"), exact("Total Pupils"), exact("Total pupils in trust"),
                             r"total (number of )?pupils( in trust)?"],
    "trust_central_spend_per_pupil": [exact("Trust Total Exp per pupil"), r"trust total exp(enditure)? per pupil.*"],
}

# ----------------------------------------------------------------- line-level detail

# CFR line codes at the start of a header: "I08a Income from lettings", "E20A Connectivity", "OB01 ...".
# "I08a/b Total ..." and "E28a/b Total ..." are the a+b totals and are keyed by the bare code (I08, E28)
# so the total has one key in every year; "I01/2 Total ..." has no single code and is skipped.
CFR_LINE = re.compile(r"^((?:OB|I|E|B)\d{2})([a-gA-G])?(?:/([a-g0-9]))?(?=\s)")

# Hand-written public labels for every CFR code (2024-25 wording). read_workbook refreshes them from the
# most recent workbook that carries the code, so the dict always has a label for every code in `lines`.
CFR_LINE_LABELS: dict[str, str] = {
    "I01": "Funds delegated by the local authority",
    "I02": "Funding for sixth form students",
    "I03": "SEN funding",
    "I04": "Funding for minority ethnic pupils",
    "I05": "Pupil premium",
    "I06": "Other government grants",
    "I07": "Other grants and payments",
    "I08": "Income from facilities and services (total)",
    "I08a": "Income from lettings",
    "I08b": "Income from facilities and services",
    "I09": "Income from catering",
    "I10": "Receipts from supply teacher insurance claims",
    "I11": "Receipts from other insurance claims",
    "I12": "Income from contributions to visits etc.",
    "I13": "Donations and/or private funds",
    "I14": "School standards grant, pupil focused (no longer collected)",
    "I15": "Pupil focused extended school funding and/or grants",
    "I16": "Community focused school funding and/or grants",
    "I17": "Community focused school facilities income",
    "I18": "Total additional grant for schools",
    "I18a": "Income from the Coronavirus Job Retention Scheme",
    "I18b": "Income from the DfE grant scheme for exceptional COVID-19 costs",
    "I18c": "Income from the £1bn COVID-19 catch-up package",
    "I18d": "Income from other additional grants",
    "E01": "Teaching staff",
    "E02": "Supply teaching staff",
    "E03": "Education support staff",
    "E04": "Premises staff",
    "E05": "Administrative and clerical staff",
    "E06": "Catering staff",
    "E07": "Cost of other staff",
    "E08": "Indirect employee expenses",
    "E09": "Development and training",
    "E10": "Supply teacher insurance",
    "E11": "Staff related insurance",
    "E12": "Building maintenance and improvement",
    "E13": "Grounds maintenance and improvement",
    "E14": "Cleaning and caretaking",
    "E15": "Water and sewerage",
    "E16": "Energy",
    "E17": "Rates",
    "E18": "Other occupation costs",
    "E19": "Learning resources (not ICT equipment)",
    "E20": "ICT learning resources",
    "E20A": "Connectivity",
    "E20B": "Onsite servers",
    "E20C": "IT learning resources",
    "E20D": "Administration software and systems",
    "E20E": "Laptops, desktops and tablets",
    "E20F": "Other hardware",
    "E20G": "IT support",
    "E21": "Exam fees",
    "E22": "Administrative supplies",
    "E23": "Other insurance premiums",
    "E24": "Special facilities",
    "E25": "Catering supplies",
    "E26": "Agency supply teaching staff",
    "E27": "Bought in professional services: curriculum",
    "E28": "Bought in professional services: other (total)",
    "E28a": "Bought in professional services: other, not PFI",
    "E28b": "Bought in professional services: other, PFI",
    "E29": "Loan interest",
    "E30": "Direct revenue financing (revenue contributions to capital)",
    "E31": "Community focused school staff",
    "E32": "Community focused school costs",
    "OB01": "Opening pupil-focused revenue balance",
    "OB02": "Opening community-focused revenue balance",
    "OB03": "Opening capital balance",
    "B01": "Committed revenue balances",
    "B02": "Uncommitted revenue balances",
    "B03": "Devolved formula capital balance",
    "B04": "Other Standards Fund capital balances (no longer collected)",
    "B05": "Other capital balances",
    "B06": "Community-focused school revenue balances",
    "B07": "Outstanding balance on capital loans to school",
}

# AAR line keys are the lowercased 2024-25 benchmarking codes. Older workbooks used BNCH codes for the
# same columns; this table translates them so a key means the same column in every year.
AAR_CODE_TRANSLATION = {
    "BNCH11141": "BAI030", "BNCH11142": "BAI040", "BNCH11151": "BAI060", "BNCHBAI061": "BAI061",
    "BNCH11161": "BAI070", "BNCH11162": "BAI080", "BNCH11163": "BAI090", "BNCH11202": "BAI110",
    "BNCH11203": "BAI120", "BNCH11204": "BAI130", "BNCH11300T": "BAI140", "BNCH11400T": "BAI150",
    "BNCH21101": "BAE010", "BNCH21102": "BAE020", "BNCH21103": "BAE030", "BNCH21104": "BAE040",
    "BNCH21105": "BAE050", "BNCH21106": "BAE060", "BNCH21107": "BAE070", "BNCH21201": "BAE080",
    "BNCH21202": "BAE090", "BNCH21204": "BAE100", "BNCH21203": "BAE110", "BNCH21401": "BAE130",
    "BNCH21402": "BAE140", "BNCH21403": "BAE150", "BNCH21404": "BAE160", "BNCH21406": "BAE180",
    "BNCH21501": "BAE190", "BNCH21601": "BAE200", "BNCH21602": "BAE210", "BNCH21603": "BAE220",
    "BNCH21604": "BAE230", "BNCH21606": "BAE240", "BNCH21701": "BAE250", "BNCH21703": "BAE260",
    "BNCH21705": "BAE270", "BNCH21706": "BAE280", "BNCH21707": "BAE290", "BNCH21702": "BAE300",
    "BNCH21802": "BAE310", "BNCH21801": "BAE320",
}
AAR_SINGLE_CODE = re.compile(r"^(BNCH[A-Z0-9]+|BA[IE]\d{3})( \(is -ve income\))?$", re.IGNORECASE)

# Columns whose code cell lists several codes, or whose code changed meaning: matched on the label
# (first) or the code cell, in order, before the single-code rule. Keys are stable slugs.
AAR_LINE_ALIASES: dict[str, list[str]] = {
    "bai010": [exact("DfE revenue grants"), r"dfe/efa revenue grants( \(includes coronavirus government funding\)?)?",
               exact("Pre-16 DFE/EFA Revenue grants")],
    "bai061": [exact("Coronavirus Government Funding"), exact("of which: Coronavirus Government Funding"), exact("BAI061"), exact("BNCHBAI061")],
    "income_from_facilities_and_services": [exact("All income from facilities and services"), exact("Income from facilities and services")],
    "building_and_grounds_maintenance": [exact("Building and Grounds maintenance and improvement")],
}

AAR_LINE_LABELS: dict[str, str] = {
    "bai010": "DfE revenue grants (before 2024-25 this line also held 16 to 19 and coronavirus funding)",
    "bai011": "16 to 19 allocations",
    "bai020": "Other DfE Group grants (revenue)",
    "bai030": "SEN funding",
    "bai040": "Other DfE revenue grants",
    "bai050": "Grants for trust activity",
    "bai060": "Other income: LA and other government grants",
    "bai061": "Coronavirus government funding",
    "bai070": "Government source (non-grant)",
    "bai080": "Income from other academies",
    "bai090": "Non-government income",
    "bai100": "Income from rentals and lettings",
    "bai101": "Income from facilities and services: other",
    "income_from_facilities_and_services": "Income from facilities and services (lettings included; split into bai100 and bai101 from 2024-25)",
    "bai110": "Income from catering",
    "bai120": "Receipts from supply teacher insurance claims",
    "bai130": "Other self-generated income",
    "bai140": "Donations and/or voluntary funds",
    "bai150": "Investment income",
    "bae010": "Teaching staff",
    "bae020": "Supply teaching staff",
    "bae030": "Education support staff",
    "bae040": "Administrative and clerical staff",
    "bae050": "Premises staff",
    "bae060": "Catering staff",
    "bae070": "Other staff",
    "bae080": "Indirect employee expenses",
    "bae090": "Staff development and training",
    "bae100": "Supply teacher insurance",
    "bae110": "Staff-related insurance",
    "bae120": "Maintenance of premises",
    "building_and_grounds_maintenance": "Building and grounds maintenance and improvement (split into bae120 and bae170 from 2024-25)",
    "bae130": "Cleaning and caretaking",
    "bae140": "Water and sewerage",
    "bae150": "Energy",
    "bae160": "Rent and rates",
    "bae170": "Grounds maintenance",
    "bae180": "Other occupation costs",
    "bae190": "Special facilities",
    "bae200": "Learning resources (not ICT equipment)",
    "bae210": "ICT learning resources",
    "bae220": "Examination fees",
    "bae230": "Educational consultancy",
    "bae240": "Agency supply teaching staff",
    "bae250": "Catering supplies",
    "bae260": "Auditor costs",
    "bae270": "Other insurance premiums",
    "bae280": "Administrative supplies (non-educational)",
    "bae290": "Direct revenue financing (revenue contributions to capital)",
    "bae300": "Legal and professional services",
    "bae310": "PFI charges",
    "bae320": "Interest charges for loans and bank",
}

# Public labels for every key that can appear in row['lines'], refreshed from the newest workbook read.
LINE_LABELS: dict[str, str] = {**CFR_LINE_LABELS, **AAR_LINE_LABELS}
_LINE_LABEL_SEEN: dict[str, str] = {}  # code -> period_end of the workbook whose label is in LINE_LABELS


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def cfr_line_code(label: str) -> str | None:
    """CFR code at the start of a header label, or None. 'I08a/b Total ...' -> 'I08'; 'I01/2 ...' -> None."""
    m = CFR_LINE.match(_norm(label))
    if not m:
        return None
    base, suffix, second = m.group(1), m.group(2), m.group(3)
    if second is not None:
        return base if (suffix and second.isalpha()) else None
    return base + (suffix or "")


def aar_line_key(label: str, code_cell: str) -> str | None:
    """Stable key for an AAR detail column from its label and the code-row cell above it, or None."""
    label, code_cell = _norm(label), _norm(code_cell)
    for key, patterns in AAR_LINE_ALIASES.items():
        if any(_matches(p, label) or _matches(p, code_cell) for p in patterns):
            return key
    m = AAR_SINGLE_CODE.match(code_cell)
    if not m:
        return None
    code = m.group(1).upper()
    code = AAR_CODE_TRANSLATION.get(code, code)
    if not re.fullmatch(r"BA[IE]\d{3}", code):
        return None  # a BNCH code with no modern equivalent (e.g. the revenue reserve BNCH44001)
    return code.lower()


# AAR columns that are never a detail line, for exports without a code row: identifiers, names, dates,
# counts, percentages, categories, flags, and the totals/reserves that the canonical keys already hold.
# Whole-label matches first (so "PFI" is excluded but "PFI Charges" is a line), then fragments.
AAR_NON_LINE_LABEL = re.compile(
    r"^(la|urn|estab|laestab|laesteb|uid|pfi|gender|phase|overall phase|type|region|london borough|london weighting|"
    r"admissions policy|has a 6th form|mat/?sat|mat sat or central services|school name|academy ?upin|lead upin)$"
    r"|^total\b|^no\b|upin|company (number|name)|trust or company|trust type|\bdate\b|\bperiod\b|reserve|balance|"
    r"\brr\b|%|\bno\.? of\b|\bnumber of\b|\bage of\b|\bflag\b|urban|rural", re.IGNORECASE)


def aar_has_code_row(codes: list[str]) -> bool:
    """True when at least one code cell above the header carries a benchmarking code (BAI010, BNCH11141...)."""
    return any(re.search(r"\b(BA[IE]\d{3}|BNCH[A-Z0-9]+)\b", c, re.IGNORECASE) for c in codes if c)


def line_columns(header: list, neighbours: list[list], source: str) -> dict[str, int]:
    """Map line keys to column indexes for one workbook.

    AAR keys are the lowercased benchmarking codes from the code row above the header. An export with no
    code row at all falls back to a slug of each detail label (teaching_staff, income_from_catering...),
    skipping identifier, count, percentage and total columns (AAR_NON_LINE_LABEL).
    """
    width = max([len(header)] + [len(r) for r in neighbours])
    labels = [_norm(header[i]) if i < len(header) else "" for i in range(width)]
    codes = [""] * width
    for row in neighbours:
        for i in range(width):
            cell = _norm(row[i]) if i < len(row) else ""
            if cell and not codes[i]:
                codes[i] = cell
    slug_fallback = source == "AAR" and not aar_has_code_row(codes)
    out: dict[str, int] = {}
    for i, label in enumerate(labels):
        if source == "CFR":
            key = cfr_line_code(label)
        else:
            key = aar_line_key(label, codes[i])
            if key is None and slug_fallback and label and not AAR_NON_LINE_LABEL.search(label):
                key = _slug(label)
        if key and key not in out:
            out[key] = i
    return out


def _learn_line_labels(index: dict[str, int], header: list, period_end: str) -> None:
    for key, i in index.items():
        label = _norm(header[i]) if i < len(header) else ""
        if not label:
            continue
        if key[:1].isupper():  # CFR: strip the leading code from the label
            label = re.sub(r"^\S+\s+", "", label)
        if period_end >= _LINE_LABEL_SEEN.get(key, ""):
            LINE_LABELS[key] = label
            _LINE_LABEL_SEEN[key] = period_end


# ----------------------------------------------------------------- workbook reading

def sheet_names(path: Path) -> list[str]:
    """Sheet names in workbook order (xlsx.py has no helper for this)."""
    with zipfile.ZipFile(path) as zf, zf.open("xl/workbook.xml") as fh:
        return [el.get("name") for _, el in iterparse(fh) if el.tag == xlsx.NS + "sheet"]


def _squash(name: str) -> str:
    return re.sub(r"[\s_]+", "", name or "").lower()


def pick_sheet(names: list[str], source: str) -> str:
    """CFR: 'CFR Data' / 'CFR_Output' / 'CFRData' / 'CFR_Data'. AAR: 'Academies' / 'Academies 2018 to 19'."""
    for name in names:
        squashed = _squash(name)
        if source == "CFR" and squashed in ("cfrdata", "cfroutput"):
            return name
        if source == "AAR" and squashed.startswith("academies"):
            return name
    raise ValueError(f"no {source} data sheet among {names}")


def pick_central_sheet(names: list[str]) -> str | None:
    """AAR 'Central Services' / 'CentralServices' / 'Central Services 2018 to 19', or None."""
    for name in names:
        if _squash(name).startswith("centralservices"):
            return name
    return None


def _matches(alias: str, text: str) -> bool:
    return bool(text) and re.fullmatch(alias, text, re.IGNORECASE) is not None


def resolve_columns(header: list, neighbours: list[list], source: str, aliases=None, notes=None) -> tuple[dict[str, int], dict[str, str]]:
    """Map canonical keys to column indexes. Returns (key -> index, key -> label used).

    For each key the aliases are tried in order against the descriptive labels. If
    none matches, formula-note aliases are tried against the label and then the
    neighbouring rows (the code row above, a second header row below), and finally
    the ordinary aliases against those neighbouring rows.
    """
    width = max([len(header)] + [len(r) for r in neighbours])
    labels = [_norm(header[i]) if i < len(header) else "" for i in range(width)]
    others = [[_norm(r[i]) if i < len(r) else "" for i in range(width)] for r in neighbours]
    aliases = ALIASES[source] if aliases is None else aliases
    notes = NOTE_ALIASES[source] if notes is None else notes
    index: dict[str, int] = {}
    used: dict[str, str] = {}

    def find(patterns, texts):
        for pattern in patterns:
            for i, text in enumerate(texts):
                if i not in index.values() and _matches(pattern, text):
                    return i
        return None

    for key, patterns in aliases.items():
        attempts = [(patterns, labels, None), (notes.get(key, []), labels, "formula note")]
        attempts += [(notes.get(key, []), texts, "neighbour row") for texts in others]
        attempts += [(patterns, texts, "neighbour row") for texts in others]
        for candidates, texts, how in attempts:
            i = find(candidates, texts)
            if i is not None:
                index[key] = i
                used[key] = labels[i] if how is None else f"{labels[i] or '(blank)'} [via {how}: {texts[i]}]"
                break
    return index, used


def _sort_date(value):
    """Join date as an Excel serial day, so mixed serial-number and text dates sort on one scale.

    Excel serials are kept; dd/mm/yyyy and yyyy-mm-dd text are converted to the same epoch
    (day 0 = 1899-12-30); blanks and 'n/a' sort first as 0.
    """
    n = num(value)
    if n is not None:
        return n
    text = _norm(value)
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4}).*", text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2}).*", text)
        if not m:
            return 0
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    from datetime import date
    return date(year, month, day).toordinal() - EXCEL_EPOCH_ORDINAL


def _int_str(value) -> str | None:
    n = num(value)
    return str(int(n)) if n is not None else None


def _company_number(value) -> str | None:
    """Companies House numbers as text; numeric cells lose their leading zeros, so pad back to 8 digits."""
    n = num(value)
    if n is not None:
        return str(int(n)).zfill(8)
    text = _norm(value)
    return text.upper() or None


def _truthy_flag(value) -> bool:
    return _norm(value).upper() in ("Y", "YES", "DNS", "1", "TRUE")


def _federated(value) -> tuple[str | None, str | None]:
    """Normalise the federation column to the 2024-25 vocabulary.

    Returns (federated, lead_laestab_from_this_column). Old workbooks use
    'Y/S/N' (lead / member / none) or put the lead school's LAEstab in the cell.
    """
    v = _norm(value)
    if v == "":
        return None, None
    upper = v.upper()
    if upper in ("N", "NO", "0"):
        return "No", None
    if upper == "Y":
        return "Lead school", None
    if upper == "S":
        return "Non returning school", None
    if re.fullmatch(r"\d{5,7}", v):
        return "Non returning school", v
    return v, None


def _year_labels(path: Path) -> tuple[str, str, str]:
    m = FILENAME.match(path.name)
    if not m:
        raise ValueError(f"{path.name}: expected CFR_<yyyy-yy>_... or AAR_<yyyy-yy>_...")
    source, start, end2 = m.group(1), int(m.group(2)), m.group(3)
    if source == "CFR":
        return source, f"{start}-{end2}", f"{start + 1}-03"
    return source, f"{start}/{end2}", f"{start + 1}-08"


def _detect_header(rows, marker: str = "URN") -> tuple[int, list, list[list], list]:
    """Find the header row (first row within HEADER_SEARCH_ROWS holding a `marker` cell).

    Returns (header_index, header, neighbour_rows, buffered_rows_after_header).
    The neighbours are the row above and, when it is not already data, the row below.
    """
    seen: list[list] = []
    header_index = None
    for i, row in enumerate(rows):
        seen.append(row)
        if any(_norm(c).upper() == marker.upper() for c in row):
            header_index = i
            break
        if i + 1 >= HEADER_SEARCH_ROWS:
            break
    if header_index is None:
        raise ValueError(f"no header row with a {marker!r} cell in the first {HEADER_SEARCH_ROWS} rows")
    header = seen[header_index]
    marker_col = next(i for i, c in enumerate(header) if _norm(c).upper() == marker.upper())
    neighbours = [seen[header_index - 1]] if header_index > 0 else []
    rest: list[list] = []
    below = next(rows, None)
    if below is not None:
        if marker_col < len(below) and num(below[marker_col]) is not None:
            rest.append(below)
        else:
            neighbours.append(below)
    return header_index, header, neighbours, rest


def read_central_services(path: Path, sheet: str) -> tuple[dict[str, dict], dict]:
    """Trust central-services rows keyed by company number: {trust_central_* keys}, plus mapping info."""
    rows = xlsx.iter_rows(path, sheet)
    header_index, header, neighbours, rest = _detect_header(rows, marker="Company Number")
    index, used = resolve_columns(header, neighbours, "AAR", aliases=CENTRAL_ALIASES, notes={})
    out: dict[str, dict] = {}
    for row in _chain(rest, rows):
        def get(key):
            i = index.get(key)
            return row[i] if i is not None and i < len(row) else None
        company = _company_number(get("company_number"))
        if not company or company in out:
            continue
        spend = num(get("trust_central_total_expenditure")) if "trust_central_total_expenditure" in index else None
        pupils = num(get("trust_central_pupils")) if "trust_central_pupils" in index else None
        per_pupil = num(get("trust_central_spend_per_pupil")) if "trust_central_spend_per_pupil" in index else None
        if per_pupil is None and spend is not None and pupils:
            per_pupil = spend / pupils
        out[company] = {"trust_central_spend_per_pupil": per_pupil, "trust_central_total_expenditure": spend,
                        "trust_central_pupils": pupils}
    info = {"sheet": sheet, "header_row": header_index, "mapping": used, "trusts": len(out)}
    return out, info


def read_workbook(path: Path) -> tuple[list[dict], dict]:
    """Read one FBIT workbook into canonical rows.

    Returns (rows, info) where info has sheet, header_row, mapping {key: label},
    lines {key: label}, central {...}, warnings, year, period_end and source.
    Raises ValueError when a required key cannot be mapped, listing every header seen.
    """
    path = Path(path)
    source, year, period_end = _year_labels(path)
    names = sheet_names(path)
    sheet = pick_sheet(names, source)
    rows = xlsx.iter_rows(path, sheet)
    header_index, header, neighbours, rest = _detect_header(rows)
    index, used = resolve_columns(header, neighbours, source)
    missing = [k for k in REQUIRED if k not in index]
    if missing:
        labels = [_norm(c) for c in header if _norm(c)]
        raise ValueError(f"{path.name} (sheet {sheet!r}, header row {header_index}): could not map required keys "
                         f"{missing}. Headers seen: {labels}")
    lines_index = line_columns(header, neighbours, source)
    _learn_line_labels(lines_index, header, period_end)
    warnings: list[str] = []
    for key, alias in COPY_KEYS.items():
        if alias in used:
            used[key] = f"= {alias}"
    info = {"file": path.name, "source": source, "year": year, "period_end": period_end, "sheet": sheet,
            "header_row": header_index, "mapping": {k: used[k] for k in ALIASES[source] if k in used},
            "lines": {k: _norm(header[i]) if i < len(header) else "" for k, i in lines_index.items()},
            "central": None, "warnings": warnings}
    for key in COPY_KEYS:
        if key in used:
            info["mapping"][key] = used[key]

    central: dict[str, dict] = {}
    if source == "AAR":
        central_sheet = pick_central_sheet(names)
        if central_sheet is None:
            warnings.append("no central-services sheet; trust_central_* written as null")
        else:
            try:
                central, central_info = read_central_services(path, central_sheet)
                info["central"] = central_info
                for key in TRUST_CENTRAL_KEYS:
                    if key not in central_info["mapping"] and key != "trust_central_spend_per_pupil":
                        warnings.append(f"central-services sheet {central_sheet!r} has no column for {key!r}")
                if "trust_central_spend_per_pupil" not in central_info["mapping"]:
                    warnings.append("trust_central_spend_per_pupil derived as central total expenditure / trust pupils")
            except ValueError as exc:
                warnings.append(f"central-services sheet {central_sheet!r} unreadable ({exc}); trust_central_* written as null")

    def reader(row):
        def get(key):
            i = index.get(key)
            return row[i] if i is not None and i < len(row) else None
        return get

    out: list[dict] = []
    skipped = 0
    harmonise_e30 = source == "CFR" and "e30" in index and "e30" not in used.get("total_income", "").lower()
    for row in _chain(rest, rows):
        get = reader(row)
        urn = _int_str(get("urn"))
        if urn is None:
            skipped += 1
            continue
        la = num(get("la"))
        item: dict = {
            "urn": urn, "year": year, "period_end": period_end, "source": source,
            "la": int(la) if la is not None else None,
            "laestab": _int_str(get("laestab")),
            "name": _norm(get("name")) or None,
            "phase": finance._phase(_norm(get("phase"))),
            "period_months": num(get("period_months")),
            "pupils": num(get("pupils")),
            "teachers_fte": num(get("teachers_fte")),
        }
        for key in MONEY_KEYS:
            item[key] = num(get(key)) if key in index else None
        for key, alias in COPY_KEYS.items():
            item[key] = item.get(alias)
        item["ehcp_pct"] = num(get("ehcp_pct"))
        item["sixth_form_pupils"] = num(get("sixth_form_pupils"))
        item["company_number"] = None
        for key in TRUST_CENTRAL_KEYS:
            item[key] = None
        lines = {code: num(row[i]) if i < len(row) else None for code, i in lines_index.items()}
        derived: list[str] = []
        adjusted: list[str] = []
        suspect: list[str] = []
        if source == "CFR":
            federated, lead_from_flag = _federated(get("federated"))
            lead = _int_str(get("lead_laestab")) if "lead_laestab" in index else None
            if lead in (None, "0"):
                lead = lead_from_flag
            item["did_not_supply"] = _truthy_flag(get("did_not_supply")) if "did_not_supply" in index else False
            item["federated"] = federated
            item["lead_laestab"] = lead if lead != "0" else None
            item.pop("revenue_reserve_incl_trust_share")
            item["grant_funding_government"] = item["grant_funding"]
            if item["did_not_supply"]:
                for key in MONEY_KEYS:
                    if key in item:
                        item[key] = None
                lines = {}
            elif harmonise_e30:
                e30 = num(get("e30"))
                if e30:
                    for key in ("total_income", "total_expenditure"):
                        if item[key] is not None:
                            item[key] -= e30
                            derived.append(key)
                            adjusted.append(key)
        else:
            item["trust"] = _norm(get("trust")) or None
            item["trust_type"] = _norm(get("trust_type")) or None
            item["did_not_supply"] = False
            item["date_joined"] = _sort_date(get("date_joined"))
            item["company_number"] = _company_number(get("company_number")) if "company_number" in index else None
            if item["company_number"] in central:
                item.update(central[item["company_number"]])
            if "revenue_reserve_incl_trust_share" not in index and "trust_reserve_share" in index:
                # Only the central-services share may be added: the older whole-trust distributed
                # column already includes this academy's own reserve (see whole_trust_reserve_share).
                share = num(get("trust_reserve_share"))
                if item["revenue_reserve"] is not None:
                    item["revenue_reserve_incl_trust_share"] = item["revenue_reserve"] + (share or 0)
                    derived.append("revenue_reserve_incl_trust_share")
            if item["facilities_income"] is None and "lettings_income" in index and "facilities_other_income" in index:
                # A suppressed (or missing) part makes the sum unknown, not smaller: never treat it as zero.
                lettings, other = item["lettings_income"], num(get("facilities_other_income"))
                if lettings is not None and other is not None:
                    item["facilities_income"] = lettings + other
                    derived.append("facilities_income")
            # Government-only grants need every operand; an absent column or a suppressed cell leaves it unknown.
            parts = (item["grant_funding"], item["non_government_grants"], item["income_from_academies"])
            item["grant_funding_government"] = parts[0] - parts[1] - parts[2] if None not in parts else None
        item["fsm_pct"] = num(get("fsm_pct"))
        if item["fsm_pct"] is not None and item["fsm_pct"] > 100:
            suspect.append("fsm_pct")
        if "in_year_balance" not in index and not item["did_not_supply"]:
            if item["total_income"] is not None and item["total_expenditure"] is not None:
                item["in_year_balance"] = item["total_income"] - item["total_expenditure"]
                derived.append("in_year_balance")
        if derived:
            item["derived"] = derived
        item["lines"] = lines
        if adjusted:
            item["adjusted"] = adjusted
        if suspect:
            item["suspect"] = suspect
        out.append(item)

    if source == "AAR":
        out = _merge_academies(out)
    _null_all_zero_column(out, "sixth_form_pupils", "sixth_form_pupils" in index, warnings)
    derived_counts: dict[str, int] = {}
    for item in out:
        for key in item.get("derived", []):
            derived_counts[key] = derived_counts.get(key, 0) + 1
    for key in ALIASES[source]:
        if key in index or key in REQUIRED or key in INTERNAL_KEYS or key == "did_not_supply" or key in derived_counts:
            continue
        warnings.append(f"optional key {key!r} not found; written as null")
    if skipped:
        warnings.append(f"skipped {skipped} rows without a numeric URN")
    for key, count in sorted(derived_counts.items()):
        if key in ("total_income", "total_expenditure"):
            warnings.append(f"{key} harmonised by subtracting E30 direct revenue financing in {count} rows (later workbooks already exclude it)")
        elif key == "facilities_income":
            warnings.append(f"facilities_income derived as lettings + other facilities income in {count} rows (no total column)")
        else:
            warnings.append(f"{key} derived in {count} rows")
    suspect_fsm = sum(1 for r in out if "fsm_pct" in r.get("suspect", []))
    if suspect_fsm:
        warnings.append(f"fsm_pct above 100% in {suspect_fsm} rows; raw value kept and 'fsm_pct' added to suspect")
    if source == "AAR":
        negative = sum(1 for r in out if (r.get("non_government_grants") or 0) < 0 or (r.get("income_from_academies") or 0) < 0)
        if negative:
            warnings.append(f"{negative} academies report negative non-government or inter-academy income (refunds), so "
                            "grant_funding_government exceeds grant_funding for them")
    if source == "AAR" and central:
        unmatched = sum(1 for r in out if r.get("company_number") and r["company_number"] not in central)
        if unmatched:
            warnings.append(f"{unmatched} academies have a company number with no central-services row; trust_central_* null")
    if source == "AAR" and "whole_trust_reserve_share" in index and "revenue_reserve_incl_trust_share" not in index:
        warnings.append(f"{used['whole_trust_reserve_share']!r} spreads the whole trust's reserve (central services plus "
                        "every academy's own reserve) per pupil, so it already contains this school's reserve; it is not "
                        "comparable with 2024-25's 'RR + share of CS RR' and revenue_reserve_incl_trust_share is left null")
    if source == "CFR" and "lead_laestab" not in index:
        warnings.append("no 'Lead school in federation' column; lead_laestab only known where the federation column holds a LAEstab")
    if (source, year) in KNOWN_ISSUES:
        warnings.append(KNOWN_ISSUES[(source, year)])
    info["rows"] = len(out)
    return _ordered(out), info


def _null_all_zero_column(rows: list[dict], key: str, present: bool, warnings: list[str]) -> None:
    """A column that is 0 (or blank) for every school was not collected: write None and flag it suspect."""
    if not present or not rows:
        return
    if any(r.get(key) not in (None, 0) for r in rows):
        return
    for r in rows:
        r[key] = None
        r.setdefault("suspect", []).append(key)
    warnings.append(f"{key} column is zero for every row; written as null and added to suspect")


def _chain(first: list, rest):
    yield from first
    yield from rest


def _merge_academies(rows: list[dict]) -> list[dict]:
    """One row per academy per year: a trust change mid-year gives several rows, summed as finance.py does."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["urn"], []).append(row)
    merged = []
    for urn, group in groups.items():
        item = finance._merge_academy_rows(group)
        if len(group) > 1:
            ordered = sorted(group, key=lambda r: (r.get("date_joined") or 0))
            for key in MONEY_KEYS:
                if key in finance.MONEY_KEYS:
                    continue  # already summed by finance._merge_academy_rows
                values = [r[key] for r in ordered if r.get(key) is not None]
                item[key] = sum(values) if values else None
            codes = {code for r in ordered for code in r.get("lines", {})}
            lines = {}
            for code in codes:
                values = [r["lines"][code] for r in ordered if r.get("lines", {}).get(code) is not None]
                lines[code] = sum(values) if values else None
            item["lines"] = lines
            for field in ("derived", "adjusted", "suspect"):
                combined = sorted({k for r in group for k in r.get(field, [])})
                if combined:
                    item[field] = combined
                else:
                    item.pop(field, None)
        item.pop("date_joined", None)
        merged.append(item)
    return merged


NEW_KEYS = ["ehcp_pct", "sixth_form_pupils", "self_generated_income"] + DETAIL_INCOME_KEYS + [
    "grant_funding_government", "total_staff_costs", "teaching_staff_costs", "education_support_staff_costs",
    "company_number"] + TRUST_CENTRAL_KEYS
ROW_KEYS = ["urn", "year", "period_end", "source", "la", "laestab", "name", "phase", "period_months", "pupils",
            "teachers_fte", "total_income", "total_expenditure", "in_year_balance", "revenue_reserve",
            "revenue_reserve_incl_trust_share", "trust", "trust_type", "did_not_supply", "federated", "lead_laestab",
            "fsm_pct"] + INCOME_KEYS + finance.EXPENDITURE_KEYS + ["derived"] + NEW_KEYS + ["lines", "adjusted", "suspect"]


def _ordered(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        row.pop("date_joined", None)
        out.append({k: row[k] for k in ROW_KEYS if k in row})
    return out


def _cache_dir(cache_dir=None) -> Path:
    return Path(cache_dir or os.environ.get("FBIT_CACHE") or CACHE_DEFAULT)


def workbooks(cache_dir=None) -> list[Path]:
    cache = _cache_dir(cache_dir)
    return sorted(list(cache.glob("CFR_*.xlsx")) + list(cache.glob("AAR_*.xlsx")))


def load_history_with_info(cache_dir=None) -> tuple[list[dict], list[dict]]:
    """All workbooks in the cache: (rows sorted by urn then period_end, per-workbook info)."""
    paths = workbooks(cache_dir)
    if not paths:
        raise ValueError(f"no CFR_*.xlsx or AAR_*.xlsx workbooks in {_cache_dir(cache_dir)}")
    rows: list[dict] = []
    infos: list[dict] = []
    for path in paths:
        part, info = read_workbook(path)
        rows.extend(part)
        infos.append(info)
    rows.sort(key=lambda r: (r["urn"], r["period_end"], r["source"]))
    return rows, infos


def load_history(cache_dir=None) -> list[dict]:
    return load_history_with_info(cache_dir)[0]


def _money_bn(value) -> str:
    return f"£{value / 1e9:.2f}bn"


def _md(text: str) -> str:
    return "`" + text.replace("|", "\\|") + "`"


def report(rows: list[dict], infos: list[dict]) -> str:
    """Deterministic markdown report: one section per workbook plus totals and new-key coverage tables."""
    by_file: dict[tuple, list[dict]] = {}
    for row in rows:
        by_file.setdefault((row["source"], row["year"]), []).append(row)
    lines = ["# Finance history: FBIT workbooks", "",
             "Generated by `pipeline/dfe/finance_history.py`. One row per school per year; "
             "CFR years run April to March, AAR years September to August.", "",
             "Each row also carries `lines` (line-level detail keyed by CFR code or lowercased AAR benchmarking code), "
             "`adjusted` (keys harmonised against later years) and `suspect` (keys with known-bad source values).", ""]
    totals = []
    coverage = []
    for info in sorted(infos, key=lambda i: i["file"]):
        part = by_file.get((info["source"], info["year"]), [])
        supplied = [r for r in part if not r.get("did_not_supply")]
        negative = sum(1 for r in supplied if (r.get("revenue_reserve") or 0) < 0)
        income = sum(r["total_income"] for r in supplied if r.get("total_income") is not None)
        totals.append((info["file"], len(part), len(supplied), negative, income))
        adjusted = sum(1 for r in part if r.get("adjusted"))
        suspect = sum(1 for r in part if r.get("suspect"))
        with_lines = sum(1 for r in part if r.get("lines"))
        coverage.append((info["file"], {k: sum(1 for r in part if r.get(k) is not None) for k in NEW_KEYS},
                         len(info.get("lines", {})), with_lines, adjusted, suspect))
        lines += [f"## {info['file']}", "",
                  f"- Sheet: `{info['sheet']}`; header row index: {info['header_row']}",
                  f"- Rows: {len(part)} ({len(supplied)} with a return, {len(part) - len(supplied)} federation members without one)",
                  f"- Schools with revenue_reserve < 0: {negative}",
                  f"- England total income: {_money_bn(income)}",
                  f"- Line columns: {len(info.get('lines', {}))} ({with_lines} rows carry lines); rows with adjusted: {adjusted}; rows with suspect: {suspect}"]
        central = info.get("central")
        if central:
            lines.append(f"- Central services: sheet `{central['sheet']}`, {central['trusts']} trusts, columns "
                         + ", ".join(f"{k}={_md(v)}" for k, v in sorted(central["mapping"].items())))
        lines.append("")
        if info["warnings"]:
            lines += ["Warnings:", ""] + [f"- {w}" for w in info["warnings"]] + [""]
        lines += ["| key | source column |", "|---|---|"]
        keys = [k for k in ALIASES[info["source"]]] + [k for k in COPY_KEYS if k not in ALIASES[info["source"]]]
        for key in keys:
            if key in INTERNAL_KEYS and key not in info["mapping"]:
                continue
            label = info["mapping"].get(key)
            lines.append(f"| {key} | {_md(label) if label else '*absent*'} |")
        lines.append("")
        if info.get("lines"):
            lines += ["Line columns:", "", "| code | source column |", "|---|---|"]
            for code, label in info["lines"].items():
                lines.append(f"| {code} | {_md(label)} |")
            lines.append("")
    lines += ["## Totals", "", "| workbook | rows | with return | reserve < 0 | total income |", "|---|---:|---:|---:|---:|"]
    for file, n, supplied, negative, income in totals:
        lines.append(f"| {file} | {n} | {supplied} | {negative} | {_money_bn(income)} |")
    lines.append("")
    lines += ["## New keys: rows with a value per workbook", "",
              "| workbook | " + " | ".join(NEW_KEYS) + " | line cols | rows with lines | adjusted | suspect |",
              "|---|" + "---:|" * (len(NEW_KEYS) + 4)]
    for file, counts, n_lines, with_lines, adjusted, suspect in coverage:
        lines.append(f"| {file} | " + " | ".join(str(counts[k]) for k in NEW_KEYS)
                     + f" | {n_lines} | {with_lines} | {adjusted} | {suspect} |")
    lines.append("")
    all_counts = {k: sum(1 for r in rows if r.get(k) is not None) for k in NEW_KEYS}
    lines += ["## New keys: all rows", "", f"Rows in total: {len(rows)}", "", "| key | rows with a value |", "|---|---:|"]
    for key in NEW_KEYS:
        lines.append(f"| {key} | {all_counts[key]} |")
    lines.append(f"| lines (non-empty) | {sum(1 for r in rows if r.get('lines'))} |")
    lines.append("")
    flag_counts: dict[str, dict[str, int]] = {"adjusted": {}, "suspect": {}}
    for row in rows:
        for field in flag_counts:
            for key in row.get(field, []):
                flag_counts[field][key] = flag_counts[field].get(key, 0) + 1
    lines += ["## Adjusted and suspect flags", "", "| flag | key | rows |", "|---|---|---:|"]
    for field in ("adjusted", "suspect"):
        for key, n in sorted(flag_counts[field].items()):
            lines.append(f"| {field} | {key} | {n} |")
    lines.append("")
    return "\n".join(lines)


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=None, help=f"FBIT workbook directory (env FBIT_CACHE or {CACHE_DEFAULT})")
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    args = parser.parse_args(argv)
    rows, infos = load_history_with_info(args.cache)
    write_jsonl(rows, args.out)
    args.report.write_text(report(rows, infos), encoding="utf-8")
    print(f"{len(rows)} rows from {len(infos)} workbooks -> {args.out}; report {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
