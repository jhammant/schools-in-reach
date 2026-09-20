"""Greenwich (LA 203), current editions: parse the PageSuite admissions booklets.

Royal Greenwich rebuilt its website in 2026 and moved both admissions booklets out of
royalgreenwich.gov.uk PDFs (those URLs now return 500) into a PageSuite reader. That is why
our figures froze at entry 2023 for primary and entry 2025 for secondary.

The reader serves each booklet page as its own public PDF on pages.pagesuite.com and lists
them in a `flatPlanData` object in the page, with no server-side manifest endpoint, so
greenwich_booklet_pages.mjs opens the reader in a headless browser and prints the page URLs.
This module downloads those pages, runs pdftotext -layout, splits each two-column page down
its gutter, and reads the per-school table:

    Applications to <school> for entry <year>
      Places available            <n>
      Distance of last offer (m)  <metres>

Distances are published in metres and converted to miles.

Usage (from the project root):
    python3 pipeline/admissions_london/b3_greenwich_booklet.py [--phase primary|secondary]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "pipeline" / ".cache" / "admissions_london" / "203"
HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "SchoolsInReach-pipeline/1.0 (+https://www.schoolsinreach.com; open data collection)"}
MILE_M = 1609.344

BOOKLETS = {
    "primary": {
        "pubid": "35d3d72f-a72e-4e55-ab70-a95e264740e0",
        "page": "https://www.royalgreenwich.gov.uk/schools-and-education/apply-school-place/apply-primary-school-place",
    },
    "secondary": {
        "pubid": "544b8783-16f8-47e1-aa52-9701795c26c5",
        "page": "https://www.royalgreenwich.gov.uk/schools-and-education/apply-school-place/apply-secondary-school-place",
    },
}


def page_urls(phase: str) -> dict:
    """Ask the reader for its page list, cached so re-runs need no browser."""
    cache = CACHE / f"{phase}_pages.json"
    if cache.exists():
        return json.loads(cache.read_text())
    out = subprocess.run(
        ["node", str(HERE / "greenwich_booklet_pages.mjs"), BOOKLETS[phase]["pubid"]],
        capture_output=True, text=True, timeout=300, cwd=HERE,
    )
    if out.returncode != 0:
        raise SystemExit(f"page list failed for {phase}: {out.stderr[-400:]}")
    data = json.loads(out.stdout.strip().splitlines()[-1])
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, indent=1))
    return data


def fetch_pages(phase: str, urls: list[str]) -> list[Path]:
    """Download each page PDF once and convert it to layout-preserving text."""
    out_dir = CACHE / f"{phase}_pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = []
    for i, url in enumerate(urls, 1):
        pdf, txt = out_dir / f"{i:02d}.pdf", out_dir / f"{i:02d}.txt"
        if not pdf.exists() or pdf.stat().st_size < 1000:
            pdf.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
            time.sleep(0.25)
        if not txt.exists():
            subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], check=True)
        texts.append(txt)
    return texts


def columns(text: str) -> list[str]:
    """Split a two-column booklet page into its columns, at the blank gutter."""
    lines = [l.rstrip() for l in text.splitlines()]
    body = [l for l in lines if len(l.strip()) > 3]
    if not body:
        return []
    width = max(len(l) for l in body)
    cands = [c for c in range(int(width * 0.3), int(width * 0.72))
             if sum(1 for l in body if len(l) <= c or l[c] == " ") >= len(body) * 0.97]
    if not cands:
        return [text]
    g = min(cands, key=lambda c: abs(c - width / 2))
    return ["\n".join(l[:g] for l in lines), "\n".join(l[g:] for l in lines)]


KM_MILE = 1.609344


def parse_secondary_page(text: str) -> dict | None:
    """Secondary pages are a magazine spread: prose on the left, a data sidebar on the right.

    pdftotext -layout puts both on the same visual lines, so rather than splitting columns
    this reads the label rows, which stay intact, and takes the numbers that follow them.
    Banded schools carry one column per band; the rest carry a single "Total" column.
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or "Last offer on distance" not in text:
        return None

    # The school's name heads the page, sometimes wrapping onto a second line.
    name = lines[0].strip()
    if len(lines) > 1:
        nxt = lines[1].strip()
        if nxt and not re.search(r"[|\d]", nxt) and nxt[:1].isupper() and len(nxt) < 40:
            name = f"{name} {nxt}"

    entry = re.search(r"for entry\s+(20\d\d)", text)
    nums = lambda s: [float(x) for x in re.findall(r"\d+\.?\d*", s)]

    def after(label: str, want: int = 1) -> str:
        """Text following a label row. The contact block repeats "Places available:" with the
        school total, so prefer the row whose column count matches the table."""
        rows = [l.split(label, 1)[1] for l in lines if label in l]
        exact = [r for r in rows if len(nums(r)) == want]
        return (exact or rows or [""])[0]

    band_line = next((l for l in lines if re.search(r"Band\s+[\dA-Z]", l)), "")
    bands = re.findall(r"(?<=\s)([1-9]|[A-E])(?=\s|$)", band_line.split("Band", 1)[1]) if band_line else []
    dists = nums(after("Last offer on distance (km)"))
    pans = nums(after("Places available", want=max(1, len(bands))))

    groups = [f"Band {b}" for b in bands] if len(bands) > 1 and len(bands) == len(dists) else ["All"]
    if groups == ["All"] and len(dists) > 1:
        # More distances than groups means the columns could not be matched: keep none rather than guess.
        return {"name_in_source": name, "entry_year": int(entry.group(1)) if entry else None,
                "unparsed": True, "distances_km": dists}

    rec = {
        "name_in_source": name,
        "entry_year": int(entry.group(1)) if entry else None,
        "groups": groups,
        "max_distance": {g: round(d / KM_MILE, 3) for g, d in zip(groups, dists)} if dists else {},
        "distances_km": dists,
    }
    if groups == ["All"]:
        total = next((int(x) for x in re.findall(r"Places available:?\s*([\d,]+)", text.replace(",", ""))), None)
        if total:
            rec["pan"] = total
    elif len(pans) == len(groups):
        rec["band_places"] = {g: int(p) for g, p in zip(groups, pans)}
        rec["pan"] = int(sum(pans))
    return rec


