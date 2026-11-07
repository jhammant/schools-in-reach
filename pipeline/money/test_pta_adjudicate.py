"""Tests for the local-model adjudicator; HTTP is faked by replacing post_json, no sockets."""
import json
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
    """Stands in for post_json: lists models, answers chat completions from a script keyed by charity number."""

    def __init__(self, answers, models=("qwen/qwen3.8-27b",)):
        self.answers, self.models, self.calls = answers, [{"id": m} for m in models], []

    def __call__(self, url, payload=None, timeout=120):
        self.calls.append((url, payload))
        if url.endswith("/models"):
            return {"data": self.models}
        number = int(payload["messages"][1]["content"].split()[1].rstrip(":"))
        return {"choices": [{"message": {"content": self.answers[number]}}]}


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
            first = adj.run(rows, server="http://fake/v1", checkpoint=ckpt, out=out, limit=2, prioritise_recent=True, log=lambda *_: None)
            asked_first = [int(p["messages"][1]["content"].split()[1].rstrip(":")) for _, p in fake.calls]
            second = adj.run(rows, server="http://fake/v1", checkpoint=ckpt, out=out, log=lambda *_: None)
            asked_total = [int(p["messages"][1]["content"].split()[1].rstrip(":")) for _, p in fake.calls]
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
        self.assertEqual(fake.calls[0][1]["temperature"], 0)
        self.assertEqual(fake.calls[0][1]["messages"][0]["content"], adj.SYSTEM_PROMPT)

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


if __name__ == "__main__":
    unittest.main()
