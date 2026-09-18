"""Shared helpers for the Ofsted / Parent View / childcare / census pipeline.

All downloads are cached under pipeline/.cache/ofsted/. Government sites can
reject non-browser user agents, so every request sends browser-like headers.
Only the Python standard library is used here (the fetch/CSV/ODS layer has no
third-party dependencies); pandas is only imported, lazily, by nurseries.py's
NSPL postcode lookup.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "pipeline" / ".cache" / "ofsted"
SHARED = ROOT / "pipeline" / ".cache" / "shared"
LA_ROOT = ROOT / "site" / "data" / "la"
HACKNEY_DIR = ROOT / "site" / "data" / "hackney"  # reference output for compare_hackney.py; never written to

# Kept for scripts (verify.py default, compare_hackney.py) that need Hackney's own code/name.
LA_CODE = "204"
LA_NAME = "Hackney"
OGL = "Open Government Licence v3.0"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

GOVUK_CONTENT_API = "https://www.gov.uk/api/content/government/statistical-data-sets/"
REPORTS = "https://reports.ofsted.gov.uk/provider"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def http_open(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 300):
    hdrs = dict(HEADERS)
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs)
    last: Exception | None = None
    for attempt in range(4):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as err:
            last = err
            if err.code in (400, 401, 403, 404, 410):
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            last = err
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}: {last}")


def fetch(url: str, dest: Path, refresh: bool = False) -> Path:
    """Download url to dest unless already cached (atomic write)."""
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"  downloading {url}")
    tmp = dest.with_name(dest.name + ".part")
    with http_open(url) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    if tmp.stat().st_size == 0:
        tmp.unlink()
        raise RuntimeError(f"empty download: {url}")
    tmp.replace(dest)
    return dest


def fetch_json(url: str, dest: Path, refresh: bool = False):
    return json.loads(fetch(url, dest, refresh).read_text(encoding="utf-8"))


def post_json(url: str, payload) -> dict:
    body = json.dumps(payload).encode("utf-8")
    with http_open(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=120) as resp:
        return json.load(resp)


# ---------------------------------------------------------------------------
# gov.uk statistical data set pages
# ---------------------------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def title_date(text: str) -> date | None:
    """First 'D Month YYYY' date after 'as at' (or anywhere) in a title."""
    m = re.search(r"as at\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text) or re.search(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if not m:
        return None
    mon = MONTHS.get(m.group(2)[:3].lower())
    return date(int(m.group(3)), mon, int(m.group(1))) if mon else None


def govuk_attachments(slug: str, refresh: bool = False) -> tuple[dict, list[dict]]:
    page = fetch_json(GOVUK_CONTENT_API + slug, CACHE / "govuk" / f"{slug}.json", refresh)
    return page, page["details"].get("attachments", [])


def pick_attachment(attachments: list[dict], title_re: str, ext: str,
                    as_at: date | None = None) -> dict:
    """Latest attachment whose title matches title_re and url ends with ext.

    With as_at, the attachment for that exact date is returned instead.
    """
    rx = re.compile(title_re, re.I)
    cands = []
    for att in attachments:
        title = att.get("title", "")
        if rx.search(title) and att.get("url", "").lower().endswith(ext):
            d = title_date(title)
            if d and (as_at is None or d == as_at):
                cands.append((d, att))
    if not cands:
        raise RuntimeError(f"no attachment matching {title_re!r} ({ext}, as_at={as_at})")
    cands.sort(key=lambda x: x[0])
    d, att = cands[-1]
    return {"title": att["title"].strip(), "url": att["url"], "as_at": d}


def cached_attachment(att: dict, prefix: str, refresh: bool = False) -> Path:
    ext = Path(att["url"]).suffix.lower()
    return fetch(att["url"], CACHE / f"{prefix}_{att['as_at']:%Y%m%d}{ext}", refresh)


# ---------------------------------------------------------------------------
# File readers
# ---------------------------------------------------------------------------

def open_text(path: Path) -> io.TextIOWrapper:
    raw = path.read_bytes()[:4096]
    if raw.startswith(b"\xef\xbb\xbf"):
        enc = "utf-8-sig"
    else:
        try:
            path.read_bytes().decode("utf-8")
            enc = "utf-8"
        except UnicodeDecodeError:
            enc = "cp1252"
    return open(path, encoding=enc, newline="")


def read_csv(path: Path, header_first_cell: str | None = None) -> list[dict]:
    """Read a CSV into dicts. If header_first_cell is given, rows before the
    header row (title/notes rows in Ofsted accessible CSVs) are skipped."""
    with open_text(path) as fh:
        reader = csv.reader(fh)
        header = None
        rows = []
        for row in reader:
            if header is None:
                if header_first_cell is None or (row and row[0].strip() == header_first_cell):
                    header = [h.strip() for h in row]
                continue
            if not any(c.strip() for c in row):
                continue
            rows.append({header[i]: row[i] for i in range(min(len(header), len(row))) if header[i]})
    if header is None:
        raise RuntimeError(f"header not found in {path}")
    return rows


_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_X = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def ods_rows(path: Path, sheet: str) -> Iterator[list[str]]:
    """Stream the rows of one sheet of an .ods file as lists of cell text.

    Much faster than odfpy for large Ofsted workbooks (content.xml can be
    hundreds of MB); repeated empty trailing cells are trimmed.
    """
    with zipfile.ZipFile(path) as zf, zf.open("content.xml") as fh:
        current = None
        for event, el in ET.iterparse(fh, events=("start", "end")):
            if event == "start" and el.tag == _T + "table":
                current = el.get(_T + "name")
            elif event == "end" and el.tag == _T + "table-row":
                if current == sheet:
                    vals: list[str] = []
                    for cell in el:
                        rep = int(cell.get(_T + "number-columns-repeated", "1"))
                        text = "\n".join("".join(p.itertext()) for p in cell.findall(_X + "p"))
                        vals.extend([text] * min(rep, 1000))
                    while vals and vals[-1] == "":
                        vals.pop()
                    yield vals
                el.clear()
            elif event == "end" and el.tag == _T + "table":
                if current == sheet:
                    return
                el.clear()


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

NULLS = {"", "NULL", "null", "NA", "N/A", "x", "z", "c", "u", "[z]", "[x]", "[c]", "[w]", "[u]", ":", "REDACTED"}


def clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return None if v in NULLS else v


def iso(d: str | None) -> str | None:
    """dd/mm/yyyy -> yyyy-mm-dd."""
    d = clean(d)
    if not d:
        return None
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", d)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", d)
    return m.group(0) if m else None


def to_int(v: str | None) -> int | None:
    v = clean(v)
    if v is None:
        return None
    try:
        return int(float(v.replace(",", "")))
    except ValueError:
        return None


def to_float(v: str | None, dp: int = 1) -> float | None:
    v = clean(v)
    if v is None:
        return None
    try:
        return round(float(v.replace(",", "").rstrip("%")), dp)
    except ValueError:
        return None


def prune(obj):
    """Drop None values and empty dicts/lists recursively (keeps False/0)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v = prune(v)
            if v is None or v == {} or v == []:
                continue
            out[k] = v
        return out
    if isinstance(obj, list):
        return [prune(v) for v in obj]
    return obj


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_la_json(la_code: str, name: str, obj) -> Path:
    """Write one output file under site/data/la/<la_code>/<name> (atomic)."""
    out_dir = LA_ROOT / la_code
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# GIAS register (shared download made by another pipeline stage)
# ---------------------------------------------------------------------------

