#!/usr/bin/env python3
"""Build the standalone School Money site (site_money/): English school finances from DfE returns.

Inputs are local and rebuilt by pipelines; no network:
- pipeline/.cache/dfe/finance_history.jsonl from pipeline/dfe/finance_history.py
- site/data (school register and council index, from pipeline/dfe/build.py)
- pipeline/.cache/dfe/gias/links.csv (GIAS links: a converted academy's predecessor URN)
- pipeline/.cache/money/pta.json from pipeline/money/pta.py (optional)
- pipeline/money/data/la_dsg.json (council high-needs balances, committed)

Writes site_money/, served at https://money.schoolsinreach.com: national, council, constituency,
school, trust, compare, about and stub pages at clean paths; /data/{search,status}.json,
/data/s/<urn>.json and /data/a/<id>.json for the app; sitemap, robots and 404. Long tables
continue on /2/, /3/… pages so every page stays under PAGE_BUDGET. pipeline/seo/build_pages.py reads
/data/status.json to link school pages here.

Pages are wrapped by pipeline/money/site.py (the app shell) when it is present, else by a
minimal fallback below with the same signatures. areas.py, timeline.py and deflator.py are
optional too: pages gain tags, a status timeline and real-terms figures when they import.
"""
import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date
from html import escape
from pathlib import Path
import shutil
import statistics
import tempfile
import time
import xml.etree.ElementTree as ET

from pipeline.money import charts, status as health
from pipeline.money.charts import STATUS_LABELS, STATUS_ORDER, badge, esc, money
from pipeline.seo.build_pages import NS, HeadMetadata, closed, shorten, slug, table

try:
    from pipeline.money import site as shell
except ImportError:  # unit a3's shell not present: the fallback below is used
    shell = None
try:
    from pipeline.money import areas
except ImportError:
    areas = None
try:
    from pipeline.money import timeline
except ImportError:
    timeline = None
try:
    from pipeline.money import deflator
except ImportError:
    deflator = None

ROOT = Path(__file__).resolve().parents[2]
BASE_MONEY = "https://money.schoolsinreach.com"
BASE_SIR = "https://www.schoolsinreach.com"
FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk"
FBIT_SOURCES = FBIT + "/data-sources"
CHARITY = "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/"
OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
LONDON = set(range(201, 214)) | set(range(301, 321))
SIMILAR_N = 30
COMPARE_KEYS = [
    ("teaching_staff", "Teachers"),
    ("education_support_staff", "Support staff (e.g. TAs)"),
    ("supply_staff", "Supply staff"),
    ("admin_clerical_staff", "Admin and clerical"),
    ("premises", "Premises"),
    ("energy", "Energy"),
    ("educational_supplies", "Learning resources & ICT"),
    ("bought_in_services", "Bought-in services"),
]
# (row key, glossary key, label): the income lines a school page and its JSON carry when present.
INCOME_LINES = [
    ("grant_funding", "grant_funding", "Grants"),
    ("grant_funding_government", "grant_funding_government", "Government grants"),
    ("sen_funding", "sen_funding", "SEN funding (part of grants)"),
    ("pupil_premium", "pupil_premium", "Pupil premium (part of grants)"),
    ("self_generated", "self_generated_income", "Self-generated (lettings, catering, donations)"),
    ("donations_revenue", "donations_revenue", "Donations and voluntary funds"),
    ("lettings_income", "lettings_income", "Lettings"),
    ("catering_income", "catering_income", "Catering income"),
]
TOP_N = 10
# No rendered page may reach PAGE_BUDGET. Schools in Reach keeps its pages under 40 KB; here every £ figure
# carries data-* metadata for the app and the shell is richer, so the ceiling is 48 KB (about 8 KB gzipped).
PAGE_BUDGET = 48_000
TABLE_BUDGET = 24_000  # bytes of table rows on one page, leaving room for the page around them
DSG_YEARS = 6          # years of DSG balances listed on a page (the area JSON carries them all)
URN = re.compile(r"[0-9]{1,8}")
PATH = re.compile(r"/(?:[a-z0-9-]+/)*")
STUBS = [
    ("/areas/", "Areas", "School finances by region, council and constituency: how many schools are in deficit and how the money per pupil compares.",
     [("Councils", "/council/"), ("England", "/")]),
    ("/map/", "Map", "A map of every school's financial status is coming. Until then, browse by council or search for a school.",
     [("Councils", "/council/"), ("Find a school", "/")]),
    ("/ptfa/", "PTFA", "Money raised by parent-teacher associations, matched to schools from the Charity Commission register, appears on each school's page.",
     [("Find a school", "/"), ("How PTAs are matched", "/about/#method")]),
    ("/debts/", "Debts", "Schools in deficit, councils' high-needs balances and the trend over recent years.",
     [("Biggest deficits", "/"), ("Councils", "/council/")]),
    ("/guides/", "Guides", "Plain-English guides to school money for parents, governors, PTFA committees and school leaders are on their way.",
     [("How the figures work", "/about/"), ("Find a school", "/")]),
    ("/search/", "Search", "Type a school, council, trust or postcode in the search box above. Without JavaScript, browse by council instead.",
     [("Councils", "/council/"), ("Academy trusts", "/trust/")]),
]


# ----------------------------------------------------------------- shell

