"""Tests for pipeline/dfe/finance_history.py.

Offline tests build tiny xlsx workbooks in a temp dir (hand-written sheet xml
through the real xlsx.iter_rows). Real-data tests only run when the FBIT cache
exists and never write into it.
"""

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from pipeline.dfe import finance, finance_history as fh

REAL_CACHE = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/dfe/fbit")
HAS_REAL = (REAL_CACHE / "CFR_2024-25_Full_Data_Workbook.xlsx").exists() and (REAL_CACHE / "AAR_2024-25_download.xlsx").exists()


# ----------------------------------------------------------------- fixtures

def _col(i: int) -> str:
    letters = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cell(ref: str, value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def make_xlsx(path: Path, sheets: list[tuple[str, list[list]]]) -> Path:
    """Write a minimal workbook: sheets is [(name, rows)], rows are lists of str/number/None."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(path, "w") as zf:
        sheet_tags, rel_tags = [], []
        for n, (name, rows) in enumerate(sheets, start=1):
            sheet_tags.append(f'<sheet name="{name}" sheetId="{n}" r:id="rId{n}"/>')
            rel_tags.append(f'<Relationship Id="rId{n}" Type="{rel}/worksheet" Target="worksheets/sheet{n}.xml"/>')
            body = []
            for r, row in enumerate(rows, start=1):
                cells = "".join(_cell(f"{_col(c)}{r}", v) for c, v in enumerate(row) if v is not None)
                body.append(f'<row r="{r}">{cells}</row>')
            zf.writestr(f"xl/worksheets/sheet{n}.xml",
                        f'<worksheet xmlns="{ns}"><sheetData>{"".join(body)}</sheetData></worksheet>')
        zf.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>{"".join(sheet_tags)}</sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{pkg}">{"".join(rel_tags)}</Relationships>')
    return path


CFR_ADMIN = ["LA", "LAEstab", "URN", "School Name", "Overall Phase", "Period covered by return", "No pupils",
             "FTE Number of teachers", "% of pupils eligible for FSM", "Did Not Supply flag", "Federated submission",
             "Lead school in federation"]
AAR_ADMIN = ["LAEstab", "LA", "URN", "School Name", "Period covered by return", "MAT SAT or Central Services",
             "Trust or Company Name", "Date joined or opened if in period",
             "Number of pupils in academy (FTE) plus dual subsidiary registrations", "Number of teachers in academy (FTE)",
             "Overall Phase", "% of pupils eligible for FSM"]


def cfr_header(**rename) -> list[str]:
    """2024-25 CFR header; rename={canonical_key: label} swaps a column's label."""
    labels = list(CFR_ADMIN) + [finance.CFR_MAP[k] for k in finance.CFR_MAP]
    keys = ["la", "laestab", "urn", "name", "phase", "period_months", "pupils", "teachers_fte", "fsm_pct",
            "did_not_supply", "federated", "lead_laestab"] + list(finance.CFR_MAP)
    for key, label in rename.items():
        labels[keys.index(key)] = label
    return labels


def cfr_row(urn=100001, income=1000000, spend=900000, reserve=150000, dns="N", federated="No", lead=0, pupils=250) -> list:
    money = {"total_income": income, "total_expenditure": spend, "in_year_balance": income - spend, "revenue_reserve": reserve}
    base = [204, f"204{urn % 10000:04d}", urn, f"School {urn}", "Primary", 12, pupils, 12.5, 21.3, dns, federated, lead]
    return base + [money.get(k, 1000) for k in finance.CFR_MAP]


def aar_header(**rename) -> list[str]:
    labels = list(AAR_ADMIN) + [finance.AAR_MAP[k] for k in finance.AAR_MAP]
    keys = ["laestab", "la", "urn", "name", "period_months", "trust_type", "trust", "date_joined", "pupils", "teachers_fte",
            "phase", "fsm_pct"] + list(finance.AAR_MAP)
    for key, label in rename.items():
        labels[keys.index(key)] = label
    return labels


def aar_row(urn=140001, income=5000000, spend=4800000, reserve=600000, trust="Trust A", joined=None, months=12, pupils=900) -> list:
    money = {"total_income": income, "total_expenditure": spend, "in_year_balance": income - spend, "revenue_reserve": reserve,
             "revenue_reserve_incl_trust_share": reserve + 1000}
    base = [f"204{urn % 10000:04d}", 204, urn, f"Academy {urn}", months, "Multi Academy Trust (MAT)", trust, joined, pupils, 55.5,
            "Secondary", 18.0]
    return base + [money.get(k, 2000) for k in finance.AAR_MAP]


def aar_code_row(width: int, **codes) -> list:
    row = [None] * width
    for i, code in codes.items():
        row[int(i)] = code
    return row


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cfr_file(self, rows, name="CFR_2024-25_Full_Data_Workbook.xlsx", sheet="CFR Data", lead_rows=()):
        return make_xlsx(self.dir / name, [("Guidance", [["How to use this workbook"]]), (sheet, list(lead_rows) + rows)])

    def aar_file(self, rows, name="AAR_2024-25_download.xlsx", sheet="Academies", lead_rows=()):
        return make_xlsx(self.dir / name, [("Index", [["Contents"]]), (sheet, list(lead_rows) + rows), ("Central Services", [["x"]])])


# ----------------------------------------------------------------- offline tests

class HeaderDetectionTest(FixtureTest):
    def test_header_found_below_two_title_rows(self):
        # Arrange
        titles = [["School level total income and expenditure data 2018-2019 (£)"], ["Source: CFR"]]
        path = self.cfr_file([cfr_header(), cfr_row(100001)], name="CFR_2018-19_Full_Data_Workbook.xlsx",
                             sheet="CFR_Output", lead_rows=titles)
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(info["header_row"], 2)
        self.assertEqual(info["sheet"], "CFR_Output")
        self.assertEqual([r["urn"] for r in rows], ["100001"])
        self.assertEqual(rows[0]["total_income"], 1000000)

    def test_sheet_name_matching_ignores_case_underscores_and_spaces(self):
        # Arrange
        names = [("CFR Data", "CFR"), ("CFR_Output", "CFR"), ("CFRData", "CFR"), ("CFR_Data", "CFR"),
                 ("Academies", "AAR"), ("Academies 2018 to 19", "AAR")]
        # Act / Assert
        for name, source in names:
            self.assertEqual(fh.pick_sheet(["Guidance", "Central Services", name], source), name)
        with self.assertRaises(ValueError):
            fh.pick_sheet(["Guidance", "Central Services"], "AAR")


class AarCodeRowTest(FixtureTest):
    def test_formula_note_and_blank_label_resolved_via_code_row(self):
        # Arrange: descriptive cell for the in-year balance is a formula note; the
        # revenue reserve descriptive cell is blank but the code row says BAB030.
        header = aar_header(in_year_balance="= total income - total expenditure", revenue_reserve="")
        iyb_col = header.index("= total income - total expenditure")
        rr_col = header.index("")
        codes = aar_code_row(len(header), **{str(rr_col): "BAB030", str(iyb_col): "= total income - total expenditure"})
        path = self.aar_file([header, aar_row(140001, income=5000000, spend=4800000, reserve=777000)], lead_rows=[codes])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(rows[0]["in_year_balance"], 200000)
        self.assertEqual(rows[0]["revenue_reserve"], 777000)
        self.assertNotIn("derived", rows[0])
        self.assertIn("formula note", info["mapping"]["in_year_balance"])
        self.assertIn("BAB030", info["mapping"]["revenue_reserve"])

    def test_title_row_above_code_row_still_finds_header(self):
        # Arrange: 2018-19 layout: title, code row, descriptive header.
        header = aar_header()
        codes = aar_code_row(len(header), **{str(header.index("Revenue Reserve")): "BAB030"})
        path = self.aar_file([header, aar_row()], name="AAR_2018-19_download.xlsx", sheet="Academies 2018 to 19",
                             lead_rows=[["Benchmarking Return (Accounts Return) for year ending 31st August 2019"], codes])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(info["header_row"], 2)
        self.assertEqual(info["sheet"], "Academies 2018 to 19")
        self.assertEqual(len(rows), 1)


class AliasDriftTest(FixtureTest):
    def test_cfr_2025_26_labels(self):
        # Arrange
        header = cfr_header(total_income="Total Income: I01:I17 - E30", pupils="No pupils (including dual registrations)",
                            in_year_balance="In-year Balance: Total Income (I01:I17 - E30) - Total Expenditure (E01:E29 + E31 + E32)")
        path = self.cfr_file([header, cfr_row(100002, income=2222222, pupils=431)], name="CFR_2025-26_Full_Data_Workbook.xlsx")
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(info["mapping"]["total_income"], "Total Income: I01:I17 - E30")
        self.assertEqual(info["mapping"]["pupils"], "No pupils (including dual registrations)")
        self.assertEqual(rows[0]["total_income"], 2222222)
        self.assertEqual(rows[0]["pupils"], 431)
        self.assertNotIn("derived", rows[0])

    def test_cfr_2018_19_labels_and_e30_harmonisation(self):
        # Arrange: old totals include E30, so a non-zero E30 is subtracted from both totals.
        header = cfr_header(total_income="Total Income", total_expenditure="Total Expenditure",
                            revenue_reserve="Revenue Reserve: B01 plus B02 plus B06", pupils="No Pupils",
                            teachers_fte="No Teachers", period_months="Period covered by return (months)",
                            federated="Federation Y/S/N", grant_funding="Grant Funding", self_generated="Self Generated Funding",
                            in_year_balance="In-year Balance: Total Income (I01 to I18) minus Total Expenditure (E01 to E32)",
                            teaching_staff="E01 Teaching Staff", education_support_staff="E03 Education support staff",
                            supply_staff="Supply Staff", other_staff_costs="Other Staff Costs", total_staff="Staff Total",
                            premises="Premises", occupation="Occupation", catering="Catering Exp",
                            educational_supplies="Educational Supplies", supplies_services="Supplies and Services",
                            bought_in_services="Brought in Professional Sevices")
        header.append("E30 Direct revenue financing (revenue contributions to capital)")
        lead = cfr_row(100003, income=1000000, spend=900000, dns="0", federated="Y") + [25000]
        plain = cfr_row(100004, income=1000000, spend=900000, dns="0", federated="N") + [0]
        path = self.cfr_file([header, lead, plain], name="CFR_2018-19_Full_Data_Workbook.xlsx")
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        by_urn = {r["urn"]: r for r in rows}
        self.assertEqual(by_urn["100003"]["total_income"], 975000)
        self.assertEqual(by_urn["100003"]["total_expenditure"], 875000)
        self.assertEqual(by_urn["100003"]["in_year_balance"], 100000)
        self.assertEqual(by_urn["100003"]["derived"], ["total_income", "total_expenditure"])
        self.assertEqual(by_urn["100003"]["federated"], "Lead school")
        self.assertEqual(by_urn["100004"]["total_income"], 1000000)
        self.assertNotIn("derived", by_urn["100004"])
        self.assertEqual(by_urn["100004"]["federated"], "No")
        self.assertEqual(info["mapping"]["premises"], "Premises")
        self.assertEqual(info["mapping"]["total_staff"], "Staff Total")

    def test_aar_2023_24_pupils_label(self):
        # Arrange
        header = aar_header(pupils="Number of pupils in academy (FTE)", trust_type="MAT/SAT",
                            revenue_reserve_incl_trust_share="Share of Revenue Reserve, distributed on per pupil basis")
        path = self.aar_file([header, aar_row(140002, reserve=500000, pupils=1234)], name="AAR_2023-24_download.xlsx")
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(info["mapping"]["pupils"], "Number of pupils in academy (FTE)")
        self.assertEqual(rows[0]["pupils"], 1234)
        self.assertEqual(rows[0]["trust_type"], "Multi Academy Trust (MAT)")
        # The combined column is absent, so reserve + share is derived from the share column.
        self.assertEqual(rows[0]["revenue_reserve_incl_trust_share"], 500000 + 501000)
        self.assertEqual(rows[0]["derived"], ["revenue_reserve_incl_trust_share"])

    def test_optional_key_missing_is_warned_not_fatal(self):
        # Arrange
        header = aar_header()
        header[header.index("Energy")] = "Something unrelated"
        path = self.aar_file([header, aar_row()])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertIsNone(rows[0]["energy"])
        self.assertIsNone(rows[0]["pupil_premium"])
        self.assertTrue(any("'energy'" in w for w in info["warnings"]))
        self.assertTrue(any("'pupil_premium'" in w for w in info["warnings"]))


class DerivedBalanceTest(FixtureTest):
    def test_in_year_balance_derived_when_column_absent(self):
        # Arrange
        header = cfr_header()
        iyb = header.index(finance.CFR_MAP["in_year_balance"])
        row = cfr_row(100005, income=1500000, spend=1400000)
        del header[iyb], row[iyb]
        path = self.cfr_file([header, row])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(rows[0]["in_year_balance"], 100000)
        self.assertEqual(rows[0]["derived"], ["in_year_balance"])
        self.assertNotIn("in_year_balance", info["mapping"])


class LoudFailureTest(FixtureTest):
    def test_missing_required_keys_listed_with_headers(self):
        # Arrange
        header = cfr_header(revenue_reserve="Balances (see note)", pupils="Pupil count")
        path = self.cfr_file([header, cfr_row()])
        # Act / Assert
        with self.assertRaises(ValueError) as ctx:
            fh.read_workbook(path)
        message = str(ctx.exception)
        self.assertIn("'revenue_reserve'", message)
        self.assertIn("'pupils'", message)
        self.assertNotIn("'total_income'", message.split("Headers seen")[0])
        self.assertIn("Balances (see note)", message)
        self.assertIn("CFR_2024-25_Full_Data_Workbook.xlsx", message)

    def test_no_urn_header_fails(self):
        # Arrange
        path = self.cfr_file([["LA", "School", "Money"], [204, "x", 1]])
        # Act / Assert
        with self.assertRaises(ValueError) as ctx:
            fh.read_workbook(path)
        self.assertIn("URN", str(ctx.exception))


class AcademyMergeTest(FixtureTest):
    def test_two_rows_same_urn_summed_latest_trust_kept(self):
        # Arrange
        rows_in = [aar_header(),
                   aar_row(140003, income=1000000, spend=900000, reserve=100000, trust="Old Trust", joined=44000, months=5),
                   aar_row(140003, income=2000000, spend=1700000, reserve=250000, trust="New Trust", joined=44200, months=7),
                   aar_row(140004, income=3000000, spend=2900000, reserve=10000, trust="Solo Trust")]
        path = self.aar_file(rows_in)
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert
        by_urn = {r["urn"]: r for r in rows}
        self.assertEqual(sorted(by_urn), ["140003", "140004"])
        merged = by_urn["140003"]
        self.assertEqual(merged["total_income"], 3000000)
        self.assertEqual(merged["total_expenditure"], 2600000)
        self.assertEqual(merged["in_year_balance"], 400000)
        self.assertEqual(merged["revenue_reserve"], 350000)
        self.assertEqual(merged["period_months"], 12)
        self.assertEqual(merged["trust"], "New Trust")
        self.assertNotIn("date_joined", merged)
        self.assertEqual(by_urn["140004"]["trust"], "Solo Trust")

    def test_text_join_dates_sort_without_error(self):
        # Arrange
        rows_in = [aar_header(),
                   aar_row(140005, income=100, trust="First", joined="01/09/2019"),
                   aar_row(140005, income=200, trust="Second", joined="01/03/2020")]
        path = self.aar_file(rows_in)
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert
        self.assertEqual(rows[0]["trust"], "Second")
        self.assertEqual(rows[0]["total_income"], 300)


class FederationTest(FixtureTest):
    def test_member_row_kept_with_money_none(self):
        # Arrange
        member = cfr_row(100006, dns="Y", federated="Non returning school", lead=2043358)
        lead = cfr_row(100007, dns="N", federated="Lead school", lead=0)
        path = self.cfr_file([cfr_header(), member, lead])
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert
        by_urn = {r["urn"]: r for r in rows}
        m = by_urn["100006"]
        self.assertTrue(m["did_not_supply"])
        self.assertEqual(m["lead_laestab"], "2043358")
        self.assertEqual(m["federated"], "Non returning school")
        for key in fh.MONEY_KEYS:
            if key in m:
                self.assertIsNone(m[key], key)
        self.assertEqual(m["name"], "School 100006")
        self.assertEqual(m["pupils"], 250)
        self.assertFalse(by_urn["100007"]["did_not_supply"])
        self.assertIsNone(by_urn["100007"]["lead_laestab"])
        self.assertEqual(by_urn["100007"]["total_income"], 1000000)

    def test_2019_20_lead_laestab_taken_from_federation_column(self):
        # Arrange: that year the federation column holds the lead school's LAEstab and the flag reads DNS.
        header = cfr_header(federated="Federated submission (Y/LAEstab/N)")
        del header[header.index("Lead school in federation")]
        member = cfr_row(100008, dns="DNS", federated="8783128")
        del member[11]
        path = self.cfr_file([header, member], name="CFR_2019-20_Full_Data_Workbook.xlsx")
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertTrue(rows[0]["did_not_supply"])
        self.assertEqual(rows[0]["federated"], "Non returning school")
        self.assertEqual(rows[0]["lead_laestab"], "8783128")
        self.assertTrue(any("lead_laestab" in w for w in info["warnings"]))


class YearLabelTest(FixtureTest):
    def test_cfr_and_aar_year_labels(self):
        # Arrange
        cfr = self.cfr_file([cfr_header(), cfr_row(100009)], name="CFR_2018-19_Full_Data_Workbook.xlsx")
        aar = self.aar_file([aar_header(), aar_row(140009)], name="AAR_2018-19_download.xlsx")
        # Act
        cfr_rows, _ = fh.read_workbook(cfr)
        aar_rows, _ = fh.read_workbook(aar)
        # Assert
        self.assertEqual((cfr_rows[0]["year"], cfr_rows[0]["period_end"], cfr_rows[0]["source"]), ("2018-19", "2019-03", "CFR"))
        self.assertEqual((aar_rows[0]["year"], aar_rows[0]["period_end"], aar_rows[0]["source"]), ("2018/19", "2019-08", "AAR"))
        self.assertNotIn("trust", cfr_rows[0])
        self.assertIn("federated", cfr_rows[0])
        self.assertIn("trust", aar_rows[0])
        self.assertNotIn("federated", aar_rows[0])

    def test_row_has_every_shared_format_key(self):
        # Arrange
        path = self.cfr_file([cfr_header(), cfr_row(100010)])
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert
        expected = {"urn", "year", "period_end", "source", "la", "laestab", "name", "phase", "period_months", "pupils",
                    "teachers_fte", "total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "did_not_supply",
                    "federated", "lead_laestab", "fsm_pct", "grant_funding", "self_generated", "sen_funding", "pupil_premium",
                    *finance.EXPENDITURE_KEYS}
        self.assertEqual(set(rows[0]), expected)
        self.assertEqual(rows[0]["la"], 204)
        self.assertEqual(rows[0]["phase"], "primary")
        self.assertIsInstance(rows[0]["urn"], str)
        self.assertIsInstance(rows[0]["laestab"], str)


class LoadHistoryTest(FixtureTest):
    def test_rows_from_all_workbooks_sorted_by_urn_then_period(self):
        # Arrange
        self.cfr_file([cfr_header(), cfr_row(100011), cfr_row(100012)], name="CFR_2024-25_Full_Data_Workbook.xlsx")
        self.cfr_file([cfr_header(), cfr_row(100011)], name="CFR_2023-24_Full_Data_Workbook.xlsx")
        self.aar_file([aar_header(), aar_row(100012)], name="AAR_2024-25_download.xlsx")
        # Act
        rows = fh.load_history(self.dir)
        # Assert
        self.assertEqual([(r["urn"], r["period_end"]) for r in rows],
                         [("100011", "2024-03"), ("100011", "2025-03"), ("100012", "2025-03"), ("100012", "2025-08")])

    def test_env_var_and_argument_select_cache(self):
        # Arrange
        self.cfr_file([cfr_header(), cfr_row(100013)])
        old = os.environ.get("FBIT_CACHE")
        os.environ["FBIT_CACHE"] = str(self.dir)
        try:
            # Act
            rows = fh.load_history()
            # Assert
            self.assertEqual(rows[0]["urn"], "100013")
        finally:
            if old is None:
                os.environ.pop("FBIT_CACHE")
            else:
                os.environ["FBIT_CACHE"] = old
        with self.assertRaises(ValueError):
            fh.load_history(self.dir / "empty")

    def test_main_writes_jsonl_and_report(self):
        # Arrange
        self.cfr_file([cfr_header(), cfr_row(100014, reserve=-5000)])
        out = self.dir / "out" / "finance_history.jsonl"
        rep = self.dir / "report.md"
        # Act
        fh.main(["--cache", str(self.dir), "--out", str(out), "--report", str(rep)])
        # Assert
        lines = out.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn('"urn": "100014"', lines[0])
        text = rep.read_text(encoding="utf-8")
        self.assertIn("CFR_2024-25_Full_Data_Workbook.xlsx", text)
        self.assertIn("revenue_reserve < 0: 1", text)
        self.assertIn("| total_income | `Total Income: I01:I18 - E30` |", text)
        self.assertIn("## Totals", text)


# ----------------------------------------------------------------- real data

_REAL: dict = {}


def real_history() -> list[dict]:
    if "rows" not in _REAL:
        _REAL["rows"] = fh.load_history(REAL_CACHE)
    return _REAL["rows"]


@unittest.skipUnless(HAS_REAL, "real FBIT cache not present")
class RegressionAgainstFinanceTest(unittest.TestCase):
    KEYS = ["total_income", "total_expenditure", "in_year_balance", "revenue_reserve"]

    def test_cfr_2024_25_matches_finance_read_cfr(self):
        # Arrange
        expected, members = finance._read_cfr(REAL_CACHE / "CFR_2024-25_Full_Data_Workbook.xlsx")
        # Act
        rows, _ = fh.read_workbook(REAL_CACHE / "CFR_2024-25_Full_Data_Workbook.xlsx")
        # Assert
        ours = {r["urn"]: r for r in rows if not r["did_not_supply"]}
        theirs = {r["urn"]: r for r in expected}
        self.assertEqual(set(ours), set(theirs))
        for urn, item in theirs.items():
            for key in self.KEYS:
                self.assertEqual(ours[urn][key], item[key], f"{urn} {key}")
        self.assertTrue(set(members) <= {r["urn"] for r in rows if r["did_not_supply"]})

    def test_aar_2024_25_matches_finance_read_aar(self):
        # Arrange
        raw = finance._read_aar(REAL_CACHE / "AAR_2024-25_download.xlsx")
        groups: dict = {}
        for item in raw:
            groups.setdefault(item["urn"], []).append(item)
        theirs = {urn: finance._merge_academy_rows(items) for urn, items in groups.items()}
        # Act
        rows, _ = fh.read_workbook(REAL_CACHE / "AAR_2024-25_download.xlsx")
        # Assert
        ours = {r["urn"]: r for r in rows}
        self.assertEqual(set(ours), set(theirs))
        for urn, item in theirs.items():
            for key in self.KEYS + ["revenue_reserve_incl_trust_share", "period_months"]:
                self.assertEqual(ours[urn][key], item[key], f"{urn} {key}")
            self.assertEqual(ours[urn]["trust"], " ".join(item["trust"].split()), urn)


@unittest.skipUnless(HAS_REAL, "real FBIT cache not present")
class RealDataTest(unittest.TestCase):
    def test_all_fifteen_workbooks_map(self):
        # Arrange / Act
        rows, infos = fh.load_history_with_info(REAL_CACHE)
        _REAL["rows"] = rows
        # Assert
        self.assertEqual(len(infos), 15)
        self.assertEqual(sorted(i["year"] for i in infos if i["source"] == "CFR"),
                         [f"{y}-{str(y + 1)[2:]}" for y in range(2018, 2026)])
        self.assertEqual(sorted(i["year"] for i in infos if i["source"] == "AAR"),
                         [f"{y}/{str(y + 1)[2:]}" for y in range(2018, 2025)])
        for info in infos:
            self.assertTrue(all(k in info["mapping"] for k in fh.REQUIRED), info["file"])
            self.assertIn("in_year_balance", info["mapping"], info["file"])

    def test_william_patten_primary(self):
        # Arrange
        rows = [r for r in real_history() if r["urn"] == "130932"]
        # Act
        by_year = {r["year"]: r for r in rows if r["source"] == "CFR"}
        # Assert
        self.assertEqual(sorted(by_year), [f"{y}-{str(y + 1)[2:]}" for y in range(2018, 2026)])
        self.assertTrue(all(r["la"] == 204 for r in rows))
        reserve = by_year["2019-20"]["revenue_reserve"]
        self.assertTrue(500000 <= reserve <= 600000, reserve)
        self.assertEqual(by_year["2019-20"]["period_end"], "2020-03")
        self.assertIn("William Patten", by_year["2024-25"]["name"])


if __name__ == "__main__":
    unittest.main()
