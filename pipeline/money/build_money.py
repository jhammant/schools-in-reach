#!/usr/bin/env python3
"""Build the standalone School Money site (site_money/): English school finances from DfE returns.

Inputs are local and rebuilt by pipelines; no network:
- pipeline/.cache/dfe/finance_history.jsonl from pipeline/dfe/finance_history.py
- site/data (school register and council index, from pipeline/dfe/build.py)
- pipeline/.cache/dfe/gias/links.csv (GIAS links: a converted academy's predecessor URN)
- pipeline/.cache/money/pta.json from pipeline/money/pta.py (optional)
- pipeline/money/data/la_dsg.json (councils' Dedicated Schools Grant balances, all four blocks, committed)

Writes site_money/, served at https://money.schoolsinreach.com: national, England, region, council,
constituency, school, trust, debts, PTFA, compare, about and stub pages at clean paths;
/data/{search,status}.json, /data/s/<urn>.json (with 'nearby': the school beside its nearest schools of the
same phase, see add_nearby), /data/sx/<urn>.json (a school's multi-year SERIES) and
/data/a/<id>.json for the app; sitemap, robots and 404. Every open register school except colleges and
universities gets a page. Long tables continue on /2/, /3/… pages sized against the page around them,
so pages stay under AREA_PAGE_TARGET where they can and always under PAGE_BUDGET (SCHOOL_PAGE_BUDGET
for /school/ pages; the first page of a council's or constituency's schools also gets AREA_TABLE_ALLOWANCE,
so it lists AREA_TABLE_ROWS of them). pipeline/seo/build_pages.py reads /data/status.json to link school pages here.

Pages are wrapped by pipeline/money/site.py (the app shell) when it is present, else by a
minimal fallback below with the same signatures. The other modules are optional too, each through a
lazy import with the renderers below as the fallback: areas.py (tags and area statistics), timeline.py,
deflator.py (real terms), series.py (the SERIES behind charts and drills), school_page.py (the school
dashboard) and area_pages.py (the area dashboards). After the core pages, the extensions in EXTENSIONS
(map, deck, Wrapped, guides) write their own pages through write_pages(env).
"""
import argparse
import csv
import hashlib
import importlib
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
try:
    from pipeline.money import series
except ImportError:  # unit B1's SERIES: local_series below follows the same contract
    series = None
try:
    from pipeline.money import school_page
except ImportError:  # unit B2's school dashboard: render_school below is the fallback
    school_page = None
try:
    from pipeline.money import area_pages
except ImportError:  # unit B3's area dashboards: render_council, render_trust, ... are the fallback
    area_pages = None

ROOT = Path(__file__).resolve().parents[2]
BASE_MONEY = "https://money.schoolsinreach.com"
BASE_SIR = "https://www.schoolsinreach.com"
FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk"
FBIT_SOURCES = FBIT + "/data-sources"
# A charity's register page: the number sits mid-URL, so links are built only by charity_url().
CHARITY_URL = ("https://register-of-charities.charitycommission.gov.uk/charity-search?p_p_id=uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet"
               "&p_p_lifecycle=0&p_p_state=maximized&p_p_mode=view"
               "&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_regId={number}"
               "&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_subId=0")
CHARITY_REGISTER = "https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download"
OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
ONS_NOTICE = "Source: Office for National Statistics licensed under the Open Government Licence v.3.0"
# (boundaries, where the site uses them, the year of their OS notice): the notice each ONS boundary set carries.
BOUNDARIES = [("Council boundaries", "the map", "2025"), ("Parliamentary constituency boundaries", "the map", "2024"),
              ("Lower layer super output area (LSOA) boundaries", "each school's neighbourhood and catchment figures", "2021")]
HELD = "reserve_held_by_trust"  # status.py's sixth status: never tight, never a deficit
HELD_ICON = "◇"
REPORT_LINK = '<a class="report-link" href="/about/#corrections">Report an error or add context</a>'
DSG_NAME = "Dedicated Schools Grant balance (all four blocks)"
DSG_DENOMINATOR = "pupils at the council's schools on this site that year"
SCOPE_NOTE = ("Counts sit below the DfE's published totals: only full-year returns count (schools that opened, converted, "
              "changed trust or closed mid-year are left out), a federation counts once through its lead school, and "
              "independent schools are not included.")
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
# School dashboards carry several years of every line, so /school/ pages get SCHOOL_PAGE_BUDGET.
PAGE_BUDGET = 48_000
# 80 KB (~15 KB gzipped), up from 64 KB: the nearby-schools section and the charts' per-year readout data pushed
# most pages to the old limit, where the nearby section fell back to a cut-down table or none.
SCHOOL_PAGE_BUDGET = 80_000
AREA_PAGE_TARGET = 40_000  # paged tables are cut so each page, shell included, stays under this when it can
# A council or constituency page opens with its charts, so at 40 KB its first page held only about five schools
# (Hackney: 5 of 60). Its school table gets its own allowance on top: AREA_TABLE_ROWS rows of up to 2.5 KB each
# (five money figures with their data-* attributes and a sparkline; the largest real row is 2.35 KB), so a parent
# finds their school without paging. Only those first pages get it; every other page keeps PAGE_BUDGET.
AREA_TABLE_ROWS = 25
AREA_TABLE_ALLOWANCE = AREA_TABLE_ROWS * 2_500
SX_BUDGET = 12_000         # bytes of one /data/sx/<urn>.json
SIMILAR_MIN = 5            # similar schools with a value before their median is passed to a page
DSG_YEARS = 6              # years of DSG balances listed on a page (the area JSON carries them all)
SCHOOL_HEAD = '<link rel="stylesheet" href="/assets/school.css"><script src="/assets/trend.js" defer></script>'
AREA_HEAD = '<link rel="stylesheet" href="/assets/areas.css"><script src="/assets/trend.js" defer></script>'
EXTENSIONS = ("map_page", "deck", "wrapped", "guides")
NOT_SCHOOLS = {"Further education", "Higher education institutions", "Sixth form centres"}
NOT_SCHOOL_GROUPS = {"Colleges", "Universities"}
# series.METRICS when series.py is absent: (row key, glossary key, group), in the SHARED order.
METRICS = [(k, k, "income") for k in ("total_income", "grant_funding_government", "sen_funding", "pupil_premium", "self_generated_income",
                                      "donations_revenue", "donations_capital", "facilities_income", "catering_income", "other_dfe_grants")]
METRICS += [(k, k, "spend") for k in ("total_expenditure", "teaching_staff", "supply_staff", "education_support_staff", "admin_clerical_staff",
                                     "premises_staff", "catering_staff", "other_staff_costs", "total_staff", "premises", "energy", "occupation",
                                     "catering", "educational_supplies", "supplies_services", "bought_in_services")]
METRICS += [(k, k, "balance") for k in ("revenue_reserve", "in_year_balance")]
SIMILAR_SERIES = ("total_income", "total_expenditure", "grant_funding_government", "revenue_reserve")
SX_CORE = {"total_income", "total_expenditure", "revenue_reserve", "in_year_balance", "grant_funding_government", "total_staff",
           "sen_funding", "other_dfe_grants", "donations_revenue"}  # kept in a SERIES file whatever its size
