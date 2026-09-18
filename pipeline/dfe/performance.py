"""Performance tables (CSCP downloads): KS2, KS4, 16-18, census, absence, destinations.

Each builder returns (per_school: {urn: section}, benchmark: dict).
`years` is newest-first, e.g. ["2024-2025", "2023-2024", "2022-2023"], and
`dirs` maps each year to its extracted CSV folder.
"""

from __future__ import annotations

from pathlib import Path

from values import Section, num, prev_year, read_csv, text, year_label

LA = "204"

# ---------------------------------------------------------------------------
# Labels (short, human readable) for per-school sections and benchmarks.
# ---------------------------------------------------------------------------

KS2_LABELS = {
    "cohort": "Pupils at end of KS2 (eligible)",
    "rwm_expected_pct": "% meeting expected standard in reading, writing & maths",
    "rwm_higher_pct": "% achieving higher standard in reading, writing & maths",
    "reading_expected_pct": "% expected standard in reading",
    "writing_expected_pct": "% expected standard in writing (teacher assessment)",
    "maths_expected_pct": "% expected standard in maths",
    "gps_expected_pct": "% expected standard in grammar, punctuation & spelling",
    "reading_high_pct": "% high score in reading",
    "maths_high_pct": "% high score in maths",
    "writing_greater_depth_pct": "% working at greater depth in writing",
    "reading_scaled_score": "Average scaled score in reading (80-120, 100 = expected)",
    "maths_scaled_score": "Average scaled score in maths (80-120, 100 = expected)",
    "gps_scaled_score": "Average scaled score in GPS (80-120, 100 = expected)",
    "rwm_expected_3yr_pct": "% expected standard RWM, 3-year total",
    "disadvantaged_pct": "% of KS2 cohort who are disadvantaged",
    "progress": "Progress scores (reading/writing/maths) for this year",
    "latest_progress": "Most recent published progress scores (0 = national average)",
    "trend": "Headline results over recent years",
}

KS4_LABELS = {
    "cohort": "Pupils at end of KS4",
    "attainment8": "Attainment 8 score",
    "attainment8_english": "Attainment 8 - English element",
    "attainment8_maths": "Attainment 8 - maths element",
    "eng_maths_5plus_pct": "% grade 5 or above in English & maths GCSEs",
    "eng_maths_4plus_pct": "% grade 4 or above in English & maths GCSEs",
    "ebacc_entry_pct": "% entering the English Baccalaureate",
    "ebacc_aps": "EBacc average point score",
    "ebacc_5plus_pct": "% achieving the EBacc at grade 5+",
    "progress8": "Progress 8 score (0 = national average)",
    "progress8_ci_lower": "Progress 8 lower 95% confidence limit",
    "progress8_ci_upper": "Progress 8 upper 95% confidence limit",
    "progress8_pupils": "Pupils included in Progress 8",
    "progress8_banding": "Progress 8 banding",
    "latest_progress8": "Most recent published Progress 8",
    "disadvantaged_pct": "% of KS4 cohort who are disadvantaged",
    "triple_science_entry_pct": "% entering triple science",
    "trend": "Headline results over recent years",
}

KS5_LABELS = {
    "students_1618": "16-18 students on roll",
    "cohort": "Students at end of 16-18 study",
    "alevel_cohort": "Students entered for A levels",
    "alevel_aps": "A level average point score per entry",
    "alevel_grade": "A level average grade per entry",
    "best3_aps": "Average point score of best 3 A levels",
    "best3_grade": "Average grade of best 3 A levels",
    "aab_2facilitating_pct": "% achieving AAB or better (at least 2 facilitating subjects)",
    "alevel_value_added": "A level progress (value added) score",
    "alevel_va_ci_lower": "A level progress lower 95% confidence limit",
    "alevel_va_ci_upper": "A level progress upper 95% confidence limit",
    "alevel_progress_band": "A level progress band (1 = well above average ... 5 = well below)",
    "academic_cohort": "Students entered for academic qualifications",
    "academic_aps": "Academic average point score per entry",
    "academic_grade": "Academic average grade per entry",
    "applied_general_cohort": "Students entered for applied general qualifications",
    "applied_general_aps": "Applied general average point score per entry",
    "applied_general_grade": "Applied general average grade per entry",
    "tech_level_cohort": "Students entered for tech level qualifications",
    "tech_level_aps": "Tech level average point score per entry",
    "tech_level_grade": "Tech level average grade per entry",
    "alevel_retention_pct": "% of A level core aims retained to the end of study",
    "english_progress": "Progress in English (students without GCSE grade 4)",
    "maths_progress": "Progress in maths (students without GCSE grade 4)",
    "trend": "A level results over recent years",
}

