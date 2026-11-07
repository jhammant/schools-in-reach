"""Find parents' association charity numbers on school websites, politely.

For each open state school with a website, reads at most six pages: the homepage, the
school's own PTA / Friends pages linked from it, and the PTA's own site when the school
links to one. Charity numbers found there are kept only when the Charity Commission
register names a parents' association (or the page around the number clearly does), and
written to pta_crawl.json for pta.py to merge with method "website-crawl".

Polite by construction: robots.txt is honoured per host, every request carries a
User-Agent naming the project, and no host sees more than one request a second.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections import Counter, defaultdict, namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from pipeline.money import pta

MAIN = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
CHARITY_DIR = MAIN / "pipeline/.cache/charity"
SITE_DATA = MAIN / "site/data"
OUT = MAIN / "pipeline/.cache/money/pta_crawl.json"
USER_AGENT = "SchoolsInReach-research/1.0 (+https://www.schoolsinreach.com/about.html)"
MAX_WORKERS = 24
HOST_INTERVAL = 1.0      # seconds between requests to one host
MAX_CRAWL_DELAY = 30.0   # a robots.txt Crawl-delay is honoured up to this
TIMEOUT = 10
MAX_PAGES = 6            # per school, robots.txt not counted
PTA_SITE_PAGES = 3       # the PTA's own homepage, /about*, /contact*
MAX_BYTES = 2_000_000
SAVE_EVERY = 200
LOG_EVERY = 500
MAX_SHARED = 4           # a number on more schools' sites than this is an umbrella body, held back
NEAR = 120               # a bare number must sit this close to PTA wording

# ----------------------------------------------------------------- words

_EDGE_L, _EDGE_R = r"(?<![a-z0-9])", r"(?![a-z0-9])"
ACRONYMS = r"(?:pta|ptfa|ptsa|pfa|psa|hsa)"
# Wording that marks a parents' association, in page text or in a link's text or href.
PTA_WORDS = re.compile(
    _EDGE_L + ACRONYMS + _EDGE_R + r"|\bfriends[\s_-]+of\b|\bparents?['’]?[\s_-]+(?:and[\s_-]+(?:teachers?|friends)[\s_-]+)?"
    r"association\b|\bparent[\s_/-]*(?:teacher|staff)\b|\bhome[\s_-]+school[\s_-]+association\b", re.I)
LINK_WORDS = re.compile(PTA_WORDS.pattern + r"|fundrais", re.I)
# What the text around an accepted number must say when the register name alone does not.
EVIDENCE_WORDS = re.compile(_EDGE_L + ACRONYMS + _EDGE_R + r"|\bfriends\b|\bparents?\b", re.I)
# A host that is itself a PTA's site: williampattenptfa.org.uk, friendsofx.org, x-pta.co.uk.
PTA_HOST = re.compile(r"^" + ACRONYMS + r"|" + ACRONYMS + r"$|friendsof|parents?association|parentteacher", re.I)

# 'Registered charity no. 1103834', 'Charity number: 1103834', 'a registered charity (number 1179031)',
# 'registered with the Charity Commission (1103834)'.
CHARITY_NO = re.compile(
    r"\bcharity\s*\(?\s*(?:commission\s*)?(?:in\s+england\s+(?:and|&)\s+wales\s*)?(?:registration\s*|reg(?:istered)?\.?\s*)?"
    r"(?:number|no|num)?\.?\s*[:#.]?\s*\(?\s*(\d{6,7})(?!\d)", re.I)
BARE_NO = re.compile(r"(?<![\w£$€/=#.-])(\d{6,7})(?![\w/=-]|[.,]\d)")
# Numbers that are something else, blanked before looking for bare numbers.
PHONE = re.compile(r"(?:\+\s?44\s?(?:\(0\)\s?)?|(?<!\d)0)\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?!\d)")
LABELLED = re.compile(r"\b(?:urn|ofsted|dfe|laestab|ukprn|company|vat|tel|telephone|phone|fax|mobile|ref|reference)\b"
                      r"[^\d]{0,25}\d[\d ]{5,9}", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Links to the register that carry the number itself.
REGISTER_LINK = re.compile(r"(?:regid=|registeredcharitynumber=|gb-chc-)(\d{6,7})(?!\d)", re.I)

# Register names that are not one school's parents' association even beside PTA wording.
NATIONAL_BODY = re.compile(r"\b(?:national|confederation|parentkind|associations)\b", re.I)
NOT_PTA_NAME = re.compile(r"\b(?:trust|trustees|foundation|diocese|diocesan|endowment|parish|church|chapel|almshouses?)\b", re.I)

SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
FILE_LINK = re.compile(r"\.(?:pdf|docx?|xlsx?|pptx?|jpe?g|png|gif|zip|mp4|mp3)$", re.I)
OFFSITE_SKIP = pta.GENERIC_HOSTS | {
    "youtube.com", "youtu.be", "paypal.com", "paypal.me", "amazon.co.uk", "amazon.com", "eventbrite.co.uk", "eventbrite.com",
    "gofundme.com", "parentpay.com", "scopay.com", "schoolmoney.co.uk", "arbor-education.com", "tiktok.com", "linkedin.com",
    "whatsapp.com", "givey.com", "totalgiving.co.uk", "virginmoneygiving.com", "bit.ly", "goo.gl", "office.com",
    "microsoft.com", "sharepoint.com", "live.com", "dropbox.com", "list-manage.com", "mailchimp.com", "schoolgateway.com",
    "school-gateway.co.uk", "squarespace.com", "canva.com", "padlet.com", "flickr.com", "vimeo.com", "apple.com",
    "donorbox.org", "crowdfunder.co.uk", "givebutter.com", "ticketsource.co.uk", "ticketsource.com", "tickettailor.com",
    "jumblebee.co.uk", "yourschoollottery.co.uk", "giveasyoulive.com", "signupgenius.com", "doodle.com", "zoom.us",
    "forms.gle", "stripe.com", "sumup.co.uk", "square.site", "wonde.com", "google.co.uk",
}

Page = namedtuple("Page", "url html status")       # status: ok | robots | error
Link = namedtuple("Link", "url text offsite strong")


def plausible_number(n) -> bool:
    """Registered charity numbers run 200000-999999 (older) and 1000000-1299999; Ofsted URNs sit below."""
    return 200_000 <= n < 1_300_000


def host_key(url) -> str:
    host = (urlsplit(url).hostname or "").lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def normalise_url(raw) -> str | None:
    """A fetchable http(s) URL for a register website field, or None."""
    text = str(raw or "").strip().split()[0] if str(raw or "").strip() else ""
    if not text:
        return None
    if "://" not in text:
        text = "http://" + text
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https") or "." not in (parts.hostname or ""):
        return None
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def site_key(url) -> str:
    """Two register entries pointing at the same site share a key."""
    parts = urlsplit(url)
    return host_key(url) + parts.path.rstrip("/").lower()


# ------------------------------------------------------------------- html

class _Parser(HTMLParser):
    """Visible text, footer text, links and title of one page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks, self.footer, self.links, self.title = [], [], [], []
        self._skip = 0
        self._footer = None   # [tag, depth] while inside a footer
        self._link = None     # [href, [text]] while inside <a>
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = {k: v or "" for k, v in attrs}
        self.chunks.append(" ")
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        if self._footer and tag == self._footer[0]:
            self._footer[1] += 1
        elif self._footer is None and (tag == "footer" or (
                tag in ("div", "section") and "footer" in (attrs.get("id", "") + " " + attrs.get("class", "")).lower())):
            self._footer = [tag, 1]
        if tag == "a" and attrs.get("href"):
            self._link = [attrs["href"], [attrs.get("title", ""), attrs.get("aria-label", "")]]
        elif tag == "img" and self._link:
            self._link[1].append(attrs.get("alt", ""))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in SKIP_TAGS:
            self._skip -= 1

    def handle_endtag(self, tag):
        self.chunks.append(" ")
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        if self._footer and tag == self._footer[0]:
            self._footer[1] -= 1
            if not self._footer[1]:
                self._footer = None
        if tag == "a" and self._link:
            self.links.append((self._link[0], _squash(" ".join(self._link[1]))))
            self._link = None

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
            return
        if self._skip:
            return
        self.chunks.append(data)
        if self._footer:
            self.footer.append(data)
        if self._link:
            self._link[1].append(data)


