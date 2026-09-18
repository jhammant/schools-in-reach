"""Westminster (LA 213), Kensington and Chelsea (LA 207) and Hammersmith and
Fulham (LA 205), secondary: parse "How places were offered for each school in
the Bi-borough area" (Westminster and Kensington & Chelsea, one shared document
per year, 2022-2026) and "How places were offered for LBHF secondary schools"
(Hammersmith & Fulham, 2022-2025; 2022 is an Internet Archive copy, removed from
lbhf.gov.uk). Both use the same template: a heading
per school with "Places available = N (Applications received = M)", then a
criterion table whose "Offers" cells are sentences such as "87 offers up to
0.519 of a mile straight-line distance", sometimes laid out in ability or
faith bands across several columns. The shared document is split by its
"Kensington and Chelsea Secondary Schools" / "Westminster Secondary Schools"
section headings.

The shared document is published by both councils; rbkc.gov.uk answers
automated requests with a bot-protection challenge, so the copies on
westminster.gov.uk are used.

Cells wrap over several lines, so the table is read from pdfplumber word
positions: each criterion label (left column) owns the words between the
midpoints to its neighbouring labels, and in banded tables each word belongs to
the band heading above it. Every "up to X miles" in a cell is the last
distance offered under that criterion (and band); a school with more than one
becomes one group per criterion/band.
"""

from __future__ import annotations

import re

import b2_common as bc
import pdftools

SECTIONS = {"Kensington and Chelsea": "207", "Kensington & Chelsea": "207", "Westminster": "213",
            "Hammersmith & Fulham": "205", "Hammersmith and Fulham": "205"}
WCC = "https://www.westminster.gov.uk/"
BIBOROUGH_DOCS = {
    2022: {"cache": "sec_2022.pdf", "url": WCC + "media/document/bi-borough-secondary-school-admissions-2022"},
    2023: {"cache": "sec_2023.pdf",
           "url": WCC + "media/document/how-places-were-offered-in-westminster-and-kensington-and-chelsea"},
    2024: {"cache": "sec_2024.pdf", "url": WCC + "media/document/places-offered-at-bi-borough-secondary-schools-1-march-2024"},
    2025: {"cache": "sec_2025.pdf",
           "url": WCC + "media/document/how-places-were-offered-at-bi-borough-secondary-schools-3-march-2025"},
    2026: {"cache": "sec_2026.pdf", "url": WCC + "sites/default/files/media/documents/"
                                               "how-places-were-offered-at-bi-borough-secondary-schools-2-march-2026.pdf"},
}
LBHF = "https://www.lbhf.gov.uk/sites/default/files/"
HF_DOCS = {
    2022: {"cache": "wb-secondary-offered-2022.pdf",
           "url": "https://web.archive.org/web/20220421112405id_/" + LBHF +
                  "section_attachments/how-hf-school-places-were-offered-2022.pdf"},
    2023: {"cache": "secondary-offered-2023.pdf", "url": LBHF + "section_attachments/how_lbhf_school_places_were_offered_2023.pdf"},
    2024: {"cache": "secondary-offered-2024.pdf", "url": LBHF + "2024-03/secondary-school-allocations-places-2024.pdf"},
    2025: {"cache": "secondary-offered-2025.pdf", "url": LBHF + "2025-02/how-lbhf-school-places-were-offered-2025_0.pdf"},
}
MANUAL_ALIASES = {
    "213": {
        # Two open URNs contain "Marylebone": the source names are resolved explicitly.
        bc.alias_key("St Marylebone School"): ("137353", "GIAS: The St Marylebone CofE School (W1U 5BA)"),
        bc.alias_key("St Marylebone CE School"): ("137353", "GIAS: The St Marylebone CofE School (W1U 5BA)"),
        bc.alias_key("Marylebone Boys' School"):
            ("140884", "free school opened 01-09-2014 at W2 1QZ, now named Marylebone Academy in GIAS"),
        # Reception (brochure) names that GIAS spells differently
        bc.alias_key("St. Augustine's C of E Primary School"):
            ("101125", "GIAS: St Augustines Federated Schools: CofE Primary School (NW6 5XA)"),
        bc.alias_key("St. Matthew's C of E School"): ("101138", "GIAS: St Matthew's School, Westminster (SW1P 2DG)"),
    },
    "205": {
        bc.alias_key("Fulham Cross Girls' School"):
            ("139365", "GIAS: Fulham Cross Girls' School and Language College (SW6 6BP)"),
        bc.alias_key("St Thomas of Canterbury"):
            ("152441", "GIAS: St Thomas of Canterbury Catholic Primary School (open academy URN)"),
    },
    "207": {},
}
DISTANCE_NOTES = ("Distances are published as \"up to X miles (straight-line distance)\" for the last offer under "
                  "each criterion; the admissions brochures state distance is measured in a straight line from the "
                  "home address point to the school's address point.")