AUDIENCE_LINKS = [
    ("Parents and carers", "/guides/parents/", "What a school's money means and the questions worth asking."),
    ("Governors", "/guides/governors/", "Reading the budget, reserves and the trend before a finance meeting."),
    ("PTFA committees", "/ptfa/", "What parents' associations raise and how it compares with similar schools."),
    ("School leaders", "/guides/school-leaders/", "Your school's figures beside similar schools and the national picture."),
    ("Pupils", "/guides/pupils/", "Where a school's money comes from and what it is spent on."),
]
URN = re.compile(r"[0-9]{1,8}")
PATH = re.compile(r"/(?:[a-z0-9-]+/)*")
STUBS = [
    ("/areas/", "Areas", "School finances by region, council and constituency: how many schools are in deficit and how the money per pupil compares.",
     [("Councils", "/council/"), ("England", "/")]),
    ("/map/", "Map", "A map of every school's financial status is coming. Until then, browse by council or search for a school.",
     [("Councils", "/council/"), ("Find a school", "/")]),
    ("/ptfa/", "PTFA", "Money raised by parent-teacher associations, matched to schools from the Charity Commission register, appears on each school's page.",
     [("Find a school", "/"), ("How PTAs are matched", "/about/#method")]),
    ("/debts/", "Debts", "Schools in deficit, councils' Dedicated Schools Grant balances and the trend over recent years.",
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
           ("PTFA", "/ptfa/"), ("Debts", "/debts/"), ("Compare", "/compare/"), ("Guides", "/guides/"), ("Tools", "/tools/")]

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
    """pipeline/money/data/la_dsg.json (every key, such as its statutory-override note), or an empty
    shape when the file is missing or unreadable."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        doc = {}
    doc = doc if isinstance(doc, dict) else {}
    return {**doc, "las": doc.get("las") or {}, "england": doc.get("england") or {},
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


def local_reserve_basis(rows):
    """series.reserve_basis's contract when series.py lacks it: the basis status.assess's headline uses,
    'incl_trust_share' when the latest full year carries the trust-share figure, else 'own'."""
    years = full_years(rows)
    latest = years[-1] if years else {}
    return "incl_trust_share" if latest.get("revenue_reserve_incl_trust_share") is not None else "own"


def local_reserve_on_basis(row, basis):
    """series.reserve_on_basis's contract: the row's reserve on that basis, never the other one (None when missing)."""
    return (row or {}).get("revenue_reserve_incl_trust_share" if basis == "incl_trust_share" else "revenue_reserve")


def reserve_basis(rows):
    """C3: one reserve basis for every year a school's page lists ('own' or 'incl_trust_share')."""
    rule = getattr(series, "reserve_basis", None) or local_reserve_basis
    return rule(rows)


def reserve_on(row, basis):
    rule = getattr(series, "reserve_on_basis", None) or local_reserve_on_basis
    return rule(row, basis)


def status_label(status):
    """The plain label of any status status.py gives, including ones charts.py may not know yet."""
    labels = dict(getattr(health, "LABELS", {}) or {}, **STATUS_LABELS)
    return labels.get(status) or ("Reserve held by the trust" if status == HELD else str(status).replace("_", " ").capitalize())


def status_badge(status, size=""):
    """charts.badge when charts knows the status, else the same markup with icon and word (never a KeyError)."""
    if status in STATUS_LABELS:
        return badge(status, size)
    icon = HELD_ICON if status == HELD else "•"
    return (f'<span class="badge s-{esc(status)} {esc(size)}"><span aria-hidden="true">{icon}</span> '
            f'{esc(status_label(status))}</span>')


def status_keys(counts):
    """STATUS_ORDER, then any other status present (reserve_held_by_trust last), for printing counts."""
    order = list(getattr(health, "ORDER", None) or STATUS_ORDER)
    return order + sorted(k for k in counts if k not in order)


def full_years(rows):
    """The full-year returns status.assess judges, oldest first, so the year a page reports
    is the year its reserve, share and status come from."""
    return health.full_years(rows)


def pupils_of_row(row):
    """A row's pupils for a per-pupil figure: None when missing or flagged suspect (a federation lead's
    combined return lists one school's pupils against the whole federation's money)."""
    pupils = (row or {}).get("pupils")
    return None if not pupils or suspect(row, "pupils") else pupils


def per_pupil(row, key):
    value, pupils = (row or {}).get(key), pupils_of_row(row)
    return value / pupils if value is not None and pupils else None


def metric_value(row, key):
    """A row's figure for a METRICS key. other_dfe_grants (pension, NI and other DfE grants, added by
    finance_history) is derived from its source line when the row predates it."""
    row = row or {}
    value = row.get(key)
    if value is None and key == "other_dfe_grants":
        value = row.get("aar_other_dfe_revenue_grants" if row.get("source") == "AAR" else "cfr_additional_grants_i18")
    return value


def suspect(row, key):
    return key in ((row or {}).get("suspect") or ())


def clean_pp(row, key):
    """£ per pupil for a median: None when the value is missing, has no pupils or either is flagged suspect."""
    if suspect(row, key):
        return None
    value, pupils = metric_value(row, key), pupils_of_row(row)
    return value / pupils if value is not None and pupils else None


def with_suspect_pupils(rows):
    """C5: series.suspect_pupils(rows) merged into each flagged row's 'suspect' list, as a new list on the
    row (school_rows already copies each row, and the list itself is never changed in place). Rows are
    returned unchanged without the helper or when it fails."""
    rule = getattr(series, "suspect_pupils", None)
    if rule is None or not rows:
        return rows
    try:
        flagged = rule(rows) or {}
    except Exception:  # a page must never fail on a data-quality hint
        return rows
    out = []
    for r in rows:
        keys = flagged.get(r.get("period_end")) or ()
        old = list(r.get("suspect") or [])
        new = [k for k in keys if k not in old]
        out.append(dict(r, suspect=old + new) if new else r)
    return out


def federation_of(item, row=None):
    """The GIAS federation name ('' when the register has none) when the row (else the latest return) is a
    federation lead school's combined return; None otherwise."""
    r = row if row is not None else item.get("latest")
    if not r or r.get("federated") != "Lead school":
        return None
    return str((item.get("school") or {}).get("federation") or "").strip()


def is_independent(school):
    return school.get("type_group") == "Independent schools" or "independent" in str(school.get("type") or "").lower()


def is_school(school):
    """Colleges and universities are on the register but are not schools here."""
    return school.get("type") not in NOT_SCHOOLS and school.get("type_group") not in NOT_SCHOOL_GROUPS


def local_pta_year(period_end, source):
    """The school year holding a charity return: April-March for a CFR school, September-August for an AAR one."""
    y, m = int(period_end[:4]), int(period_end[5:7])
    start = y if m >= (9 if source == "AAR" else 4) else y - 1
    return f"{start}-{str(start + 1)[2:]}"


def pta_year_label(period_end, rows):
    """SHARED PTA year rule for one school: the label of the school year containing period_end, using
    the source of the school's own row for that year, else its nearest year's source."""
    rule = getattr(series, "pta_year", None) or local_pta_year
    labelled = {(year_label(r), r.get("source")) for r in rows}
    for source in ("CFR", "AAR"):
        label = local_pta_year(period_end, source)
        if (label, source) in labelled:
            return rule(period_end, source)
    nearest = min(rows, key=lambda r: abs(_months(r["period_end"]) - _months(period_end)), default=None)
    return rule(period_end, (nearest or {}).get("source") or "CFR")


def _months(period_end):
    return int(period_end[:4]) * 12 + int(period_end[5:7])


def year_pupils(rows, label):
    """Pupils on roll in the school year `label`, from the school's own full-year return, else any return;
    None when that count is flagged suspect."""
    for pool in (full_years(rows), rows):
        for r in pool:
            if year_label(r) == label and r.get("pupils"):
                return pupils_of_row(r)
    return None


def pta_history_status(charity):
    """B4's history_status, derived from the history when pta.json predates it."""
    if charity.get("history_status"):
        return charity["history_status"]
    years = [int(h["period_end"][:4]) for h in charity.get("history") or [] if h.get("income") and h.get("period_end")]
    if years and max(years) >= 2024:
        return "current"
    return "recent" if years and max(years) >= 2019 else "historical"


def pta_share(charity):
    """A charity shared by an infant and a junior school is split equally between them."""
    return 1 / (1 + len(charity.get("shared_with") or []))


def local_series(rows, pta=None, *, sen_share_q3=None):
    """series.school_series's contract when series.py is absent: cash, per pupil and real figures for
    METRICS, the funding gap, PTA by school year and the suspect / not-reported flags. The site's
    falling-rolls, pass-through and high-SEND flags are left to series.py (None here)."""
    years = full_years(rows)
    basis = reserve_basis(rows)
    out = {"years": [], "source": {}, "pupils": {}, "m": {}, "gap": {}, "pta": {},
           "flags": {"falling_rolls": None, "pass_through": None, "high_send": None, "suspect": {}, "not_reported": {}},
           "trust_central_pp": {}, "reserve_basis": basis}
    for r in years:
        y, raw_pupils = year_label(r), r.get("pupils")
        pupils = pupils_of_row(r)
        out["years"].append(y)
        out["source"][y] = r.get("source")
        if raw_pupils:
            out["pupils"][y] = round(raw_pupils, 1)
        if r.get("suspect"):
            out["flags"]["suspect"][y] = list(r["suspect"])
        for key, _, _ in METRICS + ([("revenue_reserve_own", None, None)] if basis == "incl_trust_share" else []):
            if key == "revenue_reserve":
                value = reserve_on(r, basis)
            elif key == "revenue_reserve_own":
                value = r.get("revenue_reserve")
            else:
                value = metric_value(r, key)
            if value is None or (key == "pupil_premium" and r.get("source") == "AAR"):
                continue
            cell, real = {"v": round(value)}, real_terms(value, r)
            if pupils:
                cell["pp"] = round(value / pupils)
            if real is not None:
                cell["r"] = round(real)
                if pupils:
                    cell["rpp"] = round(real / pupils)
            out["m"].setdefault(key, {})[y] = cell
        gov, spend = (out["m"].get("grant_funding_government") or {}).get(y), (out["m"].get("total_expenditure") or {}).get(y)
        if gov and spend and "pp" in gov and "pp" in spend:
            out["gap"][y] = {"gov_pp": gov["pp"], "spend_pp": spend["pp"], "gov_rpp": gov.get("rpp"), "spend_rpp": spend.get("rpp")}
        if r.get("trust_central_spend_per_pupil") is not None:
            out["trust_central_pp"][y] = round(r["trust_central_spend_per_pupil"])
    if any(r.get("source") == "AAR" for r in years):
        out["flags"]["not_reported"]["pupil_premium"] = "not reported in academy accounts"
    by_year = {}
    for c in pta or []:
        if c.get("review"):
            continue
        share = pta_share(c)
        for h in c.get("history") or []:
            if h.get("income") is None or not h.get("period_end"):
                continue
            label = pta_year_label(h["period_end"], rows) if rows else local_pta_year(h["period_end"], "CFR")
            slot = by_year.setdefault(label, {"income": 0, "spend": 0, "top": (0, None), "confidence": "high"})
            income, spend = h["income"] * share, (h.get("expenditure") or 0) * share
            slot["income"] += income
            slot["spend"] += spend
            slot["top"] = max(slot["top"], (income, c.get("charity_number")), key=lambda t: t[0])
            if (c.get("match") or {}).get("confidence") == "medium":
                slot["confidence"] = "medium"
    for label in sorted(by_year):
        slot, pupils = by_year[label], year_pupils(rows, label)
        out["pta"][label] = {"income": round(slot["income"]), "spend": round(slot["spend"]),
                             "income_pp": round(slot["income"] / pupils) if pupils else None,
                             "spend_pp": round(slot["spend"] / pupils) if pupils else None,
                             "charity_number": slot["top"][1], "confidence": slot["confidence"]}
    return out


def school_series(item, sen_share_q3=None):
    """The school's SERIES: series.school_series when it imports, else local_series."""
    build = getattr(series, "school_series", None) or local_series
    return build(item["rows"], item["pta"], sen_share_q3=sen_share_q3)


def sen_share(row):
    rule = getattr(series, "sen_share", None)
    if rule is not None:
        return rule(row)
    income, sen = (row or {}).get("total_income"), (row or {}).get("sen_funding")
    return sen / income if sen is not None and income else None


def series_json(doc, limit=SX_BUDGET):
    """A SERIES dict as compact JSON of `limit` bytes or less. Over the limit the least-used parts go
    first: empty metrics, then the real-terms totals ('r', detailed lines first; every per-pupil real
    figure stays, and those are what drills and Wrapped read), then whole detailed lines from the end
    of METRICS. The core lines always stay; anything still over the limit is an error."""
    def dumps(d):
        return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

    def fits(d):
        return len(dumps(d).encode("utf-8")) <= limit

    if fits(doc):
        return dumps(doc)
    m = {k: {y: dict(c) for y, c in v.items()} for k, v in (doc.get("m") or {}).items() if v}
    doc = dict(doc, m=m)
    order = [k for k, _, _ in (getattr(series, "METRICS", None) or METRICS)]
    detail = sorted((k for k in m if k not in SX_CORE), key=lambda k: -order.index(k) if k in order else -len(order) - 1)

    def drop_r(keys):
        for k in keys:
            for c in m[k].values():
                c.pop("r", None)

    steps = [lambda: drop_r(detail), lambda: drop_r([k for k in m if k in SX_CORE])] + [lambda k=k: m.pop(k) for k in detail]
    for step in [lambda: None] + steps:
        step()
        if fits(doc):
            return dumps(doc)
    raise ValueError(f"SERIES file too large ({len(dumps(doc).encode('utf-8')):,} bytes) even with only its core lines")




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
            if closed(s) or not is_school(s):
                continue
            urn = str(s["urn"])
            if not URN.fullmatch(urn):
                raise ValueError(f"Bad URN {urn!r} in the {la['name']} register")
            rows = with_suspect_pupils(school_rows(urn, by_urn, pred))
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
                "la": code, "la_name": la["name"], "pupils": (latest or {}).get("pupils"),
                "lat": s.get("lat"), "lon": s.get("lon"), "independent": is_independent(s),
            }
            item["profile"] = profile_of(item, data)
            item["tags"] = (item["profile"] or {}).get("tags") or {}
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
    add_nearby(schools)
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


SIMILAR_JSON_KEYS = [k for k, _ in COMPARE_KEYS] + ["total_expenditure", "total_income"]  # /data/s 'similar'


def peer_row(other, year):
    """A similar school's full-year return for the year label (the later one if two share it), or None."""
    rows = [r for r in other.get("years") or [] if year_label(r) == year]
    return rows[-1] if rows else None


def similar_benchmark(item):
    """C2: the school's similar-school benchmark, worked out once and kept on the item. Every figure is for
    one stated year, the school's latest full year: {'year', 'peers' (similar schools with a full-year return
    that year), 'rows' (those returns), 'medians' {METRICS key: median £ per pupil from SIMILAR_MIN or more
    values}, 'quartiles' {COMPARE_KEYS key: (p25, p75) from 10 or more}}, suspect values and suspect pupil
    counts left out. ctx['similar'], /data/s 'similar', the compare rows and the fallback page all read it,
    so they never disagree. Only medians and quartiles are kept, not the values behind them."""
    if item.get("benchmark") is not None:
        return item["benchmark"]
    year = year_label(item["latest"]) if item.get("latest") else None
    keys = [k for k, _, _ in (getattr(series, "METRICS", None) or METRICS)]
    keys += [k for k in SIMILAR_JSON_KEYS if k not in keys]
    rows = [r for r in (peer_row(o, year) for o in item.get("similar") or []) if r is not None] if year else []
    medians, quartiles = {}, {}
    compared = {k for k, _ in COMPARE_KEYS}
    for k in keys:
        found = sorted(v for v in (clean_pp(r, k) for r in rows) if v is not None)
        if len(found) >= SIMILAR_MIN:
            medians[k] = statistics.median(found)
        if k in compared and len(found) >= 10:
            q = statistics.quantiles(found, n=4)
            quartiles[k] = (q[0], q[2])
    item["benchmark"] = {"year": year, "peers": len(rows), "rows": rows, "medians": medians, "quartiles": quartiles}
    return item["benchmark"]


def similar_meta(item):
    """C2: {'year', 'peers', 'method'} for the benchmark, the plain sentence readers can show beside it."""
    bench = similar_benchmark(item)
    phase = phase_label(item.get("phase")).lower()
    where = "in London" if item.get("london") else "outside London"
    method = (f"School Money's similar schools: the {len(item.get('similar') or [])} {phase} schools {where} closest in pupil "
              f"numbers and in the share of pupils on free school meals; medians use the {bench['peers']} of them with a "
              f"full-year return for {bench['year']}, leaving out figures flagged as unusual.")
    return {"year": bench["year"], "peers": bench["peers"], "method": method}


def similar_label(item):
    """'similar schools (17 schools, 2025-26)': how every page names the benchmark."""
    bench = similar_benchmark(item)
    return f"similar schools ({bench['peers']:,} school{'s' if bench['peers'] != 1 else ''}, {bench['year']})"


def compare_rows(s):
    """The school's spending lines beside the middle half of its similar schools, from the benchmark."""
    bench, out = similar_benchmark(s), []
    for key, label in COMPARE_KEYS:
        mine = per_pupil(s["latest"], key)
        if mine is None or key not in bench["quartiles"]:
            continue
        p25, p75 = bench["quartiles"][key]
        out.append({"key": key, "label": label, "value": mine, "p25": p25, "median": bench["medians"][key], "p75": p75})
    return out


def similar_medians(item):
    """Median £ per pupil among similar schools for /data/s 'similar' (its shape unchanged), from the benchmark."""
    medians = similar_benchmark(item)["medians"]
    return {k: medians[k] for k in SIMILAR_JSON_KEYS if k in medians}


def reserve_rank(s):
    mine = s["status"]["reserve_share"]
    others = [health.reserve_share(r) for r in similar_benchmark(s)["rows"]]
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


def sortable(headers, rows, css="", caption=""):
    html = table(headers, rows, caption=caption, css=f"sortable {css}".strip())
    return html.replace('<table class="responsive', '<table data-sortable class="responsive', 1)


def charity_url(number):
    """C9: a charity's page on the Charity Commission register (the number sits mid-URL)."""
    return CHARITY_URL.format(number=str(number).strip())


def status_cell(item):
    if item.get("status"):
        return status_badge(item["status"]["status"], "small")
    return '<span class="muted">Independent school</span>' if item.get("independent") else '<span class="muted">No full-year return</span>'


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
    if areas is None or data_root is None:
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

