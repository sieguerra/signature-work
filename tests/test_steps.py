"""Waterfall step mapping tests. No API."""

from __future__ import annotations

from swrag.tracing.steps import trace_to_steps


def _base(**overrides):
    payload = {
        "run_id": "run_1",
        "timestamp": "2026-09-10T00:00:00+00:00",
        "query": "When does the library close?",
        "retrieved_chunks": [
            {
                "chunk_id": "harbor-library::c000",
                "doc_id": "harbor-library",
                "title": "Harbor Library",
                "score": 0.9,
                "text": "Saturday: 10:00–16:00",
            }
        ],
        "answer": "Saturday 10:00–16:00",
        "model": "gpt-4o-mini",
        "embedding_model": "fake-hash",
        "top_k": 4,
    }
    payload.update(overrides)
    return payload


def test_baseline_trace_has_query_retrieve_generate() -> None:
    kinds = [step["id"] for step in trace_to_steps(_base())]
    assert kinds == ["query", "retrieve", "generate"]


def test_retrieve_only_marks_generate_skipped() -> None:
    steps = {step["id"]: step for step in trace_to_steps(_base(answer="", model="none"))}
    assert steps["generate"]["status"] == "skipped"


def test_first_pass_diagnosis_without_a_class_still_appears() -> None:
    steps = trace_to_steps(
        _base(
            runtime_evaluation={
                "evidence_sufficient": False,
                "answer_supported": False,
                "sufficiency_rationale": "thin",
                "support_rationale": "",
                "judge": "scripted",
                "model": "none",
            },
            diagnosis={
                "failure_class": None,
                "rationale": "not split on first pass",
                "detector": "first-pass-runtime",
            },
        )
    )
    diagnose = next(step for step in steps if step["id"] == "diagnose")
    assert diagnose["summary"] == "deferred until rewrite"


def test_supported_first_pass_diagnose_says_no_failure() -> None:
    steps = trace_to_steps(
        _base(
            runtime_evaluation={
                "evidence_sufficient": True,
                "answer_supported": True,
                "sufficiency_rationale": "hours in chunk",
                "support_rationale": "hours cited",
                "judge": "scripted",
                "model": "none",
            },
            diagnosis={
                "failure_class": None,
                "rationale": "Evidence was sufficient and the answer was supported.",
                "detector": "first-pass-runtime",
            },
            recovery={"action": "accept", "reason": "ok", "source": "policy"},
            recovery_status="applied",
        )
    )
    diagnose = next(step for step in steps if step["id"] == "diagnose")
    assert diagnose["summary"] == "no failure"


def test_loop_trace_adds_evaluate_diagnose_recover_verify() -> None:
    steps = trace_to_steps(
        _base(
            runtime_evaluation={
                "evidence_sufficient": False,
                "answer_supported": False,
                "sufficiency_rationale": "wrong docs",
                "support_rationale": "unsupported",
                "judge": "scripted",
                "model": "none",
            },
            diagnosis={
                "failure_class": "evidence_insufficiency",
                "rationale": "still thin",
                "detector": "rewrite-outcome",
            },
            recovery={
                "action": "rewrite",
                "reason": "first-pass evidence insufficient",
                "attributed_class": "evidence_insufficiency",
            },
            verification={"outcome": "still_failing", "rationale": "did not improve"},
            rewritten_query="Harbor Institute Library Saturday hours",
            previous_answer="The library is on the moon.",
        )
    )
    kinds = [step["id"] for step in steps]
    assert kinds == [
        "query",
        "retrieve",
        "generate-first",
        "recover",
        "generate",
        "evaluate",
        "diagnose",
        "verify",
    ]
    retrieve = next(step for step in steps if step["id"] == "retrieve")
    assert "post-recovery" in retrieve["payload"]["note"]
    first_gen = next(step for step in steps if step["id"] == "generate-first")
    assert first_gen["payload"]["answer"] == "The library is on the moon."
    after_gen = next(step for step in steps if step["id"] == "generate")
    assert after_gen["payload"]["answer"].startswith("Saturday")
    recover = next(step for step in steps if step["id"] == "recover")
    assert recover["payload"]["rewritten_query"].startswith("Harbor")
    assert recover["payload"]["previous_answer"]
    evaluate = next(step for step in steps if step["id"] == "evaluate")
    assert evaluate["title"] == "Evaluate (after recovery)"
    verify = next(step for step in steps if step["id"] == "verify")
    assert verify["status"] == "error"


