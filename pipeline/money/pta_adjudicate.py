"""Ask a local model to settle ambiguous PTA -> school matches, keeping only name-consistent answers.

Reads pta_ambiguous.jsonl (one charity and its candidate schools per line), asks an OpenAI-compatible
server (LM Studio by default) for one JSON answer per charity, and writes pta_llm.json for pta.py to
merge with method "llm". The model is never trusted on its own: an answer counts only when its
confidence clears the threshold, the chosen urn is one of the candidates, and the school's current or
former name shares a distinctive word with the charity's name (the pilot found the model's confidence
useless as a filter and this guard doing the real work). Answers checkpoint to a JSONL file as they
arrive, so a stopped run resumes where it left off.

The server is queried for its model list first and any model whose id or metadata says more than
about 40B parameters or 40 GB is refused, so a typo can never pull a huge model into memory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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
SERVER = "http://localhost:1234/v1"
MODEL = "qwen/qwen3.8-27b"
THRESHOLD = 0.8
MAX_PARAMS_B = 40          # refuse models over ~40B parameters
MAX_BYTES = 40 * 10**9     # or over ~40 GB on disk
PROMPT_VERSION = "v1"
MAX_TOKENS = 400

SYSTEM_PROMPT = """\
You match school parent associations (PTA, PTFA, PFA, PSA, "Friends of ...") from the Charity Commission \
register of England and Wales to the state-funded school they raise money for. You get one charity and a \
short list of candidate schools from the DfE register. Pick the candidate this charity supports, or null. \
Answer null unless certain.

How to decide:
1. The school named in the charity's name, objects or area of benefit must match the candidate's current or \
former name in its distinctive words. A shared town, council or saint's name alone is not a match: "St Mary's" \
in one town is not "St Mary's" in another.
2. Location must fit. Compare the charity's address, postcode, area of benefit and council areas with the \
candidate's town and postcode. A place word left over in the charity name that is not the candidate's place \
points to a different school.
3. Phase must fit. An Infant PTA is not a Junior school's, a Primary PTA is not a secondary school's, a High \
School or Grammar School PTA is not a primary's.
4. A former name of a candidate counts as a match when the charity is older than the rename.
5. Return null when: the charity probably supports an independent (private) school, especially one listed \
under "independent schools with a fitting name"; the school it names is not in the list (closed, renamed \
beyond recognition, or in another town); two or more candidates fit equally well; the charity is not a parent \
association of one school (music, sport, minibus, playgroup, alumni, a federation of several schools); or the \
evidence is too thin.
6. If the charity serves two listed schools jointly (for example "X Infant and Junior Schools PTA"), return \
null and start the reason with "shared:" followed by both URNs.
7. A school can have had several parent-association charities over the years, so a candidate that already has \
a matched PTA is still allowed.

confidence is your probability that the chosen urn is right. Give 0.9 or more only when name, location and \
phase all clearly fit and no other candidate is plausible. With urn null, confidence is how sure you are that \
none of the candidates is this charity's school.

Answer with one JSON object only, no other text:
{"urn": "<urn>" or null, "confidence": <number 0-1>, "reason": "<one short sentence>"}"""


class ModelRefused(RuntimeError):
    """The requested model is missing from the server or too large to run safely."""


# ------------------------------------------------------------------ HTTP

def post_json(url, payload=None, timeout=120):
    """The one HTTP call: POST payload as JSON (GET when payload is None) and return the decoded body."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def model_too_big(info) -> str | None:
    """Why a /v1/models entry is over the cap, or None. Reads the id ('...-128b') and any size or parameter metadata."""
    model_id = str(info.get("id") or "")
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*b(?![a-z0-9])", model_id, re.I):
        if float(m.group(1)) > MAX_PARAMS_B:
            return f"id says {m.group(1)}B parameters"
    for key, value in info.items():
        if not isinstance(key, str):
            continue
        k = key.lower()
        n = _number(value)
        if n is None:
            continue
        if ("size" in k or "bytes" in k) and n > MAX_BYTES:
            return f"{key} = {n / 1e9:.0f} GB"
        if "param" in k and (n > MAX_PARAMS_B * 10**9 or 1000 > n > MAX_PARAMS_B):
            return f"{key} = {value}"
    return None