def pta_html(item):
    """Each matched charity's returns by school year (the SHARED PTA year rule), with that year's pupils;
    a charity shared with another school counts its share only."""
    html = ""
    for n, c in enumerate(item["pta"][:2]):
        share = pta_share(c)
        dated = [h for h in c.get("history") or [] if h.get("income") is not None and h.get("period_end")]
        dated.sort(key=lambda h: h["period_end"])
        lines = []
        for h in dated[-3:] if n == 0 else dated[-1:]:
            label = pta_year_label(h["period_end"], item["rows"])
            pupils = year_pupils(item["rows"], label)
            spend = h.get("expenditure")
            lines.append((h, label, mf("pta_income", h["income"] * share, pupils, label),
                          mf("pta_spending", spend * share if spend is not None else None, pupils, label)))
        status = pta_history_status(c)
        name = f'<a href="{esc(charity_url(c["charity_number"]))}">{esc(c["name"])}</a> (charity {esc(c["charity_number"])}'
        if status == "historical" and dated:
            until = c.get("last_income_year") or dated[-1]["period_end"][:4]
            html += f'<p>{name}). Had a registered PTA until {esc(until)}.</p>'
        elif lines:
            h, label, income, _ = lines[-1]
            html += f'<p>{name}, {esc(c.get("status") or "")}) raised {income} in {esc(label)}, its latest return (year ending {esc(h["period_end"])}).</p>'
        else:
            html += f'<p>{name}, {esc(c.get("status") or "")}).</p>'
        if (c.get("match") or {}).get("confidence") == "medium":
            html += '<p class="muted small">This charity was matched with lower confidence.</p>'
        if share < 1:
            html += f'<p class="muted small">Shared with {len(c["shared_with"])} other school{"s" if len(c["shared_with"]) > 1 else ""}, so this school\'s figures are its equal share.</p>'
        if n == 0 and len(lines) > 1:
            html += table(["School year", "Income", "Spending"], [[f'{esc(label)} <span class="muted small">(year ending {esc(h["period_end"])})</span>', income, spend]
                                                                   for h, label, income, spend in lines])
    return html + ('<p class="muted small">Matched to this school from the Charity Commission register. Parent associations\' money isn\'t in the school\'s accounts above. '
                   'Money a parents\' association gives the school can also appear in the school\'s own donations income, so the two are never added together. '
                   'Per-pupil figures use the pupils on roll in the school year each return falls in.</p>')


