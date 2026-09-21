"""Judge-independent retrieval signal and the repair it can trigger (#64)."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.evaluation.retrieval_signal import (
    DEFAULT_MIN_RELATIVE_MARGIN,
    DEFAULT_MIN_TOP_SCORE,
    retrieval_signal,
)
from swrag.orchestration.loop import run_first_pass, run_with_recovery
from swrag.recovery.policy import (
    ACCEPT,
    REGENERATE,
    REWRITE,
    TRIGGER_JUDGE,
    TRIGGER_RETRIEVAL_SIGNAL,
    select_recovery,
)
from swrag.recovery.rewrite import ScriptedRewriter
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.types import Chunk, RetrievalResult, RuntimeEvaluation, ScoredChunk

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "corpus"


def _retrieval(*scores: float) -> RetrievalResult:
    chunks = tuple(
        ScoredChunk(
            chunk=Chunk(
                chunk_id=f"doc-{index}::c000",
                doc_id=f"doc-{index}",
                title=f"Doc {index}",
                text="text",
                start_char=0,
                end_char=4,
            ),
            score=score,
        )
        for index, score in enumerate(scores)
    )
    return RetrievalResult(query="q", chunks=chunks, top_k=len(chunks), embedding_model="fake")


def _eval(*, sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="test",
        support_rationale="test",
        judge="scripted",
        model="none",
    )


def test_healthy_retrieval_is_not_weak() -> None:
    signal = retrieval_signal(_retrieval(0.80, 0.40, 0.20))
    assert signal.is_weak is False
    assert signal.weak_top is False
    assert signal.ambiguous_top is False
    assert signal.reason == "retrieval looks healthy"


def test_low_top_score_is_weak() -> None:
    signal = retrieval_signal(_retrieval(DEFAULT_MIN_TOP_SCORE - 0.01, 0.02))
    assert signal.weak_top is True
    assert signal.is_weak is True
    assert "below" in signal.reason


def test_near_tie_between_top_two_is_ambiguous() -> None:
    """The corpora pair a current notice with a superseded one on purpose."""
    signal = retrieval_signal(_retrieval(0.80, 0.799))
    assert signal.ambiguous_top is True
    assert signal.weak_top is False
    assert signal.relative_margin is not None
    assert signal.relative_margin < DEFAULT_MIN_RELATIVE_MARGIN


def test_empty_retrieval_is_weak() -> None:
    signal = retrieval_signal(_retrieval())
    assert signal.is_weak is True
    assert signal.top_score is None
    assert signal.reason == "no chunks were retrieved"


def test_single_chunk_has_no_margin() -> None:
    signal = retrieval_signal(_retrieval(0.9))
    assert signal.relative_margin is None
    assert signal.ambiguous_top is False


def test_margin_is_relative_so_it_survives_a_scale_change() -> None:
    """Absolute gaps differ by embedder; the ratio should not."""
    big = retrieval_signal(_retrieval(0.90, 0.45))
    small = retrieval_signal(_retrieval(0.09, 0.045))
    assert big.relative_margin == small.relative_margin


def test_weak_retrieval_proposes_repair_even_when_the_judge_accepts() -> None:
    """The core of #64: the judge alone must not be able to end the run."""
    accepted = _eval(sufficient=True, supported=True)
    diagnosis = diagnose_runtime(accepted)
    assert diagnosis.failure_class is None

    without_signal = select_recovery(diagnosis, accepted)
    assert without_signal.action == ACCEPT

    with_signal = select_recovery(diagnosis, accepted, retrieval_signal(_retrieval(0.80, 0.799)))
    assert with_signal.action == REWRITE
    assert with_signal.trigger == TRIGGER_RETRIEVAL_SIGNAL
    assert "judge raised no failure" in with_signal.reason


def test_healthy_retrieval_still_accepts() -> None:
    accepted = _eval(sufficient=True, supported=True)
    decision = select_recovery(
        diagnose_runtime(accepted),
        accepted,
        retrieval_signal(_retrieval(0.80, 0.40)),
    )
    assert decision.action == ACCEPT
    assert decision.trigger == ""


def test_judge_findings_still_take_precedence_over_the_signal() -> None:
    unsupported = _eval(sufficient=True, supported=False)
    decision = select_recovery(
        diagnose_runtime(unsupported),
        unsupported,
        retrieval_signal(_retrieval(0.80, 0.799)),
    )
    assert decision.action == REGENERATE
    assert decision.trigger == TRIGGER_JUDGE


def test_signal_does_not_fire_without_a_judgement_to_disagree_with() -> None:
    """Retrieve-only runs have no judge, so there is no verdict to second-guess."""
    decision = select_recovery(None, None, retrieval_signal(_retrieval(0.01, 0.0099)))
    assert decision.action == ACCEPT


class _ScoreJudge:
    """Always accepts. Stands in for a lenient judge."""

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        return _eval(sufficient=True, supported=True)


class _CannedGenerator:
    def generate(self, query: str, retrieval: RetrievalResult):
        del query, retrieval
        from swrag.types import GenerationResult

        return GenerationResult(answer="The library is on the moon.", model="canned")


def test_trace_records_the_signal_and_the_trigger(tmp_path: Path) -> None:
    result = run_first_pass(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        judge=_ScoreJudge(),
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    signal = payload["retrieval_signal"]
    assert signal is not None
    assert signal["detector"] == "retrieval-score"
    assert "top_score" in signal
    assert "relative_margin" in signal
    assert payload["recovery"]["trigger"] in {"", TRIGGER_JUDGE, TRIGGER_RETRIEVAL_SIGNAL}


def test_retrieve_only_never_needs_a_rewriter(tmp_path: Path) -> None:
    """Regression: a signal-triggered rewrite must not break the no-key harness."""
    from swrag.evaluation.scripted_judge import ScriptedJudge

    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generate=False,
        judge=ScriptedJudge(evidence_sufficient=True, answer_supported=None),
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["rewritten_query"] is None
    assert payload["retrieval_signal"] is not None


def test_signal_triggered_rewrite_runs_end_to_end(tmp_path: Path) -> None:
    """An off-corpus question retrieves nothing similar, so the signal fires.

    The judge here accepts everything. Before #64 that ended the run at
    ``accept``; the rewrite below only happens because the signal overrode it.
    """
    result = run_with_recovery(
        "quantum chromodynamics lattice gauge",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("Harbor Institute Library Saturday opening hours"),
        judge=_ScoreJudge(),
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["trigger"] == TRIGGER_RETRIEVAL_SIGNAL
    assert payload["recovery"]["action"] == REWRITE
    assert payload["rewritten_query"] == "Harbor Institute Library Saturday opening hours"
    assert payload["retrieval_signal"]["weak_top"] is True


def test_on_corpus_question_with_healthy_retrieval_is_left_alone(tmp_path: Path) -> None:
    """Guard against over-triggering: a normal question must still accept."""
    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        judge=_ScoreJudge(),
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["retrieval_signal"]["weak_top"] is False
    assert payload["retrieval_signal"]["ambiguous_top"] is False
    assert payload["recovery"]["action"] == ACCEPT
