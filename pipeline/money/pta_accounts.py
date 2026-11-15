"""How parents' associations raise their money, read from the accounts they file with the Charity Commission.

The register's open data gives a parents' association's total income and spending, not how it raised the money. A
charity with an income over £25,000 files its accounts and trustees' annual report (TAR) as a PDF, and those say it:
"school discos, winter and summer fairs, cake sales", "Gift Aid claim £805", "Donations to the school £13,088".

Stages, each cached under pipeline/.cache/money/accounts/ so a stopped run resumes:
  list      the matched, registered associations with the largest latest income (pta.json), with their register
            organisation numbers (the register's URLs use those, not the charity number)
  download  each one's newest "Accounts and TAR" PDF from the register, one request every two seconds
  read      every page's text: the PDF's own text layer when it has one, else the page image read by a local vision
            model (LM Studio, OpenAI-compatible, never a remote service)
  extract   a local text model turns the pages into one JSON record per charity (EXTRACT_PROMPT below)
  write     pta_accounts.json: {charity_number: record}, for the site build

The models are local, so nothing about a charity leaves this machine. Every record carries the PDF's register URL
and the reporting year, and is labelled on the site as read automatically from the charity's own accounts.
"""

from __future__ import annotations

import argparse
import base64
import os
import html
import json
import re
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import urllib.parse
import urllib.request
from pathlib import Path

MAIN = Path(__file__).resolve().parents[2]
CACHE = MAIN / "pipeline/.cache/money/accounts"
PTA = MAIN / "pipeline/.cache/money/pta.json"
REGISTER = MAIN / "pipeline/.cache/charity/publicextract.charity.json"
OUT = MAIN / "pipeline/.cache/money/pta_accounts.json"
SITE = "https://register-of-charities.charitycommission.gov.uk"
USER_AGENT = "SchoolsInReach-research/1.0 (+https://www.schoolsinreach.com/about.html)"
REQUEST_GAP = 2.0          # seconds between requests to the register
LMSTUDIO = "http://127.0.0.1:1234/v1/chat/completions"
VISION_MODEL = "qwen/qwen3-vl-8b"
TEXT_MODEL = "qwen/qwen3.8-27b"
TEXT_LAYER_MIN = 80        # characters: a page with less text than this is read as an image
MAX_PAGES = 30

EXTRACT_PROMPT = """You are reading the annual report and accounts of a UK parents' association (a PTA, PTFA or
"Friends of" charity) for one school. Using ONLY what the pages say, return one JSON object:

{
  "year_end": "YYYY-MM-DD or null",
  "total_income": number or null,
  "total_spending": number or null,
  "how_raised": [ {"method": "short plain description, e.g. Summer fair", "amount": number or null} ],
  "gift_aid": number or null,
  "given_to_school": number or null,
  "paid_for": [ {"item": "short plain description, e.g. New playground markings", "amount": number or null} ],
  "platforms": ["named fundraising or giving platforms, e.g. easyfundraising, Kindlink, PTA Events"],
  "volunteers": number or null,
  "notes": "one short sentence only if something important doesn't fit above, else null"
}

Rules: amounts in pounds as plain numbers for the year the accounts are for (not the comparative year). List
"how_raised" and "paid_for" largest first, include every line that is at least 5% of the total, skip lines of zero,
and stop at 10 entries. When a table shows both gross takings and costs for an event, use the gross takings. A
method or item named without an amount gets "amount": null. Never invent, estimate or total anything yourself. If
the pages don't say, use null or an empty list. Plain British English, sentence case. Output only the JSON object.

PAGES:
"""


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- list

def top_associations(n: int, min_income: float = 25_000) -> list[dict]:
    """The matched, registered associations with the largest latest income, one entry per charity: the top n, or
    (n == 0) every one whose latest income is over min_income, the level above which a charity must file accounts."""
    schools = (load_json(PTA) or {}).get("schools") or {}
    seen = {}
    for urn, charities in schools.items():
        for ch in charities:
            if ch.get("status") != "Registered" or not ch.get("latest_income"):
                continue
            entry = seen.setdefault(ch["charity_number"], {"charity_number": ch["charity_number"], "name": ch["name"],
                                                           "latest_income": ch["latest_income"], "urns": []})
            entry["urns"].append(urn)
    ranked = sorted(seen.values(), key=lambda e: -e["latest_income"])
    ranked = [e for e in ranked if e["latest_income"] <= 500_000]   # pta.py holds larger ones back as likely mismatches
    return ranked[:n] if n else [e for e in ranked if e["latest_income"] > min_income]


