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
class GoldQuestion:
    """One evaluation question with its offline ground truth.

    ``answers`` holds acceptable short answers (aliases), and is empty when
    ``answerable`` is False. Per ADR 003 these are never read at runtime.
    """

    question_id: str
    question: str
    answerable: bool
    answers: tuple[str, ...] = field(default_factory=tuple)
    supporting_doc_ids: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


@dataclass(frozen=True)
class AnswerScore:
    """Offline correctness of one answer against a ``GoldQuestion``.

    Three metrics are recorded because they disagree in ways that matter.
    ``exact_match`` is strict and near-zero on free-form generated prose.
    ``contains_answer`` is the lenient Contain-Acc variant used in the RAG
    literature. ``f1`` sits in between. Which one is primary is an open
    methodology decision (issue #6), so all three are stored rather than
    collapsing them early.
    """

    exact_match: bool
    contains_answer: bool
    f1: float
    abstained: bool
    answerable: bool


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
    provider: dict[str, Any] | None = field(default=None)
    question_id: str | None = field(default=None)


@dataclass(frozen=True)
class BaselineRunResult:
    run_id: str
    query: str
    answer: str
    retrieval: RetrievalResult
    generation_model: str
    embedding_model: str
    trace_path: Path | None = field(default=None)
