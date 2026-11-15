"""The School Money app shell: one HTML document wrapper, money figures, pin buttons and the
static assets. Python stdlib only; the page builder (build_money.py) supplies escaped body HTML.

Nothing here reads data. Every £ figure the page shows carries data-* attributes that
assets/app.js turns into tooltips, drill-downs and pins; the HTML works without it.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from html import escape
from pathlib import Path

try:
    from pipeline.money.charts import money as _money
except ImportError:  # pragma: no cover - charts.py is owned by another unit; keep a tiny copy
    def _money(value, signed=False):
        if value is None:
            return "—"
        sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
        v = abs(value)
        if v >= 1e9:
            return f"{sign}£{v / 1e9:.2f}bn"
        if v >= 1e6:
            return f"{sign}£{v / 1e6:.1f}m"
        if v >= 1e3:
            return f"{sign}£{v / 1e3:.0f}k"
        return f"{sign}£{v:,.0f}"

try:
    from pipeline.seo.build_pages import slug
except ImportError:  # pragma: no cover
    def slug(value):
        text = unicodedata.normalize("NFKD", str(value).replace("&", " and "))
        text = text.encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:80].rstrip("-") or "school"

BASE_MONEY = "https://money.schoolsinreach.com"
BASE_SIR = "https://www.schoolsinreach.com"
SITE_NAME = "School Money"
ASSETS = Path(__file__).with_name("assets")

NAV = [
    ("Find a school", "/"),
    ("PTFA fundraising", "/ptfa/"),
    ("Compare", "/compare/"),
    ("Areas", "/areas/"),
    ("Guides", "/guides/"),
]
MORE_NAV = [
    ("Map", "/map/"),
    ("Trusts", "/trust/"),
    ("Debts", "/debts/"),
    ("Videos", "/video/"),
    ("Tools", "/tools/"),
]

AUDIENCES = [
    ("parent", "Parent"),
    ("governor", "Governor"),
    ("ptfa", "PTFA"),
    ("leader", "School leader"),
    ("pupil", "Pupil"),
]

SOURCES = [
    ("DfE Financial Benchmarking and Insights Tool (CFR and AAR)", "https://financial-benchmarking-and-insights-tool.education.gov.uk/data-sources"),
    ("Get Information about Schools", "https://get-information-schools.service.gov.uk/"),
    ("Charity Commission register", "https://register-of-charities.charitycommission.gov.uk/"),
    ("HM Treasury GDP deflators", "https://www.gov.uk/government/collections/gdp-deflators-at-market-prices-and-money-gdp"),
]
OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
# The address that takes corrections and privacy questions. None until a monitored mailbox exists: the about page then
# says how to get a figure corrected at source and that a direct address is coming. Never a person's own address.
CONTACT_EMAIL = None
# Beside every status badge and in the footer (contract C6); used verbatim.
REPORT_LINK = '<a class="report-link" href="/about/#corrections">Report an error or add context</a>'
IFS_CITE = "IFS, Annual report on education spending in England: 2025–26 (January 2026)"
IFS_URL = "https://ifs.org.uk/publications/annual-report-education-spending-england-2025-26"

MARK = ('<svg class="mark" viewBox="0 0 32 32" width="28" height="28" aria-hidden="true" focusable="false">'
        '<rect x="3" y="6" width="26" height="20" rx="4" fill="none" stroke="currentColor" stroke-width="2.5"/>'
        '<path d="M3 13h26" stroke="currentColor" stroke-width="2.5"/>'
        '<path d="M9 20h6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>'
        '<circle cx="23" cy="20" r="2.2" fill="currentColor"/></svg>')


def esc(value) -> str:
    return escape(str(value), quote=True)


def _ifs_citation():
    """The IFS short citation from data/ifs_context.json, or the built-in copy if the file is missing."""
    try:
        with open(Path(__file__).with_name("data") / "ifs_context.json", encoding="utf-8") as fh:
            src = json.load(fh).get("source", {})
        return src.get("short_cite") or IFS_CITE, src.get("url") or IFS_URL
    except (OSError, ValueError):
        return IFS_CITE, IFS_URL


def breadcrumbs(crumbs):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": BASE_MONEY + path}
        for i, (name, path) in enumerate(crumbs, 1)]}


def _trail(crumbs):
    parts = []
    for i, (name, path) in enumerate(crumbs):
        if i < len(crumbs) - 1:
            parts.append(f'<a href="{esc(path)}">{esc(name)}</a>')
        else:
            parts.append(f'<span aria-current="page">{esc(name)}</span>')
    return ' <span aria-hidden="true">›</span> '.join(parts)


def _nav(path):
    def link(label, href):
        current = ' aria-current="page"' if href == path or (href != "/" and path.startswith(href)) else ""
        extra = ' <span class="count" data-pin-count>0</span>' if href == "/compare/" else ""
        return f'<a href="{esc(href)}"{current}>{esc(label)}{extra}</a>'
    return ("".join(link(*entry) for entry in NAV)
            + '<details class="nav-more"><summary>More</summary><div class="more-links">'
            + "".join(link(*entry) for entry in MORE_NAV) + '</div></details>')


AUDIENCE_LEGEND = "Show me useful links. I'm a…"
# Runs in <head> before first paint: html.js shows the picker (without JavaScript its chips would do nothing), and the
# reader chosen on an earlier page (app.js's localStorage key) sets html[data-reader]. app.css reserves the slim
# strip's space and audience.css tags the relevant sections before app.js runs.
AUDIENCE_BOOT = ('<script>!function(h){h.classList.add("js");try{var r=JSON.parse(localStorage.getItem("moneyAudience"));'
                 '/^(' + "|".join(key for key, _ in AUDIENCES) + ')$/.test(r)&&h.setAttribute("data-reader",r)}catch(e){}}'
                 '(document.documentElement)</script>')


def _audience():
    """Home-page reader choices; old moneyAudience values remain unchanged."""
    buttons = "".join(f'<button type="button" data-audience="{key}" aria-pressed="false">{esc("PTFA member" if key == "ptfa" else label)}</button>' for key, label in AUDIENCES)
    return (f'<div class="aud-bar"><fieldset class="audience"><legend>{AUDIENCE_LEGEND}</legend><span class="aud-chips">{buttons}</span>'
            '<button type="button" class="aud-clear">Clear</button></fieldset></div>')


MENU_BUTTON = '<button type="button" class="menu-toggle" aria-expanded="false" aria-controls="main-nav">Menu</button>'


def corrections_html() -> str:
    """The about page's corrections section: where each kind of figure is corrected at source, and how to reach School
    Money (CONTACT_EMAIL, or a note that a direct address is coming while it is None)."""
    if CONTACT_EMAIL:
        mail = esc(CONTACT_EMAIL)
        reach = (f'<p>If our figure differs from the source, the mistake is ours: email <a href="mailto:{mail}">{mail}</a> with the '
                 "school's name or URN, the figure and year, and where you saw the right one. We check it against the source and reply.</p>")
    else:
        reach = ("<p>If our figure differs from the source, the mistake is ours. A direct corrections address is coming; when it opens it "
                 "will be given here. Until then, the school or council can check the return with the DfE, and a corrected return "
                 "reaches this site when it is next rebuilt.</p>")
    return ('<h2 id="corrections">Corrections</h2>'
            "<p>Every figure here comes from a published source and is shown as it was filed. If one looks wrong, compare it first "
            "with the source page linked beside it.</p><ul>"
            "<li><strong>A school's income, spending, reserve or pupil numbers</strong> come from its return to the Department for "
            "Education (DfE): the Consistent Financial Reporting return, made through the council, for a council-run school; the "
            "Academy Accounts Return, made by the trust, for an academy. The school, its council or its trust can ask for a return to "
            "be corrected, and the corrected figures appear here once the DfE republishes them.</li>"
            "<li><strong>A parents' association's income and spending</strong> come from the charity's annual return to the Charity "
            "Commission, which its trustees correct with the Commission. A charity matched to the wrong school, or a missing one, "
            "is ours to fix.</li>"
            "<li><strong>A council's Dedicated Schools Grant balance (all four blocks)</strong> comes from the DfE's published outturn, "
            "which the council corrects with the DfE.</li></ul>"
            f"{reach}"
            "<p>A school, trust or council can also send context to sit beside its figures, such as a deficit already covered by an "
            "agreed recovery plan.</p>")


def privacy_html() -> str:
    """The about page's privacy section: what is stored on the reader's device, which requests leave this site, and
    hosting logs. No personal name, address or legal entity."""
    ask = (f'<p>Questions about privacy: email <a href="mailto:{esc(CONTACT_EMAIL)}">{esc(CONTACT_EMAIL)}</a>.</p>' if CONTACT_EMAIL else "")
    return ('<h2 id="privacy">Privacy</h2>'
            "<p>School Money has no accounts, sign-ups, adverts, analytics or tracking cookies.</p><ul>"
            "<li><strong>On your device only.</strong> The reader you choose, the schools and areas you pin and whether you have "
            "answered the Schools in Reach import offer are kept in your browser's local storage (localStorage) on this device. "
            "They are never sent to us. The Clear buttons, or your browser's site data settings, remove them.</li>"
            "<li><strong>Postcode search.</strong> Typing a postcode, or a district such as N16, reads a file from this site. When "
            "you press Search with a full postcode, your browser also asks postcodes.io (api.postcodes.io), a free public postcode lookup, "
            "where that postcode is, so the nearest schools come first; postcodes.io receives the postcode and, like any website, "
            "your IP address. Searching by name sends nothing outside this site.</li>"
            "<li><strong>Maps, presentations and videos</strong> load their code from the public code hosts cdnjs and jsDelivr, "
            "and the map its background tiles from tiles.schoolsinreach.com. Those hosts see the request.</li>"
            "<li><strong>Hosting logs.</strong> Like any website, the servers that host School Money keep standard request logs "
            "(the page, the time, the browser and the IP address) to keep the site running and secure. They are not used to "
            "follow or profile visitors.</li>"
            "<li><strong>No personal details.</strong> The figures are about schools, trusts, councils and charities, from public "
            "registers. The site publishes no one's name or contact details.</li></ul>"
            f"{ask}")


def _footer():
    cite, url = _ifs_citation()
    items = "".join(f'<li><a href="{esc(href)}" rel="noopener">{esc(name)}</a>, <a href="{OGL}" rel="license noopener">OGL v3</a></li>'
                    for name, href in SOURCES)
    return (f'<footer><div class="wrap"><section class="sources"><h2 id="sources">Sources</h2><ul>{items}'
            f'<li>Context: <a href="{esc(url)}" rel="noopener">{esc(cite)}</a></li></ul></section>'
            f'<p class="foot-links"><a href="/about/#sources">Sources</a> · <a href="/about/#licences">Licences</a> · '
            f'<a href="/about/">How the figures are worked out</a> · {REPORT_LINK} · <a href="/about/#privacy">Privacy</a> · '
            f'<a href="{BASE_SIR}">Schools in Reach</a></p>'
            f'<p class="muted small">{esc(SITE_NAME)} shows published open data as it was filed. Figures are a starting point for a '
            f'conversation with your school, not a verdict on it.</p></div></footer>')


def analytics_tag() -> str:
    """The page-view loader, only when the build is given one: MONEY_ANALYTICS_SCRIPT=https://... (deploy/money/deploy.sh
    sets the owner's cookieless loader). A copy of this site built without it loads no analytics and reports to no one.
    Anything but a plain https URL is ignored."""
    url = os.environ.get("MONEY_ANALYTICS_SCRIPT", "").strip()
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::\d+)?/[A-Za-z0-9._~/-]*", url):
        return ""
    return f'<script defer src="{esc(url)}"></script>'


def page(title, description, path, body, crumbs, *, og_image=None, indexable=True, extra_head="") -> str:
    """A complete HTML document. title/description are plain text; body is trusted, already-escaped HTML;
    path is the clean absolute path of the page; crumbs = [(name, path), ...] ending with this page."""
    if not path.startswith("/"):
        raise ValueError(f"path must be absolute: {path!r}")
    url = BASE_MONEY + path
    # HTML entities must not be used inside JSON; escape '<' and '&' so </script> cannot close the block.
    ld = json.dumps([breadcrumbs(crumbs)], ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    head = [
        f"<title>{esc(title)}</title>",
        f'<meta name="description" content="{esc(description)}">',
        f'<link rel="canonical" href="{esc(url)}">',
    ]
    if not indexable:
        head.append('<meta name="robots" content="noindex,follow">')
    for key, value in (("og:type", "website"), ("og:site_name", SITE_NAME), ("og:title", title),
                       ("og:description", description), ("og:url", url), ("og:locale", "en_GB")):
        head.append(f'<meta property="{key}" content="{esc(value)}">')
    for key, value in (("twitter:card", "summary_large_image" if og_image else "summary"),
                       ("twitter:title", title), ("twitter:description", description)):
        head.append(f'<meta name="{key}" content="{esc(value)}">')
    if og_image:
        head.append(f'<meta property="og:image" content="{esc(og_image)}"><meta name="twitter:image" content="{esc(og_image)}">')
    head.append('<meta name="theme-color" content="#f6f2ea" media="(prefers-color-scheme: light)">'
                '<meta name="theme-color" content="#16181b" media="(prefers-color-scheme: dark)">')
    head.append(AUDIENCE_BOOT)
    head.append('<link rel="stylesheet" href="/assets/app.css"><script src="/assets/app.js" defer></script>'
                '<link rel="stylesheet" href="/assets/audience.css">')
    head.append(analytics_tag())
    head.append(f'<script type="application/ld+json">{ld}</script>')
    if extra_head:
        head.append(extra_head)
    search = ('<form class="search" role="search" action="/search/"><label for="q" class="visually-hidden">Search schools, councils, '
              'constituencies and trusts</label><input id="q" name="q" type="search" placeholder="School, council, trust or postcode" '
              'autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="q-list"><button type="submit">Search</button>'
              '<ul id="q-list" class="listbox" role="listbox" aria-label="Suggestions" hidden></ul></form>')
    # Home has one large finder in its body. Every other page keeps the unchanged header search contract.
    if path == "/":
        search = ""
    header = (f'<header class="top{" home" if path == "/" else ""}"><div class="wrap"><a class="brand" href="/">{MARK}'
              f'<span class="name">{SITE_NAME}</span></a><a class="tagline" href="{BASE_SIR}">by Schools in Reach</a>{search}'
              f'{MENU_BUTTON}<nav class="main-nav" id="main-nav" aria-label="Main">{_nav(path)}</nav></div></header>')
    quick_links = '<div id="for-you"></div>' if path != "/" else ""
    return (f'<!doctype html>\n<html lang="en-GB" data-audience="parent"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n{chr(10).join(head)}\n</head>'
            f'<body><a class="skip" href="#main">Skip to content</a>{header}{quick_links}'
            f'<main id="main" class="wrap"><nav class="crumbs" aria-label="Breadcrumb">{_trail(crumbs)}</nav>{body}</main>'
            f'{_footer()}</body></html>\n')


def _exact(value, signed=False):
    """Per-pupil amounts are small, so show them to the pound: £4,115 rather than £4k."""
    sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
    return f"{sign}£{abs(round(value)):,}"


def _num(value):
    """A short, exact string for a data-* attribute (no exponent, no trailing .0)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def money_figure(key, value, pupils, year, *, label=None, src=None, cmp_similar=None, cmp_england=None,
                 drill=None, signed=False, cls="") -> str:
    """A £ figure with its per-pupil companion. key is a glossary key (assets/glossary.json); value is the
    total; pupils is the same row's pupil count (falsy = no per-pupil); year is the display label."""
    attrs = [f'class="mf{" " + esc(cls) if cls else ""}"', f'data-mf="{esc(key)}"', f'data-v="{_num(value) or ""}"']
    pp = None
    if value is not None and pupils and _num(value) is not None:
        pp = value / pupils
        attrs.append(f'data-pp="{_num(round(pp))}"')
    attrs.append(f'data-year="{esc(year)}"')
    if label:
        attrs.append(f'data-label="{esc(label)}"')
    if src:
        attrs.append(f'data-src="{esc(src)}"')
    if cmp_similar is not None and _num(cmp_similar) is not None:
        attrs.append(f'data-cmp-similar="{_num(round(cmp_similar))}"')
    if cmp_england is not None and _num(cmp_england) is not None:
        attrs.append(f'data-cmp-england="{_num(round(cmp_england))}"')
    if drill:
        attrs.append(f'data-drill="{esc(drill)}"')
    if signed:
        attrs.append('data-signed="1"')
    text = esc(_money(value, signed))
    small = f' <small>{esc(_exact(pp, signed))} per pupil</small>' if pp is not None else ""
    return f'<span {" ".join(attrs)}>{text}{small}</span>'


