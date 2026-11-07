"""Inline SVG charts for the Money pages. Static markup only; money.js adds hover tooltips.

Every chart ships with a text alternative (a table or a sentence) on the page, colours
come from CSS variables in money.css (light and dark), and status colours always sit
beside their icon and label, never alone.
"""

from __future__ import annotations

import re
from html import escape

STATUS_ORDER = ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves"]
STATUS_LABELS = {
    "in_deficit": "In deficit",
    "heading_for_deficit": "Heading for deficit",
    "tight": "Tight",
    "healthy": "Healthy",
    "large_reserves": "Large reserves",
}
STATUS_ICONS = {
    "in_deficit": "▼",
    "heading_for_deficit": "↘",
    "tight": "●",
    "healthy": "✓",
    "large_reserves": "▲",
}


def esc(value) -> str:
    return escape(str(value), quote=True)


def money(value, signed=False) -> str:
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


def badge(status: str, size: str = "") -> str:
    return (f'<span class="badge s-{esc(status)} {esc(size)}"><span aria-hidden="true">{STATUS_ICONS[status]}</span> '
            f'{esc(STATUS_LABELS[status])}</span>')


def _nice_step(span: float) -> float:
    raw = span / 4 or 1
    mag = 10 ** len(str(int(raw))) / 10
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * mag:
            return mult * mag
    return 10 * mag


