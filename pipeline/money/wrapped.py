"""School Wrapped and PTFA Wrapped (unit C3): a shareable, tap-through story of one school's year in money
that ends as a vertical video, made in the browser by assets/wrapped.js.

Writes, through write_pages(env):
  /wrapped/                         the story shell (env['page'], noindex); ?urn=<urn>[&mode=ptfa] picks the school
  /data/wrapped/context.json        the IFS lines the cards quote (each with its page numbers), real_label, base_url
  <school path>wrapped/             a hand-built stub (at most 3,072 bytes, noindex) for every school with a status

Reads: pipeline/money/data/ifs_context.json, deflator.real_label(), and each school item through school_view().
The browser then reads /data/s/<urn>.json, /data/sx/<urn>.json, /data/a/council-<code>.json and /data/a/england.json.
Nothing here builds a figure the story shows except headline(), which the stub's description and share card use.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pipeline.money import deflator, site, status as health

HERE = Path(__file__).resolve().parent
REAL_ROOT = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
IFS_FILE = "pipeline/money/data/ifs_context.json"
STUB_LIMIT = 3072
SHELL_PATH = "/wrapped/"
CONTEXT_PATH = "/data/wrapped/context.json"
REGISTER_NOTE = ("Charities with an income of £5,000 or less don't have to register with the Charity Commission, "
                 "so a small parents' association may still exist.")
OVERLAP_NOTE = ("Money a parents' association gives the school can also appear in the school's own donations income, "
                "so the two are never added together.")
NOT_FOUND = "No registered parents' association found"

# For each status: the IFS framing that explains it and the question set that helps (both keys of ifs_context.json),
# plus one plain 'what helps' sentence. The sentences are this site's wording, drawn from the framing they sit beside.
WHAT_HELPS = {
    "in_deficit": ("why_schools_go_into_deficit", "in_deficit",
                   "What helps: a recovery plan agreed with the council or trust, and knowing what drives the gap."),
    "heading_for_deficit": ("one_deficit_year", "heading_for_deficit",
                            "What helps: looking at the pattern early, while there is still a reserve to plan with."),
    "tight": ("why_schools_go_into_deficit", "tight",
              "What helps: a small cushion for surprises, and knowing which costs are expected to rise next year."),
    "healthy": ("funding_vs_spending_per_pupil", "any",
                "What helps: keeping an eye on the trend, and comparing spending per pupil with similar schools."),
    "large_reserves": ("one_deficit_year", "large_reserves",
                       "What helps: a clear purpose and timetable for the reserve, so current pupils benefit too."),
}


def _repo_file(rel: str) -> Path:
    """A committed repo file, resolved next to this module first and then in the real checkout."""
    local = HERE.parents[1] / rel
    return local if local.exists() else REAL_ROOT / rel


def _load_ifs() -> dict:
    try:
        with open(_repo_file(IFS_FILE), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _status_of(raw) -> dict | None:
    """A status.assess() dict, a bare status key or None, as {key, label, reason, reserve, year, source} or None."""
    if isinstance(raw, dict):
        key = raw.get("status")
        if key not in health.LABELS:
            return None
        return {"key": key, "label": raw.get("label") or health.LABELS[key], "reason": raw.get("reason"),
                "reserve": raw.get("reserve"), "year": raw.get("year"), "source": raw.get("source")}
    if isinstance(raw, str) and raw in health.LABELS:
        return {"key": raw, "label": health.LABELS[raw], "reason": None, "reserve": None, "year": None, "source": None}
    return None


def school_view(item: dict) -> dict:
    """The one place this module reads a school item (build_money.build_model's shape, which Wave B is reshaping)."""
    urn = str(item["urn"])
    name = item["name"]
    council = item.get("council") or {}
    school = item.get("school") or {}
    rows = item.get("rows") or []
    years = health.full_years(rows)
    latest = years[-1] if years else {}
    tags = item.get("tags") or {}
    pupils = item.get("pupils")
    if pupils is None:
        pupils = latest.get("pupils")
    return {
        "urn": urn,
        "name": name,
        "path": item.get("path") or site.page_path("school", urn, name),
        "la": item.get("la") or council.get("code"),
        "la_name": item.get("la_name") or council.get("name"),
        "phase": item.get("phase"),
        "status": _status_of(item.get("status")),
        "governance": tags.get("governance") or ("academy" if item.get("academy") else "council-run"),
        "pupils": pupils,
        "lat": item.get("lat") if item.get("lat") is not None else school.get("lat"),
        "lon": item.get("lon") if item.get("lon") is not None else school.get("lon"),
        "rows": rows,
        "latest": latest,
        "pta": [c for c in (item.get("pta") or []) if not c.get("review")],
    }


def _half_up(value: float) -> int:
    """Round halves up, as the browser's Math.round does, so Python and JS print the same figure."""
    return math.floor(value + 0.5)


def fmt_pupils(value) -> str:
    """Pupils to 1 dp, without a trailing .0: 432.5, 435, 1,204.5."""
    text = f"{_half_up(float(value) * 10) / 10:,.1f}"
    return text[:-2] if text.endswith(".0") else text


def _exact(value) -> str:
    rounded = _half_up(value)
    return f"{'-' if rounded < 0 else ''}£{abs(rounded):,}"


def headline(item: dict) -> str:
    """One supportive line with a year and source: pupils and government funding per pupil, else pupils, else the name."""
    return _headline(school_view(item))


def _headline(view: dict) -> str:
    name, latest, pupils = view["name"], view["latest"], view["pupils"]
    year = latest.get("year") or (view["status"] or {}).get("year")
    when = f" in {year}" if year else ""
    grant = latest.get("grant_funding")
    if pupils and grant and latest.get("pupils"):
        per_pupil = grant / latest["pupils"]
        return f"{name}: {fmt_pupils(latest['pupils'])} pupils and {_exact(per_pupil)} government funding per pupil{when} (DfE)"
    if pupils:
        return f"{name}: {fmt_pupils(pupils)} pupils{when} (DfE)"
    return f"{name}: its year in money, from published figures"


def stub_path(item: dict) -> str:
    """Where a school's Wrapped stub lives: its school page path + 'wrapped/'."""
    return school_view(item)["path"] + "wrapped/"


def wrapped_links(item: dict) -> str:
    """An escaped snippet linking both Wrapped modes, for Wave B to place on the school page."""
    view = school_view(item)
    href = view["path"] + "wrapped/"
    return (f'<p class="wrapped-links"><a href="{site.esc(href)}">School Wrapped: {site.esc(view["name"])}\'s year in money</a>'
            f' · <a href="{site.esc(href)}?mode=ptfa">PTFA Wrapped</a></p>')


def stub_html(item: dict, og_image: str | None = None) -> str:
    """The minimal, shareable document at <school path>wrapped/. It is under STUB_LIMIT bytes for any real name."""
    return _stub_html(school_view(item), og_image)


def _stub_html(view: dict, og_image: str | None) -> str:
    html = _stub(view, _headline(view), og_image)
    if len(html.encode("utf-8")) > STUB_LIMIT:  # only for absurd names: shorten the name, keep the page whole
        short = dict(view, name=view["name"][:60].rstrip() + "…")
        html = _stub(short, f"{short['name']}: its year in money, from published figures", og_image)
    return html


def _stub(view: dict, line: str, og_image: str | None) -> str:
    e = site.esc
    name, path = view["name"], view["path"]
    title = f"{name}: School Wrapped"
    url = site.BASE_MONEY + path + "wrapped/"
    head = [
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{e(title)}</title>",
        f'<meta name="description" content="{e(line)}">',
        f'<link rel="canonical" href="{e(site.BASE_MONEY + path)}">',
        '<meta name="robots" content="noindex,follow">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(line)}">',
        f'<meta property="og:url" content="{e(url)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{e(site.SITE_NAME)}">',
        '<meta name="twitter:card" content="summary">',
    ]
    if og_image:
        head.append(f'<meta property="og:image" content="{e(og_image)}">')
    head.append('<link rel="stylesheet" href="/assets/app.css"><link rel="stylesheet" href="/assets/wrapped.css">'
                '<script src="/assets/wrapped.js" defer></script>')
    body = (f'<main id="wrapped-app" class="wrapped" data-urn="{e(view["urn"])}" data-mode="school" '
            f'data-name="{e(name)}" data-path="{e(path)}">'
            f'<noscript><p class="wr-noscript">This story needs JavaScript. Every figure is on '
            f'<a href="{e(path)}">the school\'s own page</a>.</p></noscript></main>')
    return f'<!doctype html>\n<html lang="en-GB"><head>{"".join(head)}</head><body>{body}</body></html>\n'


def _framing(ifs: dict, key: str) -> dict:
    f = (ifs.get("framings") or {}).get(key) or {}
    return {"key": key, "title": f.get("title"), "text": f.get("text"), "pages": f.get("pages") or []}


def _questions(ifs: dict, key: str) -> list[dict]:
    block = (ifs.get("questions") or {}).get(key) or {}
    return [{"text": q.get("text"), "why": q.get("why"), "page": q.get("page")} for q in block.get("questions") or []]


def _line(ifs: dict, block: str, ident: str) -> dict | None:
    for line in (ifs.get("context_lines") or {}).get(block) or []:
        if line.get("id") == ident:
            return {"id": ident, "text": line.get("text"), "page": line.get("page")}
    return None


def _dsg_note() -> str | None:
    """la_dsg.json's note on the statutory override, which the council card sits beside."""
    try:
        with open(_repo_file("pipeline/money/data/la_dsg.json"), encoding="utf-8") as fh:
            notes = (json.load(fh).get("source") or {}).get("notes") or []
    except (OSError, ValueError):
        return None
    return next((n for n in notes if "statutory override" in n.lower()), None)


def context_doc(today: str | None = None) -> dict:
    """What /data/wrapped/context.json holds: every IFS line a card quotes, with its pages, and the site constants."""
    ifs = _load_ifs()
    src = ifs.get("source") or {}
    framings = {k: _framing(ifs, k) for k in (ifs.get("framings") or {})}
    lines = ifs.get("context_lines") or {}
    return {
        "generated": today,
        "base_url": site.BASE_MONEY,
        "real_label": deflator.real_label(),
        "ifs": {"cite": src.get("short_cite") or site.IFS_CITE, "url": src.get("url") or site.IFS_URL,
                "page_note": "Page numbers are the printed pages of the IFS report."},
        "staff": {"line": _line(ifs, "school", "staff_share"), "framing": framings.get("why_schools_go_into_deficit")},
        "framings": framings,
        "what_helps": {key: {"status": key, "label": health.LABELS[key], "text": text,
                             "framing": framings.get(fkey), "questions": _questions(ifs, qkey)}
                       for key, (fkey, qkey, text) in WHAT_HELPS.items()},
        "any_questions": _questions(ifs, "any"),
        "school_lines": [{"id": x.get("id"), "use_when": x.get("use_when"), "text": x.get("text"), "page": x.get("page")}
                         for x in lines.get("school") or []],
        "council_lines": [{"id": x.get("id"), "use_when": x.get("use_when"), "text": x.get("text"), "page": x.get("page")}
                          for x in lines.get("council") or []],
        "national_lines": [{"id": x.get("id"), "text": x.get("text"), "page": x.get("page")} for x in lines.get("national") or []],
        "dsg_note": _dsg_note(),
        "pta": {"not_found": NOT_FOUND, "register_note": REGISTER_NOTE, "overlap_note": OVERLAP_NOTE,
                "source": "Charity Commission register",
                "register_url": "https://www.gov.uk/setting-up-charity/register-your-charity",
                "charity_url": "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/"},
        "fbit_url": "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/",
    }


def _shell_body(real_label: str) -> str:
    e = site.esc
    return (
        '<section class="wrapped-intro"><h1>School Wrapped</h1>'
        '<p class="lead">A short story of one school\'s year in money, from published figures, that you can turn into a video and share.</p>'
        '</section>'
        f'<div id="wrapped-app" class="wrapped" data-urn="" data-mode="school" data-real-label="{e(real_label)}" '
        f'data-context="{CONTEXT_PATH}">'
        '<p class="wr-pick">Pick a school to see its year in money: <a href="/search/">search for a school</a>, '
        'then choose School Wrapped on its page.</p>'
        '<noscript><p class="wr-noscript">The story needs JavaScript. Every figure is also on each '
        '<a href="/search/">school\'s own page</a>.</p></noscript></div>'
    )


def _write_context(out: Path, today: str | None) -> None:
    folder = Path(out) / "data" / "wrapped"
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(context_doc(today), separators=(",", ":"), ensure_ascii=False)
    (folder / "context.json").write_text(text, encoding="utf-8")


def write_pages(env: dict, **_overrides) -> list[tuple[str, bool]]:
    """Write the /wrapped/ shell, context.json and every school's stub; return [(path, indexable), ...] in write order."""
    write, page = env["write"], env["page"]
    crumbs = [("Home", "/"), ("School Wrapped", SHELL_PATH)]
    html = page("School Wrapped: a school's year in money",
                "A short, shareable story of one school's year in money, made from published DfE and Charity Commission figures.",
                SHELL_PATH, _shell_body(deflator.real_label()), crumbs, indexable=False,
                extra_head='<link rel="stylesheet" href="/assets/wrapped.css"><script src="/assets/wrapped.js" defer></script>')
    write(SHELL_PATH, html)
    written = [(SHELL_PATH, False)]
    _write_context(env["out"], env.get("today"))
    og_image = env.get("og_image")
    for item in env.get("items") or []:
        view = school_view(item)
        if view["status"] is None:
            continue
        path = view["path"] + "wrapped/"
        write(path, _stub_html(view, og_image))
        written.append((path, False))
    return written
