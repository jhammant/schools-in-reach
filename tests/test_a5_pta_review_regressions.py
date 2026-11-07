"""Offline reproductions for the A5 independent review."""

import json
from unittest.mock import patch

import pytest

from pipeline.money import pta
from pipeline.money import pta_adjudicate as adj


def school(urn, name, postcode=None, **extra):
    return {
        "urn": urn,
        "name": name,
        "postcode": postcode,
        "phase": "Primary",
        "la_code": "850",
        "council": "Hampshire",
        "type_group": "Local authority maintained schools",
        **extra,
    }


def charity(number, name, postcode=None, **extra):
    return {
        "registered_charity_number": number,
        "linked_charity_number": 0,
        "charity_name": name,
        "charity_registration_status": "Registered",
        "charity_contact_postcode": postcode,
        "date_of_registration": "2004-01-01",
        "latest_income": 1000,
        **extra,
    }


def pass2(schools, charities, predecessors=None):
    numbers = {c["registered_charity_number"] for c in charities}
    return pta.match_pass2(
        schools,
        charities,
        numbers,
        {n: ["Hampshire"] for n in numbers},
        {},
        predecessors or {},
        councils={"850": "Hampshire"},
    )


def ambiguous_row(number=10):
    return {
        "charity_number": number,
        "charity_name": "WOODLEA PRIMARY SCHOOL PTA",
        "candidates": [
            {
                "urn": "1",
                "name": "Woodlea Primary School",
                "phase": "Primary",
                "town": "Liphook",
                "predecessor_names": [],
            }
        ],
    }


def test_sector_match_keeps_longer_independent_namesake_as_blocker():
    # Arrange: the treasurer is near the state school, but the full charity name
    # belongs to an independent elsewhere in the same postcode district.
    schools = [
        school(1, "Woodlea Primary School", "GU14 1AA", street="Park Road"),
        school(2, "Woodlea Park School", "GU14 2BB", type_group="Independent schools"),
    ]
    charities = [charity(10, "FRIENDS OF WOODLEA PARK SCHOOL", "GU14 1ZZ")]

    # Act
    matches, _ = pta.match(schools, charities)

    # Assert: G1 must retain the longer independent name in the district tie.
    assert matches == {}, "The independent school's charity was assigned to the state primary"


def test_predecessor_cannot_override_current_gias_phase():
    # Arrange: the spec's Arena/Perry Beeches case; the current school is
    # secondary even though one of its GIAS predecessor names says Junior.
    schools = [school(1, "Arena Academy", "B42 2AA", phase="Secondary")]
    charities = [charity(10, "FRIENDS OF PERRY BEECHES JUNIOR SCHOOL")]
    predecessors = {"1": ["Perry Beeches Junior School"]}

    # Act
    matches, _ = pass2(schools, charities, predecessors)

    # Assert: G8 must rule out attributing a junior PTA to a secondary school.
    assert matches == {}, "The predecessor's phase masked the contradictory current GIAS phase"


def test_main_shares_pta_explicitly_naming_infant_and_junior(tmp_path):
    # Arrange: a joint PTA uses the infant school's contact address. Both
    # schools are present, and the name explicitly supports both phases.
    data = tmp_path / "data"
    register = data / "la" / "850"
    register.mkdir(parents=True)
    (data / "england").mkdir()
    (data / "england" / "las.json").write_text(
        json.dumps({"las": [{"la_code": "850", "name": "Hampshire"}]}), encoding="utf-8"
    )
    (register / "schools.json").write_text(
        json.dumps({"schools": [
            school(1, "Woodlea Infant School", "GU14 1AA"),
            school(2, "Woodlea Junior School", "GU14 1AB"),
        ]}), encoding="utf-8"
    )
    extracts = tmp_path / "charity"
    extracts.mkdir()
    (extracts / "publicextract.charity.json").write_text(
        json.dumps([charity(10, "WOODLEA INFANT AND JUNIOR SCHOOLS PTA", "GU14 1AA")]), encoding="utf-8"
    )
    (extracts / "publicextract.charity_annual_return_history.json").write_text("[]", encoding="utf-8")
    output = tmp_path / "pta.json"

    # Act: exercise the real pass-1 -> pass-2 -> export path with isolated inputs.
    pta.main([
        "--site-data", str(data), "--charity-dir", str(extracts),
        "--out", str(output), "--report", str(tmp_path / "report.md"),
        "--ambiguous", str(tmp_path / "ambiguous.jsonl"),
        "--links", str(tmp_path / "missing-links.csv"),
        "--llm", str(tmp_path / "missing-llm.json"),
        "--crawl", str(tmp_path / "missing-crawl.json"),
    ])
    matches = json.loads(output.read_text(encoding="utf-8"))["schools"]

    # Assert: the same joint charity is represented on both schools, reciprocally.
    assert set(matches) == {"1", "2"}, "An explicit joint PTA was assigned only to its contact school"
    assert matches["1"][0]["shared_with"] == ["2"]
    assert matches["2"][0]["shared_with"] == ["1"]


