"""Find parents' association charity numbers on school websites, politely.

For each open state school with a website, reads at most six pages, in priority order: the homepage,
the school's own PTA / Friends pages (or a Parents / Community hub page when the homepage has no PTA
link), one level of PTA sub-pages, and the PTA's own site with one about/contact page. A number is kept
only when, in this order, it is in the Charity Commission register, the register name reads as a
parents' association, PTA wording sits within 400 characters of it, and the charity agrees with the
school (a shared name word, its postcode, or its website on a domain crawled for the school). Numbers
failing only that last step go to pta_crawl_review.json for a person to check; it is never merged.
Accepted numbers go to pta_crawl.json for pta.py to merge with method "website-crawl".

Polite by construction: robots.txt is honoured per host (and for every redirect hop, which is followed
by hand), every request carries a User-Agent naming the project, no host sees more than one request a
second (or its Crawl-delay) and no IP more than two, WAF and captcha pages count as refusals, and the
crawl stops handing out schools on SIGINT/SIGTERM. Each finished school is journalled to
pta_crawl.results.jsonl; the outputs are rebuilt from the journal, so --resume picks up where it stopped.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import random
import re
import signal
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections import Counter, defaultdict, deque, namedtuple
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from heapq import heappop, heappush
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from pipeline.money import pta

MAIN = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
CHARITY_DIR = MAIN / "pipeline/.cache/charity"
SITE_DATA = MAIN / "site/data"
OUT = MAIN / "pipeline/.cache/money/pta_crawl.json"
USER_AGENT = "SchoolsInReach-research/1.0 (+https://www.schoolsinreach.com/about.html)"
CRAWL_VERSION = 2        # bump when the crawl rules change, so --resume re-crawls older results
MAX_WORKERS = 24
HOST_INTERVAL = 1.0      # seconds between requests to one host
IP_INTERVAL = 0.5        # and to one IP: two requests a second however many school sites it serves
MAX_CRAWL_DELAY = 30.0   # a robots.txt Crawl-delay is honoured up to this in the main pass...
SLOW_MAX_DELAY = 600.0   # ...and up to this in the slow lane; a longer one is a refusal
TIMEOUT = 10
RETRY_TIMEOUT = 20       # one more try, after the main pass, for homepages that timed out
MAX_PAGES = 6            # HTML pages per school; robots.txt and redirect hops are requests, not pages
MAX_REDIRECTS = 5
MAX_BYTES = 2_000_000
MAX_SCRIPT = 500_000     # script text kept per page, for Wix-style JSON and JSON-LD
CHALLENGE_BYTES = 8000
ROBOTS_TTL = 24 * 3600
LOG_EVERY = 500
MAX_SHARED = 4           # a number on more schools' sites than this is an umbrella body, held back
NEAR = 120               # a bare number (no 'charity' wording) must sit this close to PTA wording
TERM_NEAR = 400          # PTA wording must sit this close to any accepted number
SEED = 20261107          # crawl order: shuffled, because platforms cluster by council

# Pages a school's crawl may fetch, per kind, after the homepage (crawl_spec §2).
CAP = {"pta": 3, "pta_sub": 2, "offsite_home": 1, "offsite_about": 1, "hub": 1}
PTA_KINDS = {"pta", "pta_sub", "offsite_home", "offsite_about"}
# Journal outcomes that --resume skips; the rest (error, incomplete, slow, crawler_error) are re-crawled.
FINAL = {"hit", "no_pta", "review_only", "robots", "blocked"}

# ----------------------------------------------------------------- words

_EDGE_L, _EDGE_R = r"(?<![a-z0-9])", r"(?![a-z0-9])"
ACRONYMS = r"(?:pta|ptfa|ptsa|pfa|psa|hsa)"
# Wording that marks a parents' association closely enough to anchor a bare number.
PTA_WORDS = re.compile(
    _EDGE_L + ACRONYMS + _EDGE_R + r"|\bfriends[\s_-]+of\b|\bparents?['’]?[\s_-]+(?:and[\s_-]+(?:teachers?|friends)[\s_-]+)?"
    r"association\b|\bparent[\s_/-]*(?:teacher|staff)\b|\bhome[\s_-]+school[\s_-]+association\b", re.I)
# PTA wording an accepted number needs within TERM_NEAR characters; also read in link text.
PTA_TERMS = re.compile(
    r"\b(?:p\.?t\.?a|p\.?t\.?f\.?a|pfa|psa|hsa|fsa|ptsa|fofs?)\b|\bfriends\b|parents?['’]?\s*(?:and|&)\s*friends|"
    r"parent[s'’]*\s*(?:teacher|staff)|parents?['’]?\s+(?:association|council|forum)|famil(?:y|ies)\s+(?:and|&)\s+staff|"
    r"home[\s-]+school\s+association|school\s+association", re.I)
# A host that is itself a PTA's site: williampattenptfa.org.uk, friendsofx.org, x-pta.co.uk.
PTA_HOST = re.compile(r"^" + ACRONYMS + r"|" + ACRONYMS + r"$|friendsof|parents?association|parentteacher", re.I)
# Link heuristics, on a link's path and query (and on its host with dots read as slashes).
PTA_HREF = re.compile(r"(?:^|[/_.=-])(?:pta|ptfa|pfa|psa|hsa|fsa|ptsa|fos|fofs)(?:$|[/_.?#=+-])|"
                      r"(?:^|[/_.=-])friends(?:-?of)?(?:$|[/_.?#=+-])|friendsof|friends\+of|parents?-?(?:and-?)?friends|"
                      r"parent-?teacher|parents?-?association|parent-?staff", re.I)
HUB_TEXT = re.compile(r"^\s*(?:our\s+)?(?:parents?|parent\s+(?:information|info|zone|area|hub|portal)|"
                      r"parents?['’]?\s+(?:area|zone|corner|information|info|hub|page|section)|for\s+parents|"
                      r"information\s+for\s+parents|community|get\s+involved|fundraising|"
                      r"support\s+(?:us|the\s+school|our\s+school)|how\s+(?:you\s+)?can\s+(?:you\s+)?help)\s*$", re.I)
HUB_HREF = re.compile(r"(?:^|/)(?:parents?|parent-information|parents-area|parent-zone|for-parents|community|"
                      r"get-involved|fundraising)/?$", re.I)
ABOUT_TEXT = re.compile(r"\b(?:about|who\s+we\s+are|contact|committee|charity|constitution|privacy|meet\s+the|"
                        r"our\s+team|the\s+team)\b", re.I)
ABOUT_HREF = re.compile(r"(?:^|/)(?:about|about-us|who-we-are|contact|contact-us|committee|meet-the-(?:team|committee)|"
                        r"charity|constitution|privacy)|event=your-organisation", re.I)
OFFSITE_WEBSITE_TEXT = re.compile(r"\b(?:our|the|their|pta|ptfa|friends['’]?)\s+(?:own\s+)?web\s?site\b|"
                                  r"\bvisit\s+(?:the|our)\b", re.I)
LOW_VALUE = re.compile(r"\b(?:news|newsletter|event|events|calendar|minutes|uniform|shop|lottery|disco|fair|raffle|"
                       r"gallery|photos?|blog)\b", re.I)

# 'Registered charity no. 1103834', 'Charity Reg. No 289123', 'CIO no. 1190000', 'registered with the Charity
# Commission (no. 1185555)'; the reverse '1112223 (registered charity)'. A gap naming something else vetoes it.
CHARITY_FWD = re.compile(
    r"(?P<kw>\bregistered\s+charit(?:y|able)|\bcharit(?:y|able)|\bc\.?\s?i\.?\s?o\b|charity\s+commission)"
    r"(?P<gap>[^0-9]{0,80}?)(?<!\d)(?P<num>[1-9]\d{5,6})(?!\d)", re.I)
CHARITY_REV = re.compile(r"(?<!\d)(?P<num>[1-9]\d{5,6})(?!\d)(?P<gap>[\s(:\-–]{0,6}(?:is\s+an?\s+)?)"
                         r"(?P<kw>registered\s+charity)", re.I)
GAP_VETO = re.compile(r"compan|\btel\b|phone|fax|\bvat\b|ofsted|\burn\b|dfe|laestab|\bukprn\b|postcode|"
                      r"registered\s+office", re.I)
# Links to the register that carry the number itself.
CC_LINK = re.compile(r"charitycommission\.gov\.uk/.*?(?:charity-details/|charity-search/-/charity-details/|"
                     r"registeredcharitynumber=|regid=|/charity/)(\d{6,7})\b", re.I)
REGISTER_LINK = re.compile(r"(?:regid=|registeredcharitynumber=|gb-chc-)(\d{6,7})(?!\d)", re.I)
BARE_NO = re.compile(r"(?<![\w£$€/=#.-])(\d{6,7})(?![\w/=-]|[.,]\d)")
# Numbers that are something else, blanked before looking for bare numbers.
PHONE = re.compile(r"(?:\+\s?44\s?(?:\(0\)\s?)?|(?<!\d)0)\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?!\d)")
LABELLED = re.compile(r"\b(?:urn|ofsted|dfe|laestab|ukprn|company|vat|tel|telephone|phone|fax|mobile|ref|reference)\b"
                      r"[^\d]{0,25}\d[\d ]{5,9}", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Register names: which read as a parents' association (crawl_spec §5 tiers), and which never do.
NATIONAL_BODY = re.compile(r"\b(?:national|confederation|parentkind|associations)\b", re.I)
NOT_PTA_NAME = re.compile(r"\b(?:trust|trustees|foundation|diocese|diocesan|endowment|parish|church|chapel|almshouses?)\b", re.I)
BROAD_NAME = re.compile(r"\b(?:friends|parents?|supporters|association|fund|society|committee)\b", re.I)
BROAD_VETO = re.compile(r"pre\s*-?\s*school|supplementary|carers?\b|parent\s+and\s+(?:child|toddler)|\bchurch\b|parish|"
                        r"sunday|\bmusic|\bband\b|orchestra|choir|sport|swim|minibus|bursar|scholarship|alumni|"
                        r"old\s+(?:boys|girls)|foster|adopt|deaf|blind|disab|autis|bereave", re.I)
ACTIVITY_PARENTS = re.compile(r"\bparents?\b|\bp\.?t\.?a\b|\bptfa\b|\bfriends\s+of\b", re.I)
ACTIVITY_MONEY = re.compile(r"fund|rais|event|social|donat|equipment|resources", re.I)
ACTIVITY_SCHOOL = re.compile(r"\bschool|\bpupil|\bacademy|\bchildren", re.I)
WEB_NAME = re.compile(r"\bfriends\b|\bparents?\b|famil(?:y|ies)\s*(?:and|&)\s*staff|\bsupporters\b|"
                      r"\b(?:pta|ptfa|pfa|psa|hsa|fsa|ptsa|fos|fofs)\b|\bp\.\s?t\.\s?a\b|\bschool\s+(?:association|society)\b",
                      re.I)
WEB_VETO = re.compile(r"\bchurch\b|chapel|parish|hospital|hospice|library|museum|cathedral|abbey|theatre|wildlife|"
                      r"nature|village\s+hall|community\s+cent|scouts?\b|guides?\b|\bpark\s+trust|railway|canal|"
                      r"\bearth\b|refugee|overseas|africa|india|kenya|uganda|gambia|nepal|romania|league\s+of\s+friends|"
                      r"society\s+of\s+friends|medical|health|graveyard|cemetery|monument|handicap|mental|\bschool\s+fund\b",
                      re.I)

# Never fetched (crawl_spec §3).
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "whatsapp:", "fax:", "callto:")
SKIP_EXT = re.compile(r"\.(?:pdf|docx?|xlsx?|pptx?|jpe?g|png|gif|svg|webp|zip|mp4|mp3|mov|ics|csv|rtf|odt|ods)$", re.I)
DOC_PATH = re.compile(r"/attachments/|documents?\.asp|/download|getfile|file\.aspx|/uploads/|/media/|/storage/|/docs/|"
                      r"[?&](?:file|attachment|download)=", re.I)
NO_FOLLOW = {
    # social
    "facebook.com", "fb.com", "fb.me", "twitter.com", "twitter.co.uk", "x.com", "instagram.com", "youtube.com",
    "youtu.be", "linkedin.com", "tiktok.com", "pinterest.com", "flickr.com", "vimeo.com", "wa.me", "whatsapp.com",
    "threads.net",
    # login walls and school systems
    "classlist.com", "weduc.co.uk", "schoolcomms.com", "arbor-education.com", "arbor.sc", "parentmail.co.uk",
    "schoolgateway.com", "school-gateway.co.uk", "wonde.com",
    # payment, donations and tickets
    "parentpay.com", "scopay.com", "schoolmoney.co.uk", "justgiving.com", "easyfundraising.org.uk", "paypal.com",
    "paypal.me", "gofundme.com", "givey.com", "localgiving.org", "givealittle.co.uk", "giveasyoulive.com",
    "totalgiving.co.uk", "virginmoneygiving.com", "donorbox.org", "crowdfunder.co.uk", "givebutter.com", "sumup.com",
    "sumup.co.uk", "stripe.com", "square.site", "ticketsource.co.uk", "ticketsource.com", "tickettailor.com",
    "eventbrite.co.uk", "eventbrite.com", "jumblebee.co.uk", "yourschoollottery.co.uk", "amazon.co.uk", "amazon.com",
    # big platforms and government
    "google.com", "google.co.uk", "goo.gl", "forms.gle", "microsoft.com", "office.com", "sharepoint.com", "live.com",
    "apple.com", "spotify.com", "zoom.us", "gov.uk", "parentkind.org.uk",
    # shorteners, documents and mailing lists
    "bit.ly", "tinyurl.com", "linktr.ee", "issuu.com", "padlet.com", "canva.com", "calameo.com", "dropbox.com",
    "list-manage.com", "mailchimp.com", "signupgenius.com", "doodle.com",
}
# Shared hosts whose PTA mini-sites ARE followed; on these a site is its own host, not the platform.
PLATFORMS = {"sites.google.com", "pta-events.co.uk", "ptaevents.co.uk", "pta-events.com", "wixsite.com", "weebly.com",
             "wordpress.com"}
UK_SLD = {"co.uk", "org.uk", "ac.uk", "gov.uk", "ltd.uk", "me.uk", "net.uk", "plc.uk", "sch.uk", "nhs.uk", "police.uk"}
# WAF / captcha / bot-check pages (SiteGround sgcaptcha, Cloudflare, Incapsula, Sucuri...).
CHALLENGE = re.compile(r"just a moment|checking your browser|attention required|cf-browser-verification|cf_chl|"
                       r"challenge-platform|sgcaptcha|_incapsula_resource|request unsuccessful|sucuri website firewall|"
                       r"ddos protection|access denied", re.I)
CHALLENGE_STATUS = {202, 403, 429, 503}

SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}

Page = namedtuple("Page", "url html status err", defaults=(None,))   # status: ok | robots | blocked | slow | error
Link = namedtuple("Link", "priority url kind depth")
Charity = namedtuple("Charity", "name status removed tier postcode web")
Verdict = namedtuple("Verdict", "accepted review rejects")
SiteCrawl = namedtuple("SiteCrawl", "candidates pages status trail incomplete domains deferred tls_unverified")
Robots = namedtuple("Robots", "parser verdict status delay")          # verdict: rules | allow | deny | error


class Stopped(BaseException):
    """A slow-lane wait cut short by a stop request; the school is dropped unjournalled and re-crawled later."""


def plausible_number(n) -> bool:
    """Registered charity numbers run 200000-999999 (older) and 1000000-1299999; Ofsted URNs sit below."""
    return 200_000 <= n < 1_300_000


def host_key(url) -> str:
    host = (urlsplit(url).hostname or "").lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def base_domain(host) -> str:
    """Registrable domain: the last two labels, three for *.co.uk and the like, four for *.<la>.sch.uk."""
    host = (host or "").lower().strip(".")
    host = host[4:] if host.startswith("www.") else host
    parts = host.split(".")
    if len(parts) >= 4 and ".".join(parts[-2:]) == "sch.uk":
        return ".".join(parts[-4:])
    if len(parts) >= 3 and ".".join(parts[-2:]) in UK_SLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _under(host, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def site_of(host) -> str:
    """The site a host belongs to: its registrable domain, or on a PTA platform the host itself."""
    host = (host or "").lower().strip(".")
    host = host[4:] if host.startswith("www.") else host
    return host if _under(host, PLATFORMS) else base_domain(host)


def no_follow(host) -> bool:
    return not _under(host, PLATFORMS) and _under(host, NO_FOLLOW)


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


def norm_url(url) -> str:
    """Lower-case scheme and host, no fragment, stray spaces and non-ASCII in the path and query percent-encoded."""
    parts = urlsplit(url.strip())
    netloc = parts.netloc.lower()
    try:
        netloc.encode("ascii")
    except UnicodeEncodeError:
        netloc = netloc.encode("idna").decode("ascii")
    safe = "/%:@!$&'()*+,;=-._~"
    return urlunsplit((parts.scheme.lower(), netloc, quote(parts.path or "/", safe=safe), quote(parts.query, safe=safe + "?"), ""))


def site_key(url) -> str:
    """Two register entries pointing at the same site share a key; a query string makes a different page."""
    parts = urlsplit(url)
    key = host_key(url) + parts.path.rstrip("/").lower()
    return key + "?" + parts.query.lower() if parts.query else key


def toggle_www(url) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc[4:] if parts.netloc.startswith("www.") else "www." + parts.netloc
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


def never_fetch(url) -> str | None:
    """Why a URL is never fetched (crawl_spec §3), or None."""
    parts = urlsplit(url)
    host = host_key(url)
    if parts.scheme not in ("http", "https"):
        return "scheme"
    if "." not in host:
        return "host"
    if "charitycommission" in host:
        return "register"
    if no_follow(host):
        return "no_follow"
    if SKIP_EXT.search(parts.path):
        return "file"
    if DOC_PATH.search(parts.path + ("?" + parts.query if parts.query else "")):
        return "document"
    return None


# ------------------------------------------------------------------- html

class _Text:
    """Visible text with whitespace squashed as it is built, so offsets match the text the patterns run on."""

    def __init__(self):
        self.parts, self.size, self._gap = [], 0, False

    def gap(self):
        self._gap = self.size > 0

    def add(self, data):
        for word in re.findall(r"\S+|\s+", data):
            if word[0].isspace():
                self.gap()
                continue
            if self._gap:
                self.parts.append(" ")
                self.size += 1
                self._gap = False
            self.parts.append(word)
            self.size += len(word)

    def value(self) -> str:
        return "".join(self.parts)


class _Parser(HTMLParser):
    """Visible text with footer spans, script text, links with their text offset, title, and the meta tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.script, self.links, self.title, self.spans = _Text(), [], [], [], []
        self.base = self.refresh = None
        self.robots = ""
        self._skip = self._scripts = self._script_size = 0
        self._footer = None   # [tag, depth, start] while inside a footer
        self._link = None     # [href, [text], start] while inside <a>
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = {k: v or "" for k, v in attrs}
        self.text.gap()
        if tag in SKIP_TAGS:
            self._skip += 1
            self._scripts += tag == "script"
        elif tag == "title":
            self._in_title = True
        elif tag == "base" and attrs.get("href") and self.base is None:
            self.base = attrs["href"].strip()
        elif tag == "meta":
            if attrs.get("name", "").lower() == "robots":
                self.robots = attrs.get("content", "").lower()
            m = re.search(r"url\s*=\s*['\"]?([^'\";]+)", attrs.get("content", ""), re.I)
            if attrs.get("http-equiv", "").lower() == "refresh" and m and self.refresh is None:
                self.refresh = m.group(1).strip()
        marker = (attrs.get("id", "") + " " + attrs.get("class", "")).lower()
        if self._footer and tag == self._footer[0]:
            self._footer[1] += 1
        elif self._footer is None and (tag == "footer" or attrs.get("role") == "contentinfo"
                                       or (tag in ("div", "section") and "footer" in marker)):
            self._footer = [tag, 1, self.text.size]
        if tag == "a" and attrs.get("href"):
            self._link = [attrs["href"], [attrs.get("title", ""), attrs.get("aria-label", "")], self.text.size]
        elif tag == "img" and self._link:
            self._link[1].append(attrs.get("alt", ""))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        self.text.gap()
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
            if tag == "script" and self._scripts:
                self._scripts -= 1
        elif tag == "title":
            self._in_title = False
        if self._footer and tag == self._footer[0]:
            self._footer[1] -= 1
            if not self._footer[1]:
                self.spans.append((self._footer[2], self.text.size))
                self._footer = None
        if tag == "a" and self._link:
            href, label, start = self._link
            self.links.append((href, _squash(" ".join(label)), start))
            self._link = None

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
            return
        if self._skip:
            if self._scripts and self._script_size < MAX_SCRIPT:
                self.script.append(data)
                self._script_size += len(data)
            return
        self.text.add(data)
        if self._link:
            self._link[1].append(data)