CENSUS_LABELS = {
    "census_date": "School census date",
    "pupils": "Pupils on roll",
    "girls": "Girls on roll",
    "boys": "Boys on roll",
    "girls_pct": "% girls",
    "boys_pct": "% boys",
    "fsm_pct": "% eligible for free school meals (GIAS, latest census)",
    "fsm_ever6_pct": "% eligible for FSM at any time in the past 6 years",
    "fsm_eligible": "Pupils eligible for free school meals",
    "eal_pct": "% with English as an additional language",
    "english_first_language_pct": "% with English as first language",
    "sen_support_pct": "% with SEN support",
    "sen_support": "Pupils with SEN support",
    "ehcp_pct": "% with an education, health and care (EHC) plan",
    "ehcp": "Pupils with an EHC plan",
}

ABSENCE_LABELS = {
    "overall_absence_pct": "Overall absence (% of sessions missed)",
    "persistent_absence_pct": "% of pupils persistently absent (missing 10%+ of sessions)",
    "trend": "Absence over recent years",
}

KS4_DEST_LABELS = {
    "cohort": "Pupils completing KS4",
    "sustained_pct": "% staying in education or employment for 2+ terms",
    "education_pct": "% in sustained education",
    "fe_college_pct": "% at a further education college",
    "school_sixth_form_pct": "% at a state-funded school sixth form",
    "sixth_form_college_pct": "% at a sixth form college",
    "other_education_pct": "% in other education",
    "apprenticeship_pct": "% in apprenticeships",
    "employment_pct": "% in sustained employment",
    "not_sustained_pct": "% not staying in education or employment",
    "unknown_pct": "% activity not captured",
    "trend": "% sustained destination over recent cohorts",
}

KS5_DEST_LABELS = {
    "cohort": "Students completing 16-18 study",
    "sustained_pct": "% staying in education or employment for 2+ terms",
    "education_pct": "% in sustained education",
    "higher_education_pct": "% in higher education (level 4+)",
    "fe_pct": "% in further education (level 3 or below)",
    "other_education_pct": "% in other education",
    "apprenticeship_pct": "% in apprenticeships",
    "employment_pct": "% in sustained employment",
    "not_sustained_pct": "% not staying in education or employment",
    "unknown_pct": "% activity not captured",
}

HE_LABELS = {
    "cohort": "Level 3 students in cohort",
    "progressed_pct": "% progressing to higher education or training by age 19/20",
    "degree_level_pct": "% progressing to degree-level study",
    "top_third_hei_pct": "% progressing to a top-third higher education institution",
    "apprenticeship_pct": "% progressing to a higher/degree apprenticeship",
    "higher_technical_pct": "% progressing to higher technical education",
}


def _rows_by_urn(rows: list[dict]) -> dict[str, dict]:
    return {r["URN"]: r for r in rows if r.get("URN", "").isdigit() and r.get("RECTYPE", "1") in ("1", "2")}


def _record(rows: list[dict], rectype: str) -> dict | None:
    for r in rows:
        if r.get("RECTYPE") == rectype:
            return r
    return None


def _records_by_lea(rows: list[dict], rectype: str) -> dict[str, dict]:
    """LA aggregate rows (one per local authority in an all-England file)."""
    return {r["LEA"]: r for r in rows if r.get("RECTYPE") == rectype and r.get("LEA", "").strip()}


# ---------------------------------------------------------------------------
# Key stage 2
# ---------------------------------------------------------------------------

KS2_NOT_PUBLISHED = {
    "2024/25": "KS2 progress measures are not published for 2024/25: the cohort had no KS1 baseline (KS1 assessments cancelled in 2020/21).",
    "2023/24": "KS2 progress measures are not published for 2023/24: the cohort had no KS1 baseline (KS1 assessments cancelled in 2019/20).",
}


def _suffix(label: str, back: int) -> str:
    """Column suffix for a year `back` years before `label` in that year's file.

    e.g. in the 2024/25 file, 2023/24 values use '_24' and 2022/23 use '_23'.
    """
    return "_" + str(int(label[:4]) + 1 - back)[2:]


def _ks2_progress(r: dict, sfx: str = "") -> dict | None:
    out = {}
    for subject, code in (("reading", "READ"), ("writing", "WRIT"), ("maths", "MAT")):
        score = num(r.get(f"{code}PROG{sfx}"))
        lo = num(r.get(f"{code}PROG_LOWER{sfx}"))
        hi = num(r.get(f"{code}PROG_UPPER{sfx}"))
        out[subject] = score
        out[f"{subject}_ci"] = [lo, hi] if lo is not None and hi is not None else None
    return out if any(v is not None for v in out.values()) else None


