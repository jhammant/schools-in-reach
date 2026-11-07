"""Free guides and in-browser tools for School Money (unit C4).

Writes, in this order:
- /guides/ (an index grouped by audience) and /guides/<slug>/ for every Markdown file in data/guides/;
- /tools/, /tools/budget-check/, /tools/pta-planner/ and /tools/embed/;
all through env['page'] and indexable. Then /embed/<urn>/ for every school that has a status: a tiny,
static, noindex document (not env['page']) for other websites to show in an iframe.

Reads: data/guides/*.md (front matter plus a small Markdown subset), data/ifs_context.json (framings,
for {{ifs:framings.<key>}}), data/la_dsg.json (source.notes, for {{dsg:override_note}}) and env['items'].
assets/tools.js and assets/guides.css reach /assets/ through site.asset_files(); this module copies nothing.
Python stdlib only.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from pipeline.money import site
from pipeline.money import status as health

HERE = Path(__file__).resolve().parent
REAL_ROOT = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
GUIDES_DIR = HERE / "data" / "guides"

FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk/"
GUIDES_CSS = '<link rel="stylesheet" href="/assets/guides.css">'
TOOLS_JS = '<script src="/assets/tools.js" defer></script>'
EMBED_MAX_BYTES = 2048
REQUIRED = ("title", "description", "audience", "slug", "last_reviewed")

# audience key in the front matter -> who it is for, as in "Guide for ..." and "For ..."
AUDIENCES = [
    ("parents", "parents and carers"),
    ("governors", "governors"),
    ("ptfa", "PTFA and PTA committees"),
    ("school-leaders", "school leaders"),
    ("pupils", "pupils"),
    ("everyone", "everyone"),
]
ICONS = {"in_deficit": "▼", "heading_for_deficit": "↘", "tight": "●", "healthy": "✓", "large_reserves": "▲"}
SOURCE_NAMES = {"CFR": "DfE CFR return", "AAR": "DfE academy accounts return"}

# The framings the tools explain a forecast with; guides.py hands them to tools.js with their pages.
TOOL_FRAMINGS = ("why_schools_go_into_deficit", "one_deficit_year", "falling_rolls", "send_pressure", "pass_through_grants")

TOOLS = [
    ("budget-check", "Budget check",
     "Type in a school's income and spending for the next three years and see what would happen to its reserve, "
     "with the same five statuses the site uses."),
    ("pta-planner", "PTA planner",
     "Plan a year of fundraising, see what Gift Aid adds and compare the result per pupil with parents' "
     "associations at other schools in the council."),
    ("embed", "Embed a school's badge",
     "Get a small badge showing a school's money status to paste into a school, PTFA or governors' website."),
]


# ----------------------------------------------------------------- files

def _data_file(name: str) -> Path:
    """A data file next to this module, else the same file in the real repo (like areas.REAL_ROOT)."""
    local = HERE / "data" / name
    return local if local.exists() else REAL_ROOT / "pipeline" / "money" / "data" / name


def load_ifs() -> dict:
    """data/ifs_context.json: the IFS 2026 report's framings, questions and context lines with page numbers."""
    with open(_data_file("ifs_context.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_dsg() -> dict:
    """data/la_dsg.json: councils' Dedicated Schools Grant balances and the notes on how to read them."""
    with open(_data_file("la_dsg.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------- front matter and Markdown

def parse_front_matter(text: str) -> tuple[dict, str]:
    """(meta, body) for a guide. The file opens with 'key: value' lines between two '---' lines; the
    'sources:' key takes the '- title | url | detail' lines under it. Raises ValueError when malformed."""
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("a guide must start with a '---' front-matter block")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("the front-matter block is not closed with '---'")
    meta: dict = {}
    key = None
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and key == "sources":
            parts = [p.strip() for p in stripped[2:].split("|", 2)]
            if len(parts) != 3 or not all(parts):
                raise ValueError(f"a source must read 'title | url | detail': {stripped!r}")
            meta["sources"].append({"title": parts[0], "url": parts[1], "detail": parts[2]})
            continue
        match = re.match(r"^([a-z_]+):\s*(.*)$", stripped)
        if not match:
            raise ValueError(f"bad front-matter line: {stripped!r}")
        key, value = match.group(1), match.group(2).strip()
        if key == "sources":
            if value:
                raise ValueError("list sources on the lines under 'sources:'")
            meta["sources"] = []
        else:
            meta[key] = value
    return meta, "\n".join(lines[end + 1:]).strip("\n") + "\n"


_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_SAFE_URL = (re.compile(r"^https?://[^\s<>\"'\\]+$"), re.compile(r"^/(?![/\\])[^\s<>\"'\\]*$"))
_UL = re.compile(r"^- (.+)$")
_OL = re.compile(r"^\d+\. (.+)$")


def safe_url(url: str) -> bool:
    """True for http(s) links and site-relative paths; javascript:, data:, mailto: and //host are refused."""
    return any(p.match(url) for p in _SAFE_URL)


def _bold(text: str) -> str:
    parts = text.split("**")
    if len(parts) % 2 == 0:  # an unpaired ** stays as typed
        return site.esc(text)
    return "".join(f"<strong>{site.esc(p)}</strong>" if i % 2 else site.esc(p) for i, p in enumerate(parts))


def _inline(text: str) -> str:
    """Escaped text with **bold** and [text](url) links. An unsafe link URL raises ValueError."""
    out, pos = [], 0
    for match in _LINK.finditer(text):
        label, url = match.group(1), match.group(2)
        if not safe_url(url):
            raise ValueError(f"unsafe link URL in guide: {url!r}")
        out.append(_bold(text[pos:match.start()]))
        out.append(f'<a href="{site.esc(url)}">{_bold(label)}</a>')
        pos = match.end()
    out.append(_bold(text[pos:]))
    return "".join(out)


def render_markdown(text: str) -> str:
    """HTML for the guide subset: ## and ### headings, paragraphs, '- ' and '1. ' lists, '> ' notes,
    **bold** and [text](url) links (http(s) or site-relative only). Everything else is escaped text."""
    html: list[str] = []
    para: list[str] = []
    note: list[str] = []
    items: list[str] = []
    kind = None
    ids: set[str] = set()

    def flush():
        nonlocal kind
        if para:
            html.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()
        if note:
            html.append(f'<div class="note" role="note"><p>{_inline(" ".join(note))}</p></div>')
            note.clear()
        if items:
            html.append(f"<{kind}>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + f"</{kind}>")
            items.clear()
        kind = None

    def heading(level, words):
        anchor = base = site.slug(words)
        n = 2
        while anchor in ids:
            anchor, n = f"{base}-{n}", n + 1
        ids.add(anchor)
        html.append(f'<h{level} id="{anchor}">{_inline(words)}</h{level}>')

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("### "):
            flush()
            heading(3, line[4:].strip())
        elif line.startswith("## "):
            flush()
            heading(2, line[3:].strip())
        elif re.match(r"^#+(\s|$)", line):
            raise ValueError(f"only ## and ### headings are supported: {line!r}")
        elif line.startswith(">"):
            if para or items:
                flush()
            note.append(line[1:].strip())
        elif _UL.match(line) or _OL.match(line):
            new = "ul" if _UL.match(line) else "ol"
            if para or note or (kind and kind != new):
                flush()
            kind = new
            items.append((_UL.match(line) or _OL.match(line)).group(1))
        elif items and raw[:1].isspace():
            items[-1] += " " + line  # an indented line continues the list item above
        else:
            if note or items:
                flush()
            para.append(line)
    flush()
    return "\n".join(html)


# ----------------------------------------------------------------- placeholders

def pages_label(pages) -> str:
    """'p. 82' or 'pp. 62–63' or 'pp. 7, 10, 46': printed IFS page numbers, runs collapsed."""
    nums = sorted({int(p) for p in pages})
    if not nums:
        raise ValueError("an IFS framing needs page numbers")
    runs, start = [], nums[0]
    for prev, cur in zip(nums, nums[1:] + [None]):
        if cur is None or cur != prev + 1:
            runs.append(str(start) if start == prev else f"{start}–{prev}")
            start = cur
    return ("p. " if len(nums) == 1 else "pp. ") + ", ".join(runs)


def ifs_framing(ifs: dict, key: str) -> str:
    """One IFS framing's text with its pages, e.g. '... (IFS 2026 report, pp. 62–63)'."""
    framing = (ifs.get("framings") or {}).get(key)
    if not framing or not framing.get("text"):
        raise ValueError(f"unknown IFS framing: {key!r}")
    return f"{framing['text']} (IFS 2026 report, {pages_label(framing.get('pages') or [])})"


def dsg_override_note(dsg: dict) -> str:
    """The la_dsg.json source note that starts 'Statutory override' (the High Needs Stability Grant note)."""
    notes = (dsg.get("source") or {}).get("notes") or []
    note = next((n for n in notes if str(n).startswith("Statutory override")), None)
    if note is None:
        raise ValueError("la_dsg.json has no 'Statutory override' note")
    return note


_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")


def expand_placeholders(text: str, ifs: dict, dsg: dict) -> str:
    """Fill {{ifs:framings.<key>}} and {{dsg:override_note}}. Any other placeholder raises ValueError."""
    def fill(match):
        name = match.group(1)
        if name.startswith("ifs:framings."):
            return ifs_framing(ifs, name[len("ifs:framings."):])
        if name == "dsg:override_note":
            return dsg_override_note(dsg)
        raise ValueError(f"unknown placeholder: {{{{{name}}}}}")
    out = _PLACEHOLDER.sub(fill, text)
    if "{{" in out or "}}" in out:
        raise ValueError("unclosed placeholder in guide")
    return out


# ----------------------------------------------------------------- guides

def _reviewed(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.day} {day:%B %Y}"


def load_guides(dir=None, *, ifs=None, dsg=None) -> list[dict]:
    """Every guide in dir (default data/guides/), sorted by file name: the front matter plus 'body'
    (Markdown with placeholders filled), 'html' and 'path'. Raises ValueError for an incomplete guide."""
    folder = Path(dir) if dir else (GUIDES_DIR if GUIDES_DIR.exists() else REAL_ROOT / "pipeline/money/data/guides")
    ifs = ifs if ifs is not None else load_ifs()
    dsg = dsg if dsg is not None else load_dsg()
    guides = []
    for file in sorted(folder.glob("*.md")):
        meta, body = parse_front_matter(file.read_text(encoding="utf-8"))
        missing = [k for k in REQUIRED if not meta.get(k)]
        if missing or not meta.get("sources"):
            raise ValueError(f"{file.name}: missing {', '.join(missing) or 'sources'}")
        if meta["slug"] != file.stem or not re.fullmatch(r"[a-z0-9-]+", meta["slug"]):
            raise ValueError(f"{file.name}: slug must match the file name")
        date.fromisoformat(meta["last_reviewed"])
        for source in meta["sources"]:
            if not source["url"].startswith(("https://", "http://")):
                raise ValueError(f"{file.name}: source URL must be http(s): {source['url']!r}")
        body = expand_placeholders(body, ifs, dsg)
        guides.append({**meta, "body": body, "html": render_markdown(body), "path": f"/guides/{meta['slug']}/"})
    return guides


def _audience_label(key: str) -> str:
    return dict(AUDIENCES).get(key, key.replace("-", " "))


def guides_index(guides: list[dict], page) -> str:
    """/guides/: every guide grouped by audience, then the tools."""
    groups = []
    known = [k for k, _ in AUDIENCES] + sorted({g["audience"] for g in guides} - {k for k, _ in AUDIENCES})
    for key in known:
        mine = [g for g in guides if g["audience"] == key]
        if not mine:
            continue
        links = "".join(f'<li><a href="{site.esc(g["path"])}">{site.esc(g["title"])}</a>'
                        f'<p class="muted small">{site.esc(g["description"])}</p></li>' for g in mine)
        groups.append(f'<section class="guide-group" aria-labelledby="g-{site.esc(key)}"><h2 id="g-{site.esc(key)}">'
                      f'For {site.esc(_audience_label(key))}</h2>'
                      f'<ul class="guide-list">{links}</ul></section>')
    body = ('<div class="guide-index"><h1>Guides</h1>'
            '<p class="lead">Free, plain-English guides to school money: what the figures mean, how to read a deficit fairly, '
            'and what helps. Each one lists the official sources it relies on.</p>'
            f'<div class="guide-groups">{"".join(groups)}</div>{_tools_strip()}</div>')
    return page("Guides to school money | School Money",
                "Free guides to school money for parents, governors, PTFA committees, school leaders and pupils, with official sources.",
                "/guides/", body, [("School Money", "/"), ("Guides", "/guides/")], extra_head=GUIDES_CSS)


def _tools_strip() -> str:
    links = "".join(f'<li><a href="/tools/{slug}/">{site.esc(name)}</a>: {site.esc(text)}</li>' for slug, name, text in TOOLS)
    return (f'<section class="tool-strip" aria-labelledby="free-tools"><h2 id="free-tools">Free tools</h2>'
            f'<ul class="guide-list">{links}</ul><p class="muted small">The tools run in your browser. Nothing you type is sent anywhere.</p></section>')


def guide_page(guide: dict, page, guides: list[dict]) -> str:
    """/guides/<slug>/: the article, its sources and the date it was last checked."""
    sources = "".join(f'<li><a href="{site.esc(s["url"])}" rel="noopener">{site.esc(s["title"])}</a>, {site.esc(s["detail"])}</li>'
                      for s in guide["sources"])
    others = "".join(f'<li><a href="{site.esc(g["path"])}">{site.esc(g["title"])}</a></li>' for g in guides if g["slug"] != guide["slug"])
    body = (f'<article class="guide"><header class="guide-head"><p class="kicker">Guide for {site.esc(_audience_label(guide["audience"]))}</p>'
            f'<h1>{site.esc(guide["title"])}</h1><p class="lead">{site.esc(guide["description"])}</p></header>'
            f'<div class="guide-body">{guide["html"]}</div>'
            f'<section class="guide-sources" aria-labelledby="guide-sources"><h2 id="guide-sources">Sources</h2><ul>{sources}</ul>'
            f'<p class="muted small">Last reviewed <time datetime="{site.esc(guide["last_reviewed"])}">{_reviewed(guide["last_reviewed"])}</time>.</p></section>'
            f'<nav class="guide-more" aria-label="More guides"><h2>More guides</h2><ul>{others}</ul>'
            f'<p><a href="/tools/">Free tools</a> · <a href="/about/">How the figures are worked out</a></p></nav></article>')
    crumbs = [("School Money", "/"), ("Guides", "/guides/"), (guide["title"], guide["path"])]
    return page(f"{guide['title']} | School Money", guide["description"], guide["path"], body, crumbs, extra_head=GUIDES_CSS)


# ----------------------------------------------------------------- tools

def tools_context(ifs: dict) -> dict:
    """Static context tools.js reads from the page: the IFS citation and framings with their pages."""
    source = ifs.get("source") or {}
    framings = {}
    for key in TOOL_FRAMINGS:
        f = (ifs.get("framings") or {}).get(key)
        if f:
            framings[key] = {"title": f.get("title"), "text": f.get("text"), "pages": pages_label(f.get("pages") or [])}
    return {"ifs": {"cite": source.get("short_cite") or site.IFS_CITE, "url": source.get("url") or site.IFS_URL, "framings": framings}}


def _json_block(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    return f'<script type="application/json" id="tools-context">{text}</script>'


def _field(ident, label, *, hint="", kind="text", attrs="", value=""):
    hint_html = f'<span class="hint" id="{ident}-hint">{site.esc(hint)}</span>' if hint else ""
    described = f' aria-describedby="{ident}-hint"' if hint else ""
    val = f' value="{site.esc(value)}"' if value else ""
    return (f'<div class="field"><label for="{ident}">{site.esc(label)}</label>{hint_html}'
            f'<input id="{ident}" name="{ident}" type="{kind}"{val}{described} {attrs}></div>')


def _money_field(ident, label, hint=""):
    return _field(ident, label, hint=hint, attrs='inputmode="decimal" autocomplete="off" placeholder="£"')


def _urn_form(prefix, button, hint):
    return (f'<form class="tool-form tool-load" id="{prefix}-load" novalidate>'
            + _field(f"{prefix}-urn", "School URN", hint=hint, attrs='inputmode="numeric" autocomplete="off" pattern="[0-9]{5,8}"')
            + f'<button type="submit" class="button">{site.esc(button)}</button>'
            f'<p class="tool-status" id="{prefix}-load-status" role="status" aria-live="polite"></p></form>')


NOTHING_SENT = ('<p class="tool-private"><strong>Nothing is sent anywhere.</strong> Everything you type stays in this browser '
                '(a draft is kept on this device so you can come back to it). The tool only downloads figures this site publishes.</p>')
URN_HINT = "The number in the school's School Money web address, for example 130932."


def _noscript(what):
    return (f'<noscript><p class="note">This tool needs JavaScript. Without it, you can {what} on the '
            f'<a href="{FBIT}" rel="noopener">DfE Financial Benchmarking and Insights Tool</a>, '
            'or <a href="/">find the school\'s page</a> on School Money.</p></noscript>')


def _budget_body():
    years = "".join(
        f'<fieldset class="year"><legend>Year {i}</legend><div class="field-row">'
        + _money_field(f"bc-inc-{i}", "Income")
        + _money_field(f"bc-sp-{i}", "Spending")
        + _money_field(f"bc-res-{i}", "Reserve at year end (optional)", "Only if you know it; otherwise it is worked out.")
        + "</div></fieldset>" for i in (1, 2, 3))
    phase = ('<div class="field"><label for="bc-phase">Type of school</label><select id="bc-phase" name="bc-phase">'
             '<option value="primary">Primary</option><option value="secondary">Secondary</option>'
             '<option value="default">Special, all-through or other</option></select></div>')
    return (
        '<p>A budget check takes one school\'s last full year and your forecast for up to three more, then works out '
        'the reserve at the end of each year and the status this site would give it: in deficit, heading for deficit, '
        'tight, healthy or large reserves. It uses exactly the same rules as the school pages, and explains the result '
        'with what helps.</p>'
        '<p>Start from a school\'s published figures, or type in your own. Figures are cash, as reported to the DfE.</p>'
        + NOTHING_SENT + _noscript("see a school's published figures and its three-year forecasts")
        + '<div class="tool" data-tool="budget-check" hidden>'
        + '<h2>1. Start from a school (optional)</h2>' + _urn_form("bc", "Load published figures", URN_HINT)
        + '<form class="tool-form" id="bc-form" novalidate><h2>2. The last full year</h2><div class="field-row">'
        + _field("bc-year", "Year", hint="For example 2025-26.", attrs='autocomplete="off"', value="2025-26")
        + phase + _money_field("bc-income", "Income") + _money_field("bc-spend", "Spending")
        + _money_field("bc-reserve", "Reserve at year end", "Below zero means in deficit, e.g. -20000.")
        + _field("bc-pupils", "Pupils", attrs='inputmode="decimal" autocomplete="off"')
        + '</div><h2>3. The next three years</h2><p class="hint">Leave a year blank to stop the forecast there.</p>' + years
        + '<div class="actions"><button type="submit" class="button">Check the budget</button>'
          '<button type="button" class="button quiet" data-clear>Clear</button></div></form>'
        + '<section class="tool-result" aria-labelledby="bc-result-h"><h2 id="bc-result-h">What the figures show</h2>'
          '<div id="bc-out" aria-live="polite"><p class="muted">Fill in the figures and press Check the budget.</p></div></section></div>'
        + '<p class="muted small">Want to understand the statuses first? Read the <a href="/guides/parents/">guide for parents</a> '
          'or the <a href="/guides/governors/">guide for governors</a>.</p>')


def _pta_body():
    rows = "".join(
        f'<fieldset class="event"><legend>Event {i}</legend><div class="field-row">'
        + _field(f"pp-name-{i}", "Name", attrs=f'autocomplete="off" placeholder="{site.esc(name)}"')
        + _money_field(f"pp-inc-{i}", "Ticket sales and other takings", "Not eligible for Gift Aid.")
        + _money_field(f"pp-don-{i}", "Donations", "Gifts with nothing in return.")
        + "</div></fieldset>" for i, name in ((1, "Summer fair"), (2, "Sponsored walk"), (3, "Winter appeal")))
    return (
        '<p>The PTA planner adds up a year of fundraising, shows what Gift Aid could add on top of donations, and works '
        'out the total per pupil. With a school or council loaded, it compares that with what registered parents\' '
        'associations at schools in the same council raised per pupil, from the Charity Commission register.</p>'
        '<p>Gift Aid adds 25p to every £1 donated by a UK taxpayer who has signed a Gift Aid declaration. It cannot be '
        'claimed on ticket sales, raffles or anything bought. Read the <a href="/guides/ptfa/">guide for PTFA committees</a> '
        'for registering, Gift Aid and reporting.</p>'
        + NOTHING_SENT + _noscript("look up a parents' association on the Charity Commission register or see the school's figures")
        + '<div class="tool" data-tool="pta-planner" hidden>'
        + '<h2>1. Start from a school (optional)</h2>' + _urn_form("pp", "Load the school", URN_HINT)
        + '<section id="pp-charity" class="tool-charity" aria-live="polite"></section>'
        + '<form class="tool-form" id="pp-form" novalidate><h2>2. The year\'s fundraising</h2><div class="field-row">'
        + _field("pp-pupils", "Pupils at the school", attrs='inputmode="decimal" autocomplete="off"')
        + _field("pp-gift", "Donations with a Gift Aid declaration (%)", hint="Your best guess, for example 50.",
                 attrs='inputmode="decimal" autocomplete="off"')
        + _money_field("pp-target", "Target per pupil (optional)")
        + f'</div><div id="pp-events">{rows}</div>'
        + '<div class="actions"><button type="button" class="button quiet" id="pp-add">Add another event</button>'
          '<button type="submit" class="button">Work it out</button>'
          '<button type="button" class="button quiet" data-clear>Clear</button></div></form>'
        + '<section class="tool-result" aria-labelledby="pp-result-h"><h2 id="pp-result-h">Your plan</h2>'
          '<div id="pp-out" aria-live="polite"><p class="muted">Add your events and press Work it out.</p></div></section></div>')


def _embed_body():
    return (
        '<p>The badge shows a school\'s latest money status (with its icon and label), its reserve per pupil with the '
        'year and source, and a link back to its School Money page. It is a plain page with no scripts, no cookies '
        'and no tracking, and it updates whenever the site is rebuilt.</p>'
        '<p>Type the school\'s URN, copy the code, and paste it into your website\'s HTML.</p>'
        + NOTHING_SENT + _noscript("see the school's figures")
        + '<div class="tool" data-tool="embed" hidden>' + _urn_form("em", "Make the code", URN_HINT)
        + '<div class="field"><label for="em-code">Code to paste into your website</label>'
          '<textarea id="em-code" rows="4" readonly></textarea></div>'
        + '<div class="actions"><button type="button" class="button" id="em-copy">Copy the code</button>'
          '<span class="tool-status" id="em-copied" role="status" aria-live="polite"></span></div>'
        + '<h2>Preview</h2><div class="embed-preview"><p class="muted" id="em-empty">The preview appears here.</p>'
          '<iframe id="em-preview" title="Preview of the School Money badge" width="320" height="140" loading="lazy" hidden></iframe></div></div>')


def tools_index(page) -> str:
    """/tools/: the three tools, explained."""
    cards = "".join(f'<li class="card"><h2><a href="/tools/{slug}/">{site.esc(name)}</a></h2><p>{site.esc(text)}</p></li>'
                    for slug, name, text in TOOLS)
    body = ('<h1>Free tools</h1><p class="lead">Small tools for parents, governors, PTFA committees and school leaders. '
            'They run in your browser: nothing you type is sent anywhere.</p>'
            f'<ul class="tool-cards">{cards}</ul>'
            '<p>New to school money? Start with the <a href="/guides/">guides</a>.</p>')
    return page("Free school money tools | School Money",
                "A budget check, a PTA fundraising planner and an embeddable school badge. Free, and nothing you type leaves your browser.",
                "/tools/", body, [("School Money", "/"), ("Tools", "/tools/")], extra_head=GUIDES_CSS)


def tool_page(slug: str, page, context: dict) -> str:
    """/tools/<slug>/: server-rendered explanation, a form tools.js brings to life, and a no-JS fallback."""
    name, text = next((n, t) for s, n, t in TOOLS if s == slug)
    body = {"budget-check": _budget_body, "pta-planner": _pta_body, "embed": _embed_body}[slug]()
    path = f"/tools/{slug}/"
    html = f'<h1>{site.esc(name)}</h1><p class="lead">{site.esc(text)}</p>{body}{_json_block(context)}'
    return page(f"{name} | School Money", text, path, html, [("School Money", "/"), ("Tools", "/tools/"), (name, path)],
                extra_head=GUIDES_CSS + TOOLS_JS)


# ----------------------------------------------------------------- embeds

def school_view(item: dict) -> dict:
    """The one place this unit reads a school item (see the shared contracts): urn, name, path, pupils
    (latest, and in the status year) and a status dict, or None when the school has no status."""
    urn = str(item["urn"])
    name = str(item["name"])
    raw = item.get("status")
    if isinstance(raw, dict) and raw.get("status") in health.LABELS:
        state = {k: raw.get(k) for k in ("status", "label", "reason", "reserve", "year", "source")}
        state["label"] = state["label"] or health.LABELS[state["status"]]
    elif isinstance(raw, str) and raw in health.LABELS:
        state = {"status": raw, "label": health.LABELS[raw], "reason": None, "reserve": None, "year": None, "source": None}
    else:
        state = None
    years = health.full_years(item.get("rows") or [])
    pupils = item.get("pupils")
    if pupils is None and years:
        pupils = years[-1].get("pupils")
    status_pupils = next((r.get("pupils") for r in reversed(years) if state and r.get("year") == state["year"] and r.get("pupils")), None)
    return {"urn": urn, "name": name, "path": item.get("path") or site.page_path("school", urn, name),
            "pupils": pupils, "status_pupils": status_pupils or pupils, "status": state}


def _exact(value) -> str:
    """£4,115 style, to the pound, with a minus sign for a deficit."""
    return f"{'-' if value < 0 else ''}£{abs(round(value)):,}"


def embed_page(view: dict) -> str:
    """A static iframe document of at most 2,048 bytes: badge (icon + label), reserve per pupil with year
    and source, and a link back to the school's page. No scripts, noindex."""
    state = view["status"]
    key = state["status"]
    name = site.esc(view["name"])
    reserve, pupils = state.get("reserve"), view.get("status_pupils")
    when = ", ".join(site.esc(x) for x in (state.get("year"), SOURCE_NAMES.get(state.get("source"), state.get("source"))) if x)
    if isinstance(reserve, (int, float)) and pupils:
        figure = f'<p class="embed-fig"><b>{_exact(reserve / pupils)}</b> reserve per pupil</p>'
        detail = f"{_exact(reserve)} in total" + (f" · {when}" if when else "")
    elif isinstance(reserve, (int, float)):
        figure, detail = f'<p class="embed-fig"><b>{_exact(reserve)}</b> reserve</p>', when
    else:
        figure, detail = '<p class="embed-fig">Figures are on the school\'s page.</p>', when
    source = f'<p class="embed-src">{detail}</p>' if detail else ""
    url = site.esc(site.BASE_MONEY + view["path"])
    html = ('<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
            f'<title>{name}: {site.SITE_NAME}</title><link rel="stylesheet" href="/assets/app.css">'
            '<link rel="stylesheet" href="/assets/guides.css"></head><body class="embed"><div class="embed-card">'
            f'<span class="badge s-{key}"><span aria-hidden="true">{ICONS[key]}</span> {site.esc(state["label"])}</span>'
            f'{figure}{source}<a class="embed-link" href="{url}" target="_blank" rel="noopener"><span class="n">{name}</span><span class="s"> on {site.SITE_NAME}</span></a>'
            '</div></body></html>\n')
    if len(html.encode("utf-8")) > EMBED_MAX_BYTES:
        raise ValueError(f"embed for {view['urn']} is over {EMBED_MAX_BYTES} bytes")
    return html


# ----------------------------------------------------------------- entry point

def write_pages(env, *, guides_dir=None, ifs=None, dsg=None) -> list[tuple[str, bool]]:
    """Write the guides, the tools and the embeds; return (path, indexable) for each page, in write order.
    guides_dir, ifs and dsg are test overrides for data/guides/, ifs_context.json and la_dsg.json."""
    ifs = ifs if ifs is not None else load_ifs()
    dsg = dsg if dsg is not None else load_dsg()
    page, write = env["page"], env["write"]
    written: list[tuple[str, bool]] = []

    def emit(path, html, indexable):
        write(path, html)
        written.append((path, indexable))

    guides = load_guides(guides_dir, ifs=ifs, dsg=dsg)
    emit("/guides/", guides_index(guides, page), True)
    for guide in guides:
        emit(guide["path"], guide_page(guide, page, guides), True)
    emit("/tools/", tools_index(page), True)
    context = tools_context(ifs)
    for slug, _name, _text in TOOLS:
        emit(f"/tools/{slug}/", tool_page(slug, page, context), True)
    for item in env.get("items") or []:
        view = school_view(item)
        if view["status"] is None or not re.fullmatch(r"\d+", view["urn"]):
            continue
        emit(f"/embed/{view['urn']}/", embed_page(view), False)
    return written