def parse_column(col: str) -> dict | None:
    flat = re.sub(r"\s+", " ", col)
    head = re.search(r"Applications to\s+(.+?)\s+for\s+entry\s+(20\d\d)", flat)
    if not head:
        return None
    rec = {"name_in_source": head.group(1).strip(), "entry_year": int(head.group(2))}
    pan = re.search(r"Places available\s+([\d,]+)", col)
    dist = re.search(r"Distance of last offer \(m\)\s+([\d,]+\.?\d*)", col)
    apps = re.search(r"Applications received\s+([\d,]+)", col)
    if pan:
        rec["pan"] = int(pan.group(1).replace(",", ""))
    if dist:
        metres = float(dist.group(1).replace(",", ""))
        rec["max_distance"] = round(metres / MILE_M, 3)
        rec["distance_m"] = metres
    if apps:
        rec["applications"] = int(apps.group(1).replace(",", ""))
    return rec if ("max_distance" in rec or "pan" in rec) else None


def parse(phase: str) -> dict:
    manifest = page_urls(phase)
    texts = fetch_pages(phase, manifest["pages"])
    schools = []
    for t in texts:
        body = t.read_text(errors="replace")
        if phase == "secondary":
            rec = parse_secondary_page(body)
            if rec:
                schools.append(rec)
            continue
        if "Distance of last offer" not in body and "Places available" not in body:
            continue
        for col in columns(body):
            rec = parse_column(col)
            if rec:
                schools.append(rec)
    return {"edition": manifest.get("name"), "edition_date": manifest.get("date"), "schools": schools}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["primary", "secondary", "both"], default="both")
    args = ap.parse_args()
    phases = ["primary", "secondary"] if args.phase == "both" else [args.phase]
    for phase in phases:
        data = parse(phase)
        years = {}
        for s in data["schools"]:
            years[s["entry_year"]] = years.get(s["entry_year"], 0) + 1
        print(f"\n{phase}: {data['edition']} ({data['edition_date']}) — {len(data['schools'])} schools, entry years {years}")
        for s in data["schools"][:6]:
            print(f"   {s['name_in_source'][:42]:44} entry {s['entry_year']}  PAN {s.get('pan', '-'):>4}  {s.get('max_distance', '-')} mi")
        out = CACHE / f"{phase}_parsed.json"
        out.write_text(json.dumps(data, indent=1))
        print(f"   -> {out}")


if __name__ == "__main__":
    main()