def _ticks(lo: float, hi: float) -> list[float]:
    """Round tick values from lo to hi; always at least one, whatever the order or span."""
    lo, hi = min(lo, hi), max(lo, hi)
    step = _nice_step(hi - lo)
    start = (lo // step) * step
    out, v = [], start
    while v <= hi + step * 0.01:
        out.append(v)
        v += step
    return out or [lo]


def _num(value):
    """A finite number, or None for anything else (None, text, nan)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def reserve_bars(years: list[dict], width: int = 640, height: int = 200) -> str:
    """Revenue reserve at the end of each year: bars up from zero when positive, down when negative."""
    pts = [(y["year"], _num(y.get("reserve"))) for y in years]
    pts = [(label, v) for label, v in pts if v is not None]
    if not pts:
        return ""
    values = [v for _, v in pts]
    lo, hi = min(0, min(values)), max(0, max(values))
    if lo == hi:
        hi = 1
    ticks = _ticks(lo, hi)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    left, right, top, bottom = 56, 8, 10, 26
    plot_w, plot_h = width - left - right, height - top - bottom

    def y_of(v):
        return top + (hi - v) / (hi - lo) * plot_h

    slot = plot_w / len(pts)
    bar_w = min(40, slot - 6)
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Revenue reserve at the end of each year">']
    for t in ticks:
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y_of(t):.1f}" y2="{y_of(t):.1f}"/>'
                     f'<text class="tick" x="{left - 6}" y="{y_of(t) + 4:.1f}" text-anchor="end">{esc(money(t))}</text>')
    zero = y_of(0)
    for i, (label, v) in enumerate(pts):
        x = left + i * slot + (slot - bar_w) / 2
        y0, y1 = sorted((zero, y_of(v)))
        h = max(y1 - y0, 1)
        cls = "neg" if v < 0 else "pos"
        # Rounded data-end only: a full rounded rect, squared off at the baseline by an overlay.
        r = min(4, h / 2)
        if v >= 0:
            path = f"M{x:.1f},{zero:.1f}V{y0 + r:.1f}Q{x:.1f},{y0:.1f} {x + r:.1f},{y0:.1f}H{x + bar_w - r:.1f}Q{x + bar_w:.1f},{y0:.1f} {x + bar_w:.1f},{y0 + r:.1f}V{zero:.1f}Z"
        else:
            path = f"M{x:.1f},{zero:.1f}V{y1 - r:.1f}Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f}H{x + bar_w - r:.1f}Q{x + bar_w:.1f},{y1:.1f} {x + bar_w:.1f},{y1 - r:.1f}V{zero:.1f}Z"
        tip = f"{label}: {money(v)} reserve"
        parts.append(f'<g class="mark" tabindex="0" data-tip="{esc(tip)}"><title>{esc(tip)}</title>'
                     f'<rect class="hit" x="{left + i * slot:.1f}" y="{top}" width="{slot:.1f}" height="{plot_h}"/>'
                     f'<path class="bar {cls}" d="{path}"/></g>')
        parts.append(f'<text class="tick" x="{x + bar_w / 2:.1f}" y="{height - 8}" text-anchor="middle">{esc(label)}</text>')
    parts.append(f'<line class="axis" x1="{left}" x2="{width - right}" y1="{zero:.1f}" y2="{zero:.1f}"/></svg>')
    return "".join(parts)


def income_spend_lines(years: list[dict], width: int = 640, height: int = 200) -> str:
    """Income and spending per year on one £ axis (same unit, so one scale)."""
    pts = [y for y in years if _num(y.get("income")) is not None and _num(y.get("spend")) is not None]
    if len(pts) < 2:
        return ""
    values = [y["income"] for y in pts] + [y["spend"] for y in pts]
    lo, hi = min(values), max(values)
    lo, hi = lo - abs(lo) * 0.05, hi + abs(hi) * 0.03
    if hi <= lo:
        hi = lo + 1
    ticks = _ticks(lo, hi)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    left, right, top, bottom = 56, 72, 10, 26
    plot_w, plot_h = width - left - right, height - top - bottom
    step = plot_w / (len(pts) - 1)

    def xy(i, v):
        return left + i * step, top + (hi - v) / (hi - lo) * plot_h

    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Income and spending each year">']
    for t in ticks:
        y = xy(0, t)[1]
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/>'
                     f'<text class="tick" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{esc(money(t))}</text>')
    for key, cls, name in (("income", "s1", "Income"), ("spend", "s2", "Spending")):
        d = "M" + "L".join(f"{xy(i, y[key])[0]:.1f},{xy(i, y[key])[1]:.1f}" for i, y in enumerate(pts))
        parts.append(f'<path class="line {cls}" d="{d}"/>')
        ex, ey = xy(len(pts) - 1, pts[-1][key])
        parts.append(f'<circle class="dot {cls}" cx="{ex:.1f}" cy="{ey:.1f}" r="4"/>'
                     f'<text class="direct" x="{ex + 8:.1f}" y="{ey + 4:.1f}">{name}</text>')
    for i, y in enumerate(pts):
        x = xy(i, 0)[0]
        tip = f"{y['year']}: income {money(y['income'])}, spending {money(y['spend'])}"
        parts.append(f'<g class="mark" tabindex="0" data-tip="{esc(tip)}"><title>{esc(tip)}</title>'
                     f'<rect class="hit" x="{x - step / 2:.1f}" y="{top}" width="{step:.1f}" height="{plot_h}"/></g>'
                     f'<text class="tick" x="{x:.1f}" y="{height - 8}" text-anchor="middle">{esc(y["year"])}</text>')
    parts.append("</svg>")
    legend = ('<p class="legend"><span class="key line s1"></span>Income <span class="key line s2"></span>Spending</p>')
    return legend + "".join(parts)


def status_bar(counts: dict, total: int | None = None) -> str:
    """One stacked bar of how many schools sit in each status, with a text legend."""
    counts = {s: _num(counts.get(s)) or 0 for s in STATUS_ORDER}
    total = total or sum(counts.values())
    if not total:
        return ""
    segs, x = [], 0.0
    for s in STATUS_ORDER:
        n = counts[s]
        if n <= 0:
            continue
        w = n / total * 100
        tip = f"{STATUS_LABELS[s]}: {n:,} schools ({n / total:.0%})"
        segs.append(f'<span class="seg s-{s}" style="width:{w:.2f}%" tabindex="0" data-tip="{esc(tip)}" title="{esc(tip)}"></span>')
        x += w
    legend = "".join(f'<li>{badge(s, "small")} <strong>{counts.get(s, 0):,}</strong> <span class="muted">({counts.get(s, 0) / total:.0%})</span></li>'
                     for s in STATUS_ORDER)
    return f'<div class="statusbar" role="img" aria-label="Schools by financial status">{"".join(segs)}</div><ul class="statuslegend">{legend}</ul>'


def count_bars(series: list[tuple[str, int, int]], width: int = 640, height: int = 180, what: str = "schools in deficit") -> str:
    """Share of schools per year (label, count, out_of), drawn as a percentage so a shrinking
    group (council-run schools becoming academies) doesn't read as improvement."""
    series = [(label, max(n, 0) / out_of * 100, out_of, max(n, 0)) for label, n, out_of in series
              if _num(out_of) and out_of > 0 and _num(n) is not None]
    if not series:
        return ""
    hi = max(1, max(c for _, c, _, _ in series))
    ticks = _ticks(0, hi)
    hi = max(hi, ticks[-1])
    left, right, top, bottom = 44, 8, 16, 26
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / len(series)
    bar_w = min(40, slot - 6)
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Number of {esc(what)} each year">']
    for t in ticks:
        y = top + (hi - t) / hi * plot_h
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/>'
                     f'<text class="tick" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{t:g}%</text>')
    base = top + plot_h
    for i, (label, n, out_of, count) in enumerate(series):
        x = left + i * slot + (slot - bar_w) / 2
        y = top + (hi - n) / hi * plot_h
        h = base - y
        r = min(4, h / 2)
        tip = f"{label}: {count:,} of {out_of:,} schools ({n:.1f}%)"
        path = f"M{x:.1f},{base:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}H{x + bar_w - r:.1f}Q{x + bar_w:.1f},{y:.1f} {x + bar_w:.1f},{y + r:.1f}V{base:.1f}Z"
        parts.append(f'<g class="mark" tabindex="0" data-tip="{esc(tip)}"><title>{esc(tip)}</title>'
                     f'<rect class="hit" x="{left + i * slot:.1f}" y="{top}" width="{slot:.1f}" height="{plot_h}"/>'
                     f'<path class="bar neg" d="{path}"/></g>'
                     f'<text class="tick" x="{x + bar_w / 2:.1f}" y="{height - 8}" text-anchor="middle">{esc(label)}</text>')
    label, n, _, _ = series[-1]
    x = left + (len(series) - 1) * slot + slot / 2
    parts.append(f'<text class="direct" x="{x:.1f}" y="{top + (hi - n) / hi * plot_h - 4:.1f}" text-anchor="middle">{n:.1f}%</text>')
    parts.append(f'<line class="axis" x1="{left}" x2="{width - right}" y1="{base:.1f}" y2="{base:.1f}"/></svg>')
    return "".join(parts)