def test_ambiguous_candidate_limit_counts_state_schools_only():
    # Arrange: five state-school fits are within the specified export limit;
    # the independent is an extra warning, not a sixth candidate for the LLM.
    schools = [school(i, "Woodlea Primary School") for i in range(1, 6)]
    schools.append(school(6, "Woodlea School", type_group="Independent schools"))
    charities = [charity(10, "WOODLEA SCHOOL PTA")]

    # Act
    matches, rows = pass2(schools, charities)

    # Assert
    assert matches == {}
    assert len(rows) == 1, "An independent blocker caused all five valid state candidates to be dropped"
    assert rows[0]["kind"] == "several_fit"
    assert {c["urn"] for c in rows[0]["candidates"]} == {"1", "2", "3", "4", "5"}
    assert rows[0]["also_fits_independent"] == ["Woodlea School"]


def test_crawl_merge_requires_actual_parent_association_wording():
    # Arrange: 'transparent' contains 'parent', but says nothing about a PTA.
    registry = {10: charity(10, "Hampshire Educational Trust")}
    hit = {
        "charity_number": 10,
        "source_url": "https://woodlea.example/accounts",
        "evidence": "Our transparent accounts: registered charity 10",
    }
    matches = {}

    # Act
    count = pta.merge_crawl(matches, {"schools": {"1": [hit]}}, registry, {"1"})

    # Assert: a charity that fails is_parent_association needs real PTA evidence.
    assert count == 0, "The substring 'parent' inside 'transparent' was treated as PTA evidence"
    assert matches == {}


@pytest.mark.parametrize("metadata", [
    {"size_gb": 55},
    {"parameters": "70B"},
    {"metadata": {"size_bytes": 55_000_000_000}},
])
def test_oversized_model_metadata_is_refused(metadata):
    # Arrange: the id has no size hint, but the server explicitly reports an
    # oversized model. No network or model loading is allowed in this test.
    model = {"id": "opaque-model", **metadata}
    with patch.object(adj, "post_json", return_value={"data": [model]}):
        # Act / Assert
        with pytest.raises(adj.ModelRefused):
            adj.check_model("http://fake/v1", "opaque-model")


@pytest.mark.parametrize("confidence", [1.01, 95, float("inf"), True])
def test_out_of_range_model_confidence_is_not_accepted(confidence):
    # Arrange: a valid candidate and name must not make a malformed probability
    # (including a percentage written as 95) count as a confident answer.
    raw = json.dumps({"urn": "1", "confidence": confidence, "reason": "Woodlea fits"})

    # Act
    answer = adj.judge(adj.parse_answer(raw), ambiguous_row(), 0.8)

    # Assert
    assert not answer["accepted"], "An invalid 0..1 probability passed the acceptance threshold"


def test_checkpoint_resume_recovers_after_partial_final_line(tmp_path):
    # Arrange: a process stopped while appending its next answer. Preserve the
    # completed answer and retry only the incomplete charity.
    checkpoint = tmp_path / "checkpoint.jsonl"
    raw = '{"urn":"1","confidence":0.95,"reason":"Woodlea fits"}'
    completed = {
        "charity_number": 10,
        "model": adj.MODEL,
        "prompt_version": adj.PROMPT_VERSION,
        "raw": raw,
    }
    checkpoint.write_text(json.dumps(completed) + '\n{"charity_number":', encoding="utf-8")
    requested = []

    def fake_post(url, payload=None, timeout=120):
        if url.endswith("/models"):
            return {"data": [{"id": adj.MODEL}]}
        requested.append(int(payload["messages"][1]["content"].split()[1].rstrip(":")))
        return {"choices": [{"message": {"content": raw}}]}

    with patch.object(adj, "post_json", side_effect=fake_post):
        # Act
        result = adj.run(
            [ambiguous_row(10), ambiguous_row(11)], server="http://fake/v1",
            checkpoint=checkpoint, out=tmp_path / "llm.json", log=lambda *_: None,
        )

    # Assert: completion also leaves a checkpoint that the next resume can read.
    assert requested == [11]
    assert set(result["answers"]) == {"10", "11"}
    assert all(a["accepted"] for a in result["answers"].values())
    assert set(adj.load_checkpoint(checkpoint, adj.MODEL, adj.PROMPT_VERSION)) == {10, 11}
