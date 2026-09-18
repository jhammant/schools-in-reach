"""Shared helpers for the batch-2 London boroughs (build_batch2.py).

Builds on the batch-1 helpers (common.py, gias.py, pdftools.py, owned by the
batch-1 pipeline and imported, not edited): adds record constructors in the
Hackney output shape and a word-geometry table reader for PDFs whose column
headers wrap over several lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pdfplumber

import common
import pdftools

OGL = "Open Government Licence v3.0"
METRES_PER_MILE = 1609.344


def miles_from_metres(value: float | None) -> float | None:
    return None if value is None else round(value / METRES_PER_MILE, 3)


def secondary_record(name: str, year: int, *, pan=None, applications=None, groups=None, criteria=None,
                     max_distance=None, all_offered=None, non_preference_offers=None, total_offers=None,
                     allocation="distance", notes=None) -> dict:
    groups = groups or ["All"]
    if max_distance is None or not isinstance(max_distance, dict):
        max_distance = {g: max_distance for g in groups}
    return {"name": name, "year": int(year), "pan": pan, "applications": applications, "groups": groups,
            "criteria": criteria or [], "max_distance": max_distance, "all_offered": all_offered or [],
            "non_preference_offers": non_preference_offers, "total_offers": total_offers,
            "allocation": allocation, "notes": notes or []}


def primary_record(name: str, year: int, *, pan=None, applications=None, criteria=None, max_distance=None,
                   all_offered=False, non_preference_offers=None, total_offers=None, allocation="distance",
                   notes=None) -> dict:
    return {"name": name, "year": int(year), "pan": pan, "applications": applications, "total_offers": total_offers,
            "criteria": criteria or [], "max_distance": max_distance, "all_offered": bool(all_offered),
            "non_preference_offers": non_preference_offers, "allocation": allocation, "notes": notes or []}


def text_of(path) -> str:
    return common.pdftotext(path)


# --------------------------------------------------------------------------- wrapped-header tables

@dataclass
class Column:
    label: str
    x0: float
    x1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


def header_columns(words: list[pdftools.Word], top: float, bottom: float, left: float) -> list[Column]:
    """Group the header words between y=top and y=bottom (right of x=left) into columns: words whose
    horizontal extents overlap belong to the same column; each column's label is its words read top-down."""
    hdr = sorted((w for w in words if top <= w.cy < bottom and w.x0 >= left), key=lambda w: w.x0)
    groups: list[list[pdftools.Word]] = []
    for w in hdr:
        for g in groups:
            gx0, gx1 = min(x.x0 for x in g), max(x.x1 for x in g)
            overlap = min(gx1, w.x1) - max(gx0, w.x0)
            if overlap > 0.35 * min(w.x1 - w.x0, gx1 - gx0):
                g.append(w)
                break
        else:
            groups.append([w])
    # merging can make groups overlap each other; repeat until stable
    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                ax0, ax1 = min(x.x0 for x in a), max(x.x1 for x in a)
                bx0, bx1 = min(x.x0 for x in b), max(x.x1 for x in b)
                overlap = min(ax1, bx1) - max(ax0, bx0)
                if overlap > 0.35 * min(ax1 - ax0, bx1 - bx0):
                    groups[i] = a + b
                    del groups[j]
                    changed = True
                    break
            if changed:
                break
    cols = []
    for g in groups:
        g.sort(key=lambda w: (round(w.top), w.x0))
        cols.append(Column(" ".join(w.text for w in g), min(w.x0 for w in g), max(w.x1 for w in g)))
    return sorted(cols, key=lambda c: c.x0)


def assign(words: list[pdftools.Word], cols: list[Column], max_gap: float = 40.0) -> dict[int, list[str]]:
    """Assign value words to the column whose extent contains (or is nearest to) the word centre."""
    out: dict[int, list[str]] = {}
    for w in sorted(words, key=lambda w: w.x0):
        best, dist = None, None
        for i, c in enumerate(cols):
            d = 0.0 if c.x0 - 2 <= w.cx <= c.x1 + 2 else min(abs(w.cx - c.x0), abs(w.cx - c.x1))
            if dist is None or d < dist:
                best, dist = i, d
        if dist is not None and dist <= max_gap:
            out.setdefault(best, []).append(w.text)
    return out


def open_pdf(path):
    return pdfplumber.open(path)


NUM_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")


def to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip().replace(",", "")
    m = re.match(r"^\(?(\d+(?:\.\d+)?)", raw)
    return float(m.group(1)) if m else None


def to_int(raw: str | None) -> int | None:
    v = to_float(raw)
    return None if v is None else int(v)


