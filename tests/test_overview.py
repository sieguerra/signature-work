"""Logical-run overview aggregation. No gold, no batch summaries, no model calls."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.api.overview import (
    aggregate_overview,
    group_logical_runs,
    logical_run_history,
    overview_for_traces,
)


def _eval(sufficient: bool, supported: bool | None = True) -> dict:
    return {"evidence_sufficient": sufficient, "answer_supported": supported}


def _trace(run_id: str, **overrides: object) -> dict:
    payload: dict = {
        "run_id": run_id,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "query": f"Question {run_id}",
        "answer": "An answer.",
    }
    payload.update(overrides)
    return payload


def _overview(payloads: list[dict]) -> dict:
    return aggregate_overview(group_logical_runs(payloads))


def _write(directory: Path, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{payload['run_id']}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_confirm_parent_and_child_are_one_logical_run() -> None:
    parent = _trace(
        "parent",
        timestamp="2026-01-01T00:00:00+00:00",
        query="When does the library close?",
        runtime_evaluation=_eval(False, False),
        diagnosis={"failure_class": "unsupported_generation"},
        recovery={"action": "rewrite", "attributed_class": "unsupported_generation"},
        recovery_status="proposed",
        latency_ms=100,
    )
    child = _trace(
        "child",
        timestamp="2026-01-01T00:01:00+00:00",
        query="When does the library close?",
        parent_run_id="parent",
        runtime_evaluation=_eval(True, True),
        recovery={"action": "rewrite"},
        recovery_status="applied",
        verification={"outcome": "improved"},
        latency_ms=40,
    )
    overview = _overview([parent, child])
    assert overview["observed_runs"] == 1
    assert overview["judged_runs"] == 1
    assert overview["recovery_required"] == {"count": 1, "total": 1, "rate": 1.0}
    assert overview["verified_improved"] == {"count": 1, "total": 1, "rate": 1.0}
    assert overview["unresolved"] == 0
    assert [row["logical_run_id"] for row in overview["recent_activity"]] == ["parent"]
    assert overview["recent_activity"][0]["inspect_run_id"] == "child"
    assert overview["recent_activity"][0]["latency_ms"] == 140
    assert overview["latency"]["median_ms"] == 140
    assert "child" not in {row["logical_run_id"] for row in overview["recent_activity"]}


def test_auto_recovery_trace_is_one_logical_run() -> None:
    overview = _overview(
        [
            _trace(
                "auto",
                first_pass_evaluation=_eval(False, False),
                runtime_evaluation=_eval(True, True),
                recovery={"action": "expand"},
                recovery_status="applied",
                recovery_attempts=[
                    {"action": "rewrite", "attributed_class": "retrieval_miss"},
                    {"action": "expand", "attributed_class": "evidence_insufficiency"},
                ],
                verification={"outcome": "improved"},
                diagnosis={"failure_class": "unsupported_generation"},
            )
        ]
    )
    assert overview["observed_runs"] == 1
    assert overview["judged_runs"] == 1
    assert overview["verified_improved"]["count"] == 1
    assert overview["verified_improved"]["total"] == 1
    names = {item["name"]: item["count"] for item in overview["applied_actions"]}
    assert names == {"rewrite": 1, "expand": 1}
    assert "regenerate" not in names
    diagnosis = {item["name"]: item["count"] for item in overview["diagnoses"]}
    assert diagnosis["unsupported_generation"] == 1
    assert diagnosis["retrieval_miss"] == 1
    assert diagnosis["evidence_insufficiency"] == 1


def test_accept_is_not_recovery() -> None:
    overview = _overview(
        [
            _trace(
                "accepted",
                runtime_evaluation=_eval(True, True),
                recovery={"action": "accept"},
                recovery_status="applied",
            )
        ]
    )
    assert overview["judged_runs"] == 1
    assert overview["recovery_required"]["count"] == 0
    assert overview["outcomes"]["applied"] == 0
    assert overview["verified_improved"]["total"] == 0
    assert overview["verified_improved"]["rate"] is None
    assert overview["applied_actions"] == []
    assert overview["unresolved"] == 0


def test_proposed_recovery_is_pending_and_excluded_from_verified_improved() -> None:
    overview = _overview(
        [
            _trace(
                "waiting",
                runtime_evaluation=_eval(False, None),
                recovery={"action": "expand", "attributed_class": "evidence_insufficiency"},
                recovery_status="proposed",
            )
        ]
    )
    assert overview["recovery_required"] == {"count": 1, "total": 1, "rate": 1.0}
    assert overview["verified_improved"] == {"count": 0, "total": 0, "rate": None}
    assert overview["outcomes"]["applied"] == 0
    assert overview["unresolved"] == 1
    assert overview["needs_attention"][0]["kind"] == "pending"
    assert overview["needs_attention"][0]["inspect_run_id"] == "waiting"
    assert overview["pending_actions"] == [{"name": "expand", "count": 1}]
    assert overview["applied_actions"] == []
    assert "Not enough recovery data" in overview["summary"]


def test_improved_unchanged_still_failing_and_degraded() -> None:
    overview = _overview(
        [
            _trace(
                "better",
                timestamp="2026-04-01T00:00:00+00:00",
                runtime_evaluation=_eval(True, True),
                first_pass_evaluation=_eval(False, False),
                recovery={"action": "regenerate"},
                recovery_status="applied",
                verification={"outcome": "improved"},
            ),
            _trace(
                "same",
                timestamp="2026-03-01T00:00:00+00:00",
                runtime_evaluation=_eval(False, False),
                first_pass_evaluation=_eval(False, False),
                recovery={"action": "rewrite"},
                recovery_status="applied",
                verification={"outcome": "unchanged"},
            ),
            _trace(
                "stuck",
                timestamp="2026-02-01T00:00:00+00:00",
                runtime_evaluation=_eval(False, False),
                first_pass_evaluation=_eval(False, False),
                recovery={"action": "expand"},
                recovery_status="applied",
                verification={"outcome": "still_failing"},
            ),
            _trace(
                "worse",
                timestamp="2026-05-01T00:00:00+00:00",
                runtime_evaluation=_eval(False, False),
                first_pass_evaluation=_eval(True, True),
                recovery={"action": "rewrite"},
                recovery_status="applied",
                verification={"outcome": "degraded"},
            ),
        ]
    )
    assert overview["verified_improved"] == {"count": 1, "total": 4, "rate": 0.25}
    assert overview["unchanged"] == 1
    assert overview["outcomes"]["improved"] == 1
    assert overview["outcomes"]["unchanged"] == 1
    assert overview["outcomes"]["still_failing"] == 1
    assert overview["outcomes"]["degraded"] == 1
    assert overview["unresolved"] == 2
    kinds = [item["kind"] for item in overview["needs_attention"]]
    assert kinds == ["degraded", "still_failing"]
    assert "same" not in {item["logical_run_id"] for item in overview["needs_attention"]}


def test_abstain_is_not_unresolved_unless_verification_says_so() -> None:
    overview = _overview(
        [
            _trace(
                "safe-stop",
                runtime_evaluation=_eval(True, True),
                first_pass_evaluation=_eval(False, False),
                recovery={"action": "abstain"},
                recovery_status="applied",
                verification={"outcome": "unchanged"},
            )
        ]
    )
    assert overview["applied_actions"] == [{"name": "abstain", "count": 1}]
    assert overview["unchanged"] == 1
    assert overview["unresolved"] == 0
    assert overview["needs_attention"] == []


def test_retrieve_only_and_unjudged_baseline_are_outside_the_judged_denominator() -> None:
    overview = _overview(
        [
            _trace("retrieve", answer="", model="retrieve-only"),
            _trace("baseline", answer="A baseline answer.", recovery=None),
            _trace(
                "judged",
                runtime_evaluation=_eval(True, True),
                recovery={"action": "accept"},
                recovery_status="applied",
            ),
        ]
    )
    assert overview["observed_runs"] == 3
    assert overview["judged_runs"] == 1
    assert overview["recovery_required"] == {"count": 0, "total": 1, "rate": 0.0}
    assert overview["signals"]["evidence_sufficient"]["initial"]["total"] == 1
    assert "0 of 1 judged runs required recovery" in overview["summary"]


def test_summary_json_and_gold_fields_do_not_enter_the_overview(tmp_path: Path) -> None:
    _write(
        tmp_path,
        _trace(
            "real",
            runtime_evaluation=_eval(True, True),
            recovery={"action": "accept"},
            recovery_status="applied",
            gold_answer="GOLD_ANSWER_SHOULD_NOT_LEAK",
        ),
    )
    (tmp_path / "summary.json").write_text(
        json.dumps({"n": 99, "gold_answer": "GOLD_ANSWER_SHOULD_NOT_LEAK", "batch": True}),
        encoding="utf-8",
    )
    (tmp_path / "comparison.json").write_text(
        json.dumps({"run_id": "comparison", "query": "not a run", "n": 50}),
        encoding="utf-8",
    )
    overview = overview_for_traces(tmp_path)
    encoded = json.dumps(overview)
    assert overview["observed_runs"] == 1
    assert overview["judged_runs"] == 1
    assert "batch_summary" not in overview
    assert "GOLD_ANSWER_SHOULD_NOT_LEAK" not in encoded
    assert "gold" not in encoded


def test_historical_trace_and_empty_directory_do_not_crash(tmp_path: Path) -> None:
    empty = overview_for_traces(tmp_path)
    assert empty["observed_runs"] == 0
    assert empty["judged_runs"] == 0
    assert empty["recovery_required"]["rate"] is None
    assert empty["verified_improved"]["rate"] is None
    assert empty["unresolved"] == 0
    assert empty["summary"] == "No judged runs yet."
    assert empty["latency"]["median_ms"] is None
    assert empty["recent_activity"] == []

    _write(
        tmp_path,
        {
            "run_id": "old",
            "query": "An old question",
            "timestamp": "2019-05-01",
            "diagnosis": "not-a-dict",
            "recovery": "not-a-dict",
            "latency_ms": "slow",
            "verification": None,
        },
    )
    historical = overview_for_traces(tmp_path)
    assert historical["observed_runs"] == 1
    assert historical["judged_runs"] == 0
    assert historical["summary"] == "No judged runs yet."
    assert historical["recent_activity"][0]["initial_state"] == "not_judged"
    assert historical["latency"]["median_ms"] is None


def test_null_answer_supported_is_not_counted_as_false() -> None:
    overview = _overview(
        [
            _trace(
                "null-support",
                runtime_evaluation=_eval(True, None),
                recovery={"action": "accept"},
                recovery_status="applied",
            )
        ]
    )
    supported = overview["signals"]["answer_supported"]["final"]
    evidence = overview["signals"]["evidence_sufficient"]["final"]
    assert supported == {"true": 0, "total": 0, "rate": None}
    assert evidence == {"true": 1, "total": 1, "rate": 1.0}


def test_initial_and_final_signals_use_first_pass_and_final_state() -> None:
    overview = _overview(
        [
            _trace(
                "repaired",
                first_pass_evaluation=_eval(False, False),
                runtime_evaluation=_eval(True, True),
                recovery={"action": "regenerate"},
                recovery_status="applied",
                verification={"outcome": "improved"},
            )
        ]
    )
    evidence = overview["signals"]["evidence_sufficient"]
    assert evidence["initial"] == {"true": 0, "total": 1, "rate": 0.0}
    assert evidence["final"] == {"true": 1, "total": 1, "rate": 1.0}


def test_logical_run_history_joins_confirm_child_and_skips_summary(tmp_path: Path) -> None:
    _write(
        tmp_path,
        _trace(
            "parent",
            query="Library hours",
            runtime_evaluation=_eval(False, False),
            recovery={"action": "rewrite"},
            recovery_status="proposed",
        ),
    )
    _write(
        tmp_path,
        _trace(
            "child",
            query="Library hours",
            parent_run_id="parent",
            runtime_evaluation=_eval(True, True),
            recovery={"action": "rewrite"},
            recovery_status="applied",
            verification={"outcome": "improved"},
        ),
    )
    (tmp_path / "summary.json").write_text('{"gold_answer":"GOLD_ANSWER_SHOULD_NOT_LEAK"}', encoding="utf-8")
    history = logical_run_history(tmp_path)
    assert len(history["runs"]) == 1
    row = history["runs"][0]
    assert row["logical_run_id"] == "parent"
    assert row["trace_ids"] == ["parent", "child"]
    assert row["verification"] == "improved"
    assert "GOLD_ANSWER_SHOULD_NOT_LEAK" not in json.dumps(history)


def test_logical_run_history_keeps_recovery_path_source_and_missing_diagnosis(tmp_path: Path) -> None:
    traces = [
        _trace(
            "parent",
            query="When does the library close?",
            runtime_evaluation=_eval(False, None),
            diagnosis={"failure_class": None},
            recovery={"action": "rewrite", "source": "policy", "trigger": "judge"},
            recovery_status="proposed",
        ),
        _trace(
            "child",
            parent_run_id="parent",
            query="When does the library close?",
            runtime_evaluation=_eval(False, False),
            recovery={"action": "rewrite", "source": "operator", "trigger": "judge"},
            recovery_status="applied",
            verification={"outcome": "unchanged"},
            usage={"prompt_tokens": 10, "completion_tokens": 4},
        ),
        _trace(
            "auto",
            query="How many seats?",
            first_pass_evaluation=_eval(True, False),
            runtime_evaluation=_eval(True, True),
            recovery={"action": "expand", "source": "policy", "trigger": "retrieval_signal"},
            recovery_status="applied",
            recovery_attempts=[
                {"action": "rewrite", "trigger": "judge", "source": "policy"},
                {"action": "expand", "trigger": "retrieval_signal", "source": "policy"},
            ],
            verification={"outcome": "improved"},
        ),
        _trace(
            "accepted",
            query="Breakfast?",
            runtime_evaluation=_eval(True, True),
            recovery={"action": "accept", "source": "policy"},
            recovery_status="applied",
        ),
        _trace(
            "historical",
            query="Annex hours?",
            runtime_evaluation=_eval(False, None),
            recovery={"action": "rewrite", "source": "policy", "trigger": "judge"},
            recovery_status="applied",
            verification={"outcome": "still_failing"},
        ),
        _trace(
            "degraded",
            runtime_evaluation=_eval(False, False),
            recovery={"action": "regenerate"},
            recovery_status="applied",
            verification={"outcome": "degraded"},
        ),
        _trace(
            "pending",
            runtime_evaluation=_eval(False, None),
            recovery={"action": "expand", "source": "policy", "trigger": "retrieval_signal"},
            recovery_status="proposed",
        ),
        _trace(
            "null_supported",
            query="Evidence only?",
            runtime_evaluation=_eval(True, None),
        ),
    ]
    for payload in traces:
        _write(tmp_path, payload)
    rows = {row["logical_run_id"]: row for row in logical_run_history(tmp_path)["runs"]}
    assert "child" not in rows
    assert rows["parent"]["trace_ids"] == ["parent", "child"]
    assert rows["parent"]["recovery"] == ["rewrite"]
    assert rows["parent"]["source"] == "operator"
    assert rows["parent"]["diagnoses"] == []
    assert rows["parent"]["verification"] == "unchanged"
    assert rows["parent"]["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "tokens_observed": True,
    }
    assert rows["auto"]["recovery"] == ["rewrite", "expand"]
    assert rows["auto"]["trigger"] == "judge · retrieval_signal"
    assert rows["auto"]["source"] == "policy"
    assert rows["accepted"]["recovery"] == []
    assert rows["accepted"]["recovery_required"] is False
    assert rows["accepted"]["recovery_pending"] is None
    assert rows["historical"]["recovery"] == ["rewrite"]
    assert rows["historical"]["verification"] == "still_failing"
    assert rows["degraded"]["verification"] == "degraded"
    assert rows["pending"]["recovery_pending"] == "expand"
    assert rows["pending"]["recovery"] == []
    assert rows["pending"]["verification"] is None
    assert rows["null_supported"]["initial_state"] == "evidence_sufficient"
    assert rows["null_supported"]["recovery_required"] is False


def test_overview_endpoint_follows_the_active_system(tmp_path: Path) -> None:
    _write(
        tmp_path / "dku",
        _trace(
            "dku-run",
            query="DKU only question",
            runtime_evaluation=_eval(False, False),
            recovery={"action": "rewrite"},
            recovery_status="applied",
            verification={"outcome": "still_failing"},
        ),
    )
    _write(
        tmp_path / "harbor",
        _trace(
            "harbor-run",
            query="Harbor only question",
            runtime_evaluation=_eval(True, True),
            recovery={"action": "accept"},
            recovery_status="applied",
        ),
    )
    app = create_app(traces_root=tmp_path)
    with TestClient(app) as client:
        dku = client.get("/api/overview")
        assert dku.status_code == 200
        dku_body = dku.json()
        assert dku_body["judged_runs"] == 1
        assert dku_body["unresolved"] == 1
        assert dku_body["recent_activity"][0]["query"] == "DKU only question"
        assert "batch_summary" not in dku_body
        history = client.get("/api/logical-runs")
        assert history.status_code == 200
        assert history.json()["runs"][0]["trace_ids"] == ["dku-run"]

        switched = client.post("/api/corpus", json={"id": "harbor"})
        assert switched.status_code == 200
        harbor = client.get("/api/overview").json()
        assert harbor["judged_runs"] == 1
        assert harbor["unresolved"] == 0
        assert harbor["recovery_required"]["count"] == 0
        assert harbor["recent_activity"][0]["query"] == "Harbor only question"
        assert "DKU only question" not in json.dumps(harbor)
