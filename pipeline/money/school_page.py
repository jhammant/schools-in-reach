"""One school's School Money page: status, funding against spending, reserves, every income and
spending line over the years, how it compares with the schools nearby, pupils, PTA money and the IFS
context, in that order.

render(item, ctx) -> {"title", "description", "body", "indexable", "lighter"}. item is build_money.build_model's
item; ctx carries the school's SERIES (pipeline/money/series.py), status timeline, similar-school
medians, area figures, the parsed ifs_context.json and, when the school has neighbours, 'nearby'
(build_money's nearby contract). Any ctx value except series, ifs and check_url may be None, and
'nearby' may be absent. build_money wraps body with site.page(..., extra_head=EXTRA_HEAD); 'lighter'
holds the same body with a lighter nearby section, then none, for pages near the size budget.

Every £ amount in the body text is a money-figure span: school data through site.money_figure, IFS
amounts quoted in prose as data-mf="ifs_figure" spans that keep the report's exact text. Charts are
inline SVG with a figures list beside them, so the page reads in order without JavaScript.
Python stdlib only.
"""

from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from pipeline.money import charts, site
from pipeline.money import status as health
from pipeline.money.charts import badge

try:
    from pipeline.money import series as _series
except ImportError:  # finance-series (B1) owns series.py; the local copies below follow its contract
    _series = None
try:
    from pipeline.money import phrasing
except ImportError:  # comparisons-stories owns phrasing.py; without it the page keeps its plain wording
    phrasing = None
try:
    from pipeline.seo.build_pages import shorten
except ImportError:  # pragma: no cover
    def shorten(text, limit):
        return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:–—-") + "…"

esc = site.esc
DATA = Path(__file__).with_name("data")
GLOSSARY = Path(__file__).with_name("assets") / "glossary.json"
EXTRA_HEAD = ('<link rel="stylesheet" href="/assets/school.css"><link rel="stylesheet" href="/assets/nearby.css">'
              '<script src="/assets/trend.js" defer></script>')
CHARITY_PAGE = ("https://register-of-charities.charitycommission.gov.uk/charity-search?p_p_id=uk_gov_ccew_onereg_charitydetails_web_portlet_"
                "CharityDetailsPortlet&p_p_lifecycle=0&p_p_state=maximized&p_p_mode=view&_uk_gov_ccew_onereg_charitydetails_web_portlet_"
                "CharityDetailsPortlet_regId={number}&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_subId=0")
CHARITY_REGISTER = "https://register-of-charities.charitycommission.gov.uk/"
FBIT_SOURCES = "https://financial-benchmarking-and-insights-tool.education.gov.uk/data-sources"
GIAS = "https://get-information-schools.service.gov.uk/"
PTA_ROWS = 10        # PTA years listed as figures; older ones stay in the chart and on the register
MAX_QUESTIONS = 8
SIMILAR_LISTED = 5
GOV, SPEND, RESERVE = "grant_funding_government", "total_expenditure", "revenue_reserve"
RESERVE_INCL_TRUST = "revenue_reserve_incl_trust_share"
RESERVE_OWN = "revenue_reserve_own"  # SERIES: the academy's own reserve when m['revenue_reserve'] includes the trust share
INCL = "incl_trust_share"
TRUST_SHARE_WORDS = "including its share of the trust's reserve"
REPORT_LINK = '<a class="report-link" href="/about/#corrections">Report an error or add context</a>'
TRUST_CENTRAL_KEYS = ("trust_central_spend_per_pupil", "trust_central_spend_pp", "trust_central_pp")  # suspect-flag names
CFR_I18_REMOVED = "2025-26"  # finance_history KNOWN_ISSUES: I18 removed, its grants now in I06

_METRICS = ([(k, k, "income") for k in (
    "total_income", "grant_funding_government", "sen_funding", "pupil_premium", "self_generated_income",
    "donations_revenue", "donations_capital", "facilities_income", "catering_income", "other_dfe_grants")]
    + [(k, k, "spend") for k in (
        "total_expenditure", "teaching_staff", "supply_staff", "education_support_staff", "admin_clerical_staff",
        "premises_staff", "catering_staff", "other_staff_costs", "total_staff", "premises", "energy", "occupation",
        "catering", "educational_supplies", "supplies_services", "bought_in_services")]
    + [(k, k, "balance") for k in ("revenue_reserve", "in_year_balance")])
METRICS = getattr(_series, "METRICS", None) or _METRICS

LABELS = {
    "total_income": "Total income", "grant_funding_government": "Government funding",
    "sen_funding": "Special needs (SEN) funding", "pupil_premium": "Pupil premium",
    "self_generated_income": "Money the school raised itself", "donations_revenue": "Donations (day-to-day)",
    "donations_capital": "Donations for buildings and equipment", "facilities_income": "Facilities and services",
    "catering_income": "Catering income", "other_dfe_grants": "Other DfE grants",
    "total_expenditure": "Total spending", "teaching_staff": "Teachers", "supply_staff": "Supply staff",
    "education_support_staff": "Support staff", "admin_clerical_staff": "Office and admin staff",
    "premises_staff": "Premises staff", "catering_staff": "Catering staff", "other_staff_costs": "Other staff costs",
    "total_staff": "All staff costs", "premises": "Premises", "energy": "Energy",
    "occupation": "Occupation costs", "catering": "Catering", "educational_supplies": "Learning resources",
    "supplies_services": "Supplies and services", "bought_in_services": "Bought-in services",
    "revenue_reserve": "Reserve", "in_year_balance": "In-year balance",
}
TOTALS = {"total_income", "total_expenditure", "total_staff"}
# The DfE's spending subtotals take in other rows of the table, so the rows add up to more than total spending.
OVERLAPS = {
    "total_staff": "subtotal of the staff rows above, without premises and catering staff",
    "premises": "includes premises staff",
    "occupation": "includes energy, catering staff and catering supplies",
    "catering": "includes catering staff",
    "supplies_services": "includes learning resources and bought-in services",
}
OVERLAP = ("Money a parents' association gives the school can also appear in the school's own accounts as donations, "
           "so the two can overlap. They are shown separately here and never added together.")
DSG_NOTE = ("Statutory override: since 2020-21 DSG deficits are held in a separate unusable reserve rather than met from council "
            "general funds. The override runs to the end of 2027-28. Under the February 2026 approach, the High Needs Stability "
            "Grant pays 90% of each LA's eligible DSG deficit at 31 March 2026 from autumn 2026, so 2026-27 balances will fall sharply.")
_POUND = re.compile(r"£(\d[\d,]*(?:\.\d+)?)(\s?(?:billion|million|bn|m|k)\b)?")
_SCALE = {"billion": 1e9, "bn": 1e9, "million": 1e6, "m": 1e6, "k": 1e3}
_FOURTEEN_BN = re.compile(r"£14\s?(?:billion|bn)")
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# ----------------------------------------------------------------- small helpers

def _num(value):
    """A finite number, or None for anything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _attr(value) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def _pct(value, signed=False) -> str:
    return f"{value * 100:+.0f}%" if signed else f"{value * 100:.0f}%"


def _label(key) -> str:
    return LABELS.get(key) or (_glossary().get(key) or {}).get("label") or key.replace("_", " ").capitalize()


@lru_cache(maxsize=1)
def _glossary() -> dict:
    try:
        return json.loads(GLOSSARY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def dsg_note() -> str:
    """la_dsg.json's statutory-override note (the High Needs Stability Grant), shown beside the IFS £14bn."""
    try:
        notes = json.loads((DATA / "la_dsg.json").read_text(encoding="utf-8"))["source"]["notes"]
        return next(n for n in notes if str(n).startswith("Statutory override"))
    except (OSError, ValueError, KeyError, StopIteration):
        return DSG_NOTE


def pages_label(pages) -> str:
    pages = sorted({p for p in (pages if isinstance(pages, (list, tuple)) else [pages]) if isinstance(p, int)})
    if not pages:
        return ""
    if len(pages) == 1:
        return f"p. {pages[0]}"
    if len(pages) == 2 and pages[1] == pages[0] + 1:
        return f"pp. {pages[0]}–{pages[1]}"
    return "pp. " + ", ".join(str(p) for p in pages)


def ifs_cite(pages) -> str:
    label = pages_label(pages)
    return f' <span class="cite">(IFS, {label})</span>' if label else ' <span class="cite">(IFS)</span>'


def ifs_text(text) -> str:
    """Escape IFS prose and wrap each £ amount, exact text kept, in an ifs_figure money-figure span.
    The IFS's £14bn council-deficit forecast always gets la_dsg.json's statutory-override note beside it."""
    text, out, last = str(text), [], 0
    for m in _POUND.finditer(text):
        value = float(m.group(1).replace(",", "")) * _SCALE.get((m.group(2) or "").strip(), 1)
        out.append(esc(text[last:m.start()]))
        out.append(f'<span class="mf" data-mf="ifs_figure" data-v="{_attr(value)}" data-year="2025-26">{esc(m.group(0))}</span>')
        last = m.end()
    out.append(esc(text[last:]))
    html = "".join(out)
    if _FOURTEEN_BN.search(text):
        html += f' <span class="sp-dsg">{esc(dsg_note())}</span>'
    return html


def threshold_figure(value=5000) -> str:
    """The Charity Commission's registration threshold, as a pta_gap money-figure span."""
    return f'<span class="mf" data-mf="pta_gap" data-v="{value}">£{value:,}</span>'


def pta_year(period_end, source) -> str | None:
    """The school year holding a charity return: April-March for CFR schools, September-August for AAR."""
    fn = getattr(_series, "pta_year", None)
    if fn is not None:
        return fn(period_end, source)
    try:
        y, mth = int(str(period_end)[:4]), int(str(period_end)[5:7])
    except ValueError:
        return None
    start = y if mth >= (9 if source == "AAR" else 4) else y - 1
    return f"{start}-{(start + 1) % 100:02d}"


def _month_year(period_end) -> str:
    try:
        return f"{_MONTHS[int(str(period_end)[5:7]) - 1]} {str(period_end)[:4]}"
    except (ValueError, IndexError):
        return str(period_end)


def charity_url(number) -> str:
    """The Charity Commission register page for one charity (the number sits mid-URL)."""
    return CHARITY_PAGE.format(number=str(number).strip())


def ratio_words(a, b):
    """phrasing.ratio_words(a, b), or None when the module is absent or says nothing (the page then keeps its plain wording)."""
    fn = getattr(phrasing, "ratio_words", None)
    if fn is None:
        return None
    try:
        return fn(a, b)
    except Exception:  # another unit's helper must never break a school page
        return None


def _day(text) -> str:
    try:
        d = date.fromisoformat(str(text)[:10])
    except ValueError:
        return str(text)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


# ----------------------------------------------------------------- the series

