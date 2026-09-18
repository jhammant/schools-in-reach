"""Reception outcomes for Westminster (LA 213), Kensington and Chelsea (LA 207)
and Hammersmith and Fulham (LA 205), read from each council's primary
admissions brochure ("Starting school" / "Primary school admissions").

None of the three councils publishes a Reception allocation table. Instead each
school's page in the brochure carries a "How places were offered in <year>"
panel with the previous year's outcome, e.g. "Total number of on-time
applications submitted: 71", "Siblings: 7", "Distance: 13 (last distance
offered was 1.243 of a mile)" or "All applicants were offered". The brochures
are magazine layouts (Westminster's are two-page spreads), so the panel is
read from pdfplumber word positions: the words under the panel heading, in the
heading's own text column, down to the next section heading ("Appeals",
"*For the full admission policy", ...). The school is the largest-font title on
the same page (or half of a spread).

The distance recorded is the last distance printed in the panel, normally the
final (distance) criterion; panels that print several distances (e.g. a faith
and an open route) keep all of them in the notes.
"""

from __future__ import annotations

import re

import b2_common as bc
import pdftools

WCC = "https://www.westminster.gov.uk/"
WB_RBKC = "https://web.archive.org/web/{ts}id_/https://www.rbkc.gov.uk/sites/default/files/media/documents/{path}"
LBHF = "https://www.lbhf.gov.uk/sites/default/files/"
BROCHURES = {
    "213": [
        {"cache": "primary-brochure-2023.pdf", "url": WCC + "media/document/primary-school-admissions-brochure-2023",
         "title": "Westminster City Council: Primary school admissions brochure 2023"},
        {"cache": "primary-brochure-2024.pdf",
         "url": WCC + "sites/default/files/media/documents/Primary%20school%20admissions%20brochure%202024.pdf",
         "title": "Westminster City Council: Primary school admissions brochure 2024"},
        {"cache": "primary-brochure-2025.pdf", "url": WCC + "media/document/primary-school-admissions-brochure-2025",
         "title": "Westminster City Council: Primary school admissions brochure 2025"},
        {"cache": "primary-brochure-2026.pdf",
         "url": WCC + "sites/default/files/media/documents/Primary%20Admissions%20Brochure%202026.pdf",
         "title": "Westminster City Council: Primary admissions brochure 2026"},
    ],
    "207": [
        {"cache": "wb-primary-brochure-2025.pdf",
         "url": WB_RBKC.format(ts="20250413113014", path="RBKC%20Primary%20School%20Admissions%20Brochure%202025.pdf"),
         "title": "RBKC: Primary school admissions brochure 2025 (Internet Archive copy; rbkc.gov.uk blocks automated "
                  "requests)"},
        {"cache": "wb-primary-brochure-2026.pdf", "data_year": 2025,
         "url": WB_RBKC.format(ts="20251214034447", path="RBKC%20-%20Primary%20Admissions%20Brochure%202026.pdf"),
         "title": "RBKC: Primary admissions brochure 2026 (Internet Archive copy; rbkc.gov.uk blocks automated "
                  "requests)"},
    ],
    "205": [
        {"cache": "primary-brochure-2026.pdf", "url": LBHF + "2025-09/primary-starting-school-2026-brochure-final.pdf",
         "title": "Hammersmith & Fulham Council: Starting school 2026 brochure"},
        {"cache": "primary-brochure-2027.pdf", "url": LBHF + "2026-09/starting-school-2027-brochure.pdf",
         "title": "Hammersmith & Fulham Council: Starting school 2027 brochure"},
    ],
}

# Brochure titles with no state-funded GIAS entry of that name: token matching would otherwise attach them to a
# different school sharing a word ("Fulham").
NOT_IN_GIAS = {"The Fulham Bilingual"}
HEAD = ["how", "places", "were", "offered", "in"]
STOP_RE = re.compile(r"^(Appeals|APPEALS|\*\s*For the full|Note:|Nearest tube|Bus routes|About our school|ABOUT OUR|"
                     r"Address|Telephone|Email|Website|Headteacher|Type of school|Admission number|Apply online|"
                     r"Visiting|Supplementary|School uniform|Breakfast|After-school|Nursery|Admissions criteria|"
                     r"ADMISSION CRITERIA|Summarised|Tie-break|OVERSUBSCRIPTION|Oversubscription)")