Parsed = namedtuple("Parsed", "text footer links title")


def _squash(text) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse(html) -> Parsed:
    """Parse once; the public helpers below accept either HTML or a Parsed."""
    if isinstance(html, Parsed):
        return html
    p = _Parser()
    try:
        p.feed(html or "")
        p.close()
    except Exception:  # html.parser is lenient, but a broken page must never stop the crawl
        pass
    text = _squash("".join(p.chunks))
    tail = text[int(len(text) * 0.8):]
    footer = _squash(" ".join(p.footer))
    return Parsed(text, _squash(footer + " " + tail) if footer else tail, p.links, _squash(" ".join(p.title)))


def footer_text(html) -> str:
    """Text of the page's <footer> (or footer div) plus the last 20% of its visible text."""
    return parse(html).footer


def _snippet(text, start, end, pad=90) -> str:
    """The text around a match, with volunteers' emails and phone numbers taken out."""
    text = _squash(text[max(0, start - pad):end + pad])
    return PHONE.sub("[phone]", EMAIL.sub("[email]", text))[:240]


def _blank(text) -> str:
    """Phone numbers and labelled numbers (URN, company, VAT...) blanked, offsets kept."""
    for pattern in (PHONE, LABELLED):
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


def is_pta_page(url, title="") -> bool:
    parts = urlsplit(url)
    if any(PTA_HOST.search(label) for label in re.split(r"[.-]", host_key(url))):
        return True
    return bool(PTA_WORDS.search(unquote(parts.path + " " + parts.query)) or PTA_WORDS.search(title or ""))


