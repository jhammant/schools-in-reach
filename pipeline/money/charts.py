"""Inline SVG charts for the Money pages. Static markup only; money.js adds hover tooltips.

Every chart ships with a text alternative (a table or a sentence) on the page, colours
come from CSS variables in money.css (light and dark), and status colours always sit
beside their icon and label, never alone.
"""

from __future__ import annotations

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
    step = _nice_step(hi - lo)
    start = (lo // step) * step
    out, v = [], start
    while v <= hi + step * 0.01:
        out.append(v)
        v += step
    return out


def reserve_bars(years: list[dict], width: int = 640, height: int = 200) -> str:
    """Revenue reserve at the end of each year: bars up from zero when positive, down when negative."""
    pts = [(y["year"], y["reserve"]) for y in years if y.get("reserve") is not None]
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
    pts = [y for y in years if y.get("income") is not None and y.get("spend") is not None]
    if len(pts) < 2:
        return ""
    values = [y["income"] for y in pts] + [y["spend"] for y in pts]
    lo, hi = min(values) * 0.95, max(values) * 1.03
    ticks = _ticks(lo, hi)
    lo, hi = ticks[0], max(hi, ticks[-1])
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
    total = total or sum(counts.get(s, 0) for s in STATUS_ORDER)
    if not total:
        return ""
    segs, x = [], 0.0
    for s in STATUS_ORDER:
        n = counts.get(s, 0)
        if not n:
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
    series = [(label, n / out_of * 100, out_of, n) for label, n, out_of in series if out_of]
    if not series:
        return ""
    hi = max(c for _, c, _, _ in series) or 1
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
    rows = [r for r in rows if r.get("value") is not None and r.get("median") is not None]
    if not rows:
        return ""
    row_h, top, left, right = 34, 8, 190, 64
    height = top + row_h * len(rows) + 8
    hi = max(max(r["value"], r.get("p75") or 0) for r in rows) * 1.08 or 1
    plot_w = width - left - right

    def x_of(v):
        return left + v / hi * plot_w

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
    parts.append("</svg>")
    legend = ('<p class="legend"><span class="key dot s1"></span>This school <span class="key band"></span>Middle half of similar schools '
              '<span class="key median"></span>Similar schools’ median</p>')
    return legend + "".join(parts)
