"""Match parents' association charities to English schools, high confidence only.

Reads the Charity Commission register extract (two large JSON arrays, streamed) and the
site's school register, and writes pta.json: for each matched school the charities that
raise money for it, newest first, with their annual return history.

A wrong match attributes a charity's money to the wrong school in public, so every rule
here errs towards missing a real PTA rather than inventing one.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

MAIN = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea")
CHARITY_DIR = MAIN / "pipeline/.cache/charity"
SITE_DATA = MAIN / "site/data"
OUT = MAIN / "pipeline/.cache/money/pta.json"
REPORT = Path(__file__).resolve().parent / "REPORT_pta.md"
LICENCE = "Open Government Licence v3.0 (Charity Commission register)"
SOURCE = "Charity Commission register of charities, full extract"

# ----------------------------------------------------------------- names

# Phrases removed before tokenising, so 'C of E' and 'Church of England' cannot leak tokens.
PHRASES = [
    r"church\s+of\s+england", r"\bc\s*\.?\s*of\s*\.?\s*e\b", r"roman\s+catholic",
    r"voluntary\s+(aided|controlled)", r"parent[s']*[\s-]*(teacher|staff)[s']*",
    r"home[\s-]*school", r"pre[\s-]*school", r"all[\s-]*through",
]
GENERIC = {
    "the", "of", "and", "a", "an", "in", "at", "for", "to", "with", "on",
    "school", "schools", "primary", "infant", "infants", "junior", "juniors", "academy",
    "academies", "ce", "cofe", "coe", "rc", "catholic", "voluntary", "aided", "controlled",
    "community", "nursery", "foundation", "federation", "trust", "pta", "ptfa", "pfa", "psa",
    "hsa", "fos", "ptsa", "fsa", "pa", "parent", "parents", "teacher", "teachers", "friend",
    "friends", "association", "assoc", "assn", "staff", "home", "fund", "funds", "st", "saint",
    "college", "high", "secondary", "middle", "first", "lower", "upper", "prep", "preparatory",
    "preschool", "church", "england", "roman", "limited", "ltd", "cio", "charity", "charitable",
    "va", "vc", "jmi", "jm", "ci", "county", "council", "combined", "endowed", "free", "grammar",
    "specialist", "special", "sports", "arts", "science", "technology", "language", "music",
    "learning", "centre", "center", "campus", "group", "society", "committee", "club", "support",
    "supporters", "parentteacher", "pre", "day", "independent", "international", "national",
}
SCHOOL_WORDS = re.compile(
    r"\b(school|schools|primary|infant|infants|junior|juniors|academy|academies|nursery|college|"
    r"pre[\s-]*school|preschool|kindergarten|prep|preparatory|sch)\b", re.I)
# Explicit parents' association markers: enough on their own.
PARENT_MARKERS = re.compile(
    r"\b(pta|ptfa|pfa|psa|hsa|fos|ptsa)\b|parent[s']*[\s-]*(teacher|staff|and\s+friends|&\s+friends|"
    r"teachers|friends|association|assoc)|parents'?\s+association|home[\s-]*school\s+association|"
    r"parent[\s-]*teacher", re.I)
# Weaker markers: only a candidate when the name also mentions a school.
WEAK_MARKERS = re.compile(r"\bfriends\s+of\b|\bschool\s+association\b|\bparents?\b", re.I)
# A charity whose name adds one of these words beside the school's is something else parents run.
EXCLUDED = {"toddler", "playgroup", "play", "scout", "guide", "cub", "brownie", "chapel", "choir", "band", "orchestra",
            "swimming", "pool", "youth", "mosque", "prize", "bursary", "bursarie"}
# Words that say which part of the school system a name belongs to.
PHASE = {"infant", "junior", "nursery", "primary", "first", "middle", "high", "secondary", "grammar",
         "college", "sixth", "upper", "lower", "prep", "senior", "comprehensive"}
INFANT, JUNIOR = {"infant", "nursery"}, {"junior"}
PRIMARY = {"infant", "nursery", "junior", "primary", "first", "middle", "prep", "lower"}
SECONDARY = {"high", "secondary", "grammar", "college", "sixth", "upper", "senior", "comprehensive"}
GENERIC_HOSTS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "pta-events.co.uk", "ptaevents.co.uk",
    "pta-events.com", "classlist.com", "justgiving.com", "localgiving.org", "wix.com", "weebly.com",
    "wordpress.com", "google.com", "sites.google.com", "gov.uk", "charitycommission.gov.uk",
    "linktr.ee", "easyfundraising.org.uk", "parentkind.org.uk", "pta.co.uk", "ptasocial.com",
}


def _tokens(name) -> list[str]:
    """Every word of a name, lowercased, de-possessived, singular, St for Saint."""
    text = str(name or "").lower().replace("&", " and ")
    text = text.replace("’", "'").replace("'s", "").replace("'", "")
    for phrase in PHRASES:
        text = re.sub(phrase, " ", text)
    tokens = []
    for raw in re.findall(r"[a-z0-9]+", text):
        tok = "st" if raw == "saint" else "prep" if raw == "preparatory" else raw
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        tokens.append(tok)
    return tokens


def normalise(name) -> list[str]:
    """Distinctive tokens of a school or charity name, generic words removed."""
    tokens = []
    for tok in _tokens(name):
        if len(tok) < 2 or tok in GENERIC or tok in tokens:
            continue
        tokens.append(tok)
    return tokens


def phase_words(name) -> set[str]:
    """Phase words (infant, junior, high...) in a name."""
    return PHASE & set(_tokens(name))


def phases_conflict(school_phase, charity_phase) -> bool:
    """True when the two names clearly belong to different parts of the system."""
    if not school_phase or not charity_phase or school_phase & charity_phase:
        return False
    return bool((school_phase & INFANT and charity_phase & JUNIOR) or (school_phase & JUNIOR and charity_phase & INFANT)
                or (school_phase & PRIMARY and charity_phase & SECONDARY and not school_phase & SECONDARY)
                or (school_phase & SECONDARY and charity_phase & PRIMARY and not school_phase & PRIMARY))


def is_parent_association(name) -> bool:
    """True when a charity name reads as a school parents' association."""
    text = str(name or "")
    if PARENT_MARKERS.search(text):
        return True
    return bool(WEAK_MARKERS.search(text) and SCHOOL_WORDS.search(text))


