"""Batch a gold set through the pipeline and aggregate offline scores.

Each invocation writes to its own timestamped directory so historical results
are never overwritten, as the architecture rules require.

This runner deliberately knows nothing about diagnosis, recovery, or
verification. Those arrive in Phase 1 and plug in behind the same interface, so
the baseline numbers produced now stay comparable to later runs.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from swrag.config import load_provider_config
from swrag.evaluation.gold import load_gold_set
from swrag.evaluation.judge import GroundingJudge
from swrag.evaluation.scoring import score_answer
from swrag.pipeline.baseline import run_query
from swrag.retrieval.embedder import Embedder
from swrag.types import AnswerScore, GoldQuestion


@dataclass(frozen=True)
class QuestionOutcome:
    """One gold question's result, joined with its offline score."""

    question_id: str
    question: str
    answerable: bool
    answer: str
    score: AnswerScore
    retrieved_doc_ids: tuple[str, ...]
    supporting_doc_ids: tuple[str, ...]
    run_id: str
    trace_path: str | None

    @property
    def retrieval_hit(self) -> bool:
        """Whether any expected supporting document was retrieved.

        Undefined for unanswerable questions, which have no supporting
        documents; reported as ``False`` and excluded from the aggregate.
        """
        if not self.supporting_doc_ids:
            return False
        return bool(set(self.retrieved_doc_ids) & set(self.supporting_doc_ids))


@dataclass(frozen=True)
class ExperimentSummary:
    """Aggregate over a batch, split by answerability.

    Results are not collapsed into a single headline number. Per ADR 002 and
    the LayerRAG-Bench principle, an intervention must be credited for the
    class it targets rather than for lifting an average.
    """

    run_label: str
    timestamp: str
    gold_path: str
    corpus_dir: str
    output_dir: str
    top_k: int
    provider: dict[str, object]
    total: int
    answerable_total: int
    unanswerable_total: int
    exact_match: float
    contains_answer: float
    f1: float
    answerable_exact_match: float
    answerable_contains_answer: float
    answerable_f1: float
    unanswerable_abstention_rate: float
    answerable_abstention_rate: float
    retrieval_hit_rate: float
    outcomes: tuple[QuestionOutcome, ...] = field(default_factory=tuple)


def run_experiment(
    *,
    gold_path: str | Path,
    corpus_dir: str | Path,
    output_root: str | Path,
    top_k: int = 4,
    embedder: Embedder | None = None,
    generate: bool = True,
    answer_fn: Callable[[GoldQuestion], tuple[str, str, tuple[str, ...], str | None]] | None = None,
    run_label: str | None = None,
    judge: GroundingJudge | None = None,
) -> ExperimentSummary:
    """Score every gold question and write results to a fresh directory.

    ``answer_fn`` exists so tests can supply canned answers without an API key.
    When omitted, the baseline pipeline runs for real. ``judge`` is attached to
    each pipeline trace; it is never given gold labels. Canned ``answer_fn``
    paths skip the judge because they do not produce a retrieval object.
    """
    questions = load_gold_set(gold_path)
    label = run_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_dir = Path(output_root) / label
    if run_dir.exists():
        raise FileExistsError(f"Experiment directory already exists (refusing to overwrite): {run_dir}")
    traces_dir = run_dir / "traces"
    traces_dir.mkdir(parents=True)

    outcomes: list[QuestionOutcome] = []
    for question in questions:
        if answer_fn is not None:
            answer, run_id, retrieved_doc_ids, trace_path = answer_fn(question)
        else:
            result = run_query(
                question.question,
                corpus_dir=corpus_dir,
                output_dir=traces_dir,
                top_k=top_k,
                embedder=embedder,
                generate=generate,
                question_id=question.question_id,
                judge=judge,
            )
            answer = result.answer
            run_id = result.run_id
            retrieved_doc_ids = tuple(
                scored.chunk.doc_id for scored in result.retrieval.chunks
            )
            trace_path = str(result.trace_path) if result.trace_path else None

        outcomes.append(
            QuestionOutcome(
                question_id=question.question_id,
                question=question.question,
                answerable=question.answerable,
                answer=answer,
                score=score_answer(answer, question),
                retrieved_doc_ids=retrieved_doc_ids,
                supporting_doc_ids=question.supporting_doc_ids,
                run_id=run_id,
                trace_path=trace_path,
            )
        )

    summary = _summarize(
        outcomes,
        run_label=label,
        gold_path=str(gold_path),
        corpus_dir=str(corpus_dir),
        output_dir=str(run_dir),
        top_k=top_k,
    )
    (run_dir / "summary.json").write_text(
        json.dumps(asdict(summary), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def _summarize(
    outcomes: list[QuestionOutcome],
    *,
    run_label: str,
    gold_path: str,
    corpus_dir: str,
    output_dir: str,
    top_k: int,
) -> ExperimentSummary:
    answerable = [item for item in outcomes if item.answerable]
    unanswerable = [item for item in outcomes if not item.answerable]
    with_support = [item for item in outcomes if item.supporting_doc_ids]

    return ExperimentSummary(
        run_label=run_label,
        timestamp=datetime.now(timezone.utc).isoformat(),
        gold_path=gold_path,
        corpus_dir=corpus_dir,
        output_dir=output_dir,
        top_k=top_k,
        provider=load_provider_config().as_trace_payload(),
        total=len(outcomes),
        answerable_total=len(answerable),
        unanswerable_total=len(unanswerable),
        exact_match=_mean([item.score.exact_match for item in outcomes]),
        contains_answer=_mean([item.score.contains_answer for item in outcomes]),
        f1=_mean([item.score.f1 for item in outcomes]),
        answerable_exact_match=_mean([item.score.exact_match for item in answerable]),
        answerable_contains_answer=_mean([item.score.contains_answer for item in answerable]),
        answerable_f1=_mean([item.score.f1 for item in answerable]),
        unanswerable_abstention_rate=_mean([item.score.abstained for item in unanswerable]),
        answerable_abstention_rate=_mean([item.score.abstained for item in answerable]),
        retrieval_hit_rate=_mean([item.retrieval_hit for item in with_support]),
        outcomes=tuple(outcomes),
    )


def _mean(values: list[bool] | list[float]) -> float:
    """Mean of a possibly-empty sequence; empty means 0.0, not an error."""
    if not values:
        return 0.0
    return sum(float(value) for value in values) / len(values)