class _View:
    """Read-only accessors over SERIES (pipeline/money/series.py's dict) plus the item and ctx."""

    def __init__(self, item, ctx):
        self.item, self.ctx = item, ctx or {}
        s = self.ctx.get("series") or {}
        self.s = s
        self.years = list(s.get("years") or [])
        self.source = s.get("source") or {}
        self.pupils = s.get("pupils") or {}
        self.m = dict(s.get("m") or {})
        self.flags = s.get("flags") or {}
        self.suspect = {y: set(k) for y, k in (self.flags.get("suspect") or {}).items()}
        # Years whose pupils don't match the money (series.suspect_pupils): no per-pupil figure is shown or compared.
        self.odd_pupils = {y for y, keys in self.suspect.items() if "pupils" in keys}
        # The one reserve basis m['revenue_reserve'] carries; a series without reserve_basis holds the own reserve.
        self.basis = s.get("reserve_basis") or "own"
        self.reserve_key = RESERVE_INCL_TRUST if self.basis == INCL else RESERVE
        self.held_years = set(self.flags.get("reserve_held_by_trust") or [])
        self.not_reported = self.flags.get("not_reported") or {}
        self.federation_years = set(self.flags.get("federation_years") or [])
        self.latest = self.years[-1] if self.years else None
        self.first = self.years[0] if self.years else None
        self.urn = str(item["urn"])
        self.check = self.ctx.get("check_url") or f"https://financial-benchmarking-and-insights-tool.education.gov.uk/school/{self.urn}"
        self.ifs = self.ctx.get("ifs") or {}
        self.real_label = self.ctx.get("real_label")
        self.academy = bool(item.get("academy")) or (self.latest is not None and self.source.get(self.latest) == "AAR")
        self.phase = str(item.get("phase") or (item.get("school") or {}).get("phase") or "").lower()
        if "other_dfe_grants" not in self.m:
            self._derive_other_dfe_grants()

    def _derive_other_dfe_grants(self):
        """other_dfe_grants from the rows when the series predates it (CFR I18, AAR other DfE revenue grants).
        From 2025-26 the CFR has no I18: those grants moved into I06 Other government grants."""
        out = {}
        for r in self.item.get("rows") or []:
            label = str(r.get("year", "")).replace("/", "-")
            if label not in self.years or r.get("did_not_supply") or r.get("period_months", 12) != 12:
                continue
            derive = getattr(_series, "other_dfe_grants", None)
            v = derive(r) if derive else r.get("other_dfe_grants")
            if v is None and not derive:
                v = r.get("aar_other_dfe_revenue_grants") if r.get("source") == "AAR" else r.get("cfr_additional_grants_i18")
            if v is None and not derive and r.get("source") == "CFR" and label >= CFR_I18_REMOVED:
                v = (r.get("lines") or {}).get("I06")
            if _num(v) is None:
                continue
            p = self.pupils.get(label)
            out[label] = {"v": round(v), **({"pp": round(v / p)} if p else {})}
        if out:
            self.m["other_dfe_grants"] = out

    def cell(self, metric, year) -> dict:
        return (self.m.get(metric) or {}).get(year) or {}

    def v(self, metric, year, basis="v"):
        if basis in ("pp", "rpp") and year in self.odd_pupils:
            return None
        return _num(self.cell(metric, year).get(basis))

    def pupils_for(self, year):
        """That year's pupils as a per-pupil denominator, or None when they don't match the money."""
        return None if year in self.odd_pupils else self.pupils.get(year)

    def pta_pupils_for(self, year):
        """pupils_for a parents' association: None in a federation lead's combined return too, whose pupils are the
        whole federation's while the association is this one school's."""
        return None if year in self.federation_years else self.pupils_for(year)

    def glossary_key(self, metric) -> str:
        """The glossary key for a SERIES row: the reserve row names its basis, the own row is the plain reserve."""
        if metric == RESERVE:
            return self.reserve_key
        return RESERVE if metric == RESERVE_OWN else metric

    def is_suspect(self, metric, year) -> bool:
        return metric in self.suspect.get(year, ())

    def clean(self, metric, year, basis="v"):
        """A value fit for comparisons: present and not flagged suspect."""
        return None if self.is_suspect(metric, year) else self.v(metric, year, basis)

    def similar(self, metric, year):
        """The similar-school median per pupil for metric in year: ctx['similar'] holds the latest year's medians,
        ctx['similar_series'] each year's. None when that year's median isn't known, so older figures are never
        compared with a newer cohort."""
        if year == self.latest:
            latest = _num((self.ctx.get("similar") or {}).get(metric))
            if latest is not None:
                return latest
        return _num(((self.ctx.get("similar_series") or {}).get(metric) or {}).get(year))

    def has_real(self) -> bool:
        return bool(self.real_label) and any(_num(c.get("r")) is not None for c in (self.m.get(SPEND) or {}).values())

    def drill(self, metric) -> str:
        return f"/data/sx/{self.urn}.json#m:{metric}"

    def figure(self, metric, year, *, src=True, signed=False, cmp_similar=None, key=None, drill=True):
        """The money figure for metric in year, greyed when suspect; None when there is no value."""
        value = self.v(metric, year)
        if value is None:
            return None
        suspect = self.is_suspect(metric, year)
        return site.money_figure(key or self.glossary_key(metric), value, self.pupils_for(year), year,
                                 src=self.check if src else None, signed=signed,
                                 cmp_similar=None if suspect else cmp_similar,
                                 drill=self.drill(metric) if drill else None, cls="suspect" if suspect else "")


# ----------------------------------------------------------------- charts

def _ticks(lo, hi):
    fn = getattr(charts, "_ticks", None)
    return fn(lo, hi) if fn else [lo, (lo + hi) / 2, hi]


def _tick_text(value, unit):
    if unit == "%":
        return f"{value:g}%"
    if unit == "pupils":
        return f"{value:,.0f}"
    return charts.money(value)


def _trend_fallback(lines, *, years, unit="£", title, desc, height=220, suspect=(), partial=()):
    """Local stand-in for charts.trend_chart with the same contract markers: role=img, <title>/<desc>,
    gaps for None, hollow suspect markers, dashed segments into partial years, a direct label at each
    line's end, and <g data-basis> groups (real ones display=none)."""
    years = list(years)
    values = [v for line in lines for v in (line.get("values") or {}).values() if _num(v) is not None]
    if not years or not values:
        return ""
    width, left, right, top, bottom = 480, 50, 92, 10, 24
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    if min(values) >= 0:
        lo = max(lo, 0)
    ticks = _ticks(lo, hi)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    plot_w, plot_h = width - left - right, height - top - bottom
    step = plot_w / max(len(years) - 1, 1)

    def x_of(i):
        return left + (i * step if len(years) > 1 else plot_w / 2)

    def y_of(v):
        return top + (hi - v) / ((hi - lo) or 1) * plot_h

    colour = {}
    for line in lines:
        colour.setdefault(line["label"], len(colour) % 4 + 1)
    out = [f'<svg class="chart trend-chart" viewBox="0 0 {width} {height}" role="img"><title>{esc(title)}</title><desc>{esc(desc)}</desc>']
    for t in ticks:
        out.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y_of(t):.0f}" y2="{y_of(t):.0f}"/>'
                   f'<text class="tick" x="{left - 5}" y="{y_of(t) + 4:.0f}" text-anchor="end">{esc(_tick_text(t, unit))}</text>')
    for i, y in enumerate(years):
        out.append(f'<text class="tick" x="{x_of(i):.0f}" y="{height - 7}" text-anchor="middle">{esc(y[2:] if len(years) > 5 else y)}</text>')
    for basis in ("cash", "real", None):
        group = [line for line in lines if line.get("basis") == basis]
        if not group:
            continue
        ends, body = [], []
        for line in group:
            cls = f"line s{colour[line['label']]}" + (" dashed" if line.get("style") == "dashed" else "") + (" emph" if line.get("emph") else "")
            d, dashed, dots, prev, last = "", "", [], None, None
            for i, y in enumerate(years):
                v = _num((line.get("values") or {}).get(y))
                if v is None:
                    prev = None
                    continue
                x, yy = x_of(i), y_of(v)
                if prev is None:
                    d += f"M{x:.0f},{yy:.0f}"
                elif y in partial:
                    dashed += f"M{prev[0]:.0f},{prev[1]:.0f}L{x:.0f},{yy:.0f}"
                    d += f"M{x:.0f},{yy:.0f}"
                else:
                    d += f"L{x:.0f},{yy:.0f}"
                if y in suspect:
                    dots.append(f'<circle class="dot s{colour[line["label"]]} hollow" cx="{x:.0f}" cy="{yy:.0f}" r="3.5"/>')
                prev = last = (x, yy)
            if d.count("L"):
                body.append(f'<path class="{cls}" d="{d}"/>')
            if dashed:
                body.append(f'<path class="{cls} dashed" d="{dashed}"/>')
            body.extend(dots)
            if last:
                if not dots or not dots[-1].endswith(f'cx="{last[0]:.0f}" cy="{last[1]:.0f}" r="3.5"/>'):
                    body.append(f'<circle class="dot s{colour[line["label"]]}" cx="{last[0]:.0f}" cy="{last[1]:.0f}" r="3"/>')
                ends.append([last[1], last[0], line["label"]])
        ends.sort()
        for n in range(1, len(ends)):
            ends[n][0] = max(ends[n][0], ends[n - 1][0] + 13)
        body.extend(f'<text class="direct" x="{x + 7:.0f}" y="{y + 4:.0f}">{esc(label)}</text>' for y, x, label in ends)
        attrs = "" if basis is None else f' data-basis="{basis}"' + (' display="none"' if basis == "real" else "")
        out.append(f"<g{attrs}>{''.join(body)}</g>")
    out.append("</svg>")
    return "".join(out)


def _spark_fallback(values, *, width=96, height=24, label):
    """Local stand-in for charts.sparkline: one path, role=img, aria-label, 400 bytes or less."""
    pts = [(i, v) for i, (_, v) in enumerate(values) if _num(v) is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    span = (hi - lo) or 1
    step = (width - 4) / max(len(values) - 1, 1)
    d, prev = "", None
    for i, v in pts:
        d += ("L" if prev == i - 1 else "M") + f"{2 + i * step:.0f},{height - 2 - (v - lo) / span * (height - 4):.0f}"
        prev = i
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
            f'aria-label="{esc(label[:120])}"><path d="{d}"/></svg>')


def trend(lines, **kw) -> str:
    fn = getattr(charts, "trend_chart", None)
    return (fn or _trend_fallback)(lines, **kw)


def spark(values, label) -> str:
    """A sparkline of (year, value) pairs; gaps (None) are dropped before drawing."""
    values = [(y, v) for y, v in values if _num(v) is not None]
    if len(values) < 2:
        return ""
    fn = getattr(charts, "sparkline", None)
    return (fn or _spark_fallback)(values, label=label)


def toggles(basis=True, unit=True) -> str:
    """TREND DOM buttons: cash/real basis and per-pupil/total unit, cash and per pupil pressed."""
    parts = []
    if basis:
        parts.append('<span role="group" aria-label="Prices"><button type="button" data-basis-toggle="cash" aria-pressed="true">Cash</button>'
                     '<button type="button" data-basis-toggle="real" aria-pressed="false">Real terms</button></span>')
    if unit:
        parts.append('<span role="group" aria-label="Amounts"><button type="button" data-unit-toggle="pp" aria-pressed="true">Per pupil</button>'
                     '<button type="button" data-unit-toggle="total" aria-pressed="false">Total</button></span>')
    return f'<div class="trend-toggles">{"".join(parts)}</div>' if parts else ""


# ----------------------------------------------------------------- sections

# Who each section matters most to, as site.AUDIENCES keys: when a reader is chosen, audience.css tags these sections
# "For governors" and so on. Not data-for: app.css hides every [data-for] block except the chosen reader's.
READERS = {"status": "parent pupil", "funding": "governor leader", "reserve": "governor leader", "income": "ptfa pupil",
           "spending": "governor leader", "pupils": "leader", "ptfa": "parent ptfa", "split": "parent pupil",
           "questions": "parent governor ptfa"}


def _readers(ident) -> str:
    return f' data-readers="{READERS[ident]}"' if ident in READERS else ""


def _section(ident, heading, html) -> str:
    return f'<section id="{ident}" class="sp-sec"{_readers(ident)}><h2>{heading}</h2>{html}</section>' if html else ""


def _overseer(item) -> str:
    if item.get("academy"):
        return item.get("trust") or "the trust"
    return "the council"


def status_reserve_figure(item, view, *, deficit=False) -> str | None:
    """status.py's reserve as a money figure, or None without one. A trust-inclusive reserve keeps its own glossary
    key, and the figure is greyed when the series flags that year's reserve as suspect. deficit=True shows it as
    the deficit (a positive amount) under the school's own deficit definition (glossary school_deficit)."""
    st = item.get("status") or {}
    if _num(st.get("reserve")) is None:
        return None
    year = str(st.get("year") or view.latest or "").replace("/", "-")
    pupils = view.pupils_for(year) if year in view.pupils else (item.get("latest") or {}).get("pupils")
    key = RESERVE_INCL_TRUST if st.get("trust_share_included") else RESERVE
    cls = "suspect" if view.is_suspect(key, year) or (view.reserve_key == key and view.is_suspect(RESERVE, year)) else ""
    if st.get("status") == health.HELD_BY_TRUST:
        return site.money_figure(RESERVE, st["reserve"], None, year, src=view.check, cls=cls)
    if deficit:
        return site.money_figure("school_deficit", -st["reserve"], pupils, year, label="Deficit", src=view.check, cls=cls)
    return site.money_figure(key, st["reserve"], pupils, year, src=view.check, cls=cls)


def reason_html(item, view) -> str:
    """status.py's reason with its £ figure as a money figure."""
    st = item["status"]
    text = esc(st["reason"])
    m = re.search(r"-?£[0-9][0-9.,]*(?:bn|m|k)?", text)
    fig = status_reserve_figure(item, view, deficit=st["status"] == "in_deficit")
    if not m or fig is None:
        return text
    return text[:m.start()] + fig + text[m.end():]