def organisation_numbers(numbers: set[int]) -> dict[int, int]:
    """{registered charity number: register organisation number}, read from the register extract in one pass."""
    pattern = re.compile(rb'"organisation_number":(\d+),"registered_charity_number":(\d+),"linked_charity_number":0')
    found = {}
    with open(REGISTER, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            for org, reg in pattern.findall(chunk):
                if int(reg) in numbers:
                    found[int(reg)] = int(org)
    return found


# ---------------------------------------------------------------- download

_last = [0.0]
_fetch_lock = threading.Lock()


def fetch(url: str) -> bytes:
    """One request to the register at a time, REQUEST_GAP apart, however many workers are reading."""
    with _fetch_lock:
        wait = REQUEST_GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        finally:
            _last[0] = time.time()


def newest_accounts_url(org: int) -> tuple[str | None, str | None]:
    """(PDF URL, reporting year end text) of the newest 'Accounts and TAR' with a download link, or (None, None)."""
    page = fetch(f"{SITE}/en/charity-search/-/charity-details/{org}/accounts-and-annual-returns").decode("utf-8", "replace")
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        if "Accounts and TAR" not in row:
            continue
        link = re.search(r'href="([^"]*accounts-resource[^"]*)"', row)
        if link:
            year = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", row))).strip()
            when = re.search(r"\d{1,2} \w+ \d{4}", year)
            return html.unescape(link.group(1)), (when.group(0) if when else None)
    return None, None


# ---------------------------------------------------------------- read

def chat(model: str, content, max_tokens: int) -> str:
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}
    if model == TEXT_MODEL:
        body["reasoning_effort"] = "none"   # as pta_adjudicate does: a straight answer, no thinking preamble
    req = urllib.request.Request(LMSTUDIO, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def read_pages(pdf: Path) -> list[str]:
    """Each page's text: the text layer when it has enough, else the local vision model's transcription."""
    pages = []
    count = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout).group(1))
    for n in range(1, min(count, MAX_PAGES) + 1):
        text = subprocess.run(["pdftotext", "-layout", "-f", str(n), "-l", str(n), str(pdf), "-"], capture_output=True, text=True).stdout
        if len(text.strip()) >= TEXT_LAYER_MIN:
            pages.append(text.strip())
            continue
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-r", "110", "-png", "-f", str(n), "-l", str(n), str(pdf), f"{tmp}/p"], check=True)
            image = next(Path(tmp).glob("p*.png"))
            data = base64.b64encode(image.read_bytes()).decode()
        pages.append(chat(VISION_MODEL, [
            {"type": "text", "text": "Transcribe all the text on this page of a charity's annual report and accounts, exactly as "
                                     "written. Keep table rows on one line with their amounts. Output only the text."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + data}}], 2500).strip())
    return pages


# ---------------------------------------------------------------- extract

def extract(pages: list[str]) -> dict:
    text = "\n\n".join(f"--- page {i + 1} ---\n{p}" for i, p in enumerate(pages))[:60_000]
    raw = chat(TEXT_MODEL, EXTRACT_PROMPT + text, 2500)
    raw = re.sub(r"^.*?</think>", "", raw, flags=re.S).strip()
    match = re.search(r"\{.*\}", raw, re.S)
    return json.loads(match.group(0)) if match else {}


NUMBER = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?(?![\d,])|(?<![\d.,])\d+(?:\.\d{1,2})?(?![\d,.]\d)")