def extract_candidates(html, base_url, pta_page=None) -> list[dict]:
    """Charity numbers on one page: explicit 'registered charity no.' phrases anywhere, bare numbers
    within NEAR characters of PTA wording, register links, and on PTA pages bare numbers in the footer.

    Each candidate is {"charity_number", "evidence", "context_url", "pta_page"}.
    """
    page = parse(html)
    if pta_page is None:
        pta_page = is_pta_page(base_url, page.title)
    found = {}

    def add(number, evidence):
        n = int(number)
        if plausible_number(n) and n not in found:
            found[n] = {"charity_number": n, "evidence": evidence, "context_url": base_url, "pta_page": bool(pta_page)}

    text = page.text
    for m in CHARITY_NO.finditer(text):
        add(m.group(1), _snippet(text, m.start(), m.end()))
    for href, label in page.links:
        m = REGISTER_LINK.search(unquote(href))
        if m:
            add(m.group(1), _squash(f"link to the charity register: {label}"))
    blanked = _blank(text)
    marks = [m.span() for m in PTA_WORDS.finditer(text)]
    for m in BARE_NO.finditer(blanked):
        if any(s - NEAR <= m.end() and m.start() <= e + NEAR for s, e in marks):
            add(m.group(1), _snippet(text, m.start(), m.end()))
    if pta_page:
        footer = page.footer
        for m in BARE_NO.finditer(_blank(footer)):
            add(m.group(1), _snippet(footer, m.start(), m.end()))
    return list(found.values())


def pta_links(html, base_url) -> list[Link]:
    """Links that lead to the school's PTA: same-site pages first (strong wording before 'fundraising'),
    then other sites flagged offsite=True when the link clearly points at a PTA's own site."""
    page = parse(html)
    home = host_key(base_url)
    same, off, seen = [], [], {base_url.rstrip("/")}
    for href, label in page.links:
        url = urljoin(base_url, href.strip()).split("#")[0]
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or FILE_LINK.search(parts.path) or url.rstrip("/") in seen:
            continue
        target = unquote(parts.path + " " + parts.query)
        host = host_key(url)
        if host == home:
            if LINK_WORDS.search(label) or LINK_WORDS.search(target):
                seen.add(url.rstrip("/"))
                strong = bool(PTA_WORDS.search(label) or PTA_WORDS.search(target))
                same.append(Link(url, label, False, strong))
            continue
        if not pta.domain(url) or host in OFFSITE_SKIP or any(host.endswith("." + h) for h in OFFSITE_SKIP):
            continue
        # A link whose host says PTA is the PTA's site; one whose text alone says so must point at a site's
        # front or one page of it, not deep into a donation or ticketing platform.
        shallow = "/" not in parts.path.strip("/") and not parts.query
        if any(PTA_HOST.search(part) for part in re.split(r"[.-]", host)) or (shallow and _clearly_pta(label, home)):
            seen.add(url.rstrip("/"))
            off.append(Link(url, label, True, True))
    same.sort(key=lambda link: not link.strong)
    return same + off


