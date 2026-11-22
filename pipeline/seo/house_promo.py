# Copied unchanged from jhammant/hammantlabs-sites promo/render.py (the house promo slot).
# Keep the two in step: hammantlabs-sites tests/promo_vectors.json pins the pick rule that
# this file shares with the browser loader on hammantlabs.com.
"""House promo slot: validate the offers, build the public feed, pick and render one offer.

Python standard library only, so a static site's build can copy this one file and use
it without installing anything (Schools in Reach does: pipeline/seo/house_promo.py).

The browser loader (promo/slot.js) picks offers with exactly the same rule as pick()
below; tests/promo_vectors.json pins both to the same answers, so change them together.

The rule, in order:
  1. the offer lists this site in show_on;
  2. it is not this site's own product, nor a product the page already links to (exclude);
  3. it shares at least one audience tag with the page;
  4. today is inside its optional starts/ends dates;
  5. the highest priority wins; a tie is settled by a stable hash of the page key, so
     each page always shows the same offer and tied offers split pages evenly.
"""
from datetime import date
from html import escape
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DELIVERIES = ("loader", "static", "none")
LIMITS = {"headline": 60, "text": 220, "cta": 40, "kicker": 80}


def validate(source):
    """Every problem with an offers source, as plain sentences. An empty list means valid."""
    errors = []
    if not isinstance(source, dict):
        return ["the offers file must be a JSON object"]
    if source.get("version") != 1:
        errors.append("version must be 1")
    if not SLUG.match(str(source.get("utm_medium", ""))):
        errors.append("utm_medium must be a lower-case slug")
    audiences = source.get("audiences")
    if not isinstance(audiences, dict) or not audiences:
        errors.append("audiences must name at least one audience")
        audiences = {}
    for tag in audiences:
        if not SLUG.match(tag):
            errors.append(f"audience {tag!r} must be a lower-case slug")
    sites = source.get("sites")
    if not isinstance(sites, dict) or not sites:
        errors.append("sites must name at least one site")
        sites = {}
    for name, site in sites.items():
        if not SLUG.match(name) or not isinstance(site, dict):
            errors.append(f"site {name!r} must be a lower-case slug with an object")
            continue
        if not SLUG.match(str(site.get("product", ""))):
            errors.append(f"site {name}: product must be a lower-case slug")
        if site.get("delivery") not in DELIVERIES:
            errors.append(f"site {name}: delivery must be one of {', '.join(DELIVERIES)}")
        errors += _text_errors(f"site {name}", "kicker", site.get("kicker"))
    offers = source.get("offers")
    if not isinstance(offers, list) or not offers:
        return errors + ["offers must list at least one offer"]
    seen = set()
    for offer in offers:
        if not isinstance(offer, dict):
            errors.append("each offer must be an object")
            continue
        oid = str(offer.get("id", ""))
        label = f"offer {oid or '?'}"
        if not SLUG.match(oid):
            errors.append(f"{label}: id must be a lower-case slug (it becomes utm_campaign)")
        if oid in seen:
            errors.append(f"{label}: id is used twice")
        seen.add(oid)
        product = offer.get("product")
        if not SLUG.match(str(product or "")):
            errors.append(f"{label}: product must be a lower-case slug")
        tags = offer.get("audiences")
        if not isinstance(tags, list) or not tags:
            errors.append(f"{label}: audiences must list at least one audience")
        else:
            errors += [f"{label}: unknown audience {t!r}" for t in tags if t not in audiences]
        show_on = offer.get("show_on")
        if not isinstance(show_on, list):
            errors.append(f"{label}: show_on must be a list of sites (it may be empty)")
            show_on = []
        for name in show_on:
            site = sites.get(name)
            if not isinstance(site, dict):
                errors.append(f"{label}: show_on names unknown site {name!r}")
            elif site.get("product") == product:
                errors.append(f"{label}: would advertise {name} on its own site")
            elif site.get("delivery") == "none":
                errors.append(f"{label}: {name} takes no offers (delivery is none)")
        priority = offer.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 100:
            errors.append(f"{label}: priority must be a whole number from 0 to 100")
        for field in ("headline", "text", "cta"):
            errors += _text_errors(label, field, offer.get(field))
        url = str(offer.get("url", ""))
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.netloc:
            errors.append(f"{label}: url must be an absolute https:// address")
        elif any(k.lower().startswith("utm_") for k, _ in parse_qsl(parts.query)):
            errors.append(f"{label}: url must not carry utm_ tags; the feed adds them")
        for field in ("starts", "ends"):
            value = offer.get(field)
            if value is not None and not _is_date(value):
                errors.append(f"{label}: {field} must be a YYYY-MM-DD date")
        if _is_date(offer.get("starts")) and _is_date(offer.get("ends")) and offer["starts"] > offer["ends"]:
            errors.append(f"{label}: starts is after ends")
    return errors