def numbers_in(pages: list[str]) -> set[float]:
    """Every whole number written in the pages ("1,776.30", "25,000", "145"), as values, so a figure only counts as
    stated when it is a number on the page, not digits inside a bigger one ("5000" in "25,000")."""
    found = set()
    for match in NUMBER.finditer("\n".join(pages)):
        try:
            found.add(round(float(match.group(0).replace(",", "")), 2))
        except ValueError:
            continue
    return found


COMMON = {"income", "costs", "cost", "from", "other", "total", "funds", "fund", "with", "and", "for", "the", "school",
          "including", "received", "paid", "expenses", "events", "event"}


def label_words(label) -> list[str]:
    """The distinctive words of a line's label ("Xmas fair costs" -> ["xmas", "fair"]): an amount for that line must
    appear on a line of the accounts carrying one of them, so a stray number elsewhere ("section 145") can't vouch
    for it (on_a_line_with allows three lines either side, for scans). A label with no distinctive word is checked by the number alone."""
    words = re.findall(r"[a-z]{3,}", str(label or "").lower())
    return [w[:5] for w in words if w not in COMMON]


def verify_amounts(facts: dict, pages: list[str]) -> dict:
    """Keep only the amounts that are written as numbers in the pages. The model is told never to add lines up or
    estimate, but it sometimes does (Belleville's two spending lines summed into £189,709; Brodetsky's gifts to two
    schools summed into one 'given to school'). Any amount not on the page becomes null and is listed under
    'dropped', so a figure on the site is always one the charity's own accounts state."""
    stated = numbers_in(pages)
    lines = [(line.lower(), numbers_in([line])) for page in pages for line in page.splitlines()]
    dropped = []

    def on_a_line_with(value: float, words: list[str], reach: int = 3) -> bool:
        """The amount is on a line within `reach` lines of one carrying a label word: scans read by the vision model
        often put a label and its amount on neighbouring lines."""
        for i, (_, nums) in enumerate(lines):
            if value in nums and any(any(w in text for w in words) for text, _ in lines[max(0, i - reach): i + reach + 1]):
                return True
        return False

    def keep(label, value, words=None):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return value
        value_r = round(float(value), 2)
        if value_r in stated and (not words or on_a_line_with(value_r, words)):
            return value
        dropped.append({"field": label, "amount": value})
        return None

    for key in ("total_income", "total_spending", "gift_aid"):
        if key in facts:
            facts[key] = keep(key, facts[key])
    if "given_to_school" in facts:     # a sum the model passed off as one gift fails here: it must sit by "school"
        facts["given_to_school"] = keep("given_to_school", facts["given_to_school"], ["schoo"])
    for key, name in (("how_raised", "method"), ("paid_for", "item")):
        for entry in facts.get(key) or []:
            if isinstance(entry, dict) and "amount" in entry:
                entry["amount"] = keep(f"{key}: {entry.get(name)}", entry["amount"], label_words(entry.get(name)))
    if dropped:
        facts["dropped"] = (facts.get("dropped") or []) + dropped
    return facts


def coverage(facts: dict) -> float | None:
    """Share of total income that the listed fundraising lines account for (None when it can't be worked out).
    The site lists the methods either way, but only calls them a breakdown when they cover most of the income."""
    total = facts.get("total_income")
    amounts = [m.get("amount") for m in facts.get("how_raised") or [] if isinstance(m, dict) and isinstance(m.get("amount"), (int, float))]
    if not isinstance(total, (int, float)) or total <= 0 or not amounts:
        return None
    return round(min(sum(amounts) / total, 9.99), 3)


# ---------------------------------------------------------------- run

RECHECK_DAYS = 14          # an association with no accounts online yet is looked at again after this long
LOAD_CEILING = 60          # 1-minute load average above which no new association is started
LOCK = CACHE / "run.lock"
DONE = CACHE / "complete.json"


def stop_time(text: str | None, now: datetime | None = None) -> datetime | None:
    """The moment to stop handing out work: 'HH:MM' is its next occurrence after now, else an ISO date-time."""
    if not text:
        return None
    now = now or datetime.now()
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        h, m = map(int, text.split(":"))
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return at if at > now else at + timedelta(days=1)
    return datetime.fromisoformat(text)


