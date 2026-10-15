"""Engine regressions found in the October 2026 backend audit. No live model calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swrag.config import DEFAULT_MAX_RETRIES, openai_client
from swrag.evaluation.llm_judge import constrain_support_to_evidence
from swrag.experiments.benchmark import build_comparison
from swrag.experiments.runner import run_experiment
from swrag.orchestration.loop import run_with_recovery
from swrag.pipeline.baseline import build_corpus_index
from swrag.recovery.rewrite import ScriptedRewriter
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import GenerationResult, RetrievalResult, RuntimeEvaluation
from swrag.verification.runtime import IMPROVED, STILL_FAILING

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"
GOLD = ROOT / "datasets" / "gold" / "questions.jsonl"
QUESTION = "When is the Harbor Institute Library open on Saturday?"


def _eval(sufficient: bool, supported: bool | None, span: tuple[str, ...] = ()) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="",
        support_rationale="",
        judge="scripted",
        model="scripted",
        span_rejections=span,
    )


class _Judge:
    def __init__(self, *results: RuntimeEvaluation) -> None:
        self._results = list(results)

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        return self._results.pop(0)


class _Answers:
    """Generator and regenerator that hand out answers in order."""

    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)

    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return GenerationResult(answer=self._answers.pop(0), model="scripted")

    def regenerate(self, *, question: str, retrieval: RetrievalResult, previous_answer: str) -> GenerationResult:
        del question, retrieval, previous_answer
        return GenerationResult(answer=self._answers.pop(0), model="scripted")


def _run(tmp_path: Path, judge: _Judge, answers: _Answers, *, budget: int) -> dict:
    result = run_with_recovery(
        QUESTION,
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=answers,  # type: ignore[arg-type]
        regenerator=answers,
        rewriter=ScriptedRewriter(QUESTION),
        judge=judge,
        max_recoveries=budget,
    )
    return json.loads(result.trace_path.read_text(encoding="utf-8"))


def test_a_rewrite_with_a_rejected_fact_is_not_reported_improved(tmp_path: Path) -> None:
    """#134: sufficient evidence alone is not a repair."""
    trace = _run(
        tmp_path,
        _Judge(_eval(False, False), _eval(True, None), _eval(True, False, ("99:99",))),
        _Answers("first", "rewritten answer with 99:99"),
        budget=1,
    )
    assert trace["verification"]["outcome"] == STILL_FAILING
    assert trace["answer"].startswith("I do not know")
    assert [item["action"] for item in trace["recovery_attempts"]][-1] == "abstain"


def test_with_budget_left_the_loop_keeps_repairing_after_an_unsupported_rewrite(tmp_path: Path) -> None:
    """#134: the escalation ADR 007 allows now happens."""
    trace = _run(
        tmp_path,
        _Judge(_eval(False, False), _eval(True, None), _eval(True, False, ("99:99",)), _eval(True, True)),
        _Answers("first", "rewritten answer with 99:99", "grounded answer"),
        budget=2,
    )
    actions = [item["action"] for item in trace["recovery_attempts"]]
    assert actions[0] == "rewrite" and len(actions) == 2
    assert trace["answer"] == "grounded answer"
    assert trace["verification"]["outcome"] == IMPROVED


def test_an_empty_regenerated_answer_becomes_an_abstention_and_still_fails(tmp_path: Path) -> None:
    """#138."""
    trace = _run(tmp_path, _Judge(_eval(True, False), _eval(True, None)), _Answers("unsupported first", ""), budget=1)
    assert trace["answer"].startswith("I do not know")
    assert trace["verification"]["outcome"] == STILL_FAILING


def _retrieval(text: str) -> RetrievalResult:
    index = build_corpus_index(CORPUS, FakeEmbedder())
    result = index.search("library Saturday", top_k=1)
    chunk = result.chunks[0]
    replaced = type(chunk.chunk)(**{**chunk.chunk.__dict__, "text": text})
    return RetrievalResult(
        query=result.query,
        chunks=(type(chunk)(chunk=replaced, score=chunk.score),),
        top_k=1,
        embedding_model=result.embedding_model,
    )


