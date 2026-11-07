"""Ask a local model to settle ambiguous PTA -> school matches, keeping only name-consistent answers.

Reads pta_ambiguous.jsonl (one charity and its candidate schools per line), asks an OpenAI-compatible
server (LM Studio by default) for one JSON answer per charity, and writes pta_llm.json for pta.py to
merge with method "llm". The model is never trusted on its own: an answer counts only when its
confidence is a real probability of at least 0.9, the chosen urn is one of the candidates, and the
pilot's deterministic guard (name_consistent, copied verbatim from llm_pilot.py) passes; the pilot
found the model's confidence useless as a filter and this guard doing the real work. Answers
checkpoint to a JSONL file as they arrive, so a stopped run resumes where it left off.

Safety: the model must already be loaded, as LM Studio's model-state endpoint confirms (never JIT; a server
that cannot confirm it is refused); mistral-medium-3.5-128b and anything whose id or
metadata says more than 40B parameters or 40 GB is refused; the run stops below 15% free memory,
checked every 10 answers.

Subcommands:
  run           adjudicate the ambiguous file (prompt v1, temperature 0, reasoning_effort "none", 2 slots)
  import-pilot  turn the pilot's full run (llm_pilot.py JSONL) into pta_llm.json, recomputing nothing
  sample        write 50 random accepted picks to pta_llm_review.md for a person to judge
  spot-check    record the judged sample in pta_llm.json; pta.py merges only when n >= 50 and wrong == 0
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import math
import random
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from pipeline.money import pta

MONEY_DIR = Path("/Users/jhammant/dev/personal/SchoolCatchmentArea/pipeline/.cache/money")
AMBIGUOUS = MONEY_DIR / "pta_ambiguous.jsonl"
OUT = MONEY_DIR / "pta_llm.json"
CHECKPOINT = MONEY_DIR / "pta_llm.checkpoint.jsonl"
REVIEW = MONEY_DIR / "pta_llm_review.md"
# The overnight pilot's full run (llm_pilot.py, guard and prompt v1) and the rows it was given.
OVERNIGHT = Path("/private/tmp/claude-501/-Users-jhammant-dev/3787c852-6591-4a87-b978-00c39c16a567/scratchpad/overnight")
PILOT_RUN = OVERNIGHT / "llm_pilot_runs/full_qwen38.jsonl"
PILOT_INPUT = OVERNIGHT / "llm_full_input.jsonl"
SERVER = "http://localhost:1234/v1"
MODEL = "qwen/qwen3.8-27b"
BLOCKLIST = {"mistral-medium-3.5-128b"}
THRESHOLD = 0.9            # a sanity floor, not a discriminator: every v1 pick came back at 0.95 or more
MAX_PARAMS_B = 40          # refuse models over ~40B parameters
MAX_BYTES = 40 * 10**9     # or over ~40 GB
PROMPT_VERSION = "v1"
MAX_TOKENS = 400
SLOTS = 2                  # parallel requests; URNs were identical at 1 and 2 slots in the pilot
MIN_FREE = 15              # stop below this percentage of free memory
MEM_EVERY = 10             # answers between memory checks
SAMPLE_N = 50

# Prompt v1, verbatim from llm_pilot.py (SYSTEM_PROMPT_V1). Keep it identical and first in every request: LM Studio
# reuses the cached prefix.
SYSTEM_PROMPT_V1 = """\
You match school parent associations (PTA, PTFA, PFA, PSA, "Friends of ...") \
from the Charity Commission register of England and Wales to the \
state-funded school they raise money for. You get one charity and a short \
list of candidate schools from the DfE register. Pick the candidate this \
charity supports, or null.

How to decide:
1. The school named in the charity's name, objects or area of benefit must \
match the candidate's current or former name in its distinctive words. A \
shared town, council or saint's name alone is not a match: "St Mary's" in \
one town is not "St Mary's" in another.
2. Location must fit. Compare the charity's address, postcode, area of \
benefit and council areas with the candidate's town and postcode. A place \
word left over in the charity name that is not the candidate's place points \
to a different school.
3. Phase must fit. An Infant PTA is not a Junior school's, a Primary PTA is \
not a secondary school's, a High School or Grammar School PTA is not a \
primary's.
4. A former name of a candidate counts as a match when the charity is older \
than the rename.
5. Return null when: the charity probably supports an independent (private) \
school, especially one listed under "independent schools with a fitting \
name"; the school it names is not in the list (closed, renamed beyond \
recognition, or in another town); two or more candidates fit equally well; \
the charity is not a parent association of one school (music, sport, \
minibus, playgroup, alumni, a federation of several schools); or the \
evidence is too thin.
6. If the charity serves two listed schools jointly (for example "X Infant \
and Junior Schools PTA"), return null and start the reason with "shared:" \
followed by both URNs.
7. A school can have had several parent-association charities over the \
years, so a candidate that already has a matched PTA is still allowed.

