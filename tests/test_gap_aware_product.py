"""Product wiring for the frozen gap-aware policy. Decisions are not retuned here."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.api.overview import LogicalRun, _usage_totals, aggregate_overview, group_logical_runs
from swrag.orchestration.loop import run_first_pass
from swrag.pipeline.baseline import run_query
from swrag.projects import default_project_config, normalize_project_config
from swrag.recovery.gap_signal import CONFLICT, assess_evidence, blocking_assessment, safe_abstention
from swrag.recovery.policy import (
    DEFAULT_POLICY,
    POLICY_V1,
    POLICY_V2C_GAP_AWARE,
    resolve_product_policy,
)
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import GenerationResult, RetrievalResult, RuntimeEvaluation
from swrag.usage import estimated_list_cost

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"


def test_product_policy_defaults_to_v1_and_rejects_research_variants() -> None:
    assert DEFAULT_POLICY == POLICY_V1
    assert resolve_product_policy(None) == POLICY_V1
    assert resolve_product_policy("") == POLICY_V1
    assert resolve_product_policy("gap_aware") == POLICY_V2C_GAP_AWARE
    assert resolve_product_policy("v2c_gap_aware") == POLICY_V2C_GAP_AWARE
    try:
        resolve_product_policy("v2a_margin")
    except ValueError:
        return
    raise AssertionError("research-only policies must stay off the product surface")


def test_missing_config_stays_v1_until_gap_aware_is_explicit() -> None:
    assert default_project_config()["recovery_policy"] == "v1"
    assert normalize_project_config({"instructions": "", "chat_model": "gpt-4o-mini", "top_k": 4})[
        "recovery_policy"
    ] == "v1"
    chosen = normalize_project_config(
        {"instructions": "", "chat_model": "gpt-4o-mini", "top_k": 4, "recovery_policy": "gap_aware"}
    )
    assert chosen["recovery_policy"] == "gap_aware"


def test_conflict_answer_does_not_assert_the_diagnosis() -> None:
    phones = (
        "DKU Library phone (+86) 0512-36658756.",
        "DKU Library handbook phone (0512) 3665-7027.",
    )
    assessment = assess_evidence("What phone number is listed for the DKU Library?", phones)
    assert assessment.label == CONFLICT
    answer = safe_abstention(assessment)
    assert answer.lower().startswith("i do not know")
    assert "more than one value" not in answer.lower()
    assert "36658756" not in answer
    assert "3665-7027" not in answer
    assert "sufficient support" in answer
    blocked = blocking_assessment(
        "How much does a Tide Canteen meal cost in harbor credits?",
        "A standard meal costs 3 harbor credits.",
        ("A standard meal at the East Canteen costs 3 harbor credits.",),
    )
    assert blocked is not None
    neighbor_answer = safe_abstention(blocked)
    assert "3 harbor credits" not in neighbor_answer
    assert "4 harbor credits" not in neighbor_answer


def test_prose_time_range_is_the_same_hours_as_the_hyphenated_span() -> None:
    chunks = (
        "Saturday walk-in hours are 09:00-13:00 on the March 2026 notice.",
        "Saturday walk-in hours were 10:00-12:00 on the 2023 notice.",
    )
    question = "What are the Saturday walk-in hours at the Northhaven Cedar Street billing desk?"
    for answer in (
        "The Saturday walk-in hours are from 09:00 to 13:00.",
        "The Saturday walk-in hours are 09:00-13:00.",
        "The Saturday walk-in hours are 09:00 – 13:00.",
    ):
        blocked = blocking_assessment(question, answer, chunks)
        assert blocked is not None
        abstained = safe_abstention(blocked)
        assert "09:00" not in abstained
        assert "13:00" not in abstained
        assert "10:00" not in abstained
    assert blocking_assessment(question, "The desk is closed on Saturday.", chunks) is None


def test_retrieve_only_and_baseline_store_policy_without_recovering(tmp_path: Path) -> None:
    retrieve = run_query(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "retrieve",
        generate=False,
        embedder=FakeEmbedder(),
        run_mode="retrieve_only",
        recovery_policy=POLICY_V2C_GAP_AWARE,
    )
    retrieve_payload = json.loads(retrieve.trace_path.read_text(encoding="utf-8"))
    assert retrieve_payload["recovery_policy"] == POLICY_V2C_GAP_AWARE
    assert not retrieve_payload.get("recovery_attempts")
    assert retrieve_payload.get("recovery") is None

    baseline = run_query(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "baseline",
        generate=False,
        embedder=FakeEmbedder(),
        run_mode="baseline",
        recovery_policy=POLICY_V1,
    )
    baseline_payload = json.loads(baseline.trace_path.read_text(encoding="utf-8"))
    assert baseline_payload["recovery_policy"] == POLICY_V1
    assert not baseline_payload.get("recovery_attempts")


def test_confirm_mode_proposes_expand_and_does_not_apply_it(tmp_path: Path) -> None:
    class _Judge:
        def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
            del question, answer, retrieval
            return RuntimeEvaluation(
                evidence_sufficient=False,
                answer_supported=None,
                sufficiency_rationale="not enough",
                support_rationale="",
                judge="scripted",
                model="none",
            )

    class _Canned:
        def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
            del query, retrieval
            return GenerationResult(answer="A made up answer.", model="canned")

    result = run_first_pass(
        "What fee is listed?",
        corpus_dir=ROOT / "datasets/kestrel-aero/corpus",
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_Canned(),  # type: ignore[arg-type]
        judge=_Judge(),
        recovery_policy="gap_aware",
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["recovery_status"] == "proposed"
    assert payload["recovery"]["action"] == "expand"
    assert payload["recovery_policy"] == POLICY_V2C_GAP_AWARE
    assert not payload.get("recovery_attempts")


def test_api_omitted_policy_is_v1_and_unknown_policy_is_rejected(tmp_path: Path) -> None:
    app = create_app(corpus_dir=CORPUS, traces_dir=tmp_path)
    with TestClient(app) as client:
        omitted = client.post(
            "/api/runs",
            json={"question": "When is the library open?", "mode": "retrieve_only"},
        )
        assert omitted.status_code == 200, omitted.text
        body = omitted.json()
        assert body["recovery_policy"] == "v1"
        assert body["trace"]["recovery_policy"] == "v1"
        assert body["safe_stop"] is False
        assert body["cost_estimate"] is None
        selected = client.post(
            "/api/runs",
            json={
                "question": "When is the library open?",
                "mode": "retrieve_only",
                "recovery_policy": "gap_aware",
            },
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["recovery_policy"] == POLICY_V2C_GAP_AWARE
        assert not selected.json()["trace"].get("recovery_attempts")
        rejected = client.post(
            "/api/runs",
            json={
                "question": "When is the library open?",
                "mode": "retrieve_only",
                "recovery_policy": "v2a_margin",
            },
        )
        assert rejected.status_code == 400


def test_saved_project_config_keeps_an_explicit_policy(tmp_path: Path) -> None:
    app = create_app(
        corpus_dir=CORPUS,
        traces_dir=tmp_path / "traces",
        traces_root=tmp_path / "traces-root",
        projects_root=tmp_path / "projects",
    )
    with TestClient(app) as client:
        created = client.post("/api/projects", json={"name": "Guarded"})
        assert created.status_code == 200, created.text
        project_id = created.json()["active_id"]
        saved = client.patch(
            f"/api/projects/{project_id}/config",
            json={
                "instructions": "",
                "chat_model": "gpt-4o-mini",
                "top_k": 4,
                "recovery_policy": "gap_aware",
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["project"]["config"]["recovery_policy"] == "gap_aware"
        omitted = client.patch(
            f"/api/projects/{project_id}/config",
            json={"instructions": "", "chat_model": "gpt-4o-mini", "top_k": 4},
        )
        assert omitted.status_code == 200, omitted.text
        assert omitted.json()["project"]["config"]["recovery_policy"] == "v1"


def test_unobserved_tokens_are_not_summed_as_zero() -> None:
    missing = LogicalRun(
        traces=[
            {
                "run_id": "missing",
                "usage": {
                    "chat_calls": 2,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "tokens_observed": False,
                },
            }
        ]
    )
    assert _usage_totals(missing) is None
    observed = LogicalRun(
        traces=[
            {
                "run_id": "seen",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "tokens_observed": True,
                },
            }
        ]
    )
    assert _usage_totals(observed) == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "tokens_observed": True,
    }


def test_usage_estimate_is_absent_until_tokens_are_observed() -> None:
    assert estimated_list_cost(None) is None
    assert (
        estimated_list_cost(
            {
                "chat_calls": 2,
                "embedding_calls": 1,
                "prompt_tokens": None,
                "completion_tokens": None,
                "embedding_tokens": None,
                "tokens_observed": False,
            }
        )
        is None
    )
    estimate = estimated_list_cost(
        {
            "chat_calls": 1,
            "embedding_calls": 0,
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            "embedding_tokens": 0,
            "tokens_observed": True,
        }
    )
    assert estimate is not None
    assert estimate["label"] == "estimated"
    assert estimate["estimated_list_usd"] == 0.15
    assert "Not an invoice" in str(estimate["assumptions"])


def test_safe_stop_is_not_counted_as_improved_or_unresolved() -> None:
    stopped = {
        "run_id": "stop",
        "timestamp": "2026-10-07T00:00:00+00:00",
        "query": "What is the fee?",
        "recovery_policy": "v2c_gap_aware",
        "recovery_status": "applied",
        "answer": "I do not know based on the retrieved documents.",
        "runtime_evaluation": {"evidence_sufficient": False, "answer_supported": None},
        "verification": {"outcome": "still_failing", "rationale": "stopped"},
        "recovery": {
            "action": "abstain",
            "parameters": {"stop_reason": "bounded search did not find support"},
        },
        "recovery_attempts": [
            {
                "action": "abstain",
                "executed": True,
                "parameters": {"stop_reason": "bounded search did not find support"},
            }
        ],
    }
    failing = {
        "run_id": "fail",
        "timestamp": "2026-10-07T00:01:00+00:00",
        "query": "Still wrong",
        "recovery_policy": "v1",
        "recovery_status": "applied",
        "runtime_evaluation": {"evidence_sufficient": False, "answer_supported": False},
        "verification": {"outcome": "still_failing", "rationale": "unsupported"},
        "recovery": {"action": "rewrite"},
        "recovery_attempts": [{"action": "rewrite", "executed": True}],
    }
    degraded_stop = {
        "run_id": "degraded-stop",
        "timestamp": "2026-10-07T00:02:00+00:00",
        "query": "Which phone?",
        "recovery_policy": "v2c_gap_aware",
        "recovery_status": "applied",
        "answer": "I do not know based on the retrieved documents.",
        "runtime_evaluation": {"evidence_sufficient": True, "answer_supported": None},
        "verification": {"outcome": "degraded", "rationale": "support flag dropped"},
        "recovery": {
            "action": "abstain",
            "parameters": {"stop_reason": "bounded search did not find support"},
        },
        "recovery_attempts": [
            {
                "action": "abstain",
                "executed": True,
                "parameters": {"stop_reason": "bounded search did not find support"},
            }
        ],
    }
    overview = aggregate_overview(group_logical_runs([stopped, failing, degraded_stop]))
    assert overview["safe_stops"] == 2
    assert overview["unresolved"] == 1
    assert overview["verified_improved"]["count"] == 0
    history = {run.root_id: run for run in group_logical_runs([stopped, failing])}
    assert history["stop"].traces[0]["recovery_policy"] == "v2c_gap_aware"


def test_product_sources_do_not_read_offline_labels() -> None:
    files = [
        ROOT / "src/swrag/api/app.py",
        ROOT / "src/swrag/api/overview.py",
        ROOT / "src/swrag/projects.py",
        ROOT / "web/app.js",
        ROOT / "web/flight-recorder.js",
        ROOT / "web/reliability.js",
    ]
    for path in files:
        source = path.read_text(encoding="utf-8")
        assert "corpus_answerability" not in source
        assert "human_before" not in source
        assert "supporting_rank" not in source
        assert "phase8a_holdout" not in source


def test_policy_resolution_is_cheap() -> None:
    started = time.perf_counter()
    for _ in range(10000):
        assert resolve_product_policy("v1") == POLICY_V1
    assert time.perf_counter() - started < 0.5
