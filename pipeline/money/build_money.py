#!/usr/bin/env python3
"""Build the Money section (site/money/): English school finances from DfE returns.

Inputs are local and rebuilt by pipelines; no network:
- pipeline/.cache/dfe/finance_history.jsonl from pipeline/dfe/finance_history.py
- site/data (school register and council index, from pipeline/dfe/build.py)
- pipeline/.cache/dfe/gias/links.csv (GIAS links: a converted academy's predecessor URN)
- pipeline/.cache/money/pta.json from pipeline/money/pta.py (optional)

Writes site/money/ (national, council, school and trust pages, compare tool, method page,
per-school JSON for the compare tool) and site/money/sitemap.xml. Run before
pipeline/seo/build_pages.py, which links school pages here and adds the sitemap.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import shutil
import statistics
import tempfile
import time

from pipeline.money import charts, status as health
from pipeline.money.charts import STATUS_LABELS, STATUS_ORDER, badge, esc, money
from pipeline.seo.build_pages import HeadMetadata, LABS_FOOTER, closed, document, shorten, slug, table, write_sitemap

ROOT = Path(__file__).resolve().parents[2]
FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk"
FBIT_SOURCES = FBIT + "/data-sources"
CHARITY = "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/"
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
INCOME_KEYS = [("grant_funding", "Government grants"), ("sen_funding", "SEN funding (part of grants)"),
               ("pupil_premium", "Pupil premium (part of grants)"), ("self_generated", "Self-generated (lettings, catering, donations)")]
TOP_N = 25


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
    by_end = {}
    for r in rows:
        if r.get("did_not_supply") or r.get("period_months") != 12 or r.get("total_income") is None:
            continue
        by_end[r["period_end"]] = r
    return [by_end[k] for k in sorted(by_end)]


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


def trust_paths(names):
    """One distinct /money/trust/<slug>/ per trust name. Names whose slugs collide, or that
    slugify to nothing, get a short hash of the name so no page overwrites another."""
    by_slug = defaultdict(list)
    for name in names:
        by_slug[slug(name)].append(name)
    paths = {}
    for key, group in by_slug.items():
        for name in group:
            if len(group) > 1 or key == "school":
                key_for = f"{key}-{hashlib.sha1(name.encode('utf-8')).hexdigest()[:6]}"
            else:
                key_for = key
            paths[name] = f"/money/trust/{key_for}/"
    if len(set(paths.values())) != len(paths):
        raise ValueError("Trust pages would overwrite each other")
    return paths


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
                   "path": f"/money/council/{slug(la['name'])}/", "site_path": f"/council/{slug(la['name'])}/"}
        if any(c["path"] == council["path"] for c in councils):
            raise ValueError(f"Two councils share the page {council['path']}: {la['name']}")
        councils.append(council)
        for s in json.loads(reg_path.read_text(encoding="utf-8")).get("schools", []):
            if closed(s):
                continue
            urn = str(s["urn"])
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
                "path": f"/money/school/{urn}-{slug(s['name'])}/", "site_path": f"/school/{urn}-{slug(s['name'])}/",
                "rows": rows, "years": years, "latest": latest, "member_of": member,
                "status": None if member else health.assess(rows),
                "phase": phase_group(latest, s), "london": int(code) in LONDON if code.isdigit() else False,
                "fsm": s.get("fsm_pct") if s.get("fsm_pct") is not None else (latest or {}).get("fsm_pct"),
                "pta": pta.get(urn, []),
                "trust": (s.get("trust") or (latest or {}).get("trust") or "").strip() or None,
                "academy": (latest or {}).get("source") == "AAR",
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
    return f'<a href="{esc(item["path"])}">{esc(item["name"])}</a>'


def sources(extra=""):
    return ('<footer><h2>Sources and how to check</h2><ul>'
            f'<li><a href="{FBIT_SOURCES}">DfE Financial Benchmarking and Insights Tool data</a>: CFR returns for council-run schools (April–March) '
            'and Academy Accounts Returns (September–August) — Open Government Licence v3.0</li>'
            '<li><a href="https://get-information-schools.service.gov.uk/">Get Information about Schools</a> (school register and academy conversions) — Open Government Licence v3.0</li>'
            f'{extra}</ul><p><a href="/money/about/">How these figures are worked out</a> · <a href="/money/">School money home</a></p>'
            + LABS_FOOTER + "</footer>")


def page(title, description, path, body, crumbs, metadata, indexable=True):
    html = document(title, description, path, body, crumbs, metadata, indexable=indexable)
    return html.replace('<link rel="stylesheet" href="/css/seo.css">',
                        '<link rel="stylesheet" href="/css/seo.css"><link rel="stylesheet" href="/money/money.css">', 1
                        ).replace("</body>", '<script src="/money/money.js" defer></script></body>', 1)


def questions(item, cmp):
    st, q = item["status"], []
    kind = st["status"]
    academy = item["academy"]
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
    for r in sorted(cmp, key=lambda r: -(r["value"] / r["median"] if r["median"] else 0)):
        if r["value"] > r["p75"] * 1.1 and len(q) < 6:
            q.append(f"Spending on {r['label'].lower()} is £{r['value']:,.0f} a pupil, against a typical £{r['median']:,.0f} for similar schools. What's behind that?")
    if item["pta"]:
        q.append("How does the school decide what the money the parents' association raises is spent on?")
    return q[:6]


# ----------------------------------------------------------------- pages

def render_school(item, metadata):
    s, st = item["school"], item["status"]
    council = item["council"]
    crumbs = [("Home", "/"), ("School money", "/money/"), (council["name"], council["path"]), (item["name"], item["path"])]
    check = f'<a href="{FBIT}/school/{esc(item["urn"])}">DfE benchmarking page for this school</a>'
    if item.get("member_of"):
        lead = item.get("lead")
        lead_html = school_link(lead) if lead else "the lead school"
        body = (f'<h1>{esc(item["name"])}: school finances</h1><p class="lead">This school is part of a federation. Its money is reported '
                f'in one combined return made by {lead_html}, so its figures and status are shown on that school\'s page.</p>'
                f'<p>Check at source: {check}.</p>' + sources())
        return page(shorten(f"{item['name']} finances | Schools in Reach", 70),
                    shorten(f"{item['name']} reports its finances jointly with its federation. See the federation's combined figures.", 160),
                    item["path"], body, crumbs, metadata, indexable=False)
    if not st:
        body = (f'<h1>{esc(item["name"])}: school finances</h1><p class="lead">No full-year finance return is published for this school yet, '
                f'usually because it opened, converted to an academy or changed trust part-way through the year.</p><p>Check at source: {check}.</p>' + sources())
        return page(shorten(f"{item['name']} finances | Schools in Reach", 70), shorten(f"Finance returns for {item['name']}.", 160),
                    item["path"], body, crumbs, metadata, indexable=False)
    latest, years = item["latest"], item["years"]
    points = [{"year": year_label(r), "income": r.get("total_income"), "spend": r.get("total_expenditure"),
               "reserve": reserve_of(r), "pupils": r.get("pupils"), "balance": r.get("in_year_balance")} for r in years]
    span = f"{points[0]['year']} to {points[-1]['year']}" if len(points) > 1 else points[0]["year"]
    kind = "academy (accounts return, September–August)" if item["academy"] else "council-run school (CFR return, April–March)"
    body = f'<h1>{esc(item["name"])}: school finances</h1>'
    body += f'<p class="status-line">{badge(st["status"], "large")}</p><p class="lead">{esc(st["reason"])}</p>'
    body += (f'<p class="muted small">Latest full year {esc(year_label(latest))}, as a {kind}. '
             f'{esc(council["name"])} · {esc(s.get("phase") or "")} · {esc(s.get("type") or "")}.</p>')
    change = st.get("pupils_change")
    body += tiles([
        ("Reserve at year end", f'{money(st["reserve"])}<span class="sub">{pct(st["reserve_share"])} of a year\'s income</span>'),
        ("Last year's balance", f'{money(latest.get("in_year_balance"), signed=True)}<span class="sub">income minus spending</span>'),
        ("Income per pupil", f'£{per_pupil(latest, "total_income"):,.0f}' if per_pupil(latest, "total_income") else "—"),
        ("Pupils", f'{latest.get("pupils") or 0:,.0f}' + (f'<span class="sub">{change:+.0%} since {esc(points[0]["year"])}</span>' if change is not None else "")),
    ])
    if item["academy"]:
        trust = item["trust"]
        trust_html = f'<a href="{esc(item["trust_path"])}">{esc(trust)}</a>' if trust and item.get("trust_path") else "its academy trust"
        body += (f'<p class="note">Academies in a trust don\'t hold money on their own: {trust_html} can move money between its schools. '
                 + ("The reserve includes this school's per-pupil share of the trust's central reserve." if st["trust_share_included"] else
                    "The DfE doesn't publish this school's share of the trust's central reserve for this year, so the reserve shown is the school's own.")
                 + "</p>")
    if any(r.get("via_urn") for r in years):
        body += '<p class="note">Earlier years come from this school\'s return before it became an academy (a different DfE number).</p>'
    body += f'<h2>Reserve at the end of each year, {esc(span)}</h2>' + charts.reserve_bars(points)
    body += f'<h2>Income and spending, {esc(span)}</h2>' + charts.income_spend_lines(points)
    body += details_table("Show the figures as a table", ["Year", "Income", "Spending", "Balance", "Reserve", "Pupils"],
                          [[esc(p["year"]), money(p["income"]), money(p["spend"]), money(p["balance"], signed=True), money(p["reserve"]),
                            f'{p["pupils"]:,.0f}' if p["pupils"] else "—"] for p in points])
    cmp = compare_rows(item)
    if cmp:
        rank = reserve_rank(item)
        body += '<h2>Compared with similar schools</h2>'
        body += (f'<p>Similar schools are the {len(item["similar"])} {esc(item["phase"].replace("_", "-"))} schools '
                 f'{"in London" if item["london"] else "outside London"} closest in size and in the share of pupils on free school meals. ')
        if rank is not None:
            body += f'Its reserve, as a share of income, is higher than {rank:.0%} of them. '
        total, others = per_pupil(latest, "total_expenditure"), [per_pupil(o["latest"], "total_expenditure") for o in item["similar"]]
        others = [v for v in others if v]
        if total and len(others) >= 10:
            body += f'It spends £{total:,.0f} a pupil in total; similar schools typically spend £{statistics.median(others):,.0f}.'
        body += "</p>" + charts.compare_dots(cmp)
        body += details_table("Show the comparison as a table", ["Spending per pupil", "This school", "Similar schools (median)", "Middle half"],
                              [[esc(r["label"]), f'£{r["value"]:,.0f}', f'£{r["median"]:,.0f}', f'£{r["p25"]:,.0f}–£{r["p75"]:,.0f}'] for r in cmp])
        near = ",".join([item["urn"]] + [o["urn"] for o in item["similar"][:3]])
        body += (f'<p><a class="button" href="/money/compare/?urns={esc(near)}">Compare side by side with the 3 most similar schools</a></p>'
                 '<details class="tableview"><summary>Which schools are these?</summary><ul class="nearby">'
                 + "".join(f'<li>{school_link(o)} {status_cell(o)}</li>' for o in item["similar"][:12]) + "</ul></details>")
    income = [(label, latest.get(key)) for key, label in INCOME_KEYS if latest.get(key)]
    if income:
        body += f'<h2>Where the money comes from, {esc(year_label(latest))}</h2>' + table(
            ["Source", "Amount", "Per pupil"],
            [[esc(label), money(v), f'£{v / latest["pupils"]:,.0f}' if latest.get("pupils") else "—"] for label, v in income])
    if item["pta"]:
        body += "<h2>Money raised by parents</h2>"
        for c in item["pta"][:2]:
            hist = [h for h in c.get("history", []) if h.get("income") is not None][-5:]
            body += (f'<p><a href="{CHARITY}{esc(c["charity_number"])}">{esc(c["name"])}</a> (charity {esc(c["charity_number"])}, {esc(c.get("status") or "")}) '
                     + (f'raised {money(c.get("latest_income"))} in its latest year.' if c.get("latest_income") is not None else "")
                     + "</p>")
            if hist:
                body += table(["Year ending", "Income", "Spending"], [[esc(h["period_end"]), money(h["income"]), money(h.get("expenditure"))] for h in hist])
        body += '<p class="muted small">Matched to this school by name and postcode from the Charity Commission register. Parent associations\' money isn\'t in the school\'s accounts above.</p>'
    qs = questions(item, cmp)
    if qs:
        body += "<h2>Questions to ask the school</h2><p>Useful for parents, governors and PTA committees.</p><ul>" + "".join(f"<li>{esc(q)}</li>" for q in qs) + "</ul>"
    body += (f'<h2>Check these figures</h2><p>Every figure here comes from the school\'s published return to the DfE. Check it on the {check}, '
             f'and see <a href="/money/about/">how the status is worked out</a>.</p>'
             f'<p><a href="{esc(item["site_path"])}">Admissions, Ofsted and results for {esc(item["name"])}</a> · '
             f'<a href="{esc(council["path"])}">All {esc(council["name"])} school finances</a></p>')
    pta_source = '<li><a href="https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download">Charity Commission register</a> — Open Government Licence v3.0</li>' if item["pta"] else ""
    body += sources(pta_source)
    title = shorten(f"{item['name']} finances: {st['label']} | Schools in Reach", 70)
    description = shorten(f"{item['name']}: {st['reason']} Income, spending and reserves {span}, compared with similar schools.", 160)
    return page(title, description, item["path"], body, crumbs, metadata)


def council_rows(items):
    rows = []
    for i in sorted(items, key=lambda i: (i["status"]["rank"], i["status"]["reserve"])):
        st = i["status"]
        rows.append([school_link(i), status_cell(i), f'<span data-sort="{st["reserve"]:.0f}">{money(st["reserve"])}</span>',
                     f'<span data-sort="{(st["reserve_share"] or 0):.4f}">{pct(st["reserve_share"])}</span>',
                     f'<span data-sort="{st["deficit_streak"]}">{st["deficit_streak"] or "—"}</span>',
                     f'<span data-sort="{(st["pupils_change"] or 0):.3f}">{"—" if st["pupils_change"] is None else f"{st["pupils_change"]:+.0%}"}</span>'])
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


def render_council(council, metadata):
    items = [i for i in council["schools"] if i["status"]]
    counts = Counter(i["status"]["status"] for i in items)
    deficit = [i for i in items if i["status"]["status"] == "in_deficit"]
    owed = -sum(i["status"]["reserve"] for i in deficit)
    held = sum(i["status"]["reserve"] for i in items if i["status"]["reserve"] > 0)
    name = council["name"]
    crumbs = [("Home", "/"), ("School money", "/money/"), (name, council["path"])]
    body = f'<h1>{esc(name)} school finances</h1>'
    if items:
        body += (f'<p class="lead"><strong>{len(deficit):,} of {len(items):,}</strong> schools in {esc(name)} were in deficit in their latest return, '
                 f'with combined deficits of <strong>{money(owed)}</strong>. {counts["heading_for_deficit"]:,} more are heading that way.</p>')
    else:
        body += f'<p class="lead">No school in {esc(name)} has a full-year finance return in the latest data, so there are no statuses to show yet.</p>'
    body += charts.status_bar(counts)
    body += tiles([("Schools in deficit", f"{len(deficit):,}"), ("Combined deficits", money(owed)),
                   ("Heading for deficit", f'{counts["heading_for_deficit"]:,}'), ("Reserves held by the rest", money(held))])
    series = yearly_deficit_series([i["rows"] for i in council["schools"]])
    if len(series) > 1:
        body += f'<h2>Share of {esc(name)}\'s council-run schools in deficit, by year</h2>' + charts.count_bars(series)
        body += '<p class="muted small">Council-run schools only, so years compare like with like; academies report differently and are in the table below.</p>'
    back = [i for i in items if recovered(i)]
    if back:
        body += "<h2>Back in the black</h2><p>Schools that were in deficit in an earlier year and are now healthy:</p><ul class=\"nearby\">" + "".join(
            f"<li>{school_link(i)}</li>" for i in sorted(back, key=lambda i: i["name"])) + "</ul>"
    if items:
        body += f'<h2>Every school, worst first</h2><p class="muted small">Tap a column heading to sort.</p>' + sortable(COUNCIL_HEADERS, council_rows(items))
    members = [i for i in council["schools"] if not i["status"]]
    if members:
        body += '<p class="muted small">Not shown: ' + ", ".join(school_link(i) for i in members[:40]) + (" and others" if len(members) > 40 else "") + ' (in a federation\'s combined return, or no full-year return yet).</p>'
    body += (f'<p>Check at source: <a href="{FBIT}/local-authority/{esc(council["code"])}">DfE benchmarking page for {esc(name)}</a> · '
             f'<a href="{esc(council["site_path"])}">{esc(name)} admissions and catchments</a></p>' + sources())
    title = shorten(f"{name} school finances: {len(deficit)} schools in deficit | Schools in Reach", 70)
    description = shorten(f"{len(deficit)} of {len(items)} schools in {name} are in deficit ({money(owed)} combined). See every school's reserves, spending and trend from DfE returns.", 160)
    return page(title, description, council["path"], body, crumbs, metadata)


def ranked(items, headers, cells):
    return table(["#"] + headers, [[str(n)] + cells(i) for n, i in enumerate(items, 1)])


def render_national(councils, schools, metadata):
    items = [i for i in schools if i["status"]]
    counts = Counter(i["status"]["status"] for i in items)
    deficit = sorted((i for i in items if i["status"]["status"] == "in_deficit"), key=lambda i: i["status"]["reserve"])
    heading = sorted((i for i in items if i["status"]["status"] == "heading_for_deficit"), key=lambda i: i["status"]["runway_years"] or 99)
    large = sorted((i for i in items if i["status"]["status"] == "large_reserves"), key=lambda i: -(i["status"]["reserve_share"] or 0))
    back = sorted((i for i in items if recovered(i)), key=lambda i: -(i["status"]["reserve_share"] or 0))
    owed = -sum(i["status"]["reserve"] for i in deficit)
    body = '<h1>School money: which schools are in deficit, and which are doing well</h1>'
    if items:
        body += (f'<p class="lead">Of {len(items):,} state schools in England with a full-year return, <strong>{len(deficit):,} were in deficit</strong> '
                 f'({len(deficit) / len(items):.0%}), owing a combined <strong>{money(owed)}</strong>. Another {counts["heading_for_deficit"]:,} are '
                 'heading that way: they have spent more than they received for two years or more and their reserves are running out.</p>')
    else:
        body += '<p class="lead">No school has a full-year finance return in the latest data yet, so there are no statuses to show.</p>'
    body += ('<form class="finder" action="/money/compare/" role="search"><label for="find">Find a school</label>'
             '<input id="find" name="q" type="search" placeholder="School name or town" autocomplete="off"><button type="submit">Find</button></form>')
    body += charts.status_bar(counts)
    body += '<p class="muted small">Latest returns: council-run schools 2025-26 (April–March), academies 2024/25 (September–August). <a href="/money/about/">How each status is worked out</a>.</p>'
    series = yearly_deficit_series([i["rows"] for i in schools])
    if len(series) > 1:
        body += "<h2>Share of council-run schools in deficit, by year</h2>" + charts.count_bars(series)
    body += "<h2>Biggest deficits</h2>" + ranked(deficit[:TOP_N], ["School", "Council", "Deficit", "% of income"], lambda i: [
        school_link(i), f'<a href="{esc(i["council"]["path"])}">{esc(i["council"]["name"])}</a>', money(-i["status"]["reserve"]), pct(-(i["status"]["reserve_share"] or 0))])
    body += "<h2>Heading for deficit soonest</h2><p>Spending more than they receive, with reserves that would run out within about three years at the current rate.</p>" + ranked(
        heading[:TOP_N], ["School", "Council", "Reserve", "Runs out in about"], lambda i: [
            school_link(i), f'<a href="{esc(i["council"]["path"])}">{esc(i["council"]["name"])}</a>', money(i["status"]["reserve"]),
            f'{max(i["status"]["runway_years"], 0.5):.0f} year(s)'])
    if back:
        body += "<h2>Back in the black</h2><p>Schools that were in deficit earlier in the period and now have healthy reserves.</p>" + ranked(
            back[:TOP_N], ["School", "Council", "Reserve now", "% of income"], lambda i: [
                school_link(i), f'<a href="{esc(i["council"]["path"])}">{esc(i["council"]["name"])}</a>', money(i["status"]["reserve"]), pct(i["status"]["reserve_share"])])
    body += "<h2>Largest reserves for their size</h2><p>A big reserve is a cushion, but it is also money not yet spent on current pupils.</p>" + ranked(
        large[:TOP_N], ["School", "Council", "Reserve", "% of income"], lambda i: [
            school_link(i), f'<a href="{esc(i["council"]["path"])}">{esc(i["council"]["name"])}</a>', money(i["status"]["reserve"]), pct(i["status"]["reserve_share"])])
    rows = []
    for c in councils:
        cs = [i for i in c["schools"] if i["status"]]
        if not cs:
            continue
        d = [i for i in cs if i["status"]["status"] == "in_deficit"]
        h = sum(i["status"]["status"] == "heading_for_deficit" for i in cs)
        total = -sum(i["status"]["reserve"] for i in d)
        rows.append([f'<a href="{esc(c["path"])}">{esc(c["name"])}</a>', f'<span data-sort="{len(cs)}">{len(cs):,}</span>',
                     f'<span data-sort="{len(d)}">{len(d):,}</span>', f'<span data-sort="{len(d) / len(cs):.4f}">{len(d) / len(cs):.0%}</span>',
                     f'<span data-sort="{h}">{h:,}</span>', f'<span data-sort="{total:.0f}">{money(total)}</span>'])
    body += ('<h2>Every council</h2><p class="muted small">Tap a column heading to sort.</p>'
             + sortable(["Council", "Schools", "In deficit", "% in deficit", "Heading for deficit", "Combined deficits"], rows))
    body += '<p><a href="/money/trust/">Academy trusts</a> · <a href="/money/compare/">Compare schools side by side</a> · <a href="/money/about/">How it works</a></p>'
    body += sources()
    crumbs = [("Home", "/"), ("School money", "/money/")]
    description = shorten(f"{len(deficit):,} English state schools are in deficit. See which, by council and school: reserves, spending and 8-year trends from DfE returns.", 160)
    return page("School finances in England: which schools are in deficit | Schools in Reach", description, "/money/", body, crumbs, metadata)


def trusts_of(schools):
    trusts = defaultdict(list)
    for i in schools:
        if i["academy"] and i["trust"] and i["status"]:
            trusts[i["trust"]].append(i)
    return trusts


def render_trust(name, items, metadata):
    path = items[0]["trust_path"]
    counts = Counter(i["status"]["status"] for i in items)
    total = sum(i["status"]["reserve"] for i in items)
    shared = all(i["status"]["trust_share_included"] for i in items)
    crumbs = [("Home", "/"), ("School money", "/money/"), ("Academy trusts", "/money/trust/"), (name, path)]
    body = f'<h1>{esc(name)}: academy finances</h1>'
    body += (f'<p class="lead">{len(items):,} academies with a full-year return. Their reserves add up to <strong>{money(total)}</strong>'
             + (", including each school's share of the trust's central reserve." if shared else ".") + "</p>")
    body += charts.status_bar(counts)
    body += ('<p class="note">A trust can move money between its academies, so a school shown in deficit may be supported by the trust '
             'as a whole. The trust-wide figure is the better guide to whether the trust is in difficulty.</p>')
    body += "<h2>Academies, worst first</h2>" + sortable(COUNCIL_HEADERS, council_rows(items)) + sources()
    description = shorten(f"{name}: reserves and financial status of its {len(items)} academies from DfE accounts returns.", 160)
    return path, page(shorten(f"{name} academy finances | Schools in Reach", 70), description, path, body, crumbs, metadata)


def render_trust_index(trusts, metadata):
    rows = []
    for name, items in sorted(trusts.items(), key=lambda kv: kv[0].casefold()):
        d = sum(i["status"]["status"] == "in_deficit" for i in items)
        total = sum(i["status"]["reserve"] for i in items)
        rows.append([f'<a href="{esc(items[0]["trust_path"])}">{esc(name)}</a>', f'<span data-sort="{len(items)}">{len(items):,}</span>',
                     f'<span data-sort="{d}">{d:,}</span>', f'<span data-sort="{total:.0f}">{money(total)}</span>'])
    body = ('<h1>Academy trust finances</h1><p class="lead">Every academy trust in England with its academies\' reserves and how many are in deficit.</p>'
            + sortable(["Trust", "Academies", "In deficit", "Combined reserves"], rows) + sources())
    crumbs = [("Home", "/"), ("School money", "/money/"), ("Academy trusts", "/money/trust/")]
    return page("Academy trust finances in England | Schools in Reach", "Academy trusts in England: combined reserves and how many of their academies are in deficit, from DfE accounts returns.",
                "/money/trust/", body, crumbs, metadata)


def render_compare(metadata):
    body = ('<h1>Compare school finances side by side</h1><p class="lead">Pick up to four schools to compare their reserves, spending per pupil and trends.</p>'
            '<div id="compare-app"><form class="finder" role="search" onsubmit="return false"><label for="cmp-find">Add a school</label>'
            '<input id="cmp-find" type="search" placeholder="School name or town" autocomplete="off" aria-controls="cmp-results">'
            '</form><ul id="cmp-results" class="results" role="listbox" aria-label="Matching schools"></ul>'
            '<ul id="cmp-chosen" class="chosen" aria-live="polite"></ul><div id="cmp-out"><p class="muted">Search above, or open any school\'s money page and use “Compare side by side”.</p></div></div>'
            '<noscript><p>The comparison needs JavaScript. Each school\'s own money page works without it.</p></noscript>' + sources())
    crumbs = [("Home", "/"), ("School money", "/money/"), ("Compare", "/money/compare/")]
    return page("Compare school finances | Schools in Reach", "Compare up to four English schools' reserves, spending per pupil and finance trends side by side.",
                "/money/compare/", body, crumbs, metadata)


def render_about(metadata):
    labels = [
        ("in_deficit", "The school's revenue reserve was below zero at the end of its latest full year: over the years it has spent more than it received."),
        ("heading_for_deficit", "Still above zero, but the school has spent more than it received for at least two years running and, at its average overspend over the last three years, its reserve would run out within about three years."),
        ("tight", "A reserve under 3% of a year's income: little room for an unexpected cost."),
        ("healthy", "A reserve between 3% of income and the large-reserve level."),
        ("large_reserves", "A reserve of 8% of a year's income or more (5% for secondary schools), the levels the DfE once called excessive and many councils still use to claw back surpluses."),
    ]
    body = '<h1>How the school money figures work</h1>'
    body += "<h2>The five statuses</h2><ul class=\"defs\">" + "".join(f"<li>{badge(k)} {esc(v)}</li>" for k, v in labels) + "</ul>"
    body += """<h2>What a deficit means</h2>
