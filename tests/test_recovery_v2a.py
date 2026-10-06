"""Recovery Engine v2A policies. The product default stays v1."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.evaluation.retrieval_signal import RetrievalSignal, retrieval_signal
from swrag.orchestration.loop import run_with_recovery
from swrag.recovery.policy import (
    ABSTAIN,
    ACCEPT,
    DEFAULT_POLICY,
    EXPAND,
    POLICY_V1,
    POLICY_V2A_COMBINED,
    POLICY_V2A_EXPAND_FIRST,
    POLICY_V2A_MARGIN,
    REGENERATE,
    REWRITE,
    margin_only_trigger,
    normalize_policy,
    select_next_recovery,
    select_recovery,
)
from swrag.recovery.rewrite import ScriptedRewriter
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import (
    Chunk,
    GenerationResult,
    RecoveryDecision,
    RetrievalResult,
    RuntimeEvaluation,
    ScoredChunk,
)
from swrag.recovery_benchmark.v2a import replay_action, retrospective_report
from swrag.verification.runtime import STILL_FAILING, Verification

ROOT = Path(__file__).resolve().parents[1]
POLICY_SOURCE = (ROOT / "src" / "swrag" / "recovery" / "policy.py").read_text(encoding="utf-8")
LOOP_SOURCE = (ROOT / "src" / "swrag" / "orchestration" / "loop.py").read_text(encoding="utf-8")
KESTREL = ROOT / "datasets" / "kestrel-aero" / "corpus"


def _eval(*, sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="test",
        support_rationale="test",
        judge="scripted",
        model="none",
    )


def _signal(*, weak: bool = False, ambiguous: bool = False) -> RetrievalSignal:
    return RetrievalSignal(
        top_score=0.4,
        runner_up_score=0.39,
        relative_margin=0.01 if ambiguous else 0.2,
        weak_top=weak,
        ambiguous_top=ambiguous,
        reason="test",
    )


def _retrieval(*scores: float) -> RetrievalResult:
    chunks = []
    for index, score in enumerate(scores):
        chunks.append(
            ScoredChunk(
                chunk=Chunk(
                    chunk_id=f"c{index}",
                    doc_id=f"d{index}",
                    title=f"t{index}",
                    text="passage",
                    start_char=0,
                    end_char=7,
                ),
                score=score,
            )
        )
    return RetrievalResult(query="q", chunks=tuple(chunks), top_k=len(scores), embedding_model="fake")


def test_default_policy_is_v1_and_unknown_names_fail() -> None:
    assert DEFAULT_POLICY == POLICY_V1
    assert normalize_policy(None) == POLICY_V1
    assert normalize_policy("") == POLICY_V1
    assert inspect.signature(run_with_recovery).parameters["recovery_policy"].default == POLICY_V1
    with pytest.raises(ValueError):
        normalize_policy("planner")
    assert "GoldQuestion" not in POLICY_SOURCE
    assert "answerable" not in POLICY_SOURCE
    assert "human_label" not in POLICY_SOURCE
    assert "human_label" not in LOOP_SOURCE


def test_margin_policy_accepts_only_the_margin_only_case() -> None:
    accepted = _eval(sufficient=True, supported=True)
    diagnosis = diagnose_runtime(accepted)
    ambiguous = _signal(ambiguous=True)
    assert margin_only_trigger(accepted, ambiguous) is True
    assert select_recovery(diagnosis, accepted, ambiguous).action == EXPAND
    decision = select_recovery(diagnosis, accepted, ambiguous, policy=POLICY_V2A_MARGIN)
    assert decision.action == ACCEPT
    assert decision.parameters["ambiguous_top_observed"] is True
    assert decision.parameters["intervened_on_margin"] is False
    assert ambiguous.ambiguous_top is True


def test_margin_policy_still_recovers_other_failures() -> None:
    accepted = _eval(sufficient=True, supported=True)
    ambiguous = _signal(ambiguous=True)
    weak = _signal(weak=True, ambiguous=True)
    assert select_recovery(diagnose_runtime(accepted), accepted, weak, policy=POLICY_V2A_MARGIN).action == EXPAND
    insufficient = _eval(sufficient=False, supported=None)
    assert (
        select_recovery(diagnose_runtime(insufficient), insufficient, ambiguous, policy=POLICY_V2A_MARGIN).action
        == REWRITE
    )
    unsupported = _eval(sufficient=True, supported=False)
    assert (
        select_recovery(diagnose_runtime(unsupported), unsupported, ambiguous, policy=POLICY_V2A_MARGIN).action
        == REGENERATE
    )
    missing_support = _eval(sufficient=True, supported=None)
    assert (
        select_recovery(diagnose_runtime(missing_support), missing_support, ambiguous, policy=POLICY_V2A_MARGIN).action
        == EXPAND
    )


def test_expand_first_orders_expand_then_rewrite_at_the_expanded_k() -> None:
    insufficient = _eval(sufficient=False, supported=None)
    decision = select_recovery(
        diagnose_runtime(insufficient),
        insufficient,
        _signal(),
        policy=POLICY_V2A_EXPAND_FIRST,
    )
    assert decision.action == EXPAND
    assert decision.parameters["search_query"] == "original"
    nxt = select_next_recovery(
        last=decision,
        verification=Verification(outcome=STILL_FAILING, rationale="still thin"),
        evaluation=insufficient,
        used=(EXPAND,),
        current_top_k=12,
        policy=POLICY_V2A_EXPAND_FIRST,
    )
    assert nxt is not None
    assert nxt.action == REWRITE
    assert nxt.parameters["rewrite_top_k"] == "expanded"
    assert nxt.parameters["top_k"] == 12
    stopped = select_next_recovery(
        last=decision,
        verification=Verification(outcome=STILL_FAILING, rationale="still thin"),
        evaluation=insufficient,
        used=(EXPAND,),
        current_top_k=12,
        policy=POLICY_V1,
    )
    assert stopped is not None
    assert stopped.action == ABSTAIN


def test_expand_first_budget_still_caps_applied_actions(tmp_path: Path) -> None:
    thin = _eval(sufficient=False, supported=None)
    result = run_with_recovery(
        "Which bay houses the traveler office?",
        corpus_dir=KESTREL,
        output_dir=tmp_path,
        top_k=4,
        max_recoveries=2,
        embedder=FakeEmbedder(),
        generator=_Canned(),  # type: ignore[arg-type]
        judge=_Sequence(thin, thin, thin),
        rewriter=ScriptedRewriter("traveler office bay"),
        recovery_policy=POLICY_V2A_EXPAND_FIRST,
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    actions = [row["action"] for row in payload["recovery_attempts"]]
    assert actions[0] == EXPAND
    assert actions[1] == REWRITE
    assert sum(1 for action in actions if action != ABSTAIN) == 2
    assert actions[0] != REWRITE
    rewrite = payload["recovery_attempts"][1]
    assert rewrite["parameters"]["rewrite_top_k"] == "expanded"
    assert rewrite["top_k"] == 12
    assert payload["initial"]["retrieval_signal"] is not None


def test_combined_policy_suppresses_margin_and_expands_first() -> None:
    accepted = _eval(sufficient=True, supported=True)
    assert (
        select_recovery(
            diagnose_runtime(accepted),
            accepted,
            _signal(ambiguous=True),
            policy=POLICY_V2A_COMBINED,
        ).action
        == ACCEPT
    )
    insufficient = _eval(sufficient=False, supported=None)
    assert (
        select_recovery(
            diagnose_runtime(insufficient),
            insufficient,
            _signal(ambiguous=True),
            policy=POLICY_V2A_COMBINED,
        ).action
        == EXPAND
    )


def test_margin_accept_keeps_the_ambiguous_signal(tmp_path: Path) -> None:
    signal = retrieval_signal(_retrieval(0.80, 0.799))
    assert signal.ambiguous_top is True
    assert signal.weak_top is False
    state_signal = signal
    accepted = _eval(sufficient=True, supported=True)
    from swrag.pipeline.baseline import QueryState

    state = QueryState(
        query="What phone number is listed?",
        retrieval=_retrieval(0.80, 0.799),
        generation=GenerationResult(answer="(0512) 3665-7027", model="canned"),
        runtime_evaluation=accepted,
        diagnosis=diagnose_runtime(accepted),
        retrieval_signal=state_signal,
    )
    result = run_with_recovery(
        state.query,
        corpus_dir=KESTREL,
        output_dir=tmp_path,
        top_k=4,
        embedder=FakeEmbedder(),
        generator=_Canned(),  # type: ignore[arg-type]
        judge=_Sequence(accepted),
        recovery_policy=POLICY_V2A_MARGIN,
        prepared_state=state,
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == ACCEPT
    assert payload["recovery"]["parameters"]["intervened_on_margin"] is False
    assert payload["retrieval_signal"]["ambiguous_top"] is True
    assert not payload.get("recovery_attempts")


def test_retrospective_metrics_exclude_unclear_and_the_holdout() -> None:
    rows = [
        {
            "question_id": "bad",
            "panel": "analysis",
            "before_state": "incorrect",
            "transition": "improved",
            "historical_action": "rewrite",
            "evidence_sufficient": False,
            "answer_supported": None,
            "weak_top": False,
            "ambiguous_top": False,
        },
        {
            "question_id": "margin",
            "panel": "analysis",
            "before_state": "correct",
            "transition": "degraded",
            "historical_action": "expand",
            "evidence_sufficient": True,
            "answer_supported": True,
            "weak_top": False,
            "ambiguous_top": True,
        },
        {
            "question_id": "unsure",
            "panel": "analysis",
            "before_state": "unclear",
            "transition": "unchanged",
            "historical_action": "expand",
            "evidence_sufficient": True,
            "answer_supported": True,
            "weak_top": False,
            "ambiguous_top": True,
        },
    ]
    assert replay_action(rows[1], POLICY_V2A_MARGIN) == ACCEPT
    report = retrospective_report(rows, (POLICY_V1, POLICY_V2A_MARGIN))
    assert report[POLICY_V1]["triggered"] == 2
    assert report[POLICY_V1]["gate_precision"] == 0.5
    assert report[POLICY_V2A_MARGIN]["triggered"] == 1
    assert report[POLICY_V2A_MARGIN]["needed_missed"] == []
    assert report[POLICY_V2A_MARGIN]["unnecessary_recovery"] == 0
    assert report[POLICY_V2A_MARGIN]["n_unclear_excluded"] == 1
    with pytest.raises(ValueError):
        retrospective_report([{**rows[0], "panel": "future_holdout"}], (POLICY_V1,))


class _Sequence:
    def __init__(self, *results: RuntimeEvaluation) -> None:
        self._results = list(results)

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        if not self._results:
            raise AssertionError("judge was called more times than scripted")
        return self._results.pop(0)


class _Canned:
    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return GenerationResult(answer="Hangar 2, bay C.", model="canned")
