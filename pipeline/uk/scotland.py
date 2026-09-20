#!/usr/bin/env python3
"""Build the school register for Scotland's 32 councils from open government data.

Usage (from the project root):
    python3 pipeline/uk/scotland.py [--refresh]

Sources (all Open Government Licence v3.0):
  * Scottish Government "School contact details" - every publicly funded school,
    its SEED code, address, council, departments and denomination.
  * Scottish Government "Pupil census supplementary statistics" table 9.1 -
    school level pupil rolls.
  * ONS Open Geography Portal - Local Authority District names and codes, for
    the S12... council codes the site keys its data directories on.
  * postcodes.io - postcode centroids, because the Scottish files publish
    postcodes but no coordinates.

Outputs (site/data/):
    la/<ONS council code>/schools.json   register shaped like the English files
    uk/scotland_las.json                 council index shaped like england/las.json

Everything downloaded is cached under pipeline/.cache/uk/scotland/ so re-runs
work offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xlsx  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "pipeline" / ".cache" / "uk" / "scotland"
OUT = ROOT / "site" / "data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

OGL = "Open Government Licence v3.0"

CONTACT_PAGE = "https://www.gov.scot/publications/school-contact-details/"
CONTACT_XLSX = (
    "https://www.gov.scot/binaries/content/documents/govscot/publications/factsheet/2019/03/"
    "school-contact-details/documents/school-contact-details/school-contact-details/"
    "govscot%3Adocument/school%2Bcontact%2Blist%2B31%2BJanuary%2B2026.xlsx"
)
CONTACT_AS_AT = "2026-01-31"

CENSUS_PAGE = "https://www.gov.scot/publications/pupil-census-supplementary-statistics/"
CENSUS_XLSX = (
    "https://www.gov.scot/binaries/content/documents/govscot/publications/statistics/2019/07/"
    "pupil-census-supplementary-tables/documents/pupil-census-supplementary-statistics-2025/"
    "pupil-census-supplementary-statistics-2025/govscot%3Adocument/"
    "Pupil%2Bcensus%2Bsupplementary%2Bstatistics%2B2025%2B-%2BMarch.xlsx"
)
CENSUS_YEAR = 2025

LAD_SERVICE = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "LAD_APR_2025_UK_NC_v2/FeatureServer/0/query"
    "?where=LAD25CD+LIKE+%27S12%25%27&outFields=LAD25CD%2CLAD25NM"
    "&returnGeometry=false&outSR=4326&f=json"
)
LAD_PAGE = "https://geoportal.statistics.gov.uk/"

POSTCODES_API = "https://api.postcodes.io/postcodes"
POSTCODES_TERMINATED = "https://api.postcodes.io/terminated_postcodes/"
POSTCODE_BATCH = 100
POSTCODE_PAUSE = 0.4  # seconds between calls to postcodes.io

SOURCES = [
    {"title": "School contact details: January 2026 (Scottish Government)", "url": CONTACT_PAGE, "licence": OGL},
    {"title": "Pupil census supplementary statistics 2025, table 9.1 School Level Pupil Rolls (Scottish Government)", "url": CENSUS_PAGE, "licence": OGL},
    {"title": "Local Authority Districts (April 2025) Names and Codes in the United Kingdom (ONS Open Geography Portal)", "url": LAD_PAGE, "licence": OGL},
    {"title": "postcodes.io postcode centroids (ONS Postcode Directory)", "url": "https://postcodes.io/", "licence": OGL},
]

# Council names as the contact list spells them -> names as ONS spells them.
LA_NAME_FIXES = {
    "Argyll & Bute": "Argyll and Bute",
    "Dumfries & Galloway": "Dumfries and Galloway",
    "Edinburgh City": "City of Edinburgh",
    "Perth & Kinross": "Perth and Kinross",
}

# Schools funded directly by the Scottish Government rather than by a council.
GRANT_AIDED = "Grant aided"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- http


def _open(url: str, data: bytes | None = None, timeout: int = 120):
    headers = dict(HEADERS)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except (urllib.error.URLError, TimeoutError) as err:
            last_err = err
            if isinstance(err, urllib.error.HTTPError) and err.code in (400, 401, 403, 404):
                break
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{'POST' if data else 'GET'} {url} failed: {last_err}")


def download(url: str, dest: Path, refresh: bool = False) -> Path:
    """Fetch url to dest unless it is already cached."""
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"  downloading {url[:110]}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _open(url) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    if tmp.stat().st_size == 0:
        tmp.unlink()
        raise RuntimeError(f"empty download: {url}")
    tmp.replace(dest)
    return dest


def post_json(url: str, payload: dict, dest: Path, refresh: bool = False) -> dict:
    """POST payload to url, caching the raw response under dest."""
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return json.loads(dest.read_text(encoding="utf-8"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload).encode("utf-8")
    with _open(url, data=body) as resp:
        raw = resp.read().decode("utf-8")
    dest.write_text(raw, encoding="utf-8")
    time.sleep(POSTCODE_PAUSE)
    return json.loads(raw)


# --------------------------------------------------------------------------- parsing


def text(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def yes(value) -> bool | None:
    s = (text(value) or "").lower()
    return True if s == "yes" else False if s == "no" else None


def normalise_postcode(value) -> str | None:
    s = (text(value) or "").upper().replace(" ", "")
    if len(s) < 5 or len(s) > 7:
        return None
    return f"{s[:-3]} {s[-3:]}"


def load_councils(refresh: bool) -> dict[str, str]:
    """{council name: ONS code} for Scotland's 32 councils."""
    dest = CACHE / "ons_lad_scotland.json"
    download(LAD_SERVICE, dest, refresh)
    data = json.loads(dest.read_text(encoding="utf-8"))
    codes = {f["attributes"]["LAD25NM"]: f["attributes"]["LAD25CD"] for f in data.get("features", [])}
    if len(codes) != 32:
        raise RuntimeError(f"expected 32 Scottish councils from ONS, got {len(codes)}")
    return codes


