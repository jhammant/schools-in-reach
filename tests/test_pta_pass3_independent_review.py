"""Offline regression reproductions for the independent B4 review."""

import json
from urllib.error import URLError

import pytest

from pipeline.money import pta
from pipeline.money import pta_adjudicate as adj


def school(urn, name, postcode="GU14 1AA", **extra):
    return {
        "urn": str(urn),
        "name": name,
        "postcode": postcode,
        "phase": "Primary",
        "la_code": "850",
        "council": "Hampshire",
        "type_group": "Local authority maintained schools",
        **extra,
    }


def charity(name, postcode="GU14 1AA", **extra):
    return {
        "registered_charity_number": 1000001,
        "linked_charity_number": 0,
        "charity_name": name,
        "charity_contact_postcode": postcode,
        "charity_registration_status": "Registered",
        "date_of_registration": "2004-01-01",
        "latest_income": 1000,
        **extra,
    }


def build_fixture(tmp_path, schools, charities, llm=None):
    """Run the public builder with all inputs and outputs isolated from the live cache."""
    data = tmp_path / "data"
    (data / "england").mkdir(parents=True)
    (data / "england" / "las.json").write_text(
        json.dumps({"las": [{"la_code": "850", "name": "Hampshire"}]}), encoding="utf-8"
    )
    register = data / "la" / "850"
    register.mkdir(parents=True)
    (register / "schools.json").write_text(json.dumps({"schools": schools}), encoding="utf-8")
    extracts = tmp_path / "charities"
    extracts.mkdir()
    (extracts / "publicextract.charity.json").write_text(json.dumps(charities), encoding="utf-8")
    (extracts / "publicextract.charity_annual_return_history.json").write_text("[]", encoding="utf-8")
    llm_path = tmp_path / "pta_llm.json"
    if llm is not None:
        llm_path.write_text(json.dumps(llm), encoding="utf-8")
    output = tmp_path / "pta.json"
    pta.main([
        "--site-data", str(data), "--charity-dir", str(extracts),
        "--out", str(output), "--report", str(tmp_path / "report.md"),
        "--links", str(tmp_path / "absent-links.csv"),
        "--ambiguous", str(tmp_path / "ambiguous.jsonl"),
        "--llm", str(llm_path), "--crawl", str(tmp_path / "absent-crawl.json"),
    ])
    return json.loads(output.read_text(encoding="utf-8"))["schools"]


def test_shared_answer_cannot_override_an_independent_school_blocker(tmp_path):
    # Arrange: the full charity name AND its contact postcode belong to the independent.
    schools = [
        school(100001, "Woodlea Infant School"),
        school(100002, "Woodlea Junior School", "GU14 1AB"),
        school(100003, "Woodlea Park School", "GU14 2BB", type_group="Independent schools"),
    ]
    record = charity("FRIENDS OF WOODLEA PARK SCHOOL", "GU14 2BB")
    first, _ = pta.match(schools, [record])
    second, _ = pta.match_pass2(schools, [record], {1000001}, {1000001: ["Hampshire"]}, {}, {})
    assert first == second == {}
    llm = {
        "spot_check": {"n": 50, "wrong": 0},
        "answers": {"1000001": {
            "urn": None, "confidence": 0.99, "accepted": False, "name_consistent": False,
            "reason": "shared: 100001 and 100002",
        }},
    }

    # Act: the model's unchecked shared suggestion reaches the real output path.
    matches = build_fixture(tmp_path, schools, [record], llm)

    # Assert: a model suggestion cannot turn a known independent PTA into state-school income.
    assert matches == {}, "The shared-answer path bypassed the independent-school rejection"


def test_widened_joint_pta_matches_both_schools_at_one_postcode(tmp_path):
    # Arrange: an explicitly joint dotted PTA, with both schools on the same site.
    schools = [school(100001, "Woodlea Infant School"), school(100002, "Woodlea Junior School")]
    record = charity("WOODLEA INFANT AND JUNIOR SCHOOLS P.T.A.")

    # Act
    matches = build_fixture(tmp_path, schools, [record])

    # Assert: the pair is the joint target, with reciprocal sharing for income allocation.
    assert set(matches) == {"100001", "100002"}, "A shared postcode discarded the explicit joint PTA"
    assert matches["100001"][0]["shared_with"] == ["100002"]
    assert matches["100002"][0]["shared_with"] == ["100001"]