UNIT = r"(?:miles?|of\s+a\s+mile)"
DIST_RE = re.compile(rf"up\s+to\s+(?:a\s+distance\s+of\s+)?(\d+\.\d+)(?:\s*{UNIT})?|"
                     rf"up\s+to\s+(?:a\s+distance\s+of\s+)?(\d+)\s*{UNIT}|(\d+\.\d+)\s*{UNIT}", re.I)
OFFERS_RE = re.compile(r"(\d+)\s+offers?\b", re.I)
HEADER_RE = re.compile(r"Places available\s*=\s*(\d+)\s*\(Applications received\s*=\s*(\d+)\)")
FAITH_RE = re.compile(r"Catholic|\bCE\b|C of E|Church|Oratory|Sacred Heart|Grey Coat|St Marylebone|Lady Margaret|"
                      r"Fulham Boys|St Augustine|St George|Cardinal Vaughan|St Thomas More", re.I)


def _stream(path) -> list[tuple[pdftools.Line, list[pdftools.Word]]]:
    """All lines of the document in reading order, with page-offset y coordinates."""
    out = []
    with bc.open_pdf(path) as pdf:
        for pno, page in enumerate(pdf.pages):
            offset = pno * 2000.0
            words = [pdftools.Word(w.text, w.x0, w.x1, w.top + offset, w.bottom + offset)
                     for w in pdftools.page_words(page)]
            for line in pdftools.group_lines(words, tol=2.5):
                out.append(line)
    return out


def _blocks(lines: list[pdftools.Line]) -> list[dict]:
    blocks, section = [], None
    for line in lines:
        text = line.text
        m = re.match(r"^\s*(Kensington (?:and|&) Chelsea|Westminster|Hammersmith (?:&|and) Fulham) Secondary Schools",
                     text)
        if m:
            section = SECTIONS[m.group(1)]
            continue
        h = HEADER_RE.search(text)
        if h:
            places = next(w for w in line.words if w.text == "Places")
            name = " ".join(w.text for w in line.words if w.x1 < places.x0 - 5).strip()
            blocks.append({"name": name, "la": section, "pan": int(h.group(1)), "apps": int(h.group(2)),
                           "lines": []})
            continue
        if blocks:
            blocks[-1]["lines"].append(line)
    return blocks


def _parse_block(blk: dict) -> dict:
    lines = blk["lines"]
    end = next((i for i, l in enumerate(lines) if l.text.startswith(("For further information", "Contained within"))),
               len(lines))
    body = lines[:end]
    text = " ".join(l.text for l in body)
    out = {"all_offered": "All applicants who applied were offered a place" in text, "groups": [], "criteria": [],
           "text": text}
    ehcp = re.search(r"(\d+) places? for (?:a )?pupils? with (?:a final |an )?Education", text)
    out["ehcp"] = int(ehcp.group(1)) if ehcp else None
    crit_i = next((i for i, l in enumerate(body) if l.words[0].text == "Criterion"), None)
    if crit_i is None:
        return out
    offers_w = next((w for w in body[crit_i].words if w.text == "Offers"), None)
    boundary = (offers_w.x0 - 3) if offers_w else 240.0
    band_cols: list[tuple[str, float]] = []
    rest = body[crit_i + 1:]
    for i, l in enumerate(rest):
        bands = [(f"Band {l.words[j + 1].text}", (w.x0 + l.words[j + 1].x1) / 2) for j, w in enumerate(l.words[:-1])
                 if w.text == "Band" and re.fullmatch(r"[A-D1-4]", l.words[j + 1].text) and w.x0 > boundary - 60]
        if len(bands) >= 2 and all(w.x0 > boundary - 60 for w in l.words):
            band_cols = bands
            boundary = min(b[1] for b in bands) - 60
            rest = rest[:i] + rest[i + 1:]
            break
    labels: list[dict] = []
    value_words: list[pdftools.Word] = []
    for l in rest:
        # a label is the leading words of a line up to the table's value column, or up to an "N offers" phrase
        # that starts left of it (e.g. "Band A 54 offers total - ...")
        split = next((j for j, w in enumerate(l.words[:-1]) if j and re.fullmatch(r"\d+", w.text)
                      and l.words[j + 1].text.lower().startswith("offer") and w.x0 < boundary + 40), None)
        if split is not None and not band_cols:
            lw, vw = l.words[:split], l.words[split:]
        else:
            lw = [w for w in l.words if w.x1 <= boundary]
            vw = [w for w in l.words if w.x1 > boundary]
        value_words.extend(vw)
        if not lw:
            continue
        continuation = re.match(r"^(Random tie-breaker|criterion$|\(|those qualifying)", " ".join(w.text for w in lw))
        if labels and ((l.top - labels[-1]["bottom"] < 4 and not band_cols) or continuation):
            labels[-1]["words"] += lw
            labels[-1]["bottom"] = max(w.bottom for w in l.words)
        else:
            labels.append({"words": lw, "top": l.top, "bottom": max(w.bottom for w in l.words)})
    if not labels:
        return out
    top_bound = body[crit_i].top + 8
    bottom_bound = (lines[end].top if end < len(lines) else rest[-1].top + 20) if rest else top_bound
    for k, lab in enumerate(labels):
        lo = top_bound if k == 0 else (labels[k - 1]["bottom"] + lab["top"]) / 2
        hi = bottom_bound if k == len(labels) - 1 else (lab["bottom"] + labels[k + 1]["top"]) / 2
        label = " ".join(w.text for w in lab["words"])
        cell_words = [w for w in value_words if lo <= w.cy < hi]
        cells: dict[str, list[pdftools.Word]] = {}
        for w in cell_words:
            band = min(band_cols, key=lambda b: abs(b[1] - w.cx))[0] if band_cols else ""
            cells.setdefault(band, []).append(w)
        counts = {}
        for band, words in cells.items():
            cell_text = " ".join(w.text for w in sorted(words, key=lambda w: (round(w.top), w.x0)))
            dists = DIST_RE.findall(cell_text)
            found = OFFERS_RE.findall(cell_text)
            if found:
                counts[band or "All"] = sum(int(n) for n in found)
            if dists:
                group = f"{label} ({band})" if band else label
                value = next(v for v in dists[-1] if v)
                out["groups"].append((group, float(value), cell_text))
        if counts:
            out["criteria"].append({"label": label, "counts": counts, "total": sum(counts.values())})
    return out


