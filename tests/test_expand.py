"""Expand recovery, multi-attempt budget, and first-pass-fail gold (#67–#69)."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.evaluation.gold import load_gold_set
from swrag.experiments.benchmark import load_benchmark_config
from swrag.orchestration.loop import run_with_recovery
from swrag.pipeline.baseline import execute_query
from swrag.recovery.expand import next_top_k
from swrag.recovery.policy import (
    ABSTAIN,
    EXPAND,
    REGENERATE,
    REWRITE,
    select_next_recovery,
    select_recovery,
)
from swrag.recovery.rewrite import ScriptedRewriter
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.tracing.steps import trace_to_steps
from swrag.types import GenerationResult, RecoveryDecision, RetrievalResult, RuntimeEvaluation
from swrag.verification.runtime import IMPROVED, STILL_FAILING, Verification

ROOT = Path(__file__).resolve().parents[1]
KESTREL = ROOT / "datasets" / "kestrel-aero" / "corpus"
KESTREL_GOLD = ROOT / "datasets" / "kestrel-aero" / "gold" / "first-pass-fail.jsonl"
DKU = ROOT / "datasets" / "dku" / "corpus"
DKU_GOLD = ROOT / "datasets" / "dku" / "gold" / "first-pass-fail.jsonl"
KESTREL_CONFIG = ROOT / "experiments" / "configs" / "v3_kestrel_expand_vs_loop.json"
DKU_CONFIG = ROOT / "experiments" / "configs" / "v3_dku_expand_vs_loop.json"


def _eval(*, sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="test",
        support_rationale="test",
        judge="scripted",
        model="none",
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
        return GenerationResult(answer="Hangar 2, bay C.", model="canned")


def test_next_top_k_widens_then_stops_at_the_cap() -> None:
    assert next_top_k(1) == 8
    assert next_top_k(4) == 12
    assert next_top_k(8) == 20
    assert next_top_k(20) is None


def test_select_next_recovery_escalates_rewrite_to_expand() -> None:
    last = RecoveryDecision(action=REWRITE, reason="thin", trigger="judge")
    nxt = select_next_recovery(
        last=last,
        verification=Verification(outcome=STILL_FAILING, rationale="still thin"),
        evaluation=_eval(sufficient=False, supported=None),
        used=(REWRITE,),
        current_top_k=1,
    )
    assert nxt is not None
    assert nxt.action == EXPAND
    assert "widen top_k from 1 to 8" in nxt.reason


def test_select_next_recovery_stops_after_improve() -> None:
    last = RecoveryDecision(action=REWRITE, reason="thin", trigger="judge")
    nxt = select_next_recovery(
        last=last,
        verification=Verification(outcome=IMPROVED, rationale="enough"),
        evaluation=_eval(sufficient=True, supported=True),
        used=(REWRITE,),
        current_top_k=1,
    )
    assert nxt is None


def test_select_next_recovery_stops_when_the_current_answer_is_already_good() -> None:
    last = RecoveryDecision(action=EXPAND, reason="widen", trigger="retrieval_signal")
    nxt = select_next_recovery(
        last=last,
        verification=Verification(outcome="unchanged", rationale="flags unchanged"),
        evaluation=_eval(sufficient=True, supported=True),
        used=(EXPAND,),
        current_top_k=12,
    )
    assert nxt is None
    last = RecoveryDecision(action=EXPAND, reason="widen", trigger="judge")
    nxt = select_next_recovery(
        last=last,
        verification=Verification(outcome=STILL_FAILING, rationale="unsupported"),
        evaluation=_eval(sufficient=True, supported=False),
        used=(EXPAND,),
        current_top_k=8,
    )
    assert nxt is not None
    assert nxt.action == REGENERATE


def test_select_next_recovery_does_not_repeat_expand() -> None:
    last = RecoveryDecision(action=EXPAND, reason="widen", trigger="judge")
    nxt = select_next_recovery(
        last=last,
        verification=Verification(outcome=STILL_FAILING, rationale="still thin"),
        evaluation=_eval(sufficient=False, supported=None),
        used=(REWRITE, EXPAND),
        current_top_k=8,
    )
    assert nxt is not None
    assert nxt.action == ABSTAIN


def test_budget_one_does_not_expand_after_a_failed_rewrite(tmp_path: Path) -> None:
    result = run_with_recovery(
        "Which bay houses the traveler office?",
        corpus_dir=KESTREL,
        output_dir=tmp_path,
        top_k=1,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("Which bay houses the traveler office?"),
        judge=_SequenceJudge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=False, supported=None),
        ),
        max_recoveries=1,
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == REWRITE
    attempts = payload["recovery_attempts"]
    assert attempts is not None
    assert [item["action"] for item in attempts] == [REWRITE]
    docs = {chunk["doc_id"] for chunk in payload["retrieved_chunks"]}
    assert "about" not in docs


def test_rewrite_then_expand_brings_in_the_missing_chunk(tmp_path: Path) -> None:
    result = run_with_recovery(
        "Which bay houses the traveler office?",
        corpus_dir=KESTREL,
        output_dir=tmp_path,
        top_k=1,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("Which bay houses the traveler office?"),
        judge=_SequenceJudge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=False, supported=None),
            _eval(sufficient=True, supported=True),
        ),
        max_recoveries=2,
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == EXPAND
    assert [item["action"] for item in payload["recovery_attempts"]] == [REWRITE, EXPAND]
    rewrite_class = payload["recovery_attempts"][0]["attributed_class"]
    assert rewrite_class is not None
    assert payload["recovery_attempts"][1]["attributed_class"] == rewrite_class
    assert payload["recovery"]["attributed_class"] == rewrite_class
    assert payload["verification"]["outcome"] == IMPROVED
    assert payload["first_pass_evaluation"]["evidence_sufficient"] is False
    assert payload["runtime_evaluation"]["evidence_sufficient"] is True
    docs = {chunk["doc_id"] for chunk in payload["retrieved_chunks"]}
    assert "about" in docs
    assert payload["top_k"] == 8
    assert payload["recovery"]["parameters"]["from_k"] == 1
    assert payload["recovery"]["parameters"]["to_k"] == 8
    recover = next(step for step in trace_to_steps(payload) if step["id"] == "recover")
    assert recover["summary"] == "rewrite → expand"


def test_successful_rewrite_does_not_spend_the_second_slot(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=ROOT / "datasets" / "corpus",
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_CannedGenerator(),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("Harbor Institute Library Saturday hours term time"),
        judge=_SequenceJudge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=None),
            _eval(sufficient=True, supported=True),
        ),
        max_recoveries=2,
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery"]["action"] == REWRITE
    assert [item["action"] for item in payload["recovery_attempts"]] == [REWRITE]
    assert payload["verification"]["outcome"] == IMPROVED


def test_expand_is_selectable_on_the_first_pass_from_a_weak_signal() -> None:
    accepted = _eval(sufficient=True, supported=True)
    from swrag.evaluation.retrieval_signal import retrieval_signal
    from swrag.types import Chunk, ScoredChunk

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
        for index, score in enumerate((0.80, 0.799))
    )
    retrieval = RetrievalResult(query="q", chunks=chunks, top_k=2, embedding_model="fake")
    decision = select_recovery(diagnose_runtime(accepted), accepted, retrieval_signal(retrieval))
    assert decision.action == EXPAND


def _rank(corpus: Path, question: str, top_k: int, index) -> set[str]:
    state = execute_query(
        question,
        corpus_dir=corpus,
        top_k=top_k,
        embedder=FakeEmbedder(),
        generate=False,
        index=index,
    )
    return {scored.chunk.doc_id for scored in state.retrieval.chunks}


def test_first_pass_fail_gold_misses_at_k_one_and_hits_at_k_eight() -> None:
    """The #69 set is only useful if expand can actually change the evidence."""
    from swrag.pipeline.baseline import build_corpus_index

    for gold_path, corpus in ((KESTREL_GOLD, KESTREL), (DKU_GOLD, DKU)):
        index = build_corpus_index(corpus, FakeEmbedder())
        questions = load_gold_set(gold_path)
        answerable = [item for item in questions if item.answerable]
        assert answerable
        for question in answerable:
            support = set(question.supporting_doc_ids)
            first = _rank(corpus, question.question, 1, index)
            widened = _rank(corpus, question.question, 8, index)
            assert not (first & support), (question.question_id, first)
            assert widened & support, (question.question_id, widened)


def test_expand_benchmark_configs_use_a_real_budget() -> None:
    for path, name, gold, corpus in (
        (KESTREL_CONFIG, "v3_kestrel_expand_vs_loop", KESTREL_GOLD, KESTREL),
        (DKU_CONFIG, "v3_dku_expand_vs_loop", DKU_GOLD, DKU),
    ):
        payload = load_benchmark_config(path, repo_root=ROOT)
        assert payload["name"] == name
        assert Path(payload["gold_path"]) == gold
        assert Path(payload["corpus_dir"]) == corpus
        assert payload["top_k"] == 1
        assert int(payload.get("max_recoveries", 1)) == 2
