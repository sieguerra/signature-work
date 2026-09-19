"""Baseline pipeline tests without calling OpenAI."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.ingestion.loader import load_documents
from swrag.pipeline.baseline import run_query
from swrag.retrieval.fake_embedder import FakeEmbedder

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "corpus"


def test_loader_reads_toy_corpus() -> None:
    documents = load_documents(CORPUS)
    ids = {doc.doc_id for doc in documents}
    assert "harbor-library" in ids
    assert len(documents) >= 3


def test_run_query_retrieve_only_writes_trace(tmp_path: Path) -> None:
    result = run_query(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        top_k=3,
        embedder=FakeEmbedder(),
        generate=False,
    )
    assert result.trace_path is not None
    assert result.trace_path.exists()
    assert result.generation_model == "none"
    assert result.answer == ""
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert isinstance(payload.get("latency_ms"), (int, float))
    assert payload["latency_ms"] >= 0

    # Asserts plumbing, not retrieval quality. The corpus now contains
    # deliberate near-neighbours (ADR 004), so which document ranks top-3 is
    # expected to change and is measured by the experiment runner instead.
    assert len(result.retrieval.chunks) == 3
    corpus_doc_ids = {doc.doc_id for doc in load_documents(CORPUS)}
    assert all(scored.chunk.doc_id in corpus_doc_ids for scored in result.retrieval.chunks)
