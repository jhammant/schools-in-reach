"""Shared helpers for the eight-borough admissions pipeline: HTTP fetch with
caching, GIAS-matching assembly of per-school-year records into the output
schema, and small utilities. Modelled on pipeline/admissions/build.py (the
working Hackney pipeline) but generalised across boroughs and simplified: each
borough module is responsible for producing one flat record per school per
year in the shapes below; assemble() only does GIAS matching and grouping.

Secondary record fields: name, year, pan, applications, groups, criteria
  (list of {label, counts, total}), max_distance (dict group->float|None),
  all_offered (list of groups), non_preference_offers, total_offers,
  allocation, notes.
Primary record fields: name, year, pan, applications, total_offers, criteria
  (list of {label, total}), max_distance (float|None), all_offered (bool),
  non_preference_offers, allocation, notes.
"""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

PDFTOTEXT = "/opt/homebrew/bin/pdftotext"

ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = ROOT / "pipeline" / ".cache" / "admissions_london"
GIAS_CSV_GLOB = "gias_edubasealldata_*.csv"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36",
    "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
IMPLAUSIBLE_MILES = 100.0


def gias_csv() -> Path:
    found = sorted((ROOT / "pipeline" / ".cache" / "shared").glob(GIAS_CSV_GLOB))
    if not found:
        raise SystemExit("GIAS extract not found in pipeline/.cache/shared/")
    return found[-1]


