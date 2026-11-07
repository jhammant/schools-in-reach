"""Tests for pipeline/dfe/finance_history.py.

Offline tests build tiny xlsx workbooks in a temp dir (hand-written sheet xml
through the real xlsx.iter_rows). Real-data tests only run when the FBIT cache
exists and never write into it.
"""

import json
import os
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from pipeline.dfe import finance, finance_history as fh
from pipeline.money import build_money

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

    def test_code_row_resolves_trailing_blank_descriptive_cell(self):
        # Arrange: the reserve column's descriptive cell is blank and last, so the header row
        # as read is one cell shorter than the code row that names it BAB030.
        header = ["URN", "LA", "Overall Phase", "Period covered by return", "No Pupils",
                  "Total Income", "Total Expenditure", None]
        codes = aar_code_row(8, **{"7": "BAB030"})
        data = [140001, 204, "Primary", 12, 300, 2000000, 1950000, 150000]
        path = self.aar_file([codes, header, data], name="AAR_2023-24_download.xlsx")
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(rows[0]["revenue_reserve"], 150000)
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
        self.assertEqual(by_urn["100003"]["adjusted"], ["total_income", "total_expenditure"])
        self.assertNotIn("adjusted", by_urn["100004"])
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
        # The distributed column pools the whole trust's reserve (academies included), so it is
        # neither the combined 2024-25 measure nor something to add to the school's own reserve.
        self.assertIsNone(rows[0]["revenue_reserve_incl_trust_share"])
        self.assertNotIn("derived", rows[0])
        self.assertEqual(info["mapping"]["whole_trust_reserve_share"], "Share of Revenue Reserve, distributed on per pupil basis")
        self.assertTrue(any("already contains this school's reserve" in w for w in info["warnings"]))

    def test_whole_trust_distributed_reserve_is_not_added_to_school_reserve(self):
        # Arrange: a single-academy trust with no central reserve; the 2021-22..2023-24 code row
        # spells out that the distributed column is (CS RR + sum of academy RR) spread per pupil.
        header = aar_header(pupils="Number of pupils in academy (FTE)", trust_type="MAT/SAT",
                            revenue_reserve_incl_trust_share="Share of Revenue Reserve, distributed on per pupil basis")
        share_col = header.index("Share of Revenue Reserve, distributed on per pupil basis")
        codes = aar_code_row(len(header), **{str(share_col): "(CS RR+ Sum of Acad RR / total pupils in Trust * Pupils in Acad)"})
        row = aar_row(140010, reserve=150000)
        row[share_col] = 150000
        path = self.aar_file([codes, header, row], name="AAR_2023-24_download.xlsx")
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert: the reserve a consumer picks is the school's own 150000, not 300000.
        self.assertEqual(rows[0]["revenue_reserve"], 150000)
        self.assertIsNone(rows[0]["revenue_reserve_incl_trust_share"])
        self.assertEqual(build_money.reserve_of(rows[0]), 150000)

    def test_central_services_share_is_added_when_combined_column_absent(self):
        # Arrange: the 2024-25 central-only share label, but no 'RR + share of CS RR' column.
        header = aar_header(revenue_reserve_incl_trust_share=(
            "Share of Central Services Revenue Reserve, distributed on per pupil basis, at end of period based on time spent in trust"))
        path = self.aar_file([header, aar_row(140011, reserve=500000)])
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert: aar_row puts reserve + 1000 in that column, so the derived total is reserve + share.
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
        header = aar_header() + ["Donations and/or voluntary funds"]
        codes = aar_code_row(len(header), **{str(len(header) - 1): "BAI140"})
        rows_in = [header,
                   aar_row(140003, income=1000000, spend=900000, reserve=100000, trust="Old Trust", joined=44000, months=5) + [1500],
                   aar_row(140003, income=2000000, spend=1700000, reserve=250000, trust="New Trust", joined=44200, months=7) + [2500],
                   aar_row(140004, income=3000000, spend=2900000, reserve=10000, trust="Solo Trust") + [700]]
        path = self.aar_file(rows_in, lead_rows=[codes])
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
        # Detail keys and lines sum across the two rows too.
        self.assertEqual(merged["donations_revenue"], 4000)
        self.assertEqual(merged["lines"]["bai140"], 4000)
        self.assertEqual(by_urn["140004"]["donations_revenue"], 700)
        self.assertEqual(by_urn["140004"]["lines"], {"bai140": 700})

    def test_mixed_excel_serial_and_text_join_dates_share_one_epoch(self):
        # Arrange: an earlier textual date and a later Excel serial for the same academy.
        later_serial = (date(2024, 3, 1) - date(1899, 12, 30)).days
        rows_in = [aar_header(),
                   aar_row(140006, income=1000000, trust="Old Trust", joined="01/09/2023", months=6, pupils=300),
                   aar_row(140006, income=1100000, trust="New Trust", joined=later_serial, months=6, pupils=310)]
        path = self.aar_file(rows_in, name="AAR_2023-24_download.xlsx")
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_income"], 2100000)
        self.assertEqual(rows[0]["trust"], "New Trust")
        self.assertEqual(rows[0]["pupils"], 310)

    def test_sort_date_converts_text_to_excel_serial(self):
        # Arrange / Act / Assert: 2024-03-01 is Excel serial 45352 whichever way it is written.
        self.assertEqual(fh._sort_date("01/03/2024"), 45352)
        self.assertEqual(fh._sort_date("2024-03-01"), 45352)
        self.assertEqual(fh._sort_date(45352), 45352)
        self.assertEqual(fh._sort_date("n/a"), 0)
        self.assertEqual(fh._sort_date(None), 0)

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
                    *finance.EXPENDITURE_KEYS, *fh.NEW_KEYS, "lines"}
        self.assertEqual(set(rows[0]), expected)
        self.assertEqual(list(rows[0])[-len(fh.NEW_KEYS) - 1:], fh.NEW_KEYS + ["lines"])
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