# ------------------------------------------------------------- postcodes

def norm_postcode(raw) -> str | None:
    text = re.sub(r"\s+", "", str(raw or "")).upper()
    return text if re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}", text) else None


def postcode_parts(pc) -> tuple[str, str]:
    """(district, sector) of a normalised postcode."""
    return pc[:-3], pc[:-2]


def domain(url) -> str | None:
    """Registrable host of a website, ignoring www. and known generic hosts."""
    text = str(url or "").strip().lower()
    if not text:
        return None
    if "://" not in text:
        text = "http://" + text
    host = (urlsplit(text).hostname or "").strip(".")
    host = host[4:] if host.startswith("www.") else host
    if "." not in host or host in GENERIC_HOSTS or any(host.endswith("." + g) for g in GENERIC_HOSTS):
        return None
    return host


# ----------------------------------------------------------------- match

def _date(raw):
    return str(raw)[:10] if raw else None


def _school_record(school):
    pc = norm_postcode(school.get("postcode"))
    district, sector = postcode_parts(pc) if pc else (None, None)
    place = " ".join(str(school.get(k) or "") for k in ("town", "locality", "street", "council"))
    return {
        "urn": str(school["urn"]), "name": school.get("name") or "", "tokens": normalise(school.get("name")),
        "phase": phase_words(school.get("name")), "place": set(normalise(place)),
        "postcode": pc, "district": district, "sector": sector, "domain": domain(school.get("website")),
    }


def _charity_record(charity, method, evidence):
    return {
        "charity_number": int(charity["registered_charity_number"]),
        "name": charity.get("charity_name") or "",
        "status": charity.get("charity_registration_status") or "",
        "registered": _date(charity.get("date_of_registration")),
        "removed": _date(charity.get("date_of_removal")),
        "latest_income": charity.get("latest_income"),
        "history": [],
        "match": {"method": method, "evidence": evidence},
    }


