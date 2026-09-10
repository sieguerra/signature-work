"""Recovery controller and verification tests. No live API calls."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.diagnosis.diagnose import (
    EVIDENCE_INSUFFICIENCY,
    RETRIEVAL_MISS,
    diagnose_after_rewrite,
    diagnose_runtime,
)
from swrag.recovery.policy import ABSTAIN, ACCEPT, REGENERATE, REWRITE, select_recovery
from swrag.recovery.rewrite import ScriptedRewriter
from swrag.orchestration.loop import ABSTAIN_ANSWER, run_with_recovery
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import GenerationResult, RetrievalResult, RuntimeEvaluation
from swrag.verification.runtime import DEGRADED, IMPROVED, STILL_FAILING, UNCHANGED, verify_runtime

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "corpus"


def _eval(*, sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="test",
        support_rationale="test",
        judge="scripted",
        model="none",
    )


def test_selects_regenerate_for_unsupported_generation() -> None:
    diagnosis = diagnose_runtime(_eval(sufficient=True, supported=False))
    decision = select_recovery(diagnosis, _eval(sufficient=True, supported=False))
    assert decision.action == REGENERATE


def test_selects_rewrite_when_evidence_is_insufficient() -> None:
    diagnosis = diagnose_runtime(_eval(sufficient=False, supported=False))
    decision = select_recovery(diagnosis, _eval(sufficient=False, supported=False))
    assert decision.action == REWRITE


def test_selects_abstain_after_evidence_insufficiency_is_attributed() -> None:
    diagnosis = diagnose_after_rewrite(
        _eval(sufficient=False, supported=False),
        _eval(sufficient=False, supported=None),
    )
    assert diagnosis.failure_class == EVIDENCE_INSUFFICIENCY
    decision = select_recovery(diagnosis, _eval(sufficient=False, supported=None))
    assert decision.action == ABSTAIN


def test_selects_accept_when_there_is_no_failure() -> None:
    diagnosis = diagnose_runtime(_eval(sufficient=True, supported=True))
    decision = select_recovery(diagnosis, _eval(sufficient=True, supported=True))
    assert decision.action == ACCEPT


def test_verify_improved_degraded_and_still_failing() -> None:
    unsupported = _eval(sufficient=True, supported=False)
    supported = _eval(sufficient=True, supported=True)
    assert verify_runtime(unsupported, supported).outcome == IMPROVED
    assert verify_runtime(supported, unsupported).outcome == DEGRADED
    assert verify_runtime(unsupported, unsupported).outcome == STILL_FAILING
    assert verify_runtime(supported, supported).outcome == UNCHANGED
    assert (
        verify_runtime(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=True),
        ).outcome
        == IMPROVED
    )


class _SequenceJudge:
    def __init__(self, *results: RuntimeEvaluation) -> None:
        self._results = list(results)

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        return self._results.pop(0)


class _CannedGenerator:
    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return GenerationResult(answer="The library is on the moon.", model="canned")


class _CannedRegenerator:
    def regenerate(
        self,
        *,
        question: str,
        retrieval: RetrievalResult,
        previous_answer: str,
    ) -> GenerationResult:
        del question, retrieval
        assert "moon" in previous_answer
        return GenerationResult(answer="Saturday 10:00-16:00", model="canned-repair")


def test_loop_regenerates_and_records_improved_verification(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        regenerator=_CannedRegenerator(),
        judge=_SequenceJudge(
            _eval(sufficient=True, supported=False),
            _eval(sufficient=True, supported=True),
        ),
    )
    assert result.answer == "Saturday 10:00-16:00"
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == REGENERATE
    assert payload["previous_answer"] == "The library is on the moon."
    assert payload["verification"]["outcome"] == IMPROVED
    assert payload["runtime_evaluation"]["answer_supported"] is True
    assert "answers" not in payload
    assert payload["diagnosis"]["failure_class"] is None


def test_loop_rewrites_and_attributes_retrieval_miss(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("Harbor Institute Library Saturday hours term time"),
        judge=_SequenceJudge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=None),
            _eval(sufficient=True, supported=True),
        ),
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == REWRITE
    assert payload["recovery"]["attributed_class"] == RETRIEVAL_MISS
    assert payload["rewritten_query"] == "Harbor Institute Library Saturday hours term time"
    assert payload["verification"]["outcome"] == IMPROVED
    assert payload["previous_answer"] == "The library is on the moon."
    assert result.answer == "The library is on the moon."


def test_loop_rewrites_then_abstains_on_corpus_gap(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("Harbor Institute Library Saturday hours"),
        judge=_SequenceJudge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=False, supported=None),
        ),
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == REWRITE
    assert payload["recovery"]["attributed_class"] == EVIDENCE_INSUFFICIENCY
    assert payload["diagnosis"]["failure_class"] == EVIDENCE_INSUFFICIENCY
    assert payload["verification"]["outcome"] == STILL_FAILING
    assert result.answer == ABSTAIN_ANSWER


def test_loop_accepts_without_calling_regenerator(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        regenerator=_CannedRegenerator(),
        judge=_SequenceJudge(_eval(sufficient=True, supported=True)),
    )
    assert result.answer == "The library is on the moon."
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == ACCEPT
    assert payload["verification"] is None
    assert payload["previous_answer"] is None
