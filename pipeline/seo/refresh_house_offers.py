#!/usr/bin/env python3
"""Save the latest house offers from hammantlabs.com for build_pages.py; stdlib only.

deploy/railway/deploy.sh runs this before building the pages. It writes
pipeline/.cache/house_offers.json (not committed) only when the live feed is valid and
still has offers for this site. On any failure it exits 1 and changes nothing, and the
build uses the last saved copy or, failing that, pipeline/seo/house_offers.json.

Visitors' browsers never contact hammantlabs.com: the offer is built into the page.
"""
import json
from pathlib import Path
import sys
import tempfile
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import house_promo  # noqa: E402

FEED_URL = "https://hammantlabs.com/promo/offers.json"
CACHE_PATH = Path(__file__).resolve().parents[1] / ".cache" / "house_offers.json"
SITE = "schoolsinreach"


def check(feed):
    """Problems that stop this feed being used here; an empty list means use it."""
    errors = house_promo.validate_feed(feed)
    if not errors and SITE not in feed.get("sites", {}):
        errors.append(f"the feed no longer lists {SITE}")
    return errors


def refresh(url=FEED_URL, cache=CACHE_PATH, timeout=10):
    request = Request(url, headers={"User-Agent": "schoolsinreach-build/1"})
    with urlopen(request, timeout=timeout) as response:
        feed = json.loads(response.read().decode("utf-8"))
    errors = check(feed)
    if errors:
        raise ValueError("; ".join(errors))
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=cache.parent, delete=False, suffix=".tmp") as handle:
        json.dump(feed, handle, ensure_ascii=False, indent=2)
    Path(handle.name).replace(cache)
    placed = [offer["id"] for offer in feed["offers"] if SITE in offer["show_on"]]
    return placed


def main():
    try:
        placed = refresh()
    except Exception as exc:  # any failure keeps the saved copy
        print(f"House offers not refreshed ({exc}); the build uses the saved copy.", file=sys.stderr)
        return 1
    print(f"House offers refreshed from {FEED_URL}: {', '.join(placed) or 'none'} for {SITE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
