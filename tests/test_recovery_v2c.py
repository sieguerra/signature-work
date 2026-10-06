"""Gap-aware recovery policies. The product default stays v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.orchestration.loop import run_with_recovery
from swrag.recovery.gap_signal import (
    CONFLICT,
    LIKELY_CORPUS_GAP,
    LIKELY_QUERY_MISMATCH,
    NEIGHBOR_FACT,
    UNCERTAIN,
    assess_evidence,
    blocking_assessment,
)
from swrag.recovery.policy import (
    ABSTAIN,
    DEFAULT_POLICY,
    EXPAND,
    POLICY_V1,
    POLICY_V2C_EXPAND_STOP,
    POLICY_V2C_GAP_AWARE,
    REWRITE,
    normalize_policy,
    select_next_recovery,
    select_recovery,
)
from swrag.recovery.rewrite import ScriptedRewriter
from swrag.recovery_benchmark.v2c import (
    assert_runtime_kwargs,
    assign_panels,
    score_case,
    summarize,
)
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import GenerationResult, RecoveryDecision, RetrievalResult, RuntimeEvaluation, ScoredChunk, Chunk

ROOT = Path(__file__).resolve().parents[1]
GAP = ROOT / "experiments/recovery-benchmark/gap-aware"
POLICY_SOURCE = (ROOT / "src/swrag/recovery/policy.py").read_text(encoding="utf-8")
LOOP_SOURCE = (ROOT / "src/swrag/orchestration/loop.py").read_text(encoding="utf-8")
SIGNAL_SOURCE = (ROOT / "src/swrag/recovery/gap_signal.py").read_text(encoding="utf-8")


def _eval(*, sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="test",
        support_rationale="test",
        judge="scripted",
        model="none",
    )


def _next(policy: str, texts: tuple[str, ...], question: str) -> RecoveryDecision:
    last = RecoveryDecision(action=EXPAND, reason="expanded", trigger="judge")
    decision = select_next_recovery(
        last=last,
        verification=None,
        evaluation=_eval(sufficient=False, supported=None),
        used=("expand",),
        current_top_k=12,
        policy=policy,
        question=question,
        evidence_texts=texts,
    )
    assert decision is not None
    return decision


def test_default_policy_is_unchanged_and_v2c_opens_with_expand() -> None:
    assert DEFAULT_POLICY == POLICY_V1
    assert normalize_policy(POLICY_V2C_EXPAND_STOP) == POLICY_V2C_EXPAND_STOP
    insufficient = _eval(sufficient=False, supported=None)
    assert select_recovery(diagnose_runtime(insufficient), insufficient, policy=POLICY_V2C_EXPAND_STOP).action == EXPAND
    assert select_recovery(diagnose_runtime(insufficient), insufficient, policy=POLICY_V2C_GAP_AWARE).action == EXPAND
    assert select_recovery(diagnose_runtime(insufficient), insufficient, policy=POLICY_V1).action == REWRITE


def test_expand_then_stop_never_rewrites() -> None:
    texts = tuple(
        f"The fish stall bond mentions the hire only to say it is not printed here. Aisle {i}."
        for i in range(4)
    )
    decision = _next(POLICY_V2C_EXPAND_STOP, texts, "What is the Wick Market linen stall hire?")
    assert decision.action == ABSTAIN
    assert decision.parameters["safe_answer"].lower().startswith("i do not know")
    assert "stop_reason" in decision.parameters


def test_gap_aware_rewrites_only_a_denial_cluster_and_stops_on_omission() -> None:
    denial = tuple(
        "This fish stall bond poster mentions the linen stall hire only to say it is not printed here."
        for _ in range(4)
    )
    rewrite = _next(POLICY_V2C_GAP_AWARE, denial, "What is the Wick Market linen stall hire per Saturday?")
    assert rewrite.action == REWRITE
    assert rewrite.parameters["recovery_opportunity"] == LIKELY_QUERY_MISMATCH
    omission = ("Holiday hours are announced separately and are not listed here.",)
    stop = _next(POLICY_V2C_GAP_AWARE, omission, "What are the library holiday closing hours?")
    assert stop.action == ABSTAIN
    assert stop.parameters["recovery_opportunity"] == LIKELY_CORPUS_GAP
    assert "not listed" in stop.parameters["safe_answer"]


def test_conflict_and_neighbor_are_separate_and_block_a_substantive_answer() -> None:
    phones = (
        "DKU Library phone (+86) 0512-36658756.",
        "DKU Library handbook phone (0512) 3665-7027.",
    )
    conflict = assess_evidence("What phone number is listed for the DKU Library?", phones)
    assert conflict.label == CONFLICT
    address = assess_evidence(
        "What is the street address of the DKU Library?",
        ("The street address is No. 8 Duke Avenue.", "Phone (+86) 0512-36658756 and (0512) 3665-7027."),
    )
    assert address.label != CONFLICT
    neighbor = assess_evidence(
        "What mooring fee does Wick Market charge at its own quay?",
        ("East Wharf mooring fee is 15 reed tokens. East Wharf is not Wick Market.",),
    )
    assert neighbor.label == NEIGHBOR_FACT
    brine = assess_evidence(
        "What is the design capacity of Northhaven's Brine Wellfield in gallons per day?",
        ("Plover Plant design capacity is 8 million gallons per day.",),
    )
    assert brine.label == NEIGHBOR_FACT
    blocked = blocking_assessment(
        "How much does a Tide Canteen meal cost in harbor credits?",
        "A standard meal costs 3 harbor credits.",
        ("A standard meal at the East Canteen costs 3 harbor credits.",),
    )
    assert blocked is not None
    assert blocked.label == NEIGHBOR_FACT
    assert (
        blocking_assessment(
            "What is the street address of the DKU Library?",
            "The street address of the DKU Library is No. 8 Duke Avenue.",
            (
                "DKU Library contact: No. 8 Duke Avenue. Phone 555-0100.",
                "Duke University in Durham is not the DKU Library. The switchboard is 555-0199.",
            ),
        )
        is None
    )
    assert blocking_assessment(
        "What phone number is listed for the DKU Library?",
        "The phone number is (0512) 3665-7027.",
        phones,
    ) is not None
    assert blocking_assessment("What is the fee?", "I do not know based on the retrieved documents.", phones) is None


def test_uncertain_evidence_does_not_rewrite() -> None:
    decision = _next(POLICY_V2C_GAP_AWARE, ("The desk opens at 09:00.",), "Who keeps the key?")
    assert decision.action == ABSTAIN
    assert decision.parameters["recovery_opportunity"] == UNCERTAIN
    assert decision.parameters["uncertain_fallback"] == "safe_stop"


def test_runtime_sources_do_not_read_offline_labels() -> None:
    for source in (POLICY_SOURCE, LOOP_SOURCE, SIGNAL_SOURCE):
        assert "corpus_answerability" not in source
        assert "supporting_rank" not in source
        assert "human_before" not in source
        assert "stratum" not in source
    assert_runtime_kwargs({"query": "What is the fee?", "corpus_dir": "datasets/dku/corpus"})
    with pytest.raises(ValueError):
        assert_runtime_kwargs({"stratum": "corpus_gap", "query": "fee"})


def test_split_covers_every_stratum_and_matches_the_frozen_file() -> None:
    rows = [json.loads(line) for line in (GAP / "questions.jsonl").read_text().splitlines() if line.strip()]
    bare = [{key: value for key, value in row.items() if key != "panel"} for row in rows]
    again = assign_panels(bare)
    assert [(row["question_id"], row["panel"]) for row in again] == [
        (row["question_id"], row["panel"]) for row in rows
    ]
    split = json.loads((GAP / "split.json").read_text())
    assert split["status"] in {"sealed_until_candidate_selection", "opened_once"}
    assert split["phase8a_holdout"] == "phase8a_holdout_consumed"
    panels = {row["stratum"]: set() for row in rows}
    for row in rows:
        panels[row["stratum"]].add(row["panel"])
    assert all(group == {"development", "holdout"} for group in panels.values())
    criteria = json.loads((GAP / "promotion_criteria.json").read_text())
    assert criteria["written_before_holdout"] is True
    assert criteria["uncertain_fallback"] == "safe_stop"
    assert isinstance(criteria["holdout_opened"], bool)


def test_metrics_keep_answer_recovery_and_safe_failure_apart() -> None:
    scored = [
        score_case(
            {"question_id": "a", "stratum": "expand_recoverable", "panel": "development", "required_substrings": ["CH-2"]},
            "The card is CH-2.",
            actions=["expand"],
        ),
        score_case(
            {"question_id": "b", "stratum": "rewrite_recoverable", "panel": "development", "required_substrings": ["5 reed tokens"]},
            "I do not know based on the retrieved documents.",
            actions=["expand", "rewrite", "abstain"],
        ),
        score_case(
            {"question_id": "c", "stratum": "corpus_gap", "panel": "development"},
            "I do not know based on the retrieved documents.",
            actions=["expand", "abstain"],
        ),
        score_case(
            {"question_id": "d", "stratum": "neighbor_fact", "panel": "development", "forbidden_substrings": ["8 million"]},
            "The capacity is 8 million gallons.",
            actions=["expand"],
        ),
    ]
    report = summarize(scored)
    assert report["answer_recovery"]["n"] == 2
    assert report["answer_recovery"]["successes"] == 1
    assert report["safe_failure"]["successes"] == 1
    assert report["rewrite_calls"] == 1
    assert report["rewrite_direct_successes"] == 0
    assert report["by_stratum"]["neighbor_fact"]["successes"] == 0


def test_expand_stop_loop_abstains_instead_of_rewriting(tmp_path: Path) -> None:
    insufficient = _eval(sufficient=False, supported=None)

    class _Sequence:
        def __init__(self) -> None:
            self.calls = 0

        def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
            del question, answer, retrieval
            self.calls += 1
            return insufficient

    class _Canned:
        def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
            del query, retrieval
            return GenerationResult(answer="A made up fee.", model="canned")

    result = run_with_recovery(
        "What fee does the pamphlet list?",
        corpus_dir=ROOT / "datasets/kestrel-aero/corpus",
        output_dir=tmp_path,
        top_k=4,
        max_recoveries=2,
        embedder=FakeEmbedder(),
        generator=_Canned(),  # type: ignore[arg-type]
        judge=_Sequence(),
        rewriter=ScriptedRewriter("should not be used"),
        recovery_policy=POLICY_V2C_EXPAND_STOP,
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    actions = [row["action"] for row in payload["recovery_attempts"]]
    assert actions[0] == EXPAND
    assert REWRITE not in actions
    assert ABSTAIN in actions
    assert payload["answer"].lower().startswith("i do not know")
    assert "stratum" not in payload


def test_legacy_attempt_without_gap_fields_still_scores() -> None:
    case = {"question_id": "old", "stratum": "corpus_gap", "panel": "development"}
    scored = score_case(case, "I do not know based on the retrieved documents.", actions=["rewrite", "expand"])
    assert scored["success"] is True