class NewKeysTest(FixtureTest):
    def test_cfr_detail_keys_lines_and_copies(self):
        # Arrange: 2024-25 CFR with the detail columns and a run of line columns, incl. the a/b totals.
        header = cfr_header() + ["% of pupils with EHCP", "Number of pupils in 6th form", "I13 Donations and/or private funds",
                                 "CI03 Voluntary or private income", "I08a Income from lettings",
                                 "I08b Income from facilities and services", "I08a/b Total income from facilities and services",
                                 "I17 Community focused school facilities income", "I09 Income from catering",
                                 "I18 Total additional grant for schools", "I18c Income from the £1bn COVID-19 catch-up package",
                                 "I01/2 Total pre and Post-16 Funding", "E20A Connectivity", "E20G IT support",
                                 "E28a/b Total bought in professional services", "OB01 Opening pupil-focused revenue balance",
                                 "B07 Outstanding balance on capital loans to school"]
        extra = [3.5, 120, 15000, 2500, 8000, 4000, 12000, 500, 30000, 7000, 7000, 999999, 1100, 1200, 2800, 50000, 0]
        path = self.cfr_file([header, cfr_row(100020, pupils=400) + extra, cfr_row(100021, pupils=300) + extra])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        r = rows[0]
        self.assertEqual(r["ehcp_pct"], 3.5)
        self.assertEqual(r["sixth_form_pupils"], 120)
        self.assertEqual(r["donations_revenue"], 15000)
        self.assertEqual(r["donations_capital"], 2500)
        self.assertEqual(r["lettings_income"], 8000)
        self.assertEqual(r["facilities_income"], 12000)
        self.assertEqual(r["community_facilities_income"], 500)
        self.assertEqual(r["catering_income"], 30000)
        self.assertEqual(r["cfr_additional_grants_i18"], 7000)
        self.assertIsNone(r["teacher_pension_ni_grants"])
        self.assertIsNone(r["aar_other_dfe_revenue_grants"])
        self.assertIsNone(r["company_number"])
        self.assertIsNone(r["trust_central_pupils"])
        self.assertEqual(r["grant_funding_government"], r["grant_funding"])
        self.assertEqual(r["self_generated_income"], r["self_generated"])
        self.assertEqual(r["total_staff_costs"], r["total_staff"])
        self.assertEqual(r["teaching_staff_costs"], r["teaching_staff"])
        self.assertEqual(r["education_support_staff_costs"], r["education_support_staff"])
        self.assertEqual(info["mapping"]["self_generated_income"], "= self_generated")
        # 'Teaching Staff E01' is a derived column, not a line, so there is no E01 in this fixture.
        self.assertEqual(r["lines"], {"I03": 1000, "I05": 1000, "E05": 1000, "E04": 1000, "E06": 1000, "E16": 1000,
                                      "I13": 15000, "I08a": 8000, "I08b": 4000, "I08": 12000, "I17": 500, "I09": 30000,
                                      "I18": 7000, "I18c": 7000, "E20A": 1100, "E20G": 1200, "E28": 2800, "OB01": 50000, "B07": 0})
        self.assertNotIn("adjusted", r)
        self.assertNotIn("suspect", r)
        for code in r["lines"]:
            self.assertIn(code, fh.LINE_LABELS, code)
        self.assertEqual(fh.LINE_LABELS["E20A"], "Connectivity")
        self.assertEqual(info["lines"]["E28"], "E28a/b Total bought in professional services")

    def test_cfr_line_code_rules(self):
        # Arrange / Act / Assert
        self.assertEqual(fh.cfr_line_code("I18a Income from the Coronavirus Job Retention Scheme"), "I18a")
        self.assertEqual(fh.cfr_line_code("E20E Laptops, desktops and tablets"), "E20E")
        self.assertEqual(fh.cfr_line_code("OB02 Opening community-focused revenue balance"), "OB02")
        self.assertEqual(fh.cfr_line_code("I08a/b Total income from facilities and services"), "I08")
        self.assertIsNone(fh.cfr_line_code("I01/2 Total pre and Post-16 Funding"))
        self.assertIsNone(fh.cfr_line_code("CI03 Voluntary or private income"))
        self.assertIsNone(fh.cfr_line_code("Teaching Staff E01"))
        self.assertIsNone(fh.cfr_line_code("Revenue Reserve: B01 + B02 + B06"))
        for code in fh.CFR_LINE_LABELS:
            self.assertTrue(fh.LINE_LABELS[code])

    def test_sixth_form_column_all_zero_is_suspect(self):
        # Arrange: 2024-25 CFR carries the column but every school reads 0.
        header = cfr_header() + ["Number of pupils in 6th form"]
        path = self.cfr_file([header, cfr_row(100022) + [0], cfr_row(100023) + [0]])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        for r in rows:
            self.assertIsNone(r["sixth_form_pupils"])
            self.assertEqual(r["suspect"], ["sixth_form_pupils"])
        self.assertTrue(any("sixth_form_pupils column is zero" in w for w in info["warnings"]))

    def test_did_not_supply_nulls_detail_keys_and_lines(self):
        # Arrange
        header = cfr_header() + ["I13 Donations and/or private funds"]
        path = self.cfr_file([header, cfr_row(100024, dns="Y", federated="Non returning school", lead=2043358) + [900]])
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert
        self.assertIsNone(rows[0]["donations_revenue"])
        self.assertIsNone(rows[0]["grant_funding_government"])
        self.assertIsNone(rows[0]["self_generated_income"])
        self.assertEqual(rows[0]["lines"], {})

    def test_aar_government_grants_facilities_sum_suspect_fsm_and_trust_central(self):
        # Arrange: 2024-25 AAR layout: no facilities total, lettings BAI100 + other BAI101 under a code row,
        # a company number joined to the Central Services sheet, and one school with FSM 646.2%.
        header = aar_header() + ["Company Number", "Non-Government", "Academies", "Income from rentals and lettings",
                                 "Income from facilities and services - other", "Donations and/or voluntary funds",
                                 "Other DfE Revenue Grants", "% of pupils with EHCP", "No of pupils in 6th form", "Energy"]
        base = len(aar_header())
        codes = aar_code_row(len(header), **{str(base + 3): "BAI100", str(base + 4): "BAI101", str(base + 5): "BAI140",
                                             str(base + 6): "BAI040", str(base + 9): "BAE150"})
        # The canonical 'Energy' column has no code; the appended duplicate under BAE150 becomes the line.
        good = aar_row(140020, pupils=1000) + [7595434, 30000, 20000, 5000, 1500, 9000, 11000, 2.5, 80, 123]
        bad = aar_row(140021, pupils=500) + [7595434, 0, 0, 0, 0, 0, 0, 1.0, 0, 456]
        bad[aar_header().index("% of pupils eligible for FSM")] = 646.2
        central = [["MAT SAT or Central Services", "Company Number", "Company Name", "Total number of Pupils", "Total Expenditure"],
                   ["Central services", 7595434, "Trust A", 1500, 300000]]
        path = make_xlsx(self.dir / "AAR_2024-25_download.xlsx",
                         [("Index", [["Contents"]]), ("Academies", [codes, header, good, bad]), ("Central Services", central)])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        by_urn = {r["urn"]: r for r in rows}
        g, b = by_urn["140020"], by_urn["140021"]
        self.assertEqual(g["non_government_grants"], 30000)
        self.assertEqual(g["income_from_academies"], 20000)
        self.assertEqual(g["grant_funding_government"], g["grant_funding"] - 50000)
        self.assertEqual(g["lettings_income"], 5000)
        self.assertEqual(g["facilities_income"], 6500)
        self.assertIn("facilities_income", g["derived"])
        self.assertEqual(g["donations_revenue"], 9000)
        self.assertIsNone(g["donations_capital"])
        self.assertEqual(g["aar_other_dfe_revenue_grants"], 11000)
        self.assertEqual(g["ehcp_pct"], 2.5)
        self.assertEqual(g["company_number"], "07595434")
        self.assertEqual(g["trust_central_total_expenditure"], 300000)
        self.assertEqual(g["trust_central_pupils"], 1500)
        self.assertEqual(g["trust_central_spend_per_pupil"], 200)
        self.assertEqual(g["lines"]["bai100"], 5000)
        self.assertEqual(g["lines"]["bai101"], 1500)
        self.assertEqual(g["lines"]["bai140"], 9000)
        self.assertEqual(g["lines"]["bai040"], 11000)
        self.assertEqual(g["lines"]["bae150"], 123)
        self.assertNotIn("suspect", g)
        self.assertEqual(b["fsm_pct"], 646.2)
        self.assertEqual(b["suspect"], ["fsm_pct"])
        self.assertEqual(b["sixth_form_pupils"], 0)
        self.assertEqual(g["sixth_form_pupils"], 80)
        self.assertTrue(any("fsm_pct above 100%" in w for w in info["warnings"]))
        self.assertEqual(info["central"]["trusts"], 1)
        self.assertTrue(any("trust_central_spend_per_pupil derived" in w for w in info["warnings"]))

    def test_aar_without_central_sheet_warns_and_translates_old_codes(self):
        # Arrange: a 2019-20 style workbook with BNCH codes above the header and no central-services sheet.
        header = aar_header() + ["Non- Government", "Academies", "Income from facilities and services",
                                 "Building and Grounds maintenance and improvement", "Coronavirus Government Funding"]
        base = len(aar_header())
        codes = aar_code_row(len(header), **{str(base): "BNCH11163", str(base + 1): "BNCH11162", str(base + 2): "BNCH11201",
                                             str(base + 3): "BNCH21301 & BNCH21405", str(base + 4): "BNCHBAI061",
                                             str(header.index("Energy")): "BNCH21403"})
        row = aar_row(140030) + [1000, 2000, 3000, 4000, 5000]
        path = make_xlsx(self.dir / "AAR_2019-20_download.xlsx", [("Index", [["x"]]), ("Academies", [codes, header, row])])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        r = rows[0]
        self.assertEqual(r["facilities_income"], 3000)
        self.assertIsNone(r["lettings_income"])
        self.assertEqual(r["lines"]["bai090"], 1000)
        self.assertEqual(r["lines"]["bai080"], 2000)
        self.assertEqual(r["lines"]["income_from_facilities_and_services"], 3000)
        self.assertEqual(r["lines"]["building_and_grounds_maintenance"], 4000)
        self.assertEqual(r["lines"]["bai061"], 5000)
        self.assertEqual(r["lines"]["bae150"], 2000)
        self.assertIsNone(r["trust_central_total_expenditure"])
        self.assertTrue(any("no central-services sheet" in w for w in info["warnings"]))
        self.assertIn("bai061", fh.LINE_LABELS)

    def test_aar_line_key_rules(self):
        # Arrange / Act / Assert
        self.assertEqual(fh.aar_line_key("Teaching staff", "BAE010"), "bae010")
        self.assertEqual(fh.aar_line_key("Teaching staff", "BNCH21101"), "bae010")
        self.assertEqual(fh.aar_line_key("Direct revenue financing", "BAE290 (is -ve income)"), "bae290")
        self.assertEqual(fh.aar_line_key("Direct revenue financing", "BNCH21707 (is -ve income)"), "bae290")
        self.assertEqual(fh.aar_line_key("Pre-16 DFE/EFA Revenue grants", "BNCH11110T & BNCH11131"), "bai010")
        self.assertEqual(fh.aar_line_key("DFE/EFA Revenue grants (includes Coronavirus Government Funding", "BNCH11110T, BNCHBAI061 & BNCH11131"), "bai010")
        self.assertEqual(fh.aar_line_key("of which: Coronavirus Government Funding", "BAI061"), "bai061")
        self.assertEqual(fh.aar_line_key("All income from facilities and services", "BAI100_x000D_ BAI101"), "income_from_facilities_and_services")
        self.assertIsNone(fh.aar_line_key("Total Income", "BAI050 BAI010 BAI020"))
        self.assertIsNone(fh.aar_line_key("Revenue Reserve", "BNCH44001"))
        self.assertIsNone(fh.aar_line_key("URN", ""))
        for key in fh.AAR_LINE_LABELS:
            self.assertTrue(fh.LINE_LABELS[key])

    def test_report_lists_new_key_coverage_and_flags(self):
        # Arrange
        header = cfr_header() + ["Number of pupils in 6th form", "I13 Donations and/or private funds"]
        self.cfr_file([header, cfr_row(100040) + [0, 500]])
        rows, infos = fh.load_history_with_info(self.dir)
        # Act
        text = fh.report(rows, infos)
        # Assert
        self.assertIn("## New keys: rows with a value per workbook", text)
        self.assertIn("## Adjusted and suspect flags", text)
        self.assertIn("| suspect | sixth_form_pupils | 1 |", text)
        self.assertIn("| donations_revenue | 1 |", text)
        self.assertIn("| I13 | `I13 Donations and/or private funds` |", text)
        self.assertIn("| self_generated_income | `= self_generated` |", text)
        self.assertEqual(text, fh.report(rows, infos))


