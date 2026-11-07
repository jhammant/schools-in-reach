"""Pre-deploy checks on a built School Money site (site_money/), run by deploy.sh after the build. Python stdlib only.

  python3 deploy/money/check_site.py site_money      exit 1, with every problem listed, if the site must not ship

It refuses a site that
  - has fewer than MIN_POSTCODES postcode district files in data/postcodes/, or lacks any of REQUIRED_POSTCODES
    (the search boxes look postcodes up there; a 404 reads as "no schools near you");
  - is missing a file the shipped JavaScript fetches: every same-site path in an asset's 'Reads:' header and in its
    fetch / fetchJSON / getJSON calls becomes a glob (data/s/*.json, data/a/council-*.json, ...) that must match;
  - carries macOS '._*' AppleDouble files, which would ship as junk pages and data.
tests/test_deploy_money.py and tests/test_fetch_contract.py import it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MIN_POSTCODES = 2_000
REQUIRED_POSTCODES = ("N16.json", "E8.json")
SCRIPTS = ("app.js", "map.js", "deck.js", "wrapped.js", "tools.js", "trend.js")
FETCHERS = ("fetch", "fetchJSON", "getJSON", "loadJSON")
# A same-site path in prose: /data/... or /assets/..., with <placeholders>; it stops at '#', quotes, commas and spaces.
PATH = re.compile(r"/(?:data|assets)/[A-Za-z0-9_.<>*-]+(?:/[A-Za-z0-9_.<>*-]+)*")
STRING = re.compile(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'')


def postcode_problems(site: Path) -> list[str]:
    """What is wrong with data/postcodes/: too few district files, or a required district missing."""
    folder = site / "data" / "postcodes"
    files = {p.name for p in folder.glob("*.json")} if folder.is_dir() else set()
    problems = []
    if len(files) < MIN_POSTCODES:
        problems.append(f"only {len(files):,} postcode district files in data/postcodes/ (need {MIN_POSTCODES:,})")
    missing = [name for name in REQUIRED_POSTCODES if name not in files]
    if missing:
        problems.append(f"data/postcodes/ lacks {', '.join(missing)}")
    return problems


def apple_double(site: Path) -> list[str]:
    """Every macOS '._*' file under site, as paths relative to it."""
    return sorted(str(p.relative_to(site)) for p in site.rglob("._*"))


def _glob(path: str) -> str:
    """'/data/s/<urn>.json' -> 'data/s/*.json'."""
    return re.sub(r"\*+", "*", re.sub(r"<[^>]*>", "*", path)).lstrip("/").rstrip(".")


def header_reads(js: str) -> set[str]:
    """Globs from the 'Reads:' paragraph of a script's opening comment (up to the next 'Word:' label or its end)."""
    opening = js.split("*/", 1)[0]
    m = re.search(r"Reads:(.*?)(?:\n\s*(?:[A-Z][A-Za-z ]*):|\Z)", opening, re.S)
    return {_glob(p) for p in PATH.findall(m.group(1))} if m else set()


def _argument(js: str, start: int) -> str:
    """The text between the parenthesis at start and its match, skipping strings."""
    depth, i, quote = 0, start, None
    while i < len(js):
        c = js[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if not depth:
                return js[start + 1:i]
        i += 1
    return ""


def _top_level_plus(text: str) -> list[str]:
    """text split on '+' outside strings and brackets."""
    parts, depth, quote, cur = [], 0, None, ""
    for i, c in enumerate(text):
        if quote:
            if c == quote and text[i - 1] != "\\":
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "+" and not depth:
            parts.append(cur)
            cur = ""
            continue
        cur += c
    return parts + [cur]


def fetch_reads(js: str) -> set[str]:
    """Globs for the same-site paths a script's fetch calls ask for. A concatenation keeps its string pieces and turns
    everything else into '*'; a helper that prefixes its argument (getJSON(rel) -> fetch("/data/" + rel)) has the
    prefix put back on its callers' paths. Variable URLs are left to the 'Reads:' header."""
    helpers = {name: prefix for name, param, prefix in
               re.findall(r"function (\w+)\((\w+)\)\s*\{[^}]*?fetch\(\s*\"(/[^\"]*)\"\s*\+\s*\2\b", js)}
    out = set()
    for m in re.finditer(r"(?<![\w.$])(" + "|".join(FETCHERS + tuple(helpers)) + r")\s*\(", js):
        name, arg = m.group(1), _argument(js, m.end() - 1)
        if re.match(r"\s*\w+\s*\)?\s*$", arg) or not arg.strip():
            continue  # a variable: its paths are in the header
        pieces = []
        for part in _top_level_plus(arg):
            s = STRING.fullmatch(part.strip())
            pieces.append((s.group(1) if s.group(1) is not None else s.group(2)) if s else "*")
        path = "".join(pieces)
        if name in helpers and not path.startswith(("/", "*", "http")):
            path = helpers[name] + path
        if path.startswith("/") and not path.startswith("//"):
            glob = _glob(path)
            if glob.strip("*/") and not (name == "fetch" and glob.endswith("/*") and glob.count("*") == 1 and "." not in glob):
                out.add(glob)
        else:  # e.g. fetchJSON(urls.measures || "/data/map/measures.json"): its whole-path literals
            literals = [a or b for a, b in STRING.findall(arg)]
            out.update(_glob(p) for lit in literals if lit.startswith("/") for p in PATH.findall(lit))
    return out


def reads(assets: Path) -> dict[str, set[str]]:
    """{glob: {script names}} for every same-site file the shipped scripts read."""
    out: dict[str, set[str]] = {}
    for name in SCRIPTS:
        path = assets / name
        if not path.is_file():
            continue
        js = path.read_text(encoding="utf-8")
        for glob in header_reads(js) | fetch_reads(js):
            out.setdefault(glob, set()).add(name)
    return out


def missing_reads(site: Path, assets: Path | None = None) -> dict[str, set[str]]:
    """The globs from reads() that match no file under site (read from site/assets unless assets is given)."""
    wanted = reads(assets or site / "assets")
    return {glob: who for glob, who in wanted.items() if not any(p.is_file() for p in site.glob(glob))}


def problems(site: Path) -> list[str]:
    """Every reason site must not ship."""
    out = postcode_problems(site)
    for glob, who in sorted(missing_reads(site).items()):
        out.append(f"nothing matches /{glob}, which {', '.join(sorted(who))} reads")
    stray = apple_double(site)
    if stray:
        out.append(f"{len(stray)} macOS '._*' files (first: {', '.join(stray[:3])})")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_site.py <site_money dir>", file=sys.stderr)
        return 2
    site = Path(argv[1])
    found = problems(site)
    if found:
        print("Deploy aborted: " + "; ".join(found), file=sys.stderr)
        return 1
    count = len(list((site / "data" / "postcodes").glob("*.json")))
    print(f"School Money site check passed: {count:,} postcode districts, every file the scripts read, no '._*' files.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
