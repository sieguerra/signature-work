"""PDF ingest tests. No live OpenAI calls."""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from swrag.api.app import create_app
from swrag.ingestion.chunker import chunk_documents
from swrag.ingestion.loader import load_documents
from swrag.ingestion.pdf import PdfExtractError, extract_pdf_pages
from swrag.pipeline.baseline import run_query
from swrag.retrieval.fake_embedder import FakeEmbedder

_pdf_bytes_spec = importlib.util.spec_from_file_location(
    "pdf_bytes", Path(__file__).with_name("pdf_bytes.py")
)
assert _pdf_bytes_spec is not None and _pdf_bytes_spec.loader is not None
_pdf_bytes = importlib.util.module_from_spec(_pdf_bytes_spec)
_pdf_bytes_spec.loader.exec_module(_pdf_bytes)
simple_text_pdf = _pdf_bytes.simple_text_pdf

ROOT = Path(__file__).resolve().parents[1]
HARBOR = ROOT / "datasets" / "corpus"
FIXTURE_PDF = ROOT / "tests" / "fixtures" / "two-page-notice.pdf"
PAGE_ONE = "PAGEONE_HALYARD"
PAGE_TWO = "PAGETWO_WINDLASS"


def test_txt_only_corpus_is_unchanged() -> None:
    documents = load_documents(HARBOR)
    ids = {document.doc_id for document in documents}
    assert "harbor-library" in ids
    assert all(document.page is None for document in documents)
    assert all("::p" not in document.doc_id for document in documents)


def test_fixture_pdf_exposes_both_pages() -> None:
    pages = extract_pdf_pages(FIXTURE_PDF)
    by_page = dict(pages)
    assert PAGE_ONE in by_page[1]
    assert PAGE_TWO in by_page[2]


def test_load_documents_on_fixture_dir_is_page_aware() -> None:
    documents = load_documents(FIXTURE_PDF.parent)
    by_id = {document.doc_id: document for document in documents}
    assert by_id["two-page-notice::p1"].page == 1
    assert by_id["two-page-notice::p2"].page == 2
    assert PAGE_ONE in by_id["two-page-notice::p1"].text
    assert PAGE_TWO in by_id["two-page-notice::p2"].text
    assert by_id["two-page-notice::p1"].path.endswith("two-page-notice.pdf")


def test_pdf_chunks_carry_page_and_stable_ids() -> None:
    documents = load_documents(FIXTURE_PDF.parent)
    chunks = chunk_documents(documents)
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    first = by_id["two-page-notice::p1::c000"]
    second = by_id["two-page-notice::p2::c000"]
    assert first.page == 1
    assert second.page == 2
    assert PAGE_ONE in first.text
    assert PAGE_TWO in second.text


def test_retrieve_only_over_fixture_pdf_writes_page_on_the_trace(tmp_path: Path) -> None:
    result = run_query(
        PAGE_TWO,
        corpus_dir=FIXTURE_PDF.parent,
        output_dir=tmp_path,
        top_k=2,
        embedder=FakeEmbedder(),
        generate=False,
    )
    assert result.trace_path is not None
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    pages = {chunk.get("page") for chunk in payload["retrieved_chunks"]}
    texts = " ".join(chunk["text"] for chunk in payload["retrieved_chunks"])
    assert 2 in pages
    assert PAGE_TWO in texts
    assert all("page" in chunk for chunk in payload["retrieved_chunks"])


def test_empty_pdf_is_skipped_when_txt_exists(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "keep.txt").write_text("The quiet study floor is Level 3.", encoding="utf-8")
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with (tmp_path / "empty.pdf").open("wb") as handle:
        writer.write(handle)
    with caplog.at_level(logging.WARNING, logger="swrag.ingestion.loader"):
        documents = load_documents(tmp_path)
    assert [document.doc_id for document in documents] == ["keep"]
    assert "empty.pdf" in caplog.text


def test_corrupt_pdf_is_skipped_when_txt_exists(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "keep.txt").write_text("The quiet study floor is Level 3.", encoding="utf-8")
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4\nthis is not a pdf")
    with caplog.at_level(logging.WARNING, logger="swrag.ingestion.loader"):
        documents = load_documents(tmp_path)
    assert [document.doc_id for document in documents] == ["keep"]
    assert "broken.pdf" in caplog.text


def test_only_corrupt_pdf_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4\nthis is not a pdf")
    with pytest.raises(ValueError, match="No readable"):
        load_documents(tmp_path)


def test_corrupt_pdf_extract_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nthis is not a pdf")
    with pytest.raises(PdfExtractError):
        extract_pdf_pages(path)


def test_api_retrieve_on_corrupt_only_corpus_is_400(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    traces = tmp_path / "traces"
    corpus.mkdir()
    (corpus / "broken.pdf").write_bytes(b"%PDF-1.4\nthis is not a pdf")
    app = create_app(corpus_dir=corpus, traces_dir=traces)
    with TestClient(app) as client:
        response = client.post(
            "/api/runs",
            json={"question": PAGE_ONE, "mode": "retrieve_only"},
        )
    assert response.status_code == 400
    assert "readable" in response.json()["detail"].lower()


def test_api_retrieve_on_fixture_pdf_returns_pages(tmp_path: Path) -> None:
    app = create_app(corpus_dir=FIXTURE_PDF.parent, traces_dir=tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/runs",
            json={"question": PAGE_TWO, "mode": "retrieve_only", "top_k": 2},
        )
    assert response.status_code == 200
    chunks = response.json()["trace"]["retrieved_chunks"]
    assert any(chunk.get("page") == 2 and PAGE_TWO in chunk["text"] for chunk in chunks)


def test_tmp_pdf_from_bytes_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "note.pdf"
    path.write_bytes(simple_text_pdf(["ALPHA_ONLY", "BETA_ONLY"]))
    pages = dict(extract_pdf_pages(path))
    assert "ALPHA_ONLY" in pages[1]
    assert "BETA_ONLY" in pages[2]
