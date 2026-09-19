"""Chunker tests (no API)."""

from __future__ import annotations

from swrag.ingestion.chunker import chunk_document
from swrag.types import Document


def _doc(text: str) -> Document:
    return Document(doc_id="sample", title="Sample", path="sample.txt", text=text)


def test_short_document_is_one_chunk() -> None:
    text = "The quiet study floor is Level 3."
    chunks = chunk_document(_doc(text))
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "sample::c000"
    assert chunks[0].text == text
    assert chunks[0].page is None
    assert chunks[0].start_char >= 0
    assert chunks[0].end_char <= len(text)


def test_long_document_splits_under_budget() -> None:
    paragraph = "Harbor credits are used across campus. " * 20
    chunks = chunk_document(_doc(paragraph.strip()), max_chars=120, overlap=20)
    assert len(chunks) >= 2
    assert all(len(chunk.text) <= 120 for chunk in chunks)


def test_consecutive_chunks_share_overlap() -> None:
    text = "abcdefghijklmnopqrstuvwxyz" * 8
    chunks = chunk_document(_doc(text), max_chars=50, overlap=10)
    assert len(chunks) >= 2
    assert chunks[1].text[:10] in chunks[0].text