def render_school(item, metadata):
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
    if not st and item.get("independent"):
        body = (f'<h1>{esc(item["name"])}: school finances</h1>' + tags_line(item.get("profile"))
                + '<p class="lead">Independent schools don\'t publish accounts to the DfE, so there are no income, spending or reserve figures to show here.</p>'
                '<p>Many independent schools are charities: their accounts may be on the '
                '<a href="https://register-of-charities.charitycommission.gov.uk/charity-search">Charity Commission register</a>.</p>'
                f'<p><a href="{BASE_SIR}{esc(item["site_path"])}">Admissions and inspections for {esc(item["name"])}</a> · '
                f'<a href="{esc(council["path"])}">All {esc(council["name"])} school finances</a></p>' + sources(compact=True))
        return page(shorten(f"{item['name']} | School Money", 70),
                    shorten(f"{item['name']} is an independent school. Independent schools don't publish accounts to the DfE.", 160),
                    item["path"], body, crumbs, metadata, indexable=False)
    if not st:
        why = ("usually because it opened, converted to an academy or changed trust part-way through the year"
               if item["rows"] else "and no finance return for it is in the DfE's published data")
        body = (f'<h1>{esc(item["name"])}: school finances</h1>' + tags_line(item.get("profile"))
                + f'<p class="lead">No full-year finance return is published for this school yet, {why}.</p><p>Check at source: {check}.</p>' + sources())
        return page(shorten(f"{item['name']} finances | School Money", 70), shorten(f"Finance returns for {item['name']}.", 160),
                    item["path"], body, crumbs, metadata, indexable=False)
    latest, years = item["latest"], item["years"]
    pupils, year = pupils_of_row(latest), year_label(latest)
    basis = reserve_basis(item["rows"])
    points = [{"year": year_label(r), "income": r.get("total_income"), "spend": r.get("total_expenditure"),
               "reserve": reserve_on(r, basis), "pupils": pupils_of_row(r), "balance": r.get("in_year_balance"), "row": r} for r in years]
    span = f"{points[0]['year']} to {points[-1]['year']}" if len(points) > 1 else points[0]["year"]
    kind = "academy (accounts return, September–August)" if item["academy"] else "council-run school (CFR return, April–March)"
    sim = similar_medians(item)
    profile = item.get("profile")
    body = f'<h1>{esc(item["name"])}: school finances</h1>'
    body += (f'<p class="status-line">{status_badge(st["status"], "large")} {REPORT_LINK} {pin("school", item["urn"], item["name"])}</p>'
             f'<p class="lead">{reason_html(item)}</p>')
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
        reserve_tile += f'<span class="sub">{mf("real_terms", real, pupils, year, label="Reserve in 2025-26 prices", src=src)} {esc(deflator.real_label())}</span>'
    body += tiles([
        ("Reserve at year end", reserve_tile),
        ("Last year's balance", mf("in_year_balance", latest.get("in_year_balance"), pupils, year, src=src, signed=True) + '<span class="sub">income minus spending</span>'),
        ("Income", mf("total_income", latest.get("total_income"), pupils, year, src=src, cmp_similar=sim.get("total_income"), drill=income_drill)),
        ("Spending", mf("total_expenditure", latest.get("total_expenditure"), pupils, year, src=src, cmp_similar=sim.get("total_expenditure"), drill=spend_drill)),
        ("Pupils", f'{latest.get("pupils") or 0:,.1f}' + (f'<span class="sub">{change:+.0%} since {esc(points[0]["year"])}</span>' if change is not None else "")),
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
        body += '<p class="timeline">Status by year: ' + " ".join(f'<span class="tl">{esc(t["year"])} {status_badge(t["status"], "small")}</span>' for t in line) + "</p>"
    body += f'<h2>Reserve at the end of each year, {esc(span)}</h2>' + charts.reserve_bars(points)
    body += f'<h2>Income and spending, {esc(span)}</h2>' + charts.income_spend_lines(points)
    def year_figure(key, value, p):
        cls = "suspect" if suspect(p["row"], key) else ""
        return mf(key, value, p["pupils"], p["year"], src=src, cls=cls)

    body += details_table("Show the figures as a table", ["Year", "Income", "Spending", "Reserve", "Pupils"],
                          [[esc(p["year"]), year_figure("total_income", p["income"], p), year_figure("total_expenditure", p["spend"], p),
                            year_figure("revenue_reserve", p["reserve"], p), f'{p["row"]["pupils"]:,.1f}' if p["row"].get("pupils") else "—"] for p in points])
    cmp = compare_rows(item)
    if cmp:
        rank = reserve_rank(item)
        body += '<h2>Compared with similar schools</h2>'
        body += (f'<p>School Money\'s {esc(similar_label(item))} are the {esc(item["phase"].replace("_", "-"))} schools '
                 f'{"in London" if item["london"] else "outside London"} closest in size and in the share of pupils on free school meals '
                 f'that have a full-year return for {esc(year)}, leaving out figures flagged as unusual. ')
        if rank is not None:
            body += f'Its reserve, as a share of income, is higher than {rank:.0%} of them. '
        if sim.get("total_expenditure"):
            body += (f'It spends {mf("total_expenditure", latest.get("total_expenditure"), pupils, year, cmp_similar=sim["total_expenditure"], src=src)} in total; '
                     f'similar schools typically spend {mf("per_pupil", sim["total_expenditure"], None, year, label="Similar schools: median spending per pupil")} per pupil.')
        body += "</p>" + charts.compare_dots(cmp)
        body += details_table("Show the comparison as a table", ["Spending", "This school", "Similar schools (median per pupil)"],
                              [[esc(r["label"]), mf(r["key"], latest.get(r["key"]), pupils, year, cmp_similar=r["median"], src=src),
                                mf("per_pupil", r["median"], None, year)] for r in cmp])
        near = ",".join([item["urn"]] + [o["urn"] for o in item["similar"][:3]])
        body += (f'<p><a class="button" href="/compare/?urns={esc(near)}">Compare side by side with the 3 most similar schools</a></p>'
                 '<details class="tableview"><summary>Which schools are these?</summary><ul class="nearby">'
                 + "".join(f'<li>{school_link(o)} {status_cell(o)}</li>' for o in item["similar"][:6]) + "</ul></details>")
    academy_year = latest.get("source") == "AAR"
    income = [(g, label, latest[k]) for k, g, label in INCOME_LINES if latest.get(k) and not (academy_year and k == "pupil_premium")]
    if income:
        rows = [[esc(label), mf(g, v, pupils, year, src=src)] for g, label, v in income]
        if academy_year:
            rows.append(["Pupil premium", '<span class="muted">not reported in academy accounts</span>'])
        body += f'<h2 id="income">Where the money comes from, {esc(year)}</h2>' + table(["Source", "Amount"], rows)
    if item["pta"]:
        body += "<h2>Money raised by parents</h2>" + pta_html(item)
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


def row_weights(headers, rows):
    """Bytes each row adds to table(headers, rows), and the bytes of the table around them, from
    table()'s own markup (an empty row's tags plus the cells' own bytes)."""
    blank = [""] * len(headers)
    one, two = (len(table(headers, [blank] * n).encode("utf-8")) for n in (1, 2))
    row = two - one
    return [row + sum(len(str(c).encode("utf-8")) for c in cells) for cells in rows], one - row


def chunk_rows(weights, first, later, min_first=0, allowance=0):
    """Cut rows (by their byte weights) into pages: page 1 holds up to `first` bytes of rows, later
    pages `later`; every page holds at least one row. With min_first, page 1 holds at least that many
    rows as long as they fit in `first` + `allowance` bytes. Returns [(start, end)] index ranges."""
    ranges, start, size = [], 0, 0
    for i, w in enumerate(weights):
        budget = first if not ranges else later
        forced = not ranges and i < min_first and size + w <= first + allowance
        if i > start and size + w > budget and not forced:
            ranges.append((start, i))
            start, size = i, 0
        size += w
    ranges.append((start, len(weights)))
    return ranges


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


def paged(path, headers, rows, frame, metadata, *, caption="", indexable=True, extra_head="", target=AREA_PAGE_TARGET,
          first_rows=0):
    """One sortable table over as many pages as its rows need: [(path, html)]. frame(n, total,
    table_html) returns (title, description, crumbs, body) with the table placed in the body.
    Each page's rows are sized against its real frame (shell, intro, outro), so pages stay under
    `target` bytes whenever the frame alone leaves room; every page holds at least one row. With
    first_rows (a council's or constituency's schools), page 1 holds at least that many rows within
    AREA_TABLE_ALLOWANCE bytes more than `target`."""

    def render(n, total, table_html):
        where = page_path(path, n)
        title, description, crumbs, body = frame(n, total, table_html)
        if n > 1:
            crumbs = crumbs + [(f"Page {n}", where)]
        return where, page(title, description, where, body, crumbs, metadata, indexable=indexable, extra_head=extra_head)

    if not rows:
        return [render(1, 1, "")]
    weights, base = row_weights(headers, rows)
    base += len(sortable(headers, [[""] * len(headers)], caption=caption).encode("utf-8")) - len(table(headers, [[""] * len(headers)]).encode("utf-8"))
    room = base + len(pager(path, 999, 999).encode("utf-8")) + 120  # table head, pager and page-number digits
    first = target - len(render(1, 2, "")[1].encode("utf-8")) - room
    later = target - len(render(2, 2, "")[1].encode("utf-8")) - room
    ranges = chunk_rows(weights, first, later, first_rows, AREA_TABLE_ALLOWANCE if first_rows else 0)
    out = []
    for n, (a, b) in enumerate(ranges, 1):
        table_html = sortable(headers, rows[a:b], caption=caption) + pager(path, n, len(ranges))
        out.append(render(n, len(ranges), table_html))
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


def dsg_provisional(dsg):
    """Years la_dsg.json marks provisional (areas.dsg_provisional, else a note that starts with the year and
    says 'provisional', or an explicit 'provisional' list)."""
    rule = getattr(areas, "dsg_provisional", None)
    if rule is not None:
        return set(rule(dsg))
    years = {str(y) for y in (dsg or {}).get("provisional") or []}
    for note in (((dsg or {}).get("source") or {}).get("notes") or []):
        m = re.match(r"(\d{4}-\d{2})\b", str(note))
        if m and "provisional" in str(note).lower():
            years.add(m.group(1))
    return years


def dsg_year(year, provisional=()):
    """'2025-26', or '2025-26 (provisional)' when the source marks the year provisional."""
    return f"{year} (provisional)" if year in provisional else str(year)


def dsg_section(name, values, pupils, flags=(), code=None, heading=None, provisional=()):
    """A council's (or England's) Dedicated Schools Grant balance (all four blocks) by year, total and per
    pupil of that year's schools on the site, each figure with its year. Negative is a deficit (cash terms)."""
    years = sorted(y for y, v in (values or {}).items() if v is not None)
    if not years:
        return ""
    latest = years[-1]
    heading = heading or f"{name}: {DSG_NAME}"
    roll = pupils.get(latest)
    body = f'<h2 id="dsg">{esc(heading)}</h2>'
    body += (f'<p>The Dedicated Schools Grant (DSG) is the money {"councils receive" if code is None else "the council receives"} for schools, '
             'early years, central school services and high-needs (special educational needs) provision. This balance nets all four '
             f'blocks together; most deficits come from high-needs spending. At the end of {esc(dsg_year(latest, provisional))} the '
             f'cumulative {esc(DSG_NAME)} was {mf("dsg_balance", values[latest], roll, latest, signed=True)}'
             + (f' (per pupil of the {roll:,.0f} {esc(DSG_DENOMINATOR.replace("that year", "in " + latest))})' if roll else "")
             + (f' ({", ".join(flags)} programme with the DfE)' if flags else "") + ". A negative figure is a deficit carried forward.</p>")
    rows = [[esc(dsg_year(y, provisional)), mf("dsg_balance", values[y], pupils.get(y), y, signed=True)] for y in reversed(years[-DSG_YEARS:])]
    body += details_table(f"{DSG_NAME} by year", ["Year", "Balance (per pupil of that year's schools)"], rows)
    body += (f'<p class="muted small">Per-pupil figures divide by the {esc(DSG_DENOMINATOR)}; a school whose '
             'return for the year is not yet published counts its previous year\'s roll.'
             + (f' {esc(", ".join(sorted(provisional & set(years))))} figures are provisional: as councils submitted them, before audit.'
                if provisional & set(years) else "") + '</p>')
    if flags:
        body += ('<p class="muted small">Safety valve and delivering better value are DfE programmes for councils with large high-needs deficits: '
                 'the council agrees a plan to bring its Dedicated Schools Grant back into balance over several years.</p>')
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
    description = shorten(f"{len(deficit)} of {len(items)} schools in {name} were in deficit in their latest return ({money(owed)} combined). "
                          "See every school's reserves, spending and trend from DfE returns.", 160)
    dsg = dsg or {}

    def frame(n, total, table_html):
        body = f'<h1>{esc(name)} school finances</h1>'
        if n > 1:
            body += (f'<p class="lead">Every school in {esc(name)} with a full-year return, schools in deficit first: page {n} of {total}. '
                     f'<a href="{esc(council["path"])}">Back to the summary</a>.</p>' + sort_note(total) + table_html + check)
            return (shorten(f"{name} school finances, page {n} | School Money", 70),
                    shorten(f"Page {n} of {total}: every school in {name} with a full-year finance return, schools in deficit first, from DfE returns.", 160), crumbs, body)
        body += f'<p class="status-line">{pin("area", "council-" + council["code"], name)}</p>'
        if items:
            body += (f'<p class="lead"><strong>{len(deficit):,} of {len(items):,}</strong> schools in {esc(name)} were in deficit in their latest return, '
                     f'with combined deficits of <strong>{mf("deficit_total", owed, pupils_of(deficit), year)}</strong>. {counts["heading_for_deficit"]:,} more are heading that way.</p>')
        else:
            body += f'<p class="lead">No school in {esc(name)} has a full-year finance return in the latest data, so there are no statuses to show yet.</p>'
        body += charts.status_bar(counts) + held_note(counts) + f'<p class="report-line">{REPORT_LINK}</p>'
        body += tiles([("Schools in deficit", f"{len(deficit):,}"), ("Combined deficits", mf("deficit_total", owed, pupils_of(deficit), year)),
                       ("Heading for deficit", f'{counts["heading_for_deficit"]:,}'), ("Reserves held by the rest", mf("revenue_reserve", held, pupils_of(rest), year))])
        series = yearly_deficit_series([i["rows"] for i in council["schools"]])
        if len(series) > 1:
            body += f'<h2>Share of {esc(name)}\'s council-run schools in deficit, by year</h2>' + charts.count_bars(series)
            body += '<p class="muted small">Council-run schools only, so years compare like with like; academies report differently and are in the table below.</p>'
        body += dsg_section(name, dsg_for(dsg, council["code"]).get("values"), pupils_by_year(council["schools"]), dsg_flags(dsg, council["code"]),
                            code=council["code"], provisional=dsg_provisional(dsg))
        back = sorted((i for i in items if recovered(i)), key=lambda i: i["name"])
        if back:
            body += ("<h2>Back in the black</h2><p>Schools that were in deficit in an earlier year and are now healthy:</p><ul class=\"nearby\">"
                     + "".join(f"<li>{school_link(i)}</li>" for i in back[:TOP_N]) + "</ul>"
                     + (f'<p class="muted small">And {len(back) - TOP_N:,} more, in the table below.</p>' if len(back) > TOP_N else ""))
        if table_html:
            body += "<h2>Every school, schools in deficit first</h2>" + sort_note(total) + table_html
        body += f'<p class="muted small scope">{esc(SCOPE_NOTE)}</p>'
        members = [i for i in council["schools"] if not i["status"]]
        if members:
            body += ('<p class="muted small">Not shown: ' + ", ".join(school_link(i) for i in members[:TOP_N])
                     + (f" and {len(members) - TOP_N:,} others" if len(members) > TOP_N else "") + ' (in a federation\'s combined return, no full-year return yet, or independent schools, which don\'t publish accounts to the DfE).</p>')
        return title, description, crumbs, body + check

    return paged(council["path"], COUNCIL_HEADERS, council_rows(items), frame, metadata, first_rows=AREA_TABLE_ROWS)


def held_note(counts):
    """A line under a status bar for academies whose trust holds the reserve: counted on their own, never
    as tight or in deficit."""
    n = (counts or {}).get(HELD) or 0
    if not n:
        return ""
    return (f'<p class="muted small">{status_badge(HELD, "small")} {n:,} academ{"y" if n == 1 else "ies"} whose trust holds the '
            f'reserve centrally {"is" if n == 1 else "are"} counted on {"its" if n == 1 else "their"} own: '
            'not as tight and not in deficit.</p>')


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
    body += charts.status_bar(counts) + held_note(counts) + f'<p class="report-line">{REPORT_LINK}</p>'
    body += '<p class="muted small">Latest returns: council-run schools 2025-26 (April–March), academies 2024-25 (September–August). <a href="/about/">How each status is worked out</a>.</p>'
    body += f'<p class="muted small scope">{esc(SCOPE_NOTE)}</p>'
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
    busiest = sorted((c for c in councils if any(i["status"] for i in c["schools"])), key=lambda c: -len(council_summary(c)[1]))[:TOP_N - 4]
    if busiest:
        body += ("<h2>Councils with the most schools in deficit</h2>" + ranked(busiest, COUNCIL_INDEX_HEADERS, council_cells)
                 + '<p><a class="button" href="/council/">Every council</a></p>')
    if dsg and dsg.get("england"):
        body += dsg_section("England", dsg["england"], pupils_by_year(schools), heading=f"{DSG_NAME}, all councils in England",
                            provisional=dsg_provisional(dsg))
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
            body += (f'<p class="lead">Academies of {esc(name)} with a full-year return, academies in deficit first: page {n} of {pages}. '
                     f'<a href="{esc(path)}">Back to the summary</a>.</p>' + sort_note(pages) + table_html + sources())
            return (shorten(f"{name} academy finances, page {n} | School Money", 70),
                    shorten(f"Page {n} of {pages}: {name}'s academies and their financial status from DfE accounts returns.", 160), crumbs, body)
        body += (f'<p class="lead">{len(items):,} academies with a full-year return. Their reserves add up to <strong>{mf("revenue_reserve", total, pupils_of(items), latest_year(items))}</strong>'
                 + (", including each school's share of the trust's central reserve." if shared else ".") + "</p>")
        body += charts.status_bar(counts) + held_note(counts) + f'<p class="report-line">{REPORT_LINK}</p>'
        body += ('<p class="note">A trust can move money between its academies, so a school shown in deficit may be supported by the trust '
                 'as a whole. The trust-wide figure is the better guide to whether the trust is in difficulty.</p>')
        body += "<h2>Academies, those in deficit first</h2>" + sort_note(pages) + table_html + sources()
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
            counts = Counter(i["status"]["status"] for i in assessed)
            body += (f'<p class="lead">{len(deficit):,} of the {len(assessed):,} schools in {esc(name)} with a full-year return were in deficit at their latest return.</p>'
                     + charts.status_bar(counts) + held_note(counts) + f'<p class="report-line">{REPORT_LINK}</p>')
        else:
            body += f'<p class="lead">Page {n} of {total}. <a href="{esc(path)}">Back to the summary</a>.</p>'
        body += sort_note(total) + table_html + sources()
        suffix = f", page {n}" if n > 1 else ""
        description = (f"{len(deficit):,} of the {len(assessed):,} schools in {name} with a full-year return were in deficit at their latest return."
                       if assessed and n == 1 else f"Every school in the {name} constituency with its financial status from DfE returns.")
        return shorten(f"{name} school finances{suffix} | School Money", 70), shorten(description, 160), crumbs, body

    return paged(path, ["School", "Council", "Status"], rows, frame, metadata, first_rows=AREA_TABLE_ROWS)


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
            '<div id="compare-app"><form class="finder" role="search"><label for="cmp-find">Add a school</label>'
            '<input id="cmp-find" type="search" placeholder="School name or town" autocomplete="off" aria-controls="cmp-results">'
            '</form><ul id="cmp-results" class="results" aria-label="Matching schools"></ul>'
            '<p id="cmp-status" class="visually-hidden" role="status" aria-live="polite"></p>'
            '<ul id="cmp-chosen" class="chosen" aria-live="polite"></ul><div id="cmp-out"><p class="muted">Search above, pin schools from their pages, or open any school\'s money page and use “Compare side by side”.</p></div></div>'
            '<noscript><p>The comparison needs JavaScript. Each school\'s own money page works without it.</p></noscript>' + sources())
    crumbs = [("School Money", "/"), ("Compare", "/compare/")]
    return page("Compare school finances | School Money", "Compare up to four English schools' reserves, spending per pupil and finance trends side by side.",
                "/compare/", body, crumbs, metadata)


CORRECTIONS_FALLBACK = (
    '<h2 id="corrections">Corrections</h2>'
    '<p>Every figure here is copied from a published source, so the quickest way to correct one is at source. Compare it '
    'first with the DfE page linked from the school.</p><ul>'
    '<li>A school\'s income, spending, reserve or pupil numbers: ask the school. A council-run school corrects its return '
    'through its council, an academy through its trust, and the DfE republishes the corrected figures.</li>'
    '<li>A parents\' association\'s figures: the charity corrects its annual return with the Charity Commission.</li>'
    '<li>If the DfE\'s figure differs from ours, or a parents\' association is matched to the wrong school, the mistake '
    'is ours and we will put it right at the next update.</li></ul>'
    '<p>A direct address for corrections and added context is coming; until then, please raise it through the school, '
    'its council or trust, or the charity.</p>')
PRIVACY_FALLBACK = (
    '<h2 id="privacy">Privacy</h2>'
    '<p>School Money doesn\'t ask for your name, has no accounts and sets no advertising or tracking cookies.</p><ul>'
    '<li>The schools you pin and the reader you pick are kept in your browser\'s local storage, on your device only. '
    'Clearing this site\'s data in your browser removes them.</li>'
    '<li>If you search by full postcode, your browser sends that postcode straight to api.postcodes.io to find where '
    'it is; School Money doesn\'t receive or keep it.</li>'
    '<li>Like any website, the hosting service may keep standard request logs, such as IP addresses and the pages '
    'requested, to run and protect the site.</li></ul>'
    '<p>The figures on the site are about schools and charities, never about individual people.</p>')


def shell_section(name, fallback):
    """site.corrections_html() / site.privacy_html() (C6) when the shell has them, else the fallback copy."""
    render = getattr(shell, name, None)
    if render is not None:
        try:
            html = render()
        except Exception:  # the about page must never fail on the shell's copy
            html = ""
        if html:
            return html
    return fallback


def boundary_notices():
    """The ONS notices each boundary set carries, as list items for the about page's sources."""
    return "".join(f'<li>{esc(what)} (used for {esc(where)}): {esc(ONS_NOTICE)}. Contains OS data © Crown copyright and '
                   f'database right {esc(year)}.</li>' for what, where, year in BOUNDARIES)


def render_about(metadata, dsg=None, ifs=None):
    ifs = ifs or {}
    labels = [
        ("in_deficit", "The school's revenue reserve was below zero at the end of its latest full year: over the years it has spent more than it received."),
        ("heading_for_deficit", "Still above zero, but the school has spent more than it received for at least two years running and, at its average overspend over the last three years, its reserve would run out within about three years."),
        ("tight", "A reserve under 3% of a year's income: little room for an unexpected cost."),
        ("healthy", "A reserve between 3% of income and the large-reserve level."),
        ("large_reserves", "A reserve of 8% of a year's income or more (5% for secondary schools), the levels the DfE once called excessive and many councils still use to claw back surpluses."),
        (HELD, "An academy whose trust holds its schools' reserves centrally, so the academy's own reserve is zero. It isn't judged tight or in deficit on that zero: the trust-wide position is the better guide, and these academies are counted on their own in every area total."),
    ]
    body = '<h1>How the school money figures work</h1>'
    body += "<h2>The statuses</h2><ul class=\"defs\">" + "".join(f"<li>{status_badge(k)} {esc(v)}</li>" for k, v in labels) + "</ul>"
    body += """<h2 id="method">What a deficit means</h2>
<p>A school deficit isn't a bank loan. It means the school has spent more over the years than it received, so its revenue reserve, the money it carries from year to year, is below zero.</p>
<p>For a <strong>council-run school</strong>, the council covers the gap from its schools budget. It usually agrees a recovery plan, often called a licensed deficit, with a date by which the school must be back in balance, and can step in if the plan isn't kept.</p>
<p>An <strong>academy</strong> is part of a trust. A trust can move money between its schools, so one academy in deficit may be propped up by the others. Where the DfE publishes it, an academy's reserve here includes its per-pupil share of the trust's central reserve, and each trust has its own page.</p>
<h2>Where the numbers come from</h2>
<p>Every school in England reports its income, spending and balances to the Department for Education each year. Council-run schools use the Consistent Financial Reporting (CFR) return for April to March; academies use the Academy Accounts Return for September to August. The DfE publishes both in its Financial Benchmarking and Insights Tool, and every school page here links to the matching DfE page so you can check the figures.</p>
<p>Figures are shown as published, in cash terms, with the per-pupil figure beside every total using that same year's pupil numbers. Part-year returns (a school that opened, converted or changed trust during the year) are left out of statuses and trends. When a school became an academy, its earlier years come from its council-run return under its old DfE number, linked through Get Information about Schools. Where a year's pupil count doesn't match the money, as when a federation's lead school reports the whole federation's money against its own pupils, that year's per-pupil figures are left out.</p>"""
    body += f"<p>{esc(SCOPE_NOTE)}</p>"
    body += """<h2 id="real-terms">Real terms</h2>
<p>Where a figure is shown "in 2025-26 prices" it has been adjusted with the HM Treasury GDP deflator (October 2026 edition), the whole-economy measure the Treasury and the Institute for Fiscal Studies use for public spending. Academy years (September to August) use a month-weighted average of the two financial years they span. It reflects general inflation, not school-specific costs such as teacher pay or energy.</p>
<h2 id="similar">Similar schools</h2>
<p>School Money's similar schools, not the DfE's: for each school we take the 30 schools of the same phase, in London or outside it to match, that are closest in pupil numbers and in the share of pupils on free school meals. The comparison is for one year, the school's latest full year, and uses those similar schools with a full-year return for that year; pages say how many and which year. Figures flagged as unusual are left out of every median. Spending per pupil is compared with the middle half of that group.</p>
<h2 id="dsg">Councils' Dedicated Schools Grant balances</h2>
<p>Each council page shows the council's Dedicated Schools Grant balance (all four blocks) by year from the DfE's section 251 outturn: the cumulative surplus or deficit on the money it receives for schools, early years, central school services and high-needs provision, all four blocks together, in cash terms. It covers more than high needs, though most deficits come from high-needs spending. Per-pupil figures divide by the pupils at the council's schools on this site that year. The newest year is provisional where the DfE says so: as councils submitted it, before audit. Councils in the DfE's safety valve or delivering better value programmes have agreed plans to recover large deficits.</p>
<h2>Parents' associations</h2>
<p>Where a PTA or friends' charity can be matched to a school in the Charity Commission register, its income is shown. That money is separate from the school's own accounts. Where no registered parents' association was found, a school may still have one: charities with an income of <span class="mf" data-mf="pta_income" data-v="5000">£5,000</span> or less need not register, and some can't be matched with confidence.</p>"""
    body += shell_section("corrections_html", CORRECTIONS_FALLBACK)
    body += shell_section("privacy_html", PRIVACY_FALLBACK)
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
        dsg_item = f'<li>{f"<a href={json.dumps(url)}>{esc(label)}</a>" if url else esc(label)} (councils\' Dedicated Schools Grant balances) — Open Government Licence v3.0</li>'
    body += ('<h2 id="sources">Sources</h2><ul>'
             f'<li><a href="{FBIT_SOURCES}">DfE Financial Benchmarking and Insights Tool</a>: CFR and Academy Accounts Return workbooks, 2018-19 onwards</li>'
             '<li><a href="https://get-information-schools.service.gov.uk/">Get Information about Schools</a>: the school register and academy conversions</li>'
             f'<li><a href="{CHARITY_REGISTER}">Charity Commission register</a>: parents\' associations</li>'
             '<li><a href="https://www.gov.uk/government/collections/gdp-deflators-at-market-prices-and-money-gdp">HM Treasury GDP deflators</a>, October 2026</li>'
             + dsg_item + boundary_notices()
             + '<li>Postcode lookups: <a href="https://postcodes.io/">postcodes.io</a>, from ONS and Ordnance Survey open data. Contains OS data © Crown '
             'copyright and database right 2025. Contains Royal Mail data © Royal Mail copyright and database right 2025. Contains National '
             'Statistics data © Crown copyright and database right 2025.</li></ul>')
    body += (f'<h2 id="licences">Licences</h2><p>The DfE, Get Information about Schools, Charity Commission, ONS and HM Treasury data above are published under the '
             f'<a href="{OGL}">Open Government Licence v3.0</a>. Our derived figures and pages may be reused under the same terms with a link back to School Money. '
             'IFS material is quoted with attribution to the IFS and the Nuffield Foundation.</p>')
    body += sources(f'<li><a href="{CHARITY_REGISTER}">Charity Commission register</a> — Open Government Licence v3.0</li>')
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
    basis = reserve_basis(item["rows"])
    years = [{"y": year_label(r), "income": rounded(r.get("total_income")), "spend": rounded(r.get("total_expenditure")),
              "balance": rounded(r.get("in_year_balance")), "reserve": rounded(reserve_on(r, basis)), "pupils": r.get("pupils"),
              "status": statuses.get(year_label(r))} for r in item["years"]]
    pp = {k: per_pupil(latest, k) for k, _ in COMPARE_KEYS + [("total_expenditure", ""), ("total_income", "")]}
    pupils = pupils_of_row(latest)  # None when suspect: every per-pupil figure below is left out with it
    out = {"urn": item["urn"], "name": item["name"], "path": item["path"],
           "council": {"code": council["code"], "name": council["name"], "path": council["path"]},
           "status": st["status"], "label": st["label"], "reason": st["reason"], "year": year_label(latest),
           "academy": item["academy"], "trust": item["trust"], "trust_path": item.get("trust_path"), "pupils": latest.get("pupils"),
           "income": rounded(latest.get("total_income")), "income_pp": rounded(per_pupil(latest, "total_income")),
           "spend": rounded(latest.get("total_expenditure")), "spend_pp": rounded(per_pupil(latest, "total_expenditure")),
           "reserve": rounded(st["reserve"]), "reserve_pp": rounded(st["reserve"] / pupils) if pupils else None, "share": st["reserve_share"],
           "balance": rounded(latest.get("in_year_balance")), "balance_pp": rounded(per_pupil(latest, "in_year_balance")),
           "streak": st["deficit_streak"], "pupils_change": st["pupils_change"], "years": years, "reserve_basis": basis,
           "pp": {k: round(v) for k, v in pp.items() if v is not None}, "similar": {k: round(v) for k, v in similar_medians(item).items()},
           "similar_meta": similar_meta(item),
           "income_lines": {g: round(latest[k]) for k, g, _ in INCOME_LINES if latest.get(k) is not None},
           "lines": {k: v for k, v in (latest.get("lines") or {}).items() if v is not None},
           "pta": [{"charity_number": c.get("charity_number"), "name": c.get("name"), "status": c.get("status"),
                    "latest_income": c.get("latest_income"), "history": c.get("history") or []} for c in item["pta"]],
           "check": fbit_school(item)}
    if profile:
        out.update({"tags": profile.get("tags"), "band": profile.get("band"), "area": profile.get("area")})
    if line:
        out["timeline"] = line
    if item.get("nearby"):
        out["nearby"] = item["nearby"]
    return out


def area_stats(items, year, source=None):
    """Reduced yearly summary for a set of schools when areas.py is absent: None where fewer than 5.
    source "CFR" or "AAR" keeps only that year's returns of that kind, whatever the school is now.
    deficit_total and deficit_pp are negative, as in areas.py."""
    rows = [(i, r) for i in items for r in i["years"] if year_label(r) == year and source in (None, r.get("source"))]
    if len(rows) < 5:
        return None
    reserves = [(reserve_of(r), r.get("pupils")) for _, r in rows]
    deficits = [(v, p) for v, p in reserves if v is not None and v < 0]
    deficit_pupils = sum(p for _, p in deficits if p)
    deficit_total = sum(v for v, _ in deficits)

    def med(key):
        vals = [clean_pp(r, key) for _, r in rows]
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
        # Each return counts under its own source: a converted academy's earlier CFR years are council-run.
        by_year[y] = {"all": area_stats(items, y), "council-run": area_stats(items, y, "CFR"), "academy": area_stats(items, y, "AAR")}
    return {"name": name, "pupils_by_year": dict(pupils_by_year(items)),
            "schools_by_year": {y: sum(1 for i in items for r in i["years"] if year_label(r) == y) for y in years},
            "by_year": by_year, "dsg": {}, "statuses_latest": dict(Counter(i["status"]["status"] for i in items if i["status"]))}


def build_area_doc(schools, pta, dsg, data_root):
    """(areas.build_areas over the model's schools, error) — (None, None) without areas.py, (None, message)
    when it fails, so the build falls back to the reduced statistics and says why."""
    if areas is None:
        return None, None
    try:
        registers = [dict(i["school"], la_code=i["council"]["code"]) for i in schools]
        return areas.build_areas({i["urn"]: i["rows"] for i in schools if i["rows"]}, registers, pta, dsg, data_root), None
    except Exception as exc:  # B3's module reads optional files; the site still builds on reduced statistics
        return None, f"{type(exc).__name__}: {exc}"


def area_documents(councils, schools, built, dsg):
    """{area id: document} for /data/a/<id>.json, from the areas document when there is one."""
    regions = defaultdict(list)
    for c in councils:
        if c.get("region"):
            regions[c["region"]].append(c)
    constituencies = defaultdict(list)
    for i in schools:
        if i["constituency"]:
            constituencies[i["constituency"]].append(i)
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
                a["dsg"] = dsg_entries(dsg_for(dsg, ident.removeprefix("council-")).get("values"), pupils_by_year(fallback_items), dsg)
            elif kind == "england":
                a["dsg"] = dsg_entries(dsg.get("england"), pupils_by_year(fallback_items), dsg)
        docs[ident] = {"id": ident, "type": kind, "name": name, "path": path, **a}

    put("england", "england", "England", "/", schools)
    for name, cs in regions.items():
        put(f"region-{slug(name)}", "region", name, f"/areas/{slug(name)}/", [i for c in cs for i in c["schools"]])
    for c in councils:
        put(f"council-{c['code']}", "council", c["name"], c["path"], c["schools"])
    for name, items in constituencies.items():
        put(f"constituency-{items[0]['constituency_path'].strip('/').split('/')[-1]}", "constituency", name, items[0]["constituency_path"], items)
    return docs


def dsg_entries(values, pupils, dsg):
    """{year: {'balance', 'per_pupil', 'pupils' (the denominator), 'provisional' when the source says so}}."""
    provisional, out = dsg_provisional(dsg), {}
    for y, v in (values or {}).items():
        if v is None:
            continue
        roll = pupils.get(y)
        out[y] = {"balance": v, "per_pupil": round(v / roll) if roll else None, "pupils": roll or None}
        if y in provisional:
            out[y]["provisional"] = True
    return out


def areas_for_extensions(built, docs):
    """The areas document for write_pages(env): areas.build_areas's, else one assembled from the reduced docs."""
    if built:
        return built
    out = {"england": docs.get("england"), "regions": {}, "councils": {}, "constituencies": {}}
    for ident, doc in docs.items():
        if doc["type"] == "region":
            out["regions"][doc["name"]] = doc
        elif doc["type"] == "council":
            out["councils"][ident.removeprefix("council-")] = doc
        elif doc["type"] == "constituency":
            out["constituencies"][ident.removeprefix("constituency-")] = doc
    return out


# ----------------------------------------------------------------- school dashboard context

def real_label():
    if deflator is None:
        return None
    try:
        return deflator.real_label()
    except Exception:
        return None


def sen_share_q3(schools):
    """Upper quartile of the SEN share of income in assessed schools' latest full years, or None."""
    values = sorted(v for v in (sen_share(i["latest"]) for i in schools if i["status"]) if v is not None)
    return statistics.quantiles(values, n=4)[2] if len(values) >= 4 else None


def similar_ctx(item):
    """ctx 'similar' and 'similar_series': medians of similar schools' £ per pupil, from SIMILAR_MIN
    schools with a value, leaving out values flagged suspect. 'similar' is the benchmark for the school's
    own latest year (similar_benchmark, the numbers /data/s carries too); 'similar_series' is each year's."""
    bench = similar_benchmark(item)
    keys = [k for k, _, _ in (getattr(series, "METRICS", None) or METRICS)]
    by_year = defaultdict(lambda: defaultdict(list))
    for o in item["similar"]:
        for r in {year_label(r): r for r in o["years"]}.values():  # one return per year, the later, as peer_row
            for k in SIMILAR_SERIES:
                v = clean_pp(r, k)
                if v is not None:
                    by_year[k][year_label(r)].append(v)
    latest = {k: round(bench["medians"][k]) for k in keys if k in bench["medians"]}
    trend = {k: {y: round(statistics.median(v)) for y, v in sorted(by_year[k].items()) if len(v) >= SIMILAR_MIN} for k in SIMILAR_SERIES}
    return latest, trend


def school_ctx(item, shared):
    """The SHARED 'CTX CONTRACT' for school_page.render."""
    similar, similar_series = similar_ctx(item)
    doc = shared.get("areas") or {}
    ctx = {"series": school_series(item, shared.get("sen_q3")), "profile": item.get("profile"), "timeline": timeline_of(item) or [],
           "similar": similar, "similar_series": similar_series, "similar_meta": similar_meta(item),
           "council": (doc.get("councils") or {}).get(item["council"]["code"]) if doc else None,
           "england": doc.get("england") if doc else None, "pta_national": doc.get("pta") if doc else None,
           "ifs": shared.get("ifs") or {}, "real_label": real_label(), "check_url": fbit_school(item),
           "sir_url": _shell().BASE_SIR + item["site_path"]}
    if (item.get("nearby") or {}).get("schools"):
        ctx["nearby"] = item["nearby"]
    return ctx


def school_crumbs(item):
    council = item["council"]
    return [("School Money", "/"), (council["name"], council["path"]), (item["name"], item["path"])]


def page_bytes(html):
    """A page's size as write() will measure it, with every /assets/ link's ?v=<10 hex> counted."""
    return len(html.encode("utf-8")) + len("?v=0123456789") * len(ASSET_REF.findall(html))


def school_page_html(item, metadata, shared):
    """(html, indexable, SERIES or None) for one school: the school dashboard when school_page.py and
    series.py import and the school has a status, else render_school. A page that would reach
    SCHOOL_PAGE_BUDGET takes the render's first 'lighter' body that fits (a lighter nearby section,
    then none); if none fits, write() reports it."""
    if school_page is not None and series is not None and item["status"]:
        ctx = school_ctx(item, shared)
        result = school_page.render(item, ctx)
        indexable = bool(result.get("indexable", True))
        for body in [result["body"]] + list(result.get("lighter") or []):
            html = page(result["title"], result["description"], item["path"], body, school_crumbs(item), metadata,
                        indexable=indexable, extra_head=getattr(school_page, "EXTRA_HEAD", SCHOOL_HEAD))
            if page_bytes(html) < SCHOOL_PAGE_BUDGET:
                break
        return html, indexable, ctx["series"]
    return render_school(item, metadata), bool(item["status"]), None


# ----------------------------------------------------------------- area dashboards

def area_head():
    return getattr(area_pages, "EXTRA_HEAD", AREA_HEAD)


def area_ctx(shared, councils, schools, trust_path):
    """The SHARED area renderers' ctx: IFS, DSG, real-terms caption, the areas document and every page path."""
    doc = shared["areas"] or {}
    by_name = {i["constituency"]: i["constituency_path"] for i in schools if i["constituency"]}
    constituency = {code: by_name[a["name"]] for code, a in (doc.get("constituencies") or {}).items() if a.get("name") in by_name}
    regions = {c["region"] for c in councils if c.get("region")}
    return {"ifs": shared.get("ifs") or {}, "dsg": shared.get("dsg") or {}, "real_label": real_label(), "areas": doc,
            "paths": {"council": {c["code"]: c["path"] for c in councils}, "region": {r: f"/areas/{slug(r)}/" for r in regions},
                      "constituency": constituency, "trust": dict(trust_path)}}


def area_result_pages(path, crumbs, result, metadata, first_rows=0):
    """An area renderer's result as [(path, html)]: page 1 is its intro, table and outro; pages 2+
    carry the title, a link back to the summary, the table and the pager. first_rows: rows page 1
    always holds (a council's or constituency's schools, see AREA_TABLE_ROWS)."""
    title, description = result["title"], result["description"]
    heading = title.split(" | ")[0]
    tbl = result.get("table") or None
    filters = (tbl or {}).get("filters") or ""
    indexable = bool(result.get("indexable", True))

    def frame(n, total, table_html):
        if n == 1:
            return title, description, crumbs, result.get("intro", "") + (filters + table_html if table_html else "") + result.get("outro", "")
        body = (f'<h1>{esc(heading)}</h1><p class="lead">Page {n} of {total}. <a href="{esc(path)}">Back to the summary</a>.</p>'
                + filters + sort_note(total) + table_html)
        return shorten(f"{heading}, page {n} | School Money", 70), shorten(f"Page {n} of {total}. {description}", 160), crumbs, body

    rows = (tbl or {}).get("rows") or []
    return paged(path, (tbl or {}).get("headers") or [], rows, frame, metadata, caption=(tbl or {}).get("caption") or "",
                 indexable=indexable, extra_head=area_head(), first_rows=first_rows)


def region_index(regions_doc, metadata):
    """/areas/: every region with its schools' latest statuses, linking to its dashboard."""
    rows = []
    for name in sorted(regions_doc):
        counts = (regions_doc[name] or {}).get("statuses_latest") or {}
        total, deficit = sum(counts.values()), counts.get("in_deficit", 0)
        rows.append([f'<a href="/areas/{esc(slug(name))}/" data-preview="area:region-{esc(slug(name))}">{esc(name)}</a>',
                     f'<span data-sort="{total}">{total:,}</span>', f'<span data-sort="{deficit}">{deficit:,}</span>',
                     f'<span data-sort="{deficit / total if total else 0:.4f}">{pct(deficit / total) if total else "—"}</span>'])
    crumbs = [("School Money", "/"), ("Areas", "/areas/")]
    body = ('<h1>School finances by region</h1><p class="lead">Each English region\'s schools: how many have a full-year return, how many are in deficit, '
            'and the trend in funding and spending per pupil on each region\'s page.</p>'
            + (sort_note(1) + sortable(["Region", "Schools with a return", "In deficit", "% in deficit"], rows) if rows else "<p>No region has a school with a return yet.</p>")
            + '<p><a href="/england/">England as a whole</a> · <a href="/council/">Every council</a> · <a href="/constituency/">Constituencies</a></p>' + sources())
    return page("School finances by region | School Money", "School finances in each English region: schools in deficit and money per pupil, from DfE returns.",
                "/areas/", body, crumbs, metadata, extra_head=area_head())


def render_constituency_index(constituencies, metadata):
    """/constituency/: every parliamentary constituency with a school on the site, A to Z."""
    rows = []
    for (name, path), items in sorted(constituencies.items(), key=lambda kv: kv[0][0].casefold()):
        assessed = [i for i in items if i["status"]]
        deficit = sum(i["status"]["status"] == "in_deficit" for i in assessed)
        rows.append([f'<a href="{esc(path)}">{esc(name)}</a>', f'<span data-sort="{len(assessed)}">{len(assessed):,}</span>',
                     f'<span data-sort="{deficit}">{deficit:,}</span>'])
    crumbs = [("School Money", "/"), ("Constituencies", "/constituency/")]

    def frame(n, total, table_html):
        body = ('<h1>School finances by constituency</h1><p class="lead">Every parliamentary constituency in England with the number of its schools '
                'that have a full-year return and how many of them are in deficit.</p>'
                + (sort_note(total) + table_html if table_html else "<p>No constituency has a school on the site yet.</p>") + sources())
        suffix = f", page {n}" if n > 1 else ""
        return (shorten(f"School finances by constituency{suffix} | School Money", 70),
                shorten(f"Constituencies in England{suffix}: schools with a finance return and how many are in deficit, from DfE returns.", 160), crumbs, body)

    return paged("/constituency/", ["Constituency", "Schools with a return", "In deficit"], rows, frame, metadata)


def render_home(schools, metadata, england):
    """'/' with the area dashboards: search, the five audience entry points and England's headline."""
    assessed = [i for i in schools if i["status"]]
    body = ('<h1>School money: how England\'s schools are funded, what they spend and what they hold in reserve</h1>'
            f'<p class="lead">Published DfE figures for {len(assessed):,} state schools, explained for the people who care about them. '
            'Figures are a starting point for a conversation with a school, not a verdict on it.</p>'
            '<form class="finder" action="/search/" role="search"><label for="find">Find a school</label>'
            '<input id="find" name="q" type="search" placeholder="School name, town or postcode" autocomplete="off"><button type="submit">Find</button></form>'
            '<p class="home-video"><a class="watch" href="/video/"><span aria-hidden="true">▶</span> Your school in 30 seconds</a> '
            'A short video of any school\'s money, and its PTFA\'s, to watch and share.</p>'
            '<h2>Start here</h2><ul class="audiences">'
            + "".join(f'<li><a href="{esc(p)}"><strong>{esc(who)}</strong></a> {esc(why)}</li>' for who, p, why in AUDIENCE_LINKS) + "</ul>"
            '<h2>England at a glance</h2>' + (area_pages.headline(england) if england else "")
            + '<p><a class="button" href="/england/">England\'s schools in detail</a></p>'
            '<p><a href="/areas/">Regions</a> · <a href="/council/">Councils</a> · <a href="/constituency/">Constituencies</a> · <a href="/trust/">Academy trusts</a> · '
            '<a href="/debts/">Debts</a> · <a href="/ptfa/">PTFA</a> · <a href="/map/">Map</a> · <a href="/compare/">Compare schools</a> · <a href="/about/">How it works</a></p>'
            + sources())
    description = shorten(f"How {len(assessed):,} English state schools are funded, what they spend and their reserves, from DfE returns, for parents, governors and PTFAs.", 160)
    return page("School finances in England | School Money", description, "/", body, [("School Money", "/")], metadata, extra_head=area_head())


def run_extensions(env, skipped):
    """Each EXTENSIONS module's write_pages(env), in order: [(path, indexable)]. A module that cannot be
    imported is skipped (and named in `skipped`); any other error fails the build."""
    written = []
    for name in EXTENSIONS:
        try:
            mod = importlib.import_module(f"pipeline.money.{name}")
        except ImportError as exc:
            skipped.append(f"{name} ({exc})")
            continue
        for path, indexable in mod.write_pages(env) or []:
            written.append((path, bool(indexable)))
    return written


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


# "/assets/app.js" in a page, quoted: versioned at write time so a deploy's pages always fetch that deploy's assets.
ASSET_REF = re.compile(r'(["\'])/assets/([A-Za-z0-9_.-]+)\1')


def asset_versions(files):
    """{file name: first 10 hex of its SHA-1}: the ?v= each asset gets, changing only when the file does."""
    return {Path(f).name: hashlib.sha1(Path(f).read_bytes()).hexdigest()[:10] for f in files}


def versioned(html, versions):
    """Add ?v=<hash> to every quoted /assets/<name> the page links. Asset URLs were unversioned, so after a deploy a
    browser could pair new HTML with yesterday's app.js (Cache-Control lets it serve stale while it revalidates)."""
    return ASSET_REF.sub(lambda m: (f'{m.group(1)}/assets/{m.group(2)}?v={versions[m.group(2)]}{m.group(1)}'
                                    if m.group(2) in versions else m.group(0)), html)


POSTCODE_NEAREST = 30  # schools listed per postcode district, nearest to the district's centre first


def outcode(postcode):
    """'N16 0NX' -> 'N16'; None when the register has no usable postcode."""
    text = re.sub(r"\s+", "", str(postcode or "")).upper()
    m = re.fullmatch(r"([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})", text)
    return m.group(1) if m else None


def _miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(min(1.0, a)))


