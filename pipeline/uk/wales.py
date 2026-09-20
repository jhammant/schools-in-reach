"""Welsh schools -> site/data/la/<la_code>/schools.json.

The DfE register carries Welsh establishments, but without a phase or age range: every
Welsh row reads "Not applicable", which would file almost every school as primary. The
Welsh Government's own address list has the sector, the teaching language, the governance
type and pupil numbers, so that is the source here. Coordinates come from postcodes.io.

Usage (from the project root):
    python3 pipeline/uk/wales.py

Outputs:
    site/data/la/<la_code>/schools.json   one file per Welsh council (DfE LA codes 660-681)
    site/data/uk/wales_las.json           council index entries, same shape as england/las.json
"""

from __future__ import annotations

import json
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "pipeline" / ".cache" / "uk" / "wales"
OUT_LA = ROOT / "site" / "data" / "la"
OUT_UK = ROOT / "site" / "data" / "uk"

LIST_PAGE = "https://www.gov.wales/address-list-schools"
LIST_FILE = "https://www.gov.wales/sites/default/files/publications/2026-04/address-list-schools-values.ods"
UA = {"User-Agent": "Mozilla/5.0 (schoolsinreach data pipeline; +https://www.schoolsinreach.com)"}
OGL = "Open Government Licence v3.0"
SOURCES = [{"title": "Address list of schools (Welsh Government)", "url": LIST_PAGE, "licence": OGL}]
NOTES = [
    "Schools in Wales are inspected by Estyn, not Ofsted.",
    "Wales does not publish Progress 8 or Attainment 8; school-level performance measures were withdrawn in 2020.",
    "Welsh councils admit by catchment area and other published criteria rather than the distance cut-offs used in much of England.",
    "Positions come from the postcode centre, so they can sit a little away from the school gate.",
]

NS = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0", "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"

# Wales publishes a sector, not an age range; these are the statutory ranges for each.
SECTOR_AGES = {
    "Nursery": (3, 4),
    "Primary": (3, 11),
    "Middle": (3, 18),
    "Secondary": (11, 18),
    "Special": (None, None),
    "PRU": (None, None),
}


def fetch_list() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / "address-list-schools.ods"
    if not dest.exists():
        dest.write_bytes(urllib.request.urlopen(urllib.request.Request(LIST_FILE, headers=UA), timeout=90).read())
    return dest


def sheet_rows(path: Path, sheet: str) -> list[list[str]]:
    root = ET.fromstring(zipfile.ZipFile(path).read("content.xml"))
    for table in root.iter(T + "table"):
        if table.get(T + "name") != sheet:
            continue
        rows = []
        for r in table.findall("table:table-row", NS):
            cells: list[str] = []
            for c in r.findall("table:table-cell", NS):
                rep = int(c.get(T + "number-columns-repeated", 1))
                text = " ".join("".join(p.itertext()) for p in c.findall("text:p", NS)).strip()
                cells.extend([text] * min(rep, 60))
            rows.append(cells)
        return rows
    raise SystemExit(f"sheet {sheet!r} not found")


def clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return None if v in {"", "---", "N/A", "n/a"} else v


def num(v: str | None) -> int | None:
    v = (v or "").replace(",", "").strip()
    try:
        return int(float(v))
    except ValueError:
        return None


def geocode(postcodes: list[str]) -> dict[str, list[float] | None]:
    """postcodes.io bulk lookup, cached so re-runs need no network."""
    cache_path = CACHE / "postcodes.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = sorted({p for p in postcodes if p and p not in cache})
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        req = urllib.request.Request(
            "https://api.postcodes.io/postcodes",
            data=json.dumps({"postcodes": batch}).encode(),
            headers={"Content-Type": "application/json", **UA},
        )
        with urllib.request.urlopen(req, timeout=40) as resp:
            for item in json.loads(resp.read())["result"]:
                r = item.get("result")
                cache[item["query"]] = [r["latitude"], r["longitude"]] if r else None
        time.sleep(0.4)
        print(f"  geocoded {min(i + 100, len(todo))}/{len(todo)}")
    cache_path.write_text(json.dumps(cache))
    return cache


