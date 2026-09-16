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
from swrag.evaluation.llm_judge import LLMJudge
from swrag.recovery.policy import ABSTAIN, ACCEPT, REGENERATE, REWRITE, select_recovery
from swrag.recovery.regenerate import _REGENERATE_PROMPT
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


def test_regenerate_prompt_requires_a_new_grounded_answer() -> None:
    assert "NEW answer" in _REGENERATE_PROMPT
    assert "Do not copy" in _REGENERATE_PROMPT
    assert "only part of the question" in _REGENERATE_PROMPT


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
        assert previous_answer
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


class _SequenceJudgeClient:
    """Fixture OpenAI client: each create() returns the next JSON payload."""

    def __init__(self, payloads: list[dict]) -> None:
        self.chat = self._Chat(payloads)

    class _Chat:
        def __init__(self, payloads: list[dict]) -> None:
            self.completions = self._Completions(payloads)

        class _Completions:
            def __init__(self, payloads: list[dict]) -> None:
                self._payloads = list(payloads)
                self.calls: list[dict] = []

            def create(self, **kwargs: object) -> object:
                self.calls.append(kwargs)
                if not self._payloads:
                    raise AssertionError("LLMJudge made more calls than fixture replies")
                return _JudgeResponse(json.dumps(self._payloads.pop(0)))


class _JudgeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("Choice", (), {"message": type("Msg", (), {"content": content})()})]


class _UnsupportedThenRepaired:
    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return GenerationResult(
            answer="Saturday 10:00-16:00 and the library has 800 seats.",
            model="canned",
        )


def test_loop_regenerates_when_lenient_judge_is_overridden_by_span_check(
    tmp_path: Path,
) -> None:
    """Issue #32: a fact not in the evidence must select regenerate.

    The fixture LLM says answer_supported=true both times. The span check
    rejects the first answer (800 is not in Harbor hours) and keeps the
    repaired answer (10:00-16:00 is in the retrieved library note).
    """
    lenient = {
        "evidence_sufficient": True,
        "answer_supported": True,
        "sufficiency_rationale": "hours are in the evidence",
        "support_rationale": "the answer looks like library hours",
    }
    client = _SequenceJudgeClient([lenient, lenient])
    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_UnsupportedThenRepaired(),  # type: ignore[arg-type]
        regenerator=_CannedRegenerator(),
        judge=LLMJudge(model="gpt-4o-mini", client=client),
    )
    assert result.answer == "Saturday 10:00-16:00"
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == REGENERATE
    assert payload["previous_answer"] == (
        "Saturday 10:00-16:00 and the library has 800 seats."
    )
    assert payload["verification"]["outcome"] == IMPROVED
    assert payload["runtime_evaluation"]["answer_supported"] is True
    assert "800" in payload["previous_answer"]


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