def compare_dots(rows: list[dict], width: int = 640) -> str:
    """Per-pupil spend by category: similar schools' middle half as a band, their median as
    a tick, this school as a dot. rows: {label, value, p25, median, p75}."""
    rows = [r for r in rows if all(_num(r.get(k)) is not None for k in ("value", "median", "p25", "p75"))]
    if not rows:
        return ""
    row_h, top, left, right = 34, 8, 190, 64
    height = top + row_h * len(rows) + 8
    values = [r[k] for r in rows for k in ("value", "p25", "median", "p75")]
    lo, hi = min(0, min(values)), max(0, max(values))
    span = (hi - lo) or 1
    lo, hi = (lo - span * 0.08 if lo < 0 else 0), hi + span * 0.08  # room for the dot at either end
    plot_w = width - left - right

    def x_of(v):
        return left + (v - lo) / (hi - lo) * plot_w

    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Spending per pupil compared with similar schools">']
    for i, r in enumerate(rows):
        cy = top + i * row_h + row_h / 2
        tip = (f"{r['label']}: this school £{r['value']:,.0f} per pupil; similar schools £{r['median']:,.0f} "
               f"(middle half £{r['p25']:,.0f}–£{r['p75']:,.0f})")
        parts.append(f'<g class="mark" tabindex="0" data-tip="{esc(tip)}"><title>{esc(tip)}</title>'
                     f'<rect class="hit" x="0" y="{cy - row_h / 2:.1f}" width="{width}" height="{row_h}"/>'
                     f'<text class="cat" x="{left - 10}" y="{cy + 4:.1f}" text-anchor="end">{esc(r["label"])}</text>'
                     f'<line class="track" x1="{left}" x2="{width - right}" y1="{cy:.1f}" y2="{cy:.1f}"/>'
                     f'<rect class="band" x="{x_of(r["p25"]):.1f}" y="{cy - 6:.1f}" width="{max(x_of(r["p75"]) - x_of(r["p25"]), 2):.1f}" height="12" rx="4"/>'
                     f'<line class="median" x1="{x_of(r["median"]):.1f}" x2="{x_of(r["median"]):.1f}" y1="{cy - 9:.1f}" y2="{cy + 9:.1f}"/>'
                     f'<circle class="dot s1 ring" cx="{x_of(r["value"]):.1f}" cy="{cy:.1f}" r="6"/>'
                     f'<text class="direct" x="{width - right + 8}" y="{cy + 4:.1f}">£{r["value"]:,.0f}</text></g>')
    if lo < 0:
        parts.append(f'<line class="axis" x1="{x_of(0):.1f}" x2="{x_of(0):.1f}" y1="{top}" y2="{height - 8}"/>')
    parts.append("</svg>")
    legend = ('<p class="legend"><span class="key dot s1"></span>This school <span class="key band"></span>Middle half of similar schools '
              '<span class="key median"></span>Similar schools’ median</p>')
    return legend + "".join(parts)


