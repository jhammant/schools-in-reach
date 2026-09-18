"""Lambeth (LA 208): parse the council's "How offers were made for Lambeth
secondary/primary schools on National Offer Day" pages (lambeth.gov.uk).

Secondary (2024, 2025, 2026 entry): each year's page links one short PDF per
school (16 per year) in a common council template: on-time applications,
PAN, and either "All applicants received a place at the school or a higher
preferred offer" or a criteria breakdown with the last distance offered.
Three schools band by a Year 6 test (Dunraven School, Lilian Baylis
Technology School, The Norwood School) and publish a last distance per band;
La Retraite publishes separate last distances for Catholic and non-Catholic
applicants. The 2021-2023 pages now redirect to the 2024/2025 pages, so
earlier years are not available.

Primary / Reception (2024, 2025, 2026 entry): per school type -- community
schools as one table, academies / foundation / voluntary-aided schools as
per-school text blocks ("PAN (Published Admissions Number): ...", "Distance
for last child offered: ... metres (straight line)"). 2024 and 2026 are PDFs;
2025 is published as HTML pages.

Distances are published in metres (straight line unless stated, e.g. Julian's
and some voluntary-aided schools use walking routes) and converted to miles.
"""

from __future__ import annotations

import html as htmllib
import re
from pathlib import Path

import common

LA_CODE = "208"
LA_NAME = "Lambeth"
OGL = "Open Government Licence v3.0"
SITE = "https://www.lambeth.gov.uk"
SEC_BASE = f"{SITE}/schools-and-education/school-admissions-and-appeals/secondary-school-admissions"
PRI_BASE = f"{SITE}/schools-and-education/school-admissions-and-appeals/primary-school-admissions"

MANUAL_ALIASES: dict[str, tuple[str, str]] = {}

SEC_PAGES = {
    2026: f"{SEC_BASE}/how-offers-were-made-lambeth-secondary-schools-national-offer-day-2-march-2026",
    2025: f"{SEC_BASE}/how-offers-were-made-lambeth-secondary-schools-national-offer-day-3-march-2025",
    2024: f"{SEC_BASE}/how-offers-were-made-lambeth-secondary-schools-national-offer-day-1-march-2024",
}
PRI_2025 = f"{PRI_BASE}/how-offers-were-made-lambeth-primary-schools-national-offer-day-16-april-2025"
PRI_DOCS = {
    2026: [("community", f"{SITE}/sites/default/files/2026-04/nod-rec26-how-offers-were-made-community-schools.pdf"),
           ("blocks", f"{SITE}/sites/default/files/2026-04/nod-rec26-how-offers-were-made-academies%20%282%29.pdf"),
           ("blocks", f"{SITE}/sites/default/files/2026-04/nod-rec26-how-offers-were-made-foundation-schools.pdf"),
           ("blocks", f"{SITE}/sites/default/files/2026-04/nod-rec-26-how-offers-were-made-voluntary-aid.pdf")],
    2025: [("community_html", f"{PRI_2025}/lambeth-community-schools"),
           ("blocks_html", f"{PRI_2025}/lambeth-academies"),
           ("blocks_html", f"{PRI_2025}/lambeth-foundation-schools"),
           ("blocks_html", f"{PRI_2025}/lambeth-voluntary-aided-schools")],
    2024: [("community", f"{SITE}/sites/default/files/2024-11/"
                         "How%20offers%20were%20made%20Lambeth%20community%20schools%20and%20Oasis%20Academy%20Johanna%202024-25.pdf"),
           ("blocks", f"{SITE}/sites/default/files/2024-04/how%20offers%20were%20made%20academies.pdf"),
           ("blocks", f"{SITE}/sites/default/files/2024-04/how%20offers%20were%20made%20foundation%20schools.pdf"),
           ("blocks", f"{SITE}/sites/default/files/2024-04/how%20offers%20were%20made%20voluntary%20aid%20schools.pdf")],
}

