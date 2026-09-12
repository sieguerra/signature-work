"""Citation parser tests. No API."""

from __future__ import annotations

from swrag.tracing.citations import citation_spans


def test_known_chunk_id_is_linked() -> None:
    spans = citation_spans(
        "Saturday 10:00-16:00 [harbor-library::c000].",
        {"harbor-library::c000"},
    )
    assert ("[harbor-library::c000]", "harbor-library::c000") in spans
    assert any(text.startswith("Saturday") and chunk_id is None for text, chunk_id in spans)


def test_unknown_brackets_are_not_bound_to_another_chunk() -> None:
    spans = citation_spans(
        "See [not-a-chunk] and [harbor-library::c000].",
        {"harbor-library::c000"},
    )
    by_text = {text: chunk_id for text, chunk_id in spans}
    assert by_text["[not-a-chunk]"] is None
    assert by_text["[harbor-library::c000]"] == "harbor-library::c000"


def test_adjacent_citations_are_separate_spans() -> None:
    spans = citation_spans(
        "[harbor-library::c000][harbor-hours::c001]",
        {"harbor-library::c000", "harbor-hours::c001"},
    )
    linked = [chunk_id for _, chunk_id in spans if chunk_id]
    assert linked == ["harbor-library::c000", "harbor-hours::c001"]


def test_empty_answer_does_not_crash() -> None:
    assert citation_spans("", {"harbor-library::c000"}) == []


def test_html_in_the_answer_stays_plain_text_in_the_parser() -> None:
    spans = citation_spans(
        "<script>alert(1)</script> [harbor-library::c000]",
        {"harbor-library::c000"},
    )
    assert spans[0] == ("<script>alert(1)</script> ", None)
    assert spans[1] == ("[harbor-library::c000]", "harbor-library::c000")
