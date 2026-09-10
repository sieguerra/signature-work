"""Shared dataclasses for the baseline RAG slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    path: str
    text: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    chunks: tuple[ScoredChunk, ...]
    top_k: int
    embedding_model: str


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    model: str


@dataclass(frozen=True)
class TraceRecord:
    run_id: str
    timestamp: str
    query: str
    retrieved_chunks: tuple[dict[str, Any], ...]
    answer: str
    model: str
    embedding_model: str
    top_k: int


@dataclass(frozen=True)
class BaselineRunResult:
    run_id: str
    query: str
    answer: str
    retrieval: RetrievalResult
    generation_model: str
    embedding_model: str
    trace_path: Path | None = field(default=None)
