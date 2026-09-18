"""Spot-check the built JSON against Ofsted's live report pages.

Checks (fetched fresh from reports.ofsted.gov.uk each run):
  * Clapton Girls' Academy (137442)            - graded EIF inspection judgements
  * Stoke Newington School and Sixth Form (100279) - ungraded inspection + rating
  * Orchard Primary School (100234)            - renewed-framework report card
  * Hillside Children's Centre Nursery (EY450433) - early years report card
plus pupil numbers on the report pages against characteristics.json.
Grade mismatches fail the check; date offsets are reported as warnings.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime

from util import CACHE, LA_ROOT, fetch

GRADES_REIF = {"Exceptional", "Strong standard", "Expected standard", "Needs attention", "Urgent improvement"}
AREA_LABELS = {
    "inclusion": "Inclusion",
    "curriculum_and_teaching": "Curriculum and teaching",
    "achievement": "Achievement",
    "attendance_and_behaviour": "Attendance and behaviour",
    "personal_development_and_wellbeing": "Personal development and wellbeing",
    "early_years": "Early years",
    "post_16": "Post-16 provision",
    "leadership_and_governance": "Leadership and governance",
    "behaviour_attitudes_and_routines": "Behaviour, attitudes and establishing routines",
    "childrens_welfare_and_wellbeing": "Children's welfare and wellbeing",
}
EIF_LABELS = {
    "quality_of_education": "Quality of education",
    "behaviour_and_attitudes": "Behaviour and attitudes",
    "personal_development": "Personal development",
    "leadership_and_management": "Leadership and management",
    "sixth_form": "Sixth form provision",
    "early_years": "Early years provision",
}


class Report:
    def __init__(self):
        self.failed = False

    def check(self, label: str, ours, theirs, hard: bool = True) -> None:
        ok = ours == theirs
        tag = "MATCH" if ok else ("DIFF " if hard else "WARN ")
        print(f"  {tag} {label}: json={ours!r} page={theirs!r}")
        if not ok and hard:
            self.failed = True


def page_nodes(url: str, name: str) -> list[str]:
    path = fetch(url, CACHE / "reports" / f"verify_{name}.html", refresh=True)
    raw = html.unescape(path.read_text(encoding="utf-8", errors="replace"))  # report cards are escaped HTML
    raw = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", " ", raw, flags=re.S)
    nodes = [re.sub(r"\s+", " ", html.unescape(n)).strip() for n in re.split(r"<[^>]+>", raw)]
    return [n for n in nodes if n]


def to_iso(text: str | None) -> str | None:
    if not text:
        return None
    return datetime.strptime(text.strip(), "%d %B %Y").date().isoformat()


def report_card_from_page(nodes: list[str]) -> tuple[str | None, dict, str | None]:
    text = " ".join(nodes)
    m = re.search(r"Inspection report: (\d{1,2} \w+ \d{4})", text)
    grades = {}
    for i, n in enumerate(nodes):
        for key, label in AREA_LABELS.items():
            if n == label and key not in grades:
                grades[key] = next((g for g in nodes[i + 1:i + 6] if g in GRADES_REIF), None)
    sg = re.search(r"Safeguarding standards (met|not met)", text)
    return (to_iso(m.group(1)) if m else None), grades, ({"met": "Met", "not met": "Not met"}[sg.group(1)] if sg else None)


def run(la_code: str = "204") -> bool:
    """Spot-check site/data/la/<la_code>/*.json (default: Hackney, 204) against reports.ofsted.gov.uk."""
    out_dir = LA_ROOT / la_code
    rep = Report()
    ofsted = json.loads((out_dir / "ofsted.json").read_text())["schools"]
    nurseries = {p["urn"]: p for p in json.loads((out_dir / "nurseries.json").read_text())["providers"]}
    chars = json.loads((out_dir / "characteristics.json").read_text())["schools"]
    pv = json.loads((out_dir / "parentview.json").read_text())["schools"]

    # 1. Clapton Girls' Academy - graded (EIF) inspection
    urn = "137442"
    s = ofsted[urn]
    print(f"\n[{urn}] {s['name']} {s['report_url']}")
    nodes = page_nodes(s["report_url"], urn)
    text = " ".join(nodes)
    m = re.search(r"overall outcome of the inspection on (\d{1,2} \w+ \d{4}) was: (Outstanding|Good|Requires improvement|Inadequate)", text)
    rep.check("latest inspection date", s["latest"]["date"], to_iso(m.group(1)) if m else None)
    rep.check("overall effectiveness", s["latest"]["judgements"].get("overall_effectiveness"), m.group(2) if m else None)
    for key, label in EIF_LABELS.items():
        mm = re.search(re.escape(label) + r": (Outstanding|Good|Requires improvement|Inadequate)", text)
        ours = s["latest"]["judgements"].get(key)
        if ours or mm:
            rep.check(label, ours, mm.group(1) if mm else None)
    rep.check("pupils (census headcount vs page)", chars[urn]["headcount"],
              int(re.search(r"Number of pupils: (\d+)", text).group(1)) if "Number of pupils:" in text else None, hard=False)

    # 2. Stoke Newington School and Sixth Form - ungraded inspection, rating carried from graded inspection
    urn = "100279"
    s = ofsted[urn]
    print(f"\n[{urn}] {s['name']} {s['report_url']}")
    nodes = page_nodes(s["report_url"], urn)
    text = " ".join(nodes)
    rating = re.search(r"Rating and reports (Outstanding|Good|Requires improvement|Inadequate) Latest inspection", text)
    first = re.search(r"All reports (\d{1,2} \w+ \d{4}) ([A-Za-z ]+?) (?:School inspection|Short inspection|Full inspection),", text)
    rep.check("current rating (ungraded outcome)", s["latest"]["outcome"].replace("School remains ", ""),
              rating.group(1) if rating else None)
    rep.check("last graded overall effectiveness", s["last_graded"]["overall_effectiveness"], rating.group(1) if rating else None)
    rep.check("latest inspection date (MI start date vs report list date)", s["latest"]["date"],
              to_iso(first.group(1)) if first else None, hard=False)
    graded = re.search(r"(\d{1,2} \w+ \d{4}) Full inspection: (Outstanding|Good|Requires improvement|Inadequate)", text)
    rep.check("last graded inspection date", s["last_graded"]["date"], to_iso(graded.group(1)) if graded else None, hard=False)
    rep.check("pupils (census headcount vs page)", chars[urn]["headcount"],
              int(re.search(r"Number of pupils: (\d+)", text).group(1)) if "Number of pupils:" in text else None, hard=False)

    # 3. Orchard Primary School - renewed framework report card
    urn = "100234"
    s = ofsted[urn]
    print(f"\n[{urn}] {s['name']} {s['report_url']}")
    d, grades, sg = report_card_from_page(page_nodes(s["report_url"], urn))
    rep.check("report card inspection date", s["latest"]["date"], d)
    rep.check("safeguarding standards", s["latest"]["report_card"]["safeguarding_standards"], sg)
    for key, g in grades.items():
        rep.check(AREA_LABELS[key], s["latest"]["report_card"].get(key), g)
    if urn in pv and "current" in pv[urn]:
        q = pv[urn]["current"]
        print(f"  INFO parentview: {q['submissions']} submissions, Q1 {q['responses'].get('Q1')}")

    # 4. Childcare provider - early years report card
    urn = "EY450433"
    p = nurseries[urn]
    print(f"\n[{urn}] {p['name']} {p['report_url']}")
    d, grades, sg = report_card_from_page(page_nodes(p["report_url"], urn))
    rc = p["eyr_report_card"]
    rep.check("report card inspection date", rc["date"], d)
    rep.check("safeguarding standards", rc["safeguarding_standards"], sg)
    for key, g in grades.items():
        rep.check(AREA_LABELS[key], rc.get(key), g)

    print("\nverification", "FAILED" if rep.failed else "passed")
    return rep.failed


# Four non-London schools (2 primary, 2 secondary, four English regions) and two
# non-London nurseries, all with a renewed-framework report card as their latest
# inspection - checked against reports.ofsted.gov.uk the same way as run() above.
NATIONAL_SCHOOL_SAMPLE = [
    ("359", "143812"),   # Standish Community High School, Wigan (North West) - secondary
    ("929", "137457"),   # Cramlington Learning Village, Northumberland (North East) - secondary
    ("926", "146757"),   # Winterton Primary School and Nursery, Norfolk (East of England) - primary
    ("908", "143967"),   # Breage CofE Primary School, Cornwall (South West) - primary
]
NATIONAL_NURSERY_SAMPLE = [
    ("850", "EY488080"),  # Gorseway Nursery School, Hampshire (South East)
    ("888", "EY554021"),  # Cool Kidz @ Langho, Lancashire (North West)
]


def run_national() -> bool:
    """Spot-check a sample of non-London schools and nurseries across LA output files."""
    rep = Report()
    for la_code, urn in NATIONAL_SCHOOL_SAMPLE:
        s = json.loads((LA_ROOT / la_code / "ofsted.json").read_text())["schools"][urn]
        print(f"\n[{la_code}/{urn}] {s['name']} {s['report_url']}")
        d, grades, sg = report_card_from_page(page_nodes(s["report_url"], urn))
        rep.check("report card inspection date", s["latest"]["date"], d)
        rep.check("safeguarding standards", s["latest"]["report_card"]["safeguarding_standards"], sg)
        for key, g in grades.items():
            rep.check(AREA_LABELS[key], s["latest"]["report_card"].get(key), g)

    for la_code, urn in NATIONAL_NURSERY_SAMPLE:
        providers = {p["urn"]: p for p in json.loads((LA_ROOT / la_code / "nurseries.json").read_text())["providers"]}
        p = providers[urn]
        print(f"\n[{la_code}/{urn}] {p['name']} {p['report_url']}")
        d, grades, sg = report_card_from_page(page_nodes(p["report_url"], urn))
        rc = p["eyr_report_card"]
        rep.check("report card inspection date", rc["date"], d)
        rep.check("safeguarding standards", rc["safeguarding_standards"], sg)
        for key, g in grades.items():
            rep.check(AREA_LABELS[key], rc.get(key), g)

    print("\nnational verification", "FAILED" if rep.failed else "passed")
    return rep.failed


if __name__ == "__main__":
    import sys

    failed = run("204")
    failed = run_national() or failed
    sys.exit(1 if failed else 0)