DIST_RE = re.compile(r"(\d+\.\d+)\s*(?:miles?|of\s+a\s+mile)", re.I)
APPS_RE = re.compile(r"(?:applications\s+submitted|number\s+of\s+applications)\s*:?\s*(\d+)", re.I)
ALL_RE = re.compile(r"all\s+(?:on-time\s+)?applica(?:nts|tions)\s+(?:who\s+applied\s+)?(?:were\s+)?offered|"
                    r"offered\s+(?:a\s+place\s+)?to\s+all\s+(?:on-time\s+)?applicants", re.I)
CRIT_RE = re.compile(r"^[–•\-\s]*([A-Z][A-Za-z0-9 ,'’()/&-]{1,60}?):\s*(\d+)\b")
NOT_TITLE = re.compile(r"^(School information|Details of|Introduction|About|How|The application|Admission|Frequently)",
                       re.I)


def _halves(page) -> list[tuple[float, float]]:
    w = page.width
    return [(0, w / 2), (w / 2, w)] if w > page.height else [(0, w)]


def _panels(path, default_year: int) -> list[dict]:
    out = []
    info: tuple[str, int] | None = None  # (title, admission number) from a school-information page without a panel
    with bc.open_pdf(path) as pdf:
        for page in pdf.pages:
            raw = page.extract_words(x_tolerance=1.5, y_tolerance=2, extra_attrs=["size"])
            words = [pdftools.Word(pdftools.fix_text(w["text"]), w["x0"], w["x1"], w["top"], w["bottom"]) for w in raw]
            sizes = [w["size"] for w in raw]
            for hx0, hx1 in _halves(page):
                idx = [i for i, w in enumerate(words) if hx0 <= w.cx < hx1]
                lines = pdftools.group_lines([words[i] for i in idx], tol=2.5)
                heads = []
                for line in lines:
                    toks = [w.text.lower() for w in line.words]
                    for j in range(len(toks) - 3):
                        if toks[j:j + 4] != HEAD[:4]:
                            continue
                        if j + 5 < len(toks) and toks[j + 4] == "in" and re.fullmatch(r"20\d\d", toks[j + 5]):
                            heads.append((line.words[j], int(toks[j + 5]), line.words[j + 5].x1))
                        elif j + 4 == len(toks):  # "How places were offered" with no year (RBKC 2026 brochure)
                            heads.append((line.words[j], default_year, line.words[j + 3].x1))
                # the school: the largest-font line in this half that looks like a school name
                big = max((sizes[i] for i in idx), default=0)
                title_words = sorted((words[i] for i in idx if sizes[i] >= big - 0.5), key=lambda w: (w.top, w.x0))
                title = " ".join(w.text for w in title_words)
                pan = None
                half = [words[i] for i in idx]
                for k, w in enumerate(half):
                    if w.text.lower() == "admission" and k + 1 < len(half) and half[k + 1].text.lower() == "number":
                        below = [v for v in half if re.fullmatch(r"\d{1,3}", v.text) and 0 < v.top - w.bottom < 25
                                 and abs(v.x0 - w.x0) < 15]
                        if below:
                            pan = int(min(below, key=lambda v: v.top).text)
                            break
                if not heads:
                    info = (title, pan) if pan is not None else info
                    continue
                if pan is None and info is not None and info[0] == title:
                    pan = info[1]  # Hammersmith & Fulham: the admission number is on the school's previous page
                segs = [s for l in lines for s in pdftools.segments(l, gap=12)]
                for head, year, head_x1 in heads:
                    col_x0 = head.x0 - 4
                    right = [s.x0 for s in segs if s.x0 > max(head_x1 + 40, col_x0 + 150) and abs(s.top - head.top) < 400]
                    col_x1 = min(right) - 2 if right else hx1
                    col = pdftools.group_lines([w for w in (words[i] for i in idx)
                                                if col_x0 <= w.x0 < col_x1 and head.top - 90 < w.top < head.top + 260],
                                               tol=2.5)
                    before = [l.text for l in col if l.top < head.top - 1]
                    body = []
                    for l in col:
                        if l.top <= head.top + 1:
                            continue
                        if body and STOP_RE.match(l.text):
                            break
                        body.append(l.text)
                    out.append({"title": title, "year": year, "before": before, "body": body, "pan": pan})
    return out


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title.replace("•", " ")).strip()
    if title.isupper():
        title = title.title().replace("Of ", "of ").replace("And ", "and ").replace("Ce ", "CE ").replace("'S", "'s")
    return title


