"""Eight years of school finance history from the DfE FBIT workbooks.

Reads every CFR_<yyyy-yy>_Full_Data_Workbook.xlsx (council-run schools,
April-March) and AAR_<yyyy-yy>_download.xlsx (academies, September-August) in
the cache directory and writes one JSON row per school per year, in the shape
pipeline/money/build_money.py consumes (finance_history.jsonl).

Column layouts drift from year to year, so each canonical key has an ordered
list of header aliases (exact labels first, looser regexes last). A workbook
that cannot supply a required key fails loudly with every header it contains.

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
# Every money field a row carries; all None for federation members that did not supply a return.
MONEY_KEYS = ["total_income", "total_expenditure", "in_year_balance", "revenue_reserve",
              "revenue_reserve_incl_trust_share"] + INCOME_KEYS + finance.EXPENDITURE_KEYS
# Columns read for their own sake but not written out.
INTERNAL_KEYS = ["e30", "trust_reserve_share", "whole_trust_reserve_share", "date_joined"]
EXCEL_EPOCH_ORDINAL = 693594  # date(1899, 12, 30).toordinal(): Excel serial day 0


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text)).strip() if text is not None else ""


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
    "trust": [exact("Trust or Company Name"), exact("Company Name")],
    "trust_type": [exact("MAT SAT or Central Services"), exact("MAT/SAT")],
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
    "grant_funding": [exact("Total Grant Funding"), exact("Grant Funding")],
    "self_generated": [exact("Total Self Generated Funding"), exact("Self Generated Funding")],
    "sen_funding": [exact("SEN funding"), exact("SEN")],
    "pupil_premium": [],  # academies' returns do not break out pupil premium
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
}

ALIASES = {"CFR": CFR_ALIASES, "AAR": AAR_ALIASES}
NOTE_ALIASES = {"CFR": {}, "AAR": AAR_NOTE_ALIASES}


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


def _matches(alias: str, text: str) -> bool:
    return bool(text) and re.fullmatch(alias, text, re.IGNORECASE) is not None


def resolve_columns(header: list, neighbours: list[list], source: str) -> tuple[dict[str, int], dict[str, str]]:
    """Map canonical keys to column indexes. Returns (key -> index, key -> label used).

    For each key the aliases are tried in order against the descriptive labels. If
    none matches, formula-note aliases are tried against the label and then the
    neighbouring rows (the code row above, a second header row below), and finally
    the ordinary aliases against those neighbouring rows.
    """
    width = max([len(header)] + [len(r) for r in neighbours])
    labels = [_norm(header[i]) if i < len(header) else "" for i in range(width)]
    others = [[_norm(r[i]) if i < len(r) else "" for i in range(width)] for r in neighbours]
    aliases, notes = ALIASES[source], NOTE_ALIASES[source]
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


def _detect_header(rows) -> tuple[int, list, list[list], list]:
    """Find the header row (first row within HEADER_SEARCH_ROWS holding a 'URN' cell).

    Returns (header_index, header, neighbour_rows, buffered_rows_after_header).
    The neighbours are the row above and, when it is not already data, the row below.
    """
    seen: list[list] = []
    header_index = None
    for i, row in enumerate(rows):
        seen.append(row)
        if any(_norm(c).upper() == "URN" for c in row):
            header_index = i
            break
        if i + 1 >= HEADER_SEARCH_ROWS:
            break
    if header_index is None:
        raise ValueError(f"no header row with a 'URN' cell in the first {HEADER_SEARCH_ROWS} rows")
    header = seen[header_index]
    urn_col = next(i for i, c in enumerate(header) if _norm(c).upper() == "URN")
    neighbours = [seen[header_index - 1]] if header_index > 0 else []
    rest: list[list] = []
    below = next(rows, None)
    if below is not None:
        if urn_col < len(below) and num(below[urn_col]) is not None:
            rest.append(below)
        else:
            neighbours.append(below)
    return header_index, header, neighbours, rest


def read_workbook(path: Path) -> tuple[list[dict], dict]:
    """Read one FBIT workbook into canonical rows.

    Returns (rows, info) where info has sheet, header_row, mapping {key: label},
    warnings, year, period_end and source. Raises ValueError when a required key
    cannot be mapped, listing every header seen.
    """
    path = Path(path)
    source, year, period_end = _year_labels(path)
    sheet = pick_sheet(sheet_names(path), source)
    rows = xlsx.iter_rows(path, sheet)
    header_index, header, neighbours, rest = _detect_header(rows)
    index, used = resolve_columns(header, neighbours, source)
    missing = [k for k in REQUIRED if k not in index]
    if missing:
        labels = [_norm(c) for c in header if _norm(c)]
        raise ValueError(f"{path.name} (sheet {sheet!r}, header row {header_index}): could not map required keys "
                         f"{missing}. Headers seen: {labels}")
    warnings: list[str] = []
    info = {"file": path.name, "source": source, "year": year, "period_end": period_end, "sheet": sheet,
            "header_row": header_index, "mapping": {k: used[k] for k in ALIASES[source] if k in used},
            "warnings": warnings}

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
        derived: list[str] = []
        if source == "CFR":
            federated, lead_from_flag = _federated(get("federated"))
            lead = _int_str(get("lead_laestab")) if "lead_laestab" in index else None
            if lead in (None, "0"):
                lead = lead_from_flag
            item["did_not_supply"] = _truthy_flag(get("did_not_supply")) if "did_not_supply" in index else False
            item["federated"] = federated
            item["lead_laestab"] = lead if lead != "0" else None
            item.pop("revenue_reserve_incl_trust_share")
            if item["did_not_supply"]:
                for key in MONEY_KEYS:
                    if key in item:
                        item[key] = None
            elif harmonise_e30:
                e30 = num(get("e30"))
                if e30:
                    for key in ("total_income", "total_expenditure"):
                        if item[key] is not None:
                            item[key] -= e30
                            derived.append(key)
        else:
            item["trust"] = _norm(get("trust")) or None
            item["trust_type"] = _norm(get("trust_type")) or None
            item["did_not_supply"] = False
            item["date_joined"] = _sort_date(get("date_joined"))
            if "revenue_reserve_incl_trust_share" not in index and "trust_reserve_share" in index:
                # Only the central-services share may be added: the older whole-trust distributed
                # column already includes this academy's own reserve (see whole_trust_reserve_share).
                share = num(get("trust_reserve_share"))
                if item["revenue_reserve"] is not None:
                    item["revenue_reserve_incl_trust_share"] = item["revenue_reserve"] + (share or 0)
                    derived.append("revenue_reserve_incl_trust_share")
        item["fsm_pct"] = num(get("fsm_pct"))
        if "in_year_balance" not in index and not item["did_not_supply"]:
            if item["total_income"] is not None and item["total_expenditure"] is not None:
                item["in_year_balance"] = item["total_income"] - item["total_expenditure"]
                derived.append("in_year_balance")
        if derived:
            item["derived"] = derived
        out.append(item)

    if source == "AAR":
        out = _merge_academies(out)
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
        else:
            warnings.append(f"{key} derived in {count} rows")
    if source == "AAR" and "whole_trust_reserve_share" in index and "revenue_reserve_incl_trust_share" not in index:
        warnings.append(f"{used['whole_trust_reserve_share']!r} spreads the whole trust's reserve (central services plus "
                        "every academy's own reserve) per pupil, so it already contains this school's reserve; it is not "
                        "comparable with 2024-25's 'RR + share of CS RR' and revenue_reserve_incl_trust_share is left null")
    if source == "CFR" and "lead_laestab" not in index:
        warnings.append("no 'Lead school in federation' column; lead_laestab only known where the federation column holds a LAEstab")
    info["rows"] = len(out)
    return _ordered(out), info


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
            derived = sorted({k for r in group for k in r.get("derived", [])})
            if derived:
                item["derived"] = derived
            else:
                item.pop("derived", None)
        item.pop("date_joined", None)
        merged.append(item)
    return merged


ROW_KEYS = ["urn", "year", "period_end", "source", "la", "laestab", "name", "phase", "period_months", "pupils",
            "teachers_fte", "total_income", "total_expenditure", "in_year_balance", "revenue_reserve",
            "revenue_reserve_incl_trust_share", "trust", "trust_type", "did_not_supply", "federated", "lead_laestab",
            "fsm_pct"] + INCOME_KEYS + finance.EXPENDITURE_KEYS + ["derived"]


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


def report(rows: list[dict], infos: list[dict]) -> str:
    """Deterministic markdown report: one section per workbook plus a totals table."""
    by_file: dict[tuple, list[dict]] = {}
    for row in rows:
        by_file.setdefault((row["source"], row["year"]), []).append(row)
    lines = ["# Finance history: FBIT workbooks", "",
             "Generated by `pipeline/dfe/finance_history.py`. One row per school per year; "
             "CFR years run April to March, AAR years September to August.", ""]
    totals = []
    for info in sorted(infos, key=lambda i: i["file"]):
        part = by_file.get((info["source"], info["year"]), [])
        supplied = [r for r in part if not r.get("did_not_supply")]
        negative = sum(1 for r in supplied if (r.get("revenue_reserve") or 0) < 0)
        income = sum(r["total_income"] for r in supplied if r.get("total_income") is not None)
        totals.append((info["file"], len(part), len(supplied), negative, income))
        lines += [f"## {info['file']}", "",
                  f"- Sheet: `{info['sheet']}`; header row index: {info['header_row']}",
                  f"- Rows: {len(part)} ({len(supplied)} with a return, {len(part) - len(supplied)} federation members without one)",
                  f"- Schools with revenue_reserve < 0: {negative}",
                  f"- England total income: {_money_bn(income)}", ""]
        if info["warnings"]:
            lines += ["Warnings:", ""] + [f"- {w}" for w in info["warnings"]] + [""]
        lines += ["| key | source column |", "|---|---|"]
        for key in ALIASES[info["source"]]:
            if key in INTERNAL_KEYS and key not in info["mapping"]:
                continue
            label = info["mapping"].get(key)
            cell = "`" + label.replace("|", "\\|") + "`" if label else "*absent*"
            lines.append(f"| {key} | {cell} |")
        lines.append("")
    lines += ["## Totals", "", "| workbook | rows | with return | reserve < 0 | total income |", "|---|---:|---:|---:|---:|"]
    for file, n, supplied, negative, income in totals:
        lines.append(f"| {file} | {n} | {supplied} | {negative} | {_money_bn(income)} |")
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