def load_contact_list(refresh: bool) -> list[dict]:
    path = download(CONTACT_XLSX, CACHE / f"school_contact_list_{CONTACT_AS_AT}.xlsx", refresh)
    rows = xlsx.sheet_table(path, "Open Schools", "Seed Code")
    return [r for r in rows if text(r.get("Seed Code"))]


def load_rolls(refresh: bool) -> dict[str, dict]:
    """{seed code: {"total": n, "by_department": {...}}} from the pupil census."""
    path = download(CENSUS_XLSX, CACHE / f"pupil_census_supplementary_{CENSUS_YEAR}.xlsx", refresh)
    rolls: dict[str, dict] = {}
    for row in xlsx.sheet_table(path, "Table 9.1", "Local Authority"):
        seed = text(row.get("SeedCode"))
        roll = row.get("Pupil Roll")
        if not seed or not isinstance(roll, (int, float)):
            continue
        entry = rolls.setdefault(seed, {"total": 0, "by_department": {}})
        dept = text(row.get("School Type")) or "Unknown"
        entry["total"] += int(roll)
        entry["by_department"][dept] = entry["by_department"].get(dept, 0) + int(roll)
    return rolls


# --------------------------------------------------------------------------- geocoding


def geocode(postcodes: list[str], refresh: bool) -> dict[str, dict]:
    """Postcode -> {"lat","lon","council_code","council_name","ward","constituency"}.

    Uses the postcodes.io bulk endpoint (100 at a time, with a pause between
    calls) and falls back to the terminated-postcode endpoint for retired ones.
    Every raw response is cached so a re-run needs no network.
    """
    found: dict[str, dict] = {}
    unmatched: list[str] = []
    ordered = sorted(postcodes)
    chunks = [ordered[i:i + POSTCODE_BATCH] for i in range(0, len(ordered), POSTCODE_BATCH)]
    log(f"  geocoding {len(ordered)} postcodes in {len(chunks)} requests")
    for chunk in chunks:
        key = hashlib.sha1("|".join(chunk).encode("utf-8")).hexdigest()[:16]
        data = post_json(POSTCODES_API, {"postcodes": chunk}, CACHE / "postcodes" / f"bulk_{key}.json", refresh)
        for item in data.get("result", []):
            res = item.get("result")
            if not res:
                unmatched.append(item["query"])
                continue
            found[item["query"]] = {
                "lat": res.get("latitude"),
                "lon": res.get("longitude"),
                "council_code": (res.get("codes") or {}).get("admin_district"),
                "council_name": res.get("admin_district"),
                "ward": res.get("admin_ward"),
                "constituency": res.get("parliamentary_constituency"),
            }
    for pc in unmatched:
        dest = CACHE / "postcodes" / f"terminated_{pc.replace(' ', '')}.json"
        if not dest.exists() or refresh:
            try:
                download(POSTCODES_TERMINATED + urllib.parse.quote(pc), dest, refresh)
                time.sleep(POSTCODE_PAUSE)
            except RuntimeError:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps({"status": 404, "result": None}), encoding="utf-8")
        res = (json.loads(dest.read_text(encoding="utf-8")) or {}).get("result")
        if res and res.get("latitude") is not None:
            found[pc] = {
                "lat": res.get("latitude"),
                "lon": res.get("longitude"),
                "council_code": None,
                "council_name": None,
                "ward": None,
                "constituency": None,
                "terminated": True,
            }
    return found