def fetch(la_code: str, spec: dict) -> Path:
    """Download spec['url'] to pipeline/.cache/admissions_london/<la_code>/<spec['cache']>,
    unless already cached. spec['kind'] is 'pdf' or 'html' (default 'pdf')."""
    cache_dir = CACHE_ROOT / la_code
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / spec["cache"]
    kind = spec.get("kind", "pdf")
    if not path.exists():
        req = urllib.request.Request(spec["url"], headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        if kind == "pdf" and not data.startswith(b"%PDF"):
            raise SystemExit(f"download of {spec['url']} did not return a PDF")
        path.write_bytes(data)
    print(f"  source {la_code}/{path.name}: {path.stat().st_size:,} bytes")
    return path


def pdftotext(pdf_path: Path) -> str:
    """Run `pdftotext -layout` on pdf_path, caching the result alongside it."""
    txt_path = pdf_path.with_suffix(".txt")
    if not txt_path.exists():
        subprocess.run([PDFTOTEXT, "-layout", str(pdf_path), str(txt_path)], check=True)
    return txt_path.read_text(encoding="utf-8", errors="replace")


def dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def huge_distance_notes(max_distance) -> list[str]:
    if isinstance(max_distance, dict):
        items = [(g, v) for g, v in max_distance.items() if v is not None and v > IMPLAUSIBLE_MILES]
        return [f"{g}: published maximum distance {v} miles is not a real home-to-school distance; the group was "
                f"effectively undersubscribed." for g, v in items]
    if max_distance is not None and max_distance > IMPLAUSIBLE_MILES:
        return [f"Published maximum distance {max_distance} miles is not a real home-to-school distance; "
                "the school was effectively undersubscribed."]
    return []


SECONDARY_FIELDS = ["pan", "applications", "groups", "criteria", "max_distance", "all_offered",
                    "non_preference_offers", "total_offers", "allocation", "notes"]
PRIMARY_FIELDS = ["pan", "applications", "total_offers", "criteria", "max_distance", "all_offered",
                  "non_preference_offers", "allocation", "notes"]


SCALAR_FIELDS = ["pan", "applications", "total_offers", "non_preference_offers", "allocation"]


def _merge_entries(a: dict, b: dict, phase: str, name: str, year: str) -> dict:
    """Two source records resolved to the same school and year (e.g. a school whose name spelling changed
    between two published editions covering an overlapping year). Prefer non-null values, and only raise if
    both sources give conflicting non-null values for the same scalar field."""
    out = dict(a)
    for key in SCALAR_FIELDS:
        av, bv = a.get(key), b.get(key)
        if key == "allocation" and av != bv:
            # "distance" is each borough module's generic fallback classification; if a source's name string
            # was truncated in one table and so missed a more specific signal (e.g. a faith-school keyword),
            # prefer whichever side reached a more specific classification rather than treating it as a
            # genuine conflict.
            out[key] = bv if av == "distance" else av if bv == "distance" else av
            if av != "distance" and bv != "distance" and av != bv:
                raise SystemExit(f"conflicting {key!r} for {phase} {name} {year}: {av!r} vs {bv!r}")
            continue
        if av is None:
            out[key] = bv
        elif bv is not None and av != bv:
            raise SystemExit(f"conflicting {key!r} for {phase} {name} {year}: {av!r} vs {bv!r}")
    md_a, md_b = a.get("max_distance"), b.get("max_distance")
    if isinstance(md_a, dict) or isinstance(md_b, dict):
        merged_md = dict(md_a or {})
        for k, v in (md_b or {}).items():
            if merged_md.get(k) is None:
                merged_md[k] = v
            elif v is not None and merged_md[k] != v:
                raise SystemExit(f"conflicting max_distance[{k!r}] for {phase} {name} {year}: "
                                 f"{merged_md[k]!r} vs {v!r}")
        out["max_distance"] = merged_md
    else:
        out["max_distance"] = md_a if md_a is not None else md_b
    if "groups" in a or "groups" in b:
        out["groups"] = sorted(set(a.get("groups") or []) | set(b.get("groups") or []))
    if isinstance(a.get("all_offered"), list):
        out["all_offered"] = sorted(set(a.get("all_offered") or []) | set(b.get("all_offered") or []))
    else:
        out["all_offered"] = a.get("all_offered") if a.get("all_offered") else b.get("all_offered")
    out["criteria"] = a.get("criteria") or b.get("criteria") or []
    out["notes"] = dedupe((a.get("notes") or []) + (b.get("notes") or []) +
                          [f"Two source documents give the same year's figures for this school under slightly "
                           f"different published names; values were combined (preferring non-null figures from "
                           f"either source)."])
    if "name_in_source" in a or "name_in_source" in b:
        names = dedupe([n for n in (a.get("name_in_source"), b.get("name_in_source")) if n])
        if names:
            out["name_in_source"] = " / ".join(names)
    return out


def assemble(records: list[dict], matcher, phase: str, unmatched: list[dict], log: list[str]) -> dict:
    fields = SECONDARY_FIELDS if phase == "secondary" else PRIMARY_FIELDS
    schools: dict[str, dict] = {}
    for rec in records:
        m = matcher.match(rec["name"], phase)
        if m is None:
            unmatched.append({"name_in_source": rec["name"], "year": rec["year"], "phase": phase})
            continue
        if m.via != "name":
            log.append(f"{phase}: {rec['name']!r} -> {m.urn} {m.name} via {m.via}")
        school = schools.setdefault(m.urn, {"urn": int(m.urn), "name": m.name, "status": m.status,
                                            "former_names": [], "former_urns": [], "years": {}})
        school["former_names"] = dedupe(school["former_names"] + m.former_names)
        school["former_urns"] = sorted(set(school["former_urns"]) | {int(u) for u in m.former_urns})
        year = str(rec["year"])
        entry = {k: rec.get(k) for k in fields}
        entry["notes"] = dedupe((entry.get("notes") or []) + huge_distance_notes(entry.get("max_distance")))
        if rec["name"] != m.name:
            entry["name_in_source"] = rec["name"]
        if year in school["years"]:
            entry = _merge_entries(school["years"][year], entry, phase, m.name, year)
        school["years"][year] = entry
    for school in schools.values():
        school["years"] = dict(sorted(school["years"].items(), reverse=True))
        for key in ("former_names", "former_urns"):
            if not school[key]:
                del school[key]
    return dict(sorted(schools.items(), key=lambda kv: kv[1]["name"]))


def miles(value: float | None, *, from_unit: str) -> float | None:
    """Convert a distance to miles, rounded to 3dp (matching Hackney's precision)."""
    if value is None:
        return None
    factor = {"miles": 1.0, "metres": 1 / 1609.344, "m": 1 / 1609.344, "km": 1000 / 1609.344,
              "kilometres": 1000 / 1609.344}[from_unit]
    return round(value * factor, 3)
