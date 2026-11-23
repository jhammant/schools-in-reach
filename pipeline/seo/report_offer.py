"""Deploy check for the "Your chances" report offer: its email form must have a live endpoint.

site/js/config.js names the sign-up endpoint (CONFIG.parentsReport.notifyUrl). When it is set, the
endpoint's health check must answer and it must accept posts from the site, or the deploy stops:
a form that can't save would lose parents' sign-ups without anyone noticing. Deploy the endpoint
first (see deploy/report-signups/ in the README), or empty notifyUrl to show the offer without the
email box. Neither check stores anything: one GET and one CORS preflight.

    python3 pipeline/seo/report_offer.py            # exit 0 when fine, 1 with the reason otherwise
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITE_ORIGIN = "https://www.schoolsinreach.com"
CONFIG = Path(__file__).resolve().parents[2] / "site" / "js" / "config.js"
LOCAL = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/")


def notify_url(config_text: str) -> str:
    """The parentsReport.notifyUrl in config.js ("" when unset). Fails loudly if the block is missing."""
    block = re.search(r"parentsReport\s*:\s*\{([^}]*)\}", config_text)
    if not block:
        raise ValueError("site/js/config.js has no parentsReport block")
    url = re.search(r"notifyUrl\s*:\s*\"([^\"]*)\"", block.group(1))
    return url.group(1).strip() if url else ""


def health_url(url: str) -> str:
    """.../api/notify -> .../api/health"""
    return url.rsplit("/", 1)[0] + "/health"


def _request(url: str, method: str, headers: dict, timeout: float):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "schoolsinreach-deploy-check", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, dict(res.headers), res.read(4096)
    except urllib.error.HTTPError as err:
        with err:
            return err.code, dict(err.headers), err.read(4096)


def check_endpoint(url: str, timeout: float = 10) -> list[str]:
    """Problems with the endpoint, or [] when it is ready for the site's form."""
    if not url.startswith("https://") and not LOCAL.match(url):
        return [f"notifyUrl must be an https:// address (got {url!r})"]
    problems = []
    try:
        status, _, body = _request(health_url(url), "GET", {}, timeout)
        try:
            ok = status == 200 and json.loads(body or b"{}").get("ok") is True
        except (ValueError, AttributeError):
            ok = False
        if not ok:
            problems.append(f"{health_url(url)} answered {status}, not 200 {{\"ok\": true}}")
        status, headers, _ = _request(url, "OPTIONS", {"Origin": SITE_ORIGIN, "Access-Control-Request-Method": "POST"}, timeout)
        allowed = {k.lower(): v for k, v in headers.items()}.get("access-control-allow-origin")
        if status not in (200, 204) or allowed != SITE_ORIGIN:
            problems.append(f"{url} does not accept posts from {SITE_ORIGIN} (preflight {status}, allow-origin {allowed!r})")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
        problems.append(f"{url} could not be reached: {err}")
    return problems


def main(config_path: Path = CONFIG) -> int:
    url = notify_url(config_path.read_text(encoding="utf-8"))
    if not url:
        print("Report offer: no sign-up endpoint configured, so the offer shows without an email box.")
        return 0
    problems = check_endpoint(url)
    if problems:
        for problem in problems:
            print(f"Report offer: {problem}", file=sys.stderr)
        print("Deploy the endpoint first (hlsite deploy deploy/report-signups --slug sir-report --kind pages), "
              "or empty CONFIG.parentsReport.notifyUrl in site/js/config.js.", file=sys.stderr)
        return 1
    print(f"Report offer: sign-up endpoint {url} is live and accepts {SITE_ORIGIN}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