def build_ks2(years: list[str], dirs: dict[str, Path], area: str = LA):
    raw = {y: read_csv(dirs[y] / f"{area}_ks2final.csv") for y in years if (dirs[y] / f"{area}_ks2final.csv").exists()}
    tables = {y: _rows_by_urn(rows) for y, rows in raw.items()}
    latest_year = years[0]

    def older_row(label: str, urn: str | None):
        if urn is None:
            return None
        oy = next((y for y in years if year_label(y) == label), None)
        return tables.get(oy, {}).get(urn) if oy else None

    def section_for(r: dict, y: str, urn: str | None) -> dict:
        label = year_label(y)
        sec = Section(year=label)
        sec.num("cohort", r.get("TELIG"))
        sec.num("rwm_expected_pct", r.get("PTRWM_EXP"))
        sec.num("rwm_higher_pct", r.get("PTRWM_HIGH"))
        sec.num("reading_expected_pct", r.get("PTREAD_EXP"))
        sec.num("writing_expected_pct", r.get("PTWRITTA_EXP"))
        sec.num("maths_expected_pct", r.get("PTMAT_EXP"))
        sec.num("gps_expected_pct", r.get("PTGPS_EXP"))
        sec.num("reading_high_pct", r.get("PTREAD_HIGH"))
        sec.num("maths_high_pct", r.get("PTMAT_HIGH"))
        sec.num("writing_greater_depth_pct", r.get("PTWRITTA_HIGH"))
        sec.num("reading_scaled_score", r.get("READ_AVERAGE"))
        sec.num("maths_scaled_score", r.get("MAT_AVERAGE"))
        sec.num("gps_scaled_score", r.get("GPS_AVERAGE"))
        sec.num("rwm_expected_3yr_pct", r.get("PTRWM_EXP_3YR"))
        sec.num("disadvantaged_pct", r.get("PTFSM6CLA1A"))

        progress = _ks2_progress(r)
        sec.set("progress", progress)
        if progress is None and label in KS2_NOT_PUBLISHED:
            sec.set("progress_note", KS2_NOT_PUBLISHED[label])
        # Most recent published progress scores (suffix columns, then older files).
        if progress is None:
            for back in (1, 2):
                yy = prev_year(label, back)
                p = _ks2_progress(r, _suffix(label, back))
                if p is None:
                    o = older_row(yy, urn)
                    p = _ks2_progress(o) if o else None
                if p:
                    sec.set("latest_progress", {"year": yy, **p})
                    break

        # 3-year trend, oldest first
        fields = (("rwm_expected_pct", "PTRWM_EXP"), ("rwm_higher_pct", "PTRWM_HIGH"),
                  ("reading_scaled_score", "READ_AVERAGE"), ("maths_scaled_score", "MAT_AVERAGE"),
                  ("cohort", "TELIG"))
        trend = []
        for back in (2, 1, 0):
            yy = prev_year(label, back)
            sfx = _suffix(label, back) if back else ""
            point = {"year": yy, **{key: num(r.get(col + sfx)) for key, col in fields}}
            o = older_row(yy, urn) if back else None
            if o is not None:
                for key, col in fields:
                    if point[key] is None:
                        point[key] = num(o.get(col))
            if any(v is not None for k, v in point.items() if k != "year"):
                trend.append(point)
        sec.set("trend", trend)
        return sec.out(KS2_LABELS)

    # Schools with results this year, or last year only (e.g. no Year 6 cohort in 2025).
    per_school = {urn: section_for(row, latest_year, urn) for urn, row in tables.get(latest_year, {}).items()}
    for y in years[1:2]:
        for urn, row in tables.get(y, {}).items():
            per_school.setdefault(urn, section_for(row, y, urn))

    latest_rows = raw[latest_year]
    bench = {"year": year_label(latest_year), "labels": KS2_LABELS}
    la_rows = _records_by_lea(latest_rows, "3")
    eng = _record(latest_rows, "5")  # national, state-funded schools
    if la_rows:
        bench["la"] = {lea: section_for(row, latest_year, None) for lea, row in sorted(la_rows.items())}
        for s in bench["la"].values():
            s.pop("labels", None)
    if eng:
        bench["england"] = section_for(eng, latest_year, None)
        bench["england"].pop("labels", None)
    bench["england_basis"] = "State-funded schools"
    return per_school, bench


# ---------------------------------------------------------------------------
# Key stage 4
# ---------------------------------------------------------------------------

P8_NOT_PUBLISHED = {
    "2024/25": "Progress 8 is not published for 2024/25: this cohort had no KS2 test results (KS2 tests cancelled in 2020).",
    "2025/26": "Progress 8 is not published for 2025/26: this cohort had no KS2 test results (KS2 tests cancelled in 2021).",
}


