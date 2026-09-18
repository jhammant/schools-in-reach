"""Download helpers for the DfE pipeline.

Every remote file is cached under pipeline/.cache/dfe/. Government sites reject
curl/urllib's default user agent, so all requests send browser-like headers.
Large Explore Education Statistics (EES) CSVs are streamed and filtered to
Hackney (plus national/LA aggregate rows) so the cache stays small.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "pipeline" / ".cache" / "dfe"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

CSCP = "https://www.compare-school-performance.service.gov.uk"
FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk"
EES_CONTENT = "https://content.explore-education-statistics.service.gov.uk/api"

LA_CODE = "204"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _open(url: str, timeout: int = 300):
    req = urllib.request.Request(url, headers=HEADERS)
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except (urllib.error.URLError, TimeoutError) as err:  # transient network errors
            last_err = err
            if isinstance(err, urllib.error.HTTPError) and err.code in (400, 401, 403, 404):
                break
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last_err}")


def download(url: str, dest: Path, refresh: bool = False) -> Path:
    """Download url to dest unless it is already cached."""
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"  downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _open(url) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    if tmp.stat().st_size == 0:
        tmp.unlink()
        raise RuntimeError(f"empty download: {url}")
    tmp.replace(dest)
    return dest


# --------------------------------------------------------------------------
# Compare school and college performance (CSCP)
# --------------------------------------------------------------------------

CSCP_DATATYPES = [
    "GIAS", "KS2", "KS4", "KS5", "KS4DESTINATION", "KS5DESTINATION",
    "KS5DESTINATIONHE", "PUPILABSENCE", "CENSUS",
]


def cscp_la_zip(year: str, refresh: bool = False) -> Path:
    """Performance-table download for LA 204. year like '2024-2025'.

    The query string mirrors the final step of the /download-data form
    (currentstep=year -> region -> datatypes -> file link).
    """
    url = (
        f"{CSCP}/download-data?download=true&regions={LA_CODE}"
        f"&filters={','.join(CSCP_DATATYPES)}&fileformat=csv&year={year}&meta=false"
    )
    dest = download(url, CACHE / f"cscp_{LA_CODE}_{year}.zip", refresh)
    target = CACHE / "cscp"
    with zipfile.ZipFile(dest) as zf:
        zf.extractall(target)
    return target / year


def cscp_england_zip(year: str, refresh: bool = False) -> Path:
    """All-of-England performance-table download (regiontype=all -> regions=0)."""
    url = (
        f"{CSCP}/download-data?download=true&regions=0"
        f"&filters={','.join(CSCP_DATATYPES)}&fileformat=csv&year={year}&meta=false"
    )
    dest = download(url, CACHE / f"cscp_england_{year}.zip", refresh)
    target = CACHE / "cscp_england"
    if refresh and target.exists():
        shutil.rmtree(target / year, ignore_errors=True)
    with zipfile.ZipFile(dest) as zf:
        zf.extractall(target)
    return target / year


def cscp_meta_zip(year: str, refresh: bool = False) -> Path:
    url = (
        f"{CSCP}/download-data?download=true&regions={','.join(CSCP_DATATYPES)}"
        f"&filters=meta&fileformat=csv&year={year}&meta=true"
    )
    dest = download(url, CACHE / f"cscp_meta_{year}.zip", refresh)
    with zipfile.ZipFile(dest) as zf:
        zf.extractall(CACHE / "cscp")
    return CACHE / "cscp" / year


# --------------------------------------------------------------------------
# Financial Benchmarking and Insights Tool (CFR / AAR workbooks)
# --------------------------------------------------------------------------

def fbit_file(name: str, refresh: bool = False) -> Path:
    return download(f"{FBIT}/files/{name}", CACHE / "fbit" / name, refresh)


# --------------------------------------------------------------------------
# Explore Education Statistics data catalogue
# --------------------------------------------------------------------------

def ees_catalogue(publication_id: str, latest_only: bool = True) -> list[dict]:
    """List data-set files of an EES publication (all pages)."""
    results: list[dict] = []
    page = 1
    while True:
        url = (
            f"{EES_CONTENT}/data-set-files?publicationId={publication_id}"
            f"&pageSize=40&page={page}&latestOnly={'true' if latest_only else 'false'}"
        )
        with _open(url, timeout=60) as resp:
            data = json.load(resp)
        results.extend(data.get("results", []))
        paging = data.get("paging") or {}
        if page >= paging.get("totalPages", 1):
            return results
        page += 1


def ees_find(publication_id: str, filename: str, release_title: str | None = None) -> dict:
    """Return catalogue entry for filename, caching the lookup."""
    key = f"{publication_id}__{release_title or 'latest'}__{filename}"
    index_path = CACHE / "ees" / "catalogue_index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    if key in index:
        return index[key]
    entries = ees_catalogue(publication_id, latest_only=release_title is None)
    for entry in entries:
        if entry["filename"] == filename and (
            release_title is None or entry["release"]["title"] == release_title
        ):
            slim = {
                "id": entry["id"],
                "filename": entry["filename"],
                "title": entry["title"].strip(),
                "release": entry["release"]["title"],
                "publication": entry["publication"]["title"],
                "publication_slug": entry["publication"]["slug"],
                "time_period_range": entry.get("meta", {}).get("timePeriodRange"),
            }
            index[key] = slim
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(json.dumps(index, indent=1))
            return slim
    raise RuntimeError(f"EES file {filename} not found in publication {publication_id}")


SUPPRESSION_CODES = {"x", "c", "z", "u", "low", "SUPP", "NE", "NA", "LOWCOV", "NP", ":"}
ID_COLUMNS = {
    "time_period", "old_la_code", "new_la_code", "school_urn", "school_laestab",
    "urn", "laestab", "region_code", "country_code",
}


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def ees_filtered(
    publication_id: str,
    filename: str,
    release_title: str | None = None,
    refresh: bool = False,
    la_code: str | None = LA_CODE,
) -> tuple[Path, Path | None, dict]:
    """Stream an EES CSV, keeping selected rows.

    With la_code set, keeps that LA's rows plus national rows. With
    la_code=None, keeps every row (all LAs and all schools).

    School-level files also get an England-wide sum of every numeric column per
    time_period (written alongside) so national benchmarks can be derived
    without keeping the full file.

    Returns (extract_path, england_sums_path_or_None, catalogue_entry).
    """
    entry = ees_find(publication_id, filename, release_title)
    stem = Path(filename).stem
    tag = la_code or "all"
    out = CACHE / "ees" / f"{stem}__{tag}.csv"
    sums_out = CACHE / "ees" / f"{stem}__england_sums.json"
    if out.exists() and not refresh:
        return out, (sums_out if sums_out.exists() else None), entry

    url = f"{EES_CONTENT}/data-set-files/{entry['id']}/download"
    log(f"  streaming {filename} ({entry['release']}) from EES")
    out.parent.mkdir(parents=True, exist_ok=True)
    sums: dict[str, dict[str, float]] = {}
    school_level = False
    kept = 0
    with _open(url, timeout=900) as resp:
        text = io.TextIOWrapper(resp, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text)
        fields = reader.fieldnames or []
        with open(out.with_suffix(".part"), "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in reader:
                level = row.get("geographic_level", "")
                laestab = row.get("school_laestab") or row.get("laestab") or ""
                la = row.get("old_la_code") or row.get("la_code") or laestab[:3]
                if level == "School":
                    school_level = True
                    # Only rows with no suppressed cells, so numerators and
                    # denominators are summed over the same schools.
                    if not any(v in SUPPRESSION_CODES for v in row.values()):
                        bucket = sums.setdefault(row.get("time_period", ""), {"_rows": 0})
                        bucket["_rows"] += 1
                        for key, value in row.items():
                            if value and key not in ID_COLUMNS and _is_number(value):
                                bucket[key] = bucket.get(key, 0.0) + float(value)
                if la_code is None or la == la_code or level == "National":
                    writer.writerow(row)
                    kept += 1
    out.with_suffix(".part").replace(out)
    if school_level:
        sums_out.write_text(json.dumps(sums))
    elif sums_out.exists():
        sums_out.unlink()
    log(f"    kept {kept} rows")
    return out, (sums_out if school_level else None), entry