TREND_COLOURS = ("--c1", "--c2", "--c3", "--c4")


def _axis_text(value: float, unit: str, exact: bool = False) -> str:
    """An axis or tip value: percentages, pupil counts, or £ (to the pound when exact, e.g. per pupil)."""
    if unit == "%":
        return f"{value:g}%"
    if unit == "pupils":
        return f"{value:,.0f}"
    if exact:
        return f"{'-' if value < 0 else ''}£{abs(value):,.0f}"
    return money(value)


def _spread(ys: list[float], gap: float, top: float, bottom: float) -> list[float]:
    """Label y positions in the given order, nudged apart so no two sit closer than gap."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    last = None
    for i in order:
        y = max(out[i], top) if last is None else max(out[i], last + gap)
        out[i] = last = y
    overflow = (last or 0) - bottom
    if overflow > 0:
        out = [y - overflow for y in out]
    return out


def trend_chart(lines: list[dict], *, years: list[str], unit: str = "£", title: str, desc: str, height: int = 220,
                suspect=(), partial=()) -> str:
    """Lines over years on one axis, each labelled at its end so colour is never the only key.
    lines: [{label, values {year: number|None}, style solid|dashed, emph, basis cash|real|None}].
    None leaves a gap; suspect years get hollow markers; segments into partial years are dashed.
    Lines with a basis sit in <g data-basis> groups (real hidden by default) for trend.js to switch.
    Kept lean for pages with several charts: whole-pixel coordinates, colours by class (app.css styles
    s1 and s2; later series carry their colour inline), one colour per label in both bases, and markers
    only at line ends, on points with no neighbour, and (hollow) in suspect years."""
    years = [str(y) for y in years]
    suspect, partial = {str(y) for y in suspect or ()}, {str(y) for y in partial or ()}
    values = [v for line in lines for v in (_num((line.get("values") or {}).get(y)) for y in years) if v is not None]
    width, left, right, top, bottom = 480, 52, 104, 10, 24
    head = (f'<svg class="chart trend" viewBox="0 0 {width} {height}" role="img"><title>{esc(title)}</title>'
            f'<desc>{esc(desc)}</desc>')
    if not years or not values:
        return head + "</svg>"
    lo, hi = min(values), max(values)
    if lo == hi:
        lo, hi = lo - (abs(lo) * 0.1 or 1), hi + (abs(hi) * 0.1 or 1)
        lo = 0 if min(values) >= 0 > lo else lo
    ticks = _ticks(lo, hi)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    exact = max(abs(lo), abs(hi)) < 100_000  # per-pupil scales read better to the pound
    plot_w, plot_h = width - left - right, height - top - bottom

    def x_of(i):
        return round(left + (i * plot_w / (len(years) - 1) if len(years) > 1 else plot_w / 2))

    def y_of(v):
        return round(top + (hi - v) / (hi - lo) * plot_h)

    parts = [head]
    for t in ticks:
        parts.append(f'<path class="grid" d="M{left},{y_of(t)}H{width - right}"/>'
                     f'<text class="tick" x="{left - 5}" y="{y_of(t) + 4}" text-anchor="end">{esc(_axis_text(t, unit, exact))}</text>')
    if lo < 0 < hi:
        parts.append(f'<path class="axis" d="M{left},{y_of(0)}H{width - right}"/>')
    every = 1 if len(years) <= 5 else 2
    for i, y in enumerate(years):
        if (len(years) - 1 - i) % every == 0:
            parts.append(f'<text class="tick" x="{x_of(i)}" y="{height - 6}" text-anchor="middle">{esc(y)}</text>')
    groups, colour_of = {}, {}
    for line in lines:
        colour_of.setdefault(line.get("label", ""), len(colour_of))
        groups.setdefault(line.get("basis"), []).append((colour_of[line.get("label", "")], line))
    for basis, members in groups.items():
        ends, body = [], []
        for n, line in members:
            colour = f"var({TREND_COLOURS[n % len(TREND_COLOURS)]})"
            cls = f"s{n % len(TREND_COLOURS) + 1}"
            inline = f' style="stroke:{colour}"' if n % len(TREND_COLOURS) > 1 else ""
            pts = [(i, _num((line.get("values") or {}).get(y))) for i, y in enumerate(years)]
            known = [i for i, v in pts if v is not None]
            if not known:  # nothing to draw or label for this line
                continue
            solid, dashed = "", ""
            for (i, a), (j, b) in zip(pts, pts[1:]):
                if a is not None and b is not None:
                    seg = f"M{x_of(i)},{y_of(a)}L{x_of(j)},{y_of(b)}"
                    if years[j] in partial:
                        dashed += seg
                    else:
                        solid += seg
            solid = re.sub(r"L(\d+,\d+)M\1", r"L\1", solid)  # join touching segments into one run
            stroke = f'fill="none"{" stroke-width=\"3\"" if line.get("emph") else ""}{inline}'
            if solid:
                dash = ' stroke-dasharray="6 4"' if line.get("style") == "dashed" else ""
                body.append(f'<path class="line {cls}{" emph" if line.get("emph") else ""}" d="{solid}" {stroke}{dash}/>')
            if dashed:
                body.append(f'<path class="line {cls} partial" d="{dashed}" {stroke} stroke-dasharray="2 4"/>')
            for i, v in pts:
                if v is None:
                    continue
                alone = (i == 0 or pts[i - 1][1] is None) and (i == len(pts) - 1 or pts[i + 1][1] is None)
                if years[i] in suspect:
                    tip = f"{line.get('label', '')}, {years[i]}: {_axis_text(v, unit, exact)} (figure under review)"
                    body.append(f'<circle class="pt hollow" cx="{x_of(i)}" cy="{y_of(v)}" r="4" stroke-width="2" '
                                f'style="stroke:{colour};fill:var(--paper,#fff)"><title>{esc(tip)}</title></circle>')
                elif alone or i == known[-1]:
                    fill = f' style="fill:{colour}"' if inline else ""
                    body.append(f'<circle class="dot {cls}" cx="{x_of(i)}" cy="{y_of(v)}" r="3"{fill}/>')
            ends.append((y_of(pts[known[-1]][1]) + 4, x_of(known[-1]) + 7, line.get("label", "")))
        label_ys = _spread([e[0] for e in ends], 13, top + 4, top + plot_h + 4)
        body += [f'<text class="direct" x="{x}" y="{round(ly)}">{esc(text)}</text>' for (_, x, text), ly in zip(ends, label_ys)]
        if basis in ("cash", "real"):
            hidden = ' display="none"' if basis == "real" else ""
            parts.append(f'<g data-basis="{basis}"{hidden}>{"".join(body)}</g>')
        else:
            parts.append("".join(body))
    parts.append("</svg>")
    return "".join(parts)


SPARK_MAX = 400


def sparkline(values, *, width: int = 96, height: int = 24, label: str) -> str:
    """A tiny trend line of [(year, value)] for a table cell: 400 bytes or less, labelled for screen readers.
    None values leave a gap. The line takes the text colour; pages may restyle svg.spark path."""
    pts = [(i, _num(v)) for i, (_, v) in enumerate(values or [])]
    known = [v for _, v in pts if v is not None]
    if not known:
        return ""
    lo, hi = min(known), max(known)
    span = (hi - lo) or 1
    n = max(len(pts) - 1, 1)
    d, gap = "", True
    for i, v in pts:
        if v is None:
            gap = True
            continue
        d += f"{'M' if gap else 'L'}{round(2 + i * (width - 4) / n)},{round(height - 2 - (v - lo) / span * (height - 4))}"
        gap = False

    def svg(text):
        return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{esc(text)}">'
                f'<path d="{d}" fill="none" stroke="currentColor"/></svg>')

    out, text = svg(label), str(label)
    while len(out.encode("utf-8")) > SPARK_MAX and text:
        text = text[:-8] if len(text) > 8 else ""
        out = svg(text.rstrip() + "…" if text else "")
    return out if len(out.encode("utf-8")) <= SPARK_MAX else ""