def match(schools, charities):
    """Pure matcher: (matches by urn, rejections). Schools and charities are raw dicts."""
    recs = [r for r in (_school_record(s) for s in schools if not _closed(s)) if r["tokens"]]
    by_postcode, by_sector, by_domain, by_district = (defaultdict(list) for _ in range(4))
    for r in recs:
        if r["postcode"]:
            by_postcode[r["postcode"]].append(r)
            by_sector[r["sector"]].append(r)
            by_district[r["district"]].append(r)
        if r["domain"]:
            by_domain[r["domain"]].append(r)

    matches = defaultdict(list)
    rejections = []
    seen = {}  # charity number -> urn, to catch one charity matching several schools

    def reject(charity, reason, names):
        rejections.append({"charity_number": int(charity["registered_charity_number"]),
                           "charity": charity.get("charity_name") or "", "reason": reason, "schools": names})

    for charity in charities:
        if charity.get("linked_charity_number", 0) not in (0, 1) or not is_parent_association(charity.get("charity_name")):
            continue
        ctokens = set(normalise(charity.get("charity_name")))
        if not ctokens:
            continue
        cphase = phase_words(charity.get("charity_name"))
        pc = norm_postcode(charity.get("charity_contact_postcode"))
        host = domain(charity.get("charity_contact_web"))

        def fits(r):
            return (set(r["tokens"]) <= ctokens and not phases_conflict(r["phase"], cphase)
                    and not (ctokens - set(r["tokens"])) & EXCLUDED)

        candidates = {}
        if pc:
            for r in by_postcode.get(pc, []):
                if fits(r):
                    candidates[r["urn"]] = (r, "postcode", f"tokens {','.join(r['tokens'])}; postcode {pc}")
            for r in by_sector.get(pc[:-2], []):
                if r["urn"] in candidates or not fits(r):
                    continue
                # A sector is a weaker signal: the charity must name only the school (plus its own place names),
                # and no other school in the district may carry the same distinctive name.
                if ctokens - set(r["tokens"]) - r["place"]:
                    continue
                if any(o is not r and set(o["tokens"]) == set(r["tokens"]) for o in by_district[r["district"]]):
                    continue
                candidates[r["urn"]] = (r, "sector", f"tokens {','.join(r['tokens'])}; sector {pc[:-2]}, unique in {r['district']}")
        if host:
            for r in by_domain.get(host, []):
                if r["urn"] not in candidates and fits(r):
                    candidates[r["urn"]] = (r, "website", f"tokens {','.join(r['tokens'])}; website {host}")
        if not candidates:
            continue

        # The most specific candidates, plus anything else in their districts whose name also fits the
        # charity with at least as many distinctive words ('Park Primary' never blocks 'Whitelands Park Primary').
        best = max(len(c[0]["tokens"]) for c in candidates.values())
        candidates = {urn: c for urn, c in candidates.items() if len(c[0]["tokens"]) == best}
        tied = {urn: c[0] for urn, c in candidates.items()}
        for r, _, _ in candidates.values():
            for o in by_district.get(r["district"], []):
                if o["urn"] not in tied and set(o["tokens"]) <= ctokens and len(o["tokens"]) >= best:
                    tied[o["urn"]] = o
        chosen = None
        if len(tied) == 1:
            chosen, = candidates
        elif cphase:
            # 'X Junior School PTA' settles an infant/junior tie when exactly one school carries the phase words.
            survivors = [urn for urn, o in tied.items() if o["phase"] and o["phase"] <= cphase]
            if len(survivors) == 1 and survivors[0] in candidates:
                chosen = survivors[0]
        if chosen is None:
            reason = "charity fits several schools" if len(candidates) > 1 else "another school in the district also fits"
            reject(charity, reason, [o["name"] for o in tied.values()])
            continue
        r, method, evidence = candidates[chosen]
        if len(tied) > 1:
            evidence += f"; phase {','.join(sorted(cphase))} rules out {len(tied) - 1}"
        number = int(charity["registered_charity_number"])
        if number in seen and seen[number] != r["urn"]:
            reject(charity, "charity fits several schools", [seen[number], r["name"]])
            matches[seen[number]] = [c for c in matches[seen[number]] if c["charity_number"] != number]
            continue
        seen[number] = r["urn"]
        matches[r["urn"]].append(_charity_record(charity, method, evidence))
    for urn in list(matches):
        matches[urn].sort(key=lambda c: c["registered"] or "", reverse=True)
        if not matches[urn]:
            del matches[urn]
    return dict(matches), rejections


def _closed(school) -> bool:
    return "closed" in str(school.get("status") or "").lower()


# --------------------------------------------------------------- streams

_SKIP = re.compile(r"[\s,]*")