def anchored_rows(words: list[pdftools.Word], cols: list[tuple[str, float, float]], anchor: str,
                  top: float, bottom: float, name_x1: float, anchor_re=re.compile(r"^\d+$")) -> list[dict]:
    """Rows of a table whose cells wrap over several visual lines. Every row has exactly one value in the
    `anchor` column (e.g. the PAN); each other word between y=top and y=bottom is given to the row whose
    anchor is vertically nearest, then to the column it sits under (words left of name_x1 form the name).
    Returns [{"name": str, "cells": {kind: "joined text"}, "cy": float}]."""
    body = [w for w in words if top <= w.cy < bottom]
    a_col = next((x0, x1) for kind, x0, x1 in cols if kind == anchor)
    anchors = sorted((w for w in body if a_col[0] - 12 <= w.cx <= a_col[1] + 12 and anchor_re.match(w.text)),
                     key=lambda w: w.cy)
    if not anchors:
        return []
    value_cols = [Column(kind, x0, x1) for kind, x0, x1 in cols if kind != "name"]
    rows = [{"name": [], "cells": {}, "cy": a.cy} for a in anchors]
    for w in sorted(body, key=lambda w: (w.top, w.x0)):
        i = min(range(len(anchors)), key=lambda k: abs(anchors[k].cy - w.cy))
        if abs(anchors[i].cy - w.cy) > 22:
            continue
        if w.x1 <= name_x1:
            rows[i]["name"].append(w.text)
            continue
        cells = assign([w], value_cols, max_gap=30)
        for idx, texts in cells.items():
            rows[i]["cells"].setdefault(value_cols[idx].label, []).extend(texts)
    return [{"name": " ".join(r["name"]).strip(), "cells": {k: " ".join(v) for k, v in r["cells"].items()},
             "cy": r["cy"]} for r in rows]


def ruled_rows(page, words: list[pdftools.Word], cols: list[tuple[str, float, float]], name_x1: float,
               top: float, bottom: float) -> list[dict]:
    """Rows of a table drawn with horizontal cell borders (thin filled rects): every band between two
    consecutive borders is one row. Words left of name_x1 form the name; others go to the column above."""
    rules = sorted({round(r["top"], 1) for r in page.rects if r["height"] < 2 and r["width"] > 20})
    rules = [y for y in rules if top - 3 <= y <= bottom + 3]
    merged: list[float] = []
    for y in rules:
        if not merged or y - merged[-1] > 4:
            merged.append(y)
    value_cols = [Column(kind, x0, x1) for kind, x0, x1 in cols if kind != "name"]
    out = []
    for y0, y1 in zip(merged, merged[1:]):
        band = sorted((w for w in words if y0 <= w.cy < y1), key=lambda w: (round(w.top), w.x0))
        if not band:
            continue
        name = [w.text for w in band if w.x1 <= name_x1]
        cells: dict[str, list[str]] = {}
        for w in band:
            if w.x1 <= name_x1:
                continue
            for idx, texts in assign([w], value_cols, max_gap=30).items():
                cells.setdefault(value_cols[idx].label, []).extend(texts)
        out.append({"name": " ".join(name).strip(), "cells": {k: " ".join(v) for k, v in cells.items()},
                    "cy": (y0 + y1) / 2})
    return out


# --------------------------------------------------------------------------- GIAS helpers

import csv as _csv

import gias as _gias

_PHASES = {"secondary": {"Secondary", "All-through", "Middle deemed secondary"},
           "primary": {"Primary", "All-through", "Middle deemed primary"}}
_STATE = {"Local authority maintained schools", "Academies", "Free Schools"}


class GiasIndex:
    """Open state-funded schools of one LA, for resolving messy source names (names spilling between table
    cells, or several schools sharing a name that the source tells apart by postcode district)."""

    def __init__(self, la_code: str):
        self.rows: list[dict] = []
        with open(common.gias_csv(), encoding="cp1252", newline="") as fh:
            for row in _csv.DictReader(fh):
                if (row["LA (code)"] == la_code and row["EstablishmentStatus (name)"].startswith("Open")
                        and row["EstablishmentTypeGroup (name)"] in _STATE):
                    self.rows.append({"urn": row["URN"], "name": row["EstablishmentName"], "postcode": row["Postcode"],
                                      "phase": row["PhaseOfEducation (name)"],
                                      "policy": row["AdmissionsPolicy (name)"],
                                      "religion": row["ReligiousCharacter (name)"],
                                      "toks": _gias.tokens(row["EstablishmentName"])})
        self.by_urn = {r["urn"]: r for r in self.rows}

    def selective(self, urn: str) -> bool:
        return self.by_urn.get(urn, {}).get("policy") == "Selective"

    def resolve(self, text: str, phase: str, exclude: set[str] = frozenset(), min_overlap: int = 1,
                policy: str | None = None) -> dict | None:
        toks = _gias.tokens(text)
        district = re.search(r"\(([A-Z]{1,2}\d{1,2}[A-Z]?)\)", text)
        pool = [r for r in self.rows if r["phase"] in _PHASES[phase] and r["urn"] not in exclude
                and (policy is None or r["policy"] == policy)]
        if district:
            pool = [r for r in pool if r["postcode"].split(" ")[0] == district.group(1)]
            toks = toks - {district.group(1).lower()}
        weak = {"high", "primary", "college", "catholic", "ce", "church", "infant", "junior", "st", "nursery",
                "girls", "boys", "grammar", "jewish", "rc", "for", "c", "e"}
        strong = toks - weak
        if len(strong) < min_overlap:
            return None
        opposite = {"boys": "girls", "girls": "boys", "infant": "junior", "junior": "infant"}
        best = [r for r in pool if strong <= r["toks"]
                and not any(w in toks and o in r["toks"] and o not in toks for w, o in opposite.items())]
        if len(best) > 1:
            exact = [r for r in best if r["toks"] == toks]
            gendered = [r for r in best if any(g in toks and g in r["toks"] for g in ("boys", "girls"))]
            best = exact or gendered or best
        return best[0] if len(best) == 1 else None


def alias_key(name: str) -> str:
    return " ".join(sorted(_gias.tokens(name)))
