"""Citation parser tests. No API."""

from __future__ import annotations

from swrag.tracing.citations import citation_spans, looks_like_chunk_id


def test_known_chunk_id_is_linked() -> None:
    spans = citation_spans(
        "Saturday 10:00-16:00 [harbor-library::c000].",
        {"harbor-library::c000"},
    )
    linked = [span for span in spans if span.kind == "link"]
    assert linked == [
        ("[harbor-library::c000]", "harbor-library::c000", "link"),
    ]
    assert any(span.text.startswith("Saturday") and span.kind == "text" for span in spans)


def test_unknown_brackets_are_not_bound_to_another_chunk() -> None:
    spans = citation_spans(
        "See [not-a-chunk] and [harbor-library::c000].",
        {"harbor-library::c000"},
    )
    by_text = {span.text: span for span in spans}
    assert by_text["[not-a-chunk]"].kind == "text"
    assert by_text["[not-a-chunk]"].chunk_id is None
    assert by_text["[harbor-library::c000]"].kind == "link"
    assert by_text["[harbor-library::c000]"].chunk_id == "harbor-library::c000"


def test_unknown_chunk_shaped_id_is_missing_not_linked() -> None:
    spans = citation_spans(
        "See [ghost-doc::c009] and [harbor-library::c000].",
        {"harbor-library::c000"},
    )
    by_text = {span.text: span for span in spans}
    assert by_text["[ghost-doc::c009]"].kind == "missing"
    assert by_text["[ghost-doc::c009]"].chunk_id == "ghost-doc::c009"
    assert by_text["[harbor-library::c000]"].kind == "link"


def test_adjacent_citations_are_separate_spans() -> None:
    spans = citation_spans(
        "[harbor-library::c000][harbor-hours::c001]",
        {"harbor-library::c000", "harbor-hours::c001"},
    )
    linked = [span.chunk_id for span in spans if span.kind == "link"]
    assert linked == ["harbor-library::c000", "harbor-hours::c001"]


def test_empty_answer_does_not_crash() -> None:
    assert citation_spans("", {"harbor-library::c000"}) == []


def test_html_in_the_answer_stays_plain_text_in_the_parser() -> None:
    spans = citation_spans(
        "<script>alert(1)</script> [harbor-library::c000]",
        {"harbor-library::c000"},
    )
    assert spans[0] == ("<script>alert(1)</script> ", None, "text")
    assert spans[1] == ("[harbor-library::c000]", "harbor-library::c000", "link")


def test_looks_like_chunk_id_matches_v1_shape_only() -> None:
    assert looks_like_chunk_id("dku-library-hours::c001")
    assert not looks_like_chunk_id("not-a-chunk")
    assert not looks_like_chunk_id("harbor-library")
    assert not looks_like_chunk_id("::c000")