Parsed = namedtuple("Parsed", "text footer links title spans script base refresh robots")


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
    text = p.text.value()
    spans = [(min(s, len(text)), min(e, len(text))) for s, e in p.spans]
    if p._footer:
        spans.append((min(p._footer[2], len(text)), len(text)))
    tail_at = int(len(text) * 0.8)
    footer = _squash(" ".join(text[s:e] for s, e in spans) + " " + text[tail_at:]) if spans else text[tail_at:]
    return Parsed(text, footer, p.links, _squash(" ".join(p.title)), spans + [(tail_at, len(text))],
                  "\n".join(p.script), p.base, p.refresh, p.robots)


def footer_text(html) -> str:
    """Text of the page's <footer> (or footer div) plus the last 20% of its visible text."""
    return parse(html).footer


def _redact(text) -> str:
    """Volunteers' emails and phone numbers taken out."""
    return PHONE.sub("[phone]", EMAIL.sub("[email]", text))


def _term_near(text, start, end, window=TERM_NEAR):
    """The PTA wording nearest a number, within window characters either side, or None."""
    best = None
    for m in PTA_TERMS.finditer(text, max(0, start - window)):
        if m.start() > end + window:
            break
        distance = start - m.end() if m.end() <= start else max(0, m.start() - end)
        if best is None or distance < best[0]:
            best = (distance, m)
    return best[1] if best else None