def test_accept_trace_has_a_single_generate_step() -> None:
    steps = trace_to_steps(
        _base(
            runtime_evaluation={
                "evidence_sufficient": True,
                "answer_supported": True,
                "sufficiency_rationale": "enough",
                "support_rationale": "supported",
                "judge": "scripted",
                "model": "none",
            },
            diagnosis={
                "failure_class": None,
                "rationale": "no failure",
                "detector": "first-pass-runtime",
            },
            recovery={"action": "accept", "reason": "no first-pass failure", "attributed_class": None},
        )
    )
    kinds = [step["id"] for step in steps]
    assert kinds == ["query", "retrieve", "generate", "evaluate", "diagnose", "recover"]
    generate = next(step for step in steps if step["id"] == "generate")
    assert generate["title"] == "Generate"
    assert "previous_answer" not in generate["payload"]
    assert generate["payload"]["answer"].startswith("Saturday")


def test_regenerate_trace_keeps_a_single_retrieve() -> None:
    steps = trace_to_steps(
        _base(
            previous_answer="Saturday 10:00-16:00 and 800 seats.",
            recovery={
                "action": "regenerate",
                "reason": "unsupported_generation",
                "attributed_class": "unsupported_generation",
            },
            runtime_evaluation={
                "evidence_sufficient": True,
                "answer_supported": True,
                "sufficiency_rationale": "enough",
                "support_rationale": "constrained",
                "judge": "scripted",
                "model": "none",
            },
            verification={"outcome": "improved", "rationale": "unsupported fact removed"},
        )
    )
    kinds = [step["id"] for step in steps]
    assert kinds == [
        "query",
        "retrieve",
        "generate-first",
        "recover",
        "generate",
        "evaluate",
        "verify",
    ]
    retrieve = next(step for step in steps if step["id"] == "retrieve")
    assert "note" not in retrieve["payload"]
    assert retrieve["title"] == "Retrieve"


def test_stored_first_pass_chunks_become_two_retrieve_steps() -> None:
    steps = trace_to_steps(
        _base(
            previous_answer="wrong building",
            rewritten_query="Hangar 2 titanium traveler",
            previous_retrieved_chunks=[
                {
                    "chunk_id": "traveler-2018::c000",
                    "doc_id": "traveler-2018",
                    "title": "2018 traveler",
                    "score": 0.8,
                    "text": "AMS 4911N",
                }
            ],
            recovery={
                "action": "rewrite",
                "reason": "first-pass evidence insufficient",
                "attributed_class": "retrieval_miss",
            },
            verification={"outcome": "improved", "rationale": "newer traveler"},
        )
    )
    kinds = [step["id"] for step in steps]
    assert kinds == [
        "query",
        "retrieve-first",
        "generate-first",
        "recover",
        "retrieve",
        "generate",
        "verify",
    ]
    first = next(step for step in steps if step["id"] == "retrieve-first")
    after = next(step for step in steps if step["id"] == "retrieve")
    assert first["payload"]["chunks"][0]["doc_id"] == "traveler-2018"
    assert after["payload"]["chunks"][0]["doc_id"] == "harbor-library"
    assert "note" not in after["payload"]


def test_proposed_rewrite_is_labeled_on_the_recover_step() -> None:
    steps = trace_to_steps(
        _base(
            runtime_evaluation={
                "evidence_sufficient": False,
                "answer_supported": False,
                "sufficiency_rationale": "thin",
                "support_rationale": "",
                "judge": "scripted",
                "model": "none",
            },
            diagnosis={
                "failure_class": None,
                "rationale": "not split on first pass",
                "detector": "first-pass-runtime",
            },
            recovery={
                "action": "rewrite",
                "reason": "first-pass evidence insufficient",
                "attributed_class": None,
                "source": "policy",
            },
            recovery_status="proposed",
        )
    )
    kinds = [step["id"] for step in steps]
    assert kinds == ["query", "retrieve", "generate", "evaluate", "diagnose", "recover"]
    diagnose = next(step for step in steps if step["id"] == "diagnose")
    assert diagnose["summary"] == "deferred until rewrite"
    recover = next(step for step in steps if step["id"] == "recover")
    assert recover["summary"] == "proposed: rewrite"
    assert recover["payload"]["source"] == "policy"
    assert recover["payload"]["recovery_status"] == "proposed"


