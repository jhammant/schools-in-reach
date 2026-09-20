"""Minimal streaming .xlsx reader (stdlib only).

Mirrors pipeline/dfe/xlsx.py so the UK pipelines stay self-contained and
`python3 pipeline/uk/scotland.py` runs without third-party packages. Yields
each row as a list of cell values (str, float, int, bool or None), with gaps
filled so column positions are stable.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Iterator
from xml.etree.ElementTree import iterparse

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    strings: list[str] = []
    with zf.open("xl/sharedStrings.xml") as fh:
        for _, elem in iterparse(fh):
            if elem.tag == NS + "si":
                strings.append("".join(t.text or "" for t in elem.iter(NS + "t")))
                elem.clear()
    return strings


def _sheet_path(zf: zipfile.ZipFile, sheet_name: str) -> str:
    rid = None
    with zf.open("xl/workbook.xml") as fh:
        for _, elem in iterparse(fh):
            if elem.tag == NS + "sheet" and (elem.get("name") or "").strip() == sheet_name:
                rid = elem.get(REL_NS + "id")
    if rid is None:
        raise KeyError(f"sheet {sheet_name!r} not found in {zf.filename}")
    with zf.open("xl/_rels/workbook.xml.rels") as fh:
        for _, elem in iterparse(fh):
            if elem.tag == PKG_REL_NS + "Relationship" and elem.get("Id") == rid:
                target = elem.get("Target").lstrip("/")
                return target if target.startswith("xl/") else "xl/" + target
    raise KeyError(f"relationship {rid} not found in {zf.filename}")


def iter_rows(path: Path, sheet_name: str) -> Iterator[list]:
    """Yield every row of the named sheet as a list of cell values."""
    with zipfile.ZipFile(path) as zf:
        strings = _shared_strings(zf)
        with zf.open(_sheet_path(zf, sheet_name)) as fh:
            row: list = []
            for event, elem in iterparse(fh, events=("start", "end")):
                if event == "start":
                    if elem.tag == NS + "row":
                        row = []
                    continue
                if elem.tag == NS + "c":
                    idx = _col_index(elem.get("r"))
                    cell_type = elem.get("t")
                    value = None
                    if cell_type == "inlineStr":
                        value = "".join(t.text or "" for t in elem.iter(NS + "t"))
                    else:
                        v = elem.find(NS + "v")
                        if v is not None and v.text is not None:
                            if cell_type == "s":
                                value = strings[int(v.text)]
                            elif cell_type in ("str", "e"):
                                value = v.text
                            elif cell_type == "b":
                                value = v.text == "1"
                            else:
                                num = float(v.text)
                                value = int(num) if num.is_integer() else num
                    while len(row) < idx:
                        row.append(None)
                    row.append(value)
                    elem.clear()
                elif elem.tag == NS + "row":
                    yield row
                    elem.clear()


def sheet_table(path: Path, sheet_name: str, header_marker: str) -> list[dict]:
    """Rows of a sheet as dicts, using the first row whose first cell equals
    header_marker as the header. Government workbooks put titles and notes
    above the real header row, so the marker anchors it."""
    header: list[str] | None = None
    out: list[dict] = []
    for row in iter_rows(path, sheet_name):
        first = str(row[0]).strip() if row and row[0] is not None else ""
        if header is None:
            if first.lower() == header_marker.lower():
                header = [str(c).strip() if c is not None else "" for c in row]
            continue
        if not first:
            continue
        while len(row) < len(header):
            row.append(None)
        out.append({k: v for k, v in zip(header, row) if k})
    if header is None:
        raise KeyError(f"header row starting {header_marker!r} not found in {sheet_name!r}")
    return out