class _FallbackShell:
    """Minimal stand-in for pipeline/money/site.py with the same signatures, so the build runs
    (and its tests pass) before or without the app shell. Same data-* contract for app.js."""

    BASE_MONEY = BASE_MONEY
    BASE_SIR = BASE_SIR
    NAV = [("Find a school", "/"), ("Map", "/map/"), ("Areas", "/areas/"), ("Trusts", "/trust/"),
           ("PTFA", "/ptfa/"), ("Debts", "/debts/"), ("Compare", "/compare/"), ("Guides", "/guides/")]

    @staticmethod
    def _num(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (math.inf, -math.inf):
            return None
        return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")

    def page(self, title, description, path, body, crumbs, *, og_image=None, indexable=True, extra_head=""):
        if not path.startswith("/"):
            raise ValueError(f"path must be absolute: {path!r}")
        url = BASE_MONEY + path
        ld = json.dumps([{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": n, "item": BASE_MONEY + p} for i, (n, p) in enumerate(crumbs, 1)]}],
            ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
        head = [f"<title>{esc(title)}</title>", f'<meta name="description" content="{esc(description)}">',
                f'<link rel="canonical" href="{esc(url)}">']
        if not indexable:
            head.append('<meta name="robots" content="noindex,follow">')
        for k, v in (("og:type", "website"), ("og:site_name", "School Money"), ("og:title", title), ("og:description", description), ("og:url", url)):
            head.append(f'<meta property="{k}" content="{esc(v)}">')
        head.append(f'<meta name="twitter:card" content="summary"><meta name="twitter:title" content="{esc(title)}">')
        if og_image:
            head.append(f'<meta property="og:image" content="{esc(og_image)}">')
        head.append('<link rel="stylesheet" href="/assets/app.css"><script src="/assets/app.js" defer></script>')
        head.append(f'<script type="application/ld+json">{ld}</script>')
        if extra_head:
            head.append(extra_head)
        nav = "".join(f'<a href="{esc(p)}">{esc(n)}{" <span data-pin-count>0</span>" if p == "/compare/" else ""}</a>' for n, p in self.NAV)
        trail = ' <span aria-hidden="true">›</span> '.join(
            f'<a href="{esc(p)}">{esc(n)}</a>' if i < len(crumbs) - 1 else f'<span aria-current="page">{esc(n)}</span>' for i, (n, p) in enumerate(crumbs))
        audience = "".join(f'<button type="button" data-audience="{a}">{a.title()}</button>' for a in ("parent", "governor", "ptfa", "leader", "pupil"))
        return (f'<!doctype html>\n<html lang="en-GB" data-audience="parent"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">\n{chr(10).join(head)}\n</head>'
                f'<body><a class="skip" href="#main">Skip to content</a><header class="top"><a class="brand" href="/">School Money</a> '
                f'<a class="tagline" href="{BASE_SIR}">by Schools in Reach</a>'
                f'<form role="search" action="/search/"><label for="q">Search</label><input id="q" name="q" type="search"><button type="submit">Search</button></form>'
                f'<nav class="main-nav" aria-label="Main">{nav}</nav><div class="audience">{audience}</div></header>'
                f'<main id="main"><nav class="crumbs" aria-label="Breadcrumb">{trail}</nav>{body}</main>'
                f'<footer><p><a href="/about/#sources">Sources</a> · <a href="/about/#licences">Licences</a> · <a href="/about/">Method</a> · '
                f'<a href="{BASE_SIR}">Schools in Reach</a></p></footer></body></html>\n')

    def money_figure(self, key, value, pupils, year, *, label=None, src=None, cmp_similar=None, cmp_england=None,
                     drill=None, signed=False, cls=""):
        attrs = [f'class="mf{" " + esc(cls) if cls else ""}"', f'data-mf="{esc(key)}"', f'data-v="{self._num(value) or ""}"']
        pp = None
        if value is not None and pupils and self._num(value) is not None:
            pp = value / pupils
            attrs.append(f'data-pp="{self._num(round(pp))}"')
        attrs.append(f'data-year="{esc(year)}"')
        for name, v in (("data-label", label), ("data-src", src), ("data-drill", drill)):
            if v:
                attrs.append(f'{name}="{esc(v)}"')
        for name, v in (("data-cmp-similar", cmp_similar), ("data-cmp-england", cmp_england)):
            if v is not None and self._num(v) is not None:
                attrs.append(f'{name}="{self._num(round(v))}"')
        if signed:
            attrs.append('data-signed="1"')
        small = ""
        if pp is not None:
            sign = "-" if pp < 0 else ("+" if signed and pp > 0 else "")
            small = f" <small>{sign}£{abs(round(pp)):,} per pupil</small>"
        return f'<span {" ".join(attrs)}>{esc(money(value, signed))}{small}</span>'

    def pin_button(self, kind, ident, name):
        payload = json.dumps({"type": kind, "id": str(ident), "name": str(name), "p": self.pin_path(kind, ident, name)},
                             ensure_ascii=False, separators=(",", ":"))
        return f'<button type="button" class="pin" data-pin=\'{escape(payload, quote=True)}\'>📌 Pin</button>'

    @staticmethod
    def pin_path(kind, ident, name):
        ident = str(ident)
        if kind == "school":
            return f"/school/{ident}-{slug(name)}/"
        if ident == "england":
            return "/"
        if ident.startswith("council-"):
            return f"/council/{slug(name)}/"
        if ident.startswith("constituency-"):
            return f"/constituency/{ident.removeprefix('constituency-')}/"
        if ident.startswith("region-"):
            return f"/areas/{ident.removeprefix('region-')}/"
        return f"/{slug(name)}/"

    @staticmethod
    def asset_files():
        return []


_fallback_shell = _FallbackShell()


def _shell():
    return shell if shell is not None else _fallback_shell


def mf(key, value, pupils, year, **kw):
    """One £ figure through the shell: total with its per-pupil companion and data-* attributes."""
    return _shell().money_figure(key, value, pupils, year, **kw)


def page(title, description, path, body, crumbs, metadata=None, indexable=True, extra_head=""):
    image = getattr(metadata, "image", None) or None
    return _shell().page(title, description, path, body, crumbs, og_image=image, indexable=indexable, extra_head=extra_head)


def pin(kind, ident, name):
    return _shell().pin_button(kind, ident, name)


# ----------------------------------------------------------------- loading

def load_history(path):
    by_urn = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                by_urn[str(row["urn"])].append(row)
    if not by_urn:
        raise ValueError(f"No finance rows in {path}")
    return by_urn


def load_predecessors(path):
    """GIAS links: rows describe LinkURN's role relative to URN, so 'Predecessor' gives
    the school this URN replaced (an academy conversion). Merges and amalgamations are
    left out: two schools' money would be mixed."""
    pred = defaultdict(list)
    if not path.exists():
        return pred
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            if row.get("LinkType") == "Predecessor":
                pred[row["URN"].strip()].append(row["LinkURN"].strip())
    return pred


def load_dsg(path):
    """pipeline/money/data/la_dsg.json, or an empty shape when the file is missing or unreadable."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        doc = {}
    return {"las": doc.get("las") or {}, "england": doc.get("england") or {},
            "interventions": doc.get("interventions") or {}, "source": doc.get("source")}


def load_ifs(path=ROOT / "pipeline/money/data/ifs_context.json"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def school_rows(urn, by_urn, pred, depth=0, seen=None):
    seen = seen if seen is not None else set()
    seen.add(urn)
    rows = [dict(r) for r in by_urn.get(urn, [])]
    if depth < 3:
        first = min((r["period_end"] for r in rows), default="9999-99")
        for p in pred.get(urn, []):
            if p in seen:
                continue
            for r in school_rows(p, by_urn, pred, depth + 1, seen):
                if r["period_end"] < first:
                    r.setdefault("via_urn", p)
                    rows.append(r)
    return rows


def year_label(row):
    return str(row["year"]).replace("/", "-")


def reserve_of(row):
    value = row.get("revenue_reserve_incl_trust_share")
    return row.get("revenue_reserve") if value is None else value


def full_years(rows):
    """The full-year returns status.assess judges, oldest first, so the year a page reports
    is the year its reserve, share and status come from."""
    return health.full_years(rows)


def per_pupil(row, key):
    value, pupils = (row or {}).get(key), (row or {}).get("pupils")
    return value / pupils if value is not None and pupils else None


def phase_group(row, school):
    phase = (row or {}).get("phase") or ""
    if phase in ("primary", "secondary", "special", "all_through", "nursery", "alternative_provision", "post16"):
        return phase
    return (school.get("phase") or "other").lower()


def pct(value, digits=0):
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def unique_paths(names, prefix):
    """One distinct <prefix><slug>/ per name. Names whose slugs collide, or that slugify to
    nothing, get a short hash of the name so no page overwrites another."""
    by_slug = defaultdict(list)
    for name in names:
        by_slug[slug(name)].append(name)
    paths = {}
    for key, group in by_slug.items():
        for name in group:
            if len(group) > 1 or key == "school" or key.isdigit():
                key_for = f"{key}-{hashlib.sha1(name.encode('utf-8')).hexdigest()[:6]}"
            else:
                key_for = key
            paths[name] = f"{prefix}{key_for}/"
    if len(set(paths.values())) != len(paths):
        raise ValueError(f"Pages under {prefix} would overwrite each other")
    return paths


def trust_paths(names):
    return unique_paths(names, "/trust/")


def real_terms(value, row):
    """value in 2025-26 prices via the deflator, or None when the module or the year is missing."""
    if deflator is None or value is None or not row:
        return None
    try:
        return deflator.to_real(value, year_label(row), row.get("source") or "CFR")
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return None


# ----------------------------------------------------------------- model

def build_model(site, history_path, links_path, pta_path):
    data = site / "data"
    las = json.loads((data / "england/las.json").read_text(encoding="utf-8"))["las"]
    by_urn = load_history(history_path)
    pred = load_predecessors(links_path)
    pta = json.loads(pta_path.read_text(encoding="utf-8")).get("schools", {}) if pta_path and pta_path.exists() else {}
    councils, schools, paths = [], [], {}
    for la in sorted(las, key=lambda c: c["name"]):
        code = str(la["la_code"])
        reg_path = data / "la" / code / "schools.json"
        if not reg_path.exists():
            continue
        council = {"code": code, "name": la["name"], "region": la.get("region"), "schools": [],
                   "path": f"/council/{slug(la['name'])}/", "site_path": f"/council/{slug(la['name'])}/"}
        if any(c["path"] == council["path"] for c in councils):
            raise ValueError(f"Two councils share the page {council['path']}: {la['name']}")
        councils.append(council)
        for s in json.loads(reg_path.read_text(encoding="utf-8")).get("schools", []):
            if closed(s):
                continue
            urn = str(s["urn"])
            if not URN.fullmatch(urn):
                raise ValueError(f"Bad URN {urn!r} in the {la['name']} register")
            rows = school_rows(urn, by_urn, pred)
            if not rows:
                continue
            years = full_years(rows)
            latest = years[-1] if years else None
            own = by_urn.get(urn, [])
            newest = max(own, key=lambda r: r["period_end"]) if own else None
            member = newest if newest and newest.get("did_not_supply") else None
            item = {
                "urn": urn, "name": s["name"], "school": s, "council": council,
                "path": f"/school/{urn}-{slug(s['name'])}/", "site_path": f"/school/{urn}-{slug(s['name'])}/",
                "rows": rows, "years": years, "latest": latest, "member_of": member,
                "status": None if member else health.assess(rows),
                "phase": phase_group(latest, s), "london": int(code) in LONDON if code.isdigit() else False,
                "fsm": s.get("fsm_pct") if s.get("fsm_pct") is not None else (latest or {}).get("fsm_pct"),
                "pta": [c for c in pta.get(urn, []) if not c.get("review")],
                "trust": (s.get("trust") or (latest or {}).get("trust") or "").strip() or None,
                "academy": (latest or {}).get("source") == "AAR",
                "constituency": (s.get("constituency") or "").strip() or None,
            }
            if urn in paths:
                raise ValueError(f"URN {urn} appears in two registers: {paths[urn]['name']} and {council['name']}")
            paths[urn] = council
            council["schools"].append(item)
            schools.append(item)
    by_laestab = {}
    for item in schools:
        for r in item["rows"]:
            if r.get("laestab") and not r.get("did_not_supply") and str(r.get("urn")) == item["urn"]:
                by_laestab[str(r["laestab"])] = item
    for item in schools:
        if item["member_of"]:
            item["lead"] = by_laestab.get(str(item["member_of"].get("lead_laestab")))
    trust_path = trust_paths(trusts_of(schools))
    for item in schools:
        item["trust_path"] = trust_path.get(item["trust"])
    constituency_path = unique_paths({i["constituency"] for i in schools if i["constituency"]}, "/constituency/")
    for item in schools:
        item["constituency_path"] = constituency_path.get(item["constituency"])
    add_similar(schools)
    return councils, schools, by_urn


def add_similar(schools):
    """Up to 30 nearest schools of the same phase, London or not, by size and free-school-meals share.
    Schools are bucketed on a grid of (log pupils, FSM band) and searched ring by ring, so each
    lookup touches a few dozen schools rather than all of them."""
    groups, coords = defaultdict(list), {}
    for s in schools:
        s["similar"] = []
        if s["status"] and s["latest"] and s["latest"].get("pupils"):
            groups[(s["phase"], s["london"])].append(s)
            coords[s["urn"]] = (math.log(s["latest"]["pupils"]) / 0.1, (s["fsm"] if s["fsm"] is not None else 25.0) / 2.5)
    for members in groups.values():
        grid = defaultdict(list)
        for s in members:
            x, y = coords[s["urn"]]
            grid[(int(x), int(y))].append(s)
        for s in members:
            x, y = coords[s["urn"]]
            cx, cy = int(x), int(y)
            found, r, extra = [], 0, None
            while r <= 40:
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        if max(abs(dx), abs(dy)) == r:
                            found.extend(grid.get((cx + dx, cy + dy), ()))
                if extra is None and len(found) > SIMILAR_N:
                    extra = r + 2  # a couple more rings so the nearest are really in
                if extra is not None and r >= extra:
                    break
                r += 1
            found = [o for o in found if o is not s]
            found.sort(key=lambda o: abs(coords[o["urn"]][0] - x) + abs(coords[o["urn"]][1] - y))
            s["similar"] = found[:SIMILAR_N]


def compare_rows(s):
    out = []
    for key, label in COMPARE_KEYS:
        mine = per_pupil(s["latest"], key)
        others = sorted(v for v in (per_pupil(o["latest"], key) for o in s["similar"]) if v is not None)
        if mine is None or len(others) < 10:
            continue
        q = statistics.quantiles(others, n=4)
        out.append({"key": key, "label": label, "value": mine, "p25": q[0], "median": q[1], "p75": q[2]})
    return out


def similar_medians(item):
    """Median £ per pupil among similar schools for each compared line, when 10 or more have it."""
    sim = {}
    for k, _ in COMPARE_KEYS + [("total_expenditure", ""), ("total_income", "")]:
        vals = [v for v in (per_pupil(o["latest"], k) for o in item["similar"]) if v is not None]
        if len(vals) >= 10:
            sim[k] = statistics.median(vals)
    return sim


def reserve_rank(s):
    mine = s["status"]["reserve_share"]
    others = [health.reserve_share(o["latest"]) for o in s["similar"]]
    others = [v for v in others if v is not None]
    if mine is None or len(others) < 10:
        return None
    return sum(v < mine for v in others) / len(others)


def deficit_history(item):
    return [r for r in item["years"] if (reserve_of(r) or 0) < 0]


def recovered(item):
    """Was in deficit at some point in the window, and is now healthy or better."""
    st = item["status"]
    return bool(st and st["status"] in ("healthy", "large_reserves") and deficit_history(item))


def latest_year(items):
    """Display year for a total over several schools: the newest of their assessed years."""
    labels = [year_label(i["latest"]) for i in items if i.get("latest")]
    return max(labels) if labels else ""


def pupils_of(items):
    total = sum((i["latest"] or {}).get("pupils") or 0 for i in items)
    return total or None


def pupils_by_year(items):
    """Pupils on roll per display year across these schools' full-year returns. A school with no
    return for a year counts its previous year's roll, so the latest CFR year (published before
    that year's academy accounts) still divides a council-wide figure by all its pupils."""
    per_school = []
    for i in items:
        own = {year_label(r): r["pupils"] for r in i["years"] if r.get("pupils")}
        if own:
            per_school.append(own)
    years = sorted({y for own in per_school for y in own})
    totals = Counter()
    for n, y in enumerate(years):
        previous = years[n - 1] if n else None
        for own in per_school:
            value = own.get(y)
            if value is None and previous is not None:
                value = own.get(previous)
            if value:
                totals[y] += value
    return totals


def dsg_for(dsg, code):
    return (dsg.get("las") or {}).get(str(code)) or {}


def dsg_flags(dsg, code):
    flags = []
    inter = dsg.get("interventions") or {}
    if str(code) in {str(c) for c in inter.get("safety_valve", [])}:
        flags.append("safety valve")
    if str(code) in {str(c) for c in inter.get("delivering_better_value", [])}:
        flags.append("delivering better value")
    return flags


# ----------------------------------------------------------------- pieces

def tiles(pairs):
    return '<div class="tiles">' + "".join(f'<div class="tile"><div class="tlabel">{esc(k)}</div><div class="tvalue">{v}</div></div>' for k, v in pairs) + "</div>"


def details_table(summary, headers, rows):
    return f'<details class="tableview"><summary>{esc(summary)}</summary>{table(headers, rows)}</details>'


def sortable(headers, rows, css=""):
    html = table(headers, rows, css=f"sortable {css}".strip())
    return html.replace('<table class="responsive', '<table data-sortable class="responsive', 1)


def status_cell(item):
    return badge(item["status"]["status"], "small") if item.get("status") else '<span class="muted">No full-year return</span>'


def school_link(item):
    return f'<a href="{esc(item["path"])}" data-preview="school:{esc(item["urn"])}">{esc(item["name"])}</a>'


def council_link(council):
    return f'<a href="{esc(council["path"])}" data-preview="area:council-{esc(council["code"])}">{esc(council["name"])}</a>'


def fbit_school(item):
    return f"{FBIT}/school/{item['urn']}"


def sources(extra="", compact=False):
    if compact:
        return (f'<section class="sources"><p class="muted small">Sources: <a href="{FBIT_SOURCES}">DfE Financial Benchmarking and Insights Tool</a> (CFR and academy accounts returns) '
                f'and <a href="https://get-information-schools.service.gov.uk/">Get Information about Schools</a>{extra}, Open Government Licence v3.0. '
                f'<a href="/about/">How these figures are worked out</a> · <a href="/">School Money home</a> · <a href="{BASE_SIR}/">Schools in Reach</a></p></section>')
    return ('<section class="sources"><h2>Sources and how to check</h2><ul>'
            f'<li><a href="{FBIT_SOURCES}">DfE Financial Benchmarking and Insights Tool data</a>: CFR returns for council-run schools (April–March) '
            'and Academy Accounts Returns (September–August) — Open Government Licence v3.0</li>'
            '<li><a href="https://get-information-schools.service.gov.uk/">Get Information about Schools</a> (school register and academy conversions) — Open Government Licence v3.0</li>'
            f'{extra}</ul><p><a href="/about/">How these figures are worked out</a> · <a href="/">School Money home</a> · '
            f'<a href="{BASE_SIR}/">Schools in Reach: admissions and catchments</a></p></section>')


def drill_script(ident, title, year, rows, series, src):
    """Inline drill-down JSON for app.js (SHARED drill shape) and the attribute value pointing at it."""
    payload = {"title": title, "year": year,
               "rows": [{"key": k, "label": l, "v": round(v), "pp": round(p) if p is not None else None} for k, l, v, p in rows],
               "series": [{"y": y, "v": round(v), "pp": round(p) if p is not None else None} for y, v, p in series], "src": src}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    return f'<script type="application/json" id="{esc(ident)}">{text}</script>', f"#{ident}"


def reason_html(item):
    """The status reason with its £ figure rendered as a money figure (the prose is status.py's)."""
    st, latest = item["status"], item["latest"]
    text = esc(st["reason"])
    m = re.search(r"-?£[0-9][0-9.,]*(?:bn|m|k)?", text)
    if not m:
        return text
    if st["status"] == "in_deficit":
        figure = mf("deficit_total", -st["reserve"], latest.get("pupils"), year_label(latest), label="Deficit", src=fbit_school(item))
    else:
        figure = mf("revenue_reserve", st["reserve"], latest.get("pupils"), year_label(latest), src=fbit_school(item))
    return text[:m.start()] + figure + text[m.end():]


def questions(item, cmp):
    st, q = item["status"], []
    kind = st["status"]
    academy = item["academy"]
    latest = item["latest"]
    who = "its trust" if academy else "the council"
    if kind == "in_deficit":
        q.append(f"Is there a deficit recovery plan agreed with {who}, and when does the school expect to be back in balance?")
        q.append("What has been cut or changed to close the gap, and how does that affect classes and support staff?")
    elif kind == "heading_for_deficit":
        q.append("What is the plan to stop spending more than the school receives each year?")
    elif kind == "tight":
        q.append("What would the school do if costs rose unexpectedly, such as energy or a pay award that isn't fully funded?")
    elif kind == "large_reserves":
        q.append("What are the reserves set aside for, and when will they be spent on current pupils?")
        if not academy:
            q.append("Could any of the surplus be clawed back under the council's scheme for financing schools?")
    change = st.get("pupils_change")
    if change is not None and change <= -0.08:
        first = next(r for r in item["years"] if r.get("pupils"))
        q.append(f"Pupil numbers have fallen {abs(change):.0%} since {year_label(first)}. How is the school planning for fewer pupils, and the funding that goes with them?")
    q = [esc(x) for x in q]
    for r in sorted(cmp, key=lambda r: -(r["value"] / r["median"] if r["median"] else 0)):
        if r["value"] > r["p75"] * 1.1 and len(q) < 6:
            figure = mf(r["key"], latest.get(r["key"]), latest.get("pupils"), year_label(latest), cmp_similar=r["median"])
            q.append(f"Spending on {esc(r['label'].lower())} is {figure}, more per pupil than three-quarters of similar schools. What's behind that?")
    if item["pta"]:
        q.append(esc("How does the school decide what the money the parents' association raises is spent on?"))
    return q[:6]


def profile_of(item, data_root):
    """areas.school_profile for this school, or None when the module is absent or fails."""
    if areas is None:
        return None
    try:
        return areas.school_profile(item["school"], item["council"]["code"], data_root)
    except Exception:  # a2's module reads optional files; a page must never fail on context
        return None


def timeline_of(item):
    if timeline is None or not item["status"]:
        return None
    try:
        return timeline.status_by_year(item["rows"])
    except Exception:
        return None


def tags_line(profile):
    """One line of plain tags from areas.school_profile, neutral wording."""
    if not profile:
        return ""
    t = profile.get("tags") or {}
    parts = [t.get("governance"), t.get("phase"), t.get("gender")]
    if t.get("trust"):
        parts.append(f'{t["trust"]} ({"multi-academy" if t.get("trust_size") == "multi" else "single-academy"} trust)')
    for key in ("admissions", "faith"):
        if t.get(key):
            parts.append(t[key])
    if t.get("sixth_form"):
        parts.append("sixth form")
    intake = profile.get("intake") or {}
    if intake.get("fsm_pct") is not None:
        parts.append(f"{intake['fsm_pct']:.0f}% of pupils eligible for free school meals")
    band = profile.get("band")
    html = '<p class="tags">' + " · ".join(esc(p) for p in parts if p) + "</p>"
    if band:
        html += (f'<p class="muted small">Intake band <span class="mf-band" data-mf="band">{int(band)} of 5</span> nationally, '
                 'combining free-school-meal eligibility and the deprivation of the school\'s neighbourhood (1 = least disadvantaged, 5 = most).</p>')
    return html


# ----------------------------------------------------------------- pages

def render_school(item, metadata, data_root=None):
    s, st = item["school"], item["status"]
    council = item["council"]
    crumbs = [("School Money", "/"), (council["name"], council["path"]), (item["name"], item["path"])]
    src = fbit_school(item)
    check = f'<a href="{esc(src)}">DfE benchmarking page for this school</a>'
    if item.get("member_of"):
        lead = item.get("lead")
        lead_html = school_link(lead) if lead else "the lead school"
        body = (f'<h1>{esc(item["name"])}: school finances</h1><p class="lead">This school is part of a federation. Its money is reported '
                f'in one combined return made by {lead_html}, so its figures and status are shown on that school\'s page.</p>'
                f'<p>Check at source: {check}.</p>' + sources())
        return page(shorten(f"{item['name']} finances | School Money", 70),
                    shorten(f"{item['name']} reports its finances jointly with its federation. See the federation's combined figures.", 160),
                    item["path"], body, crumbs, metadata, indexable=False)
    if not st:
        body = (f'<h1>{esc(item["name"])}: school finances</h1><p class="lead">No full-year finance return is published for this school yet, '
                f'usually because it opened, converted to an academy or changed trust part-way through the year.</p><p>Check at source: {check}.</p>' + sources())
        return page(shorten(f"{item['name']} finances | School Money", 70), shorten(f"Finance returns for {item['name']}.", 160),
                    item["path"], body, crumbs, metadata, indexable=False)
    latest, years = item["latest"], item["years"]
    pupils, year = latest.get("pupils"), year_label(latest)
    points = [{"year": year_label(r), "income": r.get("total_income"), "spend": r.get("total_expenditure"),
               "reserve": reserve_of(r), "pupils": r.get("pupils"), "balance": r.get("in_year_balance"), "row": r} for r in years]
    span = f"{points[0]['year']} to {points[-1]['year']}" if len(points) > 1 else points[0]["year"]
    kind = "academy (accounts return, September–August)" if item["academy"] else "council-run school (CFR return, April–March)"
    sim = similar_medians(item)
    profile = profile_of(item, data_root) if data_root else None
    body = f'<h1>{esc(item["name"])}: school finances</h1>'
    body += f'<p class="status-line">{badge(st["status"], "large")} {pin("school", item["urn"], item["name"])}</p><p class="lead">{reason_html(item)}</p>'
    body += (f'<p class="muted small">Latest full year {esc(year)}, as a {kind}. '
             f'{council_link(council)} · {esc(s.get("phase") or "")} · {esc(s.get("type") or "")}.</p>')
    body += tags_line(profile)
    change = st.get("pupils_change")
    income_rows = [(g, label, latest[k], per_pupil(latest, k)) for k, g, label in INCOME_LINES if latest.get(k) is not None]
    spend_rows = [(k, label, latest[k], per_pupil(latest, k)) for k, label in COMPARE_KEYS if latest.get(k) is not None]
    income_script, income_drill = drill_script("drill-income", "Income by source", year, income_rows,
                                               [(p["year"], p["income"], per_pupil(p["row"], "total_income")) for p in points if p["income"] is not None], src)
    spend_script, spend_drill = drill_script("drill-spend", "Spending by line", year, spend_rows,
                                             [(p["year"], p["spend"], per_pupil(p["row"], "total_expenditure")) for p in points if p["spend"] is not None], src)
    reserve_key = "revenue_reserve_incl_trust_share" if st["trust_share_included"] else "revenue_reserve"
    reserve_tile = mf(reserve_key, st["reserve"], pupils, year, src=src) + f'<span class="sub">{pct(st["reserve_share"])} of a year\'s income</span>'
    real = real_terms(st["reserve"], latest)
    if real is not None and deflator is not None:
        reserve_tile += f'<span class="sub">{mf("real_terms", real, pupils, year, label="Reserve in 2025-26 prices")} {esc(deflator.real_label())}</span>'
    body += tiles([
        ("Reserve at year end", reserve_tile),
        ("Last year's balance", mf("in_year_balance", latest.get("in_year_balance"), pupils, year, src=src, signed=True) + '<span class="sub">income minus spending</span>'),
        ("Income", mf("total_income", latest.get("total_income"), pupils, year, src=src, cmp_similar=sim.get("total_income"), drill=income_drill)),
        ("Spending", mf("total_expenditure", latest.get("total_expenditure"), pupils, year, src=src, cmp_similar=sim.get("total_expenditure"), drill=spend_drill)),
        ("Pupils", f'{pupils or 0:,.0f}' + (f'<span class="sub">{change:+.0%} since {esc(points[0]["year"])}</span>' if change is not None else "")),
    ]) + income_script + spend_script
    if item["academy"]:
        trust = item["trust"]
        trust_html = f'<a href="{esc(item["trust_path"])}">{esc(trust)}</a>' if trust and item.get("trust_path") else "its academy trust"
        body += (f'<p class="note">Academies in a trust don\'t hold money on their own: {trust_html} can move money between its schools. '
                 + ("The reserve includes this school's per-pupil share of the trust's central reserve." if st["trust_share_included"] else
                    "The DfE doesn't publish this school's share of the trust's central reserve for this year, so the reserve shown is the school's own.")
                 + "</p>")
    if any(r.get("via_urn") for r in years):
        body += '<p class="note">Earlier years come from this school\'s return before it became an academy (a different DfE number).</p>'
    newer = [r for r in item["rows"] if r["period_end"] > latest["period_end"] and not r.get("did_not_supply")]
    if newer:
        body += (f'<p class="note">A {esc(year_label(max(newer, key=lambda r: r["period_end"])))} return is published too, but it covers part of a year '
                 'or leaves out the income or reserve figure, so the latest complete year is shown.</p>')
    line = timeline_of(item)
    if line:
        body += '<p class="timeline">Status by year: ' + " ".join(f'<span class="tl">{esc(t["year"])} {badge(t["status"], "small")}</span>' for t in line) + "</p>"
    body += f'<h2>Reserve at the end of each year, {esc(span)}</h2>' + charts.reserve_bars(points)
    body += f'<h2>Income and spending, {esc(span)}</h2>' + charts.income_spend_lines(points)
    body += details_table("Show the figures as a table", ["Year", "Income", "Spending", "Reserve", "Pupils"],
                          [[esc(p["year"]), mf("total_income", p["income"], p["pupils"], p["year"]), mf("total_expenditure", p["spend"], p["pupils"], p["year"]),
                            mf("revenue_reserve", p["reserve"], p["pupils"], p["year"]), f'{p["pupils"]:,.0f}' if p["pupils"] else "—"] for p in points])
    cmp = compare_rows(item)
    if cmp:
        rank = reserve_rank(item)
        body += '<h2>Compared with similar schools</h2>'
        body += (f'<p>Similar schools are the {len(item["similar"])} {esc(item["phase"].replace("_", "-"))} schools '
                 f'{"in London" if item["london"] else "outside London"} closest in size and in the share of pupils on free school meals. ')
        if rank is not None:
            body += f'Its reserve, as a share of income, is higher than {rank:.0%} of them. '
        if sim.get("total_expenditure"):
            body += (f'It spends {mf("total_expenditure", latest.get("total_expenditure"), pupils, year, cmp_similar=sim["total_expenditure"], src=src)} in total; '
                     f'similar schools typically spend {mf("per_pupil", sim["total_expenditure"], None, year, label="Similar schools: median spending per pupil")} per pupil.')
        body += "</p>" + charts.compare_dots(cmp)
        body += details_table("Show the comparison as a table", ["Spending", "This school", "Similar schools (median per pupil)"],
                              [[esc(r["label"]), mf(r["key"], latest.get(r["key"]), pupils, year, cmp_similar=r["median"]),
                                mf("per_pupil", r["median"], None, year)] for r in cmp])
        near = ",".join([item["urn"]] + [o["urn"] for o in item["similar"][:3]])
        body += (f'<p><a class="button" href="/compare/?urns={esc(near)}">Compare side by side with the 3 most similar schools</a></p>'
                 '<details class="tableview"><summary>Which schools are these?</summary><ul class="nearby">'
                 + "".join(f'<li>{school_link(o)} {status_cell(o)}</li>' for o in item["similar"][:6]) + "</ul></details>")
    income = [(g, label, latest[k]) for k, g, label in INCOME_LINES if latest.get(k)]
    if income:
        body += f'<h2 id="income">Where the money comes from, {esc(year)}</h2>' + table(
            ["Source", "Amount"], [[esc(label), mf(g, v, pupils, year)] for g, label, v in income])
    if item["pta"]:
        body += "<h2>Money raised by parents</h2>"
        for n, c in enumerate(item["pta"][:2]):
            hist = [h for h in c.get("history", []) if h.get("income") is not None][-3:] if n == 0 else []
            body += (f'<p><a href="{CHARITY}{esc(c["charity_number"])}">{esc(c["name"])}</a> (charity {esc(c["charity_number"])}, {esc(c.get("status") or "")}) '
                     + (f'raised {mf("pta_income", c.get("latest_income"), pupils, year)} in its latest year.'
                        if c.get("latest_income") is not None else "") + "</p>")
            if hist:
                body += table(["Year ending", "Income", "Spending"],
                              [[esc(h["period_end"]), mf("pta_income", h["income"], pupils, h["period_end"]), mf("pta_spending", h.get("expenditure"), pupils, h["period_end"])] for h in hist])
        body += '<p class="muted small">Matched to this school from the Charity Commission register. Parent associations\' money isn\'t in the school\'s accounts above; per-pupil figures use the school\'s latest roll.</p>'
    qs = questions(item, cmp)
    if qs:
        body += "<h2>Questions to ask the school</h2><p>Useful for parents, governors and PTA committees.</p><ul>" + "".join(f"<li>{q}</li>" for q in qs) + "</ul>"
    body += (f'<h2>Check these figures</h2><p>Every figure here comes from the school\'s published return to the DfE. Check it on the {check}, '
             f'and see <a href="/about/">how the status is worked out</a>.</p>'
             f'<p><a href="{BASE_SIR}{esc(item["site_path"])}">Admissions, Ofsted and results for {esc(item["name"])}</a> · '
             f'<a href="{esc(council["path"])}">All {esc(council["name"])} school finances</a>'
             + (f' · <a href="{esc(item["constituency_path"])}">Schools in {esc(item["constituency"])}</a>' if item.get("constituency_path") else "") + "</p>")
    pta_source = ' and the <a href="https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download">Charity Commission register</a>' if item["pta"] else ""
    body += sources(pta_source, compact=True)
    title = shorten(f"{item['name']} finances: {st['label']} | School Money", 70)
    description = shorten(f"{item['name']}: {st['reason']} Income, spending and reserves {span}, compared with similar schools.", 160)
    return page(title, description, item["path"], body, crumbs, metadata)


def chunk_rows(rows, budget=TABLE_BUDGET):
    """Split table rows into pages whose rows weigh at most `budget` bytes, so a council or
    trust with hundreds of schools never pushes one page past PAGE_BUDGET."""
    pages, current, size = [], [], 0
    for cells in rows:
        weight = sum(len(c.encode("utf-8")) for c in cells) + 60 * len(cells)
        if current and size + weight > budget:
            pages.append(current)
            current, size = [], 0
        current.append(cells)
        size += weight
    pages.append(current)
    return pages


def page_path(path, n):
    return path if n == 1 else f"{path}{n}/"


def pager(path, n, total):
    if total < 2:
        return ""
    parts = [f'<a href="{esc(page_path(path, n - 1))}" rel="prev">Previous page</a>'] if n > 1 else []
    parts.append(f"Page {n} of {total}")
    if n < total:
        parts.append(f'<a href="{esc(page_path(path, n + 1))}" rel="next">Next page</a>')
    return '<nav class="pager" aria-label="Pages">' + " · ".join(parts) + "</nav>"


def paged(path, headers, rows, frame, metadata):
    """One sortable table over as many pages as its rows need: [(path, html)]. frame(n, total,
    table_html) returns (title, description, crumbs, body) with the table placed in the body."""
    chunks = chunk_rows(rows)
    out = []
    for n, chunk in enumerate(chunks, 1):
        where = page_path(path, n)
        table_html = sortable(headers, chunk) + pager(path, n, len(chunks)) if chunk else ""
        title, description, crumbs, body = frame(n, len(chunks), table_html)
        if n > 1:
            crumbs = crumbs + [(f"Page {n}", where)]
        out.append((where, page(title, description, where, body, crumbs, metadata)))
    return out


def sort_note(total):
    return '<p class="muted small">Tap a column heading to sort' + (" this page" if total > 1 else "") + ".</p>"


def council_rows(items):
    rows = []
    for i in sorted(items, key=lambda i: (i["status"]["rank"], i["status"]["reserve"])):
        st, latest = i["status"], i["latest"]
        change = "—" if st["pupils_change"] is None else f'{st["pupils_change"]:+.0%}'
        rows.append([school_link(i), status_cell(i),
                     f'<span data-sort="{st["reserve"]:.0f}">{mf("revenue_reserve", st["reserve"], latest.get("pupils"), year_label(latest))}</span>',
                     f'<span data-sort="{(st["reserve_share"] or 0):.4f}">{pct(st["reserve_share"])}</span>',
                     f'<span data-sort="{st["deficit_streak"]}">{st["deficit_streak"] or "—"}</span>',
                     f'<span data-sort="{(st["pupils_change"] or 0):.3f}">{change}</span>'])
    return rows


COUNCIL_HEADERS = ["School", "Status", "Reserve", "% of income", "Years overspending", "Pupils since first year"]


def yearly_deficit_series(rows_by_school, source="CFR"):
    counts, totals = Counter(), Counter()
    for rows in rows_by_school:
        for r in full_years(rows):
            if r["source"] != source or r.get("revenue_reserve") is None:
                continue
            label = year_label(r)
            totals[label] += 1
            counts[label] += r["revenue_reserve"] < 0
    return [(label, counts[label], totals[label]) for label in sorted(totals)]


def dsg_section(name, values, pupils, flags=(), code=None, heading=None):
    """A council's (or England's) dedicated schools grant balance by year, total and per pupil of
    that year's schools on the site. Negative is a deficit (cash terms)."""
    years = sorted(y for y, v in (values or {}).items() if v is not None)
    if not years:
        return ""
    latest = years[-1]
    heading = heading or name + " council's schools budget balance"
    body = f'<h2 id="dsg">{esc(heading)}</h2>'
    body += (f'<p>The dedicated schools grant (DSG) is the money {"councils receive" if code is None else "the council receives"} for schools and high-needs '
             f'(special educational needs) provision. At the end of {esc(latest)} the cumulative balance was '
             f'{mf("dsg_balance", values[latest], pupils.get(latest), latest, signed=True)}'
             + (f' ({", ".join(flags)} programme with the DfE)' if flags else "") + ". A negative figure is a deficit carried forward.</p>")
    rows = [[esc(y), mf("dsg_balance", values[y], pupils.get(y), y, signed=True)] for y in reversed(years[-DSG_YEARS:])]
    body += details_table("DSG balance by year", ["Year", "Balance (per pupil of that year's schools)"], rows)
    body += ('<p class="muted small">Per-pupil figures divide by the pupils on roll that year at the schools on this site; a school whose '
             'return for the year is not yet published counts its previous year\'s roll.</p>')
    if flags:
        body += ('<p class="muted small">Safety valve and delivering better value are DfE programmes for councils with large high-needs deficits: '
                 'the council agrees a plan to bring its schools budget back into balance over several years.</p>')
    return body


def render_council(council, metadata, dsg=None):
    """The council's pages as [(path, html)]: the first carries the summary and charts; the
    school table continues on /2/, /3/… when it would push a page past the size budget."""
    items = [i for i in council["schools"] if i["status"]]
    counts = Counter(i["status"]["status"] for i in items)
    deficit = [i for i in items if i["status"]["status"] == "in_deficit"]
    owed = -sum(i["status"]["reserve"] for i in deficit)
    rest = [i for i in items if i["status"]["reserve"] > 0]
    held = sum(i["status"]["reserve"] for i in rest)
    name, year = council["name"], latest_year(items)
    crumbs = [("School Money", "/"), ("Councils", "/council/"), (name, council["path"])]
    check = (f'<p>Check at source: <a href="{FBIT}/local-authority/{esc(council["code"])}">DfE benchmarking page for {esc(name)}</a> · '
             f'<a href="{BASE_SIR}{esc(council["site_path"])}">{esc(name)} admissions and catchments</a></p>' + sources())
    title = shorten(f"{name} school finances: {len(deficit)} schools in deficit | School Money", 70)
    description = shorten(f"{len(deficit)} of {len(items)} schools in {name} are in deficit ({money(owed)} combined). See every school's reserves, spending and trend from DfE returns.", 160)
    dsg = dsg or {}

    def frame(n, total, table_html):
        body = f'<h1>{esc(name)} school finances</h1>'
        if n > 1:
            body += (f'<p class="lead">Every school in {esc(name)} with a full-year return, worst first: page {n} of {total}. '
                     f'<a href="{esc(council["path"])}">Back to the summary</a>.</p>' + sort_note(total) + table_html + check)
            return (shorten(f"{name} school finances, page {n} | School Money", 70),
                    shorten(f"Page {n} of {total}: every school in {name} with a full-year finance return, worst first, from DfE returns.", 160), crumbs, body)
        body += f'<p class="status-line">{pin("area", "council-" + council["code"], name)}</p>'
        if items:
            body += (f'<p class="lead"><strong>{len(deficit):,} of {len(items):,}</strong> schools in {esc(name)} were in deficit in their latest return, '
                     f'with combined deficits of <strong>{mf("deficit_total", owed, pupils_of(deficit), year)}</strong>. {counts["heading_for_deficit"]:,} more are heading that way.</p>')
        else:
            body += f'<p class="lead">No school in {esc(name)} has a full-year finance return in the latest data, so there are no statuses to show yet.</p>'
        body += charts.status_bar(counts)
        body += tiles([("Schools in deficit", f"{len(deficit):,}"), ("Combined deficits", mf("deficit_total", owed, pupils_of(deficit), year)),
                       ("Heading for deficit", f'{counts["heading_for_deficit"]:,}'), ("Reserves held by the rest", mf("revenue_reserve", held, pupils_of(rest), year))])
        series = yearly_deficit_series([i["rows"] for i in council["schools"]])
        if len(series) > 1:
            body += f'<h2>Share of {esc(name)}\'s council-run schools in deficit, by year</h2>' + charts.count_bars(series)
            body += '<p class="muted small">Council-run schools only, so years compare like with like; academies report differently and are in the table below.</p>'
        body += dsg_section(name, dsg_for(dsg, council["code"]).get("values"), pupils_by_year(council["schools"]), dsg_flags(dsg, council["code"]), code=council["code"])
        back = sorted((i for i in items if recovered(i)), key=lambda i: i["name"])
        if back:
            body += ("<h2>Back in the black</h2><p>Schools that were in deficit in an earlier year and are now healthy:</p><ul class=\"nearby\">"
                     + "".join(f"<li>{school_link(i)}</li>" for i in back[:TOP_N]) + "</ul>"
                     + (f'<p class="muted small">And {len(back) - TOP_N:,} more, in the table below.</p>' if len(back) > TOP_N else ""))
        if table_html:
            body += "<h2>Every school, worst first</h2>" + sort_note(total) + table_html
        members = [i for i in council["schools"] if not i["status"]]
        if members:
            body += ('<p class="muted small">Not shown: ' + ", ".join(school_link(i) for i in members[:TOP_N])
                     + (f" and {len(members) - TOP_N:,} others" if len(members) > TOP_N else "") + ' (in a federation\'s combined return, or no full-year return yet).</p>')
        return title, description, crumbs, body + check

    return paged(council["path"], COUNCIL_HEADERS, council_rows(items), frame, metadata)


def council_summary(council):
    """(assessed schools, in deficit, heading for deficit, combined deficits) for one council."""
    cs = [i for i in council["schools"] if i["status"]]
    d = [i for i in cs if i["status"]["status"] == "in_deficit"]
    h = sum(i["status"]["status"] == "heading_for_deficit" for i in cs)
    return cs, d, h, -sum(i["status"]["reserve"] for i in d)


def council_cells(council):
    cs, d, h, total = council_summary(council)
    return [council_link(council), f'<span data-sort="{len(cs)}">{len(cs):,}</span>',
            f'<span data-sort="{len(d)}">{len(d):,}</span>', f'<span data-sort="{len(d) / len(cs):.4f}">{len(d) / len(cs):.0%}</span>',
            f'<span data-sort="{h}">{h:,}</span>', f'<span data-sort="{total:.0f}">{mf("deficit_total", total, pupils_of(d), latest_year(cs))}</span>']


COUNCIL_INDEX_HEADERS = ["Council", "Schools", "In deficit", "% in deficit", "Heading for deficit", "Combined deficits"]


def render_council_index(councils, metadata):
    """Every council with an assessed school, as [(path, html)] over as many pages as needed."""
    rows = [council_cells(c) for c in councils if any(i["status"] for i in c["schools"])]
    crumbs = [("School Money", "/"), ("Councils", "/council/")]

    def frame(n, total, table_html):
        body = ('<h1>School finances by council</h1><p class="lead">Every council in England with how many of its schools are in deficit, '
                'heading that way, and what the deficits add up to.</p>' + (sort_note(total) + table_html if table_html else
                '<p>No council has a school with a full-year finance return in the latest data yet.</p>') + sources())
        suffix = f", page {n}" if n > 1 else ""
        return (shorten(f"School finances by council{suffix} | School Money", 70),
                shorten(f"Councils in England{suffix}: how many schools are in deficit, heading for deficit, and their combined deficits from DfE returns.", 160), crumbs, body)

    return paged("/council/", COUNCIL_INDEX_HEADERS, rows, frame, metadata)


def ranked(items, headers, cells):
    return table(["#"] + headers, [[str(n)] + cells(i) for n, i in enumerate(items, 1)])


def reserve_cell(i):
    return mf("revenue_reserve", i["status"]["reserve"], i["latest"].get("pupils"), year_label(i["latest"]))


def render_national(councils, schools, metadata, dsg=None):
    items = [i for i in schools if i["status"]]
    counts = Counter(i["status"]["status"] for i in items)
    deficit = sorted((i for i in items if i["status"]["status"] == "in_deficit"), key=lambda i: i["status"]["reserve"])
    heading = sorted((i for i in items if i["status"]["status"] == "heading_for_deficit"), key=lambda i: i["status"]["runway_years"] or 99)
    large = sorted((i for i in items if i["status"]["status"] == "large_reserves"), key=lambda i: -(i["status"]["reserve_share"] or 0))
    back = sorted((i for i in items if recovered(i)), key=lambda i: -(i["status"]["reserve_share"] or 0))
    owed = -sum(i["status"]["reserve"] for i in deficit)
    year = latest_year(items)
    body = '<h1>School money: which schools are in deficit, and which are doing well</h1>'
    if items:
        body += (f'<p class="lead">Of {len(items):,} state schools in England with a full-year return, <strong>{len(deficit):,} were in deficit</strong> '
                 f'({len(deficit) / len(items):.0%}), owing a combined <strong>{mf("deficit_total", owed, pupils_of(deficit), year)}</strong>. Another {counts["heading_for_deficit"]:,} are '
                 'heading that way: they have spent more than they received for two years or more and their reserves are running out.</p>')
    else:
        body += '<p class="lead">No school has a full-year finance return in the latest data yet, so there are no statuses to show.</p>'
    body += ('<form class="finder" action="/compare/" role="search"><label for="find">Find a school</label>'
             '<input id="find" name="q" type="search" placeholder="School name or town" autocomplete="off"><button type="submit">Find</button></form>')
    body += charts.status_bar(counts)
    body += '<p class="muted small">Latest returns: council-run schools 2025-26 (April–March), academies 2024-25 (September–August). <a href="/about/">How each status is worked out</a>.</p>'
    series = yearly_deficit_series([i["rows"] for i in schools])
    if len(series) > 1:
        body += "<h2>Share of council-run schools in deficit, by year</h2>" + charts.count_bars(series)
    body += "<h2>Biggest deficits</h2>" + ranked(deficit[:TOP_N], ["School", "Council", "Reserve", "% of income"], lambda i: [
        school_link(i), council_link(i["council"]), reserve_cell(i), pct(-(i["status"]["reserve_share"] or 0))])
    body += "<h2>Heading for deficit soonest</h2><p>Spending more than they receive, with reserves that would run out within about three years at the current rate.</p>" + ranked(
        heading[:TOP_N], ["School", "Council", "Reserve", "Runs out in about"], lambda i: [
            school_link(i), council_link(i["council"]), reserve_cell(i), f'{max(i["status"]["runway_years"], 0.5):.0f} year(s)'])
    if back:
        body += "<h2>Back in the black</h2><p>Schools that were in deficit earlier in the period and now have healthy reserves.</p>" + ranked(
            back[:TOP_N - 4], ["School", "Council", "Reserve now", "% of income"], lambda i: [
                school_link(i), council_link(i["council"]), reserve_cell(i), pct(i["status"]["reserve_share"])])
    body += "<h2>Largest reserves for their size</h2><p>A big reserve is a cushion, but it is also money not yet spent on current pupils.</p>" + ranked(
        large[:TOP_N - 4], ["School", "Council", "Reserve", "% of income"], lambda i: [
            school_link(i), council_link(i["council"]), reserve_cell(i), pct(i["status"]["reserve_share"])])
    busiest = sorted((c for c in councils if any(i["status"] for i in c["schools"])), key=lambda c: -len(council_summary(c)[1]))[:TOP_N]
    if busiest:
        body += ("<h2>Councils with the most schools in deficit</h2>" + ranked(busiest, COUNCIL_INDEX_HEADERS, council_cells)
                 + '<p><a class="button" href="/council/">Every council</a></p>')
    if dsg and dsg.get("england"):
        body += dsg_section("England", dsg["england"], pupils_by_year(schools), heading="Councils' schools budget balances across England")
    body += '<p><a href="/council/">Councils</a> · <a href="/trust/">Academy trusts</a> · <a href="/compare/">Compare schools side by side</a> · <a href="/about/">How it works</a></p>'
    body += sources()
    crumbs = [("School Money", "/")]
    description = shorten(f"{len(deficit):,} English state schools are in deficit. See which, by council and school: reserves, spending and 8-year trends from DfE returns.", 160)
    return page("School finances in England: which schools are in deficit | School Money", description, "/", body, crumbs, metadata)


def trusts_of(schools):
    trusts = defaultdict(list)
    for i in schools:
        if i["academy"] and i["trust"] and i["status"]:
            trusts[i["trust"]].append(i)
    return trusts


def render_trust(name, items, metadata):
    """The trust's pages as [(path, html)], the academy table split over pages when large."""
    path = items[0]["trust_path"]
    counts = Counter(i["status"]["status"] for i in items)
    total = sum(i["status"]["reserve"] for i in items)
    shared = all(i["status"]["trust_share_included"] for i in items)
    crumbs = [("School Money", "/"), ("Academy trusts", "/trust/"), (name, path)]
    description = shorten(f"{name}: reserves and financial status of its {len(items)} academies from DfE accounts returns.", 160)

    def frame(n, pages, table_html):
        body = f'<h1>{esc(name)}: academy finances</h1>'
        if n > 1:
            body += (f'<p class="lead">Academies of {esc(name)} with a full-year return, worst first: page {n} of {pages}. '
                     f'<a href="{esc(path)}">Back to the summary</a>.</p>' + sort_note(pages) + table_html + sources())
            return (shorten(f"{name} academy finances, page {n} | School Money", 70),
                    shorten(f"Page {n} of {pages}: {name}'s academies and their financial status from DfE accounts returns.", 160), crumbs, body)
        body += (f'<p class="lead">{len(items):,} academies with a full-year return. Their reserves add up to <strong>{mf("revenue_reserve", total, pupils_of(items), latest_year(items))}</strong>'
                 + (", including each school's share of the trust's central reserve." if shared else ".") + "</p>")
        body += charts.status_bar(counts)
        body += ('<p class="note">A trust can move money between its academies, so a school shown in deficit may be supported by the trust '
                 'as a whole. The trust-wide figure is the better guide to whether the trust is in difficulty.</p>')
        body += "<h2>Academies, worst first</h2>" + sort_note(pages) + table_html + sources()
        return shorten(f"{name} academy finances | School Money", 70), description, crumbs, body

    return paged(path, COUNCIL_HEADERS, council_rows(items), frame, metadata)


def render_trust_index(trusts, metadata):
    """Every trust, alphabetically, as [(path, html)] over as many pages as needed."""
    rows = []
    for name, items in sorted(trusts.items(), key=lambda kv: kv[0].casefold()):
        d = sum(i["status"]["status"] == "in_deficit" for i in items)
        total = sum(i["status"]["reserve"] for i in items)
        rows.append([f'<a href="{esc(items[0]["trust_path"])}">{esc(name)}</a>', f'<span data-sort="{len(items)}">{len(items):,}</span>',
                     f'<span data-sort="{d}">{d:,}</span>', f'<span data-sort="{total:.0f}">{mf("revenue_reserve", total, pupils_of(items), latest_year(items))}</span>'])
    crumbs = [("School Money", "/"), ("Academy trusts", "/trust/")]

    def frame(n, total, table_html):
        body = ('<h1>Academy trust finances</h1><p class="lead">Every academy trust in England with its academies\' reserves and how many are in deficit'
                + (f", A to Z over {total} pages" if total > 1 else "") + ".</p>"
                + (sort_note(total) + table_html if table_html else "<p>No academy trust has an academy with a full-year return in the latest data yet.</p>") + sources())
        suffix = f", page {n}" if n > 1 else ""
        return (shorten(f"Academy trust finances in England{suffix} | School Money", 70),
                shorten(f"Academy trusts in England{suffix}: combined reserves and how many of their academies are in deficit, from DfE accounts returns.", 160), crumbs, body)

    return paged("/trust/", ["Trust", "Academies", "In deficit", "Combined reserves"], rows, frame, metadata)


def render_constituency(name, path, items, metadata):
    """Stub: the schools in one parliamentary constituency with their status badges."""
    assessed = [i for i in items if i["status"]]
    deficit = [i for i in assessed if i["status"]["status"] == "in_deficit"]
    crumbs = [("School Money", "/"), ("Areas", "/areas/"), (name, path)]
    rows = [[school_link(i), council_link(i["council"]), status_cell(i)] for i in sorted(items, key=lambda i: ((i["status"] or {}).get("rank", 9), i["name"]))]

    def frame(n, total, table_html):
        body = f'<h1>Schools in {esc(name)}: finances</h1>'
        body += f'<p class="status-line">{pin("area", "constituency-" + path.strip("/").split("/")[-1], name)}</p>'
        if n == 1:
            body += (f'<p class="lead">{len(deficit):,} of the {len(assessed):,} schools in {esc(name)} with a full-year return were in deficit at their latest return.</p>'
                     + charts.status_bar(Counter(i["status"]["status"] for i in assessed)))
        else:
            body += f'<p class="lead">Page {n} of {total}. <a href="{esc(path)}">Back to the summary</a>.</p>'
        body += sort_note(total) + table_html + sources()
        suffix = f", page {n}" if n > 1 else ""
        return (shorten(f"{name} school finances{suffix} | School Money", 70),
                shorten(f"Every school in the {name} constituency with its financial status from DfE returns.", 160), crumbs, body)

    return paged(path, ["School", "Council", "Status"], rows, frame, metadata)


def render_region(name, path, councils, metadata):
    """Stub: one region's councils with their deficit counts."""
    crumbs = [("School Money", "/"), ("Areas", "/areas/"), (name, path)]
    rows = [council_cells(c) for c in councils if any(i["status"] for i in c["schools"])]
    body = (f'<h1>{esc(name)}: school finances by council</h1><p class="status-line">{pin("area", "region-" + path.strip("/").split("/")[-1], name)}</p>'
            + (sortable(COUNCIL_INDEX_HEADERS, rows) if rows else f"<p>No council in {esc(name)} has a school with a full-year return yet.</p>") + sources())
    return page(shorten(f"{name} school finances by council | School Money", 70),
                shorten(f"Councils in {name}: how many schools are in deficit and their combined deficits, from DfE returns.", 160), path, body, crumbs, metadata)


def render_stub(path, title, text, links, metadata):
    body = (f'<h1>{esc(title)}</h1><p class="lead">{esc(text)}</p><ul>' + "".join(f'<li><a href="{esc(p)}">{esc(n)}</a></li>' for n, p in links) + "</ul>" + sources())
    return page(f"{title} | School Money", shorten(text, 160), path, body, [("School Money", "/"), (title, path)], metadata, indexable=False)


def render_404(metadata):
    body = ('<h1>Page not found</h1><p class="lead">That page isn\'t here. Search for a school above, or start from one of these:</p>'
            '<ul><li><a href="/">Find a school</a></li><li><a href="/council/">Councils</a></li><li><a href="/trust/">Academy trusts</a></li>'
            '<li><a href="/about/">How the figures work</a></li></ul>')
    return page("Page not found | School Money", "This School Money page doesn't exist.", "/404.html", body, [("School Money", "/"), ("Not found", "/404.html")], metadata, indexable=False)


def render_compare(metadata):
    body = ('<h1>Compare school finances side by side</h1><p class="lead">Pick up to four schools to compare their reserves, spending per pupil and trends.</p>'
            '<div id="compare-app"><form class="finder" role="search" onsubmit="return false"><label for="cmp-find">Add a school</label>'
            '<input id="cmp-find" type="search" placeholder="School name or town" autocomplete="off" aria-controls="cmp-results">'
            '</form><ul id="cmp-results" class="results" role="listbox" aria-label="Matching schools"></ul>'
            '<ul id="cmp-chosen" class="chosen" aria-live="polite"></ul><div id="cmp-out"><p class="muted">Search above, pin schools from their pages, or open any school\'s money page and use “Compare side by side”.</p></div></div>'
            '<noscript><p>The comparison needs JavaScript. Each school\'s own money page works without it.</p></noscript>' + sources())
    crumbs = [("School Money", "/"), ("Compare", "/compare/")]
    return page("Compare school finances | School Money", "Compare up to four English schools' reserves, spending per pupil and finance trends side by side.",
                "/compare/", body, crumbs, metadata)


def render_about(metadata, dsg=None, ifs=None):
    ifs = ifs or {}
    labels = [
        ("in_deficit", "The school's revenue reserve was below zero at the end of its latest full year: over the years it has spent more than it received."),
        ("heading_for_deficit", "Still above zero, but the school has spent more than it received for at least two years running and, at its average overspend over the last three years, its reserve would run out within about three years."),
        ("tight", "A reserve under 3% of a year's income: little room for an unexpected cost."),
        ("healthy", "A reserve between 3% of income and the large-reserve level."),
        ("large_reserves", "A reserve of 8% of a year's income or more (5% for secondary schools), the levels the DfE once called excessive and many councils still use to claw back surpluses."),
    ]
    body = '<h1>How the school money figures work</h1>'
    body += "<h2>The five statuses</h2><ul class=\"defs\">" + "".join(f"<li>{badge(k)} {esc(v)}</li>" for k, v in labels) + "</ul>"
    body += """<h2 id="method">What a deficit means</h2>
<p>A school deficit isn't a bank loan. It means the school has spent more over the years than it received, so its revenue reserve, the money it carries from year to year, is below zero.</p>
<p>For a <strong>council-run school</strong>, the council covers the gap from its schools budget. It usually agrees a recovery plan, often called a licensed deficit, with a date by which the school must be back in balance, and can step in if the plan isn't kept.</p>
<p>An <strong>academy</strong> is part of a trust. A trust can move money between its schools, so one academy in deficit may be propped up by the others. Where the DfE publishes it, an academy's reserve here includes its per-pupil share of the trust's central reserve, and each trust has its own page.</p>
<h2>Where the numbers come from</h2>
<p>Every school in England reports its income, spending and balances to the Department for Education each year. Council-run schools use the Consistent Financial Reporting (CFR) return for April to March; academies use the Academy Accounts Return for September to August. The DfE publishes both in its Financial Benchmarking and Insights Tool, and every school page here links to the matching DfE page so you can check the figures.</p>
<p>Figures are shown as published, in cash terms, with the per-pupil figure beside every total using that same year's pupil numbers. Part-year returns (a school that opened, converted or changed trust during the year) are left out of statuses and trends. When a school became an academy, its earlier years come from its council-run return under its old DfE number, linked through Get Information about Schools.</p>
<h2 id="real-terms">Real terms</h2>
<p>Where a figure is shown "in 2025-26 prices" it has been adjusted with the HM Treasury GDP deflator (October 2026 edition), the whole-economy measure the Treasury and the Institute for Fiscal Studies use for public spending. Academy years (September to August) use a month-weighted average of the two financial years they span. It reflects general inflation, not school-specific costs such as teacher pay or energy.</p>
<h2>Similar schools</h2>
<p>For each school we take the 30 schools of the same phase, in London or outside it to match, that are closest in pupil numbers and in the share of pupils on free school meals. Spending per pupil is compared with the middle half of that group.</p>
<h2>Councils' schools budgets</h2>
<p>Each council page shows the council's dedicated schools grant (DSG) balance by year from the DfE's published outturn: the cumulative surplus or deficit on the money it receives for schools and high-needs provision, in cash terms. Per-pupil figures divide by the pupils on roll that year at the schools on this site. Councils in the DfE's safety valve or delivering better value programmes have agreed plans to recover large high-needs deficits.</p>
<h2>Parents' associations</h2>
<p>Where a PTA or friends' charity can be matched to a school in the Charity Commission register, its income is shown. That money is separate from the school's own accounts. A missing PTA usually means it is too small to register or couldn't be matched with confidence.</p>
<h2>Corrections</h2>
<p>If a figure looks wrong, compare it with the DfE page linked from the school. If the DfE's figure differs from ours, it's our mistake: <a href="https://www.schoolsinreach.com/about.html">tell us</a>.</p>"""
    src = ifs.get("source") or {}
    cite = ifs.get("citation") or src.get("short_cite")
    if cite:
        body += (f'<h2 id="context">Context</h2><p>National context, such as what schools spend per pupil and why costs have risen faster than funding, '
                 f'draws on <a href="{esc(src.get("url") or "https://ifs.org.uk/")}">{esc(src.get("title") or "the IFS annual report on education spending")}</a>. '
                 f'Cite as: {esc(cite)}.</p>')
    dsg_src = (dsg or {}).get("source")
    dsg_item = ""
    if dsg_src:
        label = dsg_src.get("title") if isinstance(dsg_src, dict) else str(dsg_src)
        url = dsg_src.get("url") if isinstance(dsg_src, dict) else None
        dsg_item = f'<li>{f"<a href={json.dumps(url)}>{esc(label)}</a>" if url else esc(label)} (council DSG balances) — Open Government Licence v3.0</li>'
    body += ('<h2 id="sources">Sources</h2><ul>'
             f'<li><a href="{FBIT_SOURCES}">DfE Financial Benchmarking and Insights Tool</a>: CFR and Academy Accounts Return workbooks, 2018-19 onwards</li>'
             '<li><a href="https://get-information-schools.service.gov.uk/">Get Information about Schools</a>: the school register and academy conversions</li>'
             '<li><a href="https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download">Charity Commission register</a>: parents\' associations</li>'
             '<li><a href="https://www.gov.uk/government/collections/gdp-deflators-at-market-prices-and-money-gdp">HM Treasury GDP deflators</a>, October 2026</li>'
             + dsg_item + "</ul>")
    body += (f'<h2 id="licences">Licences</h2><p>The DfE, Get Information about Schools, Charity Commission and HM Treasury data above are published under the '
             f'<a href="{OGL}">Open Government Licence v3.0</a>. Our derived figures and pages may be reused under the same terms with a link back to School Money. '
             'IFS material is quoted with attribution to the IFS and the Nuffield Foundation.</p>')
    body += sources('<li><a href="https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download">Charity Commission register</a> — Open Government Licence v3.0</li>')
    crumbs = [("School Money", "/"), ("How it works", "/about/")]
    return page("How school finance statuses are worked out | School Money",
                "What a school deficit means, where the figures come from and how each school's financial status is worked out.",
                "/about/", body, crumbs, metadata)


# ----------------------------------------------------------------- data

def rounded(value):
    return None if value is None else round(value)


def school_json(item, data_root=None, profile=None, line=None):
    st, latest = item["status"], item["latest"]
    council = item["council"]
    statuses = {t["year"]: t["status"] for t in (line or [])}
    years = [{"y": year_label(r), "income": rounded(r.get("total_income")), "spend": rounded(r.get("total_expenditure")),
              "balance": rounded(r.get("in_year_balance")), "reserve": rounded(reserve_of(r)), "pupils": r.get("pupils"),
              "status": statuses.get(year_label(r))} for r in item["years"]]
    pp = {k: per_pupil(latest, k) for k, _ in COMPARE_KEYS + [("total_expenditure", ""), ("total_income", "")]}
    pupils = latest.get("pupils")
    out = {"urn": item["urn"], "name": item["name"], "path": item["path"],
           "council": {"code": council["code"], "name": council["name"], "path": council["path"]},
           "status": st["status"], "label": st["label"], "reason": st["reason"], "year": year_label(latest),
           "academy": item["academy"], "trust": item["trust"], "trust_path": item.get("trust_path"), "pupils": pupils,
           "income": rounded(latest.get("total_income")), "income_pp": rounded(per_pupil(latest, "total_income")),
           "spend": rounded(latest.get("total_expenditure")), "spend_pp": rounded(per_pupil(latest, "total_expenditure")),
           "reserve": rounded(st["reserve"]), "reserve_pp": rounded(st["reserve"] / pupils) if pupils else None, "share": st["reserve_share"],
           "balance": rounded(latest.get("in_year_balance")), "balance_pp": rounded(per_pupil(latest, "in_year_balance")),
           "streak": st["deficit_streak"], "pupils_change": st["pupils_change"], "years": years,
           "pp": {k: round(v) for k, v in pp.items() if v is not None}, "similar": {k: round(v) for k, v in similar_medians(item).items()},
           "income_lines": {g: round(latest[k]) for k, g, _ in INCOME_LINES if latest.get(k) is not None},
           "lines": {k: v for k, v in (latest.get("lines") or {}).items() if v is not None},
           "pta": [{"charity_number": c.get("charity_number"), "name": c.get("name"), "status": c.get("status"),
                    "latest_income": c.get("latest_income"), "history": c.get("history") or []} for c in item["pta"]],
           "check": fbit_school(item)}
    if profile:
        out.update({"tags": profile.get("tags"), "band": profile.get("band"), "area": profile.get("area")})
    if line:
        out["timeline"] = line
    return out


def area_stats(items, year):
    """Reduced yearly summary for a set of schools when areas.py is absent: None where fewer than 5."""
    rows = [(i, r) for i in items for r in i["years"] if year_label(r) == year]
    if len(rows) < 5:
        return None
    reserves = [(reserve_of(r), r.get("pupils")) for _, r in rows]
    deficits = [(v, p) for v, p in reserves if v is not None and v < 0]
    deficit_pupils = sum(p for _, p in deficits if p)
    deficit_total = -sum(v for v, _ in deficits)

    def med(key):
        vals = [per_pupil(r, key) for _, r in rows]
        vals = [v for v in vals if v is not None]
        return round(statistics.median(vals)) if vals else None

    reserve_pp = [v / p for v, p in reserves if v is not None and p]
    return {"schools": len(rows), "in_deficit": len(deficits), "in_deficit_pct": round(100 * len(deficits) / len(rows), 1),
            "deficit_total": round(deficit_total), "deficit_pp": round(deficit_total / deficit_pupils) if deficit_pupils else None,
            "reserve_median_pp": round(statistics.median(reserve_pp)) if reserve_pp else None,
            "income_pp_median": med("total_income"), "spend_pp_median": med("total_expenditure")}


def reduced_area(name, items):
    years = sorted({year_label(r) for i in items for r in i["years"]})
    by_year = {}
    for y in years:
        groups = {"all": items, "council-run": [i for i in items if not i["academy"]], "academy": [i for i in items if i["academy"]]}
        by_year[y] = {g: area_stats(members, y) for g, members in groups.items()}
    return {"name": name, "pupils_by_year": dict(pupils_by_year(items)),
            "schools_by_year": {y: sum(1 for i in items for r in i["years"] if year_label(r) == y) for y in years},
            "by_year": by_year, "dsg": {}, "statuses_latest": dict(Counter(i["status"]["status"] for i in items if i["status"]))}


def area_documents(councils, schools, pta, dsg, data_root, by_urn):
    """{area id: document} for /data/a/<id>.json, from areas.build_areas when it imports."""
    regions = defaultdict(list)
    for c in councils:
        if c.get("region"):
            regions[c["region"]].append(c)
    constituencies = defaultdict(list)
    for i in schools:
        if i["constituency"]:
            constituencies[i["constituency"]].append(i)
    built = None
    if areas is not None:
        try:
            registers = [dict(i["school"], la_code=i["council"]["code"]) for i in schools]
            built = areas.build_areas({i["urn"]: i["rows"] for i in schools}, registers, pta, dsg, data_root)
        except Exception:
            built = None
    docs = {}

    def put(ident, kind, name, path, fallback_items):
        a = None
        if built:
            if kind == "england":
                a = built.get("england")
            elif kind == "region":
                a = (built.get("regions") or {}).get(name)
            elif kind == "council":
                a = (built.get("councils") or {}).get(ident.removeprefix("council-"))
            elif kind == "constituency":
                a = next((v for v in (built.get("constituencies") or {}).values() if v.get("name") == name), None)
        if a is None:
            a = reduced_area(name, fallback_items)
            if kind == "council":
                values = dsg_for(dsg, ident.removeprefix("council-")).get("values") or {}
                pupils = pupils_by_year(fallback_items)
                a["dsg"] = {y: {"balance": v, "per_pupil": round(v / pupils[y]) if pupils.get(y) else None} for y, v in values.items() if v is not None}
            elif kind == "england":
                pupils = pupils_by_year(fallback_items)
                a["dsg"] = {y: {"balance": v, "per_pupil": round(v / pupils[y]) if pupils.get(y) else None} for y, v in (dsg.get("england") or {}).items() if v is not None}
        docs[ident] = {"id": ident, "type": kind, "name": name, "path": path, **a}

    put("england", "england", "England", "/", schools)
    for name, cs in regions.items():
        put(f"region-{slug(name)}", "region", name, f"/areas/{slug(name)}/", [i for c in cs for i in c["schools"]])
    for c in councils:
        put(f"council-{c['code']}", "council", c["name"], c["path"], c["schools"])
    for name, items in constituencies.items():
        put(f"constituency-{items[0]['constituency_path'].strip('/').split('/')[-1]}", "constituency", name, items[0]["constituency_path"], items)
    return docs


def search_index(councils, schools, trusts):
    index = []
    for i in schools:
        index.append({"t": "school", "id": i["urn"], "name": i["name"], "sub": ", ".join(x for x in (i["school"].get("town"), i["council"]["name"]) if x),
                      "status": i["status"]["status"] if i["status"] else None, "p": i["path"]})
    for c in councils:
        if c["schools"]:
            index.append({"t": "council", "id": c["code"], "name": c["name"], "sub": c.get("region") or "", "status": None, "p": c["path"]})
    seen = set()
    for i in schools:
        if i["constituency"] and i["constituency_path"] not in seen:
            seen.add(i["constituency_path"])
            index.append({"t": "constituency", "id": i["constituency_path"].strip("/").split("/")[-1], "name": i["constituency"],
                          "sub": "Constituency", "status": None, "p": i["constituency_path"]})
    for name, items in trusts.items():
        index.append({"t": "trust", "id": items[0]["trust_path"].strip("/").split("/")[-1], "name": name,
                      "sub": f"{len(items)} academies", "status": None, "p": items[0]["trust_path"]})
    return index


def write_urlset(path, entries, base=BASE_MONEY, index=False):
    """A sitemap (or sitemap index) whose locs sit on `base`; entries = [(path, lastmod)]."""
    ET.register_namespace("", NS)
    root = ET.Element(f"{{{NS}}}" + ("sitemapindex" if index else "urlset"))
    for url, modified in entries:
        node = ET.SubElement(root, f"{{{NS}}}" + ("sitemap" if index else "url"))
        ET.SubElement(node, f"{{{NS}}}loc").text = base + url
        if modified:
            ET.SubElement(node, f"{{{NS}}}lastmod").text = modified
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def write_sitemaps(out, urls, today, limit=45_000):
    """sitemap.xml as an index over /sitemaps/pages-N.xml chunks (each under the 50k-loc limit)."""
    maps = []
    for start in range(0, max(len(urls), 1), limit):
        chunk = urls[start:start + limit]
        where = f"/sitemaps/pages-{start // limit + 1}.xml"
        write_urlset(out / where.lstrip("/"), chunk)
        maps.append((where, today))
    write_urlset(out / "sitemap.xml", maps, index=True)


# ----------------------------------------------------------------- build

def build(site, history_path, links_path, pta_path, out=None, dsg_path=ROOT / "pipeline/money/data/la_dsg.json"):
    started = time.perf_counter()
    site = Path(site).resolve()
    out = Path(out).resolve() if out else ROOT / "site_money"
    index_html = site / "index.html"
    metadata = HeadMetadata(index_html.read_text(encoding="utf-8")) if index_html.is_file() else None
    councils, schools, by_urn = build_model(site, history_path, links_path, pta_path)
    dsg = load_dsg(dsg_path)
    ifs = load_ifs()
    pta_doc = json.loads(pta_path.read_text(encoding="utf-8")) if pta_path and pta_path.exists() else {}
    data_root = site / "data"
    today = date.today().isoformat()
    urls = []
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".site_money-build-", dir=out.parent) as staging:
        stage = Path(staging) / "site_money"
        stage.mkdir()
        written = set()

        def write(path, html):
            """One page at a clean path, never twice, never at or over the size budget."""
            if not PATH.fullmatch(path):
                raise ValueError(f"Unsafe page path {path!r}")
            if path in written:
                raise ValueError(f"Two pages share the path {path}")
            written.add(path)
            size = len(html.encode("utf-8"))
            if size >= PAGE_BUDGET:
                raise ValueError(f"Page too large ({size:,} bytes): {path}")
            target = stage / path.lstrip("/") / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")

        def write_all(pages, indexable=True):
            for path, html in pages:
                write(path, html)
                if indexable:
                    urls.append((path, today))

        write("/", render_national(councils, schools, metadata, dsg))
        urls.append(("/", today))
        write_all(render_council_index(councils, metadata))
        for c in councils:
            if c["schools"]:
                write_all(render_council(c, metadata, dsg), indexable=any(i["status"] for i in c["schools"]))
        for item in schools:
            write(item["path"], render_school(item, metadata, data_root))
            if item["status"]:
                urls.append((item["path"], today))
        trusts = trusts_of(schools)
        write_all(render_trust_index(trusts, metadata))
        for name, items in trusts.items():
            write_all(render_trust(name, items, metadata))
        constituencies = defaultdict(list)
        for i in schools:
            if i["constituency"]:
                constituencies[(i["constituency"], i["constituency_path"])].append(i)
        for (name, path), items in constituencies.items():
            write_all(render_constituency(name, path, items, metadata), indexable=any(i["status"] for i in items))
        regions = defaultdict(list)
        for c in councils:
            if c.get("region") and c["schools"]:
                regions[c["region"]].append(c)
        for name, cs in regions.items():
            write(f"/areas/{slug(name)}/", render_region(name, f"/areas/{slug(name)}/", cs, metadata))
            urls.append((f"/areas/{slug(name)}/", today))
        write("/compare/", render_compare(metadata))
        write("/about/", render_about(metadata, dsg, ifs))
        urls += [("/compare/", today), ("/about/", today)]
        for path, title, text, links in STUBS:
            write(path, render_stub(path, title, text, links, metadata))
        (stage / "404.html").write_text(render_404(metadata), encoding="utf-8")
        (stage / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /data/\nSitemap: {BASE_MONEY}/sitemap.xml\n", encoding="utf-8")
        data = stage / "data"
        (data / "s").mkdir(parents=True)
        (data / "a").mkdir()
        statuses = {}
        for item in schools:
            if not item["status"]:
                continue
            doc = school_json(item, data_root, profile_of(item, data_root), timeline_of(item))
            (data / "s" / f"{item['urn']}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            statuses[item["urn"]] = {"status": item["status"]["status"], "label": item["status"]["label"], "path": item["path"]}
        for ident, doc in area_documents(councils, schools, pta_doc, dsg, data_root, by_urn).items():
            if not re.fullmatch(r"[a-z0-9-]+", ident):
                raise ValueError(f"Unsafe area id {ident!r}")
            (data / "a" / f"{ident}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (data / "search.json").write_text(json.dumps(search_index(councils, schools, trusts), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (data / "status.json").write_text(json.dumps(statuses, separators=(",", ":")), encoding="utf-8")
        assets = stage / "assets"
        assets.mkdir()
        for asset in _shell().asset_files():
            shutil.copyfile(asset, assets / Path(asset).name)
        write_sitemaps(stage, urls, today)
        if out.is_symlink():
            raise ValueError(f"Refusing to replace symlink: {out}")
        if out.exists():
            shutil.rmtree(out)
        shutil.move(str(stage), out)
    counts = Counter(i["status"]["status"] for i in schools if i["status"])
    return {"schools": len(schools), "with_status": sum(counts.values()), "councils": len(councils), "trusts": len(trusts),
            "constituencies": len(constituencies), "statuses": dict(counts), "pages": len(urls), "out": str(out),
            "runtime": time.perf_counter() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=ROOT / "site")
    parser.add_argument("--history", type=Path, default=ROOT / "pipeline/.cache/dfe/finance_history.jsonl")
    parser.add_argument("--links", type=Path, default=ROOT / "pipeline/.cache/dfe/gias/links.csv")
    parser.add_argument("--pta", type=Path, default=ROOT / "pipeline/.cache/money/pta.json")
    parser.add_argument("--dsg", type=Path, default=ROOT / "pipeline/money/data/la_dsg.json")
    parser.add_argument("--out", type=Path, default=ROOT / "site_money")
    args = parser.parse_args()
    try:
        summary = build(args.site_dir, args.history, args.links, args.pta, args.out, args.dsg)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Money build failed: {exc}\n")
    print(f"School Money: {summary['pages']:,} indexable pages in {summary['out']}; {summary['schools']:,} schools ({summary['with_status']:,} with a status), "
          f"{summary['councils']} councils, {summary['constituencies']:,} constituencies, {summary['trusts']:,} trusts; {summary['runtime']:.1f}s")
    print("Statuses:", ", ".join(f"{STATUS_LABELS[k]} {summary['statuses'].get(k, 0):,}" for k in STATUS_ORDER))
    print("Shell:", "pipeline/money/site.py" if shell is not None else "built-in fallback",
          "| areas:", "yes" if areas else "no", "| timeline:", "yes" if timeline else "no", "| deflator:", "yes" if deflator else "no")


if __name__ == "__main__":
    main()