def test_rewrite_with_empty_previous_answer_still_splits() -> None:
    steps = trace_to_steps(
        _base(
            previous_answer="",
            rewritten_query="Harbor Institute Library Saturday hours",
            previous_retrieved_chunks=[
                {
                    "chunk_id": "harbor-hours::c000",
                    "doc_id": "harbor-hours",
                    "title": "Hours",
                    "score": 0.4,
                    "text": "unrelated",
                }
            ],
            recovery={
                "action": "rewrite",
                "reason": "first-pass evidence insufficient",
                "attributed_class": "evidence_insufficiency",
            },
            verification={"outcome": "still_failing", "rationale": "still thin"},
            runtime_evaluation={
                "evidence_sufficient": False,
                "answer_supported": None,
                "sufficiency_rationale": "probe",
                "support_rationale": "",
                "judge": "scripted",
                "model": "none",
            },
            diagnosis={
                "failure_class": "evidence_insufficiency",
                "rationale": "still thin",
                "detector": "rewrite-outcome",
            },
            answer="I do not know based on the retrieved documents.",
            model="abstain",
        )
    )
    kinds = [step["id"] for step in steps]
    assert kinds == [
        "query",
        "retrieve-first",
        "generate-first",
        "recover",
        "retrieve",
        "generate",
        "evaluate",
        "diagnose",
        "verify",
    ]
    evaluate = next(step for step in steps if step["id"] == "evaluate")
    assert "rewrite retrieve probe" in evaluate["payload"]["note"]
    diagnose = next(step for step in steps if step["id"] == "diagnose")
    assert diagnose["title"] == "Diagnose (after recovery)"


def test_multi_attempt_recover_summary_joins_actions() -> None:
    steps = trace_to_steps(
        _base(
            previous_answer="wrong building",
            previous_retrieved_chunks=[
                {
                    "chunk_id": "traveler-2025::c000",
                    "doc_id": "traveler-2025",
                    "title": "2025 traveler",
                    "score": 0.2,
                    "text": "AMS 4911R",
                }
            ],
            recovery={
                "action": "expand",
                "reason": "widen top_k",
                "attributed_class": None,
            },
            recovery_status="applied",
            recovery_attempts=[
                {"index": 0, "action": "rewrite"},
                {"index": 1, "action": "expand"},
            ],
            verification={"outcome": "improved", "rationale": "about note entered"},
        )
    )
    recover = next(step for step in steps if step["id"] == "recover")
    assert recover["summary"] == "rewrite → expand"


def test_retrieve_step_carries_the_retrieval_signal() -> None:
    signal = {
        "top_score": 0.08,
        "runner_up_score": 0.07,
        "relative_margin": 0.125,
        "weak_top": True,
        "ambiguous_top": False,
        "reason": "top score 0.080 is below 0.150",
        "detector": "retrieval-score",
    }
    retrieve = next(
        step
        for step in trace_to_steps(_base(retrieval_signal=signal))
        if step["id"] == "retrieve"
    )
    assert retrieve["payload"]["retrieval_signal"] == signal


def test_first_pass_retrieve_keeps_the_signal_after_rewrite() -> None:
    signal = {"weak_top": True, "reason": "thin retrieve", "detector": "retrieval-score"}
    steps = trace_to_steps(
        _base(
            previous_answer="old",
            rewritten_query="Harbor Institute Library Saturday hours",
            previous_retrieved_chunks=[
                {
                    "chunk_id": "other::c000",
                    "doc_id": "other",
                    "title": "Other",
                    "score": 0.1,
                    "text": "unrelated",
                }
            ],
            retrieval_signal=signal,
            recovery={
                "action": "rewrite",
                "reason": "judge raised no failure, but retrieval looks unreliable",
                "trigger": "retrieval_signal",
            },
        )
    )
    first = next(step for step in steps if step["id"] == "retrieve-first")
    after = next(step for step in steps if step["id"] == "retrieve")
    recover = next(step for step in steps if step["id"] == "recover")
    assert first["payload"]["retrieval_signal"] == signal
    assert "retrieval_signal" not in after["payload"]
    assert recover["payload"]["trigger"] == "retrieval_signal"