def _put(header: list, row: list, label: str, value) -> None:
    """Set the cell under `label` in a fixture row."""
    row[header.index(label)] = value


# William Patten's real 2024-25 learning-resource lines: E19, E20A..E20G and E21 (E20D is admin software).
E19_E21 = ["E19 Learning resources (not ICT equipment)", "E20A Connectivity", "E20B Onsite servers",
           "E20C IT learning resources", "E20D Administration software and systems", "E20E Laptops, desktops and tablets",
           "E20F Other hardware", "E20G IT support", "E21 Exam fees"]
WP_E19_E21 = [112121, 6698, 0, 973, 10211, 12008, 3764, 11761, 0]
SUPPLY_LINES = ["E02 Supply teaching staff", "E10 Supply teacher insurance", "E26 Agency supply teaching staff"]


class GoldFixesTest(FixtureTest):
    def test_cfr_supply_staff_is_e02_plus_e26_with_e10_kept_apart(self):
        # Arrange: the workbook column is E02 + E10 + E26 = 300 + 200 + 500.
        header = cfr_header() + SUPPLY_LINES
        row = cfr_row(100050) + [300, 200, 500]
        _put(header, row, "Supply Staff: E02 + E10 + E26", 1000)
        path = self.cfr_file([header, row])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(rows[0]["supply_staff"], 800)
        self.assertEqual(rows[0]["supply_insurance"], 200)
        self.assertNotIn("adjusted", rows[0])
        self.assertEqual(info["mapping"]["supply_insurance"], "= line E10")
        self.assertIn("E02 + E26", info["mapping"]["supply_staff"])
        self.assertTrue(any("supply_insurance" in w for w in info["warnings"]))

    def test_cfr_supply_staff_falls_back_to_column_less_e10_then_unknown(self):
        # Arrange: one workbook has only the E10 line; another has no supply lines at all.
        header = cfr_header() + ["E10 Supply teacher insurance"]
        row = cfr_row(100051) + [200]
        _put(header, row, "Supply Staff: E02 + E10 + E26", 1000)
        with_e10 = self.cfr_file([header, row])
        without = self.cfr_file([cfr_header(), cfr_row(100052)], name="CFR_2023-24_Full_Data_Workbook.xlsx")
        # Act
        rows, _ = fh.read_workbook(with_e10)
        bare, info = fh.read_workbook(without)
        # Assert: a mixed figure is never passed off as supply staff.
        self.assertEqual((rows[0]["supply_staff"], rows[0]["supply_insurance"]), (800, 200))
        self.assertIsNone(bare[0]["supply_staff"])
        self.assertIsNone(bare[0]["supply_insurance"])
        self.assertTrue(any("supply_staff null in 1 workbook rows" in w for w in info["warnings"]))

    def test_aar_supply_insurance_stays_out_of_supply_staff(self):
        # Arrange: the academies' 'Supply Staff Costs' column is bae020 + bae240 + bae100 in every real workbook.
        header = aar_header() + ["Supply teaching staff", "Agency supply teaching staff", "Supply teacher insurance"]
        base = len(aar_header())
        codes = aar_code_row(len(header), **{str(base): "BAE020", str(base + 1): "BAE240", str(base + 2): "BAE100"})
        row = aar_row(140050) + [600, 300, 100]
        _put(header, row, "Supply Staff Costs", 1000)
        path = self.aar_file([codes, header, row])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(rows[0]["supply_staff"], 900)
        self.assertEqual(rows[0]["supply_insurance"], 100)
        self.assertEqual(info["mapping"]["supply_insurance"], "= line bae100")

    def test_cfr_2024_25_educational_supplies_leaves_out_e20d(self):
        # Arrange: William Patten's 2024-25 lines; the column (157,536) counts E20D admin software (10,211).
        header = cfr_header() + E19_E21
        wp = cfr_row(130932) + WP_E19_E21
        _put(header, wp, "Educational Supplies: (E19:E21)", 157536)
        no_admin_software = cfr_row(100053) + [5000, 100, 0, 0, 0, 400, 0, 0, 500]
        _put(header, no_admin_software, "Educational Supplies: (E19:E21)", 6000)
        path = self.cfr_file([header, wp, no_admin_software])
        # Act
        rows, info = fh.read_workbook(path)
        # Assert: 147,325 is the 2025-26 and FBIT basis that the gold file gives.
        by_urn = {r["urn"]: r for r in rows}
        self.assertEqual(by_urn["130932"]["educational_supplies"], 147325)
        self.assertEqual(by_urn["130932"]["adjusted"], ["educational_supplies"])
        self.assertEqual(by_urn["130932"]["derived"], ["educational_supplies"])
        self.assertEqual(by_urn["100053"]["educational_supplies"], 6000)
        self.assertNotIn("adjusted", by_urn["100053"])
        self.assertTrue(any("E19 + (E20 - E20D) + E21 in 1 rows" in w for w in info["warnings"]))

    def test_cfr_2025_26_column_already_leaves_out_e20d_and_other_grants_move_to_i06(self):
        # Arrange: 2025-26 labels; no I18 line, the pension and NI grants sit in I06.
        header = cfr_header(total_income="Total Income: I01:I17 - E30",
                            educational_supplies="Educational Supplies: (E19:E20C) + (E20E:E21)")
        header += E19_E21 + ["I06 Other government grants"]
        row = cfr_row(130932) + WP_E19_E21 + [96016]
        _put(header, row, "Educational Supplies: (E19:E20C) + (E20E:E21)", 147325)
        path = self.cfr_file([header, row], name="CFR_2025-26_Full_Data_Workbook.xlsx")
        # Act
        rows, info = fh.read_workbook(path)
        # Assert
        self.assertEqual(rows[0]["educational_supplies"], 147325)
        self.assertNotIn("adjusted", rows[0])
        self.assertIsNone(rows[0]["cfr_additional_grants_i18"])
        self.assertEqual(rows[0]["other_dfe_grants"], 96016)
        self.assertEqual(info["mapping"]["other_dfe_grants"], "= line I06")
        self.assertTrue(any("cannot be separated out" in w for w in info["warnings"]))

    def test_other_dfe_grants_is_i18_then_aar_other_dfe_revenue_grants(self):
        # Arrange: up to 2024-25 the container is I18 (I06 is a different line then).
        cfr = cfr_header() + ["I06 Other government grants", "I18 Total additional grant for schools"]
        cfr_path = self.cfr_file([cfr, cfr_row(100054) + [0, 200455]])
        aar = aar_header() + ["Other DfE Revenue Grants"]
        aar_path = self.aar_file([aar, aar_row(140054) + [11000]])
        # Act
        cfr_rows, cfr_info = fh.read_workbook(cfr_path)
        aar_rows, aar_info = fh.read_workbook(aar_path)
        # Assert
        self.assertEqual(cfr_rows[0]["other_dfe_grants"], 200455)
        self.assertEqual(cfr_info["mapping"]["other_dfe_grants"], "= cfr_additional_grants_i18")
        self.assertEqual(aar_rows[0]["other_dfe_grants"], 11000)
        self.assertEqual(aar_info["mapping"]["other_dfe_grants"], "= aar_other_dfe_revenue_grants")

    def test_merged_academy_sums_the_line_derived_keys(self):
        # Arrange: a trust change mid-year gives two rows for one academy.
        header = aar_header() + ["Supply teaching staff", "Agency supply teaching staff", "Supply teacher insurance",
                                 "Other DfE Revenue Grants"]
        base = len(aar_header())
        codes = aar_code_row(len(header), **{str(base): "BAE020", str(base + 1): "BAE240", str(base + 2): "BAE100"})
        first = aar_row(140055, trust="Old Trust", joined=44000, months=5) + [100, 50, 10, 1000]
        second = aar_row(140055, trust="New Trust", joined=44200, months=7) + [200, 70, 20, 3000]
        path = self.aar_file([codes, header, first, second])
        # Act
        rows, _ = fh.read_workbook(path)
        # Assert
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["supply_staff"], 420)
        self.assertEqual(rows[0]["supply_insurance"], 30)
        self.assertEqual(rows[0]["other_dfe_grants"], 4000)

    def test_report_shows_the_line_derived_keys(self):
        # Arrange
        header = cfr_header() + SUPPLY_LINES + ["I18 Total additional grant for schools"]
        self.cfr_file([header, cfr_row(100056) + [300, 200, 500, 7000]])
        rows, infos = fh.load_history_with_info(self.dir)
        # Act
        text = fh.report(rows, infos)
        # Assert
        self.assertIn("| supply_insurance | `= line E10` |", text)
        self.assertIn("| other_dfe_grants | `= cfr_additional_grants_i18` |", text)
        self.assertIn("| other_dfe_grants | 1 |", text)


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
        lines = by_year["2019-20"]["lines"]
        self.assertAlmostEqual(lines["B01"] + lines["B02"] + lines["B06"], reserve, delta=1)  # the reserve is rounded to the pound
        self.assertEqual(by_year["2019-20"]["adjusted"], ["total_income", "total_expenditure"])
        self.assertEqual(by_year["2019-20"]["donations_revenue"], lines["I13"])
        self.assertIsNone(by_year["2024-25"]["sixth_form_pupils"])
        self.assertIn("sixth_form_pupils", by_year["2024-25"]["suspect"])
        self.assertEqual(by_year["2024-25"]["grant_funding_government"], by_year["2024-25"]["grant_funding"])

    def test_new_keys_populated_across_real_workbooks(self):
        # Arrange
        rows = real_history()
        aar = [r for r in rows if r["source"] == "AAR"]
        cfr = [r for r in rows if r["source"] == "CFR" and not r["did_not_supply"]]
        # Act
        aar_2425 = [r for r in aar if r["year"] == "2024/25"]
        aar_2223 = [r for r in aar if r["year"] == "2022/23"]
        # Assert: detail keys, the government-only grant figure, trust-central join and the known-bad FSM year.
        self.assertTrue(all(r["ehcp_pct"] is not None for r in cfr[:200]))
        self.assertTrue(all(r["donations_revenue"] is not None for r in cfr if r["year"] == "2024-25"))
        self.assertTrue(all(r["donations_capital"] is None for r in aar))
        self.assertTrue(all(r["company_number"] for r in aar_2425))
        self.assertGreater(sum(1 for r in aar_2425 if r["trust_central_total_expenditure"] is not None), 0.9 * len(aar_2425))
        self.assertTrue(all(r["facilities_income"] is not None for r in aar_2425 if r["lettings_income"] is not None))
        # Negative non-government or inter-academy income (refunds) can push the government-only figure above the total.
        with_grants = [r for r in aar if r["grant_funding"] is not None]
        self.assertTrue(all(r["grant_funding_government"] == r["grant_funding"] - (r["non_government_grants"] or 0)
                            - (r["income_from_academies"] or 0) for r in with_grants))
        self.assertGreater(sum(1 for r in with_grants if r["grant_funding_government"] < r["grant_funding"]), len(with_grants) / 2)
        self.assertTrue(any("fsm_pct" in r.get("suspect", []) for r in aar_2223))
        self.assertTrue(all("fsm_pct" in r.get("suspect", []) for r in rows if (r["fsm_pct"] or 0) > 100))
        self.assertTrue(all("bae010" in r["lines"] and "bai030" in r["lines"] for r in aar))
        self.assertTrue(all("E01" in r["lines"] and "B01" in r["lines"] for r in cfr))