def gias_path() -> Path:
    files = sorted(SHARED.glob("gias_edubasealldata_*.csv"))
    if not files:
        raise RuntimeError(f"GIAS extract not found in {SHARED}")
    return files[-1]


_gias_rows_cache: list[dict] | None = None


def gias_rows() -> list[dict]:
    """All GIAS rows (open and closed, every country), read once and cached in memory."""
    global _gias_rows_cache
    if _gias_rows_cache is None:
        _gias_rows_cache = read_csv(gias_path())
    return _gias_rows_cache


def is_english_la_code(code: str | None) -> bool:
    """True for a DfE LA code that is an English local authority.

    Excludes '000' (not applicable - FE/HE/overseas establishments), Welsh LAs
    (660-681) and offshore/overseas establishment "LAs" (701-708).
    """
    if not code or not code.isdigit():
        return False
    n = int(code)
    if n == 0:
        return False
    if 660 <= n <= 681:
        return False
    if 701 <= n <= 708:
        return False
    return True


def gias_open_all() -> dict[str, dict]:
    """Open establishments in every English LA, keyed by URN string."""
    return {r["URN"]: r for r in gias_rows()
            if is_english_la_code(r.get("LA (code)")) and (r.get("EstablishmentStatus (name)") or "").startswith("Open")}