def check_model(server, model):
    """Confirm the model is on the server and under the size cap; raise ModelRefused otherwise."""
    try:
        data = post_json(server.rstrip("/") + "/models")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ModelRefused(f"cannot list models at {server}: {exc}") from exc
    models = {str(m.get("id")): m for m in (data or {}).get("data", []) if isinstance(m, dict)}
    if model not in models:
        raise ModelRefused(f"{model} is not on the server (have: {', '.join(sorted(models)) or 'none'}); load it first, never JIT")
    reason = model_too_big(models[model])
    if reason:
        raise ModelRefused(f"refusing {model}: {reason}, over the ~{MAX_PARAMS_B}B / {MAX_BYTES // 10**9} GB cap")
    return models[model]


# ---------------------------------------------------------------- prompt

def _clip(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def user_prompt(row) -> str:
    lines = [f"Charity {row['charity_number']}: {row.get('charity_name') or ''}"]
    if (row.get("status") or "").lower() == "removed" or row.get("removed"):
        lines.append(f"Status: removed from the register {row.get('removed') or '(date unknown)'} (removed charities lose their address)")
    else:
        lines.append("Status: registered")
    lines.append(f"Objects: {_clip(row.get('objects'), 700) or '(none)'}")
    lines.append(f"Area of benefit: {_clip(row.get('area_of_benefit'), 200) or '(none)'}")
    lines.append(f"Council areas of operation: {', '.join(row.get('area') or []) or '(none)'}")
    address = ", ".join(row.get("address") or [])
    lines.append(f"Address: {address or '(none)'}{' ' + row['postcode'] if row.get('postcode') else ''}")
    income = row.get("latest_income")
    lines.append(f"Latest income: {'not known' if income is None else f'£{income:,.0f}'}")
    if row.get("also_fits_independent"):
        lines.append("Independent schools with a fitting name in the area (not candidates): " + "; ".join(row["also_fits_independent"]))
    lines += ["", "Candidate state-funded schools:"]
    for c in row.get("candidates", []):
        bits = [f"URN {c['urn']}: {c.get('name') or ''}", c.get("phase") or "phase not given",
                " ".join(x for x in (c.get("town"), c.get("postcode")) if x) or "place not given"]
        former = [p for p in (c.get("predecessor_names") or []) if p and p != c.get("name")]
        if former:
            bits.append("former names: " + "; ".join(former))
        bits.append("already has a matched PTA" if c.get("already_matched") else "no PTA matched yet")
        lines.append("- " + " | ".join(bits))
    return "\n".join(lines)


THINK = re.compile(r"<think>.*?</think>", re.S)


def parse_answer(text):
    """{"urn", "confidence", "reason"} from the model's text, or None when no JSON object can be read."""
    text = THINK.sub("", str(text or "")).strip()
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text).strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])  # tolerates trailing junk
    except ValueError:
        return None
    if not isinstance(obj, dict) or "urn" not in obj:
        return None
    urn = obj.get("urn")
    if urn is not None:
        urn = str(urn).strip()
        if urn.lower() in ("", "null", "none"):
            urn = None
    return {"urn": urn, "confidence": _number(obj.get("confidence")), "reason": str(obj.get("reason") or "")}


# ------------------------------------------------------------ acceptance

def name_consistent(row, urn):
    """(ok, reason): the chosen school's current or a former name shares a distinctive token with the charity
    name, the phases do not conflict, and no activity word (orchestra, minibus...) is left in the charity name."""
    cand = next((c for c in row.get("candidates", []) if str(c.get("urn")) == str(urn)), None)
    if cand is None:
        return False, "urn is not a candidate"
    charity_name = row.get("charity_name") or ""
    ctok = set(pta.normalise(charity_name))
    names = [cand.get("name") or ""] + [p for p in (cand.get("predecessor_names") or []) if p]
    if not any(ctok & set(pta.normalise(n)) for n in names):
        return False, "no distinctive word shared with the school's current or former names"
    gias = pta.GIAS_PHASE.get(cand.get("phase"), set())
    if all(pta.conflict(pta.phase_words(n) | gias, pta.phase_words(charity_name)) for n in names):
        return False, "phase conflict"
    school_words = {t for n in names for t in pta._tokens(n)} | set(pta._tokens(cand.get("town")))
    scope = (set(pta._tokens(charity_name)) - school_words) & pta.OUT_OF_SCOPE
    if scope:
        return False, "activity words in the charity name: " + ", ".join(sorted(scope))
    return True, "ok"


