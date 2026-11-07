"""Area dashboards for School Money: England, regions, councils, constituencies, academy
trusts, /debts/ and /ptfa/. Python stdlib only.

Every renderer returns {"title", "description", "intro", "table", "outro", "indexable"}:
title and description are plain text; intro and outro are escaped HTML (intro starts with
the page's <h1>); table is {"headers": [plain text], "rows": [[cell html]], "caption": plain
text, "filters": html} or None. build_money pages the table and wraps everything with
site.page(..., extra_head=EXTRA_HEAD); intro and outro appear on page 1 only.

Figures come from areas.build_areas (areas.json): see that module for the combined-series
rule (all-school figures stop at the last year with academy accounts; later years are
council-run only) and the PTA year rule. Line charts use charts.trend_chart and
charts.sparkline when builder-core's charts.py has them, else the small local versions
below, which emit the same markers (role="img", <title>, <desc>, g[data-basis]).

Copy is written for parents, governors, PTFA committees, school leaders and pupils: a
deficit is always named beside its usual causes, the IFS context and what helps.
"""

from __future__ import annotations

import re
from collections import Counter

from pipeline.money import areas as agg
from pipeline.money import charts
from pipeline.money.charts import STATUS_ORDER, badge, esc, money
from pipeline.money.site import money_figure, pin_button, slug

try:
    from pipeline.money import deflator
except ImportError:  # pragma: no cover - deflator.py ships with the money package
    deflator = None

FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk"
CHARITY = "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/"
EXTRA_HEAD = '<link rel="stylesheet" href="/assets/areas.css"><script src="/assets/trend.js" defer></script>'
SUFFIX = " | School Money"
FROM_YEAR = "2018-19"
PAGE_TEXT_BUDGET = 22_000    # intro + outro bytes on any page
TOP_LIST = 10
IFS_YEAR = "2025-26"         # IFS figures are in 2025-26 prices
GOV_LABELS = {"council-run": "Council-run", "academy": "Academy"}
GROUP_LABELS = {"governance": "Run by", "phase": "Phase", "admissions": "Admissions", "faith": "Faith"}
VALUE_LABELS = {"council-run": "Council-run", "academy": "Academy", "primary": "Primary", "secondary": "Secondary",
                "special": "Special", "all-through": "All-through", "nursery": "Nursery", "other": "Other",
                "grammar": "Grammar", "non-selective": "Non-selective", "partially-selective": "Partially selective",
                "none": "No religious character"}
SECTOR_NOTE = ("Council-run schools report for April to March (CFR returns) and academies for September to August "
               "(academy accounts returns). Figures for all schools together stop at {last}, the latest year with "
               "academy accounts; later years are council-run schools only.")
GOV_NOTE = ("Government funding is academies' grant funding from government (academy accounts) against council-run "
            "schools' grant funding (CFR), which can include some money that is not from government, so the two are "
            "not strictly comparable. Lines are the middle (median) school's figure each year.")
HELPS = ("What helps: a recovery plan agreed with the council or trust that brings the budget back into balance over a "
         "few years, regular forecasts that governors check, and early conversations about pupil numbers and special "
         "needs funding.")
REASONS = ("Most of a school's money pays for staff, so deficits usually build up when pay and other costs rise faster "
           "than funding, or when pupil numbers fall and the money that comes with each pupil goes too.")
NOT_FOUND = "No registered parents' association found"
TRUST_NOTE = ("A trust can move money between its academies, so an academy shown in deficit may be supported by the "
              "trust as a whole.")
OVERLAP_NOTE = ("Parents' association income and the donations in a school's own accounts can overlap (money the "
                "association gives the school can appear in both), so the two are never added together.")
HNSG_FALLBACK = ("Statutory override: council high-needs (DSG) deficits are held apart from council general funds until "
                 "the end of 2027-28, and the High Needs Stability Grant pays 90% of each council's eligible deficit "
                 "from autumn 2026.")
POUND = re.compile(r"£(\d[\d,]*(?:\.\d+)?)(\s?(?:billion|bn|million|m)\b)?")


# ----------------------------------------------------------------- small helpers

def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _attr(value):
    """A short, exact string for a data-* attribute."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def exact(value, signed=False):
    sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
    return f"{sign}£{abs(round(value)):,}"


def shorten(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def title_of(text):
    return shorten(text, 70 - len(SUFFIX)) + SUFFIX


def pp_fig(key, value, year, *, signed=False, england=None, cls=""):
    """An area figure that is already per pupil (a median or an average), exact to the pound."""
    if _num(value) is None:
        return '<span class="muted">—</span>'
    attrs = [f'class="mf{" " + esc(cls) if cls else ""}"', f'data-mf="{esc(key)}"', f'data-v="{_attr(round(value))}"',
             f'data-year="{esc(year)}"']
    if _num(england) is not None:
        attrs.append(f'data-cmp-england="{_attr(round(england))}"')
    if signed:
        attrs.append('data-signed="1"')
    return f'<span {" ".join(attrs)}>{esc(exact(value, signed))}</span>'


def amount(key, value):
    """A fixed £ threshold quoted in copy (e.g. the £5,000 charity registration limit)."""
    return f'<span class="mf" data-mf="{esc(key)}" data-v="{_attr(value)}">{esc(exact(value))}</span>'


def ifs_fig(text, value):
    return f'<span class="mf" data-mf="ifs_figure" data-v="{_attr(value)}" data-year="{IFS_YEAR}">{esc(text)}</span>'


def ifs_text(text):
    """Escaped IFS prose with every £ amount kept verbatim inside an ifs_figure span."""
    out, last = [], 0
    for m in POUND.finditer(text or ""):
        out.append(esc(text[last:m.start()]))
        unit = (m.group(2) or "").strip()
        scale = 1e9 if unit in ("billion", "bn") else 1e6 if unit in ("million", "m") else 1
        out.append(ifs_fig(m.group(0), float(m.group(1).replace(",", "")) * scale))
        last = m.end()
    out.append(esc((text or "")[last:]))
    return "".join(out)


def ifs_line(ctx, section, ident):
    """(html, page) of one IFS context line by id, or None when the pack lacks it."""
    for line in (((ctx or {}).get("ifs") or {}).get("context_lines") or {}).get(section) or []:
        if line.get("id") == ident and line.get("text"):
            return ifs_text(line["text"]), line.get("page")
    return None


def cite(page):
    return f' <span class="cite">(IFS{", p." + esc(page) if page else ""})</span>'


def ifs_para(ctx, section, ident, cls="ifs"):
    found = ifs_line(ctx, section, ident)
    return f'<p class="{cls}">{found[0]}{cite(found[1])}</p>' if found else ""


def hnsg_note(dsg):
    """la_dsg.json's statutory-override note (the High Needs Stability Grant), or the built-in copy."""
    for note in ((dsg or {}).get("source") or {}).get("notes") or []:
        if isinstance(note, str) and note.lower().startswith("statutory override"):
            return note
    return HNSG_FALLBACK


def is_14bn(line):
    text = line.get("text") or ""
    return "£14" in text and "2028" in text


def council_ifs_lines(ctx, ids=None):
    """IFS council context lines as <li>s; the £14bn deficit line always carries the HNSG note."""
    items = []
    for line in (((ctx or {}).get("ifs") or {}).get("context_lines") or {}).get("council") or []:
        if ids is not None and line.get("id") not in ids:
            continue
        if not ids and line.get("use_when") not in (None, "always"):
            continue
        html = ifs_text(line.get("text") or "") + cite(line.get("page"))
        if is_14bn(line):
            html += f' <span class="hnsg note">{esc(hnsg_note((ctx or {}).get("dsg")))}</span>'
        items.append(f"<li>{html}</li>")
    return f'<ul class="ifs-list">{"".join(items)}</ul>' if items else ""


def label_of(year):
    return str(year or "").replace("/", "-")


def year_after(label):
    start = int(label[:4]) + 1
    return f"{start}-{(start + 1) % 100:02d}"


def by_year(area):
    return (area or {}).get("by_year") or {}


def split_of(area, year, split="all"):
    entry = by_year(area).get(year)
    value = entry.get(split) if isinstance(entry, dict) else None
    return value if isinstance(value, dict) else None


def combined_years(area):
    return sorted(y for y in by_year(area) if split_of(area, y) and (split_of(area, y).get("schools") or 0) > 0)


def latest_combined(area):
    """(year, S) for the newest year whose all-schools figures exist."""
    for year in reversed(combined_years(area)):
        s = split_of(area, year)
        if s.get("in_deficit") is not None or year == combined_years(area)[-1]:
            return year, s
    return None, None


def latest_split(area, split):
    for year in sorted(by_year(area), reverse=True):
        s = split_of(area, year, split)
        if s and s.get("in_deficit") is not None:
            return year, s
    return None, None


def series(area, key, years, split="all"):
    out = {}
    for year in years:
        value = (split_of(area, year, split) or {}).get(key)
        if _num(value) is not None:
            out[year] = value
    return out