def _evidence(text, start, end, term=None, before=140, after=100, cap=300) -> str:
    """The text around a number (140 characters before its keyword, 100 after it), always holding its PTA wording."""
    lo, hi = max(0, start - before), min(len(text), end + after)
    lo = max(lo, hi - cap)
    core = text[lo:hi]
    if term is not None and not (lo <= term.start() and term.end() <= hi):
        context = text[max(0, term.start() - 40):term.end() + 40]
        core = f"{context} … {core}" if term.start() < lo else f"{core} … {context}"
    return _redact(_squash(core))


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


def extract_candidates(html, base_url, pta_page=None, *, kind=None) -> list[dict]:
    """Charity numbers on one page (crawl_spec §4): 'registered charity no.' phrasings either way round in the
    visible text and the script text, links to the register, bare numbers within NEAR characters of PTA
    wording, and on PTA pages bare numbers in the footer.

    Each candidate is {"charity_number", "evidence", "context_url", "pta_page", "page_kind", "where",
    "pta_term"}; pta_term is the PTA wording within TERM_NEAR characters of the number, or None.
    """
    page = parse(html)
    if pta_page is None:
        pta_page = is_pta_page(base_url, page.title)
    found = {}

    def where_in(start, default):
        return "footer" if default == "body" and any(s <= start < e for s, e in page.spans[:-1]) else default

    def add(number, where, term, evidence):
        n = int(number)
        if not plausible_number(n):
            return
        old = found.get(n)
        if old is None or (old["pta_term"] is None and term is not None):
            found[n] = {"charity_number": n, "evidence": evidence, "context_url": base_url, "pta_page": bool(pta_page),
                        "page_kind": kind, "where": where, "pta_term": term.group(0) if term else None}

    vetoed = set()   # numbers whose wording says they are a company, phone or office number
    for stream, where in ((page.text, "body"), (page.script, "script")):
        for rx in (CHARITY_FWD, CHARITY_REV):
            for m in rx.finditer(stream):
                if GAP_VETO.search(m.group("gap")):
                    vetoed.add((where, m.start("num")))
                    continue
                start, end = m.start("num"), m.end("num")
                term = _term_near(stream, start, end)
                add(m.group("num"), where_in(start, where), term, _evidence(stream, min(m.start(), start), end, term))
    for href, label, at in page.links:
        target = unquote(href)
        m = CC_LINK.search(target) or REGISTER_LINK.search(target)
        if m:
            term = PTA_TERMS.search(label) or _term_near(page.text, at, at)
            context = _evidence(page.text, at, at, None if term and term.string is label else term, 160, 80)
            add(m.group(1), "cc_link", term, _squash(f"link to the charity register: {_redact(label)} | {context}"))
    text = page.text
    marks = [m.span() for m in PTA_WORDS.finditer(text)]
    footer = page.spans if pta_page else []
    for m in BARE_NO.finditer(_blank(text)):
        start, end = m.span()
        if ("body", start) in vetoed:
            continue
        near = any(s - NEAR <= end and start <= e + NEAR for s, e in marks)
        if near or any(s <= start < e for s, e in footer):
            term = _term_near(text, start, end)
            add(m.group(1), where_in(start, "body"), term, _evidence(text, start, end, term))
    return list(found.values())


# ------------------------------------------------------------------- links

def _pta_host(host) -> bool:
    return bool(PTA_HREF.search(host.replace(".", "/")) or any(PTA_HOST.search(p) for p in re.split(r"[.-]", host)))