def judge(answer, row, threshold):
    """Decorate a parsed answer with name_consistent and accepted."""
    out = {"urn": None, "confidence": None, "reason": "unparseable answer", "name_consistent": False, "accepted": False}
    if not answer:
        return out
    out.update(urn=answer.get("urn"), confidence=answer.get("confidence"), reason=answer.get("reason") or "")
    if out["urn"] is None or out["confidence"] is None:
        return out
    ok, why = name_consistent(row, out["urn"])
    out["name_consistent"] = ok
    if not ok:
        out["reason"] = f"{out['reason']} [guard: {why}]".strip()
    out["accepted"] = bool(ok and out["confidence"] >= threshold)
    return out


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


def load_checkpoint(path, model, prompt_version):
    """charity number (int) -> checkpoint line, for answers given by this model and prompt."""
    done = {}
    path = Path(path)
    if not path.exists():
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("model") == model and rec.get("prompt_version") == prompt_version:
                done[int(rec["charity_number"])] = rec
    return done


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


def run(rows, *, server=SERVER, model=MODEL, threshold=THRESHOLD, checkpoint=CHECKPOINT, out=OUT, limit=0,
        prioritise_recent=False, timeout=120, log=print):
    """Adjudicate rows (resuming from the checkpoint), write out, and return the pta_llm.json dict."""
    done = load_checkpoint(checkpoint, model, PROMPT_VERSION)
    todo = [r for r in rows if int(r["charity_number"]) not in done]
    if prioritise_recent:
        todo.sort(key=lambda r: -(r.get("recent_returns") or 0))
    if limit:
        todo = todo[:limit]
    log(f"{len(rows)} rows, {len(done)} already answered, asking {len(todo)}")
    Path(checkpoint).parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    with open(checkpoint, "a", encoding="utf-8") as f:
        for i, row in enumerate(todo, 1):
            number = int(row["charity_number"])
            try:
                raw = ask(server, model, row, timeout)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                log(f"  {number}: request failed ({exc}); will retry on the next run")
                continue
            rec = {"charity_number": number, "model": model, "prompt_version": PROMPT_VERSION, "raw": raw,
                   "asked": date.today().isoformat()}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            done[number] = rec
            if i % 25 == 0 or i == len(todo):
                verdict = judge(parse_answer(raw), row, threshold)
                log(f"  {i}/{len(todo)} ({(time.time() - start) / i:.1f}s each); last: {number} -> {verdict['urn']} accepted={verdict['accepted']}")
    result = build_output(done, rows, model, server, threshold)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    accepted = sum(1 for a in result["answers"].values() if a["accepted"])
    log(f"wrote {out}: {len(result['answers'])} answers, {accepted} accepted")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=AMBIGUOUS)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    parser.add_argument("--server", default=SERVER)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--limit", type=int, default=0, help="ask at most this many new charities (0 = all)")
    parser.add_argument("--prioritise-recent", action="store_true", help="charities with recent returns first")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args(argv)
    try:
        info = check_model(args.server, args.model)
    except ModelRefused as exc:
        sys.exit(str(exc))
    print(f"using {args.model} at {args.server}" + (f" ({info.get('state')})" if info.get("state") else ""))
    run(load_rows(args.input), server=args.server, model=args.model, threshold=args.threshold, checkpoint=args.checkpoint,
        out=args.out, limit=args.limit, prioritise_recent=args.prioritise_recent, timeout=args.timeout)


if __name__ == "__main__":
    main()
