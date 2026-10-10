"""Verification v2: gold labels, schema resolution, leakage, and metrics.

Model candidates are exercised with a scripted client. No network.
"""

from __future__ import annotations

import json
from pathlib import Path

from swrag.types import GoldQuestion
from swrag.verification.runtime import verify_runtime
from swrag.types import RuntimeEvaluation
from swrag.verification.v2.adversarial import adversarial_examples
from swrag.verification.v2.benchmark import blind_review_row, recommend, score_examples
from swrag.verification.v2.cache import cache_key, read_cache, write_cache
from swrag.verification.v2.candidates import (
    Completion,
    CoverageVerifier,
    PairwiseVerifier,
    PointwiseVerifier,
    SurfaceVerifier,
)
from swrag.verification.v2.examples import examples_from_trace, stored_v1
from swrag.verification.v2.gold_transition import label_answers, quality_rank, transition_label
from swrag.verification.v2.historical import load_archive
from swrag.verification.v2.metrics import (
    confusion_matrix,
    false_improvement_rate,
    improved_precision,
    mcnemar_exact,
    summarize_predictions,
)
from swrag.verification.v2.payload import GoldLeakageError, verifier_view
from swrag.verification.v2.protocol import DEV_GOLD, TEST_GOLD
from swrag.verification.v2.transitions import abstention_origin, transitions_from_trace
from swrag.evaluation.scoring import score_answer

ROOT = Path(__file__).resolve().parents[1]
ABSTAIN = "I do not know based on the retrieved documents."

EXPECTED_ADVERSARIAL = {
    "longer_worse": "degraded",
    "shorter_better": "improved",
    "fluent_hallucination": "degraded",
    "copies_question": "still_failing",
    "distractor_context": "improved",
    "partial_support": "improved",
    "unsupported_number": "degraded",
    "correct_abstention": "improved",
    "unnecessary_abstention": "degraded",
    "generated_versus_controller_abstention": "unchanged",
    "nearly_identical": "unchanged",
    "both_wrong": "still_failing",
    "subtle_degradation": "degraded",
    "evidence_up_answer_down": "still_failing",
    "answer_up_score_down": "improved",
    "answerable_wrong_to_abstain": "improved",
    "kept_previous_answer": "still_failing",
}


def _gold(answerable: bool, answers: tuple[str, ...] = ()) -> GoldQuestion:
    return GoldQuestion("q", "Where is it?", answerable, answers)


def _eval(sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="",
        support_rationale="",
        judge="scripted",
        model="none",
    )


def _chunk(text: str) -> dict:
    return {"chunk_id": "c", "doc_id": "d", "title": "Notice", "text": text, "score": 0.2}


def _attempt(**overrides) -> dict:
    row = {
        "index": 0,
        "action": "rewrite",
        "executed": True,
        "answer": "Northport",
        "answer_relation": "generated",
        "evidence_relation": "replaced",
        "evaluation_source": "judge",
        "answer_model": "scripted",
        "retrieved_chunks": [_chunk("The archive is in Northport.")],
        "verification": {"outcome": "improved", "rationale": "step"},
    }
    row.update(overrides)
    return row


def _trace(attempts: list[dict], **overrides) -> dict:
    payload = {
        "trace_schema_version": 2,
        "query": "Where is the archive?",
        "question_id": "ex-1",
        "answer": attempts[-1]["answer"] if attempts else "",
        "model": "scripted",
        "retrieved_chunks": [_chunk("The archive is in Northport.")],
        "verification": {"outcome": "improved", "rationale": "run"},
        "initial": {
            "answer": ABSTAIN,
            "model": "scripted",
            "retrieved_chunks": [_chunk("No address is stored.")],
            "diagnosis": {"failure_class": "retrieval_miss"},
        },
        "recovery_attempts": attempts,
    }
    payload.update(overrides)
    return payload


class _Scripted:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, *, system: str, user: str) -> Completion:
        self.calls += 1
        self.prompts.append(user)
        text = self.responses.pop(0)
        return Completion(text=text, prompt_tokens=11, completion_tokens=5, latency_ms=3.0)