def build_ks4(years: list[str], dirs: dict[str, Path], area: str = LA):
    raw = {y: read_csv(dirs[y] / f"{area}_ks4final.csv") for y in years if (dirs[y] / f"{area}_ks4final.csv").exists()}
    tables = {y: _rows_by_urn(rows) for y, rows in raw.items()}
    latest_year = years[0]

    def older_row(label: str, urn: str | None):
        if urn is None:
            return None
        oy = next((y for y in years if year_label(y) == label), None)
        return tables.get(oy, {}).get(urn) if oy else None

    def section_for(r: dict, y: str, urn: str | None, rectype: str | None = None, lea: str | None = None) -> dict:
        label = year_label(y)
        not_pub = label in P8_NOT_PUBLISHED
        sec = Section(year=label)
        sec.num("cohort", r.get("TPUP"))
        sec.num("attainment8", r.get("ATT8SCR"))
        sec.num("attainment8_english", r.get("ATT8SCRENG"))
        sec.num("attainment8_maths", r.get("ATT8SCRMAT"))
        sec.num("eng_maths_5plus_pct", r.get("PTL2BASICS_95"))
        sec.num("eng_maths_4plus_pct", r.get("PTL2BASICS_94"))
        sec.num("ebacc_entry_pct", r.get("PTEBACC_E_PTQ_EE"))
        sec.num("ebacc_aps", r.get("EBACCAPS"))
        sec.num("ebacc_5plus_pct", r.get("PTEBACC_95"))
        sec.num("triple_science_entry_pct", r.get("PTTRIPLESCI_E"))
        sec.num("disadvantaged_pct", r.get("PTFSM6CLA1A"))
        sec.num("progress8", r.get("P8MEA"), not_published=not_pub)
        sec.num("progress8_ci_lower", r.get("P8CILOW"), not_published=not_pub)
        sec.num("progress8_ci_upper", r.get("P8CIUPP"), not_published=not_pub)
        sec.num("progress8_pupils", r.get("P8PUP"), not_published=not_pub)
        sec.text("progress8_banding", r.get("P8_BANDING"), not_published=not_pub)
        if not_pub:
            sec.set("progress8_note", P8_NOT_PUBLISHED[label])
            prev_label = prev_year(label)
            lp = {
                "year": prev_label,
                "score": num(r.get("P8MEA_PREV")),
                "ci_lower": num(r.get("P8CILOW_PREV")),
                "ci_upper": num(r.get("P8CIUPP_PREV")),
                "pupils": num(r.get("P8PUP_PREV")),
            }
            o = older_row(prev_label, urn)
            if o is not None:
                for key, col in (("score", "P8MEA"), ("ci_lower", "P8CILOW"), ("ci_upper", "P8CIUPP"), ("pupils", "P8PUP")):
                    if lp[key] is None:
                        lp[key] = num(o.get(col))
                lp["banding"] = text(o.get("P8_BANDING"))
            elif rectype is not None:
                prev_y = next((yy for yy in years if year_label(yy) == prev_label), None)
                prev_rows = raw.get(prev_y, []) if prev_y else []
                orow = _records_by_lea(prev_rows, rectype).get(lea) if lea else _record(prev_rows, rectype)
                if orow is not None:
                    lp["banding"] = text(orow.get("P8_BANDING"))
            lp = {k: v for k, v in lp.items() if v is not None}
            if lp.get("score") is not None:
                sec.set("latest_progress8", lp)

        trend = []
        for back, sfx in ((2, "_PREV2"), (1, "_PREV"), (0, "")):
            yy = prev_year(label, back)
            point = {
                "year": yy,
                "progress8": num(r.get("P8MEA" + sfx)),
                "progress8_ci_lower": num(r.get("P8CILOW" + sfx)),
                "progress8_ci_upper": num(r.get("P8CIUPP" + sfx)),
                "attainment8": num(r.get("ATT8SCR" + sfx)),
                "eng_maths_5plus_pct": num(r.get("PTL2BASICS_95" + sfx)),
                "ebacc_aps": num(r.get("EBACCAPS" + sfx)),
            }
            if back:
                o = older_row(yy, urn)
                if o is not None:
                    for key, col in (("progress8", "P8MEA"), ("progress8_ci_lower", "P8CILOW"), ("progress8_ci_upper", "P8CIUPP"),
                                     ("attainment8", "ATT8SCR"), ("eng_maths_5plus_pct", "PTL2BASICS_95"), ("ebacc_aps", "EBACCAPS")):
                        if point[key] is None:
                            point[key] = num(o.get(col))
            if any(v is not None for k, v in point.items() if k != "year"):
                trend.append(point)
        sec.set("trend", trend)
        return sec.out(KS4_LABELS)

    per_school = {}
    for urn, row in tables.get(latest_year, {}).items():
        per_school[urn] = section_for(row, latest_year, urn)
    for y in years[1:2]:  # schools with results last year only (e.g. no 2025 cohort)
        for urn, row in tables.get(y, {}).items():
            per_school.setdefault(urn, section_for(row, y, urn))

    latest_rows = raw[latest_year]
    bench = {"year": year_label(latest_year), "labels": KS4_LABELS, "england_basis": "State-funded schools"}
    la_rows = _records_by_lea(latest_rows, "4")
    if la_rows:
        bench["la"] = {}
        for lea, row in sorted(la_rows.items()):
            s = section_for(row, latest_year, None, rectype="4", lea=lea)
            s.pop("labels", None)
            bench["la"][lea] = s
    row = _record(latest_rows, "7")
    if row:
        s = section_for(row, latest_year, None, rectype="7")
        s.pop("labels", None)
        bench["england"] = s
    return per_school, bench


