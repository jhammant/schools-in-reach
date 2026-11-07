"""Offline regression probes for the standalone School Money build review."""

from html.parser import HTMLParser
import json
import types
import unittest

import pytest

from pipeline.money import build_money
from pipeline.money import test_build_money as builder_tests
from pipeline.money.test_build_money import make_site, row, school
from pipeline.seo import build_pages


class Attributes(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.links = []
        self.figures = []
        self.feed(markup)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "a":
            self.links.append(attributes.get("href"))
        if "data-mf" in attributes:
            self.figures.append(attributes)


@pytest.fixture(autouse=True)
def independent_optional_modules(monkeypatch):
    # These probes must be repeatable before and after the other units land.
    for name in ("shell", "areas", "timeline", "deflator"):
        monkeypatch.setattr(build_money, name, None)


def one_school(root, rows=None, pta=None):
    rows = rows or [row("100001", "2025-03", 2_000_000, 1_900_000, 100_000)]
    return make_site(root, [("204", "Hackney")], {"204": [school(100001, "Example Primary")]}, rows, pta)


def build_fixture(root, args, **kwargs):
    out = kwargs.pop("out", root / "site_money")
    build_money.build(*args, out=out, dsg_path=root / "no-dsg.json", **kwargs)
    return out


def school_markup(out):
    return (out / "school/100001-example-primary/index.html").read_text(encoding="utf-8")


def test_legacy_status_links_resolve_on_the_new_money_site(tmp_path):
    # Arrange: only the old status bundle is available to the independently deployed SEO site.
    args = one_school(tmp_path)
    money = build_fixture(tmp_path, args, out=tmp_path / "deployed-money")
    clean_path = "/school/100001-example-primary/"
    status = {"100001": {"status": "healthy", "label": "Healthy", "path": "/money" + clean_path}}
    old = args[0] / "money/data/status.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps(status), encoding="utf-8")

    # Act
    build_pages.build(args[0], crosslinks_path=tmp_path / "no-crosslinks.json")
    links = Attributes(school_markup(args[0])).links

    # Assert: the old /money prefix has to be removed before changing the origin.
    target = build_money.BASE_MONEY + clean_path
    assert target in links, f"Legacy status produced broken Money links: {[p for p in links if p and 'money.schoolsinreach.com/school/' in p or p and 'money.schoolsinreach.com/money/' in p]}"
    assert (money / clean_path.lstrip("/") / "index.html").is_file()


def test_historical_area_governance_follows_the_return_source(tmp_path):
    # Arrange: five maintained schools plus an academy's linked, maintained predecessor.
    schools = [school(100010 + n, f"Maintained {n}") for n in range(5)]
    schools.append(school(140001, "Converted Academy", type="Academy converter", trust="Example Trust"))
    rows = [row(str(100010 + n), "2024-03", 2_000_000, 1_900_000, 100_000) for n in range(5)]
    rows.extend([
        row("100099", "2024-03", 2_000_000, 1_900_000, 100_000),
        row("140001", "2025-08", 2_000_000, 1_900_000, 100_000, source="AAR", trust="Example Trust"),
    ])
    args = make_site(tmp_path, [("204", "Hackney")], {"204": schools}, rows)
    args[2].write_text("URN,LinkURN,LinkType\n140001,100099,Predecessor\n", encoding="utf-8")

    # Act
    out = build_fixture(tmp_path, args)
    data = json.loads((out / "data/a/council-204.json").read_text(encoding="utf-8"))
    historical = data["by_year"]["2023-24"]

    # Assert: all six schools reported CFR that year, even though one is now an academy.
    assert historical["all"]["schools"] == 6
    assert historical["council-run"]["schools"] == 6, historical
    assert historical["academy"] is None


def test_pta_history_uses_the_pupil_roll_from_its_own_year(tmp_path):
    # Arrange: pupil numbers triple; the PTA's older income must retain its old denominator.
    rows = [row("100001", "2023-03", 600_000, 590_000, 50_000, pupils=100),
            row("100001", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=300)]
    pta = {"100001": [{"charity_number": 1234567, "name": "Example PTA", "status": "Registered",
                       "latest_income": 30_000,
                       "history": [{"period_end": "2023-03", "income": 12_000, "expenditure": 9_000},
                                   {"period_end": "2025-03", "income": 30_000, "expenditure": 29_000}]}]}
    args = one_school(tmp_path, rows, pta)

    # Act
    out = build_fixture(tmp_path, args)
    figures = Attributes(school_markup(out)).figures
    old = [f for f in figures if f["data-mf"] == "pta_income" and float(f["data-v"]) == 12_000]

    # Assert
    assert old, "The historical PTA income must remain visible"
    assert all(float(f["data-pp"]) == 120 for f in old), old


def test_pta_latest_income_is_not_relabelled_as_a_newer_school_year(tmp_path):
    # Arrange: the charity's latest return is two years older than the school's latest return.
    rows = [row("100001", "2023-03", 600_000, 590_000, 50_000, pupils=100),
            row("100001", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=300)]
    pta = {"100001": [{"charity_number": 1234567, "name": "Example PTA", "status": "Registered",
                       "latest_income": 12_000,
                       "history": [{"period_end": "2023-03", "income": 12_000, "expenditure": 9_000}]}]}
    args = one_school(tmp_path, rows, pta)

    # Act
    out = build_fixture(tmp_path, args)
    amounts = [f for f in Attributes(school_markup(out)).figures if f["data-mf"] == "pta_income"]

    # Assert: both the summary and the history refer to the charity's actual reporting period.
    assert amounts
    assert all(f["data-year"] in {"2023-03", "2022-23"} for f in amounts), amounts


def test_school_history_figures_keep_the_school_source_link(tmp_path):
    # Arrange
    args = one_school(tmp_path, [row("100001", "2023-03", 600_000, 590_000, 50_000, pupils=100),
                                row("100001", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=300)])

    # Act
    out = build_fixture(tmp_path, args)
    old = [f for f in Attributes(school_markup(out)).figures
           if f["data-mf"] in {"total_income", "total_expenditure", "revenue_reserve"} and f["data-year"] == "2022-23"]

    # Assert: the explanation UI needs the source on the selected figure, not just on a latest tile.
    expected = build_money.FBIT + "/school/100001"
    assert len(old) >= 3
    assert all(f.get("data-src") == expected for f in old), old


def test_acceptance_school_json_test_allows_the_optional_areas_module(monkeypatch):
    # Arrange: an implementation of a2's documented contract is available.
    monkeypatch.setattr(build_money, "areas", types.SimpleNamespace(
        school_profile=lambda school, code, root: {
            "tags": {"governance": "council-run", "trust": None, "trust_size": None,
                     "admissions": None, "faith": None, "phase": "Primary", "gender": "Mixed", "sixth_form": False},
            "intake": {"fsm_pct": None, "fsm_pct_council": None, "fsm_pct_england": None},
            "area": {"lsoa": None, "imd_decile": None, "idaci_decile": None, "income_decile": None,
                     "pct_level4_plus": None, "pct_owned": None, "pct_social_rented": None,
                     "pct_households_not_deprived": None, "catchment": None, "msoa_income": None},
            "band": None,
        },
        build_areas=lambda rows, schools, pta, dsg, root: {
            "england": {"name": "England", "pupils_by_year": {}, "schools_by_year": {},
                        "by_year": {}, "dsg": {}, "statuses_latest": {}},
            "regions": {}, "councils": {}, "constituencies": {},
        },
    ))

    # Act: run the existing acceptance test under this supported configuration.
    result = unittest.TestResult()
    builder_tests.BuildMoneyTest("test_school_json_has_the_shared_keys").run(result)

    # Assert
    assert result.wasSuccessful(), "\n".join(detail for _, detail in result.failures + result.errors)


def test_explicit_output_symlink_does_not_delete_its_target(tmp_path):
    # Arrange: the new --out parameter names a symlink to an unrelated existing directory.
    args = one_school(tmp_path)
    target = tmp_path / "unrelated-content"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("preserve this file", encoding="utf-8")
    output_link = tmp_path / "output-link"
    output_link.symlink_to(target, target_is_directory=True)

    # Act: rejecting a symlink is allowed; deleting the directory it points to is not.
    try:
        build_fixture(tmp_path, args, out=output_link)
    except ValueError:
        pass

    # Assert
    assert sentinel.is_file(), "Resolving --out bypassed the symlink guard and deleted its target"
    assert sentinel.read_text(encoding="utf-8") == "preserve this file"