def _pointwise_json(**overrides) -> str:
    payload = {
        "evidence_can_answer": True,
        "claims_supported": "supported",
        "addresses_question": True,
        "abstention": False,
        "unsupported_specifics": False,
        "rationale_codes": ["supported"],
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_gold_ranks_abstention_and_ignores_f1_wiggle():
    answerable = _gold(True, ("Northport",))
    unanswerable = _gold(False)
    wrong = score_answer("Eastport", answerable)
    also_wrong = score_answer("Southport", answerable)
    correct = score_answer("Northport", answerable)
    abstained = score_answer(ABSTAIN, answerable)
    safe = score_answer(ABSTAIN, unanswerable)
    invented = score_answer("Ada Quill", unanswerable)

    assert quality_rank(correct) == 2
    assert quality_rank(safe) == 2
    assert quality_rank(abstained) == 1
    assert quality_rank(wrong) == 0
    assert transition_label(wrong, also_wrong) == "still_failing"
    assert transition_label(correct, score_answer("The city is Northport.", answerable)) == "unchanged"
    assert transition_label(wrong, correct) == "improved"
    assert transition_label(correct, wrong) == "degraded"
    assert transition_label(correct, abstained) == "degraded"
    assert transition_label(invented, safe) == "improved"
    assert transition_label(wrong, abstained) == "improved"
    assert label_answers("Eastport", "Southport", answerable) == "still_failing"


def test_adversarial_cases_match_the_frozen_rule():
    found = {item.transition.question_id: item.gold_label for item in adversarial_examples()}
    assert found == EXPECTED_ADVERSARIAL


def test_dev_and_test_gold_files_are_disjoint():
    from swrag.evaluation.gold import load_gold_set

    dev = {item.question_id for path in DEV_GOLD for item in load_gold_set(ROOT / path)}
    test = {item.question_id for path in TEST_GOLD for item in load_gold_set(ROOT / path)}
    assert dev
    assert test
    assert dev.isdisjoint(test)
    assert all("kestrel-aero" in path for path in DEV_GOLD)
    assert all("/dku/" in f"/{path}" for path in TEST_GOLD)


def test_gold_fields_never_enter_the_verifier_view():
    transition = adversarial_examples()[0].transition
    view = verifier_view(transition)
    encoded = json.dumps(view)
    assert "answer_supported" not in encoded
    assert "evidence_sufficient" not in encoded
    for key in ("answerable", "answers", "gold_label", "v1_outcome", "supporting_doc_ids"):
        assert key not in encoded
    leaked = _trace([_attempt()])
    leaked["initial"]["retrieved_chunks"][0]["answers"] = ["secret"]
    try:
        verifier_view(transitions_from_trace(leaked)[0])
    except GoldLeakageError:
        return
    raise AssertionError("gold key was accepted")


def test_schema_resolution_attempt_run_and_skipped_execution():
    payload = _trace(
        [
            _attempt(index=0, action="rewrite", answer="Middle", executed=True),
            _attempt(index=1, action="expand", answer="Northport", executed=False),
            _attempt(
                index=2,
                action="regenerate",
                answer="Northport",
                executed=True,
                answer_relation="generated",
            ),
        ]
    )
    found = transitions_from_trace(payload)
    levels = [(item.level, item.attempt_index, item.action) for item in found]
    assert (1, "expand") not in [(item.attempt_index, item.action) for item in found]
    assert ("attempt", 0, "rewrite") in levels
    assert ("attempt", 2, "regenerate") in levels
    assert ("run", None, "multi") in levels
    run = [item for item in found if item.level == "run"][0]
    assert run.before.answer == ABSTAIN
    assert run.after.answer == "Northport"
    second = [item for item in found if item.attempt_index == 2][0]
    assert second.before.answer == "Middle"


def test_generated_abstention_is_not_a_controller_abstain():
    generated = transitions_from_trace(
        _trace([_attempt(answer=ABSTAIN, answer_relation="generated", evaluation_source="judge")])
    )[0]
    controller = transitions_from_trace(
        _trace([_attempt(answer=ABSTAIN, answer_relation="abstained", evaluation_source="probe")])
    )[0]
    assert abstention_origin(generated.after.answer, generated.after.answer_relation) == "generated"
    assert abstention_origin(controller.after.answer, controller.after.answer_relation) == "controller"
    assert verifier_view(generated)["abstention_origin_after"] == "generated"
    assert verifier_view(controller)["abstention_origin_after"] == "controller"
    assert verifier_view(controller)["after"]["evaluation_source"] == "probe"


def test_probe_and_carried_are_visible_and_not_answer_flags():
    probe = _trace([_attempt(evaluation_source="probe", answer_relation="abstained", answer=ABSTAIN)])
    carried = _trace([_attempt(evaluation_source="carried", answer_relation="kept_previous", answer="kept")])
    for payload in (probe, carried):
        view = verifier_view(transitions_from_trace(payload)[0])
        assert view["after"]["evaluation_source"] in {"probe", "carried"}
        assert "answer_supported" not in json.dumps(view)


def test_unexecuted_and_future_schema_produce_no_transition():
    none_executed = _trace([_attempt(executed=False)])
    assert transitions_from_trace(none_executed) == ()
    future = _trace([_attempt()])
    future["trace_schema_version"] = 999
    assert transitions_from_trace(future) == ()


def test_legacy_run_without_evidence_is_unknown():
    legacy = {
        "query": "Where?",
        "previous_answer": "Eastport",
        "answer": "Northport",
        "verification": {"outcome": "improved"},
        "recovery_action": "expand",
    }
    found = transitions_from_trace(legacy)
    assert len(found) == 1
    assert found[0].level == "run"
    assert found[0].before.evidence_known is False


def test_stored_v1_is_not_recomputed():
    payload = _trace([_attempt()])
    payload["verification"] = {"outcome": "unchanged", "rationale": "stored on purpose"}
    payload["initial"]["runtime_evaluation"] = {"evidence_sufficient": False, "answer_supported": False}
    payload["runtime_evaluation"] = {"evidence_sufficient": True, "answer_supported": True}
    transition = [item for item in transitions_from_trace(payload) if item.level == "run"][0]
    assert stored_v1(payload, transition) == "unchanged"
    assert verify_runtime(_eval(False, False), _eval(True, True)).outcome == "improved"


def test_coverage_and_surface_do_not_claim_improvement_from_text_alone():
    surface = SurfaceVerifier().predict(adversarial_examples()[1].transition)
    assert surface.status == "uncertain"
    assert surface.outcome is None
    archive = load_archive(ROOT)
    assert archive
    assert all(item.panel == "archive" and item.split == "archive" for item in archive)
    unavailable = CoverageVerifier().predict(archive[0].transition)
    assert unavailable.status == "unavailable"
    assert unavailable.outcome is None
    assert unavailable.error == "evidence_unavailable"


def test_coverage_rank_rules():
    improved = next(item for item in adversarial_examples() if item.transition.question_id == "shorter_better")
    prediction = CoverageVerifier().predict(improved.transition)
    assert prediction.status == "decided"
    assert prediction.outcome == "improved"
    kept = next(item for item in adversarial_examples() if item.transition.question_id == "kept_previous_answer")
    kept_prediction = CoverageVerifier().predict(kept.transition)
    assert kept_prediction.outcome != "improved"


def test_pairwise_position_disagreement_is_uncertain():
    client = _Scripted([json.dumps({"relation": "second_better"}), json.dumps({"relation": "second_better"})])
    prediction = PairwiseVerifier(client, model="scripted").predict(adversarial_examples()[0].transition)
    assert prediction.status == "uncertain"
    assert prediction.outcome is None
    assert prediction.position_consistent is False
    assert client.calls == 2


def test_pairwise_agreement_survives_a_swap():
    class _PreferShort:
        def complete(self, *, system: str, user: str) -> Completion:
            response_one = user.split("Response 2:")[0]
            relation = "first_better" if "\nNorthport\n" in response_one else "second_better"
            return Completion(json.dumps({"relation": relation}), 4, 2, 1.0)

    prediction = PairwiseVerifier(_PreferShort(), model="scripted").predict(adversarial_examples()[0].transition)
    assert prediction.status == "decided"
    assert prediction.position_consistent is True
    assert prediction.outcome == "degraded"


def test_parser_failures_stay_unavailable():
    transition = adversarial_examples()[0].transition
    cases = {
        "": "empty",
        "I can't judge this": "refusal",
        "not json": "invalid_json",
        json.dumps({"relation": "maybe"}): "unknown_label",
    }
    for text, code in cases.items():
        prediction = PairwiseVerifier(_Scripted([text, text]), model="scripted").predict(transition)
        assert prediction.status == "unavailable"
        assert prediction.outcome is None
        assert prediction.error == code

    class _Boom:
        def complete(self, *, system: str, user: str) -> Completion:
            raise RuntimeError("429 rate limit")

    class _Timeout:
        def complete(self, *, system: str, user: str) -> Completion:
            raise TimeoutError("timed out")

    rated = PairwiseVerifier(_Boom(), model="scripted").predict(transition)
    assert rated.error == "rate_limit" and rated.outcome is None
    timed = PairwiseVerifier(_Timeout(), model="scripted").predict(transition)
    assert timed.error == "timeout" and timed.outcome is None


def test_rationale_text_does_not_decide_the_label():
    transition = adversarial_examples()[1].transition
    first = _Scripted([
        _pointwise_json(rationale_codes=["alpha"]),
        _pointwise_json(rationale_codes=["beta"]),
    ])
    second = _Scripted([
        _pointwise_json(rationale_codes=["other words entirely"]),
        _pointwise_json(rationale_codes=["still not a verdict"]),
    ])
    left = PointwiseVerifier(first, model="scripted").predict(transition)
    right = PointwiseVerifier(second, model="scripted").predict(transition)
    assert left.outcome == right.outcome == "unchanged"
    assert left.diagnostic != right.diagnostic


def test_cache_key_changes_with_prompt_version(tmp_path: Path):
    transition = adversarial_examples()[1].transition
    client = _Scripted([_pointwise_json(), _pointwise_json(), _pointwise_json(), _pointwise_json()])
    verifier = PointwiseVerifier(client, model="scripted", cache_dir=tmp_path)
    PointwiseVerifier(client, model="scripted", cache_dir=tmp_path).predict(transition)
    assert client.calls == 2
    verifier.predict(transition)
    assert client.calls == 2
    verifier.prompt_version = "pointwise-changed"
    verifier.predict(transition)
    assert client.calls == 4
    view = verifier_view(transition)
    first = cache_key(
        candidate="pointwise",
        prompt_version="pointwise-2026-10-06",
        parser_version="1",
        model="scripted",
        temperature=0.0,
        view=view,
        order="before",
    )
    second = cache_key(
        candidate="pointwise",
        prompt_version="pointwise-changed",
        parser_version="1",
        model="scripted",
        temperature=0.0,
        view=view,
        order="before",
    )
    assert first != second
    write_cache(tmp_path, "abc", {"text": "stale", "prompt_version": "old"})
    assert read_cache(tmp_path, "abc")["text"] == "stale"


def test_metrics_false_improvement_and_confusion():
    matrix = confusion_matrix(
        ["improved", "still_failing", "degraded", "unchanged"],
        ["improved", "improved", "improved", "unchanged"],
    )
    assert false_improvement_rate(matrix) == 2 / 3
    assert improved_precision(matrix) == 1 / 3
    assert matrix["degraded"]["improved"] == 1
    assert matrix["still_failing"]["improved"] == 1
    empty = confusion_matrix(["unchanged"], ["unchanged"])
    assert false_improvement_rate(empty) is None
    rows = [
        {"gold_label": "improved", "v1_outcome": "improved", "v2_status": "decided", "v2_outcome": "still_failing"},
        {"gold_label": "degraded", "v1_outcome": "degraded", "v2_status": "uncertain", "v2_outcome": None},
    ]
    summary = summarize_predictions(rows)
    assert summary["n_decided"] == 1
    assert summary["coverage"] == 0.5
    assert mcnemar_exact(0, 0) is None
    assert mcnemar_exact(6, 0)["p_value"] < 0.05


def test_blind_review_hides_verdicts():
    example = adversarial_examples()[0]
    row = blind_review_row(example)
    assert set(row) == {"question", "before_evidence", "before_answer", "after_evidence", "after_answer"}
    assert "improved" not in json.dumps(row)
    assert example.gold_label not in json.dumps(row)


def test_promotion_rule_is_conservative():
    v1 = {
        "false_improvement_rate": 0.5,
        "improved_precision": 0.4,
        "macro_f1": 0.4,
        "n_decided": 20,
    }
    v2 = {
        "false_improvement_rate": 0.2,
        "improved_precision": 0.7,
        "macro_f1": 0.5,
        "n_decided": 20,
        "coverage": 0.9,
    }
    bootstrap = {"delta_v2_minus_v1": {"improved_precision": {"low": 0.05, "high": 0.4}}}
    kwargs = dict(
        position_inconsistency=0.0,
        model_calls=2,
        leakage_ok=True,
        runtime_unchanged=True,
        answerable_n=5,
        unanswerable_n=4,
    )
    assert recommend(v1, v2, bootstrap, **kwargs) == "REPLACE V1"
    guarded = {"delta_v2_minus_v1": {"improved_precision": {"low": -0.02, "high": 0.4}}}
    assert recommend(v1, v2, guarded, **kwargs) == "GUARDED READY"
    small = dict(v2, n_decided=4)
    assert recommend(v1, small, bootstrap, **kwargs) == "RESEARCH ONLY"
    worse = dict(v2, false_improvement_rate=0.9)
    assert recommend(v1, worse, bootstrap, **kwargs) == "REJECT"
    assert recommend(v1, v2, bootstrap, **dict(kwargs, leakage_ok=False)) == "REJECT"


def test_runtime_modules_do_not_import_shadow_verifiers():
    for relative in (
        "src/swrag/orchestration/loop.py",
        "src/swrag/recovery/policy.py",
        "src/swrag/verification/runtime.py",
        "src/swrag/api/app.py",
        "src/swrag/verification/v2/candidates.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        if relative.endswith("candidates.py"):
            assert "gold_transition" not in text
            assert "score_answer" not in text
            assert "load_gold" not in text
        else:
            assert "verification.v2" not in text
            assert "verification/v2" not in text


def test_scoring_passes_only_the_transition():
    seen = []

    class _Spy:
        def predict(self, transition):
            seen.append(transition)
            encoded = json.dumps(verifier_view(transition))
            assert "gold_label" not in encoded
            return SurfaceVerifier().predict(transition)

    rows = score_examples(_Spy(), adversarial_examples()[:1])
    assert len(seen) == 1
    assert rows[0]["gold_label"] == "degraded"
    assert rows[0]["v2_status"] == "uncertain"
