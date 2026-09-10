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
    assert diagnose["summary"] == "no class claimed"


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
        "generate",
        "evaluate",
        "diagnose",
        "recover",
        "verify",
    ]
    recover = next(step for step in steps if step["id"] == "recover")
    assert recover["payload"]["rewritten_query"].startswith("Harbor")
    assert recover["payload"]["previous_answer"]
    verify = next(step for step in steps if step["id"] == "verify")
    assert verify["status"] == "error"