confidence is your probability that the chosen urn is right. Give 0.9 or \
more only when name, location and phase all clearly fit and no other \
candidate is plausible. With urn null, confidence is how sure you are that \
none of the candidates is this charity's school.

Answer with one JSON object only, no other text:
{"urn": "<urn>" or null, "confidence": <number 0-1>, "reason": "<one short sentence>"}"""

SYSTEM_PROMPT = SYSTEM_PROMPT_V1


class ModelRefused(RuntimeError):
    """The requested model is missing, not loaded, blocklisted or too large to run safely."""


# ------------------------------------------------------------------ HTTP

def post_json(url, payload=None, timeout=120):
    """The one HTTP call: POST payload as JSON (GET when payload is None) and return the decoded body."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ----------------------------------------------------------- model check

BYTE_UNITS = {"": 1, "b": 1, "byte": 1, "bytes": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
              "kib": 2**10, "mib": 2**20, "gib": 2**30, "tib": 2**40}
PARAM_UNITS = {"": 1, "k": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12, "trillion": 1e12}
AMOUNT = re.compile(r"\s*(?:(\d+)\s*x\s*)?(\d+(?:\.\d+)?)\s*([a-z]*)\s*")


def _amount(value, units, default_unit=""):
    """A size or parameter count as a float from a number or a string like '70B', '8x7B' or '55 GB'; None otherwise."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) * units[default_unit] if math.isfinite(value) else None
    m = AMOUNT.fullmatch(str(value).lower().replace(",", ""))
    if not m or (m.group(3) or default_unit) not in units:
        return None
    return float(m.group(2)) * int(m.group(1) or 1) * units[m.group(3) or default_unit]


def _leaves(info, prefix=""):
    """(dotted key path, value) for every scalar in a nested model-metadata dict or list."""
    items = info.items() if isinstance(info, dict) else enumerate(info) if isinstance(info, list) else ()
    for key, value in items:
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, (dict, list)):
            yield from _leaves(value, path)
        else:
            yield path, value


def model_too_big(info) -> str | None:
    """Why a /v1/models entry is over the cap, or None. Reads the id ('...-128b', '8x22b') and every size or parameter
    field, nested or not, as numbers or strings: size_gb 55, sizeBytes, metadata.size_bytes, parameters '70B'."""
    model_id = str(info.get("id") or "")
    for m in re.finditer(r"(?<![a-z0-9.])(?:(\d+)x)?(\d+(?:\.\d+)?)b(?![a-z0-9])", model_id, re.I):
        if float(m.group(2)) * int(m.group(1) or 1) > MAX_PARAMS_B:
            return f"id says {m.group(0)} parameters"
    for path, value in _leaves(info):
        key = path.rsplit(".", 1)[-1].lower()
        if "param" in key:
            n = _amount(value, PARAM_UNITS)
            # a bare number under 1,000 is in billions ('parameters': 70); above that it is a count
            if n is not None and (n > MAX_PARAMS_B * 1e9 or (isinstance(value, (int, float)) and 1000 > n > MAX_PARAMS_B)):
                return f"{path} = {value}"
        elif "size" in key or "bytes" in key:
            unit = re.search(r"(kib|mib|gib|tib|kb|mb|gb|tb)$", key)
            n = _amount(value, BYTE_UNITS, unit.group(1) if unit else "")
            if n is not None and n > MAX_BYTES:
                return f"{path} = {n / 1e9:.0f} GB"
    return None


def _lmstudio_entry(server, model):
    """LM Studio's richer /api/v0/models entry for the model (it carries 'state'), or None when unavailable."""
    root = server.rstrip("/").rsplit("/v1", 1)[0]
    try:
        data = post_json(root + "/api/v0/models", timeout=30)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return next((m for m in (data or {}).get("data", []) if isinstance(m, dict) and str(m.get("id")) == model), None)


def check_model(server, model):
    """Confirm the model is listed by /v1/models, loaded, not blocklisted and under the size cap; raise ModelRefused
    otherwise. Never asks the server to load anything.

    Fails closed: with JIT loading on, /v1/models also lists models that are only downloaded, so a listing alone is
    no proof. LM Studio's model-state endpoint (/api/v0/models) must answer and list the model too, and every state
    either listing reports must be 'loaded'. A server without that endpoint, or one that is down, is refused."""
    if model in BLOCKLIST:
        raise ModelRefused(f"refusing blocklisted model {model}")
    try:
        data = post_json(server.rstrip("/") + "/models", timeout=30)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ModelRefused(f"cannot list models at {server}: {exc}") from exc
    models = {str(m.get("id")): m for m in (data or {}).get("data", []) if isinstance(m, dict)}
    if model not in models:
        raise ModelRefused(f"{model} is not on the server (have: {', '.join(sorted(models)) or 'none'}); load it first, never JIT")
    extra = _lmstudio_entry(server, model)
    for info in (models[model], extra or {}):
        reason = model_too_big(info)
        if reason:
            raise ModelRefused(f"refusing {model}: {reason}, over the ~{MAX_PARAMS_B}B / {MAX_BYTES // 10**9} GB cap")
    if extra is None:
        raise ModelRefused(f"cannot confirm {model} is loaded: the model-state endpoint (/api/v0/models) is unavailable "
                           "or does not list it; refusing rather than risk a JIT load")
    for state in (models[model].get("state"), extra.get("state")):
        if state is not None and state != "loaded":
            raise ModelRefused(f"{model} is {state}, not loaded; load it first (lms load {model} --parallel {SLOTS}), never JIT")
    return models[model]