_la_registry_cache: dict[str, str] | None = None


def la_registry() -> dict[str, str]:
    """English LA code -> LA name, sorted by code (derived from open GIAS establishments)."""
    global _la_registry_cache
    if _la_registry_cache is None:
        reg: dict[str, str] = {}
        for r in gias_rows():
            code = r.get("LA (code)")
            if is_english_la_code(code) and (r.get("EstablishmentStatus (name)") or "").startswith("Open"):
                reg.setdefault(code, r.get("LA (name)"))
        _la_registry_cache = dict(sorted(reg.items(), key=lambda kv: kv[0]))
    return _la_registry_cache


_LA_NAME_ALIASES = {"durham": "county durham"}


def norm_la_name(s: str) -> str:
    """Normalise a free-text LA name for matching against GIAS 'LA (name)' spellings."""
    s = (s or "").lower().strip().replace("&", "and")
    s = re.sub(r",?\s*(city|county) of$", "", s).strip()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return _LA_NAME_ALIASES.get(s, s)


_la_name_index_cache: dict[str, str] | None = None


def la_name_index() -> dict[str, str]:
    """Normalised LA name -> LA code, for matching source files' LA-name text columns."""
    global _la_name_index_cache
    if _la_name_index_cache is None:
        _la_name_index_cache = {norm_la_name(name): code for code, name in la_registry().items()}
    return _la_name_index_cache


def la_code_for_name(name: str | None) -> str | None:
    """DfE LA code for a free-text LA name (e.g. from a national MI file), or None if unmatched."""
    if not name:
        return None
    return la_name_index().get(norm_la_name(name))


_district_to_la_cache: dict[str, str] | None = None


def district_to_la() -> dict[str, str]:
    """ONS local authority district code (e.g. E09000012) -> DfE LA code, from GIAS.

    County councils cover several districts, so several district codes map to the
    same DfE LA code; that is expected, not a collision.
    """
    global _district_to_la_cache
    if _district_to_la_cache is None:
        out: dict[str, str] = {}
        for r in gias_rows():
            d = r.get("DistrictAdministrative (code)")
            code = r.get("LA (code)")
            if d and is_english_la_code(code):
                out.setdefault(d, code)
        _district_to_la_cache = out
    return _district_to_la_cache


_district_name_cache: dict[str, str] | None = None


def district_name_index() -> dict[str, str]:
    """ONS local authority district code -> district name, from GIAS (for display, e.g. nurseries.json 'district')."""
    global _district_name_cache
    if _district_name_cache is None:
        out: dict[str, str] = {}
        for r in gias_rows():
            d, name = r.get("DistrictAdministrative (code)"), r.get("DistrictAdministrative (name)")
            if d and name:
                out.setdefault(d, name)
        _district_name_cache = out
    return _district_name_cache