def page_path(kind, ident, name) -> str:
    """Where a pinned thing lives: schools at /school/<urn>-<slug>/, areas by their id prefix."""
    ident = str(ident)
    if kind == "school":
        return f"/school/{ident}-{slug(name)}/"
    if ident == "england":
        return "/"
    for prefix, root in (("council-", "/council/"), ("constituency-", "/constituency/"), ("region-", "/areas/")):
        if ident.startswith(prefix):
            tail = ident[len(prefix):]
            # Council ids carry the LA code; their pages are named after the council.
            return f"{root}{slug(name) if prefix == 'council-' else tail}/"
    return f"/{slug(name)}/"


def pin_button(kind, ident, name, path=None) -> str:
    """A pin toggle for a school ("school", urn) or an area ("area", area id); app.js keeps the list."""
    payload = {"type": kind, "id": str(ident), "name": str(name), "p": path or page_path(kind, ident, name)}
    data = escape(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), quote=True)
    return (f'<button type="button" class="pin" data-pin=\'{data}\' aria-pressed="false">'
            f'<span aria-hidden="true">📌</span> Pin</button>')


def asset_files() -> list[Path]:
    """Every file under assets/, to be copied verbatim to <out>/assets/."""
    return sorted(p for p in ASSETS.rglob("*") if p.is_file() and not p.name.startswith("."))