# ---------------------------------------------------------------- prompt

def _clip(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def money(v):
    if v is None:
        return "not known"
    return f"£{v:,.0f}"


def user_prompt(row) -> str:
    """The pilot's v1 user message (llm_pilot.user_prompt(row, 'v1'))."""
    lines = [f"Charity {row['charity_number']}: {row.get('charity_name') or ''}"]
    if row.get("status") == "Removed":
        lines.append(
            f"Status: removed from the register {row.get('removed') or '(date unknown)'}"
            " (removed charities lose their address)"
        )
    else:
        lines.append("Status: registered")
    lines.append(f"Objects: {_clip(row.get('objects'), 700) or '(none)'}")
    lines.append(f"Area of benefit: {_clip(row.get('area_of_benefit'), 200) or '(none)'}")
    lines.append(f"Council areas of operation: {', '.join(row.get('area') or []) or '(none)'}")
    addr = ", ".join(row.get("address") or [])
    pc = row.get("postcode")
    lines.append(f"Address: {addr or '(none)'}{' ' + pc if pc else ''}")
    lines.append(f"Latest income: {money(row.get('latest_income'))}")
    ind = row.get("also_fits_independent") or []
    if ind:
        lines.append(
            "Independent schools with a fitting name in the area (not candidates): "
            + "; ".join(ind)
        )
    lines.append("")
    lines.append("Candidate state-funded schools:")
    for c in row.get("candidates", []):
        bits = [f"URN {c['urn']}: {c.get('name') or ''}", c.get("phase") or "phase not given"]
        bits.append(" ".join(x for x in (c.get("town"), c.get("postcode")) if x) or "place not given")
        preds = [p for p in (c.get("predecessor_names") or []) if p and p != c.get("name")]
        if preds:
            bits.append("former names: " + "; ".join(preds))
        bits.append("already has a matched PTA" if c.get("already_matched") else "no PTA matched yet")
        lines.append("- " + " | ".join(bits))
    return "\n".join(lines)


THINK = re.compile(r"<think>.*?</think>", re.S)


def valid_confidence(value):
    """A model confidence as a finite real number in 0..1, else None: True, 95 (a percentage), 1.01 and Infinity are
    not probabilities, and None never reaches the threshold or the JSON output as Infinity."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and 0 <= x <= 1 else None


def parse_answer(text):
    """{"urn", "confidence", "reason"} from the model's text, or None when no JSON object can be read."""
    text = THINK.sub("", str(text or "")).strip()
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text).strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])  # tolerates trailing junk such as a stray "}"
    except ValueError:
        return None
    if not isinstance(obj, dict) or "urn" not in obj:
        return None
    urn = obj.get("urn")
    if urn is not None:
        urn = str(urn).strip()
        if urn.lower() in ("", "null", "none"):
            urn = None
    return {"urn": urn, "confidence": valid_confidence(obj.get("confidence")), "reason": str(obj.get("reason") or "")}


# ------------------------------------------------------------ acceptance
# The pilot's deterministic guard, verbatim from llm_pilot.py: name_consistent() and its helpers.

GENERIC = set(
    """
    the of and for at in on to a an with by
    school schools primary junior juniors infant infants nursery academy academies
    college secondary first middle upper lower all through allthrough
    friends friend pta ptfa pfa psa pa ptsa fsa ftsa association associations assoc
    parent parents parental teacher teachers staff society fund funds trust trusts
    charity charitable cio committee group council supporters support
    church england ce c e cofe coe voluntary aided controlled va vc
    rc roman catholic methodist community foundation federation federated
    learning centre center partnership free studio campus site
    st saint saints s pupil pupils home governors district associate associates
    incorporated limited ltd inc
    """.split()
)
# Words that may be shared by unrelated schools: on their own they never make
# a name match (a saint's name, a royal or religious word, a landscape or
# compass word). Any word straight after "St"/"Saint" also counts as weak.
WEAK = set(
    """
    hill heath park green field wood grove house lane road street bridge brook
    vale valley common meadow farm mill gate end cross way water lake bank
    north south east west central upper lower new old great little high
    christ church holy trinity sacred heart lady our all angel blessed
    immaculate conception assumption redeemer good shepherd emmanuel rosary
    spirit family martyr queen king royal prince princess duke boy girl
    mary john peter paul joseph jame andrew george michael mark luke matthew
    thomas patrick anne margaret nichola bartholomew edward alban augustine
    francis teresa bernadette catherine helen hilda chad cuthbert oswald
    aidan wilfrid bede dunstan gregory benedict dominic vincent anthony
    stephen philip barnaba lawrence leonard martin giles swithun christopher
    saviour mark elizabeth clement nicolas
    """.split()
)
PHASE_WORDS = {
    "infant": "infant", "infants": "infant",
    "junior": "junior", "juniors": "junior",
    "primary": "primary",
    "nursery": "nursery",
    "secondary": "secondary", "high": "secondary", "grammar": "secondary",
    "upper": "secondary",
}


