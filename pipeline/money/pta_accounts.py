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
import html
import json
import re
import subprocess
import tempfile
import time
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

def top_associations(n: int) -> list[dict]:
    """The n matched, registered associations with the largest latest income, one entry per charity."""
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
    return [e for e in ranked if e["latest_income"] <= 500_000][:n]   # pta.py holds larger ones back as likely mismatches


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


def fetch(url: str) -> bytes:
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


def coverage(facts: dict) -> float | None:
    """Share of total income that the listed fundraising lines account for (None when it can't be worked out).
    The site lists the methods either way, but only calls them a breakdown when they cover most of the income."""
    total = facts.get("total_income")
    amounts = [m.get("amount") for m in facts.get("how_raised") or [] if isinstance(m, dict) and isinstance(m.get("amount"), (int, float))]
    if not isinstance(total, (int, float)) or total <= 0 or not amounts:
        return None
    return round(min(sum(amounts) / total, 9.99), 3)


# ---------------------------------------------------------------- run

def run(n: int, log=print) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    targets = top_associations(n)
    orgs = load_json(CACHE / "orgs.json", {}) or {}
    missing = {t["charity_number"] for t in targets if str(t["charity_number"]) not in orgs}
    if missing:
        log(f"looking up {len(missing)} organisation numbers in the register extract")
        orgs.update({str(k): v for k, v in organisation_numbers(missing).items()})
        save_json(CACHE / "orgs.json", orgs)
    records = load_json(OUT, {}) or {}
    for i, t in enumerate(targets, 1):
        num = str(t["charity_number"])
        if num in records and records[num].get("extracted"):
            continue
        org = orgs.get(num)
        if not org:
            log(f"{i}/{len(targets)} {t['name']}: no organisation number"); continue
        pdf = CACHE / f"{num}.pdf"
        meta = load_json(CACHE / f"{num}.meta.json", {}) or {}
        try:
            if not pdf.exists():
                url, year = newest_accounts_url(org)
                if not url:
                    records[num] = {"name": t["name"], "urns": t["urns"], "status": "no accounts filed"}
                    save_json(OUT, records); log(f"{i}/{len(targets)} {t['name']}: no accounts to download"); continue
                pdf.write_bytes(fetch(url))
                meta = {"source_url": url, "reporting_year": year, "organisation_number": org}
                save_json(CACHE / f"{num}.meta.json", meta)
            pages_file = CACHE / f"{num}.pages.json"
            pages = load_json(pages_file)
            if pages is None:
                t0 = time.time(); pages = read_pages(pdf); save_json(pages_file, pages)
                log(f"{i}/{len(targets)} {t['name']}: read {len(pages)} pages in {time.time() - t0:.0f}s")
            t0 = time.time()
            facts = extract(pages)
            records[num] = {"name": t["name"], "urns": t["urns"], **meta, "facts": facts, "extracted": True,
                            "coverage": coverage(facts),
                            "models": {"vision": VISION_MODEL, "text": TEXT_MODEL}, "extracted_at": time.strftime("%Y-%m-%d")}
            save_json(OUT, records)
            log(f"{i}/{len(targets)} {t['name']}: extracted in {time.time() - t0:.0f}s, "
                f"{len(facts.get('how_raised') or [])} methods, {len(facts.get('paid_for') or [])} items")
        except Exception as err:   # one charity's failure never stops the run; it is retried next time
            log(f"{i}/{len(targets)} {t['name']}: {type(err).__name__}: {err}")
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--top", type=int, default=100, help="how many of the largest associations to read")
    args = parser.parse_args(argv)
    records = run(args.top)
    done = sum(1 for r in records.values() if r.get("extracted"))
    print(f"{done} of {len(records)} associations extracted; wrote {OUT}")


if __name__ == "__main__":
    main()