def iter_json_array(path, chunk_size=1 << 20):
    """Yield each object of a JSON array file without loading the whole file."""
    decoder = json.JSONDecoder()
    with open(path, encoding="utf-8-sig") as f:
        buf, pos, started = f.read(chunk_size), 0, False
        while True:
            pos = _SKIP.match(buf, pos).end()
            if pos >= len(buf):
                more = f.read(chunk_size)
                if not more:
                    return
                buf, pos = buf[pos:] + more, 0
                continue
            if buf[pos] == "[" and not started:
                started, pos = True, pos + 1
                continue
            if buf[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except json.JSONDecodeError:
                more = f.read(chunk_size)
                if not more:
                    raise ValueError(f"truncated JSON array in {path}")
                buf, pos = buf[pos:] + more, 0
                continue
            pos = end
            yield obj


def load_schools(site_data):
    """All open schools from every council's register."""
    las = Path(site_data) / "england/las.json"
    councils = {str(la["la_code"]): la["name"] for la in json.loads(las.read_text(encoding="utf-8")).get("las", [])} if las.exists() else {}
    schools = []
    for path in sorted(Path(site_data).glob("la/*/schools.json")):
        for school in json.loads(path.read_text(encoding="utf-8")).get("schools", []):
            school.setdefault("council", councils.get(path.parent.name))
            schools.append(school)
    return schools


def iter_candidates(charity_path):
    """Main charities whose name reads as a parents' association."""
    for obj in iter_json_array(charity_path):
        if obj.get("linked_charity_number", 0) in (0, 1) and is_parent_association(obj.get("charity_name")):
            yield obj


def attach_history(matches, returns):
    """Fill each matched charity's history from annual return rows (any iterable of dicts)."""
    wanted = defaultdict(list)
    for charities in matches.values():
        for c in charities:
            wanted[c["charity_number"]].append(c)
    if not wanted:
        return
    rows = defaultdict(dict)
    for ret in returns:
        number = ret.get("registered_charity_number")
        if number not in wanted or not ret.get("fin_period_end_date"):
            continue
        period = str(ret["fin_period_end_date"])[:7]
        suppressed = bool(ret.get("suppression_ind"))
        row = {"period_end": period,
               "income": None if suppressed else ret.get("total_gross_income"),
               "expenditure": None if suppressed else ret.get("total_gross_expenditure")}
        if period not in rows[number] or rows[number][period]["income"] is None:
            rows[number][period] = row
    for number, charities in wanted.items():
        history = sorted(rows[number].values(), key=lambda h: h["period_end"], reverse=True)
        for c in charities:
            c["history"] = history


# ---------------------------------------------------------------- report

def report(matches, rejections, candidate_count, schools_by_urn, seed, seconds):
    pairs = [(schools_by_urn.get(urn, urn), c) for urn, cs in matches.items() for c in cs]
    methods = defaultdict(int)
    for _, c in pairs:
        methods[c["match"]["method"]] += 1
    sample = random.Random(seed).sample(pairs, min(40, len(pairs)))
    lines = [
        "# PTA matching report", "",
        f"Generated {date.today().isoformat()} by `pipeline/money/pta.py` (seed {seed}, {seconds:.0f}s).", "",
        f"- Candidate charities (main, parents' association by name): {candidate_count:,}",
        f"- Schools matched: {len(matches):,}",
        f"- Charities matched: {len(pairs):,}",
        "- By method: " + ", ".join(f"{m} {n:,}" for m, n in sorted(methods.items())),
        f"- Ambiguity rejections: {len(rejections):,}", "",
        f"## {len(sample)} random matches for review", "",
        "| school | charity | method |", "|---|---|---|",
    ]
    lines += [f"| {s} | {c['name']} ({c['charity_number']}) | {c['match']['method']} |" for s, c in sample]
    lines += ["", f"## Ambiguity rejections ({len(rejections):,})", ""]
    lines += [f"- {r['charity']} ({r['charity_number']}): {r['reason']}: {'; '.join(r['schools'])}" for r in rejections[:20]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--charity-dir", type=Path, default=CHARITY_DIR)
    parser.add_argument("--site-data", type=Path, default=SITE_DATA)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    start = time.time()

    schools = load_schools(args.site_data)
    candidates = list(iter_candidates(args.charity_dir / "publicextract.charity.json"))
    print(f"{len(schools):,} schools, {len(candidates):,} candidate charities ({time.time() - start:.0f}s)")
    matches, rejections = match(schools, candidates)
    print(f"{len(matches):,} schools matched, {len(rejections):,} rejected ({time.time() - start:.0f}s)")
    attach_history(matches, iter_json_array(args.charity_dir / "publicextract.charity_annual_return_history.json"))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"generated": date.today().isoformat(), "source": SOURCE, "licence": LICENCE,
                                    "schools": matches}, indent=1), encoding="utf-8")
    names = {str(s["urn"]): s.get("name") or str(s["urn"]) for s in schools}
    args.report.write_text(report(matches, rejections, len(candidates), names, args.seed, time.time() - start), encoding="utf-8")
    print(f"wrote {args.out} and {args.report} ({time.time() - start:.0f}s)")


if __name__ == "__main__":
    main()