def _clearly_pta(label, home_host) -> bool:
    """Link text that names a PTA: an acronym or 'parents association' outright; 'Friends of ...' only
    when it names a school or the school's own site name ('Friends of the Earth' is not a PTA)."""
    m = PTA_TERMS.search(label)
    if not m:
        return False
    if not m.group(0).lower().startswith("friends") or PTA_TERMS.search(label, m.end()):
        return True
    letters = re.sub(r"[^a-z]", "", home_host)
    tokens = pta.normalise(label)
    return bool(pta.SCHOOL_WORDS.search(label) or (tokens and all(t in letters for t in tokens)))


def _link_url(base, href) -> str | None:
    href = (href or "").strip()
    if not href or href.startswith("#") or href.lower().startswith(SKIP_SCHEMES):
        return None
    url = urljoin(base, href).split("#")[0]
    if never_fetch(url):
        return None
    return norm_url(url)


def link_candidates(html, page_url, kind="home", depth=0, site=None, pta_sites=(), school_host=None) -> list[Link]:
    """Links on one page worth fetching, as Link(priority, url, kind, depth); lower priority goes first.

    Same-site PTA links from the homepage or a hub page are 'pta', and from a 'pta' page 'pta_sub'. A link
    to another site whose host says PTA (fetched at that site's front page), or whose text clearly names a
    PTA and points at a site's front or one page, is 'offsite_home'; that site's about / contact / charity
    page is 'offsite_about'. Parents / Community / Fundraising pages are 'hub'. News, events, shop and
    gallery links sink to the back.
    """
    page = parse(html)
    base = urljoin(page_url, page.base) if page.base else page_url
    site = site or site_of(host_key(page_url))
    school_host = school_host or host_key(page_url)
    pta_sites = set(pta_sites)
    out, seen = [], {page_url.rstrip("/")}
    for href, label, _ in page.links:
        url = _link_url(base, href)
        if not url or url.rstrip("/") in seen:
            continue
        host = host_key(url)
        parts = urlsplit(url)
        same, on_pta_site = site_of(host) == site, site_of(host) in pta_sites
        text_hit = bool(PTA_TERMS.search(label))
        href_hit = bool(PTA_HREF.search(unquote(parts.path + ("?" + parts.query if parts.query else ""))))
        target, new = url, None
        if same and kind in ("home", "hub") and (text_hit or href_hit):
            new = (10 if kind == "home" else 30, "pta", depth + 1)
        elif same and kind == "pta" and depth < 2 and (text_hit or href_hit):
            new = (25, "pta_sub", depth + 1)
        elif not same and not on_pta_site and kind in ("home", "hub", "pta", "pta_sub"):
            shallow = "/" not in parts.path.strip("/") and not parts.query
            if _pta_host(host):
                if not _under(host, PLATFORMS):
                    target = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
                new = (15, "offsite_home", 1)
            elif shallow and (_clearly_pta(label, school_host)
                              or (kind == "pta" and OFFSITE_WEBSITE_TEXT.search(label))):
                new = (15, "offsite_home", 1)
        elif kind == "offsite_home" and on_pta_site and (ABOUT_TEXT.search(label) or ABOUT_HREF.search(parts.path + "?" + parts.query)):
            new = (20 - bool(re.search(r"charity|about", label, re.I)), "offsite_about", 2)
        elif same and kind == "home" and (HUB_TEXT.search(label) or HUB_HREF.search(parts.path)):
            new = (35, "hub", 1)
        if new is None or target.rstrip("/") in seen:
            continue
        seen.update({url.rstrip("/"), target.rstrip("/")})
        priority, link_kind, link_depth = new
        if link_kind in ("pta", "pta_sub", "offsite_home"):
            tpath = urlsplit(target).path
            score = 3 * text_hit + 2 * bool(PTA_HREF.search(unquote(tpath))) + (0 < len(label) <= 25)
            priority -= score - 30 * bool(LOW_VALUE.search(label + " " + unquote(tpath)))
        out.append(Link(priority, target, link_kind, link_depth))
    return out


def pta_links(html, base_url) -> list[Link]:
    """The links a crawl would queue from a school homepage, best first; hub pages only when there is no PTA link."""
    links = link_candidates(html, base_url, "home", 0)
    if any(link.kind == "pta" for link in links):
        links = [link for link in links if link.kind != "hub"]
    order = {id(link): i for i, link in enumerate(links)}
    return sorted(links, key=lambda link: (link.priority, order[id(link)]))


# ------------------------------------------------------------- validation

def charity_tier(name, activities=None) -> str | None:
    """How a register name reads as a parents' association: 'strict' (pta.is_parent_association), 'broad'
    (a supporters' word in a school-like name, with activities about parents raising money for a school),
    'web' (a supporters' word, minus churches, hospitals and the like), or None."""
    name = str(name or "")
    if not name or NATIONAL_BODY.search(name):
        return None
    if pta.is_parent_association(name):
        return "strict"
    if pta.NOT_PTA.search(name) or BROAD_VETO.search(name):
        return None
    school_like = pta.SCHOOL_WORDS.search(name) or pta.WEAK_MARKERS.search(name)
    act = str(activities or "")
    if (BROAD_NAME.search(name) and school_like and ACTIVITY_PARENTS.search(act) and ACTIVITY_MONEY.search(act)
            and ACTIVITY_SCHOOL.search(act)):
        return "broad"
    if WEB_NAME.search(name) and (pta.SCHOOL_WORDS.search(name) or not (WEB_VETO.search(name) or NOT_PTA_NAME.search(name))):
        return "web"
    return None


def _info(value) -> Charity | None:
    """A registry value as a Charity; a bare name (as in hand-built registries) carries no postcode or website."""
    if value is None or isinstance(value, Charity):
        return value
    if isinstance(value, dict):
        tier = charity_tier(value.get("charity_name"), value.get("charity_activities"))
        return Charity(value.get("charity_name") or "", value.get("charity_registration_status"),
                       (value.get("date_of_removal") or "")[:10] or None, tier,
                       pta.norm_postcode(value.get("charity_contact_postcode")), pta.domain(value.get("charity_contact_web")))
    return Charity(str(value), None, None, charity_tier(value), None, None)


def _first_term(text):
    m = PTA_TERMS.search(text or "")
    return m.group(0) if m else None


def _judge(c, number, registry, tokens, phase, postcode, domains, shared):
    """(2 accepted | 1 review | 0 rejected, entry) for one candidate."""
    url, evidence = c.get("context_url") or c.get("source_url") or "", c.get("evidence") or ""
    info = _info(registry.get(number))

    def reject(reason):
        return 0, {"charity_number": number, "source_url": url, "reason": reason, "cc_name": info.name if info else None}

    if info is None:
        return reject("not_in_register")
    if not info.tier:
        return reject("not_pa_like")
    if pta.phases_conflict(phase, pta.phase_words(info.name)):
        return reject("phase_conflict")
    term = c["pta_term"] if "pta_term" in c else _first_term(evidence)
    if not term:
        return reject("no_pta_term_near")
    charity_tokens = set(pta.normalise(info.name))
    agrees = ["name:" + ",".join(sorted(tokens & charity_tokens))] if tokens & charity_tokens else []
    if postcode and info.postcode == postcode:
        agrees.append("postcode")
    if info.web and site_of(info.web) in domains:
        agrees.append("domain")
    if not tokens and not agrees and _first_term(evidence):
        agrees.append("pta_evidence")   # nothing of the school's name to compare: explicit PTA wording decides
    entry = {"charity_number": number, "source_url": url, "evidence": evidence,
             "meta": {"where": c.get("where"), "page_kind": c.get("page_kind"), "pta_term": term, "cc_name": info.name,
                      "cc_status": info.status, "cc_removed": info.removed, "pa_tier": info.tier, "agrees": agrees}}
    if shared and tokens and not tokens <= charity_tokens:
        return 1, dict(entry, reason="shared_site_other_school")
    if not agrees:
        return 1, dict(entry, reason="no_agreement")
    return 2, entry


def classify(candidates, registry, school=None, *, shared=False, domains=()) -> Verdict:
    """Sort candidates into Verdict(accepted, review, rejects), checking in crawl_spec §5 order: in the register,
    a parents'-association-like name (no umbrella bodies, no phase clash), PTA wording near the number, then
    agreement with the school (a shared name word, its postcode, or the charity's website on a domain crawled
    for it). Failing only agreement means review. On a site several schools share, a name must carry this
    school's whole name. A number found several times keeps its best result."""
    school = school if isinstance(school, dict) else ({"name": school} if school else {})
    name = school.get("name")
    tokens = set(pta.normalise(name)) if name else set()
    phase = pta.phase_words(name) if name else set()
    postcode, domains = pta.norm_postcode(school.get("postcode")), set(domains)
    best = {}
    for c in candidates:
        try:
            number = int(c["charity_number"])
        except (KeyError, TypeError, ValueError):
            continue
        rank, entry = _judge(c, number, registry, tokens, phase, postcode, domains, shared)
        if number not in best or rank > best[number][0]:
            best[number] = (rank, entry)
    ranked = {2: [], 1: [], 0: []}
    for rank, entry in best.values():
        ranked[rank].append(entry)
    return Verdict(ranked[2], ranked[1], ranked[0])