def words(text):
    text = (text or "").lower().replace("’", "'")
    text = re.sub(r"s'(?=[a-z])", "s ", text)  # PARENTS'ASSOCIATION -> parents association
    text = text.replace("'", "")
    return re.findall(r"[a-z0-9]+", text)


def singular(w):
    if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def distinctive(text):
    return {singular(w) for w in words(text) if w not in GENERIC and not w.isdigit()}


def saint_names(text):
    ws = words(text)
    return {singular(ws[i + 1]) for i, w in enumerate(ws[:-1]) if w in ("st", "saint")}


def strong(tokens, text=""):
    return {t for t in tokens if t not in WEAK} - saint_names(text)


def phases(text):
    return {PHASE_WORDS[w] for w in words(text) if w in PHASE_WORDS}


def phase_conflict(charity_name, cand):
    cp = phases(charity_name)
    sp = phases(cand["name"])
    gias = (cand.get("phase") or "").lower()
    if gias.startswith("primary"):
        sp |= {"primary"}
    elif gias.startswith("secondary"):
        sp |= {"secondary"}
    if not cp or not sp:
        return False
    if "infant" in cp and "junior" in sp and "infant" not in sp:
        return True
    if "junior" in cp and "infant" in sp and "junior" not in sp:
        return True
    if cp & {"infant", "junior", "primary"} and sp == {"secondary"}:
        return True
    if "secondary" in cp and not cp & {"infant", "junior", "primary"} and sp <= {
        "primary", "infant", "junior", "nursery"
    }:
        return True
    return False


def name_consistent(row, urn):
    """True when the chosen school's name (current or former) visibly fits the
    charity's own text: they share a strong word (or the school's whole
    distinctive name is in the charity text), the phases do not conflict, and
    no word in the charity name is left unexplained by the school's names,
    town or the charity's council areas."""
    cand = next((c for c in row["candidates"] if c["urn"] == urn), None)
    if cand is None:
        return False, "urn not a candidate"
    text = " ".join(
        [row.get("charity_name") or "", row.get("objects") or "",
         row.get("area_of_benefit") or "", " ".join(row.get("address") or [])]
    )
    ctoks = distinctive(text)
    names = [cand["name"]] + [p for p in (cand.get("predecessor_names") or []) if p]
    fits = False
    for n in names:
        d = distinctive(n)
        shared = d & ctoks
        if d and (shared == d or strong(shared, n + " " + text)):
            fits = True
            break
    if not fits:
        return False, "no strong shared name word"
    if phase_conflict(row["charity_name"], cand):
        return False, "phase conflict"
    explained = set()
    for n in names:
        explained |= distinctive(n)
    explained |= distinctive(cand.get("town")) | distinctive(" ".join(row.get("area") or []))
    # A charity address in the school's own postcode district explains the
    # place words in it (e.g. "... PRIMARY SCHOOL (YATE)" with a BS37 address).
    if same_district(row.get("postcode"), cand.get("postcode")):
        explained |= distinctive(" ".join(row.get("address") or []))
    name = row["charity_name"]
    leftover = {
        t for t in distinctive(name) - explained
        if not is_initialism(t, name)
        and not any(len(t) >= 3 and e.startswith(t) for e in explained)  # ALEX -> Alexander
    }
    if leftover:
        return False, "leftover: " + " ".join(sorted(leftover))
    # Two candidates carrying the same matching former name: the lineage is
    # ambiguous (e.g. one closed school split between two academies).
    for n in names[1:]:
        d = distinctive(n)
        if d and d <= ctoks:
            others = [c for c in row["candidates"] if c["urn"] != urn and n in (c.get("predecessor_names") or [])]
            others = [c for c in others if not (same_district(row.get("postcode"), cand.get("postcode"))
                                                and not same_district(row.get("postcode"), c.get("postcode")))]
            if others and not (distinctive(cand["name"]) & ctoks - WEAK):
                return False, "former name shared with " + others[0]["urn"]
    # The charity's address names a school: the chosen school must be that one.
    for line in row.get("address") or []:
        if not re.search(r"\b(school|academy|college|primary|infant|junior)", line, re.I):
            continue
        d = distinctive(line)
        if d and not d <= explained | distinctive(cand.get("town")):
            return False, f"address names another school: {line}"
        if phase_conflict(line, cand):
            return False, f"address phase conflict: {line}"
    # An independent school explains the charity's name better than the
    # candidate (e.g. "Friends of Tettenhall College" vs Tettenhall Wood School).
    name_toks = distinctive(name)
    cand_fully = any(distinctive(n) and distinctive(n) <= name_toks for n in names)
    for ind in row.get("also_fits_independent") or []:
        d = distinctive(ind)
        if d and d <= name_toks and not cand_fully:
            return False, f"independent namesake fits better: {ind}"
    # Only weak words (a saint, Trinity, Hill...) tie the name to the school:
    # then any place named in the area of benefit or the charity's town must
    # be the school's place, unless the postcode district already matches.
    best_strong = set()
    for n in names:
        best_strong |= strong(distinctive(n) & ctoks, n + " " + text)
    if not best_strong and not same_district(row.get("postcode"), cand.get("postcode")):
        places = distinctive(" ".join([row.get("area_of_benefit") or "", row.get("town") or ""]))
        places -= AOB_GENERIC | name_toks | explained
        places = {t for t in places if t not in WEAK and len(t) > 2}
        if places:
            return False, "weak name match, place not the school's: " + " ".join(sorted(places))
    return True, "ok"