# --------------------------------------------------------------------------- shaping


def phase_of(row: dict) -> str:
    """Primary / Secondary / All-through / Special / Nursery from the department flags.

    A mainstream primary or secondary department wins over a special one: a
    handful of schools run both, and the pupil census counts those as primary
    or secondary schools.
    """
    pre, pri, sec, spc = (yes(row.get(k)) for k in (
        "Pre-school Department", "Primary Department", "Secondary Department", "Special Department"))
    if pri and sec:
        return "All-through"
    if sec:
        return "Secondary"
    if pri:
        return "Primary"
    if spc:
        return "Special"
    if pre:
        return "Nursery"
    return "Not applicable"


def age_range(row: dict, phase: str) -> tuple[int | None, int | None]:
    """Statutory stage range implied by the departments the school runs.

    Scotland does not publish a per-school age range, so this is derived:
    nursery 3, primary P1-P7 (5-12), secondary S1-S6 (12-18). Special schools
    take a wide and school-specific range, so they are left unset.
    """
    if phase in ("Special", "Not applicable"):
        return None, None
    pre = yes(row.get("Pre-school Department"))
    if phase == "Nursery":
        return 3, 5
    low = 3 if pre else (5 if phase in ("Primary", "All-through") else 12)
    high = 12 if phase == "Primary" else 18
    return low, high


def type_of(centre_type: str | None, phase: str) -> tuple[str, str]:
    """(type, type_group) in the style of the English register."""
    centre = (centre_type or "").strip()
    sector = {
        "Primary": "primary", "Secondary": "secondary", "All-through": "all-through",
        "Special": "special", "Nursery": "nursery",
    }.get(phase, "")
    if centre.lower() == "grant aided":
        return (f"Grant aided {sector} school".replace("  ", " ").strip(), "Grant-aided schools")
    return (f"Local authority {sector} school".replace("  ", " ").strip(), "Local authority maintained schools")


def address_parts(row: dict) -> tuple[str | None, str | None, str | None]:
    """(street, locality, town) from the three published address lines."""
    line1, line2, line3 = (text(row.get(f"Address Line{i}")) for i in (1, 2, 3))
    if line3:
        return line1, line2, line3
    return line1, None, line2