def take_lock() -> bool:
    """One run at a time: a lock file holding the pid, taken over when that process has gone."""
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        pid = int(LOCK.read_text().strip())
        os.kill(pid, 0)
        return False                      # still running
    except (OSError, ValueError):
        pass
    LOCK.write_text(str(os.getpid()))
    return True


LMS = Path.home() / ".lmstudio/bin/lms"


def loaded() -> set[str]:
    """Model identifiers LM Studio has loaded, asked of LM Studio's own CLI (works under launchd too)."""
    try:
        out = subprocess.run([str(LMS), "ps", "--json"], capture_output=True, text=True, timeout=60).stdout
        return {m.get("identifier") or m.get("modelKey") for m in json.loads(out or "[]")}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return set()


def models(action: str, log=print) -> bool:
    """Load or unload the two local models. Loading goes through local-llm (admission-checked) first; under launchd
    local-llm has refused with "unknown size", so LM Studio's own CLI is the fallback (the two need about 22 GB of
    the 84 GB budget). Returns whether both are loaded after a load, so a night isn't spent failing extractions."""
    for model in (VISION_MODEL, TEXT_MODEL):
        if action == "load" and model in loaded():
            log(f"{model}: already loaded"); continue
        out = subprocess.run(["local-llm", action, model], capture_output=True, text=True)
        log(f"local-llm {action} {model}: {(out.stdout or out.stderr).strip().splitlines()[-1:] or ['ok']}")
        if action == "load" and model not in loaded():
            out = subprocess.run([str(LMS), "load", model, "--yes"], capture_output=True, text=True, timeout=600)
            log(f"lms load {model}: {(out.stdout or out.stderr).strip().splitlines()[-1:] or ['ok']}")
    return action != "load" or {VISION_MODEL, TEXT_MODEL} <= loaded()


def due(record: dict | None) -> bool:
    if not record:
        return True
    if record.get("extracted"):
        return False
    checked = record.get("checked")
    return not checked or datetime.fromisoformat(checked) < datetime.now() - timedelta(days=RECHECK_DAYS)


def read_one(t: dict, org: int | None, records: dict, save, log, label: str):
    num = str(t["charity_number"])
    if not org:
        log(f"{label} {t['name']}: no organisation number"); return
    pdf = CACHE / f"{num}.pdf"
    meta = load_json(CACHE / f"{num}.meta.json", {}) or {}
    try:
        if not pdf.exists():
            url, year = newest_accounts_url(org)
            if not url:
                save(num, {"name": t["name"], "urns": t["urns"], "status": "no accounts online",
                           "checked": datetime.now().isoformat(timespec="seconds")})
                log(f"{label} {t['name']}: no accounts online"); return
            pdf.write_bytes(fetch(url))
            meta = {"source_url": url, "reporting_year": year, "organisation_number": org}
            save_json(CACHE / f"{num}.meta.json", meta)
        pages_file = CACHE / f"{num}.pages.json"
        pages = load_json(pages_file)
        if pages is None:
            t0 = time.time(); pages = read_pages(pdf); save_json(pages_file, pages)
            log(f"{label} {t['name']}: read {len(pages)} pages in {time.time() - t0:.0f}s")
        t0 = time.time()
        facts = verify_amounts(extract(pages), pages)
        save(num, {"name": t["name"], "urns": t["urns"], **meta, "facts": facts, "extracted": True, "coverage": coverage(facts),
                   "models": {"vision": VISION_MODEL, "text": TEXT_MODEL}, "extracted_at": time.strftime("%Y-%m-%d")})
        log(f"{label} {t['name']}: extracted in {time.time() - t0:.0f}s, "
            f"{len(facts.get('how_raised') or [])} methods, {len(facts.get('paid_for') or [])} items")
    except Exception as err:   # one charity's failure never stops the run; it is retried next time
        log(f"{label} {t['name']}: {type(err).__name__}: {err}")