AOB_GENERIC = set(
    """
    not defined undefined in practice practise catchment area areas of the school
    schools local locally but normally and for pupils parents uk england wales
    national borough london county city parish town village district ward
    surrounding its which is are at to by who attend attending beneficiary
    beneficiaries no restriction environs neighbourhood community nationwide
    there it or with any
    """.split()
)


def district(pc):
    pc = (pc or "").upper().replace(" ", "")
    return pc[:-3] if len(pc) >= 5 else None


def same_district(a, b):
    da, db = district(a), district(b)
    return bool(da and db and da == db)


def is_initialism(token, name):
    """TEPTA, FOIS, LPSA: a bracketed short token built from the name's letters,
    starting with the name's first letter."""
    if not re.search(r"\(\s*" + re.escape(token) + r"\s*\)", name.lower()):
        return False
    if not (2 <= len(token) <= 7) or not token.isalpha():
        return False
    rest = "".join(words(re.sub(r"\(.*?\)", " ", name)))
    if not rest or rest[0] != token[0]:
        return False
    it = iter(rest[1:])
    return all(ch in it for ch in token[1:])


def judge(answer, row, threshold):
    """Decorate a parsed answer with name_consistent and accepted. A 'shared:' answer is never accepted here, even when
    the model also filled in an urn: pta.py's deterministic shared step decides it."""
    out = {"urn": None, "confidence": None, "reason": "unparseable answer", "name_consistent": False, "accepted": False}
    if not answer:
        return out
    out.update(urn=answer.get("urn"), confidence=valid_confidence(answer.get("confidence")), reason=answer.get("reason") or "")
    if out["urn"] is None or out["confidence"] is None or pta.is_shared_answer(out):
        return out
    ok, why = name_consistent(row, out["urn"])
    out["name_consistent"] = ok
    if not ok:
        out["reason"] = f"{out['reason']} [guard: {why}]".strip()
    out["accepted"] = bool(ok and out["confidence"] >= threshold)
    return out


# ---------------------------------------------------------------- memory

def memory_free_pct():
    """Percent of memory free from macOS memory_pressure (the pilot's probe), or None when it cannot be read."""
    try:
        out = subprocess.run(
            ["memory_pressure"], capture_output=True, text=True, timeout=30
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"System-wide memory free percentage:\s*(\d+)%", out)
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------- run