REAL_HISTORY = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/dfe/finance_history.jsonl")
GOLD = Path(__file__).resolve().parents[1] / "money" / "data" / "gold" / "130932.json"


def william_patten_rows() -> dict[str, dict]:
    """William Patten's CFR rows by year: from finance_history.jsonl (rows start with the urn), else the workbooks."""
    if "wp" not in _REAL:
        rows = []
        if REAL_HISTORY.exists():
            with open(REAL_HISTORY, encoding="utf-8") as fh_in:
                rows = [json.loads(line) for line in fh_in if line.startswith('{"urn": "130932"')]
        else:
            for year in ("2019-20", "2024-25", "2025-26"):
                part, _ = fh.read_workbook(REAL_CACHE / f"CFR_{year}_Full_Data_Workbook.xlsx")
                rows += [r for r in part if r["urn"] == "130932"]
        _REAL["wp"] = {r["year"]: r for r in rows if r["source"] == "CFR"}
    return _REAL["wp"]


@unittest.skipUnless(REAL_HISTORY.exists() or HAS_REAL, "neither finance_history.jsonl nor the FBIT cache is present")
class WilliamPattenAnchorTest(unittest.TestCase):
    def test_reserves_and_pupils(self):
        # Arrange / Act
        rows = william_patten_rows()
        # Assert
        self.assertEqual(rows["2019-20"]["revenue_reserve"], 543908)
        self.assertEqual(rows["2025-26"]["revenue_reserve"], -210901)
        self.assertEqual(rows["2024-25"]["pupils"], 437.5)