def postcode_index(schools, nearest=POSTCODE_NEAREST):
    """{district: {"district", "lat", "lon", "schools": [...]}} for /data/postcodes/<district>.json.

    A district's centre is the mean position of its own schools; its list is the `nearest` schools to that centre from
    anywhere, so a district on a council border still finds the school over the road. Only state-funded schools are
    listed (independents publish no accounts here, and in N16 they filled two-thirds of the list). Each row carries
    lat/lon so the page can re-sort by distance from the exact postcode when it can look that up."""
    located = [i for i in schools if isinstance(i.get("lat"), (int, float)) and isinstance(i.get("lon"), (int, float))]
    listed = [i for i in located if not i.get("independent")]
    groups = defaultdict(list)
    for i in located:
        district = outcode(i["school"].get("postcode"))
        if district:
            groups[district].append(i)
    out = {}
    for district, members in groups.items():
        lat = sum(i["lat"] for i in members) / len(members)
        lon = sum(i["lon"] for i in members) / len(members)
        # A box first (a degree of latitude is ~69 miles), widening until it holds enough schools.
        for box in (0.05, 0.12, 0.3, 1.0, 180.0):
            near = [i for i in listed if abs(i["lat"] - lat) <= box and abs(i["lon"] - lon) <= box * 1.6]
            if len(near) >= nearest:
                break
        ranked = sorted(near, key=lambda i: (_miles(lat, lon, i["lat"], i["lon"]), i["name"]))[:nearest]
        out[district] = {"district": district, "lat": round(lat, 5), "lon": round(lon, 5), "schools": [
            {"t": "school", "id": i["urn"], "name": i["name"],
             "sub": " ".join(x for x in (i["school"].get("town"), i["school"].get("postcode")) if x),
             "status": i["status"]["status"] if i["status"] else None, "p": i["path"],
             "lat": round(i["lat"], 5), "lon": round(i["lon"], 5),
             "mi": round(_miles(lat, lon, i["lat"], i["lon"]), 2)} for i in ranked]}
    return out