def validate(candidates, registry, school_name=None, shared=False, *, school=None, domains=()) -> list[dict]:
    """The accepted candidates, in the pta_crawl.json entry shape; see classify()."""
    return classify(candidates, registry, school or school_name, shared=shared, domains=domains).accepted


def load_registry(path) -> dict[int, Charity]:
    """{registered charity number: Charity} for every main charity in the register extract, streamed once."""
    registry = {}
    for obj in pta.iter_json_array(path):
        if obj.get("linked_charity_number", 0) not in (0, 1) or not obj.get("registered_charity_number"):
            continue
        number = int(obj["registered_charity_number"])
        if number in registry:
            continue
        name = obj.get("charity_name") or ""
        tier = charity_tier(name, obj.get("charity_activities"))
        registry[number] = Charity(name, obj.get("charity_registration_status"),
                                   (obj.get("date_of_removal") or "")[:10] or None, tier,
                                   pta.norm_postcode(obj.get("charity_contact_postcode")) if tier else None,
                                   pta.domain(obj.get("charity_contact_web")) if tier else None)
    return registry


# --------------------------------------------------------------- fetching

class RateLimiter:
    """At most one request per interval per key (a host, or an IP), timed from when each request really goes out."""

    def __init__(self, interval=HOST_INTERVAL, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self._next, self._last = {}, {}
        self._locks = defaultdict(threading.Lock)
        self._lock = threading.Lock()

    def _key_lock(self, key):
        with self._lock:
            return self._locks[key]

    def wait(self, key, interval=None, *, then=None, abort=None) -> float:
        """Block until key's slot opens and return the time the request goes out. then() runs once the slot is
        open, still holding it (a second gate); abort, an Event, cuts a long wait short by raising Stopped."""
        gap = max(self.interval, interval or 0)
        with self._key_lock(key):
            left = self._next.get(key, 0) - self.clock()
            if left > 0 and abort is None:
                self.sleep(left)
            while left > 0 and abort is not None:
                if abort.is_set():
                    raise Stopped(key)
                self.sleep(min(left, 1.0))
                left -= 1.0
            if then is not None:
                then()
            now = self.clock()
            self._last[key], self._next[key] = now, now + gap
            return now

    def defer(self, key, seconds):
        """Hold key's next slot until seconds after its last request (a Crawl-delay learnt from robots.txt)."""
        with self._key_lock(key):
            if key in self._last:
                self._next[key] = max(self._next.get(key, 0), self._last[key] + seconds)


def _decode(body, charset) -> str:
    if not charset:
        m = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", body[:4096], re.I)
        charset = m.group(1).decode("ascii") if m else "utf-8"
    try:
        return body.decode(charset, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hand every 3xx back, so each hop is robots-checked and paced like a request of its own."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# The unverified context is used only after a certificate failure on a school's public homepage (read-only).
_OPENERS = {verify: urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=context))
            for verify, context in ((True, ssl.create_default_context()), (False, ssl._create_unverified_context()))}