def parse(path: Path) -> list[dict]:
    """Maintained, independent and PRU sheets -> one list of school dicts."""
    out: list[dict] = []
    for sheet, kind in (("Maintained", "Maintained"), ("Independent", "Independent"), ("PRU", "Pupil referral unit")):
        rows = sheet_rows(path, sheet)
        header = next((r for r in rows if r and r[0].strip() == "School Number"), None)
        if not header:
            print(f"  {sheet}: no header row, skipped")
            continue
        idx = {name.split(" - ")[0].strip(): i for i, name in enumerate(header) if name.strip()}
        start = rows.index(header) + 1
        for r in rows[start:]:
            if not r or not (r[idx["School Number"]] or "").strip().isdigit():
                continue
            get = lambda key: clean(r[idx[key]]) if key in idx and idx[key] < len(r) else None  # noqa: E731
            sector = get("Sector") or ("Independent" if kind == "Independent" else kind)
            lo, hi = SECTOR_AGES.get(sector, (None, None))
            address = [get("Address 1"), get("Address 2"), get("Address 3"), get("Address 4")]
            address = [a for a in address if a]
            postcode = None
            for a in reversed(address):
                if len(a) <= 9 and any(ch.isdigit() for ch in a) and " " in a:
                    postcode = a
                    address.remove(a)
                    break
            postcode = (get("Postcode") or postcode or "").upper().strip() or None
            number = r[idx["School Number"]].strip()
            out.append({
                "urn": 10000000 + int(number),
                "source_id": number,
                "name": get("School Name"),
                "lat": None,
                "lon": None,
                "phase": "All-through" if sector == "Middle" else sector,
                "type": get("School Type") or sector,
                "type_group": "Independent schools" if kind == "Independent" else (get("Governance") or kind),
                "gender": None,
                "religious_character": get("Religious Character"),
                "language_category": get("School Language Category"),
                "age_low": lo,
                "age_high": hi,
                "pupils": num(get("Pupils")),
                "street": address[0] if address else None,
                "locality": address[1] if len(address) > 1 else None,
                "town": address[-1] if len(address) > 2 else None,
                "postcode": postcode,
                "phone": get("Phone Number"),
                "inspectorate": "Estyn",
                "nation": "Wales",
                "la": (get("LA Code") or "").strip(),
                "la_name": get("Local Authority"),
            })
    return out


def main() -> None:
    path = fetch_list()
    schools = parse(path)
    print(f"{len(schools)} schools from the Welsh Government list")

    positions = geocode([s["postcode"] for s in schools])
    for s in schools:
        pos = positions.get(s["postcode"] or "")
        if pos:
            s["lat"], s["lon"] = round(pos[0], 6), round(pos[1], 6)
            s["position_source"] = "postcode centre"

    OUT_UK.mkdir(parents=True, exist_ok=True)
    by_la: dict[str, list[dict]] = {}
    for s in schools:
        if s["la"]:
            by_la.setdefault(s["la"], []).append(s)

    index = []
    for code, rows in sorted(by_la.items()):
        rows.sort(key=lambda s: s["name"] or "")
        located = [s for s in rows if s["lat"] is not None]
        lats = [s["lat"] for s in located]
        lons = [s["lon"] for s in located]
        name = rows[0]["la_name"]
        out_dir = OUT_LA / code
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "schools.json").write_text(json.dumps({
            "generated": date.today().isoformat(),
            "sources": SOURCES,
            "la": {"code": code, "name": name, "nation": "Wales"},
            "count": len(rows),
            "notes": NOTES,
            "schools": rows,
        }, ensure_ascii=False), encoding="utf-8")
        index.append({
            "la_code": code,
            "name": name,
            "region": "Wales",
            "nation": "Wales",
            "lad_codes": [],
            "school_count": len(rows),
            "state_school_count": sum(1 for s in rows if s["type_group"] != "Independent schools"),
            "bbox": [round(min(lons), 5), round(min(lats), 5), round(max(lons), 5), round(max(lats), 5)] if located else None,
            "centroid": [round(sum(lats) / len(lats), 5), round(sum(lons) / len(lons), 5)] if located else None,
        })
        phases = {}
        for s in rows:
            phases[s["phase"]] = phases.get(s["phase"], 0) + 1
        print(f"{code} {name:<22} {len(rows):4} schools, {len(located)} located  {phases}")

    (OUT_UK / "wales_las.json").write_text(json.dumps({
        "generated": date.today().isoformat(),
        "sources": SOURCES,
        "notes": NOTES,
        "las": index,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(index)} Welsh councils, {len(schools)} schools")


if __name__ == "__main__":
    main()
