"""Shared parsers for the admissions-outcome tables published by Achieving for
Children (AfC), which runs school admissions for both Kingston upon Thames
(b3_kingston.py) and Richmond upon Thames (b3_richmond.py). Both boroughs
publish the same two one-page-ish PDF formats (read here via pdftotext
-layout):

1. Secondary: "National Offer Day (NOD) distance offers and final distance
   offers at the end of national coordination (NC)" -- one row per school
   (or per school sub-quota, e.g. "Turing House 20%"), and for each of three
   years a NOD cut-off cell and an end-of-NC cell. Cells are free text:
   "2.624 kms", "All preferences met", "Overseas", "Crit 18 - 3.858 kms",
   "Band 8 - 3.758 kms", "Random alloc within Bands 2&3", "CONTACT THE SCHOOL
   FOR ALLOCATION INFORMATION". Several cells wrap onto the lines above and
   below the row, so cells are assigned to columns by character position.

2. Primary: "How places have been allocated at community infant and primary
   schools over the last three years" -- one row per school per year:
   "<year> (<places>)", six criterion counts, the distance of the last child
   offered under the distance criterion at offer date, the furthest distance
   offered from the waiting list by the end of national coordination, and
   appeals. School names are split over up to three physical lines around
   the year rows, and a couple of rows have their values printed on the line
   above the "<year> (<places>)" label; both are handled below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import common

# ------------------------------------------------------------------ secondary

CELL_RE = re.compile(
    r"CONTACT THE SCHOOL FOR ALLOCATION INFORMATION"
    r"|All preferences met|All prefs met"
    r"|Crit \d+ - \d+(?:\.\d+)? ?kms?"
    r"|Band \d+ - \d+(?:\.\d+)? ?kms?"
    r"|Random alloc within Bands 2&3"
    r"|No further offers made"
    r"|Overseas"
    r"|\d+(?:\.\d+)? ?kms?")
# fragments of a cell wrapped above ("head") or below ("tail") its row
HEAD_RE = re.compile(r"All preferences(?! met)|Random alloc within(?! Bands)|No further offers(?! made)")
TAIL_RE = re.compile(r"Bands 2&3|\bmet\b|\bmade\b")
HEAD_FULL = {"All preferences": "All preferences met", "Random alloc within": "Random alloc within Bands 2&3",
             "No further offers": "No further offers made"}
KM_RE = re.compile(r"(\d+(?:\.\d+)?) ?kms?")


@dataclass
class SecondaryRow:
    name: str
    pan: int | None
    cells: dict[int, str] = field(default_factory=dict)  # column index -> cell text
    name_from_bare_line: bool = False


def _nearest(pos: int, anchors: list[int]) -> int:
    return min(range(len(anchors)), key=lambda i: abs(anchors[i] - pos))


def parse_secondary_table(text: str, anchors: list[int], name_max_col: int = 26,
                          has_pan: bool = False) -> list[SecondaryRow]:
    """anchors: character column where each of the six year cells starts (NOD, NC, NOD, NC, NOD, NC)."""
    rows: list[SecondaryRow] = []
    pending_heads: dict[int, str] = {}
    started = False
    for line in text.splitlines():
        if not line.strip():
            continue
        if re.search(r"School Name", line):
            started = True
            continue
        if not started:
            continue
        if line.lstrip().startswith(("We will not", "You can use", "Historical distance", "there is no",
                                     "to calculate", "application.")):
            break
        cells = [(m.start(), m.group()) for m in CELL_RE.finditer(line)]
        heads = [(m.start(), m.group()) for m in HEAD_RE.finditer(line)]
        name_m = re.match(r"^(\s*)(\S.*?)(?=\s{2,}|$)", line)
        name = None
        if name_m and len(name_m.group(1)) < name_max_col and not CELL_RE.match(name_m.group(2)) \
                and not HEAD_RE.match(name_m.group(2)) and not TAIL_RE.fullmatch(name_m.group(2)):
            name = name_m.group(2).strip()
        pan = None
        if has_pan and name:
            pm = re.match(r"^\s*\S.*?\s{2,}(\d{2,3})(?=\s)", line)
            pan = int(pm.group(1)) if pm else None
        if name and not cells and not heads:
            # a name-only line: either the start of a wrapped name, or its continuation after the data line
            if rows and (not rows[-1].cells or rows[-1].name_from_bare_line):
                rows[-1].name = f"{rows[-1].name} {name}"
            else:
                rows.append(SecondaryRow(name, pan, name_from_bare_line=True))
            continue
        if name:
            rows.append(SecondaryRow(name, pan))
            row = rows[-1]
        elif cells and rows and not rows[-1].cells:
            row = rows[-1]  # data line for a name printed on the line above
        elif heads and not cells:
            for pos, frag in heads:
                pending_heads[_nearest(pos, anchors)] = HEAD_FULL[frag]
            continue
        else:
            continue  # tail fragments ("met", "Bands 2&3") belong to cells already completed via heads
        if len(cells) == len(anchors):
            # a full row: assign in order (identical adjacent phrases such as six "All preferences met" cells
            # are run together with single spaces and drift off the column anchors)
            row.cells = {i: cell for i, (_, cell) in enumerate(cells)}
            cells = []
        for pos, cell in cells:
            if cell.startswith("CONTACT"):
                row.cells = {i: cell for i in range(len(anchors))}
                break
            row.cells[_nearest(pos, anchors)] = cell
        for idx, full in pending_heads.items():
            row.cells.setdefault(idx, full)
        pending_heads = {}
    return rows


def cell_miles(cell: str | None) -> float | None:
    if not cell:
        return None
    m = KM_RE.search(cell)
    return common.miles(float(m.group(1)), from_unit="km") if m else None


def cell_all_offered(cell: str | None) -> bool:
    return bool(cell) and (cell.startswith("All pref") or cell == "Overseas")


def describe_nc(cell: str | None) -> str | None:
    if not cell:
        return None
    mi = cell_miles(cell)
    if mi is not None:
        prefix = cell.split(" - ")[0] + ", " if " - " in cell else ""
        return f"{prefix}{mi} miles"
    return cell.lower()


# ------------------------------------------------------------------ primary

YEAR_ROW_RE = re.compile(r"^(?P<pre>.*?)(?P<year>20\d\d) \((?P<pan>\d+)\)(?P<rest>.*)$")
BARE_YEAR_RE = re.compile(r"^\s*(20\d\d) \((\d+)\)\s*$")
COUNT_RE = re.compile(r"^(?:-|\d+)$")
DIST_CELL_RE = re.compile(r"All prefs met|n/a|\d+(?:\.\d+)?\s*kms?|\d+\.\d+")


@dataclass
class PrimaryRow:
    idx: int
    year: int
    pan: int
    counts: list[int]
    offer_cell: str | None
    waitlist_cell: str | None
    pre: str


def _is_count_line(tokens: list[str]) -> bool:
    return bool(tokens) and all(COUNT_RE.match(t) for t in tokens)


def parse_primary_table(text: str) -> list[dict]:
    """Returns [{'name', 'year', 'pan', 'counts' (6 ints), 'offer_cell', 'waitlist_cell'}] for the
    infant/primary section(s) only (junior-school sections are skipped: they are Year 3, not Reception)."""
    raw = text.splitlines()
    # keep only the infant/primary section: in every edition seen the junior-school section comes last, and a
    # page break inside it can repeat the (stale) infant/primary page heading, so stop at the junior heading
    kept: list[str] = []
    for line in raw:
        if re.search(r"at community junior schools", line):
            break
        kept.append(line)
    lines = []
    in_header = False
    for line in kept:
        if re.search(r"How places have been allocated|Criterion", line):
            in_header = True
        if in_header:
            if "coordination" in line:
                in_header = False
            continue
        if line.strip():
            lines.append(line)

    # merge "values line" + following bare "<year> (<places>)" line
    merged: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        bm = BARE_YEAR_RE.match(nxt)
        if bm and not YEAR_ROW_RE.match(line):
            pre_m = re.match(r"^\s*([A-Za-z][^\d-]*?)?\s{2,}(.*)$", line)
            pre = (pre_m.group(1) or "") if pre_m else ""
            rest = pre_m.group(2) if pre_m else line
            merged.append(f"{pre}  {bm.group(1)} ({bm.group(2)})  {rest}")
            i += 2
            continue
        merged.append(line)
        i += 1

    rows: list[PrimaryRow] = []
    fragments: list[tuple[int, str]] = []
    i = 0
    while i < len(merged):
        line = merged[i]
        m = YEAR_ROW_RE.match(line)
        if not m:
            if not _is_count_line(line.split()):
                fragments.append((i, line.strip()))
            i += 1
            continue
        tokens = m.group("rest").split()
        counts_tok: list[str] = []
        j = 0
        while j < len(tokens) and COUNT_RE.match(tokens[j]) and len(counts_tok) < 6:
            counts_tok.append(tokens[j])
            j += 1
        if len(counts_tok) < 6 and i + 1 < len(merged) and _is_count_line(merged[i + 1].split()):
            extra = merged[i + 1].split()
            counts_tok[1:1] = extra
            i += 1
        rest = " ".join(tokens[j:])
        dist = DIST_CELL_RE.findall(rest)
        counts = [0 if t == "-" else int(t) for t in counts_tok[:6]]
        rows.append(PrimaryRow(i, int(m.group("year")), int(m.group("pan")), counts,
                               dist[0] if dist else None, dist[1] if len(dist) > 1 else None,
                               m.group("pre").strip()))
        i += 1

    groups: list[list[PrimaryRow]] = []
    for r in rows:
        if not groups or r.year <= groups[-1][-1].year:
            groups.append([r])
        else:
            groups[-1].append(r)

    names: list[list[tuple[int, str]]] = [[(r.idx, r.pre) for r in g if r.pre] for g in groups]
    for f_idx, frag in fragments:
        inside = [gi for gi, g in enumerate(groups) if g[0].idx <= f_idx <= g[-1].idx]
        if inside:
            gi = inside[0]
        else:
            after = [gi for gi, g in enumerate(groups) if g[0].idx > f_idx]
            before = [gi for gi, g in enumerate(groups) if g[-1].idx < f_idx]
            cand = []
            if after:
                cand.append((groups[after[0]][0].idx - f_idx, 1, after[0]))
            if before:
                cand.append((f_idx - groups[before[-1]][-1].idx, 0, before[-1]))
            if not cand:
                continue
            gi = sorted(cand, key=lambda c: (c[0], -c[1]))[0][2]
        names[gi].append((f_idx, frag))

    out: list[dict] = []
    for g, name_parts in zip(groups, names):
        parts = common.dedupe([p for _, p in sorted(name_parts)])
        name = re.sub(r"\s+", " ", " ".join(parts)).replace("​", "").strip()
        for r in g:
            out.append({"name": name, "year": r.year, "pan": r.pan, "counts": r.counts,
                        "offer_cell": r.offer_cell, "waitlist_cell": r.waitlist_cell})
    return out


def primary_cell_miles(cell: str | None) -> float | None:
    if not cell or cell in ("All prefs met", "n/a"):
        return None
    m = re.match(r"(\d+(?:\.\d+)?)", cell)
    return common.miles(float(m.group(1)), from_unit="km") if m else None


def primary_records(parsed: list[dict], crit_labels: list[str]) -> list[dict]:
    records = []
    for p in parsed:
        offer, wait = p["offer_cell"], p["waitlist_cell"]
        all_offered = offer == "All prefs met"
        notes = []
        if all_offered:
            notes.append("\"All prefs met\": every applicant who named the school was offered a place at offer "
                         "date, so the distance criterion was never reached.")
        if offer is None:
            notes.append("No distance-at-offer-date figure published for this school/year.")
        wmi = primary_cell_miles(wait)
        if wmi is not None:
            notes.append(f"Furthest distance offered from the waiting list by the end of national coordination: "
                         f"{wmi} miles.")
        elif wait == "All prefs met" and not all_offered:
            notes.append("By the end of national coordination every applicant who named the school had been "
                         "offered a place from the waiting list.")
        criteria = [{"label": label, "total": n} for label, n in zip(crit_labels, p["counts"])]
        records.append({
            "name": p["name"], "year": p["year"], "pan": p["pan"], "applications": None, "total_offers": None,
            "criteria": criteria, "max_distance": primary_cell_miles(offer), "all_offered": all_offered,
            "non_preference_offers": None, "allocation": "distance", "notes": notes,
        })
    return records