def _record(year: int, blk: dict) -> dict:
    parsed = _parse_block(blk)
    notes: list[str] = []
    groups = parsed["groups"]
    criteria = parsed["criteria"]
    if parsed["ehcp"] is not None:
        criteria = [{"label": "Education, Health and Care Plan", "counts": {"All": parsed["ehcp"]},
                     "total": parsed["ehcp"]}] + criteria
    text = parsed["text"]
    if parsed["all_offered"]:
        notes.append("\"All applicants who applied were offered a place.\"")
        return bc.secondary_record(blk["name"], year, pan=blk["pan"], applications=blk["apps"], criteria=criteria,
                                   all_offered=["All"], allocation="faith_then_distance" if FAITH_RE.search(
                                       blk["name"]) else "distance", notes=notes)
    for group, value, cell in groups:
        notes.append(f"{group}: \"{re.sub(r'\s+', ' ', cell)[:220]}\"")
    random = re.search(r"random", text, re.I)
    if len(groups) == 1:
        names, max_distance = ["All"], {"All": groups[0][1]}
    elif groups:
        names = [g[0] for g in groups]
        if len(set(names)) != len(names):
            names = [f"{g[0]} #{i + 1}" for i, g in enumerate(groups)]
        max_distance = dict(zip(names, (g[1] for g in groups)))
    else:
        names, max_distance = ["All"], {"All": None}
        notes.append("No distance is published for this school: places were filled under higher criteria or by "
                     "random allocation.")
    if len(names) > 1 or (random and not groups):
        allocation = "mixed"
    elif re.search(r"priority (?:area|zone)", text, re.I) and not FAITH_RE.search(blk["name"]):
        allocation = "catchment_then_distance"
    elif FAITH_RE.search(blk["name"]):
        allocation = "faith_then_distance"
    else:
        allocation = "distance"
    if random:
        notes.append("Some places are allocated by random allocation (lottery) rather than distance.")
    if len(names) > 1:
        notes.append("The school publishes a separate last distance for each criterion/band, shown as groups.")
    return bc.secondary_record(blk["name"], year, pan=blk["pan"], applications=blk["apps"], groups=names,
                               criteria=criteria, max_distance=max_distance, allocation=allocation, notes=notes)


def parse(docs: dict, paths: dict) -> dict[str, list[dict]]:
    """Returns {la_code: [secondary records]}."""
    out: dict[str, list[dict]] = {}
    for year, doc in sorted(docs.items()):
        blocks = _blocks(_stream(paths[year]))
        if len(blocks) < 10:
            raise SystemExit(f"biborough {doc['cache']}: only {len(blocks)} schools")
        for blk in blocks:
            la = blk["la"] or "205"
            out.setdefault(la, []).append(_record(year, blk))
    return out