def _record(panel: dict) -> dict | None:
    name = _clean_title(panel["title"])
    if NOT_TITLE.match(name) or len(name.split()) < 2 or len(name) > 90 or ":" in name or " Site" in name:
        return None
    text = " ".join(panel["body"])
    context = " ".join(panel["before"][-4:] + panel["body"])
    apps = APPS_RE.search(context)
    if apps is None:
        m = re.search(r"applications\s+submitted\s*$", " ".join(panel["before"][-3:]), re.I)
        nums = [t for t in panel["before"][-2:] if re.fullmatch(r"\d+", t.strip())]
        apps = int(nums[-1]) if m is None and nums else None
    else:
        apps = int(apps.group(1))
    dists = DIST_RE.findall(text)
    all_offered = bool(ALL_RE.search(text))
    criteria = [{"label": m.group(1).strip(), "total": int(m.group(2))} for line in panel["body"]
                if (m := CRIT_RE.match(line.strip())) and not re.search(r"applications", m.group(1), re.I)]
    notes = [f"From the \"How places were offered in {panel['year']}\" panel of the council's primary admissions "
             f"brochure: \"{text[:400]}\""]
    max_distance = float(dists[-1]) if dists and not all_offered else None
    if dists and all_offered:
        notes.append(f"All applicants were offered, although a last distance of {dists[-1]} miles is printed.")
    if len(dists) > 1:
        notes.append("Several distances are printed; the last one (normally the final, distance criterion) is "
                     "recorded.")
    faith = re.search(r"Catholic|\bRC\b|C of E|CofE|\bCE\b|\bChurch\b|St\.? [A-Z]|Holy|Oratory|Jewish|"
                      r"Sacred Heart|Our Lady|\bChrist\b|Saint|Servite", name)
    allocation = "faith_then_distance" if faith else "distance"
    if re.search(r"random|lottery", text, re.I):
        allocation = "mixed"
        notes.append("Some places were allocated at random, so distance does not decide every place.")
    return bc.primary_record(name, panel["year"], pan=panel["pan"], applications=apps, criteria=criteria, max_distance=max_distance,
                             all_offered=all_offered, allocation=allocation, notes=notes)


def parse(la_code: str, paths: dict[str, "Path"]) -> tuple[list[dict], list[str]]:  # noqa: F821
    out, skipped = [], []
    seen: dict[tuple[str, int], dict] = {}
    for doc in BROCHURES[la_code]:
        default = doc.get("data_year") or int(re.search(r"(20\d\d)", doc["cache"]).group(1)) - 1
        for panel in _panels(paths[doc["cache"]], default):
            rec = _record(panel)
            if rec is None:
                skipped.append(f"{la_code} {doc['cache']}: panel under non-school title {panel['title'][:60]!r}")
                continue
            key = (rec["name"], rec["year"])
            if key in seen:
                skipped.append(f"{la_code} {doc['cache']}: second panel for {rec['name']} {rec['year']} ignored")
                continue
            seen[key] = rec
            out.append(rec)
    return out, skipped
