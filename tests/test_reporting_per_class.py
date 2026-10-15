"""Rank-rule verdict agreement (#132) and the offline gold-class table (#146). No live calls."""

from __future__ import annotations

from swrag.experiments.benchmark import by_gold_class, gold_class, rank_rule_agreement
from swrag.experiments.runner import QuestionOutcome
from swrag.types import AnswerScore


def _score(answerable: bool, contains: bool, abstained: bool, f1: float = 0.0) -> AnswerScore:
    return AnswerScore(exact_match=False, contains_answer=contains, f1=f1, abstained=abstained, answerable=answerable)


def _outcome(qid: str, answerable: bool, score: AnswerScore, *, retrieved=("d1",), supporting=("d1",), **extra) -> QuestionOutcome:
    return QuestionOutcome(
        question_id=qid,
        question="q",
        answerable=answerable,
        answer="a",
        score=score,
        retrieved_doc_ids=tuple(retrieved),
        supporting_doc_ids=tuple(supporting) if answerable else (),
        run_id=qid,
        trace_path=None,
        **extra,
    )


def test_a_paraphrase_inside_the_correct_rank_agrees_under_the_rank_rule() -> None:
    # dku-008 shape: correct before and after, F1 drops a hair; the runtime said unchanged.
    item = _outcome(
        "dku-008",
        True,
        _score(True, True, False, f1=0.70),
        previous_score=_score(True, True, False, f1=0.71),
        verification_outcome="unchanged",
    )
    report = rank_rule_agreement([item])
    assert report["agrees"] == 1 and report["disagrees"] == 0
    assert report["by_answerability"]["answerable"] == {"n": 1, "agrees": 1, "disagrees": 0}
    assert report["runtime_vs_gold_transition"] == {"unchanged": {"unchanged": 1}}


def test_rank_rule_splits_by_answerability_and_skips_first_pass_only_rows() -> None:
    improved = _outcome(
        "a1", True, _score(True, True, False), previous_score=_score(True, False, False), verification_outcome="improved"
    )
    wrong_call = _outcome(
        "u1", False, _score(False, False, False), previous_score=_score(False, False, True), verification_outcome="improved"
    )
    untouched = _outcome("a2", True, _score(True, True, False))
    report = rank_rule_agreement([improved, wrong_call, untouched])
    assert report["n"] == 2
    assert report["by_answerability"]["answerable"] == {"n": 1, "agrees": 1, "disagrees": 0}
    assert report["by_answerability"]["unanswerable"] == {"n": 1, "agrees": 0, "disagrees": 1}
    assert report["runtime_vs_gold_transition"]["improved"] == {"improved": 1, "degraded": 1}


def test_gold_class_follows_adr_005() -> None:
    assert gold_class(_outcome("u", False, _score(False, False, True))) == "evidence_insufficiency"
    assert gold_class(_outcome("ok", True, _score(True, True, False))) == "no_failure"
    assert gold_class(_outcome("miss", True, _score(True, False, False), retrieved=("other",))) == "retrieval_miss"
    assert gold_class(_outcome("gen", True, _score(True, False, False))) == "unsupported_generation"
    assert gold_class(_outcome("abs", True, _score(True, False, True))) == "unsupported_generation"
    assert gold_class(_outcome("abs-miss", True, _score(True, False, True), retrieved=())) == "retrieval_miss"


def test_by_gold_class_reports_baseline_and_loop_per_class_with_runtime_attribution() -> None:
    baseline = [
        _outcome("m1", True, _score(True, False, False), retrieved=("x",)),
        _outcome("m2", True, _score(True, False, False), retrieved=("x",)),
        _outcome("u1", False, _score(False, False, False)),
        _outcome("ok", True, _score(True, True, False)),
    ]
    loop = [
        _outcome("m1", True, _score(True, True, False), recovery_action="expand", attributed_class="retrieval_miss"),
        _outcome("m2", True, _score(True, False, False), recovery_action="rewrite", attributed_class="unsupported_generation"),
        _outcome("u1", False, _score(False, False, True), recovery_action="abstain", attributed_class="evidence_insufficiency"),
        _outcome("ok", True, _score(True, True, False), recovery_action="accept"),
    ]
    report = by_gold_class(baseline, loop)
    miss = report["retrieval_miss"]
    assert (miss["n"], miss["answerable_n"], miss["unanswerable_n"]) == (2, 2, 0)
    assert miss["baseline_contains_answer"] == 0.0 and miss["loop_contains_answer"] == 0.5
    assert miss["baseline_unanswerable_abstention"] is None
    assert miss["runtime_attribution"] == {"retrieval_miss": 1, "unsupported_generation": 1}
    gap = report["evidence_insufficiency"]
    assert gap["baseline_unanswerable_abstention"] == 0.0 and gap["loop_unanswerable_abstention"] == 1.0
    assert report["no_failure"]["runtime_attribution"] == {"no_recovery": 1}
