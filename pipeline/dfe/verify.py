"""Spot-check built JSON against the live Compare School Performance school pages.

Usage (after build.py):
    uv run python pipeline/dfe/verify.py [--la 204] [--secondary URN ...] [--primary URN ...]

With no school URNs given, one secondary (with KS4 results) and one primary
(with KS2 results) are picked from the built league tables. Fetched pages are
cached in pipeline/.cache/dfe/verify/. Prints every value compared and exits
non-zero if any differ.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch  # noqa: E402

DATA = fetch.ROOT / "out" / "site" / "data"
PAGES = fetch.CACHE / "verify"
N = r"(-?\d+(?:\.\d+)?)%?"

HACKNEY_SECONDARIES = [137442, 100279]  # Clapton Girls' Academy, Stoke Newington School and Sixth Form
HACKNEY_PRIMARIES = [100223, 100218]  # Daubeney Primary School, Berger Primary School


def page_text(path: str) -> str:
    name = path.strip("/").replace("/", "__") + ".html"
    try:
        dest = fetch.download(fetch.CSCP + path, PAGES / name)
    except RuntimeError:
        return ""  # section does not exist for this school (e.g. no sixth form)
    raw = dest.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))


def slug_path(urn: int) -> str:
    text = (fetch.download(f"{fetch.CSCP}/school/{urn}", PAGES / f"school__{urn}.html")).read_text(errors="replace")
    match = re.search(rf'href="(/school/{urn}/[^"/]+)/', text)
    if not match:
        raise RuntimeError(f"no CSCP page links for {urn}")
    return match.group(1)


def get(doc: dict, dotted: str):
    cur = doc
    for part in dotted.split("."):
        if cur is None:
            return None
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


results: list[tuple] = []


def compare(urn, what: str, page_value: str, json_value):
    expected = float(page_value)
    ok = json_value is not None and abs(float(json_value) - expected) < 0.051
    results.append((urn, what, page_value, json_value, ok))


def check_triple(urn, text: str, label: str, targets: list[tuple[str, dict, str]], between: str = " "):
    """Page tables read '<label> <school> <LA> <England>' (LA omitted for census rows)."""
    match = re.search(re.escape(label) + between + " ".join([N] * len(targets)), text)
    if not match:
        results.append((urn, label, "NOT FOUND ON PAGE", None, False))
        return
    for value, (name, doc, path) in zip(match.groups(), targets):
        compare(urn, f"{label} [{name}]", value, get(doc, path))


def pick_schools(la_dir: Path) -> tuple[list[int], list[int]]:
    """One state-funded secondary with KS4 results and one primary with KS2 results."""
    league = json.loads((la_dir / "league_tables.json").read_text())
    state = [r for r in league["rows"] if "independent" not in (r.get("type") or "").lower()]
    with_ks5 = [r for r in state if r.get("ks4_a8") is not None and r.get("ks5_alevel_aps") is not None]
    secondary = (with_ks5 or [r for r in state if r.get("ks4_a8") is not None] or [{}])[0].get("urn")
    primary = next((r["urn"] for r in state if r.get("ks2_rwm_exp") is not None), None)
    return ([secondary] if secondary else [], [primary] if primary else [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--la", default="204", help="LA code to verify (default 204 = Hackney reference schools)")
    parser.add_argument("--secondary", type=int, nargs="*", default=None)
    parser.add_argument("--primary", type=int, nargs="*", default=None)
    args = parser.parse_args()

    la_dir = DATA / "la" / args.la
    bench = json.loads((DATA / "england" / "benchmarks.json").read_text())
    las = json.loads((DATA / "england" / "las.json").read_text())
    la_name = next(e["name"] for e in las["las"] if e["la_code"] == args.la)
    la_bench = {}
    for section, content in bench.items():
        if not isinstance(content, dict):
            continue
        if section == "destinations":
            la_bench[section] = {
                sub: ((content.get(sub) or {}).get("la") or {}).get(args.la, {})
                for sub in ("ks4", "ks5", "he_progression")
            }
        else:
            la_bench[section] = (content.get("la") or {}).get(args.la, {})
    la_re = re.escape(la_name)

    if args.la == "204" and args.secondary is None and args.primary is None:
        secondaries, primaries = HACKNEY_SECONDARIES, HACKNEY_PRIMARIES
    else:
        auto_s, auto_p = pick_schools(la_dir)
        secondaries = args.secondary if args.secondary is not None else auto_s
        primaries = args.primary if args.primary is not None else auto_p

    def lb(section, dotted):
        return get(la_bench, f"{section}.{dotted}")

    for urn in secondaries + primaries:
        doc = json.loads((la_dir / "schools" / f"{urn}.json").read_text())
        base = slug_path(urn)
        phase = "secondary" if urn in secondaries else "primary"
        tag = f"{urn} {doc['name']}"

        if phase == "secondary":
            t = page_text(base + "/secondary")
            for label, key in (("Attainment 8", "attainment8"),
                               ("Grade 5 or above in English & maths GCSEs", "eng_maths_5plus_pct"),
                               ("Entering EBacc", "ebacc_entry_pct"),
                               ("EBacc average point score", "ebacc_aps")):
                check_triple(tag, t, f"{label}", [("school", doc, f"ks4.{key}"), (la_name, la_bench, f"ks4.{key}"), ("England", bench, f"ks4.england.{key}")])
            check_triple(tag, t, "Staying in education, or entering apprenticeships or employment",
                         [("school", doc, "destinations.ks4.sustained_pct"), (la_name, la_bench, "destinations.ks4.sustained_pct"),
                          ("England", bench, "destinations.ks4.england.sustained_pct")])

            t = page_text(base + "/secondary/progress-measures-for-2023-and-2024")
            m = re.search(r"Progress 8 score for the 2023 to 2024 academic year.*?Score " + N + r" Confidence interval.*?" + N + " to " + N, t)
            if m:
                compare(tag, "Progress 8 2023/24 score", m.group(1), get(doc, "ks4.latest_progress8.score"))
                compare(tag, "Progress 8 2023/24 CI lower", m.group(2), get(doc, "ks4.latest_progress8.ci_lower"))
                compare(tag, "Progress 8 2023/24 CI upper", m.group(3), get(doc, "ks4.latest_progress8.ci_upper"))
                tail = t[m.end():]
                a = re.search(r"Area Score " + la_re + " " + N + " England " + N, tail)
                if a:
                    compare(tag, f"Progress 8 2023/24 [{la_name}]", a.group(1), lb("ks4", "latest_progress8.score"))
                    compare(tag, "Progress 8 2023/24 [England]", a.group(2), get(bench, "ks4.england.latest_progress8.score"))
            else:
                results.append((tag, "Progress 8 2023/24", "NOT FOUND ON PAGE", None, False))

            t = page_text(base + "/16-to-18/advanced-level-qualifications")
            m = re.search(r"Average result Points School / college (\S+) " + N + r" " + la_re + r" state-funded schools / colleges (\S+) " + N
                          + r" England all schools/colleges (\S+) " + N, t)
            if m:
                compare(tag, "A level APS [school]", m.group(2), get(doc, "ks5.alevel_aps"))
                results.append((tag, "A level grade [school]", m.group(1), get(doc, "ks5.alevel_grade"), m.group(1) == get(doc, "ks5.alevel_grade")))
                compare(tag, f"A level APS [{la_name}]", m.group(4), lb("ks5", "alevel_aps"))
                compare(tag, "A level APS [England all schools]", m.group(6), get(bench, "ks5.england_all.alevel_aps"))
            else:
                results.append((tag, "A level average result", "NOT FOUND ON PAGE", None, False))
            m = re.search(r"A levels .*?Progress score .*?Score " + N + r" Confidence interval.*?" + N + " to " + N, t)
            if m:
                compare(tag, "A level progress score", m.group(1), get(doc, "ks5.alevel_value_added"))
                compare(tag, "A level progress CI lower", m.group(2), get(doc, "ks5.alevel_va_ci_lower"))
                compare(tag, "A level progress CI upper", m.group(3), get(doc, "ks5.alevel_va_ci_upper"))

            t = page_text(base + "/16-to-18/student-destinations-he")
            check_triple(tag, t, "Students progressing to higher education or training",
                         [("school", doc, "destinations.he_progression.progressed_pct"),
                          (la_name, la_bench, "destinations.he_progression.progressed_pct"),
                          ("England", bench, "destinations.he_progression.england.progressed_pct")])
        else:
            t = page_text(base + "/primary")
            for label, key in (("Pupils meeting expected standard in reading, writing and maths", "rwm_expected_pct"),
                               ("Pupils achieving at a higher standard in reading, writing and maths", "rwm_higher_pct"),
                               ("Average score in reading", "reading_scaled_score"),
                               ("Average score in maths", "maths_scaled_score")):
                check_triple(tag, t, label, [("school", doc, f"ks2.{key}"), (la_name, la_bench, f"ks2.{key}"), ("England", bench, f"ks2.england.{key}")])
            t = page_text(base + "/primary/progress-for-22-23")
            for subject in ("Reading", "Writing", "Maths"):
                m = re.search(subject + r" The banding.*?Score " + N + r" Confidence interval.*?" + N + " to " + N, t)
                if m:
                    key = subject.lower()
                    compare(tag, f"KS2 {subject} progress 2022/23", m.group(1), get(doc, f"ks2.latest_progress.{key}"))
                    ci = get(doc, f"ks2.latest_progress.{key}_ci") or [None, None]
                    compare(tag, f"KS2 {subject} progress CI lower", m.group(2), ci[0])
                    compare(tag, f"KS2 {subject} progress CI upper", m.group(3), ci[1])

        t = page_text(base + "/absence-and-pupil-population")
        check_triple(tag, t, "Overall absence", [("school", doc, "absence.overall_absence_pct"), (la_name, la_bench, f"absence.{phase}.overall_absence_pct"),
                                                 ("England", bench, f"absence.england.{phase}.overall_absence_pct")], between=r" More info.*? ")
        check_triple(tag, t, "Persistent absence", [("school", doc, "absence.persistent_absence_pct"), (la_name, la_bench, f"absence.{phase}.persistent_absence_pct"),
                                                    ("England", bench, f"absence.england.{phase}.persistent_absence_pct")], between=r" More info.*? ")
        for label, key in (("Total number of pupils on roll (all ages)", "pupils"),
                           ("Pupils with an SEN Education, Health and Care Plan", "ehcp_pct"),
                           ("Pupils with SEN Support", "sen_support_pct"),
                           ("Pupils whose first language is not English", "eal_pct"),
                           ("Pupils eligible for free school meals at any time during the past 6 years", "fsm_ever6_pct")):
            check_triple(tag, t, label, [("school", doc, f"census.{key}"), ("England", bench, f"census.england.{phase}.{key}")])

    width = max(len(str(r[0])) for r in results)
    bad = 0
    for urn, what, page_value, json_value, ok in results:
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {str(urn):{width}}  {what}: page={page_value} json={json_value}")
    print(f"\n{len(results) - bad}/{len(results)} values match")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