def school_record(row: dict, rolls: dict, places: dict, council_code: str, council_name: str) -> dict:
    seed = text(row["Seed Code"])
    phase = phase_of(row)
    stype, type_group = type_of(text(row.get("Centre Type")), phase)
    age_low, age_high = age_range(row, phase)
    street, locality, town = address_parts(row)
    postcode = normalise_postcode(row.get("Post Code"))
    place = places.get(postcode or "", {})
    denomination = text(row.get("Denomination"))
    faith = None if not denomination or denomination.lower() == "non-denominational" else denomination
    roll = rolls.get(seed)
    record = {
        "urn": 20000000 + int(seed),
        "source_id": seed,
        "name": text(row.get("School Name")),
        "lat": place.get("lat"),
        "lon": place.get("lon"),
        "phase": phase,
        "type": stype,
        "type_group": type_group,
        "gender": None,
        "religious_ethos": denomination,
        "religious_character": faith,
        "age_low": age_low,
        "age_high": age_high,
        "pupils": roll["total"] if roll else None,
        "capacity": None,
        "street": street,
        "locality": locality,
        "town": town,
        "postcode": postcode,
        "website": text(row.get("Website Address")),
        "phone": text(row.get("Phone Number")),
        "head": None,
        "inspectorate": "Education Scotland",
        "medium_of_education": text(row.get("Medium of Education")),
        "integrated_special_unit": yes(row.get("Integrated Special Unit")),
        "ward": place.get("ward"),
        "constituency": place.get("constituency"),
        "la": council_code,
        "la_name": council_name,
        "nation": "Scotland",
    }
    if roll and len(roll["by_department"]) > 1:
        record["pupils_by_department"] = dict(sorted(roll["by_department"].items()))
    return record


def write_json(path: Path, data) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(payload, encoding="utf-8")
    return len(payload.encode("utf-8"))