SOURCES = [{"title": f"Lambeth Council: How offers were made for Lambeth secondary schools on National Offer Day "
                     f"({y}; one PDF per school linked from this page)", "url": u, "licence": OGL}
           for y, u in SEC_PAGES.items()] + \
          [{"title": f"Lambeth Council: How offers were made for Lambeth primary schools on National Offer Day "
                     f"({y}, {'community schools' if kind.startswith('community') else 'academies / foundation / voluntary-aided schools'})",
            "url": u, "licence": OGL}
           for y, docs in PRI_DOCS.items() for kind, u in docs]

DISTANCE_METHOD = "mixed"
DISTANCE_NOTES = ("The council's tables give the last distance offered in metres, \"straight line\" for community "
                  "schools and most others; some foundation and voluntary-aided schools state a walking route "
                  "instead (e.g. Julian's Primary School \"shortest walking route\", and \"safest walking route\" / "
                  "\"walking distance\" for some church schools), recorded per school in notes. Figures are as at "
                  "National Offer Day and cover on-time applications only.")

MISSING_NOTE = ("Secondary: 2024-2026 entry only (the council's 2021-2023 pages now redirect to later years); "
               "schools where \"all applicants received a place at the school or a higher preferred offer\" "
               "publish no distance. Primary: 2024-2026 entry; criteria counts are recorded for community "
               "schools only (other schools' criteria lists are school-specific free text). A few church "
               "schools publish distances by walking route or with inconsistent units (see notes).")

FAITH_RE = re.compile(r"Catholic|Church of England|\bCE\b|St\.? |Saint |La Retraite|Bishop|Christ Church|Corpus Christi"
                      r"|Holy|Sacred|Our Lady", re.I)
ALL_OFFERED_RE = re.compile(r"All applicants received a place", re.I)


def _slug(url: str) -> str:
    name = re.sub(r"[^A-Za-z0-9.]+", "-", url.rsplit("/", 1)[-1]).strip("-")
    return name if name.endswith((".pdf", ".html")) else f"{name}.html"