# ----------------------------------------------------------------- nearby schools

NEARBY_N = 8           # neighbours listed in a school's 'nearby' block, nearest first
NEARBY_MAX_MI = 30     # further than this is not "nearby", whatever the phase
NEARBY_MIN = 3         # values needed before a nearby median or rank is given
NEARBY_PTA_YEARS = 2   # a PTA return more school years than this from the comparison year is left out
NEARBY_CELL = (0.02, 0.032)  # grid cell in degrees of latitude and longitude, about 1.4 by 1.4 miles in England
NEARBY_PP = (("spend_pp", "total_expenditure"), ("income_pp", "total_income"), ("gov_pp", "grant_funding_government"))
NEARBY_MEDIANS = ("spend_pp", "income_pp", "gov_pp", "reserve_pp", "pta_pp")
NEARBY_RANKS = ("spend_pp", "reserve_pp", "pta_pp")
PHASE_LABELS = {"primary": "Primary", "secondary": "Secondary", "special": "Special", "all_through": "All-through",
                "nursery": "Nursery", "alternative_provision": "Alternative provision", "post16": "Post-16", "16_plus": "Post-16"}


def phase_label(phase):
    """The display label of a phase group ('all_through' -> 'All-through'); anything unlisted is 'Other'."""
    return PHASE_LABELS.get(str(phase or "").lower().replace("-", "_").replace(" ", "_"), "Other")