def _read(resp, deadline) -> bytes:
    chunks, size = [], 0
    while size < MAX_BYTES:
        if time.monotonic() > deadline:
            raise TimeoutError("total timeout")
        chunk = resp.read(min(65536, MAX_BYTES - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def http_get(url, headers, timeout, verify=True):
    """The real transport, one hop: (status, final url, text). HTML and plain text only, within timeout seconds
    in all. A redirect comes back as (3xx, its target, ""); error bodies are kept only when they may be a WAF page."""
    request = urllib.request.Request(url, headers=headers)
    deadline = time.monotonic() + timeout
    try:
        with _OPENERS[bool(verify)].open(request, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            body = _read(resp, deadline) if (not ctype or "html" in ctype or "text" in ctype or "xml" in ctype) else b""
            return resp.status, resp.geturl(), _decode(body, resp.headers.get_content_charset())
    except urllib.error.HTTPError as err:
        try:
            location = (err.headers.get("Location") or "").strip() if err.headers else ""
            if 300 <= err.code < 400:
                return err.code, urljoin(url, location) if location else url, ""
            return err.code, url, _decode(err.read(CHALLENGE_BYTES), None) if err.code in CHALLENGE_STATUS else ""
        except (OSError, http.client.HTTPException):
            return err.code, url, ""
        finally:
            err.close()


def resolve_ip(host) -> str | None:
    """The first address a host resolves to, for the per-IP limit; None when it does not resolve."""
    try:
        return socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)[0][4][0]
    except (OSError, UnicodeError, IndexError):
        return None


def classify_error(err) -> str:
    if isinstance(err, urllib.error.URLError) and isinstance(getattr(err, "reason", None), BaseException):
        err = err.reason
    if isinstance(err, socket.gaierror):
        return "dns"
    if isinstance(err, ssl.SSLCertVerificationError):
        return "tls_cert"
    if isinstance(err, ssl.SSLError):
        return "tls_other"
    if isinstance(err, (socket.timeout, TimeoutError)) or "timed out" in str(err):
        return "timeout"
    if isinstance(err, ConnectionRefusedError):
        return "refused"
    if isinstance(err, ConnectionResetError):
        return "reset"
    if isinstance(err, http.client.RemoteDisconnected):
        return "disconnected"
    return type(err).__name__


def is_challenge(status, text) -> bool:
    """A WAF / captcha interstitial: a small 2xx page, or a 202/403/429/503 body, that matches CHALLENGE."""
    head = (text or "")[:CHALLENGE_BYTES]
    if not head or not CHALLENGE.search(head):
        return False
    return (200 <= (status or 0) < 300 and len(text) < CHALLENGE_BYTES) or status in CHALLENGE_STATUS


def transient(page) -> bool:
    """A failed page worth another try on --resume: no answer, a 5xx or 429, or an unreachable robots.txt."""
    err = page.err or ""
    if page.status != "error" or err in ("too_many_redirects", "redirect_to_skipped"):
        return False
    return not (re.fullmatch(r"http_[34]\d\d", err) and err not in ("http_408", "http_429"))


class Fetcher:
    """Polite GETs: robots.txt per origin (cached, and kept for ROBOTS_TTL in a robots.jsonl once attached), a
    rate limit per host and per IP, redirects followed by hand, WAF pages spotted, one User-Agent.

    fetch(url, headers, timeout[, verify=False]) -> (status, final_url, text) is injectable; tests pass a fake.
    resolve(host) -> ip turns on the per-IP limit (main() passes resolve_ip; tests leave it off).
    """

    def __init__(self, fetch=http_get, limiter=None, user_agent=USER_AGENT, timeout=TIMEOUT, *, resolve=None,
                 ip_limiter=None, wall=time.time):
        self.fetch, self.limiter = fetch, limiter or RateLimiter()
        self.ip_limiter = ip_limiter or RateLimiter(IP_INTERVAL, clock=self.limiter.clock, sleep=self.limiter.sleep)
        self.user_agent, self.timeout, self.resolve, self.wall = user_agent, timeout, resolve, wall
        self.headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                        "Accept-Language": "en-GB,en;q=0.8"}
        self.stop = threading.Event()
        self._robots, self._delay, self._ips = {}, {}, {}
        self._locks = defaultdict(threading.Lock)
        self._lock = threading.Lock()
        self._cache = None
        self.stats = Counter()

    def _count(self, key, tally=None):
        with self._lock:
            self.stats[key] += 1
            if tally is not None:
                tally[key] += 1

    def _ip(self, hostname):
        if self.resolve is None or not hostname:
            return None
        with self._lock:
            if hostname in self._ips:
                return self._ips[hostname]
        ip = self.resolve(hostname)
        with self._lock:
            self._ips[hostname] = ip
        return ip

    def _request(self, url, *, verify=True, timeout=None, slow=False, tally=None):
        host = host_key(url)
        ip = self._ip(urlsplit(url).hostname)
        self.limiter.wait(host, self._delay.get(host), then=(lambda: self.ip_limiter.wait(ip)) if ip else None,
                          abort=self.stop if slow else None)
        self._count("requests", tally)
        if verify:
            return self.fetch(url, dict(self.headers), timeout or self.timeout)
        return self.fetch(url, dict(self.headers), timeout or self.timeout, verify=False)

    # robots.txt

    def attach_robots_cache(self, path) -> int:
        """Reuse robots.txt answers younger than ROBOTS_TTL from path, and append new ones to it. Returns how many."""
        self._cache = Path(path)
        rows = {}
        if self._cache.exists():
            now = self.wall()
            for line in self._cache.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    if now - float(row["fetched_at"]) <= ROBOTS_TTL:
                        rows[row["origin"]] = row
                except (ValueError, KeyError, TypeError):
                    continue
            _atomic_lines(self._cache, rows.values())   # drop stale and repeated answers
        for origin, row in rows.items():
            delay = row.get("crawl_delay")
            self._robots[origin] = self._robots_from(row["verdict"], row["status"], delay, row.get("rules_text") or "")
            if delay:
                self._delay[host_key(origin)] = float(delay)
        return len(rows)

    def _remember(self, origin, robots, text):
        if self._cache is None:
            return
        row = {"origin": origin, "host": host_key(origin), "verdict": robots.verdict, "status": robots.status,
               "crawl_delay": robots.delay, "rules_text": text[:100_000], "fetched_at": self.wall()}
        with self._lock:
            self._cache.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _robots_from(verdict, status, delay, text) -> Robots:
        rp = urllib.robotparser.RobotFileParser()
        if verdict == "rules":
            rp.parse(text.splitlines())
        elif verdict == "allow":
            rp.allow_all = True
        else:
            rp.disallow_all = True
        return Robots(rp, verdict, status, float(delay) if delay else None)

    def _fetch_robots(self, origin, verify, tally):
        """(verdict, status, crawl delay, rules text) per crawl_spec §6; redirects followed by hand."""
        url = origin + "/robots.txt"
        for _ in range(MAX_REDIRECTS + 1):
            try:
                status, final, text = self._request(url, verify=verify, tally=tally)
            except Exception as err:   # no answer: go ahead, and let the page fetch record the real error
                return "allow", "net_" + classify_error(err), None, ""
            self._count("robots_requests", tally)
            text = text or ""
            if is_challenge(status, text):
                return "deny", f"challenge_{status}", None, ""
            if 300 <= (status or 0) < 400 and final and final != url and not never_fetch(final):
                url = norm_url(final)
                continue
            if status == 200:
                if "<html" in text[:500].lower():
                    return "allow", "soft404", None, ""
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(text.splitlines())
                try:
                    delay = float(rp.crawl_delay(self.user_agent) or 0) or None
                except (TypeError, ValueError):
                    delay = None
                return "rules", "ok", delay, text
            if status in (401, 403):
                return "deny", f"http_{status}", None, ""      # conservative; RFC 9309 would allow
            if status == 429 or (status or 500) >= 500:
                return "error", f"http_{status}", None, ""     # failing: leave the host alone this run
            return "allow", f"http_{status}", None, ""
        return "allow", "too_many_redirects", None, ""

    def robots(self, url, verify=True, tally=None) -> Robots:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            lock = self._locks[origin]
        with lock:
            cached = self._robots.get(origin)
            if cached and not (cached.status.startswith("net_") and not verify):
                return cached
            verdict, status, delay, text = self._fetch_robots(origin, verify, tally)
            robots = self._robots_from(verdict, status, delay, text)
            self._robots[origin] = robots
            if robots.delay:
                host = host_key(origin)
                with self._lock:
                    self._delay[host] = max(self._delay.get(host, 0), robots.delay)
                self.limiter.defer(host, robots.delay)   # the robots.txt request starts the Crawl-delay clock
            if verdict != "error" and not status.startswith("net_"):
                self._remember(origin, robots, text)
            return robots

    def robots_note(self, url) -> dict | None:
        parts = urlsplit(url)
        robots = self._robots.get(f"{parts.scheme}://{parts.netloc}")
        return {"status": robots.status, "crawl_delay": robots.delay} if robots else None

    def allowed(self, url) -> bool:
        return self._permission(url)[0] == "ok"

    def _permission(self, url, verify=True, slow=False, tally=None):
        """('ok', None) or (page status, reason) for fetching url now."""
        robots = self.robots(url, verify, tally)
        if robots.verdict == "error":
            return "error", "robots_" + robots.status
        if robots.verdict == "deny":
            return "robots", "robots_" + robots.status
        delay = robots.delay or 0
        if delay > SLOW_MAX_DELAY:
            return "robots", f"crawl_delay_{delay:g}s"
        if delay > MAX_CRAWL_DELAY and not slow:
            return "slow", f"crawl_delay_{delay:g}s"
        try:
            if robots.verdict == "rules" and not robots.parser.can_fetch(self.user_agent, url):
                return "robots", "robots_disallow"
        except Exception:
            return "robots", "robots_unreadable"
        return "ok", None

    def get(self, url, *, verify=True, timeout=None, slow=False, tally=None) -> Page:
        """One page, each redirect hop robots-checked and paced. slow=True honours a Crawl-delay above
        MAX_CRAWL_DELAY in full (the slow lane), giving up with Stopped when self.stop is set."""
        current = url
        for hop in range(MAX_REDIRECTS + 1):
            if hop and never_fetch(current):
                self._count("errors", tally)
                return Page(current, "", "error", "redirect_to_skipped")
            status, reason = self._permission(current, verify, slow, tally)
            if status != "ok":
                self._count({"error": "errors"}.get(status, status), tally)
                return Page(current, "", status, reason)
            try:
                code, final, text = self._request(current, verify=verify, timeout=timeout, slow=slow, tally=tally)
            except Exception as err:
                self._count("errors", tally)
                return Page(current, "", "error", classify_error(err))
            if is_challenge(code, text):
                self._count("blocked", tally)
                return Page(current, "", "blocked", f"challenge_{code}")
            if 300 <= (code or 0) < 400 and final and final != current:
                self._count("redirect_hops", tally)
                current = norm_url(final)
                continue
            if not 200 <= (code or 0) < 300:
                self._count("errors", tally)
                return Page(current, "", "error", f"http_{code}")
            return Page(final or current, text or "", "ok")
        self._count("errors", tally)
        return Page(current, "", "error", "too_many_redirects")


# ------------------------------------------------------------------ crawl

def crawl_site(start_url, fetcher, enough=None, max_pages=MAX_PAGES, *, timeout=None, slow=False, tally=None) -> SiteCrawl:
    """Crawl one school website (crawl_spec §2) and return SiteCrawl(candidates, pages, status, trail,
    incomplete, domains, deferred, tls_unverified).

    The homepage first (an unverified TLS retry after a certificate error, or www. toggled after a DNS
    failure; a meta refresh followed on a near-empty page), then links in priority order within the per-kind
    caps, until enough(candidates, domains) is true or max_pages pages have been tried. status is the
    homepage's: ok | robots | blocked | slow | error. incomplete means a page failed in a way worth retrying;
    deferred means a page needs the slow lane. domains are the sites crawled for the school.
    """
    candidates, trail, queue, seen, caps = [], [], [], set(), Counter()
    unverified, pta_sites = set(), set()
    state = {"pages": 0, "incomplete": False, "deferred": False, "tls": False, "seq": 0}

    def fetch(url, kind, depth, verify=True):
        page = fetcher.get(url, verify=verify and host_key(url) not in unverified, timeout=timeout, slow=slow, tally=tally)
        trail.append({"url": url, "final": page.url, "kind": kind, "depth": depth, "status": page.status, "err": page.err})
        if page.status != "robots":
            state["pages"] += 1
        return page

    def result(status, site=None):
        domains = ({site} | pta_sites) if site else set()
        return SiteCrawl(candidates, state["pages"], status, trail, state["incomplete"], domains, state["deferred"],
                         state["tls"])

    home = fetch(start_url, "home", 0)
    if home.status == "error" and home.err == "tls_cert":
        state["tls"] = True
        unverified.add(host_key(start_url))
        home = fetch(start_url, "home_retry", 0, verify=False)
        unverified.add(host_key(home.url))
    elif home.status == "error" and home.err == "dns":
        home = fetch(toggle_www(start_url), "home_retry", 0)
    if home.status != "ok":
        return result(home.status)
    parsed = parse(home.html)
    if parsed.refresh and len(parsed.text) < 500:
        target = _link_url(home.url, parsed.refresh)
        if target and target.rstrip("/") != home.url.rstrip("/"):
            refreshed = fetch(target, "home_refresh", 0)
            if refreshed.status == "ok":
                home, parsed = refreshed, parse(refreshed.html)
    site = site_of(host_key(home.url))   # a homepage redirecting to another domain makes that the school's site
    school_host = host_key(home.url)

    def visit(page, parsed, kind, depth) -> bool:
        """Read one fetched page; True when the crawl can stop."""
        seen.add(page.url.rstrip("/"))
        if kind in ("offsite_home", "offsite_about"):
            pta_sites.add(site_of(host_key(page.url)))
        pta_page = True if kind in PTA_KINDS else (False if kind.startswith("home") else None)
        candidates.extend(extract_candidates(parsed, page.url, pta_page, kind=kind))
        if enough is not None and enough(candidates, {site} | pta_sites):
            return True
        if "nofollow" in parsed.robots:
            return False
        links = link_candidates(parsed, page.url, "home" if kind.startswith("home") else kind, depth, site, pta_sites,
                                school_host)
        if kind.startswith("home") and any(link.kind == "pta" for link in links):
            links = [link for link in links if link.kind != "hub"]
        for link in links:
            if link.url.rstrip("/") not in seen:
                state["seq"] += 1
                heappush(queue, (link.priority, state["seq"], link))
        return False

    seen.update({start_url.rstrip("/"), home.url.rstrip("/")})
    stop = visit(home, parsed, "home", 0)
    while not stop and queue and state["pages"] < max_pages:
        link = heappop(queue)[2]
        if link.url.rstrip("/") in seen or caps[link.kind] >= CAP[link.kind]:
            continue
        seen.add(link.url.rstrip("/"))
        caps[link.kind] += 1
        page = fetch(link.url, link.kind, link.depth)
        if page.status == "slow":
            state["deferred"] = True
        elif page.status != "ok":
            state["incomplete"] = state["incomplete"] or transient(page)
        elif page.url.rstrip("/") not in seen or page.url == link.url:
            stop = visit(page, parse(page.html), link.kind, link.depth)
    return result("ok", site)


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


def matched_urns(path) -> set[str]:
    """URNs a pta.json already matches with at least one charity that is not held for review."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(urn) for urn, records in (data.get("schools") or {}).items()
            if any(not r.get("review") for r in records or [])}


def crawl_order(schools, seed=SEED) -> list[dict]:
    """The schools shuffled (deterministically for a seed): never by council or name, since platforms cluster."""
    order = list(schools)
    random.Random(seed).shuffle(order)
    return order


def _outcome(site, accepted, review, lane) -> str:
    if site.status != "ok":
        return site.status
    if accepted:
        return "hit"
    if site.deferred and lane != "slow":
        return "slow"
    if site.incomplete:
        return "incomplete"
    return "review_only" if review else "no_pta"


def crawl_group(group, fetcher, registry, shared=None, *, lane="main", timeout=None) -> list[dict]:
    """Journal lines for the schools sharing one website, which is crawled once. The crawl stops early only
    when every school in the group has a number that validates for it."""
    url = normalise_url(group[0]["website"])
    on_shared_site = (shared or Counter())[site_key(url)] > 1

    def enough(candidates, domains):
        return all(classify(candidates, registry, s, shared=on_shared_site, domains=domains).accepted for s in group)

    tally = Counter()
    site = crawl_site(url, fetcher, enough, timeout=timeout, slow=lane == "slow", tally=tally)
    verdicts = [classify(site.candidates, registry, s, shared=on_shared_site, domains=site.domains) for s in group]
    sibling = {h["charity_number"] for v in verdicts for h in v.accepted}   # a federation partner's own PTA
    home_err = next((p["err"] for p in reversed(site.trail) if p["kind"].startswith("home")), None)
    robots = fetcher.robots_note(url) if hasattr(fetcher, "robots_note") else None
    lines = []
    for s, verdict in zip(group, verdicts):
        review = [r for r in verdict.review if r["charity_number"] not in sibling]
        lines.append({"urn": str(s["urn"]), "name": s.get("name"), "website": url, "pass": lane,
                      "crawl_version": CRAWL_VERSION, "at": datetime.now().isoformat(timespec="seconds"),
                      "outcome": _outcome(site, verdict.accepted, review, lane), "home_err": home_err,
                      "pages": site.trail, "hits": verdict.accepted, "review": review, "rejects": verdict.rejects[:20],
                      "requests": tally["requests"], "robots": robots, "tls_unverified": site.tls_unverified,
                      "shared_site": on_shared_site})
    return lines


def split_widespread(found, limit=MAX_SHARED):
    """(kept, held): numbers on more than limit schools' sites are held back."""
    counts = Counter(h["charity_number"] for hits in found.values() for h in hits)
    kept, held = {}, {}
    for urn, hits in found.items():
        for h in hits:
            (held if counts[h["charity_number"]] > limit else kept).setdefault(urn, []).append(h)
    return kept, held


# ----------------------------------------------------- journal and outputs

def state_path(out) -> Path:
    out = Path(out)
    return out.with_name(out.stem + ".state.json")


def journal_path(out) -> Path:
    out = Path(out)
    return out.with_name(out.stem + ".results.jsonl")


def robots_path(out) -> Path:
    out = Path(out)
    return out.with_name(out.stem + ".robots.jsonl")


def review_path(out) -> Path:
    out = Path(out)
    return out.with_name(out.stem + "_review.json")


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _atomic_lines(path, rows):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    os.replace(tmp, path)


class Journal:
    """results.jsonl: one line per finished school, appended and flushed under a lock; a later line for a URN wins."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, line):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
                f.flush()

    def latest(self) -> dict[str, dict]:
        latest = {}
        if self.path.exists():
            for raw in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    line = json.loads(raw)
                    latest[str(line["urn"])] = line
                except (ValueError, KeyError, TypeError):
                    continue   # a line cut short by a crash
        return latest

    def start_fresh(self):
        """A new run without --resume: keep the previous journal once, as .prev, and start an empty one."""
        if self.path.exists():
            os.replace(self.path, self.path.with_name(self.path.stem + ".prev.jsonl"))


def seed_from_legacy(out, journal) -> int:
    """Journal lines for the results of a crawler that wrote only pta_crawl.json and its state file."""
    out, lines = Path(out), {}
    if out.exists():
        for urn, hits in json.loads(out.read_text(encoding="utf-8")).get("schools", {}).items():
            lines[str(urn)] = {"urn": str(urn), "outcome": "hit", "hits": list(hits)}
    if state_path(out).exists():
        saved = json.loads(state_path(out).read_text(encoding="utf-8"))
        for key in ("no_pta", "robots"):
            for urn in saved.get(key, []):
                lines.setdefault(str(urn), {"urn": str(urn), "outcome": key, "hits": []})
        for urn, hits in saved.get("held", {}).items():
            line = lines.setdefault(str(urn), {"urn": str(urn), "outcome": "hit", "hits": []})
            line.update(outcome="hit", hits=line["hits"] + list(hits))
    for line in lines.values():
        journal.append(dict(line, **{"pass": "legacy", "crawl_version": CRAWL_VERSION, "review": []}))
    return len(lines)


def is_final(line) -> bool:
    return line.get("outcome") in FINAL and line.get("crawl_version") == CRAWL_VERSION


def write_outputs(out, latest) -> dict:
    """pta_crawl.json, pta_crawl_review.json and the state file, rebuilt from the journal's latest lines."""
    found = {urn: line["hits"] for urn, line in latest.items() if line.get("hits")}
    review = {urn: line["review"] for urn, line in latest.items() if line.get("review")}
    kept, held = split_widespread(found)
    outcomes = Counter(line.get("outcome") for line in latest.values())
    by = defaultdict(list)
    for urn, line in latest.items():
        by[line.get("outcome")].append(urn)
    now = datetime.now().isoformat(timespec="seconds")
    meta = {"crawl_version": CRAWL_VERSION, "schools": len(latest), "outcomes": dict(sorted(outcomes.items(), key=str)),
            "requests": sum(line.get("requests") or 0 for line in latest.values()),
            "held_schools": len(held), "review_schools": len(review),
            "tls_unverified": sum(1 for line in latest.values() if line.get("tls_unverified"))}
    _atomic_write(out, {"generated": now, "user_agent": USER_AGENT, "meta": meta,
                        "schools": {urn: kept[urn] for urn in sorted(kept)}})
    _atomic_write(review_path(out), {
        "generated": now,
        "note": ("Charity numbers that pass the register, parents'-association and PTA-wording checks on a school's "
                 "website but do not agree with that school's name, postcode or domain. For a person to check; "
                 "never merged."),
        "schools": {urn: review[urn] for urn in sorted(review)}})
    failed = sorted(set(by["error"]) | set(by["incomplete"]) | set(by["slow"]) | set(by["crawler_error"]))
    _atomic_write(state_path(out), {"generated": now, "no_pta": sorted(by["no_pta"]), "robots": sorted(by["robots"]),
                                    "blocked": sorted(by["blocked"]), "review": sorted(by["review_only"]),
                                    "failed": failed, "held": held})
    return {"kept": kept, "held": held, "review": review, "outcomes": outcomes, "failed": failed}


# --------------------------------------------------------------------- run

def _pool_sizes(workers) -> tuple[int, int]:
    """(main, slow lane) threads: a sixth for the slow lane, never more than MAX_WORKERS in all."""
    workers = max(1, min(int(workers), MAX_WORKERS))
    return workers - workers // 6, workers // 6


def _on_signals(stop, log):
    """Drain on SIGINT/SIGTERM (a second one stops at once); returns a function that restores the old handlers."""
    if threading.current_thread() is not threading.main_thread():
        return lambda: None

    def handler(signum, frame):
        if stop.is_set():
            raise KeyboardInterrupt
        stop.set()
        log("stopping: no new schools; finishing the ones in flight, then writing the outputs")

    old = {sig: signal.signal(sig, handler) for sig in (signal.SIGINT, signal.SIGTERM)}
    return lambda: [signal.signal(sig, h) for sig, h in old.items()]


def _error_line(school, lane, err) -> dict:
    return {"urn": str(school["urn"]), "name": school.get("name"), "pass": lane, "crawl_version": CRAWL_VERSION,
            "at": datetime.now().isoformat(timespec="seconds"), "outcome": "crawler_error",
            "error": f"{type(err).__name__}: {err}", "hits": [], "review": []}


def _drain(groups, crawl, record, *, workers, stop, lane):
    """Crawl groups on a bounded pool, handing out no new group once stop is set. A group whose site needs a
    Crawl-delay above MAX_CRAWL_DELAY moves to the slow lane, which honours it in full alongside the rest."""
    main_n, slow_n = _pool_sizes(workers)
    pools = {"main": ThreadPoolExecutor(main_n, thread_name_prefix="pta-crawl"),
             "slow": ThreadPoolExecutor(slow_n, thread_name_prefix="pta-slow") if slow_n else None}
    todo, slow_todo, running, busy = deque(groups), deque(), {}, Counter()
    failed = True
    try:
        while True:
            while not stop.is_set() and todo and busy["main"] < main_n:
                group = todo.popleft()
                running[pools["main"].submit(crawl, group, lane)] = (group, lane, "main")
                busy["main"] += 1
            pool = "slow" if pools["slow"] else "main"
            cap = slow_n if pools["slow"] else (0 if todo else main_n)
            while not stop.is_set() and slow_todo and busy[pool] < cap:
                group = slow_todo.popleft()
                running[pools[pool].submit(crawl, group, "slow")] = (group, "slow", pool)
                busy[pool] += 1
            if not running:
                break
            done, _ = wait(running, timeout=1.0, return_when=FIRST_COMPLETED)
            for future in done:
                group, which, pool = running.pop(future)
                busy[pool] -= 1
                try:
                    lines = future.result()
                except Stopped:
                    continue
                except Exception as err:   # never lose a school to a bug: journal it for --resume
                    lines = [_error_line(s, which, err) for s in group]
                record(group, lines, which)
                if which != "slow" and any(line["outcome"] == "slow" for line in lines):
                    slow_todo.append(group)
        failed = False
    finally:
        if failed:
            stop.set()
        for pool in pools.values():
            if pool:
                pool.shutdown(wait=not failed, cancel_futures=True)


def run(schools, fetcher, registry, out, *, workers=MAX_WORKERS, shared=None, log=print, journal=None, stop=None) -> dict:
    """Crawl every school (grouped by website, each site once), journal each result, retry homepages that timed
    out once, then rebuild the outputs from the journal. SIGINT/SIGTERM or stop.set() drains cleanly."""
    journal = journal or Journal(journal_path(out))
    shared = shared or Counter()
    stop = stop or getattr(fetcher, "stop", None) or threading.Event()
    if hasattr(fetcher, "stop"):
        fetcher.stop = stop
    groups = defaultdict(list)
    for s in schools:
        groups[site_key(normalise_url(s["website"]))].append(s)
    total, start = len(schools), time.time()
    progress = {"done": 0, "hits": 0}
    timed_out = []

    def crawl(group, lane):
        return crawl_group(group, fetcher, registry, shared, lane=lane, timeout=RETRY_TIMEOUT if lane == "retry" else None)

    def record(group, lines, lane):
        for line in lines:
            journal.append(line)
        if lane == "main" and all(line["outcome"] == "error" and line.get("home_err") == "timeout" for line in lines):
            timed_out.append(group)
        if lane != "main":
            return
        before = progress["done"]
        progress["done"] += len(lines)
        progress["hits"] += sum(1 for line in lines if line.get("hits"))
        if before // LOG_EVERY != progress["done"] // LOG_EVERY:
            stats = getattr(fetcher, "stats", Counter())
            log(f"{progress['done']:,}/{total:,} schools, {progress['hits']:,} with a PTA number, "
                f"{stats['requests']:,} requests, {stats['errors']:,} errors, {stats['robots']:,} robots-blocked, "
                f"{stats['blocked']:,} behind a bot check ({time.time() - start:.0f}s)")

    restore = _on_signals(stop, log)
    try:
        _drain(list(groups.values()), crawl, record, workers=workers, stop=stop, lane="main")
        if timed_out and not stop.is_set():
            log(f"retrying {len(timed_out):,} homepages that timed out, with a {RETRY_TIMEOUT}s timeout")
            _drain(timed_out, crawl, record, workers=workers, stop=stop, lane="retry")
    finally:
        restore()
        summary = write_outputs(out, journal.latest())
    stats = getattr(fetcher, "stats", Counter())
    kept, outcomes = summary["kept"], summary["outcomes"]
    log(f"{'stopped' if stop.is_set() else 'done'}: {progress['done']:,} schools crawled this run; in all "
        f"{len(kept):,} with a PTA number ({sum(map(len, kept.values())):,} charities), "
        f"{len(summary['held']):,} held as shared, {len(summary['review']):,} for review, {outcomes['no_pta']:,} none found, "
        f"{outcomes['robots']:,} robots-blocked, {outcomes['blocked']:,} behind a bot check, "
        f"{len(summary['failed']):,} to retry with --resume; {stats['requests']:,} requests ({time.time() - start:.0f}s)")
    return dict(summary, interrupted=stop.is_set())


def main(argv=None, *, fetcher=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site-data", type=Path, default=SITE_DATA)
    parser.add_argument("--charity-dir", type=Path, default=CHARITY_DIR)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--limit", type=int, help="crawl at most this many schools")
    parser.add_argument("--resume", action="store_true", help="skip schools the journal already has a final result for")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"threads (at most {MAX_WORKERS})")
    parser.add_argument("--urns", help="comma-separated URNs")
    parser.add_argument("--la", help="one council code, e.g. 204")
    parser.add_argument("--only-unmatched", type=Path, metavar="PTA_JSON",
                        help="crawl only schools this pta.json has no (unheld) charity for")
    parser.add_argument("--seed", type=int, default=SEED, help="seed for the shuffled crawl order")
    args = parser.parse_args(argv)

    every = [s for s in pta.load_schools(args.site_data) if _open(s) and normalise_url(s.get("website"))]
    shared = Counter(site_key(normalise_url(s["website"])) for s in every)
    las = args.site_data / "england/las.json"
    councils = ({str(la["la_code"]): la["name"] for la in json.loads(las.read_text(encoding="utf-8")).get("las", [])}
                if las.exists() else {})
    urns = {u.strip() for u in args.urns.split(",") if u.strip()} if args.urns else None
    schools = select_schools(every, urns, args.la, councils)
    if args.only_unmatched:
        matched = matched_urns(args.only_unmatched)
        schools = [s for s in schools if str(s["urn"]) not in matched]
    journal = Journal(journal_path(args.out))
    if args.resume:
        if not journal.path.exists():
            seed_from_legacy(args.out, journal)
        latest = journal.latest()
        schools = [s for s in schools if not is_final(latest.get(str(s["urn"]), {}))]
    else:
        journal.start_fresh()
        latest = {}
    if args.limit is not None:
        schools = schools[:args.limit]
    schools = crawl_order(schools, args.seed)
    print(f"{len(schools):,} schools to crawl ({sum(1 for line in latest.values() if line.get('hits')):,} already found)",
          flush=True)
    registry = load_registry(args.charity_dir / "publicextract.charity.json")
    print(f"{len(registry):,} charities in the register", flush=True)
    fetcher = fetcher or Fetcher(resolve=resolve_ip)
    if hasattr(fetcher, "attach_robots_cache"):
        fetcher.attach_robots_cache(robots_path(args.out))
    summary = run(schools, fetcher, registry, args.out, workers=args.workers, shared=shared, journal=journal,
                  log=lambda line: print(line, flush=True))
    return 130 if summary["interrupted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