# ---------------------------------------------------------------------------
# 16 to 18
# ---------------------------------------------------------------------------

def build_ks5(years: list[str], dirs: dict[str, Path], area: str = LA):
    raw = {y: read_csv(dirs[y] / f"{area}_ks5final.csv") for y in years if (dirs[y] / f"{area}_ks5final.csv").exists()}
    tables = {y: _rows_by_urn(rows) for y, rows in raw.items()}
    latest_year = years[0]

    def section_for(r: dict, y: str, urn: str | None) -> dict:
        label = year_label(y)
        sec = Section(year=label)
        sec.num("students_1618", r.get("TPUP1618"))
        sec.num("cohort", r.get("TALLPUP_1618"))
        sec.num("alevel_cohort", r.get("TALLPUP_ALEV_1618"))
        sec.num("alevel_aps", r.get("TALLPPE_ALEV_1618"))
        sec.text("alevel_grade", r.get("TALLPPEGRD_ALEV_1618"))
        sec.num("best3_aps", r.get("TB3PTSE"))
        sec.text("best3_grade", r.get("TB3PTSE_GRD"))
        sec.num("aab_2facilitating_pct", r.get("PTAAB_2FAC"))
        sec.num("alevel_value_added", r.get("VA_INS_ALEV"))
        sec.num("alevel_va_ci_lower", r.get("LCI_INS_ALEV"))
        sec.num("alevel_va_ci_upper", r.get("UCI_INS_ALEV"))
        sec.num("alevel_progress_band", r.get("PROGRESS_BAND_ALEV"))
        sec.num("academic_cohort", r.get("TALLPUP_ACAD_1618"))
        sec.num("academic_aps", r.get("TALLPPE_ACAD_1618"))
        sec.text("academic_grade", r.get("TALLPPEGRD_ACAD_1618"))
        sec.num("applied_general_cohort", r.get("TALLPUP_AGEN"))
        sec.num("applied_general_aps", r.get("TALLPPE_AGEN"))
        sec.text("applied_general_grade", r.get("TALLPPEGRD_AGEN"))
        sec.num("tech_level_cohort", r.get("TALLPUP_TLEV"))
        sec.num("tech_level_aps", r.get("TALLPPE_TLEV"))
        sec.text("tech_level_grade", r.get("TALLPPEGRD_TLEV"))
        sec.num("alevel_retention_pct", r.get("PT_RETAINED_ALEV_RET"))
        sec.num("english_progress", r.get("PROGEX_E"))
        sec.num("maths_progress", r.get("PROGEX_M"))

        trend = []
        for back in (2, 1, 0):
            yy = prev_year(label, back)
            sfx = _suffix(label, back) if back else ""
            point = {
                "year": yy,
                "alevel_aps": num(r.get("TALLPPE_ALEV_1618" + sfx)),
                "alevel_grade": text(r.get("TALLPPEGRD_ALEV_1618" + sfx)),
                "alevel_cohort": num(r.get("TALLPUP_ALEV_1618" + sfx)),
                "alevel_value_added": num(r.get("VA_INS_ALEV" + sfx)),
            }
            if back and urn is not None:
                oy = next((y2 for y2 in years if year_label(y2) == yy), None)
                o = tables.get(oy, {}).get(urn) if oy else None
                if o is not None:
                    for key, col, fn in (("alevel_aps", "TALLPPE_ALEV_1618", num), ("alevel_grade", "TALLPPEGRD_ALEV_1618", text),
                                         ("alevel_cohort", "TALLPUP_ALEV_1618", num), ("alevel_value_added", "VA_INS_ALEV", num)):
                        if point[key] is None:
                            point[key] = fn(o.get(col))
            if any(v is not None for k, v in point.items() if k != "year"):
                trend.append(point)
        sec.set("trend", trend)
        return sec.out(KS5_LABELS)

    per_school = {urn: section_for(row, latest_year, urn) for urn, row in tables.get(latest_year, {}).items()}
    for y in years[1:2]:
        for urn, row in tables.get(y, {}).items():
            per_school.setdefault(urn, section_for(row, y, urn))

    latest_rows = raw[latest_year]
    bench = {
        "year": year_label(latest_year), "labels": KS5_LABELS,
        "england_basis": "england = state-funded schools and colleges; england_all = all schools and colleges (the A level comparator shown on CSCP)",
    }
    la_rows = _records_by_lea(latest_rows, "4")
    if la_rows:
        bench["la"] = {}
        for lea, row in sorted(la_rows.items()):
            s = section_for(row, latest_year, None)
            s.pop("labels", None)
            bench["la"][lea] = s
    for key, rectype in (("england", "7"), ("england_all", "5")):
        row = _record(latest_rows, rectype)
        if row:
            s = section_for(row, latest_year, None)
            s.pop("labels", None)
            bench[key] = s
    return per_school, bench