def deficit_definition(item, view) -> str:
    """What the red badge's figure means, in plain words, for this kind of school: the first line under the badge."""
    st = item["status"]
    if st["status"] == "heading_for_deficit":
        return ("Heading for deficit means the school has spent more than it received for at least two years running and, "
                "at that rate, its reserve would run out within about three years. It is a warning, not a debt.")
    if st.get("trust_share_included"):
        return ("Counting its share of its trust's reserve, this academy's balance is below zero. The trust is responsible "
                "for its academies' money and agrees with the academy how the balance will be brought back up.")
    if view.academy:
        return ("A deficit means the academy's savings have gone below zero. Its trust is responsible for its money and agrees "
                "a plan with it to bring the balance back, usually over a few years.")
    return ("A deficit means the school's savings have gone below zero. A council-run school owes the amount to its council "
            "and agrees a plan with it to pay it back, usually over a few years.")


def _reserve_peak(view):
    """The year the reserve was highest before the latest year, with its value, or (None, None). Only years on the
    page's one basis have a value, so an own-reserve year is never compared with a trust-inclusive one."""
    earlier = [(y, view.clean(RESERVE, y)) for y in view.years[:-1]]
    earlier = [(y, v) for y, v in earlier if v is not None]
    if not earlier:
        return None, None
    return max(earlier, key=lambda yv: (yv[1], yv[0]))


def what_changed(item, view) -> str:
    """One neutral sentence from the school's own figures on how its reserve came down: from its highest year to
    the latest, with spending and income per pupil over the same years (the same years' pupils). "" when the
    figures can't say."""
    latest = view.latest
    peak_year, peak = _reserve_peak(view)
    now = view.clean(RESERVE, latest) if latest else None
    if peak_year is None or now is None or now >= peak:
        return ""
    reserve_from = view.figure(RESERVE, peak_year, src=False, drill=False)
    reserve_to = view.figure(RESERVE, latest, src=False, drill=False)
    text = f"The reserve fell from {reserve_from} in {esc(peak_year)} to {reserve_to} in {esc(latest)}"
    spend_a, spend_b = view.clean(SPEND, peak_year, "pp"), view.clean(SPEND, latest, "pp")
    inc_a, inc_b = view.clean("total_income", peak_year, "pp"), view.clean("total_income", latest, "pp")
    if all(_num(v) and v > 0 for v in (spend_a, spend_b, inc_a, inc_b)):
        spend_change, inc_change = spend_b / spend_a - 1, inc_b / inc_a - 1
        if spend_change > inc_change:
            # Say which way each moved: spending that fell less than income did is not spending that rose.
            if spend_change <= 0:
                why = "as income per pupil fell faster than spending per pupil"
            elif inc_change < 0:
                why = "as spending per pupil rose while income per pupil fell"
            else:
                why = "as spending per pupil rose faster than income per pupil"
            text += (f", {why} (spending {_pct(spend_change, signed=True)}, "
                     f"income {_pct(inc_change, signed=True)} over those years)")
        else:
            text += (f", while income per pupil kept pace with spending (income {_pct(inc_change, signed=True)}, "
                     f"spending {_pct(spend_change, signed=True)} over those years)")
    pupils_a, pupils_b = _num(view.pupils_for(peak_year)), _num(view.pupils_for(latest))
    if pupils_a and pupils_b and abs(pupils_b / pupils_a - 1) >= 0.05:
        moved = "fell" if pupils_b < pupils_a else "rose"
        text += f". Pupil numbers {moved} from {pupils_a:,.1f} to {pupils_b:,.1f}"
    return f'<p class="sp-changed"><strong>What changed here.</strong> {text}.</p>'


def _timeline_reason(status, phase) -> str:
    large = "5%" if phase == "secondary" else "8%"
    return {"in_deficit": "reserve below zero",
            "heading_for_deficit": "spending more than it received, reserve running down",
            "tight": "reserve under 3% of a year's income",
            "healthy": f"reserve between 3% and {large} of a year's income",
            "large_reserves": f"reserve {large} or more of a year's income",
            "reserve_held_by_trust": "own balance of zero: the trust holds reserves centrally"}.get(status, "")


def _watch(item, mode="school") -> str:
    """wrapped.watch_button: the ▶ 30-second video, at the top of the page and in the PTFA section ("" without the module)."""
    try:
        from pipeline.money import wrapped
        return " " + wrapped.watch_button(item, mode)
    except Exception:  # another unit's helper must never break a school page
        return ""


def _share_links(item) -> str:
    parts = []
    for mod, fn, arg in (("deck", "deck_links", item["urn"]), ("wrapped", "wrapped_links", item)):
        try:
            module = __import__(f"pipeline.money.{mod}", fromlist=[fn])
            parts.append(getattr(module, fn)(arg))
        except ImportError:
            continue
        except Exception:  # another unit's helper must never break a school page
            continue
    return f'<div class="sp-share"><span class="sp-share-label">Present and share</span>{"".join(parts)}</div>' if parts else ""


def _timeline_list(line, view) -> str:
    items, before = [], None
    for t in line:
        if t.get("status") not in charts.STATUS_LABELS:
            continue
        reason = _timeline_reason(t["status"], view.phase) if t["status"] != before else "same as the year before"
        items.append(f'<li><span class="y">{esc(t.get("year", ""))}</span> {badge(t["status"], "small")} <span class="r">{esc(reason)}</span></li>')
        before = t["status"]
    return f'<ol class="sp-timeline">{"".join(items)}</ol>' if items else ""


def timeline_html(view) -> str:
    """Status by year on the headline's reserve basis. An academy's years without the trust-inclusive figure are a
    second, labelled list on its own reserve, so the two bases never sit in one run of badges."""
    line = [t for t in view.ctx.get("timeline") or [] if isinstance(t, dict)]
    if not line:
        return ""
    page_basis = view.basis if view.s.get("reserve_basis") else None
    main = [t for t in line if page_basis is None or t.get("basis", page_basis) == page_basis]
    other = [t for t in line if t not in main]
    html = ""
    if main:
        head = "Status by year" + (f", {TRUST_SHARE_WORDS}" if page_basis == INCL and other else "")
        html += f"<h3>{esc(head)}</h3>{_timeline_list(main, view)}"
    if other:
        html += (f"<h3>Earlier years, on the academy's own reserve</h3>{_timeline_list(other, view)}"
                 '<p class="small muted">The DfE publishes the reserve including a trust\'s share only from '
                 f'{esc(main[0]["year"] if main else "a later year")}, so these years are judged on the academy\'s own balance '
                 'and are not the same measure as the status above.</p>')
    return html


def status_section(item, view) -> str:
    st = item["status"]
    framings = view.ifs.get("framings") or {}
    html = (f'<p class="status-line">{badge(st["status"], "large")} {REPORT_LINK} '
            f'{site.pin_button("school", item["urn"], item["name"], item.get("path"))}{_watch(item)}</p>')
    html += f'<p class="lead">{reason_html(item, view)}</p>'
    if st["status"] in ("in_deficit", "heading_for_deficit"):
        # The badge's own definition first, then what this school's figures show, then the national picture.
        html += f'<p class="sp-define">{esc(deficit_definition(item, view))}</p>'
        html += what_changed(item, view)
        why = framings.get("why_schools_go_into_deficit") or {}
        html += '<div class="note sp-why">'
        if why.get("text"):
            html += f'<p><strong>Why schools go into deficit.</strong> {ifs_text(why["text"])}{ifs_cite(why.get("pages"))}</p>'
        html += (f'<p><strong>What helps.</strong> Schools in this position usually agree a recovery plan with {esc(_overseer(item))}, '
                 'often over two or three years, and governors check progress against it each term. The questions further down '
                 'are a good way to start that conversation.</p></div>')
    elif st["status"] == health.HELD_BY_TRUST:
        trust = item.get("trust")
        where = (f'<a href="{esc(item["trust_path"])}">{esc(trust)}</a>' if trust and item.get("trust_path")
                 else esc(trust) if trust else "the trust")
        html += (f'<p class="sp-define">Many trusts hold their academies\' reserves centrally. {where} keeps this academy\'s '
                 'reserve with the trust, so its own accounts show a balance of zero; that is not a sign of money trouble.</p>')
    html += timeline_html(view)
    return f'<section id="status" class="sp-sec"{_readers("status")}>{html}{_share_links(item)}</section>'


def _gap_values(view, gov_key, spend_key, basis):
    gap = view.s.get("gap") or {}
    gov, spend = {}, {}
    for y in view.years:
        g = gap.get(y) or {}
        if basis in ("pp", "rpp") and y in view.odd_pupils:  # the pupils don't match the money: no per-pupil point
            gov[y] = spend[y] = None
            continue
        gov[y] = _num(g.get(gov_key)) if gov_key in g else view.v(GOV, y, basis)
        spend[y] = _num(g.get(spend_key)) if spend_key in g else view.v(SPEND, y, basis)
    return gov, spend


def _suspect_years(view, *metrics):
    return tuple(y for y in view.years if any(view.is_suspect(k, y) for k in metrics))


def funding_section(item, view) -> str:
    years = view.years
    if not years or not any(view.v(GOV, y) is not None or view.v(SPEND, y) is not None for y in years):
        return _section("funding", "Government funding vs spending per pupil",
                        '<p>This school\'s returns don\'t give both government funding and spending for any full year.</p>')
    real = view.has_real()
    suspect = _suspect_years(view, GOV, SPEND)
    span = f"{years[0]} to {years[-1]}" if len(years) > 1 else years[0]
    similar = (view.ctx.get("similar_series") or {}).get(SPEND) or {}
    blocks = []
    for unit, (cash_b, real_b) in (("pp", ("pp", "rpp")), ("total", ("v", "r"))):
        gov, spend = _gap_values(view, "gov_pp" if unit == "pp" else "gov_v", "spend_pp" if unit == "pp" else "spend_v", cash_b)
        lines = [{"label": "Gov. funding", "values": gov, "style": "solid", "emph": True, "basis": "cash"},
                 {"label": "Spending", "values": spend, "style": "solid", "emph": False, "basis": "cash"}]
        if real:
            rgov, rspend = _gap_values(view, "gov_rpp" if unit == "pp" else "gov_r", "spend_rpp" if unit == "pp" else "spend_r", real_b)
            lines += [{"label": "Gov. funding", "values": rgov, "style": "solid", "emph": True, "basis": "real"},
                      {"label": "Spending", "values": rspend, "style": "solid", "emph": False, "basis": "real"}]
        if unit == "pp" and similar:
            lines.append({"label": "Similar", "values": {y: similar.get(y) for y in years}, "style": "dashed", "emph": False, "basis": "cash"})
        what = "per pupil" if unit == "pp" else "in total"
        desc = (f"Government funding and spending {what} each year, {span}. "
                + "; ".join(f"{y}: funding {charts.money(gov[y])}, spending {charts.money(spend[y])}" for y in years
                            if gov.get(y) is not None or spend.get(y) is not None))
        chart = trend(lines, years=years, unit="£", title=f"Government funding and spending {what}, {span}", desc=desc, suspect=suspect)
        blocks.append(f'<div data-unit="{unit}"{" hidden" if unit == "total" else ""}>{chart}</div>')
    latest = next((y for y in reversed(years) if view.clean(GOV, y) is not None and view.clean(SPEND, y) is not None), None)
    summary = ""
    if latest:
        gov_v, spend_v = view.v(GOV, latest), view.v(SPEND, latest)
        summary = (f'<p>In {esc(latest)}, government funding was {view.figure(GOV, latest, src=False)} and spending '
                   f'{view.figure(SPEND, latest, src=False, cmp_similar=view.similar(SPEND, latest))}. ')
        gap = spend_v - gov_v
        if gap > 0:
            summary += (f'Spending was {site.money_figure("gov_vs_spend_gap", gap, view.pupils_for(latest), latest)} more than government '
                        'funding; the difference came from other income, such as lettings, catering or donations, or from the school\'s reserve.</p>')
        else:
            summary += (f'Government funding was {site.money_figure("gov_vs_spend_gap", -gap, view.pupils_for(latest), latest)} more than '
                        'spending.</p>')
    framing = (view.ifs.get("framings") or {}).get("funding_vs_spending_per_pupil") or {}
    notes = []
    if framing.get("text"):
        # The IFS's all-age £8,400 is not a school-level comparator, so that sentence (and its pointer) is left out.
        kept = [s for s in re.split(r"(?<=\.)\s+", framing["text"]) if "8,400" not in s and not s.startswith("Compare a school with")]
        notes.append(f'<p>{ifs_text(" ".join(kept))}{ifs_cite(framing.get("pages"))}</p>')
    notes.append('<p class="small muted">Government funding is the academy accounts line "grant funding from government" in academy (AAR) '
                 'years and the CFR grant funding total in council-run years. The two are not strictly comparable: CFR line I07 can include '
                 'some money that is not from government.')
    if len({view.source.get(y) for y in years} - {None}) > 1:
        notes[-1] += " CFR years run April to March and AAR years September to August."
    notes[-1] += "</p>"
    if real:
        notes.append(f'<p class="small muted">Real terms: {esc(view.real_label)}.</p>')
    if suspect:
        notes.append('<p class="small muted">Hollow markers are figures that look out of line with this school\'s other years; '
                     'they are left out of comparisons.</p>')
    if view.odd_pupils:
        notes.append(f'<p class="small muted">{esc(odd_pupils_note(view))}</p>')
    trend_html = f'<div class="trend">{toggles(basis=real, unit=True)}{"".join(blocks)}</div>'
    return _section("funding", "Government funding vs spending per pupil", summary + trend_html + "".join(notes))