def _clearly_pta(label, home_host) -> bool:
    """Link text that names a PTA: an acronym or 'parents association' outright; 'Friends of ...' only
    when it names a school or the school's own site name ('Friends of the Earth' is not a PTA)."""
    m = PTA_WORDS.search(label)
    if not m:
        return False
    if not m.group(0).lower().startswith("friends") or PTA_WORDS.search(label, m.end()):
        return True
    letters = re.sub(r"[^a-z]", "", home_host)
    tokens = pta.normalise(label)
    return bool(pta.SCHOOL_WORDS.search(label) or (tokens and all(t in letters for t in tokens)))


def _about_links(html, base_url) -> list[str]:
    """/about* and /contact* pages on a PTA's own site."""
    page, home, urls = parse(html), host_key(base_url), []
    for href, _ in page.links:
        url = urljoin(base_url, href.strip()).split("#")[0]
        if host_key(url) == home and re.match(r"/(?:about|contact)", urlsplit(url).path, re.I) and url not in urls:
            urls.append(url)
    return urls


# ------------------------------------------------------------- validation

def validate(candidates, registry, school_name=None, shared=False) -> list[dict]:
    """Candidates the register confirms, in the pta_crawl.json entry shape.

    Kept when the register name reads as a parents' association, or when the page around the number
    says PTA/Friends/parents and the register name shares a word with the school's name. Dropped:
    umbrella bodies, trusts and foundations, phase clashes ('Junior' PTA for an infant school), and on a
    site several schools share, any name that does not carry this school's whole name. A name sharing
    nothing with the school's (a renamed school's old PTA, or another school's PTA in the news) is kept
    only when it was found on a PTA page and is the site's one PTA.
    """
    school_tokens = set(pta.normalise(school_name)) if school_name else set()
    school_phase = pta.phase_words(school_name) if school_name else set()
    fitting, foreign, seen = [], [], set()
    for c in candidates:
        number = int(c["charity_number"])
        name = registry.get(number)
        if not name or number in seen or NATIONAL_BODY.search(name):
            continue
        tokens = set(pta.normalise(name))
        if pta.phases_conflict(school_phase, pta.phase_words(name)):
            continue
        if shared and not (school_tokens and school_tokens <= tokens):
            continue
        by_name = pta.is_parent_association(name)
        by_evidence = bool(tokens & school_tokens and EVIDENCE_WORDS.search(c.get("evidence") or "")
                           and not pta.NOT_PTA.search(name) and not NOT_PTA_NAME.search(name))
        if not (by_name or by_evidence):
            continue
        seen.add(number)
        entry = {"charity_number": number, "source_url": c.get("context_url") or "", "evidence": c.get("evidence") or ""}
        if tokens and school_tokens and not tokens & school_tokens:
            if c.get("pta_page"):
                foreign.append(entry)
        else:
            fitting.append(entry)
    return fitting or (foreign if len(foreign) == 1 else [])


def load_registry(path) -> dict[int, str]:
    """{registered charity number: name} of every main charity in the register extract, streamed once."""
    registry = {}
    for obj in pta.iter_json_array(path):
        if obj.get("linked_charity_number", 0) in (0, 1) and obj.get("registered_charity_number"):
            registry.setdefault(int(obj["registered_charity_number"]), obj.get("charity_name") or "")
    return registry


# --------------------------------------------------------------- fetching