def test_the_span_check_runs_when_the_judge_leaves_support_null() -> None:
    """#136."""
    evaluation = constrain_support_to_evidence(
        _eval(True, None), answer="It opens at 07:15, room 4471.", retrieval=_retrieval("The desk opens in the morning.")
    )
    assert evaluation.answer_supported is False
    assert set(evaluation.span_rejections) == {"07:15", "4471"}


def test_a_hedge_with_a_fabricated_fact_is_checked_but_a_pure_abstention_is_not() -> None:
    """#137."""
    retrieval = _retrieval("The meeting starts at 18:00.")
    hedged = constrain_support_to_evidence(
        _eval(True, True), answer="I do not know for certain, but the meeting ends at 20:00.", retrieval=retrieval
    )
    assert hedged.answer_supported is False and hedged.span_rejections == ("20:00",)
    pure = constrain_support_to_evidence(
        _eval(True, None), answer="I do not know based on the retrieved documents.", retrieval=retrieval
    )
    assert pure.answer_supported is None and pure.span_rejections == ()


class _FlakyJudge:
    """Raises on the first call, like a malformed JSON reply, then behaves."""

    def __init__(self) -> None:
        self.calls = 0

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        self.calls += 1
        if self.calls == 1:
            raise ValueError("grounding judge returned invalid JSON")
        return _eval(True, True)


class _Canned:
    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return GenerationResult(answer="Saturday 10:00-16:00", model="canned")


def test_one_judge_error_is_recorded_and_the_batch_continues(tmp_path: Path) -> None:
    """#140."""
    summary = run_experiment(
        gold_path=GOLD,
        corpus_dir=CORPUS,
        output_root=tmp_path,
        embedder=FakeEmbedder(),
        generate=True,
        generator=_Canned(),  # type: ignore[arg-type]
        judge=_FlakyJudge(),
        mode="loop",
        run_label="flaky",
    )
    assert len(summary.errors) == 1
    assert summary.errors[0]["error_type"] == "ValueError"
    assert len(summary.outcomes) == summary.total
    assert summary.total == len([line for line in GOLD.read_text().splitlines() if line.strip().startswith("{")]) - 1
    assert summary.median_latency_ms is not None


def test_if_every_question_fails_the_run_stops_loudly(tmp_path: Path) -> None:
    class _Broken:
        def judge(self, **_: object) -> RuntimeEvaluation:
            raise ValueError("bad key")

    with pytest.raises(RuntimeError, match="Every question failed"):
        run_experiment(
            gold_path=GOLD,
            corpus_dir=CORPUS,
            output_root=tmp_path,
            embedder=FakeEmbedder(),
            generate=True,
            generator=_Canned(),  # type: ignore[arg-type]
            judge=_Broken(),
            mode="loop",
            run_label="broken",
        )


def test_a_comparison_drops_a_question_that_errored_in_one_condition(tmp_path: Path) -> None:
    """#140: both conditions are scored on the same questions."""
    common = dict(gold_path=GOLD, corpus_dir=CORPUS, output_root=tmp_path, embedder=FakeEmbedder(), generate=True)
    baseline = run_experiment(**common, generator=_Canned(), mode="baseline", run_label="b")  # type: ignore[arg-type]
    loop = run_experiment(**common, generator=_Canned(), judge=_FlakyJudge(), mode="loop", run_label="l")  # type: ignore[arg-type]
    config = {"conditions": [{"id": "b", "mode": "baseline"}, {"id": "l", "mode": "loop"}], "gold_path": str(GOLD), "corpus_dir": str(CORPUS)}
    comparison = build_comparison(config, {"b": baseline, "l": loop})
    dropped = loop.errors[0]["question_id"]
    assert comparison["excluded_question_ids"] == [dropped]
    assert dropped not in {row["question_id"] for row in comparison["paired_outcomes"]}
    assert comparison["conditions"]["b"]["total"] == comparison["conditions"]["l"]["total"] == baseline.total - 1


def test_model_clients_have_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """#133: no call may wait the SDK default of ten minutes."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("SWRAG_OPENAI_TIMEOUT", raising=False)
    client = openai_client(None)
    assert client.timeout == 60.0 and client.max_retries == DEFAULT_MAX_RETRIES
    monkeypatch.setenv("SWRAG_OPENAI_TIMEOUT", "15")
    assert openai_client(None).timeout == 15.0