def test_broad_activity_backed_school_fund_is_loaded_and_matched(tmp_path):
    # Arrange: all three broad-tier conditions from crawl_spec section 5, plus exact postcode.
    schools = [school(100001, "Woodlea Primary School")]
    record = charity(
        "WOODLEA SCHOOL FUND",
        charity_activities="Parents organise PTA fundraising events to buy equipment for school pupils.",
    )

    # Act
    matches = build_fixture(tmp_path, schools, [record])

    # Assert: broad tier requires activity evidence, but should enter rule f when that evidence exists.
    assert set(matches) == {"100001"}, "The required activity-backed broad tier never reaches the matcher"
    assert matches["100001"][0]["match"]["method"] == "postcode-exact"


@pytest.mark.parametrize(("name", "school_name"), [
    ("ST JOHNS P.T.A.", "St John's Catholic Primary School"),
    ("SACRED HEART PARENT/TEACHER ASSOCIATION", "Sacred Heart Catholic Primary School"),
])
def test_explicit_widened_pta_marker_allows_a_saint_name_at_exact_postcode(tmp_path, name, school_name):
    # Arrange: actual PTA wording, the entire school name after normalisation, and its exact postcode.
    schools = [school(100001, school_name)]
    record = charity(name)

    # Act
    matches = build_fixture(tmp_path, schools, [record])

    # Assert: these required new forms are equivalent to the established undotted PTA wording.
    assert set(matches) == {"100001"}, "A genuine PTA marker was treated as an ambiguous church friends group"
    assert matches["100001"][0]["match"]["method"] == "postcode-exact"


def test_model_without_positive_loaded_evidence_is_refused_before_chat(tmp_path, monkeypatch):
    # Arrange: /v1/models lists an installed model, but no API confirms it is loaded.
    chats = []

    def fake_http(url, payload=None, timeout=120):
        if url == "http://fake/v1/models":
            return {"data": [{"id": adj.MODEL}]}
        if url == "http://fake/api/v0/models":
            raise URLError("model state unavailable")
        chats.append(payload)
        return {"choices": [{"message": {"content": '{"urn": null, "confidence": 1, "reason": "none"}'}}]}

    monkeypatch.setattr(adj, "post_json", fake_http)
    rows = [{"charity_number": 1000001, "charity_name": "WOODLEA PTA", "candidates": []}]

    # Act / Assert: fail closed; a completion could otherwise trigger a JIT load.
    with pytest.raises(adj.ModelRefused):
        adj.run(rows, server="http://fake/v1", checkpoint=tmp_path / "checkpoint.jsonl",
                out=tmp_path / "llm.json", memory_probe=lambda: 80, log=lambda *_: None)
    assert chats == []


def test_shared_reason_with_nonnull_urn_reaches_deterministic_pairing(tmp_path):
    # Arrange: a model follows the shared-reason convention but also fills the urn field.
    row = {
        "charity_number": 1000001, "charity_name": "WOODLEA SCHOOLS PTA",
        "candidates": [
            {"urn": "100001", "name": "Woodlea Infant School", "phase": "Primary"},
            {"urn": "100002", "name": "Woodlea Junior School", "phase": "Primary"},
        ],
    }
    raw = json.dumps({"urn": "100001", "confidence": 0.99, "reason": "shared: 100001 and 100002"})
    schools = [school(100001, "Woodlea Infant School"), school(100002, "Woodlea Junior School")]
    record = charity("WOODLEA SCHOOLS PTA", postcode=None)

    # Act
    answer = adj.judge(adj.parse_answer(raw), row, adj.THRESHOLD)
    llm = {"spot_check": {"n": 50, "wrong": 0}, "answers": {"1000001": answer}}
    matches = build_fixture(tmp_path, schools, [record], llm)

    # Assert: route the shared suggestion to deterministic validation, never one-school attribution.
    assert set(matches) == {"100001", "100002"}, "The shared answer put all income on only the first school"
    assert matches["100001"][0]["shared_with"] == ["100002"]
    assert matches["100002"][0]["shared_with"] == ["100001"]
