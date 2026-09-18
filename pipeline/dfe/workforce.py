"""School workforce (EES 'School workforce in England' school-level files)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from values import Section, num, pct, year_label

WORKFORCE_LABELS = {
    "census_date": "School workforce census date",
    "teachers_fte": "Teachers (FTE)",
    "qualified_teachers_fte": "Qualified teachers (FTE)",
    "teachers_without_qts_fte": "Teachers without qualified teacher status (FTE)",
    "leadership_teachers_fte": "Leadership teachers - head, deputy, assistant (FTE)",
    "teaching_assistants_fte": "Teaching assistants (FTE)",
    "support_staff_fte": "All support staff (FTE)",
    "other_support_staff_fte": "Support staff other than teaching assistants (FTE)",
    "workforce_fte": "Total school workforce (FTE)",
    "pupils_fte": "Pupils (FTE)",
    "pupil_teacher_ratio": "Pupils per teacher (qualified and unqualified)",
    "pupil_adult_ratio": "Pupils per adult (teachers + teaching assistants)",
    "average_teacher_salary": "Mean gross teacher salary (£)",
    "salary_year": "Year of salary figure",
    "teacher_turnover": "Teachers leaving the school by the following November",
    "teacher_sickness": "Teacher sickness absence",
    "turnover_pct": "% of teachers (FTE) who left the school",
    "left_state_sector_pct": "% of teachers (FTE) who left state-funded schools",
    "moved_school_pct": "% of teachers (FTE) who moved to another state-funded school",
    "taking_absence_pct": "% of teachers taking sickness absence",
    "days_per_teacher": "Average sickness days per teacher (all teachers)",
    "days_per_absent_teacher": "Average sickness days per teacher who took absence",
}


def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _latest_by_urn(rows: list[dict]) -> tuple[str, dict[str, dict]]:
    latest = max(r["time_period"] for r in rows if r.get("geographic_level", "School") == "School")
    return latest, {r["school_urn"]: r for r in rows if r["time_period"] == latest and r.get("school_urn")}


def build_workforce(files: dict[str, tuple[Path, Path | None, dict]]):
    size_period, size = _latest_by_urn(_load(files["size_sch"][0]))
    ptr_period, ptr = _latest_by_urn(_load(files["ptr_sch"][0]))
    pay_period, pay = _latest_by_urn(_load(files["pay_sch"][0]))
    turn_period, turnover = _latest_by_urn(_load(files["turnover_sch"][0]))
    sick_period, sickness = _latest_by_urn(_load(files["sickness_sch"][0]))

    label = year_label(size_period)
    census = f"November {label[:4]}"
    per_school = {}
    for urn in set(size) | set(ptr) | set(pay) | set(turnover) | set(sickness):
        sec = Section(year=label, census_date=census)
        s = size.get(urn, {})
        p = ptr.get(urn, {})
        sec.num("teachers_fte", s.get("fte_all_teachers") or p.get("teachers_fte"))
        sec.num("qualified_teachers_fte", p.get("qualified_teachers_fte"))
        sec.num("teachers_without_qts_fte", s.get("fte_all_teachers_without_qts"))
        sec.num("leadership_teachers_fte", s.get("fte_leadership_teachers"))
        sec.num("teaching_assistants_fte", s.get("fte_teaching_assistants"))
        support = sec.num("support_staff_fte", s.get("fte_all_support_staff"))
        tas = sec.data.get("teaching_assistants_fte")
        sec.set("other_support_staff_fte", round(support - tas, 2) if support is not None and tas is not None else None)
        sec.num("workforce_fte", s.get("fte_workforce"))
        sec.num("pupils_fte", p.get("pupils_fte"))
        sec.num("pupil_teacher_ratio", p.get("pupil_to_qual_unqual_teacher_ratio"))
        sec.num("pupil_adult_ratio", p.get("pupil_to_adult_ratio"))
        if urn in pay:
            sec.num("average_teacher_salary", pay[urn].get("average_mean"), 0)
            sec.set("salary_year", year_label(pay_period))

        t = turnover.get(urn)
        if t:
            fte = num(t.get("teacher_fte_in_census_year"))
            left_sys = num(t.get("left_the_state_funded_system"))
            moved = num(t.get("left_to_another_state_funded_school"))
            left = (left_sys or 0) + (moved or 0) if left_sys is not None or moved is not None else None
            sec.set("teacher_turnover", {
                "year": year_label(turn_period),
                "teachers_fte": fte,
                "turnover_pct": pct(left, fte),
                "left_state_sector_pct": pct(left_sys, fte),
                "moved_school_pct": pct(moved, fte),
            })
        k = sickness.get(urn)
        if k:
            sec.set("teacher_sickness", {
                "year": year_label(sick_period),
                "taking_absence_pct": num(k.get("percentage_taking_absence")),
                "days_per_teacher": num(k.get("average_number_of_days_all_teachers")),
                "days_per_absent_teacher": num(k.get("average_number_of_days_taken")),
            })
        per_school[urn] = sec.out(WORKFORCE_LABELS)

    bench = _benchmarks(files, label, census, pay_period, turn_period, sick_period)
    return per_school, bench


GROUPS = {
    "Total state-funded schools": "all",
    "State-funded nursery and primary": "primary",
    "State-funded secondary": "secondary",
    "State-funded special or PRU": "special",
}


def _area(row: dict) -> tuple[str, str | None] | None:
    level = row.get("geographic_level")
    if level == "National":
        return ("england", None)
    code = (row.get("old_la_code") or "").strip()
    if level == "Local authority" and code:
        return ("la", code)
    return None


def _bench_target(bench: dict, area: tuple[str, str | None]) -> dict:
    kind, code = area
    if kind == "england":
        return bench["england"]
    return bench["la"].setdefault(code, {g: {} for g in GROUPS.values()})


def _benchmarks(files, label, census, pay_period, turn_period, sick_period) -> dict:
    bench = {
        "year": label,
        "census_date": census,
        "labels": WORKFORCE_LABELS,
        "la": {},
        "england": {g: {} for g in GROUPS.values()},
    }
    period = label.replace("/", "")
    for row in _load(files["ptr_nat"][0]):
        area, group = _area(row), GROUPS.get(row.get("establishment_type_group"))
        if area and group and row["time_period"] == period:
            target = _bench_target(bench, area)[group]
            target["pupil_teacher_ratio"] = num(row.get("pupil_to_qual_unqual_teacher_ratio"))
            target["pupil_adult_ratio"] = num(row.get("pupil_to_adult_ratio"))
            target["schools"] = num(row.get("number_schools"))
    for row in _load(files["size_nat"][0]):
        area, group = _area(row), GROUPS.get(row.get("establishment_type_group"))
        if area and group and row["time_period"] == period:
            target = _bench_target(bench, area)[group]
            schools = num(row.get("number_schools"))
            teachers = num(row.get("fte_all_teachers"))
            tas = num(row.get("fte_teaching_assistants"))
            support = num(row.get("fte_all_support_staff"))
            target["teachers_fte_per_school"] = round(teachers / schools, 1) if teachers and schools else None
            target["teaching_assistants_fte_per_school"] = round(tas / schools, 1) if tas and schools else None
            target["support_staff_fte_per_school"] = round(support / schools, 1) if support and schools else None
            target["teachers_without_qts_pct"] = pct(num(row.get("fte_all_teachers_without_qts")), teachers)
    for row in _load(files["pay_nat"][0]):
        area, group = _area(row), GROUPS.get(row.get("establishment_type_group"))
        if (area and group and row["time_period"] == pay_period and row.get("grade") == "Total"
                and row.get("sex") == "Total" and row.get("age_category") == "Total"):
            _bench_target(bench, area)[group]["average_teacher_salary"] = num(row.get("average_mean"), 0)
    for row in _load(files["sickness_nat"][0]):
        area, group = _area(row), GROUPS.get(row.get("school_type"))
        if area and group and row["time_period"] == sick_period:
            _bench_target(bench, area)[group]["teacher_sickness"] = {
                "year": year_label(sick_period),
                "taking_absence_pct": num(row.get("percentage_taking_absence")),
                "days_per_teacher": num(row.get("average_number_of_days_all_teachers")),
                "days_per_absent_teacher": num(row.get("average_number_of_days_taken")),
            }

    # Turnover: no LA/national file, so sum school-level FTE counts.
    def turnover_entry(fte, left_sys, moved, schools):
        return {
            "year": year_label(turn_period),
            "schools": schools,
            "turnover_pct": pct(left_sys + moved, fte),
            "left_state_sector_pct": pct(left_sys, fte),
            "moved_school_pct": pct(moved, fte),
            "method": "Sum of school-level FTE counts (schools with no suppressed values)",
        }

    per_la: dict[str, list] = {}
    for row in _load(files["turnover_sch"][0]):
        if row["time_period"] != turn_period:
            continue
        vals = [num(row.get(c)) for c in ("teacher_fte_in_census_year", "left_the_state_funded_system", "left_to_another_state_funded_school")]
        if None in vals:
            continue
        code = (row.get("old_la_code") or (row.get("school_laestab") or "")[:3]).strip()
        if not code:
            continue
        acc = per_la.setdefault(code, [0.0, 0.0, 0.0, 0])
        acc[0] += vals[0]; acc[1] += vals[1]; acc[2] += vals[2]; acc[3] += 1
    for code, (fte, left_sys, moved, n) in sorted(per_la.items()):
        _bench_target(bench, ("la", code))["all"]["teacher_turnover"] = turnover_entry(fte, left_sys, moved, n)
    sums_path = files["turnover_sch"][1]
    if sums_path:
        sums = json.loads(Path(sums_path).read_text()).get(turn_period)
        if sums:
            bench["england"]["all"]["teacher_turnover"] = turnover_entry(
                sums["teacher_fte_in_census_year"], sums["left_the_state_funded_system"],
                sums["left_to_another_state_funded_school"], int(sums["_rows"]))
    return bench