# ---------------------------------------------------------------------------
# Census (pupil population)
# ---------------------------------------------------------------------------

def _census_section(r: dict, label: str) -> Section:
    sec = Section(year=label, census_date=f"January {label[:2]}{label[5:]}")
    sec.num("pupils", r.get("NOR"))
    sec.num("girls", r.get("NORG"))
    sec.num("boys", r.get("NORB"))
    sec.num("girls_pct", r.get("PNORG"))
    sec.num("boys_pct", r.get("PNORB"))
    sec.num("fsm_eligible", r.get("NUMFSM"))
    # Nursery rows carry 0.00% when the FSM-ever denominator is NA: treat as not applicable.
    if num(r.get("NORFSMEVER")) in (None, 0):
        sec.set("fsm_ever6_pct", None)
    else:
        sec.num("fsm_ever6_pct", r.get("PNUMFSMEVER"))
    sec.num("eal_pct", r.get("PNUMEAL"))
    sec.num("english_first_language_pct", r.get("PNUMENGFL"))
    sec.num("sen_support", r.get("TSENELK"))
    sec.num("sen_support_pct", r.get("PSENELK"))
    sec.num("ehcp", r.get("TSENELSE"))
    sec.num("ehcp_pct", r.get("PSENELSE"))
    return sec


PHASE_CODES = {"PRI": "primary", "SEC": "secondary", "SPE": "special"}


def build_census(years: list[str], dirs: dict[str, Path], gias_fsm: dict[str, tuple], area: str = LA):
    y = years[0]
    rows = read_csv(dirs[y] / f"{area}_census.csv")
    label = year_label(y)
    per_school = {}
    bench = {"year": label, "census_date": f"January {label[:2]}{label[5:]}", "labels": CENSUS_LABELS, "la": {}, "england": {}}
    has_la_rows = any(not r.get("URN", "").isdigit() and r.get("URN") == "LA" for r in rows)
    for r in rows:
        urn = r.get("URN", "")
        if urn.isdigit():
            sec = _census_section(r, label)
            if urn in gias_fsm:
                fsm, date = gias_fsm[urn]
                if fsm is not None:
                    sec.set("fsm_pct", fsm)
                    sec.set("fsm_pct_source", f"GIAS register, census {date}")
            per_school[urn] = sec.out(CENSUS_LABELS)
        elif urn in ("LA", "NAT"):
            # LA rows are column-shifted in the download: phase code sits in ESTAB.
            phase = PHASE_CODES.get(r.get("ESTAB", "").strip())
            if phase:
                if urn == "NAT":
                    target = bench["england"]
                else:
                    # Single-LA files have no LEA column on LA rows; England files do.
                    lea = r.get("LEA", "").strip() or (area if area.isdigit() else "")
                    target = bench["la"].setdefault(lea, {})
                out = _census_section(r, label).out()
                out.pop("year", None)
                out.pop("census_date", None)
                target[phase] = out
    if not has_la_rows:
        # All-England files carry no LA rows: derive LA aggregates from the
        # school rows (verified to match the published LA rows exactly).
        SCHOOLTYPE_PHASE = {
            "State-funded primary": "primary",
            "State-funded secondary": "secondary",
            "State-funded special school": "special",
        }
        groups: dict[tuple, dict] = {}
        for r in rows:
            if not r.get("URN", "").isdigit():
                continue
            phase = SCHOOLTYPE_PHASE.get(r.get("SCHOOLTYPE", "").strip())
            lea = r.get("LA", "").strip()
            if not phase or not lea:
                continue
            g = groups.setdefault((lea, phase), {})
            for col in ("NOR", "NORG", "NORB", "TSENELSE", "TSENELK", "NUMEAL",
                        "NUMENGFL", "NUMFSM", "NUMFSMEVER", "NORFSMEVER"):
                v = num(r.get(col))
                if v is not None:
                    g[col] = g.get(col, 0.0) + v
        for (lea, phase), g in sorted(groups.items()):
            nor = g.get("NOR") or 0
            if not nor:
                continue

            def as_int(v):
                return int(v) if v is not None and v == int(v) else v

            def share(part):
                return round(100.0 * g.get(part, 0.0) / nor, 2) if g.get(part) is not None else None

            ever = round(100.0 * g["NUMFSMEVER"] / g["NORFSMEVER"], 2) if g.get("NUMFSMEVER") is not None and g.get("NORFSMEVER") else None
            bench["la"].setdefault(lea, {})[phase] = {
                "pupils": as_int(g.get("NOR")),
                "girls": as_int(g.get("NORG")),
                "boys": as_int(g.get("NORB")),
                "girls_pct": share("NORG"),
                "boys_pct": share("NORB"),
                "fsm_eligible": as_int(g.get("NUMFSM")),
                "fsm_ever6_pct": ever,
                "eal_pct": share("NUMEAL"),
                "english_first_language_pct": share("NUMENGFL"),
                "sen_support": as_int(g.get("TSENELK")),
                "sen_support_pct": share("TSENELK"),
                "ehcp": as_int(g.get("TSENELSE")),
                "ehcp_pct": share("TSENELSE"),
            }
    return per_school, bench


