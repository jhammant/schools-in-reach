"""Tests for pipeline/money/deflator.py.

Offline tests read the committed gdp_deflator.json. The real-data test only runs
when the FBIT cache exists and never writes into it.
"""

import unittest
from pathlib import Path

from pipeline.money import deflator

REAL_CACHE = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/dfe/fbit")
HAS_REAL = (REAL_CACHE / "CFR_2019-20_Full_Data_Workbook.xlsx").exists()


class IndexTest(unittest.TestCase):
    def test_base_year_is_100(self):
        # Arrange / Act / Assert
        self.assertEqual(deflator.BASE_YEAR, "2025-26")
        self.assertEqual(deflator.load()["base_year"], deflator.BASE_YEAR)
        self.assertEqual(deflator.index("2025-26", "CFR"), 100.0)

    def test_cfr_year_accepts_both_spellings(self):
        # Arrange
        expected = deflator.load()["financial_years"]["2019-20"]
        # Act / Assert
        self.assertEqual(deflator.index("2019-20", "CFR"), expected)
        self.assertEqual(deflator.index("2019/20", "CFR"), expected)
        self.assertEqual(deflator.index("2019-20"), expected)

    def test_aar_year_accepts_both_spellings_and_uses_academic_table(self):
        # Arrange
        expected = deflator.load()["academic_years"]["2019/20"]
        # Act / Assert
        self.assertEqual(deflator.index("2019/20", "AAR"), expected)
        self.assertEqual(deflator.index("2019-20", "AAR"), expected)
        self.assertNotEqual(deflator.index("2019-20", "AAR"), deflator.index("2019-20", "CFR"))

    def test_unknown_year_raises(self):
        # Arrange / Act / Assert
        with self.assertRaises(KeyError):
            deflator.index("1999-00", "CFR")


class ToRealTest(unittest.TestCase):
    def test_round_trip(self):
        # Arrange
        cash = 543950.0
        idx = deflator.index("2019-20", "CFR")
        # Act
        real = deflator.to_real(cash, "2019-20", "CFR")
        # Assert
        self.assertAlmostEqual(real, cash * 100 / idx, places=6)
        self.assertAlmostEqual(real * idx / 100, cash, places=6)
        self.assertGreater(real, cash)

    def test_base_year_is_identity(self):
        # Arrange / Act / Assert
        self.assertEqual(deflator.to_real(1234.5, "2025-26", "CFR"), 1234.5)

    def test_none_passthrough(self):
        # Arrange / Act / Assert
        self.assertIsNone(deflator.to_real(None, "2019-20", "CFR"))
        self.assertIsNone(deflator.to_real(None, "2019/20", "AAR"))

    def test_real_label(self):
        # Arrange / Act / Assert
        self.assertEqual(deflator.real_label(), "in 2025-26 prices (HM Treasury GDP deflator, October 2026)")


@unittest.skipUnless(HAS_REAL, "real FBIT cache not present")
class RealDataTest(unittest.TestCase):
    def test_william_patten_2019_20_reserve_in_todays_prices(self):
        # Arrange
        from pipeline.dfe import finance_history as fh
        rows, _ = fh.read_workbook(REAL_CACHE / "CFR_2019-20_Full_Data_Workbook.xlsx")
        row = next(r for r in rows if r["urn"] == "130932")
        # Act
        reserve = row["revenue_reserve"]
        real = deflator.to_real(reserve, row["year"], row["source"])
        # Assert
        self.assertTrue(543900 <= reserve <= 544000, reserve)
        self.assertAlmostEqual(real, reserve * 100 / 78.3047, places=6)
        self.assertGreater(real, reserve)


if __name__ == "__main__":
    unittest.main()
