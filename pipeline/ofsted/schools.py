"""ofsted.json: latest and previous Ofsted inspection outcomes for every English school,
split into one file per local authority.

Sources (gov.uk statistical data sets, OGL v3.0), covering all of England:
  * State-funded schools inspections and outcomes: management information
      - latest monthly "latest inspections as at" CSV (renewed-framework report
        cards, latest EIF graded inspection, latest ungraded inspection)
      - pinned final pre-renewal snapshot "latest inspections as at 31 Aug 2025"
        (latest graded inspection of any framework + previous graded inspection)
  * Non-association independent schools inspections and outcomes: MI
      - latest "most recent inspections data" CSV and "additional inspections" CSV
      - pinned "most recent inspections data as at 31 July 2025" (previous
        standard inspection)
Association independent schools are inspected by ISI; they get a link only.

report_url is derived from the GIAS establishment type (and phase), not looked up
per school: reports.ofsted.gov.uk provider pages are at /provider/<category>/<urn>,
and the category depends only on the kind of establishment. The mapping below was
found by sampling reports.ofsted.gov.uk/search for one or more open English schools
of every TypeOfEstablishment/PhaseOfEducation combination (60+ schools checked; see
build.py --verify output for the HTTP 200 hit-rate sample). It is null for the small
number of types with no separate Ofsted provider page (Miscellaneous, Sixth form
centres, Secure units, Academy secure 16 to 19) and for ISI-inspected independent
schools (which get isi_url/isi_search_url instead).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from util import (OGL, REPORTS, cached_attachment, clean, gias_open_all, govuk_attachments,
                  iso, la_code_for_name, log, pick_attachment, prune, read_csv, to_int)

STATE_SLUG = "monthly-management-information-ofsteds-school-inspections-outcomes"
IND_SLUG = "non-association-independent-schools-inspections-and-outcomes-management-information"

STATE_FINAL_OEIF_AS_AT = date(2025, 8, 31)
IND_FINAL_OEIF_AS_AT = date(2025, 7, 31)

ISI_SEARCH = "https://www.isi.net/reports/"
# Resolved once by browsing https://www.isi.net/reports/ (the search is client-side).
ISI_PAGES = {
    "131343": "https://www.isi.net/institutions/school/the-lyceum-8939",
    "132791": "https://www.isi.net/institutions/school/rosemary-works-school-8833",
    "147296": "https://www.isi.net/institutions/school/beis-rochel-d-satmar-school-9804",
}

GRADE_WORDS = {"1": "Outstanding", "2": "Good", "3": "Requires improvement", "4": "Inadequate"}
CONCERN = {
    "SM": "Special measures",
    "SWK": "Serious weaknesses",
    "RSI": "Requires significant improvement",
}

FRAMEWORKS = {
    "REIF": "Renewed education inspection framework: report card with a grade for each evaluation area "
            "(state-funded schools inspected from 10 November 2025; non-association independent schools "
            "from 26 January 2026). Grades: Exceptional, Strong standard, Expected standard, Needs attention, "
            "Urgent improvement; safeguarding standards Met / Not met.",
    "EIF": "Education inspection framework (September 2019 to November 2025). Graded inspections carried out "
           "from September 2024 have no single-word overall effectiveness grade ('Not judged').",
    "CIF": "Common inspection framework (September 2015 to August 2019).",
    "pre-2015": "Section 5 inspection framework in use before September 2015.",
}

REIF_AREAS = [
    ("safeguarding_standards", "Safeguarding standards"),
    ("inclusion", "Inclusion"),
    ("curriculum_and_teaching", "Curriculum and teaching"),
    ("achievement", "Achievement"),
    ("attendance_and_behaviour", "Attendance and behaviour"),
    ("personal_development_and_wellbeing", "Personal development and wellbeing"),
    ("early_years", "Early years (where applicable)"),
    ("post_16", "Post-16 provision (where applicable)"),
    ("leadership_and_governance", "Leadership and governance"),
]
REIF_DATE_COLS = {
    "safeguarding_standards": "Safeguarding standards - date of grade",
    "inclusion": "Inclusion - date of grade",
    "curriculum_and_teaching": "Curriculum and teaching - date of grade",
    "achievement": "Achievement - date of grade",
    "attendance_and_behaviour": "Attendance and behaviour - date of grade",
    "personal_development_and_wellbeing": "Personal development and wellbeing - date of grade",
    "early_years": "Early years - date of grade",
    "post_16": "Post-16 provision - date of grade",
    "leadership_and_governance": "Leadership and governance - date of grade",
}


def framework_for(d: str | None) -> str | None:
    if not d:
        return None
    if d >= "2025-11-10":
        return "REIF"
    if d >= "2019-09-01":
        return "EIF"
    if d >= "2015-09-01":
        return "CIF"
    return "pre-2015"


def eif_framework(d: str | None) -> str | None:
    """Framework label for a graded/ungraded (pre-report-card) inspection."""
    if d and d >= "2019-09-01":
        return "EIF"
    return framework_for(d)


def grade(v: str | None) -> str | None:
    v = clean(v)
    if v is None or v in ("9", "0"):
        return None
    return GRADE_WORDS.get(v, v)


def yes_no(v: str | None) -> bool | None:
    v = clean(v)
    return {"Yes": True, "No": False}.get(v) if v else None


def concern(v: str | None) -> str | None:
    v = clean(v)
    return CONCERN.get(v, v) if v else None


def predecessor(current_urn: str, urn_at_time: str | None) -> str | None:
    u = clean(urn_at_time)
    return u if u and u != current_urn else None


# GIAS TypeOfEstablishment (name) -> reports.ofsted.gov.uk provider category, for types whose
# category does not depend on phase.
AP_TYPES = {"Pupil referral unit", "Academy alternative provision converter",
            "Academy alternative provision sponsor led", "Free schools alternative provision"}
SPECIAL_TYPES = {"Community special school", "Foundation special school", "Academy special converter",
                  "Academy special sponsor led", "Free schools special", "Non-maintained special school"}
POST16_ACADEMY_TYPES = {"Academy 16-19 converter", "Academy 16 to 19 sponsor led", "Free schools 16 to 19"}
# No separate Ofsted provider page found for these types in the sample search.
UNMAPPED_TYPES = {"Academy secure 16 to 19", "Secure units", "Miscellaneous", "Sixth form centres"}
# GIAS PhaseOfEducation (name) -> category, for the mainstream types (community/voluntary/foundation
# schools, academies, free schools, studio schools, university technical colleges).
MAINSTREAM_PHASE_CATEGORY = {
    "Primary": "21", "Middle deemed primary": "21",
    "Secondary": "23", "Middle deemed secondary": "23",
    "All-through": "28",
}


def report_category(est_type: str | None, phase: str | None, inspectorate: str | None) -> str | None:
    """reports.ofsted.gov.uk provider-page category for a GIAS establishment, or None if unmapped."""
    t = est_type or ""
    if "independent" in t.lower():
        return "27" if inspectorate == "Ofsted" else None  # ISI-inspected: no Ofsted provider page
    if t in AP_TYPES:
        return "22"
    if t in SPECIAL_TYPES:
        return "25"
    if t == "Local authority nursery school":
        return "20"
    if t == "Further education":
        return "31"
    if t == "Higher education institutions":
        return "43"
    if t == "Special post 16 institution":
        return "39"
    if t in POST16_ACADEMY_TYPES:
        return "46"
    if t in UNMAPPED_TYPES:
        return None
    if t == "City technology college":
        return "23"
    if phase in MAINSTREAM_PHASE_CATEGORY:
        return MAINSTREAM_PHASE_CATEGORY[phase]
    if phase == "16 plus":
        return "24" if t == "Community school" else None
    return None


def report_url(g: dict) -> str | None:
    """Provider page URL for a GIAS establishment row, or None if its type is unmapped."""
    if not g:
        return None
    cat = report_category(g.get("TypeOfEstablishment (name)"), g.get("PhaseOfEducation (name)"),
                          clean(g.get("InspectorateName (name)")))
    return f"{REPORTS}/{cat}/{g['URN']}" if cat else None


# ---------------------------------------------------------------------------
# State-funded schools
# ---------------------------------------------------------------------------

def state_events(urn: str, cur: dict | None, old: dict | None) -> list[dict]:
    events: dict[str, dict] = {}

    def add(ev: dict) -> None:
        key = ev.get("inspection_number") or f"{ev['kind']}:{ev.get('date')}"
        if ev.get("date") and key not in events:
            events[key] = ev

    if cur:
        num = clean(cur.get("Inspection number of latest full inspection"))
        if num:
            d = iso(cur.get("Inspection start date"))
            card, grade_dates = {}, {}
            for key, col in REIF_AREAS:
                card[key] = clean(cur.get(col))
                gd = iso(cur.get(REIF_DATE_COLS[key]))
                if gd and gd != d:
                    grade_dates[key] = gd
            add({
                "kind": "report_card", "framework": "REIF", "date": d,
                "published": iso(cur.get("Publication date")),
                "type": clean(cur.get("Inspection type")), "inspection_number": num,
                "predecessor_urn": predecessor(urn, cur.get("URN at time of latest full inspection")),
                "category_of_concern": concern(cur.get("Category of concern")),
                "report_card": card, "grade_dates": grade_dates,
            })
        num = clean(cur.get("Inspection number of latest OEIF graded inspection"))
        if num:
            d = iso(cur.get("Inspection start date of latest OEIF graded inspection"))
            add({
                "kind": "graded", "framework": eif_framework(d), "date": d,
                "published": iso(cur.get("Publication date of latest OEIF graded inspection")),
                "type": clean(cur.get("Inspection type of latest OEIF graded inspection")),
                "inspection_number": num,
                "predecessor_urn": predecessor(urn, cur.get("URN at time of latest OEIF graded inspection")),
                "category_of_concern": concern(cur.get("Latest OEIF category of concern")),
                "judgements": {
                    "overall_effectiveness": grade(cur.get("Latest OEIF overall effectiveness")),
                    "quality_of_education": grade(cur.get("Latest OEIF quality of education")),
                    "behaviour_and_attitudes": grade(cur.get("Latest OEIF behaviour and attitudes")),
                    "personal_development": grade(cur.get("Latest OEIF personal development")),
                    "leadership_and_management": grade(cur.get("Latest OEIF effectiveness of leadership and management")),
                    "safeguarding_effective": yes_no(cur.get("Latest OEIF  safeguarding is effective?")),
                    "early_years": grade(cur.get("Latest OEIF early years provision (where applicable)")),
                    "sixth_form": grade(cur.get("Latest OEIF sixth form provision (where applicable)")),
                },
            })
        num = clean(cur.get("Latest ungraded inspection number"))
        if num:
            d = iso(cur.get("Date of latest ungraded inspection"))
            add({
                "kind": "ungraded", "framework": eif_framework(d), "date": d,
                "published": iso(cur.get("Ungraded inspection publication date")),
                "type": "Ungraded inspection (section 8)", "inspection_number": num,
                "predecessor_urn": predecessor(urn, cur.get("URN at time of the ungraded inspection")),
                "outcome": clean(cur.get("Ungraded inspection overall outcome")),
            })
    if old:
        num = clean(old.get("Inspection number of latest graded inspection"))
        if num:
            d = iso(old.get("Inspection start date"))
            add({
                "kind": "graded", "framework": eif_framework(d), "date": d,
                "published": iso(old.get("Publication date")),
                "type": clean(old.get("Inspection type")), "inspection_number": num,
                "predecessor_urn": predecessor(urn, old.get("URN at time of latest graded inspection")),
                "category_of_concern": concern(old.get("Category of concern")),
                "judgements": {
                    "overall_effectiveness": grade(old.get("Overall effectiveness")),
                    "quality_of_education": grade(old.get("Quality of education")),
                    "behaviour_and_attitudes": grade(old.get("Behaviour and attitudes")),
                    "personal_development": grade(old.get("Personal development")),
                    "leadership_and_management": grade(old.get("Effectiveness of leadership and management")),
                    "safeguarding_effective": yes_no(old.get("Safeguarding is effective?")),
                    "early_years": grade(old.get("Early years provision (where applicable)")),
                    "sixth_form": grade(old.get("Sixth form provision (where applicable)")),
                },
            })
        num = clean(old.get("Previous graded inspection number"))
        if num:
            d = iso(old.get("Previous inspection start date"))
            add({
                "kind": "graded", "framework": eif_framework(d), "date": d,
                "published": iso(old.get("Previous publication date")),
                "type": None, "inspection_number": num,
                "predecessor_urn": predecessor(urn, old.get("URN at time of previous graded inspection")),
                "category_of_concern": concern(old.get("Previous category of concern")),
                "judgements": {
                    "overall_effectiveness": grade(old.get("Previous graded inspection overall effectiveness")),
                    "quality_of_education": grade(old.get("Previous quality of education")),
                    "behaviour_and_attitudes": grade(old.get("Previous behaviour and attitudes")),
                    "personal_development": grade(old.get("Previous personal development")),
                    "leadership_and_management": grade(old.get("Previous effectiveness of leadership and management")),
                    "safeguarding_effective": yes_no(old.get("Previous safeguarding is effective?")),
                    "early_years": grade(old.get("Previous early years provision (where applicable)")),
                    "sixth_form": grade(old.get("Previous sixth form provision (where applicable)")),
                },
            })
        num = clean(old.get("Latest ungraded inspection number since last graded inspection"))
        if num:
            d = iso(old.get("Date of latest ungraded inspection"))
            add({
                "kind": "ungraded", "framework": eif_framework(d), "date": d,
                "published": iso(old.get("Ungraded inspection publication date")),
                "type": "Ungraded inspection (section 8)", "inspection_number": num,
                "predecessor_urn": predecessor(urn, old.get("URN at time of the ungraded inspection")),
                "outcome": clean(old.get("Ungraded inspection overall outcome")),
            })
    return sorted(events.values(), key=lambda e: (e["date"], e.get("published") or ""), reverse=True)


def ungraded_count(evs: list[dict], cur: dict | None, old: dict | None) -> int | None:
    """Ungraded inspections since the last graded one (the MI only details the latest)."""
    graded = next((e for e in evs if e["kind"] == "graded"), None)
    if not graded:
        return None
    if not old or clean(old.get("Inspection number of latest graded inspection")) != graded["inspection_number"]:
        return sum(1 for e in evs if e["kind"] == "ungraded" and e["date"] > graded["date"])
    n = to_int(old.get("Number of ungraded inspections since the last graded inspection")) or 0
    cur_ug = clean((cur or {}).get("Latest ungraded inspection number"))
    old_ug = clean(old.get("Latest ungraded inspection number since last graded inspection"))
    return n + (1 if cur_ug and cur_ug != old_ug else 0)


def summary(ev: dict | None) -> dict | None:
    """Compact form of an inspection event for 'previous' / 'last_graded'."""
    if not ev:
        return None
    out = {k: ev.get(k) for k in ("kind", "framework", "date", "published", "type", "inspection_number",
                                  "predecessor_urn", "category_of_concern")}
    if ev["kind"] == "graded":
        out["overall_effectiveness"] = ev["judgements"].get("overall_effectiveness")
        if out["overall_effectiveness"] in (None, "Not judged"):
            out["judgements"] = ev["judgements"]
    elif ev["kind"] == "ungraded":
        out["outcome"] = ev.get("outcome")
    elif ev["kind"] == "report_card":
        out["report_card"] = ev.get("report_card")
    elif ev["kind"] == "additional":
        out["outcome"] = ev.get("outcome")
    return out


# ---------------------------------------------------------------------------
# Non-association independent schools
# ---------------------------------------------------------------------------

ISS_PARTS = {
    "part_1_quality_of_education": "Part 1 overall",
    "part_2_spiritual_moral_social_cultural": "Part 2 overall",
    "part_3_welfare_health_safety": "Part 3 overall",
    "part_4_suitability_of_staff": "Part 4 overall",
    "part_5_premises": "Part 5 overall",
    "part_6_information": "Part 6 overall",
    "part_7_complaints": "Part 7 overall",
    "part_8_leadership_and_management": "Part 8 overall",
}


def independent_events(urn: str, cur: dict | None, old: dict | None, additional: list[dict]):
    standard: dict[str, dict] = {}
    extra: dict[str, dict] = {}

    iss = None
    if cur:
        iss = {
            "overall": clean(cur.get("Most recent standard inspection: Overall compliance with ISS")),
            "complies_with_registration": {"Y": True, "N": False}.get(
                clean(cur.get("Most recent standard inspection: School complies with registration agreement (GIAS)?")) or ""),
            **{k: clean(cur.get("Most recent standard inspection: " + v)) for k, v in ISS_PARTS.items()},
        }
        num = clean(cur.get("Inspection number of latest REIF standard inspection"))
        if num:
            d = iso(cur.get("Inspection start date"))
            standard[num] = {
                "kind": "report_card", "framework": "REIF", "date": d,
                "published": iso(cur.get("Publication date")), "type": clean(cur.get("Inspection type")),
                "inspection_number": num,
                "report_card": {k: clean(cur.get(col)) for k, col in REIF_AREAS},
            }
        num = clean(cur.get("Inspection number of latest OEIF standard inspection"))
        if num:
            d = iso(cur.get("Inspection start date of latest OEIF standard inspection"))
            standard[num] = {
                "kind": "graded", "framework": eif_framework(d), "date": d,
                "published": iso(cur.get("Publication date of latest OEIF standard inspection")),
                "type": clean(cur.get("Inspection type of latest OEIF standard inspection")),
                "inspection_number": num,
                "judgements": {
                    "overall_effectiveness": grade(cur.get("Latest OEIF overall effectiveness")),
                    "quality_of_education": grade(cur.get("Latest OEIF quality of education")),
                    "behaviour_and_attitudes": grade(cur.get("Latest OEIF behaviour and attitudes")),
                    "personal_development": grade(cur.get("Latest OEIF personal development")),
                    "leadership_and_management": grade(cur.get("Latest OEIF effectiveness of leadership and management")),
                    "safeguarding_effective": yes_no(cur.get("Latest OEIF safeguarding is effective?")),
                    "early_years": grade(cur.get("Latest OEIF early years provision (where applicable)")),
                    "sixth_form": grade(cur.get("Latest OEIF sixth form provision (where applicable)")),
                },
            }
        num = clean(cur.get("Most recent progress monitoring: inspection number"))
        if num:
            extra[num] = {
                "kind": "additional", "date": iso(cur.get("Most recent progress monitoring: start date")),
                "published": iso(cur.get("Most recent progress monitoring: publication date")),
                "type": clean(cur.get("Most recent progress monitoring: inspection type")),
                "inspection_number": num,
            }
    if old:
        num = clean(old.get("Inspection number"))
        if num and num not in standard:
            d = iso(old.get("First day of inspection"))
            standard[num] = {
                "kind": "graded", "framework": eif_framework(d), "date": d,
                "published": iso(old.get("Publication date")), "type": clean(old.get("Inspection type")),
                "inspection_number": num,
                "judgements": {
                    "overall_effectiveness": grade(old.get("Overall effectiveness")),
                    "quality_of_education": grade(old.get("Quality of education")),
                    "behaviour_and_attitudes": grade(old.get("Behaviour and attitudes")),
                    "personal_development": grade(old.get("Personal development")),
                    "leadership_and_management": grade(old.get("Effectiveness of leadership and management")),
                    "safeguarding_effective": yes_no(old.get("Safeguarding is effective?")),
                    "early_years": grade(old.get("Early years provision (where applicable)")),
                    "sixth_form": grade(old.get("Sixth form provision (where applicable)")),
                },
            }
        num = clean(old.get("Previous standard inspection number"))
        if num and num not in standard:
            d = iso(old.get("Previous first day of inspection"))
            standard[num] = {
                "kind": "graded", "framework": eif_framework(d), "date": d,
                "published": iso(old.get("Previous publication date")), "type": "Independent school standard inspection",
                "inspection_number": num,
                "judgements": {"overall_effectiveness": grade(old.get("Previous overall effectiveness"))},
            }
        num = clean(old.get("Progress monitoring: inspection number"))
        if num:
            extra.setdefault(num, {
                "kind": "additional", "date": iso(old.get("Progress monitoring: first day of inspection")),
                "published": iso(old.get("Progress monitoring: publication date")),
                "type": clean(old.get("Progress monitoring: inspection type")), "inspection_number": num,
            })["outcome"] = clean(old.get("Progress monitoring: overall outcome"))
    for row in additional:
        num = clean(row.get("Inspection number"))
        if not num:
            continue
        ev = extra.setdefault(num, {
            "kind": "additional", "date": iso(row.get("Inspection start date")),
            "published": iso(row.get("Publication date")), "type": clean(row.get("Inspection type")),
            "inspection_number": num,
        })
        ev["outcome"] = clean(row.get("Overall outcome"))

    def order(evs):
        return sorted((e for e in evs if e.get("date")), key=lambda e: (e["date"], e.get("published") or ""), reverse=True)

    std = order(standard.values())
    if std and iss:
        std[0]["independent_school_standards"] = iss
    return std, order(extra.values())


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_all(refresh: bool = False) -> dict[str, dict]:
    """Build ofsted.json content for every English LA. Returns {la_code: data}."""
    log("ofsted.json: state-funded + independent school inspections (all England)")
    gias = gias_open_all()

    _, st_atts = govuk_attachments(STATE_SLUG, refresh)
    st_cur_att = pick_attachment(st_atts, r"state-funded schools.*latest inspections", ".csv")
    st_old_att = pick_attachment(st_atts, r"state-funded schools.*latest inspections", ".csv", STATE_FINAL_OEIF_AS_AT)
    st_cur = {r["URN"]: r for r in read_csv(cached_attachment(st_cur_att, "state_latest", refresh))}
    st_old = {r["URN"]: r for r in read_csv(cached_attachment(st_old_att, "state_latest", refresh))}

    _, in_atts = govuk_attachments(IND_SLUG, refresh)
    in_cur_att = pick_attachment(in_atts, r"most recent inspections data", ".csv")
    in_old_att = pick_attachment(in_atts, r"most recent inspections data", ".csv", IND_FINAL_OEIF_AS_AT)
    in_add_att = pick_attachment(in_atts, r"as at .*: additional inspections data", ".csv")
    in_cur = {r["URN"]: r for r in read_csv(cached_attachment(in_cur_att, "ind_recent", refresh))}
    in_old = {r["URN"]: r for r in read_csv(cached_attachment(in_old_att, "ind_recent", refresh))}
    in_add: dict[str, list[dict]] = {}
    for r in read_csv(cached_attachment(in_add_att, "ind_additional", refresh)):
        in_add.setdefault(r["URN"], []).append(r)

    schools_by_la: dict[str, dict[str, dict]] = defaultdict(dict)
    urns = set(gias) | set(st_cur) | set(in_cur)
    unassigned = 0
    for urn in sorted(urns, key=int):
        g = gias.get(urn, {})
        la_row = st_cur.get(urn) or in_cur.get(urn) or st_old.get(urn) or in_old.get(urn)
        la_code = g.get("LA (code)") if g else la_code_for_name((la_row or {}).get("Local authority"))
        if not la_code:
            unassigned += 1
            continue

        name = g.get("EstablishmentName") or (st_cur.get(urn) or in_cur.get(urn) or {}).get("School name")
        est_type = g.get("TypeOfEstablishment (name)", "")
        independent = "independent" in est_type.lower() or (urn in in_cur and urn not in st_cur)
        inspectorate = clean(g.get("InspectorateName (name)"))
        entry: dict = {"name": name, "establishment_type": est_type or None,
                       "open": bool(g), "sector": "independent" if independent else "state"}

        if independent and (inspectorate == "ISI" or urn in ISI_PAGES) and urn not in in_cur:
            entry.update({
                "inspectorate": "ISI",
                "isi_url": ISI_PAGES.get(urn, ISI_SEARCH),
                "isi_search_url": ISI_SEARCH,
                "note": "Association independent school inspected by the Independent Schools Inspectorate (ISI); "
                        "Ofsted does not publish its inspection outcomes.",
            })
        elif independent:
            std, extra = independent_events(urn, in_cur.get(urn), in_old.get(urn), in_add.get(urn, []))
            entry.update({
                "inspectorate": "Ofsted",
                "report_url": report_url(g) or f"{REPORTS}/27/{urn}",
                "latest": std[0] if std else None,
                "previous": summary(std[1]) if len(std) > 1 else None,
                "latest_additional_inspection": summary(extra[0]) if extra else None,
            })
            if not std:
                entry["note"] = ("No standard inspection is published in Ofsted's management information yet "
                                 "(new or recently registered school).")
        else:
            evs = state_events(urn, st_cur.get(urn), st_old.get(urn))
            latest = evs[0] if evs else None
            entry.update({
                "inspectorate": "Ofsted",
                "report_url": report_url(g),
                "latest": latest,
                "previous": summary(evs[1]) if len(evs) > 1 else None,
            })
            if latest and latest["kind"] != "graded":
                graded = next((e for e in evs if e["kind"] == "graded"), None)
                entry["last_graded"] = summary(graded)
            if latest and latest["kind"] == "ungraded":
                entry["ungraded_inspections_since_last_graded"] = ungraded_count(
                    evs, st_cur.get(urn), st_old.get(urn))
            if not evs:
                entry["note"] = "No published inspection in Ofsted's management information."
        schools_by_la[la_code][urn] = prune(entry)

    if unassigned:
        log(f"  {unassigned} schools in the MI could not be matched to an English LA (skipped)")

    sources = [
        {"title": f"State-funded school inspections and outcomes: management information - {st_cur_att['title']}",
         "url": st_cur_att["url"], "licence": OGL},
        {"title": f"State-funded school inspections and outcomes: management information - {st_old_att['title']} "
                  "(latest and previous graded inspections before the renewed framework)",
         "url": st_old_att["url"], "licence": OGL},
        {"title": f"Non-association independent schools inspections and outcomes: management information - {in_cur_att['title']}",
         "url": in_cur_att["url"], "licence": OGL},
        {"title": f"Non-association independent schools inspections and outcomes: management information - {in_add_att['title']}",
         "url": in_add_att["url"], "licence": OGL},
        {"title": f"Non-association independent schools inspections and outcomes: management information - {in_old_att['title']}",
         "url": in_old_att["url"], "licence": OGL},
        {"title": "Get Information about Schools - establishment register (school list, inspectorate)",
         "url": "https://get-information-schools.service.gov.uk/Downloads", "licence": OGL},
    ]
    notes = [
        "Keyed by URN (all open establishments in this LA in GIAS). 'latest' is the most recent published "
        "inspection in Ofsted's management information (MI); 'previous' summarises the one before it among the "
        "inspections the MI details (latest report card, latest and previous graded, latest ungraded). Earlier "
        "intermediate ungraded inspections are not itemised: see ungraded_inspections_since_last_graded.",
        "kind: report_card = renewed framework report card (grades exactly as published in the MI); graded = "
        "EIF/CIF graded inspection with judgements; ungraded = section 8 ungraded inspection (outcome text as "
        "published); additional = independent-school progress monitoring / material change inspection.",
        "For state-funded schools whose latest inspection is not a graded one, 'last_graded' holds the most recent "
        "graded inspection (the grade an ungraded inspection confirms).",
        "report_card.grade_dates lists evaluation areas whose grade was updated after the full inspection "
        "(e.g. by a monitoring inspection).",
        "overall_effectiveness 'Not judged': single-word overall effectiveness grades were removed for graded "
        "inspections from September 2024. Judgement values of 9/0 (not applicable) are omitted.",
        "predecessor_urn: the inspection was of a predecessor school (e.g. before academy conversion).",
        "MI excludes inspections not yet published; check report_url for the very latest.",
        "report_url is derived from the GIAS establishment type and phase (reports.ofsted.gov.uk provider pages "
        "are at /provider/<category>/<urn> and the category depends only on the kind of establishment), not "
        "looked up per school. It is null for a small number of types with no separate Ofsted provider page "
        "(Miscellaneous, Sixth form centres, Secure units, Academy secure 16 to 19) and for ISI-inspected "
        "independent schools (isi_url/isi_search_url are set instead).",
    ]
    data_as_at = {"state_funded": st_cur_att["as_at"].isoformat(), "independent": in_cur_att["as_at"].isoformat()}
    return {
        la_code: {
            "sources": sources,
            "data_as_at": data_as_at,
            "notes": notes,
            "frameworks": FRAMEWORKS,
            "schools": schools,
        }
        for la_code, schools in schools_by_la.items()
    }