class RateLimiter:
    """At most one request per interval per host; each caller reserves the next free slot."""

    def __init__(self, interval=HOST_INTERVAL, clock=time.monotonic, sleep=time.sleep):
        self.interval, self._clock, self._sleep = interval, clock, sleep
        self._next = {}
        self._lock = threading.Lock()

    def wait(self, host, interval=None) -> float:
        gap = max(self.interval, interval or 0)
        with self._lock:
            now = self._clock()
            at = max(now, self._next.get(host, now))
            self._next[host] = at + gap
        if at > now:
            self._sleep(at - now)
        return at


def _decode(body, charset) -> str:
    if not charset:
        m = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", body[:4096], re.I)
        charset = m.group(1).decode("ascii") if m else "utf-8"
    try:
        return body.decode(charset, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def http_get(url, headers, timeout):
    """The real transport: (status, final url, text). HTML and plain text only."""
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            body = resp.read(MAX_BYTES) if ("html" in ctype or "text" in ctype or not ctype) else b""
            return resp.status, resp.geturl(), _decode(body, resp.headers.get_content_charset())
    except urllib.error.HTTPError as err:
        return err.code, url, ""


class Fetcher:
    """Polite GETs: robots.txt per origin (cached), rate limit per host, one User-Agent.

    fetch(url, headers, timeout) -> (status, final_url, text) is injectable; tests pass a fake.
    """

    def __init__(self, fetch=http_get, limiter=None, user_agent=USER_AGENT, timeout=TIMEOUT):
        self.fetch, self.limiter = fetch, limiter or RateLimiter()
        self.user_agent, self.timeout = user_agent, timeout
        self.headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                        "Accept-Language": "en-GB,en;q=0.8"}
        self._robots, self._delay, self._locks = {}, {}, defaultdict(threading.Lock)
        self._unreachable = set()   # origins whose robots.txt failed or gave 5xx: retried on --resume
        self._lock = threading.Lock()
        self.stats = Counter()

    def _count(self, key):
        with self._lock:
            self.stats[key] += 1

    def _request(self, url):
        host = host_key(url)
        self.limiter.wait(host, self._delay.get(host))
        self._count("requests")
        return self.fetch(url, dict(self.headers), self.timeout)

    def robots(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            lock = self._locks[origin]
        with lock:
            if origin in self._robots:
                return self._robots[origin]
            rp = urllib.robotparser.RobotFileParser(origin + "/robots.txt")
            try:
                status, _, text = self._request(origin + "/robots.txt")
            except Exception:
                status, text = None, ""
            if status == 200:
                rp.parse(text.splitlines())
            elif status in (401, 403):
                rp.disallow_all = True
            elif status is None or status >= 500:
                rp.disallow_all = True   # unreachable or failing: leave the host alone this run
                self._unreachable.add(origin)
            else:
                rp.allow_all = True
            delay = rp.crawl_delay(self.user_agent) if status == 200 else None
            if delay:
                self._delay[host_key(url)] = min(float(delay), MAX_CRAWL_DELAY)
            self._robots[origin] = rp
            return rp

    def allowed(self, url) -> bool:
        return self.robots(url).can_fetch(self.user_agent, url)

    def get(self, url) -> Page:
        if not self.allowed(url):
            parts = urlsplit(url)
            if f"{parts.scheme}://{parts.netloc}" in self._unreachable:
                self._count("errors")
                return Page(url, "", "error")
            self._count("robots")
            return Page(url, "", "robots")
        try:
            status, final, text = self._request(url)
        except Exception:
            self._count("errors")
            return Page(url, "", "error")
        if not 200 <= (status or 0) < 300:
            self._count("errors")
            return Page(url, "", "error")
        return Page(final or url, text or "", "ok")


# ------------------------------------------------------------------ crawl

def crawl_site(start_url, fetcher, enough=None, max_pages=MAX_PAGES):
    """(candidates, pages fetched, homepage status) for one school website.

    Homepage, then its same-site PTA links (one level), then the PTA's own site; stops once
    enough(candidates) is true or max_pages pages have been requested.
    """
    candidates, visited = [], set()

    def visit(url, pta_page=None):
        """The page (its html parsed when it loaded), or None when over budget or already seen."""
        if len(visited) >= max_pages or url.rstrip("/") in visited:
            return None
        visited.add(url.rstrip("/"))
        page = fetcher.get(url)
        if page.status != "ok":
            return page
        parsed = parse(page.html)
        candidates.extend(extract_candidates(parsed, page.url, pta_page))
        return page._replace(html=parsed)

    def done():
        return enough is not None and enough(candidates)

    home = visit(start_url, pta_page=False)
    if home.status != "ok":
        return candidates, len(visited), home.status
    links = pta_links(home.html, home.url)
    queue = [link for link in links if not link.offsite]
    offsite = [link for link in links if link.offsite]
    while queue and len(visited) < max_pages and not done():
        if offsite and max_pages - len(visited) <= PTA_SITE_PAGES:
            break   # keep room for the PTA's own site
        page = visit(queue.pop(0).url, pta_page=True)
        if page and page.status == "ok":
            offsite += [link for link in pta_links(page.html, page.url)
                        if link.offsite and link.url not in {o.url for o in offsite}]
    if offsite and len(visited) < max_pages and not done():
        parts = urlsplit(offsite[0].url)
        page = visit(urlunsplit((parts.scheme, parts.netloc, "/", "", "")), pta_page=True)
        if page and page.status == "ok":
            for url in _about_links(page.html, page.url):
                if len(visited) >= max_pages or done():
                    break
                visit(url, pta_page=True)
    return candidates, len(visited), "ok"


def _open(school) -> bool:
    return "closed" not in str(school.get("status") or "").lower()


def select_schools(schools, urns=None, la=None, councils=None) -> list[dict]:
    """Open state schools with a website, optionally only some URNs or one council."""
    picked = []
    for s in schools:
        if not _open(s) or s.get("type_group") == "Independent schools" or not normalise_url(s.get("website")):
            continue
        if urns and str(s["urn"]) not in urns:
            continue
        if la and not (str(s.get("laestab") or "").startswith(la) or s.get("council") == (councils or {}).get(la)):
            continue
        picked.append(s)
    return picked


def split_widespread(found, limit=MAX_SHARED):
    """(kept, held): numbers on more than limit schools' sites are held back."""
    counts = Counter(h["charity_number"] for hits in found.values() for h in hits)
    kept, held = {}, {}
    for urn, hits in found.items():
        for h in hits:
            (held if counts[h["charity_number"]] > limit else kept).setdefault(urn, []).append(h)
    return kept, held


def state_path(out) -> Path:
    out = Path(out)
    return out.with_name(out.stem + ".state.json")


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def write_outputs(out, found, state):
    kept, held = split_widespread(found)
    now = datetime.now().isoformat(timespec="seconds")
    _atomic_write(out, {"generated": now, "user_agent": USER_AGENT,
                        "schools": {urn: kept[urn] for urn in sorted(kept)}})
    _atomic_write(state_path(out), {"generated": now, "no_pta": sorted(state["no_pta"]), "robots": sorted(state["robots"]),
                                    "failed": sorted(state["failed"] - set(found)), "held": held})


def load_progress(out):
    """(found, state) from an earlier run's output and state files."""
    found, state = {}, {"no_pta": set(), "robots": set(), "failed": set()}
    if Path(out).exists():
        found = {urn: list(hits) for urn, hits in json.loads(Path(out).read_text(encoding="utf-8"))["schools"].items()}
    if state_path(out).exists():
        saved = json.loads(state_path(out).read_text(encoding="utf-8"))
        for key in state:
            state[key] = set(saved.get(key, []))
        for urn, hits in saved.get("held", {}).items():
            found.setdefault(urn, []).extend(hits)
    return found, state


def run(schools, fetcher, registry, out, *, workers=MAX_WORKERS, found=None, state=None, shared=None, log=print):
    """Crawl every school (grouped by website, each site once) and write progress as it goes."""
    found = found if found is not None else {}
    state = state or {"no_pta": set(), "robots": set(), "failed": set()}
    shared = shared or Counter()
    groups = defaultdict(list)
    for s in schools:
        groups[site_key(normalise_url(s["website"]))].append(s)
    total, done, start = len(schools), 0, time.time()

    def task(group):
        url = normalise_url(group[0]["website"])
        if shared[site_key(url)] > 1:
            enough = None   # a shared site may name several schools' PTAs
        else:
            enough = lambda cands: any(pta.is_parent_association(registry.get(c["charity_number"])) for c in cands)  # noqa: E731
        return crawl_site(url, fetcher, enough)

    def record(group, result):
        candidates, _, status = result
        for s in group:
            urn = str(s["urn"])
            accepted = validate(candidates, registry, s.get("name"), shared[site_key(normalise_url(s["website"]))] > 1)
            for key in state:
                state[key].discard(urn)
            if accepted:
                found[urn] = accepted
            else:
                found.pop(urn, None)
                state["no_pta" if status == "ok" else status if status == "robots" else "failed"].add(urn)

    pool = ThreadPoolExecutor(max_workers=max(1, min(workers, MAX_WORKERS)))
    try:
        futures = {pool.submit(task, group): group for group in groups.values()}
        for future in as_completed(futures):
            group = futures[future]
            try:
                result = future.result()
            except Exception:
                result = ([], 0, "error")
            record(group, result)
            before, done = done, done + len(group)
            if before // SAVE_EVERY != done // SAVE_EVERY:
                write_outputs(out, found, state)
            if before // LOG_EVERY != done // LOG_EVERY:
                log(f"{done:,}/{total:,} schools, {len(found):,} with a PTA number, {fetcher.stats['requests']:,} requests, "
                    f"{fetcher.stats['errors']:,} errors, {fetcher.stats['robots']:,} robots-blocked ({time.time() - start:.0f}s)")
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        write_outputs(out, found, state)
    pool.shutdown()
    kept, held = split_widespread(found)
    log(f"done: {done:,} schools crawled, {len(kept):,} with a PTA number ({sum(map(len, kept.values())):,} charities), "
        f"{len(held):,} held as shared, {len(state['no_pta']):,} none found, {len(state['robots']):,} robots-blocked, "
        f"{len(state['failed']):,} unreachable; {fetcher.stats['requests']:,} requests ({time.time() - start:.0f}s)")
    return found, state


def main(argv=None, *, fetcher=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site-data", type=Path, default=SITE_DATA)
    parser.add_argument("--charity-dir", type=Path, default=CHARITY_DIR)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--limit", type=int, help="crawl at most this many schools")
    parser.add_argument("--resume", action="store_true", help="skip schools already in the output or state file")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"threads (at most {MAX_WORKERS})")
    parser.add_argument("--urns", help="comma-separated URNs")
    parser.add_argument("--la", help="one council code, e.g. 204")
    args = parser.parse_args(argv)

    every = [s for s in pta.load_schools(args.site_data) if _open(s) and normalise_url(s.get("website"))]
    shared = Counter(site_key(normalise_url(s["website"])) for s in every)
    las = args.site_data / "england/las.json"
    councils = ({str(la["la_code"]): la["name"] for la in json.loads(las.read_text(encoding="utf-8")).get("las", [])}
                if las.exists() else {})
    urns = {u.strip() for u in args.urns.split(",") if u.strip()} if args.urns else None
    schools = select_schools(every, urns, args.la, councils)
    found, state = load_progress(args.out) if args.resume else ({}, None)
    if args.resume:
        skip = set(found) | state["no_pta"] | state["robots"]
        schools = [s for s in schools if str(s["urn"]) not in skip]
    if args.limit is not None:
        schools = schools[:args.limit]
    print(f"{len(schools):,} schools to crawl ({len(found):,} already found)", flush=True)
    registry = load_registry(args.charity_dir / "publicextract.charity.json")
    print(f"{len(registry):,} charities in the register", flush=True)
    run(schools, fetcher or Fetcher(), registry, args.out, workers=args.workers, found=found, state=state,
        shared=shared, log=lambda line: print(line, flush=True))


if __name__ == "__main__":
    main()
