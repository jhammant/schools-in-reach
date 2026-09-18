"""parentview.json: Ofsted Parent View school-level results for every English school,
split into one file per local authority.

Source: gov.uk "Ofsted Parent View: management information" (OGL v3.0), which
covers all of England. Ofsted publishes school-level percentages only for
schools with at least 10 submissions in the release window.

The survey questions changed in November 2025, so two releases are used:
  * the latest release (new question set, submissions since 10 Nov 2025);
  * the pinned release as at 1 September 2025 (the last full 365-day window
    under the previous question set), shown only as an older survey.

Schools are assigned to an LA via GIAS (URN -> LA (code)) where the URN is a
currently open establishment, falling back to the release's own 'Local
Authority' name column (matched against GIAS LA names) otherwise.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime

from util import (OGL, cached_attachment, gias_open_all, govuk_attachments, la_code_for_name, log,
                  ods_rows, pick_attachment, prune, to_float, to_int)

SLUG = "ofsted-parent-view-management-information"
OLD_SET_AS_AT = date(2025, 9, 1)

OPTION_NORMALISE = {
    "strongly agree": "Strongly agree",
    "agree": "Agree",
    "neither agree nor disagree": "Neither agree nor disagree",
    "disagree": "Disagree",
    "strongly disagree": "Strongly disagree",
    "don't know": "Don't know",
    "dont know": "Don't know",
    "not applicable": "Not applicable",
    "yes": "Yes",
    "no": "No",
    "positive": "Positive",
    "neutral": "Neutral",
    "negative": "Negative",
    "i have not raised any concerns": "I have not raised any concerns",
}


def norm_option(opt: str) -> str:
    return OPTION_NORMALISE.get(opt.strip().lower(), opt.strip())


def qkey(q: str) -> tuple[int, str]:
    m = re.match(r"Q(\d+)([a-z]?)", q)
    return (int(m.group(1)), m.group(2)) if m else (999, q)


def long_date(text: str | None) -> str | None:
    """'10 November 2025' or 'Tuesday, June 16, 2026' -> ISO date (None if unparseable)."""
    for fmt in ("%d %B %Y", "%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime((text or "").strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def cover_info(path) -> dict:
    info = {}
    for row in ods_rows(path, "Cover"):
        if len(row) >= 2 and row[0].strip().endswith(":"):
            info[row[0].strip().rstrip(":").lower()] = row[1].strip()
    return info


def parse_release(path) -> tuple[dict, dict, list[dict]]:
    """Return (release meta, question definitions, school rows) for one release."""
    info = cover_info(path)
    period = info.get("period covered", "")
    m = re.search(r"between (\d{1,2} \w+ \d{4}) and (\d{1,2} \w+ \d{4})", period)
    rows = list(ods_rows(path, "Table_3"))
    hi = next(i for i, r in enumerate(rows) if r and r[0].strip() == "URN")
    header = [h.strip() for h in rows[hi]]

    questions: dict[str, dict] = {}
    columns: list[tuple[int, str, str]] = []  # (index, question id, option)
    new_style = any(re.match(r"^Q\d+[a-z]?\. ", h) for h in header)
    for i, h in enumerate(header):
        if new_style:
            mm = re.match(r"^(Q\d+[a-z]?)\.\s*(.+):\s*([^:]+?)\s*%$", h)
            if not mm:
                continue
            q, text, opt = mm.group(1), mm.group(2).strip(), norm_option(mm.group(3))
            questions.setdefault(q, {"text": text, "options": []})
        else:
            mm = re.match(r"^(Q\d+[a-z]?)\s+(.+?)\s*%$", h)
            if not mm:
                continue
            q, opt = mm.group(1), norm_option(mm.group(2))
            questions.setdefault(q, {"text": None, "options": []})
        if opt not in questions[q]["options"]:
            questions[q]["options"].append(opt)
        columns.append((i, q, opt))

    if not new_style:  # question wording lives in Table_1
        for r in ods_rows(path, "Table_1"):
            if r:
                mm = re.match(r"^(Q\d+[a-z]?)\.\s*(.+?)\.?$", r[0].strip())
                if mm and mm.group(1) in questions and not questions[mm.group(1)]["text"]:
                    questions[mm.group(1)]["text"] = mm.group(2).strip()

    col = {h: i for i, h in enumerate(header)}
    schools = []
    for r in rows[hi + 1:]:
        if not r or not r[0].strip().isdigit():
            continue
        cell = lambda i: r[i] if i < len(r) else ""
        responses: dict[str, dict] = {}
        for i, q, opt in columns:
            v = to_int(cell(i))
            if v is not None:
                responses.setdefault(q, {})[opt] = v
        schools.append({
            "urn": r[0].strip(),
            "name": cell(col["School Name"]).strip(),
            "la": cell(col["Local Authority"]).strip(),
            "phase": cell(col["Ofsted Phase or Type of Education"]).strip(),
            "submissions": to_int(cell(col["Submissions"])),
            "response_rate_pct": to_float(cell(col["Response Rate"]), 1),
            "responses": dict(sorted(responses.items(), key=lambda kv: qkey(kv[0]))),
        })
    meta = {
        "period_from": long_date(m.group(1)) if m else None,
        "period_to": long_date(m.group(2)) if m else None,
        "published": long_date(info.get("published on")),
    }
    questions = dict(sorted(questions.items(), key=lambda kv: qkey(kv[0])))
    return meta, questions, schools


def build_all(refresh: bool = False) -> dict[str, dict]:
    """Build parentview.json content for every English LA. Returns {la_code: data}."""
    log("parentview.json: Ofsted Parent View (all England)")
    gias = gias_open_all()
    _, atts = govuk_attachments(SLUG, refresh)
    latest = pick_attachment(atts, r"Parent View management information", ".ods")
    old = pick_attachment(atts, r"Parent View management information", ".ods", OLD_SET_AS_AT)

    releases, question_sets = {}, {}
    per_school_by_la: dict[str, dict[str, dict]] = defaultdict(dict)
    sources = []
    unassigned = 0
    plan = [(latest, "current", "2025-11")]
    if old["as_at"] != latest["as_at"]:
        plan.append((old, "previous_question_set", "2019-09"))
    for att, slot, qset in plan:
        path = cached_attachment(att, "parentview", refresh)
        meta, questions, rows = parse_release(path)
        rid = att["as_at"].isoformat()
        releases[rid] = {"title": att["title"], "question_set": qset, **meta, "url": att["url"]}
        question_sets[qset] = questions
        sources.append({"title": f"Ofsted Parent View: management information - {att['title']}",
                        "url": att["url"], "licence": OGL})
        for s in rows:
            g = gias.get(s["urn"])
            la_code = g.get("LA (code)") if g else la_code_for_name(s["la"])
            if not la_code:
                unassigned += 1
                continue
            entry = per_school_by_la[la_code].setdefault(s["urn"], {"name": s["name"]})
            entry[slot] = {
                "release": rid,
                "phase": s["phase"],
                "submissions": s["submissions"],
                "response_rate_pct": s["response_rate_pct"],
                "responses": s["responses"],
            }

    if unassigned:
        log(f"  {unassigned} Parent View rows could not be matched to an English LA (skipped)")

    def notes_for(per_school: dict) -> list[str]:
        n_cur = sum(1 for v in per_school.values() if "current" in v)
        return [
            "Keyed by URN. Ofsted only publishes school-level Parent View results for schools with at least 10 "
            "submissions in the release window; other schools in this LA have no published results.",
            "responses: for each question, the percentage of submissions giving each answer option (rounded by "
            "Ofsted, may not sum to 100; null/absent = no responses). Yes/No and Positive/Neutral/Negative questions "
            "are shown with their own options.",
            "Parent View questions changed in November 2025. 'current' uses the new question set (submissions since "
            "10 November 2025); 'previous_question_set' is the last release under the old questions (submissions "
            "3 September 2024 to 1 September 2025). The two are not directly comparable.",
            "Response rates are low for most schools, so treat results with caution.",
            f"{n_cur} schools in this LA have results in the latest release.",
        ]

    return {
        la_code: {
            "sources": sources,
            "notes": notes_for(per_school),
            "releases": releases,
            "question_sets": question_sets,
            "schools": {k: prune(v) for k, v in sorted(per_school.items(), key=lambda kv: int(kv[0]))},
        }
        for la_code, per_school in per_school_by_la.items()
    }