# ---------------------------------------------------------------------------
# Absence
# ---------------------------------------------------------------------------

def build_absence(years: list[str], dirs: dict[str, Path], ees_rows: list[dict] | None, area: str = LA):
    per_year = {}
    for y in years:
        path = dirs[y] / f"{area}_abs.csv"
        if path.exists():
            per_year[y] = {r["URN"]: r for r in read_csv(path) if r.get("URN", "").isdigit()}
    latest_year = years[0]
    per_school = {}
    for urn in per_year.get(latest_year, {}):
        r = per_year[latest_year][urn]
        sec = Section(year=year_label(latest_year))
        sec.num("overall_absence_pct", r.get("PERCTOT"))
        sec.num("persistent_absence_pct", r.get("PPERSABS10"))
        trend = []
        for y in reversed(years):
            o = per_year.get(y, {}).get(urn)
            if o:
                point = {"year": year_label(y), "overall_absence_pct": num(o.get("PERCTOT")), "persistent_absence_pct": num(o.get("PPERSABS10"))}
                if point["overall_absence_pct"] is not None or point["persistent_absence_pct"] is not None:
                    trend.append(point)
        sec.set("trend", trend)
        per_school[urn] = sec.out(ABSENCE_LABELS)

    label = year_label(latest_year)
    bench = {"year": label, "labels": ABSENCE_LABELS, "la": {}, "england": {}}
    phases = {"State-funded primary": "primary", "State-funded secondary": "secondary", "Special": "special", "Total": "all"}
    period = label.replace("/", "")
    trend_periods = {prev_year(label, n).replace("/", "") for n in (0, 1, 2)}
    trends: dict[tuple, list] = {}
    targets: dict[tuple, dict] = {}
    for r in ees_rows or []:
        phase = phases.get(r.get("education_phase"))
        if not phase or r.get("year_breakdown", "Six half terms") not in ("Six half terms", ""):
            continue
        level = r.get("geographic_level")
        if level == "National":
            key = ("england", phase)
            target = bench["england"]
        elif level == "Local authority":
            code = (r.get("old_la_code") or "").strip()
            if not code:
                continue
            key = ("la", code, phase)
            target = bench["la"].setdefault(code, {})
        else:
            continue
        targets[key] = target
        point = {
            "overall_absence_pct": num(r.get("sess_overall_percent"), 2),
            "persistent_absence_pct": num(r.get("enrolments_pa_10_exact_percent"), 2),
        }
        if r["time_period"] == period:
            target[phase] = dict(point)
        if r["time_period"] in trend_periods:
            trends.setdefault(key, []).append({"year": year_label(r["time_period"]), **point})
    for key, points in trends.items():
        target = targets[key]
        phase = key[-1]
        if phase in target:
            target[phase]["trend"] = sorted(points, key=lambda p: p["year"])
    return per_school, bench


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

def _dest_rows(path: Path):
    rows = read_csv(path)
    schools = {r["URN"]: r for r in rows if r.get("URN", "").isdigit()}
    la = {r["LEA"]: r for r in rows if r.get("RECTYPE") in ("LA", "4") and r.get("LEA", "").strip()}
    nat = next((r for r in rows if r.get("RECTYPE") in ("NAT", "7")), None)
    return schools, la, nat


