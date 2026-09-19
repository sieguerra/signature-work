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
    page: int | None = None


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    text: str
    start_char: int
    end_char: int
    page: int | None = None


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
    literature. ``f1`` sits in between. ADR 003 stores all three rather than
    collapsing them; offline scoring never feeds the runtime controller.
    """

    exact_match: bool
    contains_answer: bool
    f1: float
    abstained: bool
    answerable: bool


@dataclass(frozen=True)
class RuntimeEvaluation:
    """Runtime grounding signals. Must not be computed from gold labels.

    ADR 003: an LLM judge (or a later NLI replacement) produces these. Offline
    EM/F1 lives on ``AnswerScore`` and is a different mechanism.
    """

    evidence_sufficient: bool
    answer_supported: bool | None
    sufficiency_rationale: str
    support_rationale: str
    judge: str
    model: str

    def as_trace_payload(self) -> dict[str, object]:
        return {
            "evidence_sufficient": self.evidence_sufficient,
            "answer_supported": self.answer_supported,
            "sufficiency_rationale": self.sufficiency_rationale,
            "support_rationale": self.support_rationale,
            "judge": self.judge,
            "model": self.model,
        }


@dataclass(frozen=True)
class Diagnosis:
    """First-pass failure label. ``failure_class`` is None when none is claimed."""

    failure_class: str | None
    rationale: str
    detector: str = "first-pass-runtime"

    def as_trace_payload(self) -> dict[str, object]:
        return {
            "failure_class": self.failure_class,
            "rationale": self.rationale,
            "detector": self.detector,
        }


@dataclass(frozen=True)
class RecoveryDecision:
    """Controller output. Applied recoveries: regenerate, rewrite, abstain, accept.

    ``reason`` is why the action was selected. ``outcome_note`` is what the
    action then did, and is only set once the action has run.
    """

    action: str
    reason: str
    attributed_class: str | None = None
    source: str = "policy"
    outcome_note: str = ""

    def as_trace_payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "reason": self.reason,
            "attributed_class": self.attributed_class,
            "source": self.source,
            "outcome_note": self.outcome_note,
        }


@dataclass(frozen=True)
class Verification:
    """Runtime check of whether recovery helped, using judge flags only (not gold)."""

    outcome: str
    rationale: str

    def as_trace_payload(self) -> dict[str, object]:
        return {"outcome": self.outcome, "rationale": self.rationale}


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
    runtime_evaluation: dict[str, Any] | None = field(default=None)
    diagnosis: dict[str, Any] | None = field(default=None)
    recovery: dict[str, Any] | None = field(default=None)
    verification: dict[str, Any] | None = field(default=None)
    previous_answer: str | None = field(default=None)
    rewritten_query: str | None = field(default=None)
    previous_retrieved_chunks: tuple[dict[str, Any], ...] | None = field(default=None)
    recovery_status: str | None = field(default=None)
    parent_run_id: str | None = field(default=None)
    latency_ms: float | None = field(default=None)
    # The rewrite probe judges the new evidence with no answer in hand. It is a
    # different question from the post-recovery judgement, so it is stored
    # rather than folded into ``runtime_evaluation``.
    probe_evaluation: dict[str, Any] | None = field(default=None)


@dataclass(frozen=True)
class BaselineRunResult:
    run_id: str
    query: str
    answer: str
    retrieval: RetrievalResult
    generation_model: str
    embedding_model: str
    trace_path: Path | None = field(default=None)
    runtime_evaluation: RuntimeEvaluation | None = field(default=None)
    diagnosis: Diagnosis | None = field(default=None)
    recovery: RecoveryDecision | None = field(default=None)
    verification: Verification | None = field(default=None)
    previous_answer: str | None = field(default=None)
    rewritten_query: str | None = field(default=None)
