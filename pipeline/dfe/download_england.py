"""One-off: fetch all-England source files into the cache (CSCP zips + EES CSVs).

Run: uv run python pipeline/dfe/download_england.py [--refresh]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch  # noqa: E402

YEARS = ["2024-2025", "2023-2024", "2022-2023"]

WORKFORCE_PUB = "b318967f-2931-472a-93f2-fbed1e181e6a"
ABSENCE_PUB = "cbbd299f-8297-44bc-92ac-558bcf51f8ad"
EES_FILES = {
    "size_sch": (WORKFORCE_PUB, "Workforce_2010_2025_fte_hc_sch.csv", None),
    "ptr_sch": (WORKFORCE_PUB, "workforce_ptrs_2010_2025_sch.csv", None),
    "pay_sch": (WORKFORCE_PUB, "teacher_pay_school_swc_tps_merged.csv", None),
    "turnover_sch": (WORKFORCE_PUB, "teacher_turnover_2010_2025_sch.csv", None),
    "sickness_sch": (WORKFORCE_PUB, "sickness_absence_teachers_2010_2025_sch.csv", None),
    "ptr_nat": (WORKFORCE_PUB, "workforce_ptrs_2010_2025_nat_reg_la.csv", None),
    "size_nat": (WORKFORCE_PUB, "workforce_2010_2025_fte_hc_nat_reg_la.csv", None),
    "pay_nat": (WORKFORCE_PUB, "workforce_teacher_pay_2010_2025_nat_reg_la.csv", None),
    "sickness_nat": (WORKFORCE_PUB, "sickness_absence_teachers_2010_2025_nat_reg_la.csv", None),
    "absence_nat": (ABSENCE_PUB, "1_Absence_3term_nat_reg_la.csv", "Academic year 2024/25"),
}


def main() -> None:
    refresh = "--refresh" in sys.argv
    for year in YEARS:
        fetch.log(f"CSCP England zip {year}")
        fetch.cscp_england_zip(year, refresh)
    fetch.cscp_meta_zip(YEARS[0], refresh)
    for key, (pub, name, rel) in EES_FILES.items():
        fetch.log(f"EES {key}: {name}")
        fetch.ees_filtered(pub, name, rel, refresh, la_code=None)
    fetch.log("done")


if __name__ == "__main__":
    main()
