"""Baseline retrieve-then-generate pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from swrag.config import load_provider_config
from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.evaluation.judge import GroundingJudge
from swrag.generation.openai_generator import OpenAIGenerator
from swrag.ingestion.chunker import chunk_documents
from swrag.ingestion.loader import load_documents
from swrag.retrieval.embedder import Embedder
from swrag.retrieval.memory_index import InMemoryIndex
from swrag.retrieval.openai_embedder import OpenAIEmbedder
from swrag.tracing.tracer import write_trace
from swrag.types import BaselineRunResult, GenerationResult, RetrievalResult, TraceRecord


def run_query(
    query: str,
    *,
    corpus_dir: str | Path,
    output_dir: str | Path,
    top_k: int = 4,
    embedder: Embedder | None = None,
    generate: bool = True,
    generator: OpenAIGenerator | None = None,
    question_id: str | None = None,
    judge: GroundingJudge | None = None,
) -> BaselineRunResult:
    """Run baseline RAG on ``query`` and write a JSON trace.

    ``embedder`` can be injected (tests use ``FakeEmbedder``). Generation can be
    skipped so ranking tests do not need an API key. ``question_id`` links the
    run back to a gold question when called from the experiment runner.
    ``judge`` is the runtime grounding evaluator (ADR 003). It must not be
    given gold labels; this function never loads the gold set.
    """
    documents = load_documents(corpus_dir)
    chunks = chunk_documents(documents)
    index = InMemoryIndex(embedder or OpenAIEmbedder())
    index.add(chunks)
    retrieval = index.search(query, top_k=top_k)

    if generate:
        generation = (generator or OpenAIGenerator()).generate(query, retrieval)
    else:
        generation = GenerationResult(answer="", model="none")

    runtime_eval = None
    diagnosis = None
    if judge is not None:
        runtime_eval = judge.judge(
            question=query,
            answer=generation.answer,
            retrieval=retrieval,
        )
        diagnosis = diagnose_runtime(runtime_eval)

    run_id = _new_run_id()
    timestamp = datetime.now(timezone.utc).isoformat()
    trace_path = write_trace(
        TraceRecord(
            run_id=run_id,
            timestamp=timestamp,
            query=query,
            retrieved_chunks=_chunks_payload(retrieval),
            answer=generation.answer,
            model=generation.model,
            embedding_model=retrieval.embedding_model,
            top_k=retrieval.top_k,
            provider=load_provider_config().as_trace_payload(),
            question_id=question_id,
            runtime_evaluation=(
                runtime_eval.as_trace_payload() if runtime_eval is not None else None
            ),
            diagnosis=diagnosis.as_trace_payload() if diagnosis is not None else None,
        ),
        output_dir,
    )
    return BaselineRunResult(
        run_id=run_id,
        query=query,
        answer=generation.answer,
        retrieval=retrieval,
        generation_model=generation.model,
        embedding_model=retrieval.embedding_model,
        trace_path=trace_path,
        runtime_evaluation=runtime_eval,
        diagnosis=diagnosis,
    )


def _chunks_payload(retrieval: RetrievalResult) -> tuple[dict, ...]:
    payload: list[dict] = []
    for scored in retrieval.chunks:
        chunk = scored.chunk
        payload.append(
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "score": scored.score,
                "text": chunk.text,
            }
        )
    return tuple(payload)


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"