def _located(item):
    return all(isinstance(item.get(k), (int, float)) and not isinstance(item.get(k), bool) for k in ("lat", "lon"))


def _cell(lat, lon):
    return int(math.floor(lat / NEARBY_CELL[0])), int(math.floor(lon / NEARBY_CELL[1]))


def _bounds(grid):
    ys, xs = [c[0] for c in grid], [c[1] for c in grid]
    return min(ys), max(ys), min(xs), max(xs)


def _nearest(grid, item, n=NEARBY_N, max_mi=NEARBY_MAX_MI, bounds=None):
    """[(miles, other)] for the n nearest grid schools to item within max_mi, nearest first, item itself left out.
    Rings of grid cells are searched outwards until the n-th distance is inside the searched block: anything beyond
    ring r is at least r cells away, so nothing nearer can be missed. The search also stops once it covers the grid."""
    lat, lon = item["lat"], item["lon"]
    cy, cx = _cell(lat, lon)
    y0, y1, x0, x1 = bounds or _bounds(grid)
    cover = max(cy - y0, y1 - cy, cx - x0, x1 - cx)
    found, r = [], 0
    while True:
        cells = [(cy, cx)] if r == 0 else ([(cy + dy, cx + d) for d in range(-r, r + 1) for dy in (-r, r)]
                                           + [(cy + d, cx + dx) for d in range(-r + 1, r) for dx in (-r, r)])
        for c in cells:
            for o in grid.get(c, ()):
                if o is not item and o["urn"] != item["urn"]:
                    found.append((_miles(lat, lon, o["lat"], o["lon"]), o["name"], o["urn"], o))
        lat_edge = min(89.0, abs(lat) + (r + 1) * NEARBY_CELL[0])
        reach = r * 69.09 * min(NEARBY_CELL[0], NEARBY_CELL[1] * math.cos(math.radians(lat_edge)))
        if len(found) >= n:
            found.sort(key=lambda t: t[:3])
            if found[n - 1][0] <= reach:
                break
        if reach > max_mi or r >= cover:
            break
        r += 1
    found.sort(key=lambda t: t[:3])
    return [(mi, o) for mi, _, _, o in found[:n] if mi <= max_mi]


def nearby_year(item, neighbours, facts=None):
    """SHARED YEAR RULE: the newest of this school's full-year labels that at least half (rounded up) of its listed
    neighbours also have a full-year return for; else its latest full year."""
    facts = facts or _NearbyFacts()
    need = math.ceil(len(neighbours) / 2)
    have = [facts.returns(o) for o in neighbours]
    for label in sorted(facts.returns(item), reverse=True):
        if sum(label in h for h in have) >= need:
            return label
    return year_label(item["latest"])


def _value(row, key):
    """A row's figure for key, or None when it is missing, not a number or flagged suspect."""
    value = metric_value(row, key)
    if suspect(row, key) or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _pupils(row):
    """A row's pupils on roll, or None when missing, not a positive number or flagged suspect."""
    pupils = _value(row, "pupils")
    return pupils if pupils is not None and pupils > 0 else None


class _NearbyFacts:
    """Each school's figures for a comparison year, worked out once however many neighbour lists it is in."""

    def __init__(self):
        self.values, self.statuses, self.ptas, self.by_label, self.bases = {}, {}, {}, {}, {}

    def basis(self, item):
        """The school's one reserve basis (C3), so a nearby reserve never mixes bases across schools' years."""
        if item["urn"] not in self.bases:
            self.bases[item["urn"]] = reserve_basis(item["rows"])
        return self.bases[item["urn"]]

    def returns(self, item):
        """{label: the school's full-year return for it (the later one if two share a label)}."""
        if item["urn"] not in self.by_label:
            self.by_label[item["urn"]] = {year_label(r): r for r in item["years"]}
        return self.by_label[item["urn"]]

    def row_for(self, item, label):
        return self.returns(item).get(label)

    def pupils(self, item, label):
        """Pupils on roll in label from the return the year's other figures come from (the later of two full-year
        returns sharing a label, as after a conversion), else the school's latest other return for it; None when
        that count is missing or flagged suspect."""
        r = self.row_for(item, label)
        if r is None:
            r = max((x for x in item["rows"] if x.get("period_end") and year_label(x) == label),
                    key=lambda x: x["period_end"], default=None)
        return _pupils(r)

    def status(self, item, label):
        """The school's status for label, judged as the timeline does: on the returns up to that year's end."""
        key = (item["urn"], label)
        if key not in self.statuses:
            r = self.row_for(item, label)
            if r is None:
                verdict = None
            elif r is item["latest"]:
                verdict = item["status"]
            else:
                verdict = health.assess([x for x in item["rows"] if x.get("period_end") and x["period_end"] <= r["period_end"]])
            self.statuses[key] = (verdict or {}).get("status")
        return self.statuses[key]

    def pta_years(self, item):
        """{school year: (PTA income, lower confidence?)}: shared charities split equally, as local_series does."""
        if item["urn"] not in self.ptas:
            by_year = {}
            for c in item.get("pta") or []:
                share, medium = pta_share(c), (c.get("match") or {}).get("confidence") == "medium"
                for h in c.get("history") or []:
                    income = h.get("income")
                    if isinstance(income, bool) or not isinstance(income, (int, float)) or not h.get("period_end"):
                        continue
                    label = pta_year_label(h["period_end"], item["rows"]) if item["rows"] else local_pta_year(h["period_end"], "CFR")
                    total, low = by_year.get(label, (0, False))
                    by_year[label] = (total + income * share, low or medium)
            self.ptas[item["urn"]] = by_year
        return self.ptas[item["urn"]]

    def pta(self, item, label):
        """(pta_pp, pta_year, lower confidence?, PTA income) for the PTA school year nearest label, or None."""
        start = int(label[:4])
        years = [(abs(int(y[:4]) - start), -int(y[:4]), y) for y in self.pta_years(item) if y[:4].isdigit()]
        for gap, _, y in sorted(years):
            if gap > NEARBY_PTA_YEARS:
                break
            pupils = self.pupils(item, y)
            if pupils:
                income, low = self.pta_years(item)[y]
                return round(income / pupils), y, low, round(income)
        return None

    def facts(self, item, label):
        """(row fields without urn, name, path and distance; lines per pupil) for item in label."""
        key = (item["urn"], label)
        if key in self.values:
            return self.values[key]
        r = self.row_for(item, label)
        out, lines = {}, {}
        if ((r or item["latest"] or {}).get("source")) == "AAR":
            out["academy"] = True
        status = self.status(item, label)
        if status:
            out["status"] = status
        pupils = _pupils(r)
        if pupils is not None:
            out["pupils"] = round(pupils, 1)
            for field, k in NEARBY_PP:
                v = _value(r, k)
                if v is not None:
                    out[field] = round(v / pupils)
            basis = self.basis(item)
            reserve = reserve_on(r, basis)
            if (not (suspect(r, "revenue_reserve") or suspect(r, "revenue_reserve_incl_trust_share")) and status != HELD
                    and isinstance(reserve, (int, float)) and not isinstance(reserve, bool)):
                out["reserve_pp"] = round(reserve / pupils)
                if basis == "incl_trust_share":
                    out["reserve_incl_trust_share"] = True
            for k, _ in COMPARE_KEYS:
                v = _value(r, k)
                if v is not None:
                    lines[k] = round(v / pupils)
        staff, spend = (_value(r, "total_staff"), _value(r, "total_expenditure")) if r is not None else (None, None)
        if staff is not None and spend and spend > 0:
            out["staff_pct"] = round(staff / spend * 100, 1)
        pta = self.pta(item, label)
        if pta:
            out["pta_pp"], out["pta_year"], out["pta_income"] = pta[0], pta[1], pta[3]
            if pta[2]:
                out["pta_confidence"] = "medium"
        fsm = item.get("fsm")
        if isinstance(fsm, (int, float)) and not isinstance(fsm, bool):
            out["fsm_pct"] = round(fsm, 1)
        federation = federation_of(item, r)
        if federation is not None:
            out["federation"] = federation
        self.values[key] = (out, lines)
        return self.values[key]

    def row(self, item, label, mi):
        out, lines = self.facts(item, label)
        return {"urn": str(item["urn"]), "name": item["name"], "p": item["path"], "mi": round(mi, 1), **out}, lines


def _median(values):
    return round(statistics.median(values)) if len(values) >= NEARBY_MIN else None


def nearby_doc(item, neighbours, facts=None):
    """The SHARED 'nearby' contract for one school with a status and its [(miles, neighbour)] nearest first."""
    facts = facts or _NearbyFacts()
    others = [o for _, o in neighbours]
    year = nearby_year(item, others, facts)
    me, my_lines = facts.row(item, year, 0)
    rows, all_lines = [], [my_lines]
    for mi, o in neighbours:
        r, lines = facts.row(o, year, mi)
        rows.append(r)
        all_lines.append(lines)
    if my_lines:
        me["lines"] = dict(my_lines)
    every = [me] + rows
    doc = {"year": year, "phase": phase_label(item["phase"])}
    if rows:
        doc["radius_mi"] = max(r["mi"] for r in rows)
    doc["self"], doc["schools"] = me, rows
    medians = {k: _median([r[k] for r in every if k in r]) for k in NEARBY_MEDIANS}
    doc["medians"] = {k: v for k, v in medians.items() if v is not None}
    doc["rank"] = {}
    for k in NEARBY_RANKS:
        values = [r[k] for r in every if k in r]
        if k in me and len(values) >= NEARBY_MIN:
            doc["rank"][k] = {"rank": 1 + sum(v > me[k] for v in values), "of": len(values)}
    line_medians = {k: _median([lines[k] for lines in all_lines if k in lines]) for k, _ in COMPARE_KEYS}
    line_medians = {k: v for k, v in line_medians.items() if v is not None}
    if line_medians:
        doc["line_medians"] = line_medians
    return doc