def _text_errors(label, field, value):
    if not isinstance(value, str) or not value.strip():
        return [f"{label}: {field} is missing"]
    problems = []
    if len(value) > LIMITS[field]:
        problems.append(f"{label}: {field} is {len(value)} characters; the limit is {LIMITS[field]}")
    if "<" in value or ">" in value:
        problems.append(f"{label}: {field} must be plain text, not HTML")
    return problems


def _is_date(value):
    if not isinstance(value, str) or not ISO_DATE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def with_query(url, params):
    """url with params appended to its query string; any #fragment stays at the end."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True) + list(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_feed(source):
    """The public feed: the source plus one UTM-tagged link per site an offer shows on.

    utm_source is the site the visitor clicked on, utm_medium says it was a house
    offer and utm_campaign names the offer. BinMinder's sign-up attribution keeps
    exactly these three, so a sign-up can be traced to the offer that sent it.
    """
    errors = validate(source)
    if errors:
        raise ValueError("offers are not valid:\n- " + "\n- ".join(errors))
    feed = {key: value for key, value in source.items() if key != "offers"}
    feed["offers"] = []
    for offer in source["offers"]:
        out = dict(offer)
        out["links"] = {
            site: with_query(offer["url"], [
                ("utm_source", site), ("utm_medium", source["utm_medium"]), ("utm_campaign", offer["id"]),
            ])
            for site in offer["show_on"]
        }
        feed["offers"].append(out)
    return feed


def validate_feed(feed):
    """validate() for a built feed, as a site reads it: also every link a placed offer needs.

    A site that keeps a copy of the feed calls this before trusting it, so a broken or
    tampered copy shows nothing rather than something wrong.
    """
    errors = validate(feed)
    if errors:
        return errors
    for offer in feed["offers"]:
        links = offer.get("links")
        if not isinstance(links, dict):
            errors.append(f"offer {offer['id']}: links are missing")
            continue
        for site in offer["show_on"]:
            link = links.get(site)
            parts = urlsplit(link) if isinstance(link, str) else None
            if not parts or parts.scheme != "https" or not parts.netloc:
                errors.append(f"offer {offer['id']}: no https link for {site}")
            elif dict(parse_qsl(parts.query)).get("utm_source") != site:
                errors.append(f"offer {offer['id']}: the {site} link is not tagged utm_source={site}")
    return errors


def stable_hash(key):
    """32-bit FNV-1a of the key's UTF-8 bytes, then MurmurHash3's finaliser; slot.js matches.

    The finaliser matters: FNV-1a's low bit is only the parity of the key's odd bytes,
    so "% 2" on its own would split similar page paths badly.
    """
    value = 0x811C9DC5
    for byte in str(key).encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x85EBCA6B) & 0xFFFFFFFF
    value ^= value >> 13
    value = (value * 0xC2B2AE35) & 0xFFFFFFFF
    value ^= value >> 16
    return value


def pick(feed, site, tags, key, exclude=(), today=None):
    """The one offer for this page, or None. See the module docstring for the rule."""
    home = (feed.get("sites") or {}).get(site)
    if not home:
        return None
    today = today or date.today().isoformat()
    tags, exclude = set(tags), set(exclude)
    candidates = [
        offer for offer in feed.get("offers", [])
        if site in offer.get("show_on", [])
        and offer.get("product") != home.get("product")
        and offer.get("product") not in exclude
        and tags.intersection(offer.get("audiences", []))
        and (not offer.get("starts") or offer["starts"] <= today)
        and (not offer.get("ends") or today <= offer["ends"])
        and (offer.get("links") or {}).get(site)
    ]
    if not candidates:
        return None
    top = max(offer["priority"] for offer in candidates)
    best = [offer for offer in candidates if offer["priority"] == top]
    return best[stable_hash(key) % len(best)]


def offer_href(offer, site, placement=None):
    """The offer's link for this site; placement (the page type, a slug) is added as utm_content."""
    href = offer["links"][site]
    return with_query(href, [("utm_content", placement)]) if placement and SLUG.match(placement) else href


def render(feed, site, tags, key, exclude=(), placement=None, today=None, css_class="house-promo"):
    """One offer as static HTML for a server-rendered page, or "" when none suits it.

    It reads as the site's own content, says who it is from, and is never labelled or
    shaped like an advert. One link, no script, no cookie, no tracking: a click is
    counted by the UTM tags when the visitor arrives.
    """
    offer = pick(feed, site, tags, key, exclude, today)
    if not offer:
        return ""
    kicker = feed["sites"][site]["kicker"]
    href = offer_href(offer, site, placement)
    c = escape(css_class)
    return (
        f'<aside class="{c}" aria-label="{escape(kicker)}" data-offer="{escape(offer["id"])}">'
        f'<p class="{c}-kicker">{escape(kicker)}</p>'
        f'<p class="{c}-headline">{escape(offer["headline"])}</p>'
        f'<p class="{c}-text">{escape(offer["text"])}</p>'
        f'<p class="{c}-cta"><a href="{escape(href)}">{escape(offer["cta"])}</a></p>'
        "</aside>"
    )