def _html_lines(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<main.*?</main>", raw, re.S)
    body = m.group(0) if m else raw
    body = re.sub(r"<(?:p|h[1-6]|li|tr|br|div)[^>]*>", "\n", body)
    body = re.sub(r"</t[dh]>", "  |  ", body)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", body)).replace("\xa0", " ")
    return [re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines() if l.strip()]


def _m(value: str) -> float:
    return common.miles(float(value), from_unit="metres")


# ------------------------------------------------------------------ secondary

def _secondary_links(page: Path) -> list[tuple[str, str]]:
    raw = page.read_text(encoding="utf-8", errors="replace")
    out = []
    for href, label in re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', raw, re.S):
        name = re.sub(r"\s*\(PDF.*$", "", htmllib.unescape(re.sub(r"<[^>]+>", "", label))).replace("\xa0", " ").strip()
        out.append((href if href.startswith("http") else SITE + href, name))
    return out


BAND_ROW_RE = re.compile(r"^\s*(Bursary|Z|\d(?:\.\d)?)\s+(.*)$")


def _parse_secondary_doc(text: str, name: str, year: int) -> dict:
    notes: list[str] = []
    apps_m = re.search(r"applications received\s*[–=-]\s*(\d[\d,]*)", text, re.I)
    pan_m = re.search(r"\bPAN\s*[–-]\s*(\d+)", text) or re.search(r"\(PAN\) for Year 7 is (\d+)", text)
    groups, max_distance, all_offered = ["All"], {"All": None}, []
    allocation = "faith_then_distance" if FAITH_RE.search(name) else "distance"
    band_rows = []
    for line in text.splitlines():
        bm = BAND_ROW_RE.match(line)
        toks = bm.group(2).split() if bm else []
        # band rows end "... <last distance> <SEND or total>"; band Z (children who did not sit the test) is
        # never reached, so skip it
        if bm and bm.group(1) != "Z" and len(toks) >= 6 and re.fullmatch(r"\d+(?:\.\d+)?|n/a", toks[-2]):
            band_rows.append((bm.group(1), None if toks[-2] == "n/a" else toks[-2]))
    last_lines = [(m.start(), m.group(1), m.group(2)) for m in
                  re.finditer(r"^\s*((?:Last|last) distance[^\n]*?)\s+(\d+(?:\.\d+)?)\s*$", text, re.M)]
    if not band_rows and not last_lines and "Max. distance" in text:
        # single-row "Offers per criterion" table (e.g. The Elmgreen School 2024): LAC, siblings, med/soc,
        # staff, distance count, max distance; later tables in the same PDF repeat previous years, so use the first
        rm = re.search(r"^\s*\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)\s*$", text, re.M)
        if rm:
            last_lines = [(rm.start(), "Max. distance (straight line)", rm.group(1))]
    if band_rows:
        groups = [f"Band {b}" for b, _ in band_rows]
        max_distance = {f"Band {b}": (_m(d) if d else None) for b, d in band_rows}
        allocation = "mixed"
        notes.append("Ability banding by Year 6 test: places are split across bands and ranked by straight-line "
                     "distance within each band; last distance offered is published per band (\"Bursary\" places "
                     "are awarded by audition).")
    elif ALL_OFFERED_RE.search(text) and not last_lines:
        all_offered = ["All"]
        notes.append("All applicants received a place at the school or a higher preferred offer.")
    elif "Non-Catholic" in text and len(last_lines) >= 2:
        split = text.index("Non-Catholic")
        cath = [l for l in last_lines if l[0] < split and "Furthest" not in l[1]]
        other = [l for l in last_lines if l[0] > split]
        groups = ["Catholic", "Non-Catholic"]
        max_distance = {"Catholic": _m(cath[-1][2]) if cath else None,
                        "Non-Catholic": _m(other[-1][2]) if other else None}
        notes.append("Separate last distances are published for Catholic applicants (final criterion reached) "
                     "and for non-Catholic applicants.")
    elif last_lines:
        max_distance = {"All": _m(last_lines[0][2])}
    else:
        notes.append("No last-distance figure published in this school's National Offer Day document.")
    criteria = []
    if not band_rows:
        for label, count in re.findall(r"^\s*(LAC|Looked After and previously Looked After Children|Sibling|medsoc|"
                                       r"Medical/social|children of staff|Staff Children|distance|Distance|"
                                       r"Pupil Premium|Children at Oasis Johanna|SEN/EHCP|SEND)\s+(\d+)\s*$",
                                       text, re.M):
            criteria.append({"label": label, "total": int(count)})
    return {"name": name, "year": year, "pan": int(pan_m.group(1)) if pan_m else None,
            "applications": int(apps_m.group(1).replace(",", "")) if apps_m else None, "groups": groups,
            "criteria": criteria,
            "max_distance": max_distance, "all_offered": all_offered, "non_preference_offers": None,
            "total_offers": None, "allocation": allocation, "notes": notes}


def _build_secondary() -> list[dict]:
    records = []
    for year, url in SEC_PAGES.items():
        page = common.fetch(LA_CODE, {"cache": f"secondary-{year}.html", "url": url, "kind": "html"})
        links = _secondary_links(page)
        if len(links) < 10:
            raise SystemExit(f"lambeth: only {len(links)} school PDFs linked for secondary {year}")
        for href, name in links:
            path = common.fetch(LA_CODE, {"cache": f"sec{year}-{_slug(href)}", "url": href, "kind": "pdf"})
            text = common.pdftotext(path)
            # trust the year printed in the document over the page it is linked from (the 2024 page links
            # Bishop Thomas Grant's 2023 document)
            ym = re.search(r"Secondary Transfer (20\d\d)", text)
            doc_year = int(ym.group(1)) if ym else year
            rec = _parse_secondary_doc(text, name, doc_year)
            if doc_year != year:
                rec["notes"].append(f"Linked from the council's {year} page, but the document itself is headed "
                                    f"Secondary Transfer {doc_year}; recorded under {doc_year}.")
            records.append(rec)
    return records


# ------------------------------------------------------------------ primary

COMMUNITY_ROW_RE = re.compile(r"^(?P<name>[A-Z][^|]*?)\s{2,}(?P<pan>\d+)\s+(?P<apps>\d+)\s+(?P<send>\d+)\s+(?P<rest>.*)$")
COMMUNITY_LABELS = ["Looked after / previously looked after children", "Siblings", "Medical/social",
                    "Children of staff", "Distance"]


def _community_record(name, pan, apps, rest, year) -> dict:
    notes: list[str] = []
    max_distance, all_offered, criteria = None, False, []
    if ALL_OFFERED_RE.search(rest):
        all_offered = True
        notes.append("All applicants received a place at the school or a higher preferred offer.")
    else:
        toks = rest.split()
        if toks:
            max_distance = _m(toks[-1])
            if len(toks) == 6:
                criteria = [{"label": l, "total": int(t)} for l, t in zip(COMMUNITY_LABELS, toks[:5])]
            else:
                notes.append("Some criterion cells are blank in the source table, so the criteria breakdown is "
                             "not recorded for this school/year.")
    return {"name": name.strip(), "year": year, "pan": int(pan), "applications": int(apps), "total_offers": None,
            "criteria": criteria, "max_distance": max_distance, "all_offered": all_offered,
            "non_preference_offers": None, "allocation": "distance", "notes": notes}


SITE_RE = re.compile(r"^(?P<base>.*?)\s*\((?P<site>[^)]*?)\s*site\)$", re.I)


def _merge_sites(records: list[dict]) -> list[dict]:
    """Henry Cavendish Primary School publishes one row per site (Balham, Streatham) but has a single URN:
    combine them into one record, keeping each site's figures in notes rather than picking one cut-off."""
    out: list[dict] = []
    by_base: dict[str, list[dict]] = {}
    for r in records:
        m = SITE_RE.match(r["name"])
        if m:
            by_base.setdefault(m.group("base"), []).append({**r, "_site": m.group("site")})
        else:
            out.append(r)
    for base, rows in by_base.items():
        parts = []
        for r in rows:
            dist = "all applicants offered" if r["all_offered"] else \
                f"last distance offered {r['max_distance']} miles" if r["max_distance"] is not None else "no distance"
            parts.append(f"{r['_site']} site: PAN {r['pan']}, {r['applications']} on-time applications, {dist}")
        out.append({"name": base, "year": rows[0]["year"], "pan": sum(r["pan"] for r in rows), "applications": None,
                    "total_offers": None, "criteria": [], "max_distance": None,
                    "all_offered": all(r["all_offered"] for r in rows), "non_preference_offers": None,
                    "allocation": "distance",
                    "notes": ["Two sites admitted separately, each with its own cut-off (no single school-wide "
                              "distance): " + "; ".join(parts) + "."]})
    return out


def _parse_community_pdf(text: str, year: int) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = COMMUNITY_ROW_RE.match(line.strip())
        if m and "Primary school admissions" not in line:
            out.append(_community_record(m.group("name"), m.group("pan"), m.group("apps"), m.group("rest"), year))
    return _merge_sites(out)


def _parse_community_html(lines: list[str], year: int) -> list[dict]:
    out = []
    for line in lines:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 4 and cells[1].isdigit() and cells[2].isdigit() and cells[3].isdigit():
            out.append(_community_record(cells[0], cells[1], cells[2], " ".join(cells[4:]), year))
    return _merge_sites(out)


DIST_LINE_RE = re.compile(r"Distance for last child[^:]*:\s*(\d+(?:\.\d+)?)\s*(metres|miles)?\.?\s*(?:\(([^)]*)\))?", re.I)
LABEL_LINE_RE = re.compile(r"^(PAN \(|Number of on time|Breakdown|All applicants|Distance for|SEND|Criteria|\d+\.|"
                           r"Streatham Site|West Norwood Site|Primary school admissions|How offers were made|"
                           r"Lambeth (academies|foundation|voluntary|community)|Data showing|Overview|Previous|Next)", re.I)


def _parse_blocks(lines: list[str], year: int) -> list[dict]:
    starts = [i for i, l in enumerate(lines) if l.startswith("PAN (Published Admissions Number)")]
    out = []
    for n, i in enumerate(starts):
        j = i - 1
        while j >= 0 and (LABEL_LINE_RE.match(lines[j]) or re.match(r"^[\s\d.–-]+$", lines[j])
                          or lines[j].endswith((" 0", " 1"))):
            j -= 1
        name = lines[j] if j >= 0 else "?"
        end = starts[n + 1] - 1 if n + 1 < len(starts) else len(lines)
        block = "\n".join(lines[i:end])
        pan_line = lines[i].split(":", 1)[1]
        pans = [int(x) for x in re.findall(r"\d+", pan_line.split("Number of")[0])]
        apps_m = re.search(r"Number of on time applications(?: received)?:\s*(\d+)", block)
        dists = DIST_LINE_RE.findall(block)
        notes: list[str] = []
        if len(pans) > 1:
            notes.append(f"Two sites with separate admission numbers: {pan_line.split('Number of')[0].strip()}.")
        max_distance = None
        all_offered = bool(ALL_OFFERED_RE.search(block)) and not dists
        if all_offered:
            notes.append("All applicants received a place at the school or a higher preferred offer.")
        if dists:
            value, unit, method = dists[-1]
            v = float(value)
            if (unit or "").lower() == "miles" and v > 100:
                notes.append(f"Source prints \"{value} miles\", evidently metres; treated as metres.")
            max_distance = common.miles(v, from_unit="metres")
            if method:
                notes.append(f"Distance measured by {method}.")
            if len(dists) > 1:
                notes.append("Several last-distance figures are published; the last one listed is used: " +
                             "; ".join(f"{d[0]} {d[1] or 'metres'}" + (f" ({d[2]})" if d[2] else "") for d in dists) + ".")
        elif not all_offered:
            notes.append("No last-distance figure published for this school/year.")
        allocation = "faith_then_distance" if FAITH_RE.search(name) else "distance"
        out.append({"name": name, "year": year, "pan": sum(pans) if pans else None,
                    "applications": int(apps_m.group(1)) if apps_m else None, "total_offers": None, "criteria": [],
                    "max_distance": max_distance, "all_offered": all_offered, "non_preference_offers": None,
                    "allocation": allocation, "notes": notes})
    return out


def _build_primary() -> list[dict]:
    records = []
    for year, docs in PRI_DOCS.items():
        for kind, url in docs:
            if kind.endswith("html"):
                path = common.fetch(LA_CODE, {"cache": f"pri{year}-{_slug(url)}", "url": url, "kind": "html"})
                lines = _html_lines(path)
                recs = _parse_community_html(lines, year) if kind == "community_html" else _parse_blocks(lines, year)
            else:
                path = common.fetch(LA_CODE, {"cache": f"pri{year}-{_slug(url)}", "url": url, "kind": "pdf"})
                text = common.pdftotext(path)
                recs = _parse_community_pdf(text, year) if kind == "community" else \
                    _parse_blocks([l.strip() for l in text.splitlines() if l.strip()], year)
            if not recs:
                raise SystemExit(f"lambeth: no primary rows parsed from {url}")
            records.extend(recs)
    return records


def build() -> tuple[list[dict], list[dict]]:
    return _build_secondary(), _build_primary()