<p>A school deficit isn't a bank loan. It means the school has spent more over the years than it received, so its revenue reserve, the money it carries from year to year, is below zero.</p>
<p>For a <strong>council-run school</strong>, the council covers the gap from its schools budget. It usually agrees a recovery plan, often called a licensed deficit, with a date by which the school must be back in balance, and can step in if the plan isn't kept.</p>
<p>An <strong>academy</strong> is part of a trust. A trust can move money between its schools, so one academy in deficit may be propped up by the others. Where the DfE publishes it, an academy's reserve here includes its per-pupil share of the trust's central reserve, and each trust has its own page.</p>
<h2>Where the numbers come from</h2>
<p>Every school in England reports its income, spending and balances to the Department for Education each year. Council-run schools use the Consistent Financial Reporting (CFR) return for April to March; academies use the Academy Accounts Return for September to August. The DfE publishes both in its Financial Benchmarking and Insights Tool, and every school page here links to the matching DfE page so you can check the figures.</p>
<p>Figures are shown as published. Part-year returns (a school that opened, converted or changed trust during the year) are left out of statuses and trends. When a school became an academy, its earlier years come from its council-run return under its old DfE number, linked through Get Information about Schools.</p>
<h2>Similar schools</h2>
<p>For each school we take the 30 schools of the same phase, in London or outside it to match, that are closest in pupil numbers and in the share of pupils on free school meals. Spending per pupil is compared with the middle half of that group.</p>
<h2>Parents' associations</h2>
<p>Where a PTA or friends' charity can be matched to a school by name and postcode in the Charity Commission register, its income is shown. That money is separate from the school's own accounts. A missing PTA usually means it is too small to register or couldn't be matched with confidence.</p>
<h2>Corrections</h2>
<p>If a figure looks wrong, compare it with the DfE page linked from the school. If the DfE's figure differs from ours, it's our mistake: <a href="/about.html">tell us</a>.</p>"""
    body += sources('<li><a href="https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download">Charity Commission register</a> — Open Government Licence v3.0</li>')
    crumbs = [("Home", "/"), ("School money", "/money/"), ("How it works", "/money/about/")]
    return page("How school finance statuses are worked out | Schools in Reach",
                "What a school deficit means, where the figures come from and how each school's financial status is worked out.",
                "/money/about/", body, crumbs, metadata)


def school_json(item):
    st = item["status"]
    years = [[year_label(r), r.get("total_income"), r.get("total_expenditure"), reserve_of(r), r.get("pupils")] for r in item["years"]]
    pp = {k: per_pupil(item["latest"], k) for k, _ in COMPARE_KEYS + [("total_expenditure", ""), ("total_income", "")]}
    sim = {}
    for k, _ in COMPARE_KEYS + [("total_expenditure", "")]:
        vals = [v for v in (per_pupil(o["latest"], k) for o in item["similar"]) if v is not None]
        if len(vals) >= 10:
            sim[k] = statistics.median(vals)
    return {"urn": item["urn"], "name": item["name"], "council": item["council"]["name"], "path": item["path"],
            "status": st["status"], "label": st["label"], "reason": st["reason"], "reserve": st["reserve"], "share": st["reserve_share"],
            "balance": item["latest"].get("in_year_balance"), "streak": st["deficit_streak"], "pupils_change": st["pupils_change"],
            "year": year_label(item["latest"]), "academy": item["academy"], "years": years,
            "pp": {k: round(v) for k, v in pp.items() if v is not None}, "similar": {k: round(v) for k, v in sim.items()},
            "check": f"{FBIT}/school/{item['urn']}"}


# ----------------------------------------------------------------- build

def build(site, history_path, links_path, pta_path):
    started = time.perf_counter()
    site = Path(site).resolve()
    metadata = HeadMetadata((site / "index.html").read_text(encoding="utf-8"))
    councils, schools, _ = build_model(site, history_path, links_path, pta_path)
    today = date.today().isoformat()
    urls = []
    with tempfile.TemporaryDirectory(prefix=".money-build-", dir=site) as staging:
        out = Path(staging) / "money"
        out.mkdir()

        def write(path, html):
            target = out / path.removeprefix("/money/") / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")

        write("/money/", render_national(councils, schools, metadata))
        urls.append(("/money/", today))
        for c in councils:
            if c["schools"]:
                write(c["path"], render_council(c, metadata))
            if any(i["status"] for i in c["schools"]):
                urls.append((c["path"], today))
        for item in schools:
            html = render_school(item, metadata)
            if len(html.encode("utf-8")) > 40_000:
                raise ValueError(f"Money page too large: {item['path']}")
            write(item["path"], html)
            if item["status"]:
                urls.append((item["path"], today))
        trusts = trusts_of(schools)
        write("/money/trust/", render_trust_index(trusts, metadata))
        urls.append(("/money/trust/", today))
        for name, items in trusts.items():
            path, html = render_trust(name, items, metadata)
            write(path, html)
            urls.append((path, today))
        write("/money/compare/", render_compare(metadata))
        write("/money/about/", render_about(metadata))
        urls += [("/money/compare/", today), ("/money/about/", today)]
        data = out / "data"
        (data / "s").mkdir(parents=True)
        index = []
        statuses = {}
        for item in schools:
            if not item["status"]:
                continue
            (data / "s" / f"{item['urn']}.json").write_text(json.dumps(school_json(item), separators=(",", ":")), encoding="utf-8")
            index.append([item["urn"], item["name"], item["school"].get("town") or "", item["council"]["name"], item["status"]["status"]])
            statuses[item["urn"]] = {"status": item["status"]["status"], "label": item["status"]["label"], "path": item["path"]}
        (data / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
        (data / "status.json").write_text(json.dumps(statuses, separators=(",", ":")), encoding="utf-8")
        for asset in ("money.css", "money.js"):
            shutil.copyfile(Path(__file__).with_name(asset), out / asset)
        write_sitemap(out / "sitemap.xml", urls)
        target = site / "money"
        if target.is_symlink():
            raise ValueError("Refusing to replace symlink: money")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(out), target)
    counts = Counter(i["status"]["status"] for i in schools if i["status"])
    return {"schools": len(schools), "with_status": sum(counts.values()), "councils": len(councils), "trusts": len(trusts),
            "statuses": dict(counts), "pages": len(urls), "runtime": time.perf_counter() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=ROOT / "site")
    parser.add_argument("--history", type=Path, default=ROOT / "pipeline/.cache/dfe/finance_history.jsonl")
    parser.add_argument("--links", type=Path, default=ROOT / "pipeline/.cache/dfe/gias/links.csv")
    parser.add_argument("--pta", type=Path, default=ROOT / "pipeline/.cache/money/pta.json")
    args = parser.parse_args()
    try:
        summary = build(args.site_dir, args.history, args.links, args.pta)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Money build failed: {exc}\n")
    print(f"Money pages: {summary['pages']:,} indexable; {summary['schools']:,} schools ({summary['with_status']:,} with a status), "
          f"{summary['councils']} councils, {summary['trusts']:,} trusts; {summary['runtime']:.1f}s")
    print("Statuses:", ", ".join(f"{STATUS_LABELS[k]} {summary['statuses'].get(k, 0):,}" for k in STATUS_ORDER))


if __name__ == "__main__":
    main()