@unittest.skipUnless(REAL_HISTORY.exists(), "finance_history.jsonl not present")
class GoldFinanceHistoryTest(unittest.TestCase):
    def setUp(self):
        self.gold = json.loads(GOLD.read_text(encoding="utf-8"))
        self.rows = william_patten_rows()

    def lines(self, year: str) -> dict:
        found = {code: v["value"] for code, v in self.gold["years"][year]["lines"].items()}
        found.update({code: v["value"] for code, v in self.gold["years"][year].get("subtotal_lines", {}).items()})
        return found

    def test_every_gold_pipeline_value_matches(self):
        # Arrange
        expected = {year: y["totals"]["pipeline_finance_history"] for year, y in self.gold["years"].items()}
        # Act / Assert
        self.assertEqual(sorted(self.rows), sorted(expected))
        for year, values in expected.items():
            for key, value in values.items():
                self.assertEqual(self.rows[year][key], value, f"{year} {key}")

    def test_only_2019_20_totals_differ_from_the_workbook_by_e30(self):
        # Arrange: the documented adjustment takes E30 direct revenue financing out of both 2019-20 totals.
        differences = {(year, key): check for year, y in self.gold["years"].items()
                       for key, check in y["totals"]["pipeline_vs_workbook"].items() if not check["match"]}
        # Act
        e30 = self.lines("2019-20")["E30"]
        # Assert
        self.assertEqual(sorted(differences), [("2019-20", "total_expenditure"), ("2019-20", "total_income")])
        for (year, key), check in differences.items():
            self.assertEqual(check["workbook"] - check["pipeline"], e30)
            self.assertEqual(self.rows[year][key], check["pipeline"])
        self.assertEqual(self.rows["2019-20"]["adjusted"], ["total_income", "total_expenditure"])

    def test_supply_staff_and_educational_supplies_follow_fbit(self):
        # Arrange / Act / Assert: E02 + E26 every year, E10 apart; 2024-25 learning resources without E20D.
        for year, row in self.rows.items():
            lines = self.lines(year)
            self.assertEqual(row["supply_staff"], lines["E02"] + lines["E26"], year)
            self.assertEqual(row["supply_insurance"], lines["E10"], year)
        self.assertEqual(self.rows["2025-26"]["supply_staff"], 82434)
        self.assertEqual(self.rows["2024-25"]["educational_supplies"], 147325)
        self.assertIn("educational_supplies", self.rows["2024-25"]["adjusted"])

    def test_other_dfe_grants_is_the_container_line(self):
        # Arrange / Act / Assert: I18 up to 2024-25, I06 in 2025-26.
        for year, row in self.rows.items():
            lines = self.lines(year)
            expected = lines["I06"] if year == "2025-26" else lines["I18"]
            self.assertEqual(row["other_dfe_grants"], expected, year)


if __name__ == "__main__":
    unittest.main()