def odd_pupils_note(view) -> str:
    years = sorted(view.odd_pupils)
    which = (f"{years[0]}: that year's pupil count doesn't match its money" if len(years) == 1
             else f"{', '.join(years[:-1])} and {years[-1]}: those years' pupil counts don't match their money")
    return (f"No per-pupil figure is shown for {which} (a federation's combined return can count one school's pupils "
            "against every school's money), so they are left out of charts and comparisons.")


def _reserve_cell(view, metric, year) -> str:
    """One reserve figure for the yearly table: a pooled £0 says the trust holds it, a gap says why."""
    fig = view.figure(metric, year, drill=False)
    if fig is None:
        if metric == RESERVE and year in (view.flags.get("reserve_basis_missing") or []):
            return '<span class="muted">not published on this basis</span>'
        return '<span class="muted">not reported</span>'
    own_metric = RESERVE_OWN if view.basis == INCL else RESERVE
    if metric == own_metric and year in view.held_years and view.v(metric, year) == 0:  # a pooled £0
        fig += ' <small>held by the trust</small>'
    return fig


def reserve_section(item, view) -> str:
    years = view.years
    if not years:
        return ""
    real = view.has_real()
    incl = view.basis == INCL
    own_row = incl and bool(view.m.get(RESERVE_OWN))
    name = "Incl. trust" if incl else "Reserve"  # short: the label sits at the line's end; desc and table say it in full
    similar = (view.ctx.get("similar_series") or {}).get(RESERVE) or {}
    lines = [{"label": name, "values": {y: view.v(RESERVE, y, "pp") for y in years}, "style": "solid", "emph": True, "basis": "cash"}]
    if own_row:
        lines.append({"label": "Own", "values": {y: view.v(RESERVE_OWN, y, "pp") for y in years}, "style": "solid", "emph": False, "basis": "cash"})
    if real:
        lines.append({"label": name, "values": {y: view.v(RESERVE, y, "rpp") for y in years}, "style": "solid", "emph": True, "basis": "real"})
        if own_row:
            lines.append({"label": "Own", "values": {y: view.v(RESERVE_OWN, y, "rpp") for y in years}, "style": "solid", "emph": False, "basis": "real"})
    if similar and not incl:
        lines.append({"label": "Similar", "values": {y: similar.get(y) for y in years}, "style": "dashed", "emph": False, "basis": "cash"})
    span = f"{years[0]} to {years[-1]}" if len(years) > 1 else years[0]
    what = f"Reserve per pupil at the end of each year, {TRUST_SHARE_WORDS}. " if incl else "Reserve per pupil at the end of each year. "
    desc = what + "; ".join(f"{y}: {charts.money(view.v(RESERVE, y, 'pp'))}" for y in years if view.v(RESERVE, y, "pp") is not None)
    if own_row:
        desc += ". The academy's own reserve per pupil: " + "; ".join(
            f"{y}: {charts.money(view.v(RESERVE_OWN, y, 'pp'))}" for y in years if view.v(RESERVE_OWN, y, "pp") is not None)
    chart = trend(lines, years=years, unit="£", title=f"Reserve per pupil, {span}", desc=desc,
                  suspect=_suspect_years(view, RESERVE, RESERVE_OWN))
    html = f'<div class="trend">{toggles(basis=real, unit=False)}{chart}</div>' if chart else ""
    if real:
        html += f'<p class="small muted">Real terms: {esc(view.real_label)}.</p>'
    heads = ("Pupils", "Income", "Spending", "In-year balance", "Reserve" + (" incl. trust share" if incl else ""), "Own reserve")
    rows = []
    for y in reversed(years):
        cells = [view.figure(k, y, signed=(k == "in_year_balance"), src=(k != "in_year_balance"), drill=False)
                 or '<span class="muted">not reported</span>'
                 for k in ("total_income", "total_expenditure", "in_year_balance")]
        cells.append(_reserve_cell(view, RESERVE, y))
        if own_row:
            cells.append(_reserve_cell(view, RESERVE_OWN, y))
        pupils = view.pupils.get(y)
        count = f"{pupils:,.1f}" if _num(pupils) else "—"
        if y in view.odd_pupils:
            count = f'<span class="mf-odd">{count}</span> <small>doesn\'t match the money</small>'
        rows.append(f'<tr><th scope="row">{esc(y)}</th><td data-label="{heads[0]}">{count}</td>'
                    + "".join(f'<td data-label="{esc(heads[i + 1])}">{c}</td>' for i, c in enumerate(cells)) + "</tr>")
    reserve_head = f"Reserve at year end, {TRUST_SHARE_WORDS}" if incl else "Reserve at year end"
    own_head = '<th scope="col">Academy\'s own reserve</th>' if own_row else ""
    html += ('<div class="sp-scroll"><table class="sp-years"><caption>Each year\'s figures, newest first</caption><thead><tr><th scope="col">Year</th>'
             '<th scope="col">Pupils</th><th scope="col">Income</th><th scope="col">Spending</th><th scope="col">In-year balance</th>'
             f'<th scope="col">{esc(reserve_head)}</th>{own_head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    if incl:
        missing = view.flags.get("reserve_basis_missing") or []
        note = (f"The status above uses the reserve {TRUST_SHARE_WORDS}, the figure the DfE publishes for academies in a trust. "
                "The academy's own reserve is shown beside it, never mixed in.")
        if missing:
            note += (f" The DfE doesn't publish the trust-inclusive figure for {', '.join(missing)}, so those years show only the "
                     "academy's own reserve.")
        html += f'<p class="small muted">{esc(note)}</p>'
    if view.held_years:
        html += ('<p class="small muted">Where the academy\'s own reserve is £0 its trust holds reserves centrally, '
                 'so the zero is not a sign of money trouble.</p>').replace("£0", site.money_figure(RESERVE, 0, None, view.latest))
    if any(keys - {"pupils"} for keys in view.suspect.values()):
        html += '<p class="small muted">Greyed figures look out of line with this school\'s other years and are left out of comparisons.</p>'
    if view.odd_pupils:
        html += f'<p class="small muted">{esc(odd_pupils_note(view))}</p>'
    return _section("reserve", "Reserve per pupil by year", html)


def _change(view, metric):
    """Per-pupil change from the first to the latest clean year, cash and real."""
    ys = [y for y in view.years if view.clean(metric, y, "pp") is not None]
    if len(ys) < 2 or ys[-1] != view.latest:
        return ""
    a, b = view.clean(metric, ys[0], "pp"), view.clean(metric, ys[-1], "pp")
    if not a or a <= 0 or b is None:
        return ""
    text = _pct(b / a - 1, signed=True) + (f" <small>since {esc(ys[0])}</small>" if ys[0] != view.first else "")
    ra, rb = view.clean(metric, ys[0], "rpp"), view.clean(metric, ys[-1], "rpp")
    if ra and ra > 0 and rb is not None:
        text += f' <small>{_pct(rb / ra - 1, signed=True)} real</small>'
    return text


def _columns(view) -> int:
    """Line, latest, [trend,] change, similar: the trend column only once there are three years to draw."""
    return 5 if len(view.years) > 2 else 4


def _metric_row(view, metric):
    """One row of the income or spending table, or None when the school never reports the line. Donations always
    get a row: a zero reads '£0 recorded' and a gap 'not reported', with the earlier years' trend kept."""
    latest = view.latest
    similar = view.similar(metric, latest)
    label = esc(_label(metric))
    value = view.v(metric, latest)
    academy_gap = metric == "pupil_premium" and view.source.get(latest) == "AAR"
    if value is None and (metric in view.not_reported or academy_gap):
        reason = view.not_reported.get(metric) or "not reported in academy accounts"
        return f'<tr><th scope="row">{label}</th><td colspan="{_columns(view) - 1}" class="muted">{esc(reason[:1].upper() + reason[1:])}</td></tr>'
    values = [(y, view.clean(metric, y, "pp")) for y in view.years]
    if all(v is None for _, v in values) and value is None:
        if metric == "donations_revenue":
            return f'<tr><th scope="row">{label}</th><td colspan="{_columns(view) - 1}" class="muted">Not reported in {esc(latest)}</td></tr>'
        return None
    if value is None:
        fig = f'<span class="muted">not reported in {esc(latest)}</span>'
    else:
        fig = view.figure(metric, latest, src=False, cmp_similar=similar)
        if metric == "donations_revenue" and value == 0:
            fig += " recorded"
    sim = (exact_figure("per_pupil", similar, latest)
           if _num(similar) is not None and not view.is_suspect(metric, latest) else "—")
    line = f'<td>{spark(values, f"{_label(metric)} per pupil, {view.first} to {latest}")}</td>' if len(view.years) > 2 else ""
    cls = ' class="tot"' if metric in TOTALS else ""
    if metric in OVERLAPS:
        label += f' <small class="sp-overlap">{esc(OVERLAPS[metric])}</small>'
    return f'<tr{cls}><th scope="row">{label}</th><td>{fig}</td>{line}<td>{_change(view, metric)}</td><td>{sim}</td></tr>'


def similar_meta(view):
    """ctx['similar_meta'] ({year, peers, method}) when it describes at least one peer, else None."""
    meta = view.ctx.get("similar_meta")
    if not isinstance(meta, dict) or not meta.get("year") or not _num(meta.get("peers")):
        return None
    return meta


def similar_words(view) -> str:
    """'School Money's similar schools (39 schools, 2025-26)', or today's plain 'similar schools' without similar_meta."""
    meta = similar_meta(view)
    if meta is None:
        return "similar schools"
    return f"School Money's similar schools ({int(meta['peers'])} schools, {meta['year']})"


def similar_heading(view) -> str:
    meta = similar_meta(view)
    if meta is None:
        return "Similar schools (median per pupil)"
    return f"Similar schools ({int(meta['peers'])} schools, {meta['year']}): median per pupil"


def similar_sentence(view, metric=SPEND, verb="spends") -> str:
    """'Per pupil, this school spends about a quarter more than the median for School Money's similar schools
    (39 schools, 2025-26): £9,475 against £7,672.' Needs phrasing.ratio_words, similar_meta and the same year on
    both sides; "" otherwise, so the page keeps its plain table."""
    meta, latest = similar_meta(view), view.latest
    if meta is None or not latest:
        return ""
    mine, median = view.clean(metric, latest, "pp"), view.similar(metric, latest)
    words = ratio_words(mine, median)
    if not words:
        return ""
    year_note = "" if meta["year"] == latest else f" (this school's figure is for {esc(latest)})"
    return (f'<p class="sp-similar-line">Per pupil, this school {verb} {esc(words)} the median for {esc(similar_words(view))}'
            f'{year_note}: {exact_figure("per_pupil", mine, latest, "This school, per pupil")} against '
            f'{exact_figure("per_pupil", median, meta["year"], "Similar schools, median per pupil")}.</p>')


def _metric_table(view, group, caption):
    rows, missing = [], []
    for key, _, g in METRICS:
        if g != group:
            continue
        row = _metric_row(view, key)
        if row is None:
            label = _label(key)
            missing.append(label if label[1:2].isupper() else label[:1].lower() + label[1:])
        else:
            rows.append(row)
    trend_col = '<th scope="col">Trend per pupil</th>' if _columns(view) == 5 else ""
    head = (f'<thead><tr><th scope="col">Line</th><th scope="col">{esc(view.latest)}</th>{trend_col}'
            f'<th scope="col">Change per pupil since {esc(view.first)}</th><th scope="col">{esc(similar_heading(view))}</th></tr></thead>')
    html = (f'<div class="sp-scroll"><table class="sp-rows"><caption>{esc(caption)}</caption>{head}<tbody>{"".join(rows)}</tbody></table></div>'
            if rows else "")
    if group == "spend" and any(k in OVERLAPS and _metric_row(view, k) for k, _, g in METRICS if g == group):
        html += ('<p class="small muted">Rows marked "includes" are the DfE\'s own subtotals, which take in other rows of this table, '
                 'so the rows add up to more than total spending. Tap a line for the return lines it adds up and where it sits in the '
                 'DfE benchmarking tool.</p>')
    if missing:
        html += f'<p class="small muted">Not in this school\'s returns: {esc(", ".join(missing))}.</p>'
    return html


def income_section(item, view) -> str:
    if not view.latest:
        return ""
    html = _metric_table(view, "income", f"Income in {view.latest}, with the trend per pupil since {view.first}")
    pt = (view.ifs.get("framings") or {}).get("pass_through_grants") or {}
    if view.m.get("other_dfe_grants"):
        html += ('<p class="small"><strong>Other DfE grants</strong> is a container line. It includes the grants that cover higher employer '
                 'pension and National Insurance costs, which cannot be separated out, so no figure is shown for them on their own.')
        if pt.get("text"):
            html += f' {ifs_text(pt["text"])}{ifs_cite(pt.get("pages"))}'
        html += "</p>"
    if view.academy:
        html += ('<p class="small muted">Academy accounts don\'t report pupil premium as a separate line, so it is shown as '
                 'not reported rather than as zero.</p>')
    return _section("income", "Where the money comes from", html)


def _context_line(view, ident):
    for line in (view.ifs.get("context_lines") or {}).get("school") or []:
        if line.get("id") == ident:
            return line
    return None


def spending_section(item, view) -> str:
    if not view.latest:
        return ""
    html = _metric_table(view, "spend", f"Spending in {view.latest}, with the trend per pupil since {view.first}")
    html += similar_sentence(view)
    latest = view.latest
    staff, spend = view.clean("total_staff", latest), view.clean(SPEND, latest)
    staff_line = _context_line(view, "staff_share")
    if staff is not None and spend:
        html += (f'<p>All staff costs were {_pct(staff / spend)} of this school\'s spending in {esc(latest)}. That subtotal includes '
                 'teachers, supply, support, office and other staff, training and staff insurance, and leaves out premises and catering staff')
        site_staff = [view.clean(k, latest) for k in ("premises_staff", "catering_staff")]
        if all(v is not None for v in site_staff) and sum(site_staff) > 0:
            html += f'; counting them too, staff were {_pct((staff + sum(site_staff)) / spend)} of spending'
        html += "."
        if staff_line:
            html += f' {ifs_text(staff_line["text"])}{ifs_cite(staff_line.get("page"))}'
        html += "</p>"
    elif staff_line:  # the national fact stands without this school's staff total
        html += f'<p>{ifs_text(staff_line["text"])}{ifs_cite(staff_line.get("page"))}</p>'
    phase_line = _context_line(view, {"primary": "per_pupil_primary", "secondary": "per_pupil_secondary"}.get(view.phase, ""))
    if phase_line:
        real = view.clean(SPEND, latest, "r") if view.has_real() else None
        if real is not None:
            mine = site.money_figure("spend_pp", real, view.pupils_for(latest), latest, label=f"Spending in {latest}, in 2025-26 prices")
            html += f'<p>In 2025-26 prices, this school spent {mine} in {esc(latest)}. '
        elif spend is not None:
            html += f'<p>This school spent {view.figure(SPEND, latest, src=False)} in {esc(latest)}, in cash. '
        else:
            html += "<p>"
        html += f'{ifs_text(phase_line["text"])}{ifs_cite(phase_line.get("page"))}</p>'
    elif view.phase not in ("primary", "secondary"):
        html += '<p class="small muted">The IFS national spending figures are for mainstream primary and secondary schools, so no national comparison is shown here.</p>'
    if view.academy:
        html += ('<p class="note">Academy figures exclude the trust\'s central spending on its schools, so they can look lower than a '
                 'council-run school\'s. See the trust\'s central spending below. The DfE benchmarking page adds a share of the trust\'s '
                 'central spending into the academy\'s figures and this page does not, so the two will differ.</p>')
    return _section("spending", "Where it goes", html)


NEARBY_LEVELS = ("full", "table", "lite", "brief")  # the nearby section, richest first; render() returns the rest as 'lighter' bodies
NEARBY_LITE_ROWS = 4   # neighbours in the lighter table
NEARBY_COMPARE = 6     # URNs in the compare link, this school first
NEARBY_RANKS = (("spend_pp", "spending per pupil"), ("reserve_pp", "reserve per pupil"),
                ("pta_pp", "parents' association income per pupil"))


def ordinal(n) -> str:
    """1st, 2nd, 3rd, 4th ... 11th, 12th, 13th ... 21st, 22nd, 101st, 111th."""
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _nearby(view):
    """ctx['nearby'] when it lists at least one school, else None."""
    nb = view.ctx.get("nearby")
    if not isinstance(nb, dict) or not isinstance(nb.get("self"), dict):
        return None
    schools = [r for r in nb.get("schools") or [] if isinstance(r, dict) and r.get("name")]
    me = dict(nb["self"], name=nb["self"].get("name") or view.item.get("name"), urn=nb["self"].get("urn") or view.urn)
    return dict(nb, self=me, schools=schools) if schools else None


def _phase_schools(nb) -> str:
    """'primary schools', 'alternative provision schools'; 'schools of the same phase' for Other."""
    phase = str(nb.get("phase") or "").strip()
    return "schools of the same phase" if not phase or phase == "Other" else f"{phase[:1].lower() + phase[1:]} schools"


def _nb_rank_lines(nb, year, spend_words=None) -> str:
    """The rank sentences. spend_words (the lighter levels' comparison) ends the spending line: '..., about a quarter
    more than their median' (rank and median count the same schools, this one included)."""
    phases, out = _phase_schools(nb), []
    for key, what in NEARBY_RANKS:
        r = (nb.get("rank") or {}).get(key) or {}
        rank, of = _num(r.get("rank")), _num(r.get("of"))
        if not rank or not of:
            continue
        place = "Highest" if rank == 1 else ("Lowest" if rank == of else f"{ordinal(rank)} highest")
        tail = f" in {year}"
        if key == "spend_pp" and spend_words:
            tail += f", {spend_words} their median"
        if key == "pta_pp":
            low = sum(1 for row in [nb["self"]] + nb["schools"]
                      if _num(row.get("pta_pp")) is not None and row.get("pta_confidence") == "medium")
            tail = (f" with a registered parents' association (charity years nearest {year}"
                    + (f"; {low} of them matched with lower confidence" if low else "") + ")")
        out.append(f"<li>{place} {esc(what)} of {int(of)} nearby {esc(phases)}{esc(tail)}.</li>")
    return f'<ul class="nb-ranks">{"".join(out)}</ul>' if out else ""


def _nb_ratio_words(nb):
    """phrasing.ratio_words for this school's spending per pupil against the nearby median; None without the module or
    a figure, or when this school's figure is a federation's."""
    me = nb["self"]
    mine, median = _num(me.get("spend_pp")), _num((nb.get("medians") or {}).get("spend_pp"))
    return ratio_words(mine, median) if _federation(me) is None else None


def _nb_ratio_line(nb, year, words) -> str:
    """'Per pupil, this school spends about a quarter more than the median of 9 nearby primary schools, this school
    included (2024-25): £8,750 against £7,000.' build_money.nearby_doc's median is taken over this school and every
    neighbour with a figure, so the sentence counts the same schools as the rank lines. "" without words."""
    if not words:
        return ""
    me = nb["self"]
    mine, median = _num(me.get("spend_pp")), _num((nb.get("medians") or {}).get("spend_pp"))
    counted = 1 + sum(1 for r in nb["schools"] if _num(r.get("spend_pp")) is not None)
    return (f'<p class="nb-ratio">Per pupil, this school spends {esc(words)} the median of {counted} nearby '
            f'{esc(_phase_schools(nb))}, this school included ({esc(year)}): {exact_figure("spend_pp", mine, year, "This school, per pupil")} '
            f'against {exact_figure("spend_pp", median, year, "Median of this school and its neighbours, per pupil")}.</p>')


def exact_figure(key, value, year, label=None) -> str:
    """A per-pupil money figure shown to the pound (£7,672, not £8k): medians and per-pupil comparisons."""
    fig = site.money_figure(key, value, None, year, label=label)
    sign = "-" if value < 0 else ""
    return f'{fig[:fig.index(">") + 1]}{sign}£{abs(round(value)):,}</span>'


def _pp_figure(key, pp, total, pupils, year, whole="total") -> str:
    """site.money_figure's span (the same data-* for its tooltip) showing pp as the figure and the total beside it,
    for columns headed 'per pupil'. whole names the total ('federation total' for a federation's combined return)."""
    fig = site.money_figure(key, total, pupils, year)
    sign = "-" if pp < 0 else ""
    return f'{fig[:fig.index(">") + 1]}{sign}£{abs(round(pp)):,}<small> {esc(charts.money(total))} {esc(whole)}</small></span>'


def _nb_money(key, row, field, year_field=None, year=None):
    """A per-pupil value as a money figure with that year's pupils (the total is pp x pupils), or a dash."""
    pp, pupils = _num(row.get(field)), _num(row.get("pupils"))
    if pp is None and year_field and _num(row.get("pta_income")) is not None:
        # A federation lead's parents' association: its total alone, as the federation's pupils aren't its school's.
        y = row.get(year_field) or year
        return (f'{site.money_figure(key, _num(row.get("pta_income")), None, y)}<small> total, {esc(y)}; '
                'no per-pupil figure for a federation</small>')
    if pp is None:
        return "—"
    if year_field:  # PTA: its own school year, and its own income (else pp x that row's pupils when the years match)
        y, total = row.get(year_field) or year, _num(row.get("pta_income"))
        if total is None and y == year and pupils:
            total = round(pp * pupils)
        if total is None:
            return "—"
        fig = _pp_figure(key, pp, total, total / pp if pp else None, y)  # pupils as total / pp, so data-pp is pta_pp
        if y != year:
            fig += f" <small>{esc(y)}</small>"
        if row.get("pta_confidence") == "medium":
            fig += " <small>matched with lower confidence</small>"
        return fig
    if not pupils:
        return "—"
    return _pp_figure(key, pp, round(pp * pupils), pupils, year, "federation total" if _federation(row) else "total")


def _federation(row):
    """build_money's optional 'federation' on a nearby entry whose latest return is a federation lead's combined one:
    the GIAS federation name, '' when unnamed, None when the entry is one school's own return."""
    fed = row.get("federation")
    return None if fed is None or fed is False else str(fed)


def _nb_pct(value) -> str:
    value = _num(value)
    return "—" if value is None else f"{value:.1f}%"


def _nb_name(row, me) -> str:
    name = esc(row.get("name") or "")
    fed = _federation(row)
    tag = f' <small class="nb-fed">figures for the whole {esc(fed or "federation")}</small>' if fed is not None else ""
    if me:
        return f'<th scope="row">{name} <strong class="nb-you">This school</strong>{tag}</th>'
    return f'<th scope="row"><a href="{esc(row["p"])}">{name}</a>{tag}</th>' if row.get("p") else f'<th scope="row">{name}{tag}</th>'


def _nb_status(row) -> str:
    return badge(row["status"], "small") if row.get("status") in charts.STATUS_LABELS else "—"


def _nb_table(nb, year, rows, full) -> str:
    cols = ["School", "Distance", "Status", "Spending per pupil"] + (["Reserve per pupil", "Staff costs", "PTA per pupil", "FSM"] if full else [])
    head = "".join(f'<th scope="col">{c}</th>' for c in cols)
    body = []
    for row in rows:
        me = row is nb["self"]
        mi = 0 if me else _num(row.get("mi"))
        cells = [_nb_name(row, me), "<td>—</td>" if mi is None else f"<td>{mi:g} mi</td>",
                 f"<td>{_nb_status(row)}</td>", f"<td>{_nb_money('total_expenditure', row, 'spend_pp', year=year)}</td>"]
        if full:
            reserve = "revenue_reserve_incl_trust_share" if row.get("reserve_incl_trust_share") else "revenue_reserve"
            cells += [f"<td>{_nb_money(reserve, row, 'reserve_pp', year=year)}</td>", f"<td>{_nb_pct(row.get('staff_pct'))}</td>",
                      f"<td>{_nb_money('pta_income', row, 'pta_pp', 'pta_year', year)}</td>", f"<td>{_nb_pct(row.get('fsm_pct'))}</td>"]
        body.append(f'<tr{' class="nb-self"' if me else ""}>{"".join(cells)}</tr>')
    caption = f"This school and the {len(rows) - 1} nearest {_phase_schools(nb)}, {year}"
    return (f'<div class="nb-scroll"><table class="nb-table"><caption>{esc(caption)}</caption><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def _nb_chart(nb, year) -> str:
    """Horizontal bars of spending per pupil, highest first, each labelled with its school and value; this school's
    bar is filled and named 'this school', so colour is never the only key. The median is a labelled line."""
    rows = [r for r in [nb["self"]] + nb["schools"] if _num(r.get("spend_pp")) is not None and _num(r.get("spend_pp")) >= 0]
    if len(rows) < 2 or not any(r is nb["self"] for r in rows):
        return ""
    rows.sort(key=lambda r: -r["spend_pp"])
    top, width, step = max(r["spend_pp"] for r in rows) or 1, 300, 30
    parts = []
    for n, r in enumerate(rows):
        y, me = 14 + n * step, r is nb["self"]
        name = shorten(str(r.get("name") or ""), 38) + (" (this school)" if me else "") + (" (federation)" if _federation(r) is not None else "")
        cls = ' class="me"' if me else ""
        parts.append(f'<text x="0" y="{y}"{cls}>{esc(name)}: £{r["spend_pp"]:,}</text>'
                     f'<rect y="{y + 4}" width="{max(1, round(r["spend_pp"] / top * width))}" height="9"{cls}/>')
    height = 14 + len(rows) * step
    median = _num((nb.get("medians") or {}).get("spend_pp"))
    if median is not None and median > 0:
        x = round(median / top * width)
        parts.append(f'<line class="med" x1="{x}" x2="{x}" y1="4" y2="{height - 8}"/>'
                     f'<text class="med" x="{min(x + 3, width - 60)}" y="{height}">median £{round(median):,}</text>')
        height += 6
    title = f"Spending per pupil in {year}: this school and the nearest {_phase_schools(nb)}"
    return f'<svg class="nb-chart" viewBox="0 -2 360 {height + 4}" role="img"><title>{esc(title)}</title>{"".join(parts)}</svg>'


def _nb_caveats(nb, table=True) -> str:
    """What every nearby note says, however short: the two financial years when the list mixes them, and that
    doubtful figures are left out (and, under a table, what its dashes mean)."""
    text, every = "", [nb["self"]] + nb["schools"]
    if any(r.get("academy") for r in every) and not all(r.get("academy") for r in every):
        text += "Council-run schools' years run April to March, academies' September to August. "
    if not table:
        return text + "Ranks and medians leave out doubtful figures. "
    return text + ("A dash means no figure for that year (no full-year return yet, or one left out as doubtful); "
                   "doubtful figures are left out of ranks and medians. ")


def _nb_note(nb, year, view, full) -> str:
    phases, n = _phase_schools(nb), len(nb["schools"])
    radius = _num(nb.get("radius_mi"))
    within = f", all within {radius:.1f} miles" if radius is not None else ""
    text = f"Only {phases} are compared: the {n} nearest state-funded ones{within}, in {year}"
    if view.latest and view.latest != year:
        text += f", the latest year most of them have published (the rest of this page uses {view.latest})"
    text += ". " + _nb_caveats(nb)
    html = f'<p class="small muted">{esc(text)}'
    if full:
        html += (esc(f"PTA: the parents' association's income in the charity year nearest {year}; a dash means No registered parents' "
                     "association found (charities with income of ") + threshold_figure()
                 + esc(" or less need not register) or no recent return. It can overlap with school donations, so the two are never added. "))
    if any(_federation(r) is not None for r in [nb["self"]] + nb["schools"]):
        html += esc("A federation's combined return covers all its schools, so its totals are not one school's. ")
    html += ("Nearby schools serve different families: schools with more pupils on free school meals (FSM) get more funding, "
             "so higher spending per pupil often has a good reason.</p>")
    return html


def _nb_note_brief(nb, year, view) -> str:
    text = f"Figures for {year}, comparing only {_phase_schools(nb)}"
    if view.latest and view.latest != year:
        text += f" (the rest of this page uses {view.latest})"
    return (f'<p class="small muted">{esc(text)}. {esc(_nb_caveats(nb, table=False))}Nearby schools serve different families, so compare their '
            'free school meals shares too; the compare page shows every figure side by side.</p>')


def nearby_section(item, view, level="full") -> str:
    """'Compared with schools nearby' from ctx['nearby'] (build_money's 'nearby' contract): rank sentences, this school
    and its neighbours nearest first, a bar chart of spending per pupil, a compare link and what to bear in mind.
    level 'table' drops the chart; 'lite' keeps the nearest NEARBY_LITE_ROWS and fewer columns; 'brief' keeps the
    sentences and links. 'lite' and 'brief' fold the spending comparison into its rank line, without the figures.
    "" when ctx has no nearby schools."""
    nb = _nearby(view)
    if nb is None:
        return ""
    year = str(nb.get("year") or view.latest or "")
    full = level in ("full", "table")
    rows = [nb["self"]] + (nb["schools"] if full else nb["schools"][:NEARBY_LITE_ROWS])
    words = _nb_ratio_words(nb)
    html = _nb_rank_lines(nb, year, None if full else words) + (_nb_ratio_line(nb, year, words) if full else "")
    if level != "brief":
        html += _nb_table(nb, year, rows, full)
    if level == "full":
        html += _nb_chart(nb, year)
    urns = [str(r.get("urn")) for r in [nb["self"]] + nb["schools"] if r.get("urn")][:NEARBY_COMPARE]
    if len(urns) > 1:
        html += f'<p><a class="button quiet" href="/compare/?urns={esc(",".join(urns))}">Compare these schools side by side</a></p>'
    html += _nb_note(nb, year, view, full) if level != "brief" else _nb_note_brief(nb, year, view)
    return _section("nearby", "Compared with schools nearby", html)


def pupils_section(item, view) -> str:
    years = [y for y in view.years if _num(view.pupils.get(y))]
    if not years:
        return ""
    html = '<ol class="sp-pupils">' + "".join(f'<li><span class="y">{esc(y)}</span> {view.pupils[y]:,.1f}</li>' for y in years) + "</ol>"
    falling = view.flags.get("falling_rolls")
    if falling:
        change, run = falling.get("change") or 0, falling.get("run") or {}
        if change < 0:
            html += (f'<p>Pupil numbers fell from {falling["from"]:,.1f} to {falling["to"]:,.1f} '
                     f'({_pct(-change)} fewer) over the years shown.</p>')
        if run and (change >= 0 or run.get("from") != falling["from"]):
            html += (f'<p>Pupil numbers fell in each of the last {int(run.get("years") or 3)} years, from {run["from"]:,.1f} in '
                     f'{esc(run.get("from_year", ""))} to {run["to"]:,.1f}'
                     + (f', though over all the years shown they rose from {falling["from"]:,.1f}' if change >= 0 else "") + '.</p>')
        fr = (view.ifs.get("framings") or {}).get("falling_rolls") or {}
        if fr.get("text"):
            html += f'<p class="note">{ifs_text(fr["text"])}{ifs_cite(fr.get("pages"))}</p>'
    return _section("pupils", "Pupils by year", html)


def pass_through_section(item, view) -> str:
    flag = view.flags.get("pass_through")
    if not flag:
        return ""
    year = flag.get("year")
    pupils = view.pupils_for(year)
    html = (f'<p>In {esc(year)}, this school\'s income rose by '
            f'{site.money_figure("pass_through", flag.get("income_rise"), pupils, year, label="Rise in income", signed=True)} on the year before, '
            f'and its staff costs by {site.money_figure("pass_through", flag.get("staff_rise"), pupils, year, label="Rise in staff costs", signed=True)}. '
            'Much of the extra money may have gone straight out again on higher pay, pension and National Insurance costs.</p>')
    pt = (view.ifs.get("framings") or {}).get("pass_through_grants") or {}
    line = _context_line(view, "pass_through")
    if line:
        html += f'<p class="note">{ifs_text(line["text"])}{ifs_cite(line.get("page"))}</p>'
    elif pt.get("text"):
        html += f'<p class="note">{ifs_text(pt["text"])}{ifs_cite(pt.get("pages"))}</p>'
    return _section("pass-through", "Income that passed straight through", html)


def trust_section(item, view) -> str:
    if not view.academy:
        return ""
    central = {y: v for y, v in (view.s.get("trust_central_pp") or {}).items() if _num(v) is not None}
    trust = item.get("trust")
    name = (f'<a href="{esc(item["trust_path"])}">{esc(trust)}</a>' if trust and item.get("trust_path")
            else esc(trust) if trust else "its trust")
    if central:
        suspect = {y for y in central if any(view.is_suspect(k, y) for k in TRUST_CENTRAL_KEYS)}
        items = "".join(f'<li><span class="y">{esc(y)}</span> {site.money_figure("trust_central_spend_pp", v, None, y, label="Trust central spending per pupil", cls="suspect" if y in suspect else "")}</li>'
                        for y, v in sorted(central.items()))
        html = f'<p>What {name} spent centrally per pupil, on top of this school\'s own accounts:</p><ol class="sp-pupils">{items}</ol>'
        html += '<p class="small muted">These are cash figures. The IFS average below is in 2025-26 prices.</p>'
        if suspect:
            html += '<p class="small muted">Greyed figures look out of line with the trust\'s other years and are left out of comparisons.</p>'
    else:
        html = f'<p>The DfE doesn\'t publish central spending per pupil for {name} for these years.</p>'
    fr = (view.ifs.get("framings") or {}).get("academy_central_top_slice") or {}
    line = _context_line(view, "trust_central")
    if line:
        html += f'<p class="note">{ifs_text(line["text"])}{ifs_cite(line.get("page"))}</p>'
    elif fr.get("text"):
        html += f'<p class="note">{ifs_text(fr["text"])}{ifs_cite(fr.get("pages"))}</p>'
    return _section("trust-central", "Trust central spending", html)


# ----------------------------------------------------------------- PTA

def _history_status(c) -> tuple[str, int | None]:
    years = [int(str(h["period_end"])[:4]) for h in c.get("history") or []
             if h.get("period_end") and (_num(h.get("income")) or 0) > 0]
    last = c.get("last_income_year") or (max(years) if years else None)
    status = c.get("history_status")
    if not status and not last:
        # No returns on file says nothing about whether it still runs: only a removal from the register does.
        removed = c.get("removed") or c.get("removed_year") or str(c.get("status") or "").lower() == "removed"
        status = "historical" if removed else "unknown"
    elif not status:
        status = "historical" if last < 2019 else ("current" if last >= 2024 else "recent")
    return status, last


def _low_confidence(c) -> bool:
    match = c.get("match") or {}
    return match.get("confidence") == "medium" or match.get("method") == "llm"


def pta_label(view, period_end) -> str | None:
    """The PTA-year label for a charity return: the school's own source for that year, else its nearest year's."""
    sources = {y: s for y, s in view.source.items() if s}
    cfr, aar = pta_year(period_end, "CFR"), pta_year(period_end, "AAR")
    if not cfr or sources.get(cfr) == "CFR" or not sources:
        return cfr
    if sources.get(aar) == "AAR":
        return aar
    nearest = min(sources.items(), key=lambda kv: (abs(int(kv[0][:4]) - int(cfr[:4])), -int(kv[0][:4])))[1]
    return pta_year(period_end, nearest)


def _pta_by_year(view, charities) -> dict:
    """The SERIES 'pta' shape, worked out here when the series doesn't carry it."""
    out, top = {}, {}
    for c in charities:
        share = 1 / (1 + len(c.get("shared_with") or []))
        for h in c.get("history") or []:
            pe = h.get("period_end")
            inc, exp = _num(h.get("income")), _num(h.get("expenditure"))
            label = pta_label(view, pe) if pe else None
            if not label or (inc is None and exp is None):
                continue
            e = out.setdefault(label, {"income": None, "spend": None, "charity_number": None, "confidence": "high"})
            if inc is not None:
                e["income"] = (e["income"] or 0) + inc * share
                if inc * share > top.get(label, -1):
                    top[label] = inc * share
                    e["charity_number"] = c.get("charity_number")
            if exp is not None:
                e["spend"] = (e["spend"] or 0) + exp * share
            if _low_confidence(c):
                e["confidence"] = "medium"
    for label, e in out.items():
        p = view.pta_pupils_for(label)
        for k in ("income", "spend"):
            if e[k] is not None:
                e[k] = round(e[k])
                if p:
                    e[f"{k}_pp"] = round(e[k] / p)
    return out


def _charity_line(c, view) -> str:
    num = c.get("charity_number")
    status, last = _history_status(c)
    name = c.get("name") or "Parents' association"
    bits = [f'<a href="{esc(charity_url(num))}">{esc(name)}</a> (charity {esc(num)})']
    hist = sorted((h for h in c.get("history") or [] if h.get("period_end") and _num(h.get("income")) is not None),
                  key=lambda h: h["period_end"])
    share = 1 / (1 + len(c.get("shared_with") or []))
    if status == "historical":
        bits.append(f"Had a registered PTA until {esc(c.get('removed_year') or last or 'an earlier year')}.")
    elif status == "unknown":
        bits.append("Its yearly returns aren't available here yet, so this page can't show how much it raised; "
                    "the Charity Commission register has its accounts.")
    elif hist:
        h = hist[-1]
        pe = h["period_end"]
        label = pta_label(view, pe)
        fig = site.money_figure("pta_income", round(h["income"] * share), view.pta_pupils_for(label), label)
        when = "Latest return" if status == "current" else "Last reported income"
        bits.append(f"{when}: {fig} in the year to {esc(_month_year(pe))}.")
    shared = c.get("shared_with") or []
    if shared:
        n = len(shared)
        bits.append(f"Shared with {n} {'school' if n == 1 else 'schools'}, split equally: this page counts 1/{n + 1} of its money.")
    if _low_confidence(c):
        bits.append("This charity was matched with lower confidence, so check with the school that it is theirs.")
    parta = c.get("parta") or {}
    if _num(parta.get("count_volunteers")):
        bits.append(f"It reports {parta['count_volunteers']:,} volunteers.")
    if parta.get("ar_due_date"):
        bits.append(f"Annual return due {esc(_day(parta['ar_due_date']))}.")
    return "<li>" + " ".join(bits) + "</li>"


def _pta_covered(nby) -> list:
    """National school years with at least 60% as many schools as the best-covered one (areas.pta_window's rule):
    charity returns are filed up to ten months after their year ends, so the newest year's median is early filers'."""
    best = max(_num(e.get("schools")) or 0 for e in nby.values())
    return sorted(y for y, e in nby.items() if (_num(e.get("schools")) or 0) >= 0.6 * best) or sorted(nby)


def _pta_national(view, by_year=None) -> str:
    """The England median PTA income per pupil, and the council's, as context whether or not this school has a
    registered PTA. The year is the latest well-covered one in which this school's PTA has a figure (else the latest
    well-covered one), and with phrasing.ratio_words one sentence compares this PTA with each, in that same year."""
    national = view.ctx.get("pta_national") or {}
    nby = {y: e for y, e in (national.get("by_year") or {}).items() if _num((e or {}).get("median_pp")) is not None}
    if not nby:
        return ""
    by_year = by_year or {}

    def own(y):
        return None if y in view.odd_pupils else _num((by_year.get(y) or {}).get("income_pp"))

    covered = _pta_covered(nby)
    ny = ([y for y in covered if own(y) is not None] or covered)[-1]
    mine = own(ny)
    if (by_year.get(ny) or {}).get("confidence") == "medium":
        mine = None  # a lower-confidence match is shown, but never compared
    median = nby[ny]["median_pp"]
    html = (f'<p>Across England, the typical registered parents\' association raised '
            f'{site.money_figure("pta_per_pupil", median, None, ny, label="England: median PTA income per pupil")} '
            f'per pupil in {esc(ny)}.')
    words = ratio_words(mine, median)
    if words:
        html += (f' This school\'s parents\' association raised {esc(words)} that in the same school year '
                 f'({exact_figure("pta_per_pupil", mine, ny, "This school: PTA income per pupil")} per pupil).')
    html += "</p>"
    council = view.ctx.get("council") or {}
    local = (((council.get("by_year") or {}).get(ny) or {}).get("all") or {})
    cm = _num(local.get("pta_pp_median"))
    if cm is not None:
        name = council.get("name") or "this council"
        count = _num(local.get("pta_schools"))
        of = f" ({int(count):,} schools with a registered one)" if count else ""
        html += (f'<p>In {esc(name)}, the typical registered parents\' association raised '
                 f'{site.money_figure("pta_per_pupil", cm, None, ny, label=f"{name}: median PTA income per pupil")} '
                 f'per pupil in {esc(ny)}{esc(of)}.')
        local_words = ratio_words(mine, cm)
        if local_words:
            html += f' This school\'s raised {esc(local_words)} that.'
        html += "</p>"
    return html


def nearby_fundraising(item, view) -> str:
    rows = []
    for other in (view.ctx.get("nearby_fundraising") or [])[:8]:
        income, pp = other.get("income"), other.get("pp")
        figures = f'£{income:,.0f}' if income is not None else "Income not available"
        if pp is not None:
            figures += f' · £{pp:,.0f} per pupil'
        elif income is not None:
            figures += " · per pupil unavailable"
        if other.get("year"):
            figures += f' ({other["year"]})'
        if other.get("flags", 0) & 1:
            figures += " · lower-confidence match"
        if other.get("flags", 0) & 2:
            figures += " · shared association, equal share"
        distance = f'{other["mi"]:.1f} miles' if other["mi"] >= 0.1 else "under 0.1 miles"
        rows.append(f'<li><a href="{esc(other["p"])}#ptfa">{esc(other["name"])}</a> '
                    f'· {distance} · {esc(figures)}</li>')
    code = str((item.get("council") or {}).get("code") or "")
    url = f'/ptfa/?council={code}#fundraising-finder' if code.isdigit() else '/ptfa/#fundraising-finder'
    html = '<h3>What parents raise at schools nearby</h3>'
    if rows:
        html += '<p class="small muted">Nearest schools of the same phase within 30 miles. Latest returns; years may differ.</p><ul class="nearby-fundraising">' + "".join(rows) + '</ul>'
    else:
        html += '<p>No nearby registered associations found in this phase, or a school location is unavailable.</p>'
    return html + f'<p><a href="{esc(url)}">Find fundraisers in this council</a></p>'


def pta_section(item, view) -> str:
    charities = [c for c in item.get("pta") or [] if not c.get("review")]
    if not charities:
        html = (f'<p><strong>No registered parents\' association found</strong> for {esc(item["name"])}. Charities with an income of '
                f'{threshold_figure()} or less a year don\'t have to register with the Charity Commission, so many schools have an '
                'active PTA or friends\' group that isn\'t on the register.</p>')
        return _section("ptfa", "Money raised by parents", html + _pta_national(view) + nearby_fundraising(item, view))
    # A year whose pupils don't match the money has no per-pupil figure to chart or compare, even from an older series.
    by_year = {y: dict(e, income_pp=None, spend_pp=None) if y in view.odd_pupils | view.federation_years else e
               for y, e in (view.s.get("pta") or _pta_by_year(view, charities)).items()}
    years = sorted(by_year)
    html = ""
    chart_years = [y for y in years if _num(by_year[y].get("income_pp")) is not None or _num(by_year[y].get("spend_pp")) is not None]
    if len(chart_years) >= 2:
        lines = [{"label": "Raised", "values": {y: by_year[y].get("income_pp") for y in chart_years}, "style": "solid", "emph": True, "basis": None},
                 {"label": "Spent", "values": {y: by_year[y].get("spend_pp") for y in chart_years}, "style": "solid", "emph": False, "basis": None}]
        desc = "Parents' association income and spending per pupil. " + "; ".join(
            f"{y}: raised {charts.money(by_year[y].get('income_pp'))}" for y in chart_years)
        html += trend(lines, years=chart_years, unit="£", title="Parents' association money per pupil", desc=desc)
    # The charity's own year end beside each school year, so a council-run school's April-March label doesn't read as
    # the association's year: William Patten's year to August 2025 sits in 2025-26 (April 2025 to March 2026).
    ends = {}
    for c in charities:
        for h in c.get("history") or []:
            pe = h.get("period_end")
            label = pta_label(view, pe) if pe else None
            if label and (_num(h.get("income")) is not None or _num(h.get("expenditure")) is not None):
                ends.setdefault(label, set()).add(str(pe)[:7])
    rows = []
    for y in reversed(years[-PTA_ROWS:]):
        e = by_year[y]
        p = view.pta_pupils_for(y)
        inc = site.money_figure("pta_income", e["income"], p, y) if _num(e.get("income")) is not None else "—"
        exp = site.money_figure("pta_spending", e["spend"], p, y) if _num(e.get("spend")) is not None else "—"
        low = ' <small>matched with lower confidence</small>' if e.get("confidence") == "medium" else ""
        to = ", ".join(_month_year(pe) for pe in sorted(ends.get(y, ())))
        to = f'<br><small class="muted">year to {esc(to)}</small>' if to else ""
        rows.append(f'<tr><th scope="row">{esc(y)}{to}</th><td data-label="Raised">{inc}{low}</td><td data-label="Spent">{exp}</td></tr>')
    if rows:
        html += ('<table class="sp-pta"><caption>Each school year\'s returns, newest first</caption><thead><tr><th scope="col">School year</th>'
                 f'<th scope="col">Raised</th><th scope="col">Spent</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')
    if len(years) > PTA_ROWS:
        html += f'<p class="small muted">Returns go back to {esc(years[0])}; the older ones are in the chart and on the Charity Commission register.</p>'
    html += '<ul class="sp-charities">' + "".join(_charity_line(c, view) for c in charities) + "</ul>"
    html += ('<p class="small muted">Each return is placed in the school year that holds the end of the charity\'s financial year, '
             'and per-pupil figures use that year\'s pupils. A parents\' association\'s money is its own and isn\'t in the school\'s accounts above. '
             f'{esc(OVERLAP)}</p>')
    if view.odd_pupils & set(by_year):
        html += f'<p class="small muted">{esc(odd_pupils_note(view))}</p>'
    if view.federation_years & set(by_year):
        html += ('<p class="small muted">No per-pupil figure is shown for the parents\' association in years when this school\'s '
                 'return covers its whole federation: those pupil counts are every school\'s, and the association is this school\'s own.</p>')
    html += _pta_national(view, by_year)
    watch = _watch(item, "ptfa")
    if watch:
        html += f'<p class="sp-watch">{watch.strip()} — a short video of these figures for your committee or newsletter.</p>'
    return _section("ptfa", "Money raised by parents", html + nearby_fundraising(item, view))


# ----------------------------------------------------------------- profile, split, context, questions

def intake_section(item, view) -> str:
    profile = view.ctx.get("profile")
    if not profile:
        return ""
    t = profile.get("tags") or {}
    parts = [t.get("governance"), t.get("phase"), t.get("gender")]
    if t.get("trust"):
        parts.append(f'{t["trust"]} ({"multi-academy" if t.get("trust_size") == "multi" else "single-academy"} trust)')
    parts += [t.get("admissions"), t.get("faith"), "sixth form" if t.get("sixth_form") else None]
    html = '<p class="tags">' + " · ".join(esc(p) for p in parts if p) + "</p>" if any(parts) else ""
    facts = []
    intake = profile.get("intake") or {}
    if _num(intake.get("fsm_pct")) is not None:
        extra = [f"{label} {intake[k]:.0f}%" for k, label in (("fsm_pct_council", "council"), ("fsm_pct_england", "England"))
                 if _num(intake.get(k)) is not None]
        # Medians of school rates, not pupil-weighted rates, so say so: Hackney's median school is 52%.
        facts.append(f"{intake['fsm_pct']:.0f}% of pupils eligible for free school meals"
                     + (f" (median school: {', '.join(extra)})" if extra else ""))
    area = profile.get("area") or {}
    for key, text in (("imd_decile", "Neighbourhood deprivation decile {} of 10 (1 = most deprived)"),
                      ("idaci_decile", "Income deprivation affecting children: decile {} of 10 (1 = most deprived)"),
                      ("pct_level4_plus", "{:.0f}% of adults nearby hold a degree-level qualification"),
                      ("pct_owned", "{:.0f}% of nearby homes are owner-occupied"),
                      ("pct_social_rented", "{:.0f}% of nearby homes are social rented")):
        if _num(area.get(key)) is not None:
            facts.append(text.format(area[key]))
    if facts:
        html += '<ul class="sp-facts">' + "".join(f"<li>{esc(f)}</li>" for f in facts) + "</ul>"
    band = profile.get("band")
    if _num(band):
        html += (f'<p class="muted small">Intake band <span class="mf-band" data-mf="band">{int(band)} of 5</span> nationally, combining '
                 'free-school-meal eligibility and the deprivation of the school\'s neighbourhood (1 = least disadvantaged, 5 = most).</p>')
    if html:
        html += '<p class="small muted">Context, not a judgement: schools with different intakes get different funding and face different costs.</p>'
    return _section("intake", "Intake and area", html)


SPLIT = [("Teachers", "teaching_staff", ("teaching_staff", "supply_staff")),
         ("Support staff", "education_support_staff", ("education_support_staff",)),
         ("Buildings and grounds", "premises", ("premises",)),
         ("Energy", "energy", ("energy",)),
         ("Learning resources", "educational_supplies", ("educational_supplies",))]


def split_section(item, view) -> str:
    latest = view.latest
    total = view.clean(SPEND, latest) if latest else None
    if not total or total <= 0:
        return ""
    pupils = view.pupils_for(latest)
    parts = []
    for label, key, metrics in SPLIT:
        vals = [view.clean(k, latest) for k in metrics]
        if vals[0] is None:
            continue
        parts.append((label, key, sum(v for v in vals if v is not None)))
    if not parts:
        return ""
    rest = total - sum(v for _, _, v in parts)
    if rest > 0:
        parts.append(("Everything else", "per_pupil", rest))
    items = "".join(f'<li style="--w:{max(v / total * 100, 1):.0f}%"><span class="lbl">{esc(label)}</span> '
                    f'{site.money_figure(key, v, pupils, latest, label=label)}</li>' for label, key, v in parts)
    each = ", with the amount for each pupil" if pupils else ""
    html = (f'<p>For pupils: out of every pound the school spent in {esc(latest)}, here is roughly where it went{each}.</p>'
            f'<ul class="sp-split">{items}</ul>')
    if latest in view.odd_pupils:
        html += f'<p class="small muted">{esc(odd_pupils_note(view))}</p>'
    return _section("split", "How my school's money is split", html)


def _flag_on(view, item, term) -> bool:
    term = term.strip()
    st = (item.get("status") or {}).get("status")
    if term == "always":
        return True
    if term.startswith("phase =="):
        return view.phase == term.split("==", 1)[1].strip()
    if term.startswith("status in"):
        return st in {s.strip() for s in term.split("(", 1)[-1].rstrip(")").split(",")}
    if term.startswith("status =="):
        return st == term.split("==", 1)[1].strip()
    if term == "academy":
        return view.academy
    if term in ("falling_rolls", "high_send"):
        return bool(view.flags.get(term))
    if term.endswith("> 0"):
        return (view.clean(term.split(">")[0].strip(), view.latest) or 0) > 0 if view.latest else False
    if term == "has sixth form":
        return bool((item.get("school") or {}).get("sixth_form") or ((view.ctx.get("profile") or {}).get("tags") or {}).get("sixth_form"))
    if term.startswith("income rose sharply"):
        return bool(view.flags.get("pass_through"))
    return False


USED_ELSEWHERE = {"per_pupil_primary", "per_pupil_secondary", "staff_share", "trust_central", "pass_through"}


def context_section(item, view) -> str:
    lines = [ln for ln in (view.ifs.get("context_lines") or {}).get("school") or []
             if ln.get("id") not in USED_ELSEWHERE and ln.get("text")
             and any(_flag_on(view, item, t) for t in str(ln.get("use_when", "")).split(" or "))]
    if not lines:
        return ""
    html = "<ul>" + "".join(f'<li>{ifs_text(ln["text"])}{ifs_cite(ln.get("page"))}</li>' for ln in lines) + "</ul>"
    return _section("context", "National context", html)


def _fill(text, item, view) -> str:
    """Fill {name} {overseer} {reserve} {years}, escaping the words and keeping £ figures as money figures."""
    st = item.get("status") or {}
    reserve = status_reserve_figure(item, view) or "its reserve"
    subs ={"{name}": esc(item["name"]), "{overseer}": esc(_overseer(item)), "{reserve}": reserve,
            "{years}": esc(st.get("deficit_streak") or "several")}
    out, last = [], 0
    for m in re.finditer(r"\{(name|overseer|reserve|years)\}", text):
        out.append(ifs_text(text[last:m.start()]))
        out.append(subs[m.group(0)])
        last = m.end()
    out.append(ifs_text(text[last:]))
    return "".join(out)


def questions_section(item, view) -> str:
    qs = view.ifs.get("questions") or {}
    st = (item.get("status") or {}).get("status")
    triggers = [t for t, on in ((st, bool(st)), ("falling_rolls", bool(view.flags.get("falling_rolls"))),
                                ("high_send", bool(view.flags.get("high_send"))), ("academy", view.academy), ("any", True)) if on]
    lists = [list((qs.get(t) or {}).get("questions") or []) for t in triggers]
    picked = []
    while any(lists) and len(picked) < MAX_QUESTIONS:
        for lst in lists:
            if lst and len(picked) < MAX_QUESTIONS:
                picked.append(lst.pop(0))
    if not picked:
        return ""
    items = []
    for q in picked:
        html = _fill(q.get("text", ""), item, view)
        if q.get("why"):
            html += f' <small class="why">Why ask: {ifs_text(q["why"])}{ifs_cite(q.get("page"))}</small>'
        items.append(f"<li>{html}</li>")
    return _section("questions", "Questions to ask the school",
                    "<p>Useful for parents, governors and PTFA committees.</p><ol class=\"sp-questions\">" + "".join(items) + "</ol>")


def similar_list(item, view=None) -> str:
    others = [o for o in item.get("similar") or [] if o.get("path") and o.get("name")][:SIMILAR_LISTED]
    if not others:
        return ""
    lis = "".join(f'<li><a href="{esc(o["path"])}" data-preview="school:{esc(o["urn"])}">{esc(o["name"])}</a></li>' for o in others)
    near = ",".join([str(item["urn"])] + [str(o["urn"]) for o in others[:3]])
    meta = similar_meta(view) if view is not None else None
    intro = "Similar schools: the closest in phase, size and share of pupils on free school meals."
    if meta:
        intro = (f"{similar_words(view)[:1].upper()}{similar_words(view)[1:]}: the closest in phase, size and share of pupils on free "
                 "school meals, chosen by School Money (not the DfE's own comparator set).")
        if meta.get("method"):
            intro += f" {meta['method']}"
    return (f'<p>{esc(intro)}</p><ul class="sp-similar">{lis}</ul>'
            f'<p><a class="button quiet" href="/compare/?urns={esc(near)}">Compare side by side</a></p>')


def check_section(item, view) -> str:
    council = item.get("council") or {}
    links = [f'<a href="{esc(view.ctx["sir_url"])}">Admissions and catchments for {esc(item["name"])} on Schools in Reach</a>'] if view.ctx.get("sir_url") else []
    if council.get("path"):
        links.append(f'<a href="{esc(council["path"])}">All {esc(council.get("name") or "council")} school finances</a>')
    if item.get("constituency_path"):
        links.append(f'<a href="{esc(item["constituency_path"])}">Schools in {esc(item.get("constituency") or "this constituency")}</a>')
    if item.get("trust_path") and item.get("trust"):
        links.append(f'<a href="{esc(item["trust_path"])}">{esc(item["trust"])}</a>')
    src = view.ifs.get("source") or {}
    cite, url = src.get("short_cite") or site.IFS_CITE, src.get("url") or site.IFS_URL
    sources = [f'<a href="{FBIT_SOURCES}">DfE Financial Benchmarking and Insights Tool data</a>: CFR returns for council-run schools '
               '(April to March) and academy accounts returns (September to August), Open Government Licence v3.0',
               f'<a href="{GIAS}">Get Information about Schools</a>, Open Government Licence v3.0']
    if item.get("pta"):
        sources.append(f'<a href="{CHARITY_REGISTER}">Charity Commission register</a>, Open Government Licence v3.0')
    sources.append(f'National context: <a href="{esc(url)}" rel="noopener">{esc(cite)}</a>; IFS figures are in 2025-26 prices '
                   '(HM Treasury GDP deflator, November 2025)')
    if view.real_label:
        sources.append(f"Real-terms figures on this page: {esc(view.real_label)}")
    if view.academy:
        html = (f'<p>Every figure here comes from the academy\'s own accounts return. Check it on the '
                f'<a href="{esc(view.check)}">DfE benchmarking page for this school</a>, and see <a href="/about/">how the figures are worked out</a>. '
                'The DfE benchmarking page apportions the trust\'s central income and spending into each academy\'s figures and this page '
                'does not, so its income, spending and balances will differ from the ones here.</p>')
    else:
        html = (f'<p>Every figure here comes from the school\'s published return. Check it on the '
                f'<a href="{esc(view.check)}">DfE benchmarking page for this school</a>, and see <a href="/about/">how the figures are worked out</a>.</p>')
    html += similar_list(item, view)
    if links:
        html += '<p class="sp-links">' + " · ".join(links) + "</p>"
    html += '<ul class="sp-sources small">' + "".join(f"<li>{s}</li>" for s in sources) + "</ul>"
    return _section("check", "Check at source", html)


def _toc(body) -> str:
    names = [("status", "Status"), ("funding", "Funding vs spending"), ("reserve", "Reserves"), ("income", "Income"),
             ("spending", "Spending"), ("nearby", "Nearby"), ("pupils", "Pupils"), ("trust-central", "Trust"), ("ptfa", "PTA"),
             ("questions", "Questions"), ("check", "Check")]
    links = "".join(f'<li><a href="#{i}">{n}</a></li>' for i, n in names if f'id="{i}"' in body)
    return f'<nav class="sp-toc" aria-label="On this page"><ul>{links}</ul></nav>'


def _intro(item, view) -> str:
    s = item.get("school") or {}
    council = item.get("council") or {}
    kind = ("an academy (accounts return, September to August)" if view.academy
            else "a council-run school (CFR return, April to March)")
    bits = []
    if council.get("path"):
        bits.append(f'<a href="{esc(council["path"])}" data-preview="area:council-{esc(council.get("code", ""))}">{esc(council.get("name", ""))}</a>')
    bits += [esc(x) for x in (s.get("phase"), s.get("type")) if x]
    latest = f"Latest full year {esc(view.latest)}, as {kind}. " if view.latest else ""
    return f'<p class="muted small">{latest}{" · ".join(bits)}</p>' + federation_note(item, view)


def _latest_row(item, view):
    """The finance row behind the page's latest year (the later return in a conversion year), or None."""
    rows = [r for r in item.get("rows") or [] if str(r.get("year", "")).replace("/", "-") == view.latest
            and r.get("period_months", 12) == 12 and not r.get("did_not_supply")]
    return max(rows, key=lambda r: str(r.get("period_end") or "")) if rows else None


def federation_note(item, view) -> str:
    """For a federation lead school's combined return: the money and the pupils are the whole federation's."""
    row = _latest_row(item, view)
    if not row or row.get("federated") != "Lead school":
        return ""
    name = (item.get("school") or {}).get("federation") or "federation"
    pupils = _num(row.get("pupils"))
    count = f": {pupils:,.1f} pupils across its schools" if pupils else ""
    text = (f"These figures cover the whole {name}{count}. This school makes one combined return for the federation, so its "
            "totals are the federation's, not one school's.")
    return f'<p class="note sp-fed">{esc(text)}</p>'


# ----------------------------------------------------------------- the page

def _plain_page(item, view, lead) -> dict:
    body = (f'<h1>{esc(item["name"])}: school finances</h1><p class="lead">{lead}</p>'
            f'<p>Check at source: <a href="{esc(view.check)}">DfE benchmarking page for this school</a>.</p>')
    return {"title": shorten(f"{item['name']} finances | School Money", 70),
            "description": shorten(f"Finance returns for {item['name']}, from published DfE data.", 160),
            "body": body, "indexable": False}


def render(item, ctx) -> dict:
    """The school page: {'title', 'description', 'body' (escaped HTML), 'indexable'}."""
    view = _View(item, ctx)
    if item.get("member_of"):
        lead = item.get("lead")
        who = (f'<a href="{esc(lead["path"])}">{esc(lead["name"])}</a>' if lead and lead.get("path") else "the lead school")
        return _plain_page(item, view, "This school is part of a federation. Its money is reported in one combined return made by "
                           f"{who}, so its figures and status are shown on that school's page.")
    if not item.get("status"):
        return _plain_page(item, view, "No full-year finance return is published for this school yet, usually because it opened, "
                           "converted to an academy or changed trust part-way through the year.")
    before = "".join([status_section(item, view), funding_section(item, view), reserve_section(item, view),
                      income_section(item, view), spending_section(item, view)])
    after = "".join([pupils_section(item, view), pass_through_section(item, view), trust_section(item, view), pta_section(item, view),
                     intake_section(item, view), split_section(item, view), context_section(item, view),
                     questions_section(item, view), check_section(item, view)])
    head = f'<h1>{esc(item["name"])}: school finances</h1>{_intro(item, view)}'
    nearby = dict.fromkeys([nearby_section(item, view, level) for level in NEARBY_LEVELS] + [""])
    bodies = [f"{head}{_toc(before + n + after)}{before}{n}{after}" for n in nearby]
    st = item["status"]
    span = f"{view.first} to {view.latest}" if view.first and view.first != view.latest else (view.latest or "")
    return {
        "title": shorten(f"{item['name']} finances: {st['label']} | School Money", 70),
        "description": shorten(f"{item['name']}: {st['reason']} Funding, spending, reserves and PTA money, {span}.", 160),
        "body": bodies[0],
        "lighter": bodies[1:],
        "indexable": True,
    }
