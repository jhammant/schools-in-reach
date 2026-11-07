"""Independent, offline regression cases for the data-honesty unit."""

import re
from html import unescape
from statistics import median
from types import SimpleNamespace

import pytest

from pipeline.money import school_page, series, status, timeline
from pipeline.money.test_school_page import Figures, make_ctx, make_item, nearby_school, section
from pipeline.money.test_series import charity, row


def render_rows(rows, pta=(), **context):
    item = make_item(pta=pta)
    item.update(rows=rows, latest=rows[-1], status=status.assess(rows))
    sx = series.school_series(rows, pta)
    ctx = make_ctx(item, sx, timeline=timeline.status_by_year(rows), **context)
    return sx, school_page.render(item, ctx)["body"]


def federation_rows_with_suspect_latest():
    return [
        row(year, pupils=pupils, total_income=12_000_000,
            total_expenditure=12_500_000, teaching_staff=5_000_000,
            federated="Lead school")
        for year, pupils in [("2021-22", 1550), ("2022-23", 1550),
                             ("2023-24", 1550), ("2024-25", 437)]
    ]


@pytest.mark.parametrize("section_id", ["spending", "split", "ptfa"])
def test_all_school_page_figures_respect_suspect_pupil_denominators(section_id):
    # Arrange: the series detects the latest count as one school's pupils against
    # the whole federation's income; PTA returns use that same academic year.
    rows = federation_rows_with_suspect_latest()
    pta = [charity(1103834, [("2024-08", 10_000, 9_000), ("2025-08", 10_000, 9_000)])]

    # Act: use the real series and full page render, not manually inserted flags.
    sx, body = render_rows(rows, pta)
    figures = Figures(section(body, section_id)).figures
    leaked = [(f["data-mf"], f["data-pp"]) for f in figures
              if f.get("data-year") == "2024-25" and "data-pp" in f
              and "suspect" not in f.get("class", "").split()]

    # Assert: suppress the dubious per-pupil value or mark it as suspect (C5).
    assert "pupils" in sx["flags"]["suspect"]["2024-25"]
    assert not leaked, f"{section_id} still divides by the suspect pupil count: {leaked}"


def test_national_pta_comparison_excludes_suspect_pupil_year(monkeypatch):
    # Arrange: a conforming C1 helper accepts the two positive amounts. It is the
    # caller's responsibility to exclude a denominator marked suspect by C5.
    calls = []

    def ratio_words(a, b):
        calls.append((a, b))
        return "about double" if a and b and a > 0 and b > 0 else None

    monkeypatch.setattr(school_page, "phrasing", SimpleNamespace(ratio_words=ratio_words))
    pta = [charity(1103834, [("2025-08", 10_000, 9_000)],
                   match={"confidence": "high", "method": "postcode"})]

    # Act.
    sx, body = render_rows(federation_rows_with_suspect_latest(), pta,
                          pta_national={"by_year": {"2024-25": {"median_pp": 12}}})
    pta_text = unescape(section(body, "ptfa"))

    # Assert: the national context can remain, but this school cannot be compared.
    assert "pupils" in sx["flags"]["suspect"]["2024-25"]
    assert "This school's parents' association raised about double" not in pta_text, calls


def test_what_changed_does_not_describe_falling_spending_as_rising():
    # Arrange: spending fell 10%, but income fell 20%, causing a real deficit.
    rows = [row("2023-24", total_income=1_000_000, total_expenditure=1_000_000,
                in_year_balance=0, revenue_reserve=50_000),
            row("2024-25", total_income=800_000, total_expenditure=900_000,
                in_year_balance=-100_000, revenue_reserve=-50_000)]

    # Act.
    _, body = render_rows(rows)
    changed = re.search(r'<p class="sp-changed">(.*?)</p>', body, re.S)

    # Assert: retain an explanation, but do not claim spending rose when it fell.
    assert changed is not None
    text = unescape(re.sub(r"<[^>]+>", " ", changed.group(1)))
    assert "spending per pupil rose" not in text, text


def test_nearby_ratio_names_the_population_used_for_its_median(monkeypatch):
    # Arrange: the existing nearby fixture follows nearby_doc's contract: the
    # median includes this school. Neighbours alone have a different median.
    item, ctx = nearby_school()
    monkeypatch.setattr(school_page, "phrasing", SimpleNamespace(
        ratio_words=lambda a, b: "about the same as" if a and b else None))
    neighbours = [r["spend_pp"] for r in ctx["nearby"]["schools"] if r.get("spend_pp") is not None]
    neighbour_median = median(neighbours)
    assert neighbour_median != ctx["nearby"]["medians"]["spend_pp"]

    # Act.
    body = school_page.render(item, ctx)["body"]
    line = re.search(r'<p class="nb-ratio">(.*?)</p>', body, re.S)
    assert line is not None
    displayed_median = float(Figures(line.group(1)).figures[-1]["data-v"])
    text = unescape(re.sub(r"<[^>]+>", " ", line.group(1)))

    # Assert: either name the inclusive population or use the neighbours' median.
    labels_only_neighbours = re.search(r"median of the \d+ nearest", text)
    assert not labels_only_neighbours or displayed_median == neighbour_median, (
        f"The sentence claims a neighbours-only median ({neighbour_median}) "
        f"but shows {displayed_median}, which includes this school: {text}")