def areas_doc(ctx):
    doc = (ctx or {}).get("areas") or {}
    return doc.get("areas") if isinstance(doc.get("areas"), dict) else doc


def paths(ctx, kind):
    return (((ctx or {}).get("paths") or {}).get(kind)) or {}


def council_path(ctx, code, name):
    return paths(ctx, "council").get(str(code)) or f"/council/{slug(name or code)}/"


def region_path(ctx, name):
    return paths(ctx, "region").get(name) or f"/areas/{slug(name)}/"


def trust_path(ctx, name, fallback=None):
    return paths(ctx, "trust").get(name) or fallback or f"/trust/{slug(name)}/"


def council_link(ctx, code, name):
    return (f'<a href="{esc(council_path(ctx, code, name))}" data-preview="area:council-{esc(code)}">'
            f'{esc(name or code)}</a>')


def pct_text(s):
    if not s or s.get("in_deficit_pct") is None:
        return '<span class="muted">—</span>'
    return f'{s["in_deficit_pct"]:.1f}% <small>({s["in_deficit"]:,} of {s["schools"]:,})</small>'


def sort(value, html):
    key = "" if _num(value) is None else (f"{value:.4f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value))
    return f'<span data-sort="{key}">{html}</span>'


def sources(extra=""):
    return ('<section class="sources"><p class="muted small">Sources: DfE Financial Benchmarking and Insights Tool data '
            '(CFR returns for council-run schools, April to March; academy accounts returns, September to August), '
            'Get Information about Schools, DfE section 251 outturn (DSG balances), the Charity Commission register and '
            'the IFS annual report on education spending in England 2025–26 (IFS figures in 2025–26 prices, November '
            f'2025 deflator). Open Government Licence v3.0.{extra} <a href="/about/">How these figures are worked out</a>'
            '</p></section>')


def deflator_label(ctx):
    label = (ctx or {}).get("real_label")
    return label or None


# ----------------------------------------------------------------- charts

def _fmt(value, unit):
    if unit == "%":
        return f"{value:.0f}%" if float(value).is_integer() or abs(value) >= 10 else f"{value:.1f}%"
    if unit == "pupils":
        return f"{value / 1e6:.1f}m" if abs(value) >= 1e6 else f"{value / 1e3:.0f}k" if abs(value) >= 1e4 else f"{value:,.0f}"
    return money(value) if abs(value) >= 100_000 else exact(value)


def _ticks(lo, hi):
    return charts._ticks(lo, hi)


LABEL_CHARS = 20   # direct labels in the fallback chart are cut to this many characters


def line_label(text):
    """A direct label short enough for the chart's margin. A trailing measure word ("funding",
    "spending", "academies") is kept, so cutting a long place name never hides which line it is."""
    text = " ".join(str(text or "").split())
    if len(text) <= LABEL_CHARS:
        return text
    head, _, tail = text.rpartition(" ")
    if head and tail.islower() and len(tail) < LABEL_CHARS - 4:
        return shorten(head, LABEL_CHARS - len(tail) - 1) + " " + tail
    return shorten(text, LABEL_CHARS)


def fallback_trend(lines, *, years, unit="£", title, desc, height=220, suspect=(), partial=()):
    """A compact line chart with the TREND DOM markers (used until charts.trend_chart exists).
    Each line is one path per stroke style, and ticks and labels share a group, so a dashboard
    holds every measure within the page budget."""
    years = list(years)
    vals = [v for line in lines for v in (line.get("values") or {}).values() if _num(v) is not None]
    if not vals or not years:
        return ""
    names = [line_label(line.get("label")) for line in lines]
    width, left, top, bottom = 400, 44, 10, 20
    right = min(max(60, 10 + 6 * max(len(n) for n in names)), 140)  # room for the longest direct label
    lo, hi = min(vals), max(vals)
    if unit == "%" and lo > 0:
        lo = 0
    if hi == lo:
        hi = lo + 1
    ticks = _ticks(lo, hi)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    plot_w, plot_h = width - left - right, height - top - bottom
    step = plot_w / max(len(years) - 1, 1)

    def xy(i, v):
        return left + i * step, top + (hi - v) / (hi - lo) * plot_h

    out = [f'<svg class="chart trend-chart" viewBox="0 0 {width} {height}" role="img"><title>{esc(title)}</title>'
           f'<desc>{esc(desc)}</desc>']
    shown = [(t, xy(0, t)[1]) for t in ((ticks[0], ticks[len(ticks) // 2], ticks[-1]) if len(ticks) > 2 else ticks)]
    out.append(f'<path class="grid" d="{"".join(f"M{left},{y:.0f}H{width - right}" for _, y in shown)}"/>')
    if lo < 0 < hi:
        out.append(f'<path class="axis" d="M{left},{xy(0, 0)[1]:.0f}H{width - right}"/>')
    out.append('<g class="tick" text-anchor="end">' + "".join(
        f'<text x="{left - 4}" y="{y + 3:.0f}">{esc(_fmt(t, unit))}</text>' for t, y in shown) + "</g>")
    groups = {"cash": [], "real": [], None: []}
    colour = Counter()  # colour by position within a basis, so cash and real lines match
    ends = []
    for line, name in zip(lines, names):
        basis = line.get("basis") if line.get("basis") in ("cash", "real") else None
        n = colour[basis]
        colour[basis] += 1
        values = line.get("values") or {}
        pts = [(i, _num(values.get(y))) for i, y in enumerate(years)]
        runs, marks, prev = {False: [], True: []}, [], None
        for (i0, v0), (i1, v1) in zip(pts, pts[1:]):
            if v0 is None or v1 is None:
                prev = None
                continue
            dashed = line.get("style") == "dashed" or years[i1] in partial
            (x0, y0), (x1, y1) = xy(i0, v0), xy(i1, v1)
            if prev != (dashed, i0):  # a new run: after a gap or a change of stroke
                runs[dashed].append(f"M{x0:.0f},{y0:.0f}")
            runs[dashed].append(f"L{x1:.0f},{y1:.0f}")
            prev = (dashed, i1)
        for i, v in pts:
            lone = v is not None and all(v2 is None for i2, v2 in pts if abs(i2 - i) == 1)
            if v is not None and (years[i] in suspect or lone):
                x, y = xy(i, v)
                marks.append(f'<circle class="{"hollow" if years[i] in suspect else "dot"}" cx="{x:.0f}" cy="{y:.0f}" r="3"/>')
        cls = f'tl l{n}{" emph" if line.get("emph") else ""}'
        body = "".join(f'<path class="{cls}{" dash" if dashed else ""}" d="{"".join(runs[dashed])}"/>'
                       for dashed in (False, True) if runs[dashed]) + "".join(marks)
        last = next(((i, v) for i, v in reversed(pts) if v is not None), None)
        if last and body:
            ends.append([xy(*last)[1], xy(*last)[0], name, basis])
        groups[basis].append(body)
    for basis, attrs in (("cash", ' data-basis="cash"'), ("real", ' data-basis="real" display="none"'), (None, "")):
        mine = sorted((e for e in ends if e[3] == basis), key=lambda e: e[0])
        for a, b in zip(mine, mine[1:]):  # keep direct labels apart
            if b[0] - a[0] < 11:
                b[0] = a[0] + 11
        labels = "".join(f'<text x="{x + 5:.0f}" y="{y + 3:.0f}">{esc(text)}</text>' for y, x, text, _ in mine)
        if groups[basis]:
            out.append(f"<g{attrs}>{''.join(groups[basis])}" + (f'<g class="lab">{labels}</g>' if labels else "") + "</g>")
    every = 1 if len(years) <= 5 else 2
    out.append(f'<g class="tick" text-anchor="middle">' + "".join(
        f'<text x="{xy(i, lo)[0]:.0f}" y="{height - 6}">{esc(y)}</text>'
        for i, y in enumerate(years) if (len(years) - 1 - i) % every == 0) + "</g>")  # always label the newest year
    out.append("</svg>")
    return "".join(out)


def trend_svg(lines, *, years, unit="£", title, desc, suspect=(), partial=()):
    lines = [line for line in lines if any(_num(v) is not None for v in (line.get("values") or {}).values())]
    if not lines:
        return ""
    chart = getattr(charts, "trend_chart", None) or fallback_trend
    return chart(lines, years=list(years), unit=unit, title=title, desc=desc, suspect=tuple(suspect), partial=tuple(partial))


def fallback_sparkline(values, *, width=96, height=24, label):
    pts = [(y, _num(v)) for y, v in values]
    pts = [(y, v) for y, v in pts if v is not None]
    if not pts:
        return ""
    lo, hi = min(min(v for _, v in pts), 0), max(max(v for _, v in pts), 0)
    span = (hi - lo) or 1
    step = (width - 4) / max(len(pts) - 1, 1)
    xy = [(2 + i * step, 2 + (hi - v) / span * (height - 4)) for i, (_, v) in enumerate(pts)]
    d = "M" + "L".join(f"{x:.0f},{y:.0f}" for x, y in xy)
    zero = 2 + hi / span * (height - 4)
    x, y = xy[-1]
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
            f'aria-label="{esc(label)}"><line class="zero" x1="0" x2="{width}" y1="{zero:.0f}" y2="{zero:.0f}"/>'
            f'<path d="{d}"/><circle cx="{x:.0f}" cy="{y:.0f}" r="2"/></svg>')


def spark(values, label):
    fn = getattr(charts, "sparkline", None) or fallback_sparkline
    values = [(y, v) for y, v in values if _num(v) is not None]
    return fn(values, label=label) if len(values) > 1 else ""


def describe(lines, unit):
    """Plain-language <desc>: each line's latest value."""
    parts = []
    for line in lines:
        values = {y: v for y, v in (line.get("values") or {}).items() if _num(v) is not None}
        if values and line.get("basis") != "real":
            year = max(values)
            parts.append(f"{line['label']} {year}: {_fmt(values[year], unit)}")
    return "; ".join(parts) + "." if parts else ""


def basis_toggle():
    return ('<div class="toggles" role="group" aria-label="Prices"><button type="button" data-basis-toggle="cash" '
            'aria-pressed="true">Cash</button><button type="button" data-basis-toggle="real" aria-pressed="false">'
            'Real terms</button></div>')


def unit_toggle():
    return ('<div class="toggles" role="group" aria-label="Show"><button type="button" data-unit-toggle="pp" '
            'aria-pressed="true">Per pupil</button><button type="button" data-unit-toggle="total" aria-pressed="false">'
            'Total</button></div>')


def card(title, svg, note="", toggles=""):
    if not svg:
        return ""
    return (f'<figure class="trend chart-card"><figcaption>{esc(title)}</figcaption>{toggles}{svg}'
            + (f'<p class="muted small">{note}</p>' if note else "") + "</figure>")


def chart_card(title, lines, years, *, unit="£", note="", partial=(), toggles=False, where=""):
    svg = trend_svg(lines, years=years, unit=unit, title=f"{title}{', ' + where if where else ''}",
                    desc=describe(lines, unit), partial=partial)
    return card(title, svg, note, basis_toggle() if toggles and any(l.get("basis") == "real" for l in lines) else "")


# ----------------------------------------------------------------- dashboard measures

def comparators(kind, area, ctx, items):
    """[(label, A)] to draw beside the area: its region and England, as far as they apply."""
    doc = areas_doc(ctx)
    out = []
    if kind in ("council", "constituency"):
        region = area.get("region")
        if not region:
            seen = Counter((i.get("council") or {}).get("region") for i in items or [])
            seen.pop(None, None)
            region = seen.most_common(1)[0][0] if seen else None
        if region and (doc.get("regions") or {}).get(region):
            out.append((region, doc["regions"][region]))
    if kind != "england" and doc.get("england"):
        out.append(("England", doc["england"]))
    return out


def dashboard_years(area, others):
    years = set(by_year(area))
    for _, other in others:
        years.update(by_year(other))
    return sorted(y for y in years if y >= FROM_YEAR)


def measure_lines(name, area, others, key, years, *, basis=None, council_run=True):
    """The area (heavier), its region and England; plus the area's council-run schools, dashed,
    when there are years after the all-schools series stops."""
    lines = [{"label": name, "values": series(area, key, years), "style": "solid", "emph": True, "basis": basis}]
    for label, other in others:
        lines.append({"label": label, "values": series(other, key, years), "style": "solid", "emph": False, "basis": basis})
    last = (area or {}).get("combined_last_year")
    if council_run and last and any(y > last for y in years):
        lines.append({"label": "Council-run", "values": series(area, key, years, "council-run"),
                      "style": "dashed", "emph": False, "basis": basis})
    return lines


def dsg_values(area, years, field):
    out = {}
    for year in years:
        entry = ((area or {}).get("dsg") or {}).get(year)
        value = entry.get(field) if isinstance(entry, dict) else None
        if _num(value) is not None:
            out[year] = value
    return out


def pupil_change(area, base, years):
    """{year: % change in pupils since base}: areas of very different sizes share one axis."""
    pupils = (area or {}).get("pupils_by_year") or {}
    start = _num(pupils.get(base))
    if not start:
        return {}
    return {y: (pupils[y] / start - 1) * 100 for y in years if _num(pupils.get(y)) is not None}


def pupils_text(value):
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def dashboard_charts(kind, name, area, others, ctx, budget):
    """Every measure as a chart card, most useful first. Each measure is always drawn; when the
    cards would pass budget bytes, notes the page already carries are left off the cards."""
    full = measure_cards(kind, name, area, others, ctx, brief=False)
    if len("".join(full).encode("utf-8")) > budget:
        full = measure_cards(kind, name, area, others, ctx, brief=True)
    kept = [html for html in full if html]
    return f'<div class="chart-grid">{"".join(kept)}</div>' if kept else ""


def measure_cards(kind, name, area, others, ctx, brief):
    """The dashboard's chart cards in order. brief drops the sector note, which the page states
    beside the charts, and trims the high-needs note to its first sentence."""
    years = dashboard_years(area, others)
    if not years:
        return []

    def chart(*args, **kwargs):
        return chart_card(*args, where=name, **kwargs)

    last = area.get("combined_last_year") or (combined_years(area) or [None])[-1]
    partial = [y for y in years if last and y > last]
    real = deflator_label(ctx)
    sector = "" if brief else esc(SECTOR_NOTE.format(last=last or "the latest year"))
    cards = []
    deficit_lines = [{"label": "All schools", "values": series(area, "in_deficit_pct", years), "emph": True},
                     {"label": "Council-run", "values": series(area, "in_deficit_pct", years, "council-run"),
                      "style": "dashed"},
                     {"label": "Academies", "values": series(area, "in_deficit_pct", years, "academy"),
                      "style": "dashed"}]
    deficit_lines += [{"label": label, "values": series(other, "in_deficit_pct", years)} for label, other in others]
    cards.append(chart("Share of schools in deficit", deficit_lines, years, unit="%", note=sector))
    gov = []
    for basis, gkey, skey in (("cash", "gov_pp_median", "spend_pp_median"), ("real", "gov_rpp_median", "spend_rpp_median")):
        if basis == "real" and not real:
            continue
        for label, source in [(None, area)] + list(others):  # the area (heavier), its region, England
            own = label is None
            gov.append({"label": "Funding" if own else f"{label} funding", "values": series(source, gkey, years),
                        "emph": own, "basis": basis})
            gov.append({"label": "Spending" if own else f"{label} spending", "values": series(source, skey, years),
                        "style": "dashed", "emph": own, "basis": basis})
    note = (esc(GOV_NOTE) + " Solid lines are funding, dashed lines spending."
            + (f" Real terms are {esc(real)}." if real else "") + " " + academy_note(ctx))
    cards.append(chart("Government funding and spending per pupil", gov, years, note=note, toggles=True))
    cards.append(chart("Median reserve per pupil", measure_lines(name, area, others, "reserve_median_pp", years),
                            years, partial=partial, note="The dashed line is council-run schools only."))
    cards.append(chart("Deficits per pupil, in schools in deficit", measure_lines(name, area, others, "deficit_pp", years),
                            years, partial=partial, note="Each area's combined school deficits divided by the pupils in those schools."))
    if kind in ("council", "england") and (area.get("dsg") or {}):
        dyears = sorted(y for y in area["dsg"] if y >= FROM_YEAR)
        pp_lines = [{"label": name, "values": dsg_values(area, dyears, "per_pupil"), "emph": True}]
        pp_lines += [{"label": label, "values": dsg_values(other, dyears, "per_pupil")} for label, other in others]
        title = "Council high-needs (DSG) balance"
        pp_svg = trend_svg(pp_lines, years=dyears, title=f"{title} per pupil, {name}", desc=describe(pp_lines, "£"))
        total_lines = [{"label": name, "values": dsg_values(area, dyears, "balance"), "emph": True}]
        total_svg = trend_svg(total_lines, years=dyears, title=f"{title}, {name}", desc=describe(total_lines, "£"))
        if pp_svg:
            body = f'<div data-unit="pp">{pp_svg}</div>' + (f'<div data-unit="total" hidden>{total_svg}</div>' if total_svg else "")
            note = "Negative is a deficit carried forward, in cash terms."
            if not brief:
                note += (" Per pupil divides by pupils at the schools on this site; a school whose return for the year "
                         "is not yet published counts its previous year's roll.")
            cards.append(card(title, body, esc(note), unit_toggle() if total_svg else ""))
    cards.append(chart("Median parents' association income per pupil",
                            measure_lines(name, area, others, "pta_pp_median", years, council_run=False), years,
                            note=esc("Among schools with a registered parents' association, in the school year each "
                                     "charity return falls in.")))
    cards.append(chart("Pupils eligible for free school meals (median school)",
                            measure_lines(name, area, others, "fsm_pct", years, council_run=False), years, unit="%"))
    own = {y: v for y, v in ((area.get("pupils_by_year") or {}).items()) if y >= FROM_YEAR and _num(v)}
    if own:
        base, newest = min(own), max(own)
        pupil_lines = [{"label": label, "values": pupil_change(source, base, years), "emph": label == name}
                       for label, source in [(name, area)] + list(others)]
        pyears = sorted({y for line in pupil_lines for y in line["values"]})
        cards.append(chart("Pupils in schools with a full-year return", pupil_lines, pyears, unit="%",
                           note=esc(f"Change in pupils since {base}, so areas of different sizes can be compared. "
                                    f"{name} had {pupils_text(own[newest])} pupils in schools with a full-year return "
                                    f"in {newest}.")))
    return cards


def academy_note(ctx):
    found = ifs_line(ctx, "school", "trust_central")
    if not found:
        return ""
    return f"Academy figures exclude trust central spending: {found[0]}{cite(found[1])}"


def ifs_context(ctx, council=False):
    """The IFS figures every dashboard quotes: spend per pupil by phase, the outlook and, for
    councils and England, the high-needs deficits with the statutory-override note beside them."""
    parts = []
    for ident in ("per_pupil_primary", "per_pupil_secondary"):
        found = ifs_line(ctx, "school", ident)
        if found:
            parts.append(f"<li>{found[0]}{cite(found[1])}</li>")
    for ident in ("outlook_3pct",):
        found = ifs_line(ctx, "national", ident)
        if found:
            parts.append(f"<li>{found[0]}{cite(found[1])}</li>")
    body = ""
    if parts:
        body = (f'<ul class="ifs-list">{"".join(parts)}</ul><p class="muted small">Area medians mix primary and secondary '
                'schools, so compare them with these national figures with care.</p>')
    if council:
        body += council_ifs_lines(ctx, {"high_needs_deficits", "high_needs_top_up", "ehcp_share"})
    return f'<section class="context"><h2>The national picture</h2>{body}</section>' if body else ""


def lead(name, area, others, ctx=None):
    year, s = latest_combined(area)
    if not s or s.get("in_deficit") is None:
        return (f'<p class="lead">Too few schools in {esc(name)} have published full-year returns to show area '
                'figures yet; the table lists every school we hold.</p>')
    text = (f'In {esc(year)}, <strong>{s["in_deficit"]:,} of the {s["schools"]:,}</strong> schools in {esc(name)} with a '
            f'full-year return were in deficit ({s["in_deficit_pct"]:.1f}%)')
    england = dict(others).get("England")
    e = split_of(england, year) if england else None
    if e and e.get("in_deficit_pct") is not None:
        text += f", against {e['in_deficit_pct']:.1f}% across England"
    text += ". "
    cr_year, cr = latest_split(area, "council-run")
    if cr and cr_year and year and cr_year > year:
        text += (f"In {esc(cr_year)}, the latest council-run year, {cr['in_deficit']:,} of {cr['schools']:,} council-run "
                 f"schools were in deficit ({cr['in_deficit_pct']:.1f}%). ")
    costs = ifs_line(ctx, "school", "costs_outpaced_funding")
    why = f" {costs[0]}{cite(costs[1])}" if costs else ""
    return f'<p class="lead">{text}</p><p>{esc(REASONS)}{why} {esc(HELPS)}</p>'


def headline(area):
    """Headline tiles for an area: the newest all-schools year, and the newest council-run year
    and DSG balance where they are later."""
    year, s = latest_combined(area or {})
    tiles = []
    if s and s.get("in_deficit") is not None:
        tiles.append((f"Schools in deficit, {year}", f'{s["in_deficit_pct"]:.1f}% <small>({s["in_deficit"]:,} of {s["schools"]:,})</small>'))
        total, dpp = s.get("deficit_total"), s.get("deficit_pp")
        if _num(total) and _num(dpp):
            tiles.append((f"Combined school deficits, {year}",
                          money_figure("deficit_total", abs(total), abs(total / dpp), year)))
        if _num(s.get("reserve_median_pp")) is not None:
            tiles.append((f"Median reserve per pupil, {year}", pp_fig("reserve_median_pp", s["reserve_median_pp"], year, signed=True)))
    cr_year, cr = latest_split(area or {}, "council-run")
    if cr and cr_year and (not year or cr_year > year):
        tiles.append((f"Council-run schools in deficit, {cr_year}", f'{cr["in_deficit_pct"]:.1f}% <small>(council-run only)</small>'))
    dsg = (area or {}).get("dsg") or {}
    dyear = max((y for y, d in dsg.items() if isinstance(d, dict) and _num(d.get("balance")) is not None), default=None)
    if dyear:
        balance = dsg[dyear]["balance"]
        pp = dsg[dyear].get("per_pupil")
        pupils = balance / pp if _num(pp) else None
        tiles.append((f"High-needs (DSG) balance, {dyear}", money_figure("dsg_balance", balance, pupils, dyear, signed=True)))
    if not tiles:
        return ""
    return '<div class="tiles headline">' + "".join(
        f'<div class="tile"><div class="tlabel">{esc(k)}</div><div class="tvalue">{v}</div></div>' for k, v in tiles) + "</div>"


# ----------------------------------------------------------------- school rows

def item_tags(item):
    """(data-tags string, {group:value: label}) per the TABLE DOM contract. Governance follows
    the latest return's source (an academy files AAR), not today's register."""
    given = item.get("tags")
    school = item.get("school") or {}
    latest = item.get("latest") or {}
    gov = "academy" if latest.get("source") == "AAR" or (not latest and item.get("academy")) else "council-run"
    phase = agg.phase_tag(latest.get("phase") or item.get("phase"), school) or "other"
    adm = agg.admissions_tag(school) or "non-selective"
    faith = agg.faith_tag(school)
    labels = {f"governance:{gov}": GOV_LABELS[gov], f"phase:{slug(phase)}": VALUE_LABELS.get(slug(phase), phase.title()),
              f"admissions:{slug(adm)}": VALUE_LABELS.get(slug(adm), adm.title()),
              f"faith:{slug(faith) if faith else 'none'}": faith or VALUE_LABELS["none"]}
    if isinstance(given, str) and ":" in given:
        return given, {t: labels.get(t, t.partition(":")[2].replace("-", " ").title()) for t in given.split()}
    return " ".join(labels), labels


def filters(rows_tags):
    """The table-filters block from every row's tags: one button per value seen, by group."""
    counts, names = Counter(), {}
    for tags, labels in rows_tags:
        for tag in tags.split():
            counts[tag] += 1
            names[tag] = labels.get(tag, tag)
    groups = []
    for group, title in GROUP_LABELS.items():
        values = sorted((t for t in counts if t.startswith(group + ":")), key=lambda t: (-counts[t], t))
        if len(values) < 2:
            continue
        buttons = "".join(f'<button type="button" data-filter="{esc(t)}" aria-pressed="false">{esc(names[t])} '
                          f'<span class="n">{counts[t]:,}</span></button>' for t in values)
        groups.append(f'<div role="group" aria-label="{esc(title)}"><span class="fl">{esc(title)}</span>{buttons}</div>')
    if not groups:
        return ""
    return f'<div class="table-filters" data-filters>{"".join(groups)}</div>'


def history_status(charity):
    """B4's history_status, else derived the same way from the history."""
    if charity.get("history_status"):
        return charity["history_status"], charity.get("last_income_year"), charity.get("removed_year")
    years = [int(str(h.get("period_end"))[:4]) for h in charity.get("history") or []
             if str(h.get("period_end") or "")[:4].isdigit() and (h.get("income") or 0) > 0]
    last = max(years) if years else None
    removed = str(charity.get("removed") or "")[:4]
    status = "current" if last and last >= 2024 else "recent" if last and last >= 2019 else "historical"
    return status, last, int(removed) if removed.isdigit() else None


def school_pta(item, window=None):
    """The school's latest PTA year, or with window [first, newest] its latest year inside it:
    {"label", "income", "spend", "pupils", "confidence", "number"}, or {"note": wording} when it
    has none to show."""
    charities = [c for c in item.get("pta") or [] if not c.get("review")]
    if not charities:
        return {"note": NOT_FOUND}
    usable = [c for c in charities if not agg.held_back(c)]
    if not usable:
        return {"note": "Held for review"}
    statuses = [history_status(c) for c in usable]
    if all(status == "historical" for status, _, _ in statuses):
        until = max((removed or last or 0) for _, last, removed in statuses)
        return {"note": f"Had a registered PTA until {until}" if until else "Registered, no income filed yet"}
    years = item.get("years") or []
    slots = agg.school_pta(years, usable)
    if window:
        slots = {key: slot for key, slot in slots.items() if window[0] <= key[0] <= window[1]}
    if not slots:
        return {"note": "Registered, no income filed yet"}
    (label, source), slot = max(slots.items(), key=lambda kv: kv[0][0])
    row = next((r for r in reversed(years) if agg.label_of(r) == label and r.get("source") == source), None)
    pupils = row.get("pupils") if row and "pupils" not in (row.get("suspect") or []) else None
    return {"label": label, "income": slot["income"], "spend": slot["spend"], "pupils": pupils,
            "confidence": slot["confidence"], "number": max(slot["by_charity"], key=slot["by_charity"].get)}


RESERVE_SUSPECT = {"pupils", "revenue_reserve", "revenue_reserve_incl_trust_share"}


def reserve_spark(item):
    """Reserve per pupil by year. The sparkline cannot mark a point hollow, so a year whose
    pupils or either reserve figure is suspect (as the table cell beside it shows) is left out."""
    values = []
    for r in item.get("years") or []:
        suspect = set(r.get("suspect") or [])
        pupils = r.get("pupils")
        reserve = r.get("revenue_reserve_incl_trust_share")
        reserve = r.get("revenue_reserve") if reserve is None else reserve
        if pupils and _num(reserve) is not None and not suspect & RESERVE_SUSPECT:
            values.append((agg.label_of(r), reserve / pupils))
    return spark(values, "Reserve per pupil by year")


def school_cells(item):
    """One school row (TABLE DOM): tags and link, status, then latest-year figures per pupil."""
    urn, latest, st = str(item["urn"]), item.get("latest") or {}, item.get("status")
    tags, labels = item_tags(item)
    link = f'<a href="{esc(item.get("path") or "/school/" + urn + "/")}" data-preview="school:{esc(urn)}">{esc(item.get("name") or urn)}</a>'
    cells = [f'<span data-tags="{esc(tags)}">{link}</span>']
    if st:
        cells.append(sort(st.get("rank", STATUS_ORDER.index(st["status"])), badge(st["status"], "small")))
    else:
        why = "In a combined federation return" if item.get("member_of") else "No full-year return"
        cells.append(sort(9, f'<span class="muted">{why}</span>'))
    year, pupils = label_of(latest.get("year")), latest.get("pupils")
    suspect = set(latest.get("suspect") or [])
    if "pupils" in suspect:
        pupils = None
    check = f"{FBIT}/school/{urn}"

    def fig(key, value, *, drill=None, src=None, signed=False, bad=()):
        if _num(value) is None:
            return sort(None, '<span class="muted">—</span>')
        flagged = bool(suspect & set(bad or (key,)))
        html = money_figure(key, value, pupils, year, src=src, signed=signed, cls="suspect" if flagged else "",
                            drill=f"/data/sx/{urn}.json#m:{drill}" if drill and st else None)
        return sort(None if flagged else (value / pupils if pupils else value), html)

    reserve = latest.get("revenue_reserve_incl_trust_share")
    reserve = latest.get("revenue_reserve") if reserve is None else reserve
    cells.append(fig("revenue_reserve", reserve, drill="revenue_reserve", src=check, signed=True,
                     bad=("revenue_reserve", "revenue_reserve_incl_trust_share")))
    cells.append(fig("grant_funding_government", agg.government_funding(latest) if latest else None,
                     drill="grant_funding_government"))
    cells.append(fig("total_expenditure", latest.get("total_expenditure"), drill="total_expenditure"))
    pta = school_pta(item)
    if "note" in pta:
        cells += [sort(None, f'<span class="muted">{esc(pta["note"])}</span>'), sort(None, '<span class="muted">—</span>')]
    else:
        low = ' <small>matched with lower confidence</small>' if pta["confidence"] != "high" else ""
        cells.append(sort(pta["income"], money_figure("pta_income", pta["income"], pta["pupils"], pta["label"]) + low))
        pp = pta["income"] / pta["pupils"] if pta["pupils"] else None
        cells.append(sort(pp, pp_fig("pta_per_pupil", pp, pta["label"])))
    cells.append(fig("donations_revenue", latest.get("donations_revenue")))
    cells.append(reserve_spark(item))
    return cells, (tags, labels)


SCHOOL_HEADERS = ["School", "Status", "Reserve", "Government funding", "Spending", "PTA income", "PTA per pupil",
                  "Donations", "Reserve per pupil trend"]


def school_order(item):
    st = item.get("status")
    if not st:
        return (9, 0, item.get("name") or "")
    return (st.get("rank", STATUS_ORDER.index(st["status"])), st.get("reserve_share") or 0, item.get("name") or "")


def school_table(items, caption):
    rows, tags = [], []
    for item in sorted(items or [], key=school_order):
        cells, tag = school_cells(item)
        rows.append(cells)
        tags.append(tag)
    if not rows:
        return None
    return {"headers": SCHOOL_HEADERS, "rows": rows, "caption": caption, "filters": filters(tags)}


TABLE_NOTE = ("Figures are each school's latest full-year return, total with the per-pupil figure beside it. PTA income "
              "is the school's share of its registered parents' association's latest return, in the school year that "
              "return falls in. Where no registered parents' association was found, the school may still have one: "
              "charities with an income of {limit} or less need not register.")


def table_note():
    return f'<p class="muted small">{esc(TABLE_NOTE).replace("{limit}", amount("pta_income", 5000))}</p>'


# ----------------------------------------------------------------- council rows (league)

COUNCIL_HEADERS = ["Council", "Schools", "In deficit", "Deficit per pupil", "Median reserve per pupil",
                   "Government funding per pupil", "Spending per pupil", "High-needs (DSG) balance per pupil", "Trend"]


def council_cells(ctx, code, a, england=None):
    year, s = latest_combined(a)
    s = s or {}
    e = split_of(england, year) if england and year else None
    dsg = a.get("dsg") or {}
    dyear = max((y for y, d in dsg.items() if isinstance(d, dict) and _num(d.get("per_pupil")) is not None), default=None)
    dpp = dsg[dyear]["per_pupil"] if dyear else None
    trend = [(y, (split_of(a, y) or {}).get("in_deficit_pct")) for y in combined_years(a) if y >= FROM_YEAR]

    def cell(key, glossary, signed=False):
        value = s.get(key)
        return sort(value, pp_fig(glossary, value, year, signed=signed, england=(e or {}).get(key)))

    return [council_link(ctx, code, a.get("name")), sort(s.get("schools"), f'{s.get("schools") or 0:,}'),
            sort(s.get("in_deficit_pct"), pct_text(s)), cell("deficit_pp", "deficit_pp", True),
            cell("reserve_median_pp", "reserve_median_pp", True), cell("gov_pp_median", "gov_funding_pp"),
            cell("spend_pp_median", "spend_pp"), sort(dpp, pp_fig("dsg_per_pupil", dpp, dyear, signed=True)),
            spark(trend, "Share of schools in deficit by year")]


def council_rows(ctx, council_areas):
    england = areas_doc(ctx).get("england")
    ordered = sorted(council_areas.items(), key=lambda kv: (-((latest_combined(kv[1])[1] or {}).get("in_deficit_pct") or -1),
                                                            str(kv[1].get("name"))))
    return [council_cells(ctx, code, a, england) for code, a in ordered]


# ----------------------------------------------------------------- renderers

def pin_id(kind, area_id, path):
    if kind == "england":
        return "england"
    if kind == "council":
        return f"council-{area_id}"
    tail = (path or "").strip("/").split("/")[-1] or slug(area_id)
    return f"{kind}-{tail}"


def area_path(kind, area_id, area, ctx):
    if kind == "england":
        return "/england/"
    if kind == "council":
        return council_path(ctx, area_id, area.get("name"))
    if kind == "region":
        return region_path(ctx, area.get("name") or area_id)
    return paths(ctx, "constituency").get(str(area_id)) or area.get("path") or f"/constituency/{slug(area.get('name') or area_id)}/"


def fit(intro_parts, outro, budget=PAGE_TEXT_BUDGET):
    """Join intro parts, dropping optional ones from the end until intro + outro fit the budget."""
    parts = list(intro_parts)
    while parts and len("".join(p for p, _ in parts).encode("utf-8")) + len(outro.encode("utf-8")) > budget:
        optional = [n for n, (_, keep) in enumerate(parts) if not keep]
        if not optional:
            break
        parts.pop(optional[-1])
    return "".join(p for p, _ in parts)


def render_area(kind, area_id, area, items, ctx):
    """England, region, council or constituency dashboard. Council and constituency tables list
    the area's schools; England and region tables list councils."""
    area = area or {}
    name = area.get("name") or str(area_id)
    path = area_path(kind, area_id, area, ctx)
    others = comparators(kind, area, ctx, items)
    assessed = [i for i in items or [] if i.get("status")]
    heading = {"england": "School finances in England", "region": f"School finances in {name}",
               "council": f"{name} school finances", "constituency": f"Schools in {name}: finances"}[kind]
    head = f'<h1>{esc(heading)}</h1><p class="status-line">{pin_button("area", pin_id(kind, area_id, path), name, path)}</p>'
    sector = f'<p class="muted small">{esc(SECTOR_NOTE.format(last=area.get("combined_last_year") or "the latest year"))}</p>'
    if kind in ("council", "constituency"):
        table = school_table(items, f"Schools in {name}, latest full-year return")
        check = (f' Check at source: <a href="{FBIT}/local-authority/{esc(area_id)}">DfE benchmarking for {esc(name)}</a>.'
                 if kind == "council" else "")
    else:
        doc = areas_doc(ctx)
        codes = {str((i.get("council") or {}).get("code")) for i in items or [] if (i.get("council") or {}).get("code")}
        councils = {c: a for c, a in (doc.get("councils") or {}).items() if (not codes and kind == "england") or c in codes}
        rows = council_rows(ctx, councils)
        table = {"headers": COUNCIL_HEADERS, "rows": rows, "caption": f"Councils in {name}", "filters": ""} if rows else None
        check = ""
    outro = sources(check)
    status_counts = area.get("statuses_latest") or Counter(i["status"]["status"] for i in assessed)
    dsg_text = ""
    if kind == "council" and (area.get("dsg") or {}):
        flags = dsg_flags(ctx, area_id)
        if flags:
            dsg_text = (f'<p class="muted small">{esc(name)} is in the DfE {esc(" and ".join(flags))} programme for councils '
                        'with large high-needs deficits: it agrees a plan with the DfE to bring the budget back into balance.</p>')
    fixed = [(head, True), (lead(name, area, others, ctx), True), (headline(area), True), (sector, True)]
    base = len("".join(p for p, _ in fixed).encode("utf-8")) + len(outro.encode("utf-8"))
    context = ifs_context(ctx, council=kind in ("council", "england"))
    extras = (charts.status_bar(status_counts) if status_counts else "") + dsg_text
    notes = table_note() if kind in ("council", "constituency") else ""
    room = PAGE_TEXT_BUDGET - base - sum(len(p.encode("utf-8")) for p in (context, extras, notes)) - 600
    grid = dashboard_charts(kind, name, area, others, ctx, max(room, 0))
    # Every measure is required; only the status bar and programme line give way to the budget.
    intro = fit(fixed + [(extras, False), (grid, True), (context, True), (notes, True)], outro)
    n_def = sum(1 for i in assessed if i["status"]["status"] == "in_deficit")
    year, s = latest_combined(area)
    if kind in ("council", "constituency") and assessed:
        description = (f"{n_def} of {len(assessed)} schools in {name} were in deficit at their latest return. Trends since "
                       f"{FROM_YEAR}, funding and spending per pupil, reserves and parents' associations.")
    elif s and s.get("in_deficit") is not None:
        description = (f"{s['in_deficit_pct']:.1f}% of schools in {name} were in deficit in {year}. Trends since "
                       f"{FROM_YEAR}, funding and spending per pupil, reserves, high-needs balances and councils compared.")
    else:
        description = f"School finances in {name}: deficits, reserves, funding and spending per pupil from DfE returns."
    indexable = bool(assessed) or bool(s and s.get("schools"))
    return {"title": title_of(heading), "description": shorten(description, 160), "intro": intro, "table": table,
            "outro": outro, "indexable": indexable}


def dsg_flags(ctx, code):
    inter = (((ctx or {}).get("dsg") or {}).get("interventions")) or {}
    flags = []
    if str(code) in {str(c) for c in inter.get("safety_valve") or []}:
        flags.append("safety valve")
    if str(code) in {str(c) for c in inter.get("delivering_better_value") or []}:
        flags.append("delivering better value")
    return flags


def render_council_league(council_areas, ctx):
    """Every council, per pupil, most schools in deficit first, with a sparkline each."""
    council_areas = council_areas or {}
    rows = council_rows(ctx, council_areas)
    england = areas_doc(ctx).get("england")
    year, s = latest_combined(england or {})
    intro = ('<h1>School finances by council</h1><p class="lead">Every council in England: the share of its schools in '
             'deficit, the size of those deficits per pupil, and the middle school\'s reserve, government funding and '
             'spending per pupil'
             + (f", for {esc(year)}" if year else "") + '.</p>'
             f'<p>{esc(REASONS)} {esc(HELPS)}</p>' + headline(england or {})
             + f'<p class="muted small">{esc(GOV_NOTE)} {esc(SECTOR_NOTE.format(last=year or "the latest year"))}</p>'
             + council_ifs_lines(ctx, {"high_needs_deficits"}))
    outro = sources()
    return {"title": title_of("School finances by council"),
            "description": shorten("Every council in England compared per pupil: schools in deficit, deficits, reserves, "
                                   "funding, spending and high-needs balances, from DfE returns.", 160),
            "intro": intro, "table": {"headers": COUNCIL_HEADERS, "rows": rows, "caption": "Councils in England",
                                      "filters": ""} if rows else None,
            "outro": outro, "indexable": bool(rows)}


def central_compare(trust_area, ctx):
    """The trust's central spend per pupil beside the IFS average (£510 per pupil in 2023-24, in
    2025-26 prices). The IFS figure is always quoted with its own year: a trust with no 2023-24
    figure is shown for its latest year, which is not the year the IFS observed."""
    central = (trust_area or {}).get("central_pp") or {}
    found = ifs_line(ctx, "school", "trust_central")
    ifs = ((((ctx or {}).get("ifs") or {}).get("national") or {}).get("academies") or {}).get("trust_central_spend") or {}
    ifs_value = _num(ifs.get("value")) or 510
    ifs_year = label_of(ifs.get("year") or "2023-24").replace("–", "-")
    if not central:
        return f'<p class="ifs">{found[0]}{cite(found[1])}</p>' if found else ""
    year = ifs_year if ifs_year in central else max(central)
    value = central[year]
    text = (f'<p>In {esc(year)} the trust spent {pp_fig("trust_central_spend_pp", value, year)} per pupil centrally '
            '(cash), money that is not counted in its academies\' own spending')
    real = None
    if deflator is not None:
        try:
            real = deflator.to_real(value, year, "AAR")
        except (KeyError, TypeError, ValueError):
            real = None
    if _num(real) is not None:
        text += f', or {pp_fig("trust_central_spend_pp", real, year)} in 2025–26 prices'
    text += (f'. The IFS average for all trusts in {esc(ifs_year)} was {ifs_fig(exact(ifs_value), ifs_value)} per pupil, '
             f'in 2025–26 prices{cite(ifs.get("page") or 56)}')
    if year != ifs_year:
        text += f"; the trust's figure above is for {esc(year)}, so the two are for different years"
    return text + ".</p>"


def render_trust(trust_area, items, ctx):
    trust_area = trust_area or {}
    name = trust_area.get("name") or "Academy trust"
    path = trust_area.get("path") or trust_path(ctx, name)
    items = items or []
    years = sorted(y for y in by_year(trust_area) if y >= FROM_YEAR)
    england = areas_doc(ctx).get("england")
    lines = [{"label": name, "values": series(trust_area, "in_deficit_pct", years), "emph": True},
             {"label": "England academies", "values": series(england, "in_deficit_pct", years, "academy")}]
    count_rows = []
    for year in years:
        s = split_of(trust_area, year) or {}
        if s.get("schools") and s.get("in_deficit") is not None:
            count_rows.append(f"<li>{esc(year)}: {s['in_deficit']:,} of {s['schools']:,} academies in deficit</li>")
    central = trust_area.get("central_pp") or {}
    central_lines = []
    if central:
        cyears = sorted(central)
        central_lines.append({"label": "Cash", "values": central, "emph": True, "basis": "cash"})
        if deflator is not None:
            real = {}
            for y, v in central.items():
                try:
                    real[y] = deflator.to_real(v, y, "AAR")
                except (KeyError, TypeError, ValueError):
                    pass
            if real and deflator_label(ctx):
                central_lines.append({"label": "Real terms", "values": real, "emph": True, "basis": "real"})
    assessed = [i for i in items if i.get("status")]
    n_def = sum(1 for i in assessed if i["status"]["status"] == "in_deficit")
    company = trust_area.get("company_number")
    head = (f'<h1>{esc(name)}: academy finances</h1><p class="lead">{len(assessed):,} academies with a full-year return'
            + (f", {n_def:,} of them in deficit at their latest return" if assessed else "") + f'. {esc(TRUST_NOTE)}</p>'
            f'<p>{esc(REASONS)} {esc(HELPS)}</p>')
    grid = chart_card("Share of the trust's academies in deficit", lines, years, unit="%")
    if central_lines:
        grid += chart_card("Trust central spending per pupil", central_lines, sorted(central), toggles=True,
                           note=esc(deflator_label(ctx) or ""))
    body = head + (f'<ul class="year-counts">{"".join(count_rows)}</ul>' if count_rows else "")
    check = f' Check at source: <a href="{FBIT}/trust/{esc(company)}">DfE benchmarking for this trust</a>.' if company else ""
    outro = sources(check)
    intro = fit([(body, True), (f'<div class="chart-grid">{grid}</div>' if grid else "", False),
                 (central_compare(trust_area, ctx) + table_note(), True)], outro)
    table = school_table(items, f"Academies in {name}, latest full-year return")
    return {"title": title_of(f"{name} academy finances"),
            "description": shorten(f"{name}: {len(assessed)} academies, {n_def} in deficit at their latest return. Reserves, "
                                   "funding and spending per pupil, central spending and parents' associations.", 160),
            "intro": intro, "table": table, "outro": outro, "indexable": bool(assessed)}


TRUST_HEADERS = ["Trust", "Academies", "In deficit", "Median reserve per pupil", "Central spending per pupil", "Trend"]


def render_trust_index(trust_areas, ctx):
    trust_areas = trust_areas or {}
    rows = []
    for key, a in sorted(trust_areas.items(), key=lambda kv: str(kv[1].get("name") or kv[0]).casefold()):
        name = a.get("name") or key
        year, s = latest_combined(a)
        s = s or {}
        schools = s.get("schools") or max((a.get("schools_by_year") or {}).values(), default=0)
        central = a.get("central_pp") or {}
        cyear = max(central, default=None)
        trend = [(y, (split_of(a, y) or {}).get("in_deficit_pct")) for y in combined_years(a) if y >= FROM_YEAR]
        rows.append([f'<a href="{esc(trust_path(ctx, name, a.get("path")))}">{esc(name)}</a>', sort(schools, f"{schools:,}"),
                     sort(s.get("in_deficit_pct"), pct_text(s)),
                     sort(s.get("reserve_median_pp"), pp_fig("reserve_median_pp", s.get("reserve_median_pp"), year, signed=True)),
                     sort(central.get(cyear), pp_fig("trust_central_spend_pp", central.get(cyear), cyear)),
                     spark(trend, "Share of academies in deficit by year")])
    found = ifs_line(ctx, "school", "trust_central")
    intro = ('<h1>Academy trust finances</h1><p class="lead">Every academy trust in England with its academies\' latest '
             'share in deficit, the middle academy\'s reserve per pupil and the trust\'s own central spending per pupil.</p>'
             f'<p>{esc(TRUST_NOTE)} {esc(REASONS)} {esc(HELPS)}</p>'
             + (f'<p class="ifs">{found[0]}{cite(found[1])} Central spending here is cash for each year.</p>' if found else "")
             + '<p class="muted small">Area figures are withheld for trusts with fewer than five academies.</p>')
    outro = sources()
    return {"title": title_of("Academy trust finances in England"),
            "description": shorten("Academy trusts in England: academies in deficit, reserves per pupil and central "
                                   "spending per pupil against the IFS average, from DfE accounts returns.", 160),
            "intro": intro, "table": {"headers": TRUST_HEADERS, "rows": rows, "caption": "Academy trusts", "filters": ""}
            if rows else None, "outro": outro, "indexable": bool(rows)}


DEBT_YEARS = 3


def render_debts(areas_doc_, ctx):
    """/debts/: school deficits by council and year (academies apart), council DSG deficits with
    their DfE programmes, the statutory override and the IFS council context."""
    doc = (areas_doc_ or {}).get("areas") if isinstance((areas_doc_ or {}).get("areas"), dict) else (areas_doc_ or {})
    england = doc.get("england") or {}
    councils = doc.get("councils") or {}
    def split_years(split):
        return sorted({y for a in councils.values() for y in by_year(a) if (split_of(a, y, split) or {}).get("schools")})[-DEBT_YEARS:]

    cr_years, ac_years = split_years("council-run"), split_years("academy")
    ac_year = ac_years[-1] if ac_years else None
    headers = (["Council", "Council-run schools in deficit"] + [f"Council-run deficits {y}" for y in cr_years]
               + [f"Academies in deficit {ac_year or ''}".strip()] + [f"Academy deficits {y}" for y in ac_years]
               + ["High-needs (DSG) balance", "DfE programme"])
    rows = []
    for code, a in sorted(councils.items(), key=lambda kv: str(kv[1].get("name"))):
        cr_year, cr = latest_split(a, "council-run")
        cells = [council_link(ctx, code, a.get("name")), sort((cr or {}).get("in_deficit_pct"), pct_text(cr))]
        for year in cr_years:
            cells.append(deficit_cell(split_of(a, year, "council-run"), year))
        ac = split_of(a, ac_year, "academy") if ac_year else None
        cells.append(sort((ac or {}).get("in_deficit_pct"), pct_text(ac)))
        for year in ac_years:
            cells.append(deficit_cell(split_of(a, year, "academy"), year))
        dsg = a.get("dsg") or {}
        dyear = max((y for y, d in dsg.items() if isinstance(d, dict) and _num(d.get("balance")) is not None), default=None)
        if dyear:
            d = dsg[dyear]
            pupils = d["balance"] / d["per_pupil"] if _num(d.get("per_pupil")) else None
            cells.append(sort(d.get("per_pupil"), money_figure("dsg_balance", d["balance"], pupils, dyear, signed=True)))
        else:
            cells.append(sort(None, '<span class="muted">—</span>'))
        flags = dsg_flags(ctx, code)
        cells.append(esc(", ".join(f.capitalize() for f in flags)) if flags else '<span class="muted">—</span>')
        rows.append(cells)
    years = sorted(y for y in by_year(england) if y >= FROM_YEAR)
    lines = [{"label": "All schools", "values": series(england, "in_deficit_pct", years), "emph": True},
             {"label": "Council-run", "values": series(england, "in_deficit_pct", years, "council-run"), "style": "dashed"},
             {"label": "Academies", "values": series(england, "in_deficit_pct", years, "academy"), "style": "dashed"}]
    last = england.get("combined_last_year")
    grid = chart_card("Share of schools in deficit in England", lines, years, unit="%",
                      note=esc(SECTOR_NOTE.format(last=last or "the latest year")))
    dsg = england.get("dsg") or {}
    dyears = sorted(y for y in dsg if y >= FROM_YEAR)
    grid += chart_card("Councils' high-needs (DSG) balance per pupil, England",
                       [{"label": "England", "values": dsg_values(england, dyears, "per_pupil"), "emph": True}], dyears,
                       note="Negative is a deficit carried forward, in cash terms.")
    framing = (((ctx or {}).get("ifs") or {}).get("framings") or {}).get("why_schools_go_into_deficit") or {}
    why = f'<p>{ifs_text(framing["text"])}{cite(", ".join(str(p) for p in framing.get("pages") or []))}</p>' if framing.get("text") else f"<p>{esc(REASONS)}</p>"
    dsg_pp = ifs_line(ctx, "council", "high_needs_deficits")
    override = (f'<div class="override"><h2>The statutory override</h2>'
                + (f'<p class="ifs">{dsg_pp[0]}{cite(dsg_pp[1])}</p>' if dsg_pp else "")
                + f'<p class="note hnsg">{esc(hnsg_note((ctx or {}).get("dsg")))}</p></div>')
    top = ('<h1>School and council deficits</h1><p class="lead">Where school budgets and council high-needs budgets '
           'are in deficit, year by year: council-run schools and academies apart, and each council\'s dedicated schools '
           'grant (DSG) balance.</p>' + why + f"<p>{esc(HELPS)}</p>" + headline(england))
    rest = (override + '<section class="context"><h2>Councils and special needs</h2>' + council_ifs_lines(ctx) + "</section>"
            + '<p class="muted small">Safety valve and delivering better value are DfE programmes for councils with large '
            'high-needs deficits; safety valve closed in April 2026 and was replaced by the High Needs Stability Grant. '
            + esc(SECTOR_NOTE.format(last=last or "the latest year")) + "</p>")
    outro = sources()
    intro = fit([(top, True), (f'<div class="chart-grid">{grid}</div>' if grid else "", False), (rest, True)], outro)
    return {"title": title_of("School and council deficits in England"),
            "description": shorten("School deficits by council and year, academies apart, and councils' high-needs (DSG) "
                                   "deficits with the statutory override and the High Needs Stability Grant.", 160),
            "intro": intro, "table": {"headers": headers, "rows": rows, "caption": "School deficits and DSG balances by council",
                                      "filters": ""} if rows else None,
            "outro": outro, "indexable": bool(rows)}


def deficit_cell(s, year):
    if not s or s.get("deficit_total") is None:
        return sort(None, '<span class="muted">—</span>')
    total, dpp = s["deficit_total"], s.get("deficit_pp")
    pupils = abs(total / dpp) if _num(dpp) else None
    return sort(dpp, money_figure("deficit_total", abs(total), pupils, year))


PTFA_HEADERS = ["Council", "Schools", "With a registered parents' association", "Median income per pupil", "Total raised"]


def render_ptfa(areas_doc_, items, ctx):
    """/ptfa/: parents' associations nationally, by intake band and tag, the biggest fundraisers,
    councils compared, and the charities held back for review."""
    doc = (areas_doc_ or {}).get("areas") if isinstance((areas_doc_ or {}).get("areas"), dict) else (areas_doc_ or {})
    pta = doc.get("pta") or {}
    window = pta.get("window") or [None, pta.get("year")]
    newest = window[1]
    limit = amount("pta_income", 5000)
    parts = ['<h1>Parents\' associations: what PTAs and PTFAs raise</h1><p class="lead">Parents, teachers and friends '
             'associations raise money for extras: trips, equipment, playgrounds. This page shows what registered '
             'associations raised, and how that differs between schools.</p>'
             f'<p>Figures come from the Charity Commission register. Charities with an income of {limit} or less need not '
             'register, so a school where no registered parents\' association was found may still have one. '
             f'{esc(OVERLAP_NOTE)} Each return is counted in the school year it falls in (April to March for council-run '
             'schools, September to August for academies), and an association shared by several schools is split '
             'equally between them.</p>']
    by_year_ = {y: v for y, v in (pta.get("by_year") or {}).items() if y >= FROM_YEAR}
    years = sorted(by_year_)
    partial = [y for y in years if newest and y > newest]
    grid = chart_card("Median parents' association income per pupil, England",
                      [{"label": "England", "values": {y: v.get("median_pp") for y, v in by_year_.items()}, "emph": True}],
                      years, partial=partial,
                      note="Among schools with a registered parents' association. The newest year is dashed while "
                           "charities are still filing.")
    totals = "".join(f'<tr><th scope="row">{esc(y)}{" <small>(still filing)</small>" if y in partial else ""}</th>'
                     f'<td>{v.get("ptas") or 0:,}</td><td>{v.get("schools") or 0:,}</td>'
                     f'<td>{money_figure("pta_income", v.get("income"), None, y) if _num(v.get("income")) else "—"}</td>'
                     f'<td>{pp_fig("pta_per_pupil", v.get("median_pp"), y)}</td></tr>' for y, v in sorted(by_year_.items(), reverse=True)[:6])
    if totals:
        grid += ('<figure class="chart-card"><figcaption>England by year</figcaption><table class="mini"><thead><tr>'
                 '<th scope="col">Year</th><th scope="col">Charities</th><th scope="col">Schools</th>'
                 '<th scope="col">Raised</th><th scope="col">Median per pupil</th></tr></thead>'
                 f'<tbody>{totals}</tbody></table></figure>')
    parts.append(f'<div class="chart-grid">{grid}</div>')
    span = f"{window[0]} or {window[1]}" if window and window[0] else (newest or "")
    bands = pta.get("by_band") or {}
    band_rows = "".join(f'<tr><th scope="row">Band {esc(b)}{" (more affluent intake)" if b == "1" else " (less affluent intake)" if b == "5" else ""}</th>'
                        f'<td>{(v or {}).get("schools") or 0:,}</td><td>{pp_fig("pta_gap", (v or {}).get("median_pp"), newest)}</td></tr>'
                        for b, v in sorted(bands.items()))
    if band_rows:
        b1, b5 = (bands.get("1") or {}).get("median_pp"), (bands.get("5") or {}).get("median_pp")
        gap = (f'<p>In schools with the most affluent intakes, the middle association raised {pp_fig("pta_gap", b1, newest)} '
               f'per pupil; in schools with the least affluent, {pp_fig("pta_gap", b5, newest)}.</p>' if _num(b1) and _num(b5) else "")
        parts.append('<h2>The gap by intake</h2>' + gap + '<table class="mini"><thead><tr><th scope="col">Intake band</th>'
                     '<th scope="col">Schools with a registered association</th><th scope="col">Median per pupil</th></tr>'
                     f'</thead><tbody>{band_rows}</tbody></table><p class="muted small">Bands rank schools on free school meals '
                     'and neighbourhood deprivation together, in five equal groups. Each school\'s latest return in '
                     f'{esc(span)}.</p>')
    tag_rows = []
    for tag, values in (("admissions", ("grammar", "non-selective")), ("governance", ("academy", "council-run"))):
        for value in values:
            v = ((pta.get("by_tag") or {}).get(tag) or {}).get(value)
            if v:
                tag_rows.append(f'<tr><th scope="row">{esc(VALUE_LABELS.get(slug(value), value))}</th><td>{v.get("schools") or 0:,}</td>'
                                f'<td>{pp_fig("pta_per_pupil", v.get("median_pp"), newest)}</td></tr>')
    if tag_rows:
        parts.append('<h2>Grammar and non-selective, academy and council-run</h2><table class="mini"><thead><tr>'
                     '<th scope="col">Schools</th><th scope="col">With a registered association</th>'
                     f'<th scope="col">Median per pupil</th></tr></thead><tbody>{"".join(tag_rows)}</tbody></table>')
    top = [t for t in pta.get("top") or [] if _num(t.get("income"))]

    def entry(t):
        school = paths(ctx, "school").get(str(t.get("urn"))) or next(
            (i.get("path") for i in items or [] if str(i.get("urn")) == str(t.get("urn"))), None) or f"/school/{esc(t.get('urn'))}/"
        low = " <small>matched with lower confidence</small>" if t.get("confidence") not in (None, "high") else ""
        return (f'<li><a href="{esc(school)}" data-preview="school:{esc(t.get("urn"))}">{esc(t.get("name"))}</a>, '
                f'{esc(t.get("council_name") or t.get("council") or "")}: '
                f'{money_figure("pta_income", t["income"], t.get("pupils"), t.get("year_end"))} in {esc(t.get("year_end"))}{low}</li>')

    if top:
        by_total = sorted(top, key=lambda t: -t["income"])[:TOP_LIST]
        by_pp = sorted((t for t in top if _num(t.get("pp"))), key=lambda t: -t["pp"])[:TOP_LIST]
        parts.append('<h2>The biggest fundraisers</h2><div class="two-col"><div><h3>By total raised</h3><ol class="top">'
                     + "".join(entry(t) for t in by_total) + '</ol></div><div><h3>By amount per pupil</h3><ol class="top">'
                     + "".join(entry(t) for t in by_pp) + "</ol></div></div>"
                     f'<p class="muted small">Each school\'s latest return in {esc(span)}; a shared association counts its '
                     'share for each school.</p>')
    held = pta.get("held") or []
    if held:
        names = ", ".join(f'<a href="{CHARITY}{esc(c.get("charity_number"))}" rel="noopener">{esc(c.get("name"))}</a>'
                          for c in held[:12])
        parts.append(f'<p class="muted small">Held for review and left out of every figure here: charities with a year\'s '
                     f'income over {amount("pta_income", agg.HOLD_ABOVE)}, as a match that large is usually a different '
                     f'school\'s charity: {names}.</p>')
    # Councils table: each school's latest return in the window, per council.
    per_council = {}
    for item in items or []:
        council = item.get("council") or {}
        code = str(council.get("code") or "")
        if not code:
            continue
        rec = per_council.setdefault(code, {"name": council.get("name") or code, "schools": 0, "with": 0, "pps": [], "total": 0.0})
        rec["schools"] += 1
        if not window or not window[0]:
            continue
        found = school_pta(item, window)
        if "note" in found:
            continue
        rec["with"] += 1
        rec["total"] += found["income"]
        if found["pupils"]:
            rec["pps"].append(found["income"] / found["pupils"])
    rows = []
    for code, rec in sorted(per_council.items(), key=lambda kv: kv[1]["name"]):
        median = agg.median_or_none(rec["pps"], agg.MIN_SCHOOLS)
        share = rec["with"] / rec["schools"] if rec["schools"] else None
        rows.append([council_link(ctx, code, rec["name"]), sort(rec["schools"], f'{rec["schools"]:,}'),
                     sort(share, f'{rec["with"]:,} <small>({share:.0%})</small>' if share is not None else "—"),
                     sort(median, pp_fig("pta_per_pupil", median, newest)),
                     sort(rec["total"], money_figure("pta_income", rec["total"], None, span) if rec["with"] else '<span class="muted">—</span>')])
    outro = sources()
    intro = fit([(p, n == 0) for n, p in enumerate(parts)], outro)
    return {"title": title_of("Parents' associations: what PTAs and PTFAs raise"),
            "description": shorten("What registered parents' associations raise in England: by year, by intake band, "
                                   "grammar and academy schools, the biggest fundraisers and every council.", 160),
            "intro": intro, "table": {"headers": PTFA_HEADERS, "rows": rows, "caption": "Parents' associations by council",
                                      "filters": ""} if rows else None,
            "outro": outro, "indexable": bool(top or rows)}
