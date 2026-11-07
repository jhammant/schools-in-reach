"""Tests for the local-model adjudicator; HTTP is faked by replacing post_json, no sockets."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from pipeline.money import pta_adjudicate as adj


def row(number=1, name="FRIENDS OF WOODLEA SCHOOL", candidates=None, **extra):
    base = {"charity_number": number, "charity_name": name, "kind": "several_fit", "objects": "", "area_of_benefit": "",
            "area": ["Hampshire"], "postcode": None, "town": None, "address": [], "status": "Removed", "removed": "2010-01-01",
            "latest_income": None, "recent_returns": 0, "also_fits_independent": [],
            "candidates": candidates or [cand("1", "Woodlea Primary School"), cand("2", "Grasmere Primary School")]}
    base.update(extra)
    return base


def cand(urn, name, phase="Primary", preds=(), matched=False):
    return {"urn": urn, "name": name, "postcode": "GU33 7AA", "town": "Liphook", "phase": phase,
            "predecessor_names": list(preds), "already_matched": matched}


class FakeServer:
    """Stands in for post_json: lists models (/v1/models and LM Studio's /api/v0/models), answers chat completions
    from a script keyed by charity number."""

    def __init__(self, answers, models=("qwen/qwen3.8-27b",), state=None):
        self.answers, self.calls = answers, []
        self.models = [{"id": m, **({"state": state} if state else {})} for m in models]

    def __call__(self, url, payload=None, timeout=120):
        self.calls.append((url, payload))
        if url.endswith("/models"):
            return {"data": self.models}
        number = int(payload["messages"][1]["content"].split()[1].rstrip(":"))
        return {"choices": [{"message": {"content": self.answers[number]}}]}

    def asked(self):
        """Charity numbers sent to /chat/completions, in order."""
        return [int(p["messages"][1]["content"].split()[1].rstrip(":")) for u, p in self.calls if u.endswith("/chat/completions")]


def pilot_line(number, urn, confidence=0.95, reason="fits", name_consistent=True, name_check="ok", **extra):
    """One llm_pilot.py result line, as the pilot's run writes it."""
    rec = {"charity_number": number, "charity_name": "X", "model": "qwen/qwen3.8-27b", "prompt_version": "v1",
           "answer": {"urn": urn, "confidence": confidence, "reason": reason}, "parse_ok": True, "valid": True,
           "name_consistent": name_consistent, "name_check": name_check, "raw": "{}"}
    rec.update(extra)
    return json.dumps(rec)


# Rows from the pilot's guard cases (llm_pilot.md), trimmed to the fields the guard reads.
SOUTHCOTE = {"charity_number": 1180299, "charity_name": "SOUTHCOTE PFA (PARENTS & FRIENDS ASSOCIATION)", "area": ["Surrey"],
             "postcode": "KT15 2qh", "town": "Addlestone", "area_of_benefit": "", "objects": "", "also_fits_independent": [],
             "address": ["Philip Southcote School", "Addlestone Moor", "ADDLESTONE", "Surrey"],
             "candidates": [{"urn": "125116", "name": "Ash Grange Nursery and Primary School", "postcode": "GU12 6LX", "town": "Ash",
                             "phase": "Primary", "predecessor_names": ["Manfield County First School", "Southcote Middle School"]}]}
LOCKSLEY = {"charity_number": 1191011, "charity_name": "THE FRIENDS OF LOCKSLEY SCHOOL", "area": ["Norfolk"], "postcode": "NR4 6LG ",
            "town": "Norwich", "area_of_benefit": "", "objects": "", "also_fits_independent": [],
            "address": ["The Locksley School", "Locksley Road", "NORWICH"],
            "candidates": [{"urn": "150354", "name": "UET Compass Academy", "postcode": "NR31 9LD", "town": "Great Yarmouth",
                            "phase": "Not applicable", "predecessor_names": ["UET Pathfinder Academy", "The Locksley School"]},
                           {"urn": "140753", "name": "UET Pathfinder Academy", "postcode": "NR10 5JW", "town": "Norwich",
                            "phase": "Not applicable", "predecessor_names": ["Short Stay School for Norfolk", "The Locksley School"]}]}
CLINTON = {"charity_number": 1081480, "charity_name": "FRIENDS OF CLINTON PRIMARY SCHOOL ORCHESTRA", "area": ["Warwickshire"],
           "postcode": None, "town": None, "area_of_benefit": "", "objects": "", "address": [], "also_fits_independent": [],
           "candidates": [{"urn": "125551", "name": "Clinton Primary School", "postcode": "CV8 1DL", "town": "Kenilworth",
                           "phase": "Primary", "predecessor_names": []}]}
ST_JAMES_LEEDS = {"charity_number": 1042256, "charity_name": "FRIENDS OF ST JAMES CHURCH OF ENGLAND SCHOOL", "area": ["Leeds"],
                  "postcode": None, "town": None, "area_of_benefit": "NOT DEFINED", "objects": "", "address": [], "also_fits_independent": [],
                  "candidates": [{"urn": "107995", "name": "St James' Church of England Voluntary Controlled Primary School",
                                  "postcode": "LS22 6JS", "town": "Wetherby", "phase": "Primary", "predecessor_names": []},
                                 {"urn": "138824", "name": "Manston St James Primary Academy", "postcode": "LS15 8JH", "town": "Leeds",
                                  "phase": "Primary", "predecessor_names": ["Manston St James Church of England Primary School"]}]}
TETTENHALL = {"charity_number": 1191393, "charity_name": "Friends of Tettenhall College", "area": ["Wolverhampton"],
              "postcode": "WV6 8QX", "town": "Wolverhampton", "area_of_benefit": "", "objects": "",
              "address": ["TC PARENT AND TEACHER ASSOCIATION", "TETTENHALL COLLEGE", "COLLEGE ROAD", "WOLVERHAMPTON"],
              "also_fits_independent": ["Tettenhall College Incorporated"],
              "candidates": [{"urn": "149227", "name": "Tettenhall Wood School", "postcode": "WV6 8XF", "town": "Wolverhampton",
                              "phase": "Not applicable", "predecessor_names": ["Tettenhall Wood School"]}]}
BELVEDERE = {"charity_number": 1054559, "charity_name": "TRINITY SCHOOL ASSOCIATION", "area": ["Kent"], "postcode": None,
             "town": None, "area_of_benefit": "BELVEDERE, KENT", "objects": "TO ADVANCE THE EDUCATION OF PUPILS OF THE SCHOOL.",
             "address": [], "also_fits_independent": [],
             "candidates": [{"urn": "139554", "name": "Trinity School", "postcode": "TN13 3SL", "town": "Sevenoaks",
                             "phase": "Secondary", "predecessor_names": []}]}
ST_ANNES_B74 = {"charity_number": 1102188, "charity_name": "ST ANNE'S PTA", "area": ["Birmingham", "Walsall"], "postcode": "B74 3PL ",
                "town": "Sutton Coldfield", "area_of_benefit": "NOT DEFINED BUT IN PRACTICE STREETLY, SUTTON COLDFIELD", "objects": "",
                "address": ["St. Annes Rc Primary School", "Blackwood Road", "SUTTON COLDFIELD"], "also_fits_independent": [],
                "candidates": [{"urn": "103434", "name": "St Anne's Catholic Primary School", "postcode": "B12 0ER", "town": "Birmingham",
                                "phase": "Primary", "predecessor_names": []}]}
ST_JAMES_HEREFORD = {"charity_number": 1101797, "charity_name": "ST JAMES CE PRIMARY SCHOOL PTFA", "area": ["Herefordshire, County of"],
                     "postcode": "HR2 6DA", "town": "Hereford", "area_of_benefit": "NOT DEFINED", "objects": "",
                     "address": ["54 Holme Lacy Road", "HEREFORD"], "also_fits_independent": [],
                     "candidates": [{"urn": "151073", "name": "St James' Church of England Primary School", "postcode": "HR1 2QN",
                                     "town": "Hereford", "phase": "Primary", "predecessor_names": ["St James' CofE Primary School"]},
                                    {"urn": "116890", "name": "Kimbolton St James CofE Primary School", "postcode": "HR6 0HQ",
                                     "town": "Leominster", "phase": "Primary", "predecessor_names": []}]}


class AcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.real_post = adj.post_json

    def tearDown(self):
        adj.post_json = self.real_post

    def judge_with(self, text, r=None, threshold=0.8):
        return adj.judge(adj.parse_answer(text), r or row(), threshold)

    def test_accepted_when_confident_and_name_consistent(self):
        # Arrange / Act
        got = self.judge_with('{"urn": "1", "confidence": 0.95, "reason": "Woodlea is the only fit"}')
        # Assert
        self.assertEqual(got, {"urn": "1", "confidence": 0.95, "reason": "Woodlea is the only fit", "name_consistent": True, "accepted": True})

    def test_rejected_for_low_confidence(self):
        got = self.judge_with('{"urn": "1", "confidence": 0.6, "reason": "probably"}')
        self.assertTrue(got["name_consistent"])
        self.assertFalse(got["accepted"])

    def test_rejected_for_name_inconsistency(self):
        # Arrange: Grasmere shares no distinctive word with 'Friends of Woodlea School'
        got = self.judge_with('{"urn": "2", "confidence": 0.99, "reason": "same town"}')
        # Assert
        self.assertFalse(got["name_consistent"])
        self.assertFalse(got["accepted"])
        self.assertIn("guard:", got["reason"])

    def test_predecessor_name_counts_as_consistent(self):
        r = row(name="NEWNHAM MIDDLE SCHOOL PTA", candidates=[cand("7", "Castle Newnham School", preds=["Newnham Middle School"])])
        got = self.judge_with('{"urn": "7", "confidence": 0.9, "reason": "former name"}', r)
        self.assertTrue(got["accepted"])

    def test_rejected_for_urn_not_among_candidates(self):
        got = self.judge_with('{"urn": "999", "confidence": 0.99, "reason": "sure"}')
        self.assertFalse(got["accepted"])
        self.assertIn("not a candidate", got["reason"])

    def test_rejected_for_phase_conflict_and_activity_words(self):
        # Arrange
        junior = row(name="WOODLEA JUNIOR SCHOOL PTA", candidates=[cand("1", "Woodlea Infant School")])
        orchestra = row(name="FRIENDS OF WOODLEA SCHOOL ORCHESTRA")
        # Act / Assert
        self.assertFalse(self.judge_with('{"urn": "1", "confidence": 0.95, "reason": "x"}', junior)["accepted"])
        self.assertFalse(self.judge_with('{"urn": "1", "confidence": 0.95, "reason": "x"}', orchestra)["accepted"])

    def test_shared_reason_is_never_accepted_even_with_an_urn(self):
        # Arrange: prompt v1 rule 6 says urn null, but a model may fill it in anyway
        r = row(name="WOODLEA SCHOOLS PTA", candidates=[cand("1", "Woodlea Infant School"), cand("2", "Woodlea Junior School")])
        # Act
        got = self.judge_with('{"urn": "1", "confidence": 0.99, "reason": "shared: 1 and 2"}', r)
        # Assert: left for pta.py's deterministic shared step, reason prefix intact
        self.assertFalse(got["accepted"])
        self.assertTrue(got["reason"].startswith("shared:"))

    def test_null_answer_is_not_accepted(self):
        got = self.judge_with('{"urn": null, "confidence": 0.9, "reason": "shared: 1 2"}')
        self.assertIsNone(got["urn"])
        self.assertFalse(got["accepted"])

    def test_malformed_json_tolerated(self):
        # Arrange / Act
        self.assertIsNone(adj.parse_answer("I think it is school 1."))
        self.assertIsNone(adj.parse_answer(""))
        trailing = adj.parse_answer('<think>hmm</think>```json\n{"urn": 1, "confidence": "0.9", "reason": "ok"}}\n```')
        got = self.judge_with("not json at all")
        # Assert
        self.assertEqual(trailing, {"urn": "1", "confidence": 0.9, "reason": "ok"})
        self.assertEqual(got["reason"], "unparseable answer")
        self.assertFalse(got["accepted"])


class PilotGuardTest(unittest.TestCase):
    """The deterministic guard rejects every wrong pick the pilot found (llm_pilot.md, 'How the model goes wrong')."""

    def test_guard_cases_from_the_pilot(self):
        # Arrange: (row, the model's pick, the guard's expected reason)
        cases = [
            (SOUTHCOTE, "125116", "address names another school: Philip Southcote School"),
            (LOCKSLEY, "150354", "former name shared with 140753"),
            (CLINTON, "125551", "leftover: orchestra"),
            (ST_JAMES_LEEDS, "138824", "no strong shared name word"),
            (TETTENHALL, "149227", "independent namesake fits better: Tettenhall College Incorporated"),
            (BELVEDERE, "139554", "weak name match, place not the school's: belvedere"),
            (ST_ANNES_B74, "103434", "weak name match, place not the school's: coldfield streetly sutton"),
        ]
        for row_, urn, why in cases:
            with self.subTest(row_["charity_name"]):
                # Act
                got = adj.judge(adj.parse_answer(json.dumps({"urn": urn, "confidence": 0.95, "reason": "fits"})), row_, adj.THRESHOLD)
                # Assert
                self.assertEqual(adj.name_consistent(row_, urn), (False, why))
                self.assertFalse(got["accepted"])
                self.assertIn(f"[guard: {why}]", got["reason"])

    def test_guard_keeps_a_right_saint_pick_in_its_own_town(self):
        # Arrange / Act
        got = adj.judge(adj.parse_answer('{"urn": "151073", "confidence": 0.95, "reason": "Hereford"}'), ST_JAMES_HEREFORD, adj.THRESHOLD)
        # Assert
        self.assertTrue(got["accepted"])

    def test_confidence_must_be_a_probability(self):
        # Arrange / Act / Assert: strings that read as numbers are fine; booleans, percentages and non-finite are not
        self.assertEqual(adj.valid_confidence("0.95"), 0.95)
        self.assertEqual(adj.valid_confidence(1), 1.0)
        for bad in (True, False, 95, 1.01, -0.1, float("inf"), float("nan"), "NaN", "high", None):
            self.assertIsNone(adj.valid_confidence(bad), bad)
        self.assertIsNone(adj.parse_answer('{"urn": "1", "confidence": Infinity, "reason": "x"}')["confidence"])

    def test_threshold_is_the_pilots(self):
        # Arrange / Act
        got = adj.judge(adj.parse_answer('{"urn": "1", "confidence": 0.85, "reason": "Woodlea"}'), row(), adj.THRESHOLD)
        # Assert
        self.assertEqual(adj.THRESHOLD, 0.9)
        self.assertTrue(got["name_consistent"])
        self.assertFalse(got["accepted"])


class ModelCheckTest(unittest.TestCase):
    def setUp(self):
        self.real_post = adj.post_json

    def tearDown(self):
        adj.post_json = self.real_post

    def test_oversize_model_refused(self):
        # Arrange
        adj.post_json = FakeServer({}, models=("mistral-medium-3.5-128b", "qwen/qwen3.8-27b"))
        # Act / Assert
        with self.assertRaises(adj.ModelRefused):
            adj.check_model("http://fake/v1", "mistral-medium-3.5-128b")
        self.assertEqual(adj.check_model("http://fake/v1", "qwen/qwen3.8-27b")["id"], "qwen/qwen3.8-27b")

    def test_metadata_size_and_missing_model_refused(self):
        self.assertEqual(adj.model_too_big({"id": "big", "size_bytes": 55_000_000_000}), "size_bytes = 55 GB")
        self.assertEqual(adj.model_too_big({"id": "big", "parameters": 70_000_000_000}), "parameters = 70000000000")
        self.assertIsNone(adj.model_too_big({"id": "qwen/qwen3.8-27b", "size_bytes": 15_000_000_000}))
        self.assertIsNone(adj.model_too_big({"id": "laguna-xs-2.1"}))
        adj.post_json = FakeServer({}, models=("laguna-xs-2.1",))
        with self.assertRaises(adj.ModelRefused):
            adj.check_model("http://fake/v1", "qwen/qwen3.8-27b")

    def test_size_cap_reads_every_metadata_format(self):
        # Arrange / Act / Assert: units in the key or the value, nested fields, parameter strings and MoE ids
        self.assertEqual(adj.model_too_big({"id": "m", "size_gb": 55}), "size_gb = 55 GB")
        self.assertEqual(adj.model_too_big({"id": "m", "size": "48 GB"}), "size = 48 GB")
        self.assertEqual(adj.model_too_big({"id": "m", "metadata": {"size_bytes": 55_000_000_000}}), "metadata.size_bytes = 55 GB")
        self.assertEqual(adj.model_too_big({"id": "m", "parameters": "70B"}), "parameters = 70B")
        self.assertEqual(adj.model_too_big({"id": "m", "info": {"paramsString": "8x22B"}}), "info.paramsString = 8x22B")
        self.assertEqual(adj.model_too_big({"id": "mixtral-8x22b-instruct"}), "id says 8x22b parameters")
        self.assertIsNone(adj.model_too_big({"id": "m", "size_gb": 15.2, "parameters": "27B", "max_context_length": 32768}))

    def test_unloaded_and_blocklisted_models_refused(self):
        # Arrange: LM Studio lists downloaded models with a state; only 'loaded' may be used (never JIT)
        adj.post_json = FakeServer({}, state="not-loaded")
        # Act / Assert
        with self.assertRaisesRegex(adj.ModelRefused, "not loaded"):
            adj.check_model("http://fake/v1", "qwen/qwen3.8-27b")
        adj.post_json = FakeServer({}, state="loaded")
        self.assertEqual(adj.check_model("http://fake/v1", "qwen/qwen3.8-27b")["state"], "loaded")
        adj.post_json = FakeServer({}, models=("mistral-medium-3.5-128b",), state="loaded")
        with self.assertRaisesRegex(adj.ModelRefused, "blocklisted"):
            adj.check_model("http://fake/v1", "mistral-medium-3.5-128b")
        self.assertEqual(adj.post_json.calls, [], "a blocklisted model is refused before the server is asked anything")

    def test_loaded_state_must_be_confirmed(self):
        # Arrange: /v1/models lists the model, but the model-state endpoint is down, or answers without it
        listed = {"data": [{"id": adj.MODEL}]}

        def no_state_api(url, payload=None, timeout=120):
            if url.endswith("/api/v0/models"):
                raise adj.urllib.error.URLError("404")
            return listed

        def state_api_without_model(url, payload=None, timeout=120):
            return {"data": [{"id": "laguna-xs-2.1", "state": "loaded"}]} if url.endswith("/api/v0/models") else listed

        for fake in (no_state_api, state_api_without_model):
            adj.post_json = fake
            # Act / Assert
            with self.assertRaisesRegex(adj.ModelRefused, "cannot confirm"):
                adj.check_model("http://fake/v1", adj.MODEL)
        # a 'loaded' state from either listing is confirmation; a contrary one in either refuses
        adj.post_json = lambda url, payload=None, timeout=120: (
            {"data": [{"id": adj.MODEL, "state": "loaded"}]} if url.endswith("/api/v0/models") else listed)
        self.assertEqual(adj.check_model("http://fake/v1", adj.MODEL)["id"], adj.MODEL)
        adj.post_json = lambda url, payload=None, timeout=120: (
            {"data": [{"id": adj.MODEL, "state": "loaded"}]} if url.endswith("/api/v0/models")
            else {"data": [{"id": adj.MODEL, "state": "not-loaded"}]})
        with self.assertRaisesRegex(adj.ModelRefused, "not loaded"):
            adj.check_model("http://fake/v1", adj.MODEL)

    def test_run_refuses_before_asking_anything(self):
        # Arrange
        adj.post_json = FakeServer({1: "{}"}, models=("laguna-xs-2.1",))
        with tempfile.TemporaryDirectory() as tmp:
            # Act / Assert
            with self.assertRaises(adj.ModelRefused):
                adj.run([row(1)], server="http://fake/v1", checkpoint=Path(tmp) / "ck.jsonl", out=Path(tmp) / "o.json",
                        log=lambda *_: None, memory_probe=lambda: 80)
            self.assertFalse((Path(tmp) / "o.json").exists())
        self.assertEqual(adj.post_json.asked(), [])


class RunTest(unittest.TestCase):
    def setUp(self):
        self.real_post = adj.post_json

    def tearDown(self):
        adj.post_json = self.real_post

    def test_run_writes_output_and_checkpoint_then_resumes(self):
        # Arrange
        rows = [row(1), row(2, name="GRASMERE PTFA", recent_returns=3), row(3, name="FRIENDS OF WOODLEA SCHOOL", candidates=[cand("1", "Woodlea Primary School")])]
        fake = FakeServer({1: '{"urn": "1", "confidence": 0.95, "reason": "Woodlea"}',
                           2: '{"urn": "2", "confidence": 0.95, "reason": "Grasmere"}',
                           3: 'garbage'})
        adj.post_json = fake
        with tempfile.TemporaryDirectory() as tmp:
            ckpt, out = Path(tmp) / "ck.jsonl", Path(tmp) / "pta_llm.json"
            # Act: first run asks only two (limit), recent first; second run picks up the rest
            first = adj.run(rows, server="http://fake/v1", checkpoint=ckpt, out=out, limit=2, prioritise_recent=True,
                            log=lambda *_: None, slots=1, memory_probe=lambda: 80)
            asked_first = fake.asked()
            second = adj.run(rows, server="http://fake/v1", checkpoint=ckpt, out=out, log=lambda *_: None, slots=1,
                             memory_probe=lambda: 80)
            asked_total = fake.asked()
            lines = [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines()]
            written = json.loads(out.read_text(encoding="utf-8"))
        # Assert
        self.assertEqual(asked_first, [2, 1])
        self.assertEqual(asked_total, [2, 1, 3])
        self.assertEqual(sorted(first["answers"]), ["1", "2"])
        self.assertEqual(sorted(second["answers"]), ["1", "2", "3"])
        self.assertEqual([l["charity_number"] for l in lines], [2, 1, 3])
        self.assertEqual(written["model"], adj.MODEL)
        self.assertEqual(written["prompt_version"], adj.PROMPT_VERSION)
        self.assertEqual(written["threshold"], adj.THRESHOLD)
        self.assertTrue(written["answers"]["1"]["accepted"])
        self.assertTrue(written["answers"]["2"]["accepted"])
        self.assertEqual(written["answers"]["3"], {"urn": None, "confidence": None, "reason": "unparseable answer",
                                                   "name_consistent": False, "accepted": False})
        chat = [p for u, p in fake.calls if u.endswith("/chat/completions")][0]
        self.assertEqual((chat["temperature"], chat["reasoning_effort"], chat["max_tokens"]), (0, "none", 400))
        self.assertEqual(chat["messages"][0]["content"], adj.SYSTEM_PROMPT)

    def test_prompt_is_the_pilots_v1(self):
        # Assert: prompt v1 verbatim (llm_pilot.SYSTEM_PROMPT_V1), with nothing added
        self.assertTrue(adj.SYSTEM_PROMPT.startswith("You match school parent associations (PTA, PTFA, PFA, PSA, \"Friends of ...\")"))
        self.assertIn("Pick the candidate this charity supports, or null.\n\nHow to decide:", adj.SYSTEM_PROMPT)
        self.assertTrue(adj.SYSTEM_PROMPT.endswith('{"urn": "<urn>" or null, "confidence": <number 0-1>, "reason": "<one short sentence>"}'))
        self.assertEqual(adj.PROMPT_VERSION, "v1")

    def test_two_slots_answer_every_row(self):
        # Arrange
        rows = [row(n) for n in range(1, 8)]
        fake = FakeServer({n: '{"urn": "1", "confidence": 0.95, "reason": "Woodlea"}' for n in range(1, 8)})
        adj.post_json = fake
        with tempfile.TemporaryDirectory() as tmp:
            # Act
            result = adj.run(rows, server="http://fake/v1", checkpoint=Path(tmp) / "ck.jsonl", out=Path(tmp) / "o.json",
                             log=lambda *_: None, memory_probe=lambda: 80)
        # Assert
        self.assertEqual(adj.SLOTS, 2)
        self.assertEqual(sorted(fake.asked()), list(range(1, 8)))
        self.assertEqual(sorted(result["answers"], key=int), [str(n) for n in range(1, 8)])

    def test_memory_probe_stops_the_run(self):
        # Arrange: plenty of memory at the start and after 10 answers, then under 15% after 20
        rows = [row(n) for n in range(1, 31)]
        fake = FakeServer({n: '{"urn": "1", "confidence": 0.95, "reason": "Woodlea"}' for n in range(1, 31)})
        adj.post_json = fake
        readings = iter([80, 60, 12, 80])
        probes = []

        def probe():
            probes.append(1)
            return next(readings)

        with tempfile.TemporaryDirectory() as tmp:
            ckpt, out = Path(tmp) / "ck.jsonl", Path(tmp) / "o.json"
            # Act
            first = adj.run(rows, server="http://fake/v1", checkpoint=ckpt, out=out, log=lambda *_: None, slots=1, memory_probe=probe)
            low = adj.run(rows, server="http://fake/v1", checkpoint=ckpt, out=out, log=lambda *_: None, slots=1, memory_probe=lambda: 9)
            # Assert
            self.assertEqual(len(probes), 3, "checked before the run and every 10 answers")
            self.assertEqual(fake.asked(), list(range(1, 21)))
            self.assertEqual(len(first["answers"]), 20)
            self.assertEqual(len(low["answers"]), 20, "under 15% free at the start asks nothing but keeps what is done")
            self.assertEqual(adj.memory_free_pct.__name__, adj.run.__kwdefaults__["memory_probe"].__name__)

    def test_partial_checkpoint_lines_are_dropped_on_resume(self):
        # Arrange: a garbage line in the middle and a half-written last line
        fake = FakeServer({2: '{"urn": "1", "confidence": 0.95, "reason": "Woodlea"}'})
        adj.post_json = fake
        with tempfile.TemporaryDirectory() as tmp:
            ckpt = Path(tmp) / "ck.jsonl"
            good = {"charity_number": 1, "model": adj.MODEL, "prompt_version": "v1", "raw": '{"urn": "1", "confidence": 0.95}'}
            ckpt.write_text(json.dumps(good) + "\nnot json\n" + '{"charity_number": 2, "mod', encoding="utf-8")
            # Act
            adj.run([row(1), row(2)], server="http://fake/v1", checkpoint=ckpt, out=Path(tmp) / "o.json", log=lambda *_: None,
                    slots=1, memory_probe=lambda: 80)
            lines = [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines()]
        # Assert
        self.assertEqual(fake.asked(), [2])
        self.assertEqual([l["charity_number"] for l in lines], [1, 2])

    def test_prompt_lists_candidates_and_facts(self):
        # Arrange
        r = row(5, status="Registered", removed=None, postcode="GU33 7AB", address=["The School", "Liphook"], latest_income=1234.0,
                also_fits_independent=["Woodlea House School"],
                candidates=[cand("1", "Woodlea Primary School", preds=["Woodlea County Primary"], matched=True)])
        # Act
        text = adj.user_prompt(r)
        # Assert
        self.assertIn("Charity 5: FRIENDS OF WOODLEA SCHOOL", text)
        self.assertIn("Status: registered", text)
        self.assertIn("Address: The School, Liphook GU33 7AB", text)
        self.assertIn("Latest income: £1,234", text)
        self.assertIn("Independent schools with a fitting name in the area (not candidates): Woodlea House School", text)
        self.assertIn("- URN 1: Woodlea Primary School | Primary | Liphook GU33 7AA | former names: Woodlea County Primary | already has a matched PTA", text)


class ImportPilotTest(unittest.TestCase):
    def test_pilot_answers_keep_the_pilots_acceptance(self):
        # Arrange: one line per acceptance rule, a duplicate (the later line wins) and a half-written last line
        rows = [row(n) for n in range(1, 12)]
        lines = [pilot_line(1, "1"),                                              # accepted
                 pilot_line(2, "1", confidence=0.85),                             # under 0.9
                 pilot_line(3, "1", name_consistent=False, name_check="leftover: orchestra"),
                 pilot_line(4, "999", name_consistent=None, valid=False),         # not a candidate
                 pilot_line(5, "1", confidence=True),                             # not a probability
                 pilot_line(6, "1", model="laguna-xs-2.1"),                       # another model's run
                 pilot_line(7, "1", error="URLError: timed out"),
                 pilot_line(8, None, reason="shared: 1 2 infant and junior on one site", name_consistent=None),
                 pilot_line(9, "1", confidence=0.5), pilot_line(9, "1", confidence=0.96),
                 pilot_line(10, "1", reason="shared: 1 and 2"),                   # shared, even with an urn
                 pilot_line(99, "1"),                                             # not in the rows
                 '{"charity_number": 11, "model": "qwen/qw']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "full_qwen38.jsonl"
            path.write_text("\n".join(lines), encoding="utf-8")
            # Act
            got = adj.import_pilot(path, rows)
        answers = got["answers"]
        # Assert
        self.assertEqual(sorted(answers, key=int), ["1", "2", "3", "4", "5", "8", "9", "10"])
        self.assertEqual({k for k, a in answers.items() if a["accepted"]}, {"1", "9"})
        self.assertEqual(answers["1"], {"urn": "1", "confidence": 0.95, "reason": "fits", "name_consistent": True, "accepted": True})
        self.assertIn("[guard: leftover: orchestra]", answers["3"]["reason"])
        self.assertIsNone(answers["5"]["confidence"])
        self.assertEqual(answers["8"]["urn"], None)
        self.assertTrue(answers["8"]["reason"].startswith("shared:"))
        self.assertEqual(got["source"]["unreadable_lines"], 1)
        self.assertNotIn("spot_check", got, "a fresh import always needs a fresh spot check")
        self.assertEqual((got["model"], got["prompt_version"], got["threshold"]), (adj.MODEL, "v1", 0.9))

    def test_import_pilot_command_writes_valid_json(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "run.jsonl").write_text(pilot_line(1, "1") + "\n" + pilot_line(2, "1", confidence=float("inf")) + "\n", encoding="utf-8")
            (tmp / "input.jsonl").write_text(json.dumps(row(1)) + "\n" + json.dumps(row(2)) + "\n", encoding="utf-8")
            # Act
            adj.main(["import-pilot", "--pilot", str(tmp / "run.jsonl"), "--input", str(tmp / "input.jsonl"), "--out", str(tmp / "llm.json")])
            text = (tmp / "llm.json").read_text(encoding="utf-8")
        # Assert
        self.assertNotIn("Infinity", text)
        data = json.loads(text)
        self.assertEqual(data["source"]["input"], str(tmp / "input.jsonl"))
        self.assertEqual([k for k, a in data["answers"].items() if a["accepted"]], ["1"])


class SpotCheckTest(unittest.TestCase):
    def llm(self, n):
        return {"model": adj.MODEL, "prompt_version": "v1",
                "answers": {str(i): {"urn": "1", "confidence": 0.95, "reason": f"pick {i}", "name_consistent": True, "accepted": True}
                            for i in range(1, n + 1)}
                | {"999": {"urn": None, "confidence": 0.9, "reason": "shared: 1 2", "name_consistent": False, "accepted": False}}}

    def test_sample_then_spot_check_opens_the_gate(self):
        # Arrange
        llm, rows = self.llm(60), [row(i) for i in range(1, 61)]
        with tempfile.TemporaryDirectory() as tmp:
            review = Path(tmp) / "pta_llm_review.md"
            # Act: draw 50, judge them all right, record
            picks = adj.write_sample(llm, rows, review)
            sheet = review.read_text(encoding="utf-8")
            review.write_text(sheet.replace("| ? |", "| right |"), encoding="utf-8")
            spot = adj.spot_check(review, llm)
        # Assert
        self.assertEqual(len(picks), 50)
        self.assertEqual(len(set(picks)), 50)
        self.assertEqual(sheet.count("| ? |"), 50)
        self.assertIn("1 'shared:' answers go to pta.py's deterministic shared step", sheet)
        self.assertIn("URN 1 Woodlea Primary School", sheet)
        self.assertEqual((spot["n"], spot["wrong"], spot["unsure"]), (50, 0, 0))
        self.assertEqual(spot["sampled"], picks)
        self.assertIsNone(adj.pta.llm_gate(llm))

    def test_wrong_unjudged_or_stale_sheets_keep_the_gate_shut(self):
        # Arrange
        llm, rows = self.llm(60), [row(i) for i in range(1, 61)]
        with tempfile.TemporaryDirectory() as tmp:
            review = Path(tmp) / "review.md"
            adj.write_sample(llm, rows, review)
            sheet = review.read_text(encoding="utf-8")
            # Act / Assert: one wrong pick is recorded and keeps the gate shut
            review.write_text(sheet.replace("| ? |", "| right |").replace("| right |", "| wrong |", 1), encoding="utf-8")
            self.assertEqual(adj.spot_check(review, llm)["wrong"], 1)
            self.assertEqual(adj.pta.llm_gate(llm), "spot check found 1 wrong")
            # an unjudged row is refused
            review.write_text(sheet.replace("| ? |", "| right |", 49), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "verdict"):
                adj.spot_check(review, llm)
            # a pick no longer accepted (a newer import) is refused
            review.write_text(sheet.replace("| ? |", "| right |"), encoding="utf-8")
            first = int(re.search(r"\((\d+)\);", sheet).group(1))
            llm["answers"][str(first)]["accepted"] = False
            with self.assertRaisesRegex(ValueError, "fresh sample"):
                adj.spot_check(review, llm)

    def test_sample_command_writes_to_an_overridable_path(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "input.jsonl").write_text("".join(json.dumps(row(i)) + "\n" for i in range(1, 4)), encoding="utf-8")
            llm = self.llm(3) | {"source": {"input": str(tmp / "input.jsonl")}}
            (tmp / "llm.json").write_text(json.dumps(llm), encoding="utf-8")
            # Act
            adj.main(["sample", "--llm", str(tmp / "llm.json"), "--out", str(tmp / "sheet.md")])
            sheet = (tmp / "sheet.md").read_text(encoding="utf-8")
        # Assert
        self.assertEqual(sheet.count("| ? |"), 3)
        self.assertEqual(adj.REVIEW.name, "pta_llm_review.md")


if __name__ == "__main__":
    unittest.main()