def ask(server, model, row, timeout=120):
    """One chat completion; returns the model's raw text (content, else reasoning_content)."""
    payload = {"model": model, "temperature": 0, "max_tokens": MAX_TOKENS, "reasoning_effort": "none",
               "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt(row)}]}
    data = post_json(server.rstrip("/") + "/chat/completions", payload, timeout)
    choice = ((data or {}).get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return message.get("content") or message.get("reasoning_content") or ""


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _jsonl_records(path):
    """(records, unreadable line count) of a JSONL file that may end in a half-written line."""
    records, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if isinstance(rec, dict) and str(rec.get("charity_number", "")).isdigit():
                records.append(rec)
            else:
                bad += 1
    return records, bad


def repair_checkpoint(path) -> int:
    """Drop unreadable lines (a run stopped mid-write leaves a partial last line) so appends start on a clean line.
    Returns the number of lines dropped."""
    path = Path(path)
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    records, bad = _jsonl_records(path)
    if bad or (text and not text.endswith("\n")):
        pta.write_atomic(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return bad


def load_checkpoint(path, model, prompt_version):
    """charity number (int) -> checkpoint line, for answers given by this model and prompt; unreadable lines skipped."""
    path = Path(path)
    if not path.exists():
        return {}
    records, _ = _jsonl_records(path)
    return {int(r["charity_number"]): r for r in records
            if r.get("model") == model and r.get("prompt_version") == prompt_version and not r.get("error")}


def build_output(records, rows, model, server, threshold):
    """pta_llm.json contents from checkpoint records, judged against the rows at the current threshold."""
    by_number = {int(r["charity_number"]): r for r in rows}
    answers = {}
    for number, rec in sorted(records.items()):
        row = by_number.get(number)
        if row is None:
            continue
        answers[str(number)] = judge(parse_answer(rec.get("raw")), row, threshold)
    return {"generated": date.today().isoformat(), "model": model, "server": server, "prompt_version": PROMPT_VERSION,
            "threshold": threshold, "answers": answers}


def write_json(path, data):
    """Atomic JSON write that refuses NaN and Infinity."""
    pta.write_atomic(path, json.dumps(data, indent=1, ensure_ascii=False, allow_nan=False))


def run(rows, *, server=SERVER, model=MODEL, threshold=THRESHOLD, checkpoint=CHECKPOINT, out=OUT, limit=0,
        prioritise_recent=False, timeout=120, log=print, slots=SLOTS, memory_probe=memory_free_pct, min_free=MIN_FREE,
        mem_every=MEM_EVERY):
    """Adjudicate rows (resuming from the checkpoint), write out, and return the pta_llm.json dict.

    Checks the model first (check_model) and free memory before the run and every mem_every answers through
    memory_probe (a callable returning percent free, or None when unknown); below min_free it stops cleanly and the
    next run resumes from the checkpoint. With slots > 1, that many requests run at once.
    """
    check_model(server, model)
    dropped = repair_checkpoint(checkpoint)
    if dropped:
        log(f"checkpoint: dropped {dropped} unreadable line(s) left by an interrupted run")
    done = load_checkpoint(checkpoint, model, PROMPT_VERSION)
    todo = [r for r in rows if int(r["charity_number"]) not in done]
    if prioritise_recent:
        todo.sort(key=lambda r: -(r.get("recent_returns") or 0))
    if limit:
        todo = todo[:limit]
    stop = threading.Event()
    free = memory_probe()
    if free is not None and free < min_free:
        log(f"stop: memory free {free}% is under {min_free}%; asking nothing")
        stop.set()
    log(f"{len(rows)} rows, {len(done)} already answered, asking {0 if stop.is_set() else len(todo)}")
    Path(checkpoint).parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    count = [0]
    start = time.time()
    with open(checkpoint, "a", encoding="utf-8") as f:

        def work(row):
            if stop.is_set():
                return
            number = int(row["charity_number"])
            try:
                raw = ask(server, model, row, timeout)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                log(f"  {number}: request failed ({exc}); will retry on the next run")
                return
            rec = {"charity_number": number, "model": model, "prompt_version": PROMPT_VERSION, "raw": raw,
                   "asked": date.today().isoformat()}
            with lock:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                done[number] = rec
                count[0] += 1
                i = count[0]
                if i % 25 == 0 or i == len(todo):
                    verdict = judge(parse_answer(raw), row, threshold)
                    log(f"  {i}/{len(todo)} ({(time.time() - start) / i:.1f}s each); last: {number} -> {verdict['urn']} accepted={verdict['accepted']}")
                if i % mem_every == 0:
                    level = memory_probe()
                    if level is not None and level < min_free:
                        log(f"STOP: memory free {level}% under {min_free}% after {i} answers; rerun to resume")
                        stop.set()

        if slots <= 1:
            for row in todo:
                work(row)
        else:
            with cf.ThreadPoolExecutor(max_workers=slots) as pool:
                list(pool.map(work, todo))
    result = build_output(done, rows, model, server, threshold)
    write_json(out, result)
    accepted = sum(1 for a in result["answers"].values() if a["accepted"])
    log(f"wrote {out}: {len(result['answers'])} answers, {accepted} accepted")
    return result


# ------------------------------------------------------------ the pilot

def import_pilot(pilot_path, rows, *, model=MODEL, prompt_version=PROMPT_VERSION, threshold=THRESHOLD):
    """pta_llm.json contents from an llm_pilot.py run file, with the pilot's acceptance and nothing recomputed.

    An answer is accepted when its urn is one of the row's candidates, its confidence is a real number in 0..1 of at
    least threshold, and the pilot recorded name_consistent true; a 'shared:' answer never is, whatever its urn (pta.py's
    shared step decides it). The file may still be growing: an unreadable last line is skipped, and a later line for
    the same charity wins. Rows not in `rows` are left out.
    """
    by_number = {int(r["charity_number"]): r for r in rows}
    records, bad = _jsonl_records(pilot_path)
    latest = {}
    for rec in records:
        if rec.get("error") or rec.get("model") != model or rec.get("prompt_version") != prompt_version:
            continue
        latest[int(rec["charity_number"])] = rec
    answers = {}
    for number, rec in sorted(latest.items()):
        row = by_number.get(number)
        if row is None:
            continue
        ans = rec.get("answer") if isinstance(rec.get("answer"), dict) else {}
        urn = None if ans.get("urn") is None else str(ans["urn"]).strip() or None
        conf = valid_confidence(ans.get("confidence"))
        candidate = urn is not None and any(str(c.get("urn")) == urn for c in row.get("candidates", []))
        consistent = bool(candidate and rec.get("name_consistent") is True)
        reason = str(ans.get("reason") or "")
        if urn is not None and not consistent:
            reason = f"{reason} [guard: {rec.get('name_check') or 'urn not a candidate'}]".strip()
        shared = pta.is_shared_answer(ans)
        answers[str(number)] = {"urn": urn, "confidence": conf, "reason": reason, "name_consistent": consistent,
                                "accepted": bool(consistent and not shared and conf is not None and conf >= threshold)}
    return {"generated": date.today().isoformat(), "model": model, "server": None, "prompt_version": prompt_version,
            "threshold": threshold, "answers": answers,
            "source": {"pilot": str(pilot_path), "lines": len(records), "unreadable_lines": bad}}


# ----------------------------------------------------------- spot check

def _cell(text, limit=160):
    return _clip(text, limit).replace("|", "/")


def write_sample(llm, rows, out=REVIEW, n=SAMPLE_N, seed=20261107):
    """Write n random accepted picks to a Markdown review sheet with a verdict column; returns the charity numbers."""
    by_number = {int(r["charity_number"]): r for r in rows}
    accepted = sorted(int(k) for k, a in (llm or {}).get("answers", {}).items()
                      if a.get("accepted") and a.get("urn") and int(k) in by_number)
    picks = sorted(random.Random(seed).sample(accepted, min(n, len(accepted))))
    shared = sum(1 for a in (llm or {}).get("answers", {}).values() if str(a.get("reason") or "").lower().startswith("shared:"))
    lines = [
        f"# Spot check: {len(picks)} random accepted adjudicator picks", "",
        f"Drawn {date.today().isoformat()} (seed {seed}) from {len(accepted):,} accepted of "
        f"{len((llm or {}).get('answers', {})):,} answers by {(llm or {}).get('model')} (prompt {(llm or {}).get('prompt_version')}). "
        f"{shared:,} 'shared:' answers go to pta.py's deterministic shared step instead.", "",
        "Replace each `?` with right, wrong or unsure, then run `python3 -m pipeline.money.pta_adjudicate spot-check`.",
        f"pta.py merges the answers only when at least {SAMPLE_N} are judged and none is wrong.",
        "The model's reason is not evidence: it has invented locations before. Judge from the facts.", "",
        "| # | charity | chosen school | other candidates | model's reason | verdict |", "|---|---|---|---|---|---|",
    ]
    for i, number in enumerate(picks, 1):
        row, answer = by_number[number], llm["answers"][str(number)]
        chosen = next(c for c in row.get("candidates", []) if str(c.get("urn")) == str(answer["urn"]))
        others = [c for c in row.get("candidates", []) if c is not chosen]

        def school(c):
            former = [p for p in c.get("predecessor_names") or [] if p and p != c.get("name")]
            return (f"URN {c.get('urn')} {c.get('name')}, {c.get('phase') or '?'}, {c.get('town') or ''} {c.get('postcode') or ''}"
                    + (f"; formerly {'; '.join(former)}" if former else ""))

        charity = (f"{row.get('charity_name')} ({number}); {row.get('status') or ''}"
                   f"{' ' + row['removed'] if row.get('removed') else ''}; area {', '.join(row.get('area') or []) or '?'}; "
                   f"address {', '.join(row.get('address') or []) or 'none'} {row.get('postcode') or ''}; "
                   f"objects: {row.get('objects') or 'none'}")
        lines.append(f"| {i} | {_cell(charity, 400)} | {_cell(school(chosen), 200)} | "
                     f"{_cell(' / '.join(school(c) for c in others) or 'none', 300)} | {_cell(answer.get('reason'))} | ? |")
    pta.write_atomic(out, "\n".join(lines) + "\n")
    return picks


# '| 3 | NAME (1234567); ... | URN 100000 ... | ... | ... | right |': the charity number, the chosen urn, the verdict
REVIEW_ROW = re.compile(r"^\|\s*\d+\s*\|[^|]*?\((\d+)\);[^|]*\|\s*URN (\d+) [^|]*\|.*\|\s*([A-Za-z?]+)\s*\|\s*$")


def spot_check(review_path, llm):
    """Read a judged review sheet into llm['spot_check'] = {n, wrong, unsure, checked, review, sampled}.

    Refuses (ValueError) a sheet with unjudged rows, unknown verdicts, or picks that no longer match an accepted answer
    in llm, so a stale review can never open the gate for a newer run."""
    verdicts = {}
    for line in Path(review_path).read_text(encoding="utf-8").splitlines():
        m = REVIEW_ROW.match(line)
        if m:
            verdicts[int(m.group(1))] = (m.group(2), m.group(3).lower())
    if not verdicts:
        raise ValueError(f"no picks found in {review_path}")
    for number, (urn, verdict) in verdicts.items():
        answer = llm.get("answers", {}).get(str(number)) or {}
        if not answer.get("accepted") or str(answer.get("urn")) != urn:
            raise ValueError(f"{number} -> {urn} is not an accepted answer in pta_llm.json; draw a fresh sample")
        if verdict not in ("right", "wrong", "unsure"):
            raise ValueError(f"{number}: verdict {verdict!r}; mark every row right, wrong or unsure")
    counts = {v: sum(1 for _, x in verdicts.values() if x == v) for v in ("right", "wrong", "unsure")}
    llm["spot_check"] = {"n": len(verdicts), "wrong": counts["wrong"], "unsure": counts["unsure"],
                         "checked": date.today().isoformat(), "review": str(review_path), "sampled": sorted(verdicts)}
    return llm["spot_check"]


# ------------------------------------------------------------------ main

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv.insert(0, "run")  # the original interface had no subcommand
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="adjudicate the ambiguous file")
    r.add_argument("--input", type=Path, default=AMBIGUOUS)
    r.add_argument("--out", type=Path, default=OUT)
    r.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    r.add_argument("--server", default=SERVER)
    r.add_argument("--model", default=MODEL)
    r.add_argument("--threshold", type=float, default=THRESHOLD)
    r.add_argument("--limit", type=int, default=0, help="ask at most this many new charities (0 = all)")
    r.add_argument("--prioritise-recent", action="store_true", help="charities with recent returns first")
    r.add_argument("--timeout", type=float, default=120)
    r.add_argument("--slots", type=int, default=SLOTS, help="parallel requests (load the model with --parallel to match)")
    r.add_argument("--min-free", type=int, default=MIN_FREE, help="stop below this percentage of free memory")
    r.add_argument("--mem-every", type=int, default=MEM_EVERY, help="answers between memory checks")
    i = sub.add_parser("import-pilot", help="convert the pilot's full run into pta_llm.json")
    i.add_argument("--pilot", type=Path, default=PILOT_RUN)
    i.add_argument("--input", type=Path, default=PILOT_INPUT, help="the rows the pilot was given")
    i.add_argument("--out", type=Path, default=OUT)
    i.add_argument("--model", default=MODEL)
    i.add_argument("--threshold", type=float, default=THRESHOLD)
    s = sub.add_parser("sample", help="write random accepted picks for a spot check")
    s.add_argument("--llm", type=Path, default=OUT)
    s.add_argument("--input", type=Path, help="rows behind the answers (default: the input recorded in pta_llm.json)")
    s.add_argument("--out", type=Path, default=REVIEW)
    s.add_argument("--n", type=int, default=SAMPLE_N)
    s.add_argument("--seed", type=int, default=20261107)
    c = sub.add_parser("spot-check", help="record a judged review sheet in pta_llm.json")
    c.add_argument("--review", type=Path, default=REVIEW)
    c.add_argument("--llm", type=Path, default=OUT)
    args = parser.parse_args(argv)

    if args.cmd == "run":
        rows = load_rows(args.input)
        if not rows:
            sys.exit(f"stop: {args.input} has no rows; rerun pta.py or pass --input with a good copy")
        try:
            run(rows, server=args.server, model=args.model, threshold=args.threshold, checkpoint=args.checkpoint,
                out=args.out, limit=args.limit, prioritise_recent=args.prioritise_recent, timeout=args.timeout,
                slots=args.slots, min_free=args.min_free, mem_every=args.mem_every)
        except ModelRefused as exc:
            sys.exit(str(exc))
    elif args.cmd == "import-pilot":
        result = import_pilot(args.pilot, load_rows(args.input), model=args.model, threshold=args.threshold)
        result["source"]["input"] = str(args.input)
        write_json(args.out, result)
        answers = result["answers"].values()
        print(f"wrote {args.out}: {len(result['answers']):,} answers from {result['source']['lines']:,} pilot lines "
              f"({result['source']['unreadable_lines']} unreadable), {sum(1 for a in answers if a['accepted']):,} accepted, "
              f"{sum(1 for a in answers if str(a['reason']).lower().startswith('shared:')):,} shared; no spot check yet")
    elif args.cmd == "sample":
        llm = json.loads(args.llm.read_text(encoding="utf-8"))
        source = args.input or Path((llm.get("source") or {}).get("input") or AMBIGUOUS)
        picks = write_sample(llm, load_rows(source), args.out, args.n, args.seed)
        print(f"wrote {args.out}: {len(picks)} picks to judge")
    else:
        llm = json.loads(args.llm.read_text(encoding="utf-8"))
        try:
            spot = spot_check(args.review, llm)
        except ValueError as exc:
            sys.exit(str(exc))
        write_json(args.llm, llm)
        print(f"recorded spot check in {args.llm}: {spot['n']} judged, {spot['wrong']} wrong, {spot['unsure']} unsure; "
              + ("pta.py will merge the answers" if not pta.llm_gate(llm) else f"gate stays shut ({pta.llm_gate(llm)})"))


if __name__ == "__main__":
    main()