# --------------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="re-download everything instead of using the cache")
    args = parser.parse_args()

    log("Scotland: reading sources")
    councils = load_councils(args.refresh)
    contact = load_contact_list(args.refresh)
    rolls = load_rolls(args.refresh)
    log(f"  {len(contact)} open schools, {len(rolls)} with a published roll, {len(councils)} councils")

    postcodes = sorted({pc for pc in (normalise_postcode(r.get("Post Code")) for r in contact) if pc})
    places = geocode(postcodes, args.refresh)

    by_council: dict[str, list[dict]] = {code: [] for code in councils.values()}
    unplaced: list[tuple[str, str]] = []
    no_postcode: list[tuple[str, str]] = []
    boundary_mismatch: list[tuple[str, str, str, str]] = []
    grant_aided = 0
    unknown_council: list[str] = []

    for row in contact:
        published_la = text(row.get("LA Name")) or ""
        postcode = normalise_postcode(row.get("Post Code"))
        place = places.get(postcode or "", {})
        if published_la == GRANT_AIDED:
            # Funded by the Scottish Government, so the contact list names no
            # council: file it under the council its postcode sits in.
            grant_aided += 1
            code = place.get("council_code")
            name = place.get("council_name")
            if not code or code not in by_council:
                unknown_council.append(text(row.get("School Name")) or "?")
                continue
        else:
            name = LA_NAME_FIXES.get(published_la, published_la)
            code = councils.get(name)
            if not code:
                unknown_council.append(f"{published_la} / {text(row.get('School Name'))}")
                continue
            if place.get("council_code") and place["council_code"] != code:
                boundary_mismatch.append(
                    (text(row.get("School Name")) or "?", name, place.get("council_name") or "?", postcode or "?"))
        record = school_record(row, rolls, places, code, name)
        if not postcode:
            no_postcode.append((record["name"], name))
        elif record["lat"] is None:
            unplaced.append((record["name"], postcode))
        by_council[code].append(record)

    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    notes_common = [
        f"Publicly funded schools open on {CONTACT_AS_AT}, from the Scottish Government school contact list.",
        f"pupils is the school's total roll in the September {CENSUS_YEAR} pupil census (all departments added together); "
        "nursery/ELC children are counted in a separate census and are not included.",
        "lat/lon are postcode-unit centroids from postcodes.io, not the school building.",
        "phase, type and the age range are derived from the published department flags: Scotland publishes no per-school age range.",
        "capacity, head teacher and single-sex status are not published in the Scottish open data, so they are null.",
        "urn is 20000000 + the SEED code so it cannot collide with a 6-digit English URN; source_id holds the SEED code as published.",
    ]

    sizes = {}
    for code, schools in sorted(by_council.items()):
        schools.sort(key=lambda s: (s["name"] or "").lower())
        name = next(n for n, c in councils.items() if c == code)
        doc = {
            "generated": generated,
            "sources": SOURCES,
            "la": {"code": code, "name": name, "nation": "Scotland"},
            "count": len(schools),
            "notes": notes_common,
            "schools": schools,
        }
        sizes[code] = write_json(OUT / "la" / code / "schools.json", doc)

    las_entries = []
    for name, code in sorted(councils.items(), key=lambda kv: kv[1]):
        schools = by_council[code]
        coords = [(s["lat"], s["lon"]) for s in schools if s["lat"] is not None and s["lon"] is not None]
        bbox = centroid = None
        if coords:
            lats = [c[0] for c in coords]
            lons = [c[1] for c in coords]
            bbox = [round(min(lons) - 0.01, 5), round(min(lats) - 0.01, 5),
                    round(max(lons) + 0.01, 5), round(max(lats) + 0.01, 5)]
            centroid = [round(sum(lats) / len(lats), 5), round(sum(lons) / len(lons), 5)]
        las_entries.append({
            "la_code": code,
            "name": name,
            "region": "Scotland",
            "nation": "Scotland",
            "lad_codes": [code],
            "school_count": len(schools),
            "state_school_count": len(schools),
            "bbox": bbox,
            "centroid": centroid,
        })
    las_doc = {
        "generated": generated,
        "sources": SOURCES,
        "notes": [
            f"Scotland's 32 councils, with the publicly funded schools open on {CONTACT_AS_AT}.",
            "Every Scottish school in this register is publicly funded, so state_school_count equals school_count; "
            "independent schools are registered separately and are not in this source.",
            "la_code is the ONS council code and is also the site's data directory for that council.",
            "bbox is [west, south, east, north] padded by 0.01 degrees; centroid is the mean of school coordinates.",
        ],
        "las": las_entries,
    }
    las_size = write_json(OUT / "uk" / "scotland_las.json", las_doc)

    total = sum(len(v) for v in by_council.values())
    placed = sum(1 for v in by_council.values() for s in v if s["lat"] is not None)
    with_roll = sum(1 for v in by_council.values() for s in v if s["pupils"] is not None)
    print("\nSchools per council")
    for entry in las_entries:
        schools = by_council[entry["la_code"]]
        phases = {}
        for s in schools:
            phases[s["phase"]] = phases.get(s["phase"], 0) + 1
        bits = " ".join(f"{k[:3].lower()}={v}" for k, v in sorted(phases.items()))
        print(f"  {entry['la_code']}  {entry['name']:<22} {entry['school_count']:>4}  {bits}")
    print(f"\n  total                            {total:>4} schools in {len(las_entries)} councils")
    print(f"  uk/scotland_las.json             {las_size / 1024:7.1f} KB")
    print(f"\nCoverage")
    print(f"  geocoded from postcode           {placed}/{total}")
    print(f"  no postcode published            {len(no_postcode)}")
    print(f"  postcode not found by postcodes.io {len(unplaced)}")
    print(f"  pupil roll published             {with_roll}/{total}")
    print(f"  grant-aided (filed by postcode)  {grant_aided}")
    if unknown_council:
        print(f"  council could not be resolved    {len(unknown_council)}: {unknown_council}")
    if no_postcode:
        print("\nNo postcode in the source (lat/lon null)")
        for n, la in no_postcode:
            print(f"  {la:<20} {n}")
    if unplaced:
        print("\nPostcode not found (lat/lon null)")
        for n, pc in unplaced:
            print(f"  {pc:<9} {n}")
    if boundary_mismatch:
        print(f"\nPostcode sits in a different council from the one running the school ({len(boundary_mismatch)})")
        for n, run_by, sits_in, pc in boundary_mismatch:
            print(f"  {pc:<9} {n} - run by {run_by}, postcode in {sits_in}")


if __name__ == "__main__":
    main()