def _ks4_dest(r: dict, cohort_year: str) -> dict:
    sec = Section(year=cohort_year, note=f"Pupils who finished KS4 in {cohort_year}; destinations sustained in {prev_year(cohort_year, -1)}")
    sec.num("cohort", r.get("COHORT"))
    sec.num("sustained_pct", r.get("OVERALL_DESTPER"))
    sec.num("education_pct", r.get("EDUCATIONPER"))
    sec.num("fe_college_pct", r.get("FEPER"))
    sec.num("school_sixth_form_pct", r.get("SCH_6THPER"))
    sec.num("sixth_form_college_pct", r.get("SIXTH_COLPER"))
    sec.num("other_education_pct", r.get("OTHER_EDUPER"))
    sec.num("apprenticeship_pct", r.get("APPRENPER"))
    sec.num("employment_pct", r.get("EMPLOYMENTPER"))
    sec.num("not_sustained_pct", r.get("NOT_SUSTAINEDPER"))
    sec.num("unknown_pct", r.get("UNKNOWNPER"))
    trend = []
    for back in (2, 1):
        yy = prev_year(cohort_year, back)
        sfx = _suffix(cohort_year, back)
        value = num(r.get("OVERALL_DESTPER" + sfx))
        if value is not None:
            trend.append({"year": yy, "sustained_pct": value, "cohort": num(r.get("COHORT" + sfx))})
    if sec.data.get("sustained_pct") is not None:
        trend.append({"year": cohort_year, "sustained_pct": sec.data["sustained_pct"], "cohort": sec.data.get("cohort")})
    sec.set("trend", trend)
    return sec.out(KS4_DEST_LABELS)


def _ks5_dest(r: dict, cohort_year: str) -> dict:
    sec = Section(year=cohort_year, note=f"Students who finished 16-18 study in {cohort_year}; destinations sustained in {prev_year(cohort_year, -1)}")
    sec.num("cohort", r.get("TOT_COHORT"))
    sec.num("sustained_pct", r.get("TOT_OVERALLPER"))
    sec.num("education_pct", r.get("TOT_EDUCATIONPER"))
    sec.num("higher_education_pct", r.get("TOT_HEPER"))
    sec.num("fe_pct", r.get("TOT_FEPER"))
    sec.num("other_education_pct", r.get("TOT_OTHER_EDUPER"))
    sec.num("apprenticeship_pct", r.get("TOT_APPRENPER"))
    sec.num("employment_pct", r.get("TOT_EMPLOYMENTPER"))
    sec.num("not_sustained_pct", r.get("TOT_NOT_SUSTAINEDPER"))
    sec.num("unknown_pct", r.get("TOT_NOT_CAPTUREDPER"))
    return sec.out(KS5_DEST_LABELS)


def _he(r: dict, cohort_year: str) -> dict:
    sec = Section(year=cohort_year, note=f"Level 3 students who finished 16-18 study in {cohort_year}, tracked for 2 years")
    sec.num("cohort", r.get("ALL_COHORT"))
    sec.num("progressed_pct", r.get("ALL_PROGRESSED"))
    sec.num("degree_level_pct", r.get("ALL_HE"))
    sec.num("top_third_hei_pct", r.get("ALL_TOP3RD"))
    sec.num("apprenticeship_pct", r.get("ALL_APPREN"))
    sec.num("higher_technical_pct", r.get("ALL_HTECH"))
    return sec.out(HE_LABELS)


# Cohort years relative to the performance-table year (verified against EES:
# e.g. the 2024-2025 download holds 2022/23 KS4 & 16-18 leavers and the
# 2021/22 higher-education progression cohort).
DEST_LAG = {"ks4": 2, "ks5": 2, "he": 3}


def build_destinations(years: list[str], dirs: dict[str, Path], area: str = LA):
    y = years[0]
    label = year_label(y)
    per_school: dict[str, dict] = {}
    bench = {"labels": {"ks4": KS4_DEST_LABELS, "ks5": KS5_DEST_LABELS, "he_progression": HE_LABELS}}
    for key, fname, fn in (("ks4", "ks4-pupdest", _ks4_dest), ("ks5", "ks5-studest", _ks5_dest), ("he_progression", "ks5-studest-he", _he)):
        path = dirs[y] / f"{area}_{fname}.csv"
        if not path.exists():
            continue
        lag = DEST_LAG["he" if key == "he_progression" else key]
        cohort_year = prev_year(label, lag)
        schools, la_rows, nat = _dest_rows(path)
        for urn, r in schools.items():
            per_school.setdefault(urn, {})[key] = fn(r, cohort_year)
        entry = {"year": cohort_year}
        if la_rows:
            entry["la"] = {}
            for lea, row in sorted(la_rows.items()):
                s = fn(row, cohort_year)
                for k in ("labels", "year", "note"):
                    s.pop(k, None)
                entry["la"][lea] = s
        if nat is not None:
            s = fn(nat, cohort_year)
            for k in ("labels", "year", "note"):
                s.pop(k, None)
            entry["england"] = s
        bench[key] = entry
    return per_school, bench