def run(n: int, *, workers: int = 4, stop_at: datetime | None = None, log=print) -> dict:
    """Read every due association, `workers` at a time, handing out no new one after stop_at."""
    targets = top_associations(n)
    orgs = load_json(CACHE / "orgs.json", {}) or {}
    missing = {t["charity_number"] for t in targets if str(t["charity_number"]) not in orgs}
    if missing:
        log(f"looking up {len(missing)} organisation numbers in the register extract")
        orgs.update({str(k): v for k, v in organisation_numbers(missing).items()})
        save_json(CACHE / "orgs.json", orgs)
    lock = threading.Lock()
    records = load_json(OUT, {}) or {}
    todo = [t for t in targets if due(records.get(str(t["charity_number"])))]
    log(f"{len(targets)} associations, {len(todo)} still to read" + (f", stopping at {stop_at:%a %d %b %H:%M}" if stop_at else ""))

    def save(num, record):
        with lock:
            current = load_json(OUT, {}) or {}   # another writer (a spot check) may have added keys since
            current[num] = record
            records.clear(); records.update(current)
            save_json(OUT, current)

    def job(i_t):
        i, t = i_t
        # Back off while the Mac is busy: on 15 Nov it reached a load average of 400-560 with this reader, builds and
        # other agents together, and crashed (hardware watchdog, then a launchd panic). Wait for the load to fall.
        while os.getloadavg()[0] > LOAD_CEILING:
            if stop_at and datetime.now() >= stop_at:
                return "stopped"
            time.sleep(30)
        if stop_at and datetime.now() >= stop_at:
            return "stopped"
        read_one(t, orgs.get(str(t["charity_number"])), records, save, log, f"{i}/{len(todo)}")
        return "done"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(job, enumerate(todo, 1)))
    left = [t for t in targets if due((load_json(OUT, {}) or {}).get(str(t["charity_number"])))]
    if not left:
        save_json(DONE, {"completed": datetime.now().isoformat(timespec="seconds"), "associations": len(targets)})
        log("every association has been read")
    elif "stopped" in results:
        log(f"stopped at {datetime.now():%H:%M} with {len(left)} still to read")
    return load_json(OUT, {}) or {}


def reverify(log=print) -> int:
    """Re-run verify_amounts on every saved record from its cached pages (after the check changes); returns how many
    records changed. Amounts dropped earlier stay dropped: only what is still shown is re-checked."""
    with _fetch_lock:
        records = load_json(OUT, {}) or {}
        changed = 0
        for num, record in records.items():
            if not (isinstance(record, dict) and record.get("extracted")):
                continue
            pages = load_json(CACHE / f"{num}.pages.json")
            if pages is None:
                continue
            before = json.dumps(record["facts"], sort_keys=True)
            record["facts"] = verify_amounts(record["facts"], pages)
            record["coverage"] = coverage(record["facts"])
            changed += json.dumps(record["facts"], sort_keys=True) != before
        save_json(OUT, records)
    log(f"re-verified {sum(1 for r in records.values() if isinstance(r, dict) and r.get('extracted'))} records, {changed} changed")
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--top", type=int, default=0, help="read the n largest associations (0: every one that files accounts)")
    parser.add_argument("--workers", type=int, default=4, help="associations read at once (the models take 4 each)")
    parser.add_argument("--stop-at", help="stop handing out work at HH:MM (its next occurrence) or an ISO date-time")
    parser.add_argument("--manage-models", action="store_true", help="load the two models at the start, unload them at the end")
    parser.add_argument("--reverify", action="store_true", help="only re-check saved records' amounts against their pages")
    args = parser.parse_args(argv)
    log = lambda msg: print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)
    if args.reverify:
        reverify(log); return
    if DONE.exists() and not args.top:
        log(f"already complete ({load_json(DONE)}); nothing to do"); return
    if not take_lock():
        log("another run is already reading; leaving it to finish"); return
    try:
        if args.manage_models and not models("load", log):
            log("the models would not load; stopping so the night isn't spent on failures"); return
        records = run(args.top, workers=args.workers, stop_at=stop_time(args.stop_at), log=log)
        done = sum(1 for r in records.values() if isinstance(r, dict) and r.get("extracted"))
        log(f"{done} associations extracted in all; {OUT}")
    finally:
        if args.manage_models:
            models("unload", log)
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
