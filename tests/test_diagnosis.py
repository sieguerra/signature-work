"""First-pass diagnosis tests. No API calls."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.diagnosis.diagnose import (
    EVIDENCE_INSUFFICIENCY,
    RETRIEVAL_MISS,
    UNSUPPORTED_GENERATION,
    V1_FAILURE_CLASSES,
    diagnose_after_rewrite,
    diagnose_runtime,
)
from swrag.evaluation.scripted_judge import ScriptedJudge
from swrag.pipeline.baseline import run_query
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import GenerationResult, RetrievalResult, RuntimeEvaluation

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "corpus"


def _evaluation(*, sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="test",
        support_rationale="test",
        judge="scripted",
        model="none",
    )


def test_unsupported_generation_when_sufficient_but_not_supported() -> None:
    diagnosis = diagnose_runtime(_evaluation(sufficient=True, supported=False))
    assert diagnosis.failure_class == UNSUPPORTED_GENERATION
    assert diagnosis.failure_class in V1_FAILURE_CLASSES


def test_no_class_when_sufficient_and_supported() -> None:
    diagnosis = diagnose_runtime(_evaluation(sufficient=True, supported=True))
    assert diagnosis.failure_class is None


def test_no_class_when_evidence_is_insufficient() -> None:
    """retrieval_miss vs corpus-gap is not a first-pass diagnosis."""
    diagnosis = diagnose_runtime(_evaluation(sufficient=False, supported=False))
    assert diagnosis.failure_class is None
    assert "first pass" in diagnosis.rationale


def test_no_class_when_there_is_no_answer() -> None:
    diagnosis = diagnose_runtime(_evaluation(sufficient=True, supported=None))
    assert diagnosis.failure_class is None


def test_rewrite_outcome_attributes_miss_vs_insufficiency() -> None:
    before = _evaluation(sufficient=False, supported=False)
    miss = diagnose_after_rewrite(before, _evaluation(sufficient=True, supported=True))
    assert miss.failure_class == RETRIEVAL_MISS
    gap = diagnose_after_rewrite(before, _evaluation(sufficient=False, supported=None))
    assert gap.failure_class == EVIDENCE_INSUFFICIENCY


def test_first_pass_never_emits_deferred_classes() -> None:
    cases = (
        _evaluation(sufficient=True, supported=True),
        _evaluation(sufficient=True, supported=False),
        _evaluation(sufficient=False, supported=True),
        _evaluation(sufficient=False, supported=False),
        _evaluation(sufficient=True, supported=None),
    )
    emitted = {diagnose_runtime(item).failure_class for item in cases} - {None}
    assert emitted <= {UNSUPPORTED_GENERATION}
    assert "retrieval_miss" not in emitted
    assert "evidence_insufficiency" not in emitted
    assert "citation_failure" not in V1_FAILURE_CLASSES


class _CannedGenerator:
    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return GenerationResult(answer="The library is on the moon.", model="canned")


def test_pipeline_labels_unsupported_generation_with_a_generated_answer(tmp_path: Path) -> None:
    result = run_query(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generate=True,
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        judge=ScriptedJudge(evidence_sufficient=True, answer_supported=False),
    )
    assert result.diagnosis is not None
    assert result.diagnosis.failure_class == UNSUPPORTED_GENERATION
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["diagnosis"]["failure_class"] == UNSUPPORTED_GENERATION
