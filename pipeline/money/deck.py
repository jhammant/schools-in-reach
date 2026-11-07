"""Presentation decks (unit C2): one noindex shell page at /deck/ whose slides are built in the browser.

Writes: <out>/deck/index.html through env['write'] (nothing else; site.asset_files() copies
assets/deck.js and assets/deck.css to /assets/).
Reads: data/ifs_context.json (IFS framings, questions to ask and context lines, each with its page
numbers) and data/la_dsg.json (the statutory override note for council high-needs balances), both next
to this file, falling back to the real repository like areas.py does.

assets/deck.js reads the query (?urn=&view=school|ptfa, ?urns=a,b,c&view=compare, ?area=<id>), fetches
/data/s, /data/sx and /data/a, and builds the slides, the print layout and the PowerPoint file from one
model. This module only supplies the static context it needs, as an escaped JSON block.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from pipeline.money import deflator, site

PATH = "/deck/"
HERE = Path(__file__).resolve().parent
REAL_ROOT = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
REGISTER_URL = "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/"
FBIT_URL = "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/"

# The IFS framings and question sets the decks quote. Context lines are carried whole (they are short).
FRAMINGS = ["why_schools_go_into_deficit", "one_deficit_year", "falling_rolls", "send_pressure",
            "academy_central_top_slice", "real_terms", "funding_vs_spending_per_pupil", "pass_through_grants"]
QUESTION_SETS = ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves",
                 "falling_rolls", "academy", "high_send", "any"]


def _data_file(name: str) -> Path:
    """A file under pipeline/money/data, from this checkout or else the real repository."""
    local = HERE / "data" / name
    return local if local.exists() else REAL_ROOT / "pipeline/money/data" / name


def _load(name: str) -> dict:
    try:
        with open(_data_file(name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _dsg_note() -> str | None:
    """The 'Statutory override' sentence from la_dsg.json source notes, if present."""
    notes = (_load("la_dsg.json").get("source") or {}).get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    return next((n for n in notes if "statutory override" in str(n).lower()), None)


def deck_context() -> dict:
    """Everything deck.js quotes from the IFS report and the DSG notes, with page numbers kept."""
    ifs = _load("ifs_context.json")
    src = ifs.get("source") or {}
    framings = {}
    for key in FRAMINGS:
        f = (ifs.get("framings") or {}).get(key)
        if f:
            framings[key] = {"title": f.get("title"), "text": f.get("text"), "pages": f.get("pages") or []}
    questions = {}
    for key in QUESTION_SETS:
        q = (ifs.get("questions") or {}).get(key)
        if q:
            questions[key] = [{"text": x.get("text"), "why": x.get("why"), "page": x.get("page")}
                              for x in q.get("questions") or []]
    lines = {}
    for group, rows in (ifs.get("context_lines") or {}).items():
        lines[group] = [{"id": r.get("id"), "use_when": r.get("use_when"), "text": r.get("text"), "page": r.get("page")}
                        for r in rows or []]
    return {
        "cite": src.get("short_cite") or site.IFS_CITE,
        "url": src.get("url") or site.IFS_URL,
        "page_convention": src.get("page_convention"),
        "real_label": deflator.real_label(),
        "framings": framings,
        "questions": questions,
        "placeholders": (ifs.get("questions") or {}).get("_placeholders") or {},
        "context_lines": lines,
        "not_in_report": ifs.get("not_in_report") or [],
        "dsg_note": _dsg_note(),
        "links": {"register": REGISTER_URL, "fbit": FBIT_URL, "base": site.BASE_MONEY, "ptfa_guide": "/guides/ptfa/"},
    }


def _json_block(data: dict) -> str:
    """JSON safe inside <script>: '<' and '&' escaped as in site.page's JSON-LD."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("&", "\\u0026")


def _toolbar() -> str:
    buttons = [
        ("prev", "‹ Previous", "Previous slide"),
        ("next", "Next ›", "Next slide"),
        ("print", "Print / save as PDF", None),
        ("pptx", "Download PowerPoint", None),
        ("copy", "Copy link", None),
        ("full", "Full screen", "Full screen (F)"),
    ]
    out = []
    for key, text, label in buttons:
        aria = f' aria-label="{site.esc(label)}"' if label else ""
        out.append(f'<button type="button" data-deck="{key}"{aria}>{site.esc(text)}</button>')
        if key == "next":
            out.append('<span class="deck-count" id="deck-count">Slide 0 of 0</span>')
    return ('<div class="deck-toolbar" role="toolbar" aria-label="Presentation controls" hidden>'
            + "".join(out) + "</div>")


def _body(context: dict) -> str:
    intro = ("Presentations are built in your browser from the published figures for one school, its parents' "
             "association, a set of schools side by side, or a council or constituency.")
    wait = "Slides are built in your browser. If they don't appear, every figure is on the plain pages: "
    nojs = "JavaScript is off, so the slides can't be built here. You can still read every figure on the plain pages: "
    links = '<a href="/search/">search for a school</a> or <a href="/council/">browse councils</a>.'
    return (
        '<h1 class="deck-title">Presentation</h1>'
        f'<p class="lead deck-intro">{site.esc(intro)} Every figure carries its year and source.</p>'
        f"{_toolbar()}"
        '<p class="deck-msg" id="deck-msg" role="status" aria-live="polite"></p>'
        f'<div id="deck-app" class="deck" data-real-label="{site.esc(context["real_label"])}" '
        f'data-base="{site.esc(site.BASE_MONEY)}" aria-label="Slides">'
        f'<p class="deck-wait">{site.esc(wait)}{links}</p></div>'
        f'<noscript><p class="deck-noscript">{site.esc(nojs)}{links}</p></noscript>'
        '<p class="visually-hidden" id="deck-live" aria-live="polite"></p>'
        f'<script type="application/json" id="deck-context">{_json_block(context)}</script>'
    )


def write_pages(env, *, context: dict | None = None) -> list[tuple[str, bool]]:
    """Write /deck/ (noindex) through env['write']; returns [(path, indexable)]."""
    context = context or deck_context()
    og = env.get("og_image")
    if callable(og):
        og = og(PATH)
    head = '<link rel="stylesheet" href="/assets/deck.css"><script src="/assets/deck.js" defer></script>'
    html = env["page"](
        f"Presentation | {site.SITE_NAME}",
        "Slides about a school's money, its parents' association, a set of schools or an area, built from published "
        "figures. Print them, save a PDF or download PowerPoint.",
        PATH, _body(context), [("Home", "/"), ("Presentation", PATH)],
        og_image=og or None, indexable=False, extra_head=head)
    env["write"](PATH, html)
    return [(PATH, False)]


def deck_links(urn) -> str:
    """Two links for a school page: its school presentation and its PTFA presentation."""
    u = quote(str(urn), safe="")
    school = f"{PATH}?urn={u}&view=school"
    ptfa = f"{PATH}?urn={u}&view=ptfa"
    return (f'<p class="deck-links"><a href="{site.esc(school)}">School presentation</a> · '
            f'<a href="{site.esc(ptfa)}">PTFA presentation</a></p>')