def add_nearby(schools, n=NEARBY_N, max_mi=NEARBY_MAX_MI):
    """item['nearby'] (the SHARED 'nearby' contract) for every school with a status, None for the rest.

    Neighbours are open state-funded schools of the same phase group with a position and a full-year return of their
    own (federation members, whose money is in a lead school's return, are left out), up to n of them within max_mi.
    Each phase group is put on a grid of NEARBY_CELL cells and searched ring by ring, so a lookup touches a few dozen
    schools rather than all of them; each school's figures for a year are worked out once.

    The contract (written to /data/s/<urn>.json and passed to the school page as ctx['nearby']):
    {'year', 'phase', 'radius_mi' (omitted with no neighbours), 'self': ROW, 'schools': [ROW, ...] nearest first,
     'medians': {spend_pp, income_pp, gov_pp, reserve_pp, pta_pp} (NEARBY_MIN+ values), 'rank': {spend_pp, reserve_pp,
     pta_pp: {'rank', 'of'}} (1 = highest, ties share the better rank), 'line_medians': {COMPARE_KEYS}}. A ROW has urn,
    name, p, mi and, when known and not suspect, academy, status (for 'year'), pupils, spend_pp, income_pp, gov_pp,
    reserve_pp (on the school's one reserve basis, plus reserve_incl_trust_share true when that basis includes the academy's
    share of trust reserves; left out when the trust holds the reserve), staff_pct, pta_pp with pta_year and pta_income
    (plus pta_confidence 'medium' for a lower-confidence match), fsm_pct, 'federation' (the GIAS federation name, or '')
    when the year's return is a federation lead school's combined return, and on self only 'lines'. Every per-pupil figure, PTA included, divides by the pupils of the one return its year's figures come
    from. Unknown or suspect values are left out, never 0 or null."""
    assessed = [s for s in schools if s.get("status") and not s.get("member_of")]
    grids = defaultdict(lambda: defaultdict(list))
    for s in assessed:
        if _located(s) and not s.get("independent") and is_school(s.get("school") or {}) and s.get("years"):
            grids[phase_label(s["phase"])][_cell(s["lat"], s["lon"])].append(s)
    bounds = {label: _bounds(grid) for label, grid in grids.items()}
    facts = _NearbyFacts()
    for s in schools:
        s["nearby"] = None
    for s in assessed:
        label = phase_label(s["phase"])
        grid = grids.get(label)
        neighbours = _nearest(grid, s, n, max_mi, bounds[label]) if grid and _located(s) else []
        s["nearby"] = nearby_doc(s, neighbours, facts)


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
    out = Path(out) if out else ROOT / "site_money"
    if out.is_symlink():  # before resolving: resolve() would follow the link and the old tree would be deleted
        raise ValueError(f"Refusing to replace symlink: {out}")
    out = out.resolve()
    index_html = site / "index.html"
    metadata = HeadMetadata(index_html.read_text(encoding="utf-8")) if index_html.is_file() else None
    councils, schools, by_urn = build_model(site, history_path, links_path, pta_path)
    dsg = load_dsg(dsg_path)
    ifs = load_ifs()
    pta_doc = json.loads(pta_path.read_text(encoding="utf-8")) if pta_path and pta_path.exists() else {}
    data_root = site / "data"
    today = date.today().isoformat()
    built, areas_error = build_area_doc(schools, pta_doc, dsg, data_root)
    shared = {"areas": built, "ifs": ifs, "dsg": dsg, "sen_q3": sen_share_q3(schools)}
    dashboards = area_pages is not None and bool(built)
    urls, school_sizes, skipped = [], [], []
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".site_money-build-", dir=out.parent) as staging:
        stage = Path(staging) / "site_money"
        stage.mkdir()
        written = set()
        versions = asset_versions(getattr(_shell(), "asset_files", lambda: [])())
        # The first page of a council's or constituency's school table also holds AREA_TABLE_ROWS schools.
        school_tables = {c["path"] for c in councils} | {i["constituency_path"] for i in schools if i.get("constituency_path")}

        def write(path, html):
            """One page at a clean path, never twice, never at or over its size budget; asset links versioned."""
            if not PATH.fullmatch(path):
                raise ValueError(f"Unsafe page path {path!r}")
            if path in written:
                raise ValueError(f"Two pages share the path {path}")
            written.add(path)
            html = versioned(html, versions)
            size = len(html.encode("utf-8"))
            budget = (SCHOOL_PAGE_BUDGET if path.startswith("/school/") else
                      PAGE_BUDGET + AREA_TABLE_ALLOWANCE if path in school_tables else PAGE_BUDGET)
            if size >= budget:
                raise ValueError(f"Page too large ({size:,} bytes, budget {budget:,}): {path}")
            target = stage / path.lstrip("/") / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")

        def write_all(pages, indexable=True):
            for path, html in pages:
                write(path, html)
                if indexable:
                    urls.append((path, today))

        trusts = trusts_of(schools)
        trust_path = {name: items[0]["trust_path"] for name, items in trusts.items()}
        constituencies = defaultdict(list)
        for i in schools:
            if i["constituency"]:
                constituencies[(i["constituency"], i["constituency_path"])].append(i)
        regions = defaultdict(list)
        for c in councils:
            if c.get("region") and c["schools"]:
                regions[c["region"]].append(c)
        actx = area_ctx(shared, councils, schools, trust_path) if dashboards else None

        def dashboard(path, crumbs, result, first_rows=0):
            pages = area_result_pages(path, crumbs, result, metadata, first_rows)
            write_all(pages, indexable=bool(result.get("indexable", True)))

        # National, England and regions
        if dashboards:
            write("/", render_home(schools, metadata, built.get("england")))
            urls.append(("/", today))
            dashboard("/england/", [("School Money", "/"), ("England", "/england/")],
                      area_pages.render_area("england", "england", built.get("england"), schools, actx))
            write("/areas/", region_index(built.get("regions") or {}, metadata))
            urls.append(("/areas/", today))
        else:
            write("/", render_national(councils, schools, metadata, dsg))
            urls.append(("/", today))
        for name, cs in regions.items():
            path = f"/areas/{slug(name)}/"
            region = (built.get("regions") or {}).get(name) if dashboards else None
            if region is not None:
                dashboard(path, [("School Money", "/"), ("Areas", "/areas/"), (name, path)],
                          area_pages.render_area("region", name, region, [i for c in cs for i in c["schools"]], actx))
            else:
                write(path, render_region(name, path, cs, metadata))
                urls.append((path, today))

        # Councils
        council_areas = {}
        for c in councils:
            a = (built.get("councils") or {}).get(c["code"]) if dashboards else None
            if a is not None and c["schools"]:
                council_areas[c["code"]] = dict(a, code=c["code"], name=c["name"], path=c["path"], region=c.get("region"))
        if dashboards and council_areas:
            dashboard("/council/", [("School Money", "/"), ("Councils", "/council/")], area_pages.render_council_league(council_areas, actx))
        else:
            write_all(render_council_index(councils, metadata))
        for c in councils:
            if not c["schools"]:
                continue
            if c["code"] in council_areas:
                dashboard(c["path"], [("School Money", "/"), ("Councils", "/council/"), (c["name"], c["path"])],
                          area_pages.render_area("council", c["code"], council_areas[c["code"]], c["schools"], actx), AREA_TABLE_ROWS)
            else:
                write_all(render_council(c, metadata, dsg), indexable=any(i["status"] for i in c["schools"]))

        # Schools, and each one's SERIES for drills and Wrapped
        series_docs = {}
        for item in schools:
            html, indexable, doc = school_page_html(item, metadata, shared)
            write(item["path"], html)
            school_sizes.append(len(html.encode("utf-8")))
            if item["status"]:
                series_docs[item["urn"]] = doc
                if indexable:
                    urls.append((item["path"], today))

        # Trusts
        trust_areas = {}
        if dashboards:
            by_name = {a.get("name"): (key, a) for key, a in (built.get("trusts") or {}).items() if a and a.get("name")}
            for name in trusts:
                if name in by_name:
                    key, a = by_name[name]
                    trust_areas[key] = dict(a, name=name, path=trust_path[name])
        if trust_areas:
            dashboard("/trust/", [("School Money", "/"), ("Academy trusts", "/trust/")], area_pages.render_trust_index(trust_areas, actx))
        else:
            write_all(render_trust_index(trusts, metadata))
        matched = {a["name"]: a for a in trust_areas.values()}
        for name, items in trusts.items():
            if name in matched:
                path = trust_path[name]
                dashboard(path, [("School Money", "/"), ("Academy trusts", "/trust/"), (name, path)],
                          area_pages.render_trust(matched[name], items, actx))
            else:
                write_all(render_trust(name, items, metadata))

        # Constituencies
        write_all(render_constituency_index(constituencies, metadata))
        constituency_areas = {a.get("name"): (code, a) for code, a in ((built or {}).get("constituencies") or {}).items() if a} if dashboards else {}
        for (name, path), items in constituencies.items():
            if name in constituency_areas:
                code, a = constituency_areas[name]
                dashboard(path, [("School Money", "/"), ("Constituencies", "/constituency/"), (name, path)],
                          area_pages.render_area("constituency", code, a, items, actx), AREA_TABLE_ROWS)
            else:
                write_all(render_constituency(name, path, items, metadata), indexable=any(i["status"] for i in items))

        # Debts and PTFA
        if dashboards:
            dashboard("/debts/", [("School Money", "/"), ("Debts", "/debts/")], area_pages.render_debts(built, actx))
            dashboard("/ptfa/", [("School Money", "/"), ("PTFA", "/ptfa/")], area_pages.render_ptfa(built, schools, actx))
        write("/compare/", render_compare(metadata))
        write("/about/", render_about(metadata, dsg, ifs))
        urls += [("/compare/", today), ("/about/", today)]

        # Data for the app
        data = stage / "data"
        for sub in ("s", "sx", "a"):
            (data / sub).mkdir(parents=True, exist_ok=True)
        statuses = {}
        for item in schools:
            if not item["status"]:
                continue
            doc = school_json(item, data_root, item.get("profile"), timeline_of(item))
            (data / "s" / f"{item['urn']}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            sx = series_docs.get(item["urn"]) or school_series(item, shared["sen_q3"])
            (data / "sx" / f"{item['urn']}.json").write_text(series_json(sx), encoding="utf-8")
            statuses[item["urn"]] = {"status": item["status"]["status"], "label": item["status"]["label"], "path": item["path"]}
        docs = area_documents(councils, schools, built, dsg)
        for ident, doc in docs.items():
            if not re.fullmatch(r"[a-z0-9-]+", ident):
                raise ValueError(f"Unsafe area id {ident!r}")
            (data / "a" / f"{ident}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (data / "search.json").write_text(json.dumps(search_index(councils, schools, trusts), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (data / "postcodes").mkdir()
        for district, doc in postcode_index(schools).items():
            (data / "postcodes" / f"{district}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (data / "status.json").write_text(json.dumps(statuses, separators=(",", ":")), encoding="utf-8")
        assets = stage / "assets"
        assets.mkdir()
        for asset in _shell().asset_files():
            shutil.copyfile(asset, assets / Path(asset).name)

        # Extensions (map, deck, Wrapped, guides), then stubs for whatever no page has claimed
        env = {"out": stage, "write": write, "page": _shell().page, "items": schools, "areas": areas_for_extensions(built, docs),
               "today": today, "og_image": getattr(metadata, "image", None) or None}
        for path, indexable in run_extensions(env, skipped):
            if indexable:
                urls.append((path, today))
        for path, title, text, links in STUBS:
            if path not in written:
                write(path, render_stub(path, title, text, links, metadata))
        (stage / "404.html").write_text(versioned(render_404(metadata), versions), encoding="utf-8")
        (stage / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /data/\nSitemap: {BASE_MONEY}/sitemap.xml\n", encoding="utf-8")
        write_sitemaps(stage, urls, today)
        if out.is_symlink():
            raise ValueError(f"Refusing to replace symlink: {out}")
        if out.exists():
            shutil.rmtree(out)
        shutil.move(str(stage), out)
    counts = Counter(i["status"]["status"] for i in schools if i["status"])
    return {"schools": len(schools), "with_status": sum(counts.values()), "councils": len(councils), "trusts": len(trusts),
            "constituencies": len(constituencies), "statuses": dict(counts), "pages": len(urls), "out": str(out),
            "school_page_median": round(statistics.median(school_sizes)) if school_sizes else 0,
            "school_page_max": max(school_sizes, default=0), "areas_error": areas_error, "skipped_extensions": skipped,
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
    print("Statuses:", ", ".join(f"{status_label(k)} {summary['statuses'].get(k, 0):,}" for k in status_keys(summary["statuses"])))
    print(f"School pages: median {summary['school_page_median']:,} bytes, largest {summary['school_page_max']:,} bytes (budget {SCHOOL_PAGE_BUDGET:,})")
    print("Shell:", "pipeline/money/site.py" if shell is not None else "built-in fallback",
          "| areas:", "yes" if areas else "no", "| timeline:", "yes" if timeline else "no", "| deflator:", "yes" if deflator else "no",
          "| series:", "yes" if series else "local", "| school page:", "yes" if school_page else "fallback",
          "| area pages:", "yes" if area_pages else "fallback")
    if summary["areas_error"]:
        print("areas.build_areas failed, reduced area statistics used:", summary["areas_error"])
    if summary["skipped_extensions"]:
        print("Extensions skipped:", "; ".join(summary["skipped_extensions"]))


if __name__ == "__main__":
    main()
