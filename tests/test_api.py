"""HTTP adapter tests. No live OpenAI calls."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.tracing.tracer import write_trace
from swrag.types import BaselineRunResult, RetrievalResult, TraceRecord

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"


def _client(tmp_path: Path) -> TestClient:
    app = create_app(corpus_dir=CORPUS, traces_dir=tmp_path)
    return TestClient(app)


def test_meta_does_not_include_an_api_key(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        payload = client.get("/api/meta").json()
        assert "api_key" not in payload
        assert "api_key_present" in payload
        assert payload["traces_dir"] == str(tmp_path)
        assert payload["corpus_id"] == "harbor"
        assert "agent_config" in payload
        assert payload["agent_config"] is None


def test_empty_trace_list(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        payload = client.get("/api/traces").json()
        assert payload["traces"] == []


def test_lists_and_loads_an_existing_trace(tmp_path: Path) -> None:
    write_trace(
        TraceRecord(
            run_id="ui_run_1",
            timestamp="2026-09-10T12:00:00+00:00",
            query="When does the library close?",
            retrieved_chunks=(),
            answer="I do not know based on the retrieved documents.",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
        ),
        tmp_path,
    )
    with _client(tmp_path) as client:
        listing = client.get("/api/traces").json()["traces"]
        assert listing[0]["run_id"] == "ui_run_1"
        loaded = client.get("/api/traces/ui_run_1")
        assert loaded.status_code == 200
        body = loaded.json()
        assert body["trace"]["query"].startswith("When does")
        assert [step["id"] for step in body["steps"]][:3] == ["query", "retrieve", "generate"]


def test_missing_trace_is_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/traces/does-not-exist")
        assert response.status_code == 404


def test_delete_trace_removes_the_file(tmp_path: Path) -> None:
    write_trace(
        TraceRecord(
            run_id="ui_run_delete",
            timestamp="2026-09-10T12:00:00+00:00",
            query="When does the library close?",
            retrieved_chunks=(),
            answer="I do not know based on the retrieved documents.",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
        ),
        tmp_path,
    )
    (tmp_path / "summary.json").write_text("{}", encoding="utf-8")
    with _client(tmp_path) as client:
        response = client.delete("/api/traces/ui_run_delete")
        assert response.status_code == 200, response.text
        assert response.json()["deleted"] == "ui_run_delete"
        assert response.json()["also_deleted"] == []
        assert client.get("/api/traces/ui_run_delete").status_code == 404
        assert client.get("/api/traces").json()["traces"] == []
    assert not (tmp_path / "ui_run_delete.json").exists()
    assert (tmp_path / "summary.json").exists()


def test_delete_missing_trace_is_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.delete("/api/traces/does-not-exist")
        assert response.status_code == 404


def test_delete_rejects_reserved_and_path_like_ids(tmp_path: Path) -> None:
    (tmp_path / "summary.json").write_text("{}", encoding="utf-8")
    with _client(tmp_path) as client:
        assert client.delete("/api/traces/summary").status_code == 404
        assert client.delete("/api/traces/..").status_code == 404
    assert (tmp_path / "summary.json").exists()


def test_delete_all_traces_keeps_summary_files(tmp_path: Path) -> None:
    write_trace(
        TraceRecord(
            run_id="ui_run_a",
            timestamp="2026-09-10T12:00:00+00:00",
            query="When does the library close?",
            retrieved_chunks=(),
            answer="I do not know based on the retrieved documents.",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
        ),
        tmp_path,
    )
    write_trace(
        TraceRecord(
            run_id="ui_run_b",
            timestamp="2026-09-10T12:01:00+00:00",
            query="How many seats does the library have?",
            retrieved_chunks=(),
            answer="560",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
        ),
        tmp_path / "nested",
    )
    (tmp_path / "summary.json").write_text("{}", encoding="utf-8")
    with _client(tmp_path) as client:
        empty = client.delete("/api/traces")
        # First call should remove both traces, including the nested one.
        assert empty.status_code == 200, empty.text
        assert empty.json()["deleted"] == 2
        assert client.get("/api/traces").json()["traces"] == []
        again = client.delete("/api/traces")
        assert again.status_code == 200
        assert again.json()["deleted"] == 0
    assert (tmp_path / "summary.json").exists()
    assert not (tmp_path / "ui_run_a.json").exists()
    assert not (tmp_path / "nested" / "ui_run_b.json").exists()


def test_empty_question_is_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/runs", json={"question": "   ", "mode": "retrieve_only"})
        assert response.status_code == 400


def test_unknown_mode_is_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"question": "When does the library close?", "mode": "billing"},
        )
        assert response.status_code == 400


def test_loop_without_api_key_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"question": "When does the library close?", "mode": "loop"},
        )
        assert response.status_code == 400
        assert "OPENAI_API_KEY" in response.json()["detail"]


def test_retrieve_only_run_writes_a_trace(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={
                "question": "When is the Harbor Institute Library open on Saturday?",
                "mode": "retrieve_only",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["run_id"]
        assert body["steps"][0]["id"] == "query"
        trace_files = list(tmp_path.glob("*.json"))
        assert len(trace_files) == 1
        saved = json.loads(trace_files[0].read_text(encoding="utf-8"))
        assert saved["query"].startswith("When is the Harbor")
        assert saved["top_k"] == 4
        assert isinstance(saved.get("latency_ms"), (int, float))
        assert saved["latency_ms"] >= 0
        assert len(saved["retrieved_chunks"]) <= 4
        assert "answers" not in saved


def test_retrieve_only_honors_top_k_one_and_four(tmp_path: Path) -> None:
    question = "When is the Harbor Institute Library open on Saturday?"
    with _client(tmp_path) as client:
        for top_k in (1, 4):
            response = client.post(
                "/api/runs",
                json={"question": question, "mode": "retrieve_only", "top_k": top_k},
            )
            assert response.status_code == 200, response.text
            trace = response.json()["trace"]
            assert trace["top_k"] == top_k
            assert 1 <= len(trace["retrieved_chunks"]) <= top_k


def test_top_k_out_of_range_is_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        too_small = client.post(
            "/api/runs",
            json={"question": "When does the library close?", "mode": "retrieve_only", "top_k": 0},
        )
        too_large = client.post(
            "/api/runs",
            json={"question": "When does the library close?", "mode": "retrieve_only", "top_k": 21},
        )
        assert too_small.status_code == 422
        assert too_large.status_code == 422


def test_index_page_and_assets_are_served(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Trace explorer" in page.text
        assert "delete-all-runs" in page.text
        assert "Test Console" in page.text
        assert 'href="#overview"' in page.text
        assert 'href="#test"' in page.text
        assert 'id="view-playground"' in page.text
        assert 'id="pg-canvas"' in page.text
        assert 'id="pg-palette"' in page.text
        assert 'id="pg-run"' in page.text
        assert 'id="nav-knowledge"' in page.text
        assert 'id="view-knowledge"' in page.text
        assert 'id="nav-agent"' in page.text
        assert 'id="view-agent"' in page.text
        assert 'id="nav-api"' in page.text
        assert 'id="view-api"' in page.text
        css = client.get("/static/styles.css")
        assert css.status_code == 200
        assert "--bg:" in css.text
        assert "view-nav" in css.text
        assert "dropzone" in css.text
        charts = client.get("/static/charts.js")
        assert charts.status_code == 200
        assert "No runs scored yet." in charts.text
        assert "These averages are model scores." in charts.text
        assert "The loop does not use them, and a person has not checked them against human ratings." in charts.text
        assert "they have not been checked against human ratings yet." in charts.text
        js = client.get("/static/app.js")
        assert js.status_code == 200
        assert "example-chips" in js.text
        assert "run-delete" in js.text
        assert "deleteAllRuns" in js.text
        assert "switchCorpus" in js.text
        assert "readTopK" in js.text
        assert 'playground: "test"' in js.text
        assert 'evaluation: "reliability"' in js.text
        assert 'knowledge: "data"' in js.text
        assert 'agent: "configuration"' in js.text
        assert 'api: "integrations"' in js.text
        assert "createPlaygroundProject" in js.text
        assert "savePlaygroundConfig" in js.text
        assert "resetPlaygroundChat" in js.text
        assert 'id="pg-reset"' in page.text
        assert 'id="pg-rerun"' in page.text
        assert "pg-config" in css.text
        assert 'id="corpus"' in page.text
        assert 'id="top-k"' in page.text
        assert 'id="eval-strip"' in page.text
        assert "loadEval" in js.text
        assert "answer-split" in js.text
        assert "answer-pills" in js.text
        assert "Rewritten query" in js.text
        assert "Before and after are the same text" in js.text
        assert "formatAnswerHtml" in js.text
        assert "function escapeHtml" in js.text
        assert "cite-missing" in js.text
        assert "Not in this retrieve" in js.text
        assert "chunk.page" in js.text
        assert "applyRecovery" in js.text
        assert "Regenerate from evidence" in js.text
        assert "Rewrite query and retrieve" in js.text
        assert "Widen retrieval (higher top_k)" in js.text
        assert "recover-bar" in js.text
        assert 'id="recover-bar"' in page.text
        assert 'value="loop_confirm"' in page.text
        assert "Loop (confirm recovery)" in page.text
        assert "Loop (auto recover)" in page.text
        assert 'value="loop_confirm" selected' in page.text
        assert "has recovery" in js.text
        assert "after recovery" in js.text
        assert "child-run" in css.text
        assert "its recovered child" in js.text
        assert "First-pass evidence is insufficient" in js.text
        assert "proposed=" in js.text
        assert "mean latency" in js.text
        assert "no class claimed" not in js.text
        assert "Generate (first pass)" not in page.text


def test_eval_counts_active_traces_and_zeros_after_delete_all(tmp_path: Path) -> None:
    write_trace(
        TraceRecord(
            run_id="eval_accept",
            timestamp="2026-09-10T12:00:00+00:00",
            query="When does the library close?",
            retrieved_chunks=(),
            answer="Saturday 10:00-16:00",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
            recovery={"action": "accept", "reason": "ok", "attributed_class": None},
        ),
        tmp_path,
    )
    write_trace(
        TraceRecord(
            run_id="eval_rewrite",
            timestamp="2026-09-10T12:01:00+00:00",
            query="How many seats?",
            retrieved_chunks=(),
            answer="I do not know based on the retrieved documents.",
            model="abstain",
            embedding_model="fake-hash",
            top_k=4,
            recovery={
                "action": "rewrite",
                "reason": "insufficient",
                "attributed_class": "evidence_insufficiency",
            },
            verification={"outcome": "still_failing", "rationale": "still thin"},
            previous_answer="I do not know based on the retrieved documents.",
            latency_ms=1500,
        ),
        tmp_path,
    )
    write_trace(
        TraceRecord(
            run_id="eval_proposed",
            timestamp="2026-09-10T12:02:00+00:00",
            query="How many seats?",
            retrieved_chunks=(),
            answer="The library is on the moon.",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
            recovery={
                "action": "rewrite",
                "reason": "first-pass evidence insufficient",
                "attributed_class": None,
            },
            recovery_status="proposed",
        ),
        tmp_path,
    )
    (tmp_path / "summary.json").write_text('{"label": "batch"}', encoding="utf-8")
    with _client(tmp_path) as client:
        payload = client.get("/api/eval").json()
        assert payload["n"] == 3
        assert payload["proposed"] == 1
        assert payload["by_action"]["accept"] == 1
        assert payload["by_action"]["rewrite"] == 1
        assert payload["by_verification"]["still_failing"] == 1
        assert "none" not in payload["by_verification"]
        assert payload["abstain"] == 1
        assert payload["mean_latency_ms"] == 1500
        assert payload["batch_summary"]["label"] == "batch"
        assert "20260910T070623" not in payload["traces_dir"]
        runs = {row["run_id"]: row for row in payload["runs"]}
        assert [row["run_id"] for row in payload["runs"]] == [
            "eval_accept",
            "eval_rewrite",
            "eval_proposed",
        ]
        assert runs["eval_accept"]["path"] == []
        assert runs["eval_rewrite"]["path"] == ["rewrite"]
        assert runs["eval_rewrite"]["failure_class"] == "evidence_insufficiency"
        assert runs["eval_rewrite"]["abstained"] is True
        assert runs["eval_rewrite"]["first_abstained"] is True
        assert runs["eval_accept"]["first_abstained"] is False
        assert runs["eval_rewrite"]["latency_ms"] == 1500
        assert runs["eval_proposed"]["path"] == []
        assert runs["eval_proposed"]["proposed_action"] == "rewrite"
        assert not any("gold" in key for row in payload["runs"] for key in row)
        client.delete("/api/traces")
        empty = client.get("/api/eval").json()
        assert empty["n"] == 0
        assert empty["proposed"] == 0
        assert empty["abstain"] == 0
        assert empty["by_action"] == {}
        assert empty["mean_latency_ms"] is None
        assert empty["runs"] == []


def test_lists_corpora_and_switches_without_mixing_indexes(tmp_path: Path) -> None:
    app = create_app(traces_root=tmp_path)
    with TestClient(app) as client:
        listing = client.get("/api/corpora").json()
        ids = [item["id"] for item in listing["corpora"]]
        assert listing["active_id"] == "dku"
        assert "harbor" in ids
        assert "kestrel-aero" in ids
        unknown = client.post("/api/corpus", json={"id": "not-a-world"})
        assert unknown.status_code == 404
        switched = client.post("/api/corpus", json={"id": "harbor"})
        assert switched.status_code == 200, switched.text
        body = switched.json()
        assert body["active_id"] == "harbor"
        assert body["traces_dir"].endswith("harbor")
        meta = client.get("/api/meta").json()
        assert meta["corpus_id"] == "harbor"
        assert meta["examples"]
        response = client.post(
            "/api/runs",
            json={
                "question": "When is the Harbor Institute Library open on Saturday?",
                "mode": "retrieve_only",
            },
        )
        assert response.status_code == 200, response.text
        docs = [chunk["doc_id"] for chunk in response.json()["trace"]["retrieved_chunks"]]
        assert "harbor-library" in docs
        dku_docs = {"academic-building-dining", "dku-library-hours", "dku-about"}
        assert not (set(docs) & dku_docs)


def _empty_retrieval(query: str = "When does the library close?") -> RetrievalResult:
    return RetrievalResult(
        query=query,
        chunks=(),
        top_k=4,
        embedding_model="fake-hash",
    )


def _proposed_record(run_id: str = "ui_proposed") -> TraceRecord:
    return TraceRecord(
        run_id=run_id,
        timestamp="2026-09-16T12:00:00+00:00",
        query="When does the library close?",
        retrieved_chunks=(),
        answer="The library is on the moon.",
        model="none",
        embedding_model="fake-hash",
        top_k=4,
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
            "reason": "first-pass evidence insufficient: rewrite query and retrieve again",
            "attributed_class": None,
            "source": "policy",
        },
        recovery_status="proposed",
    )


def test_delete_parent_also_deletes_recovered_child(tmp_path: Path) -> None:
    write_trace(_proposed_record("keep_parent"), tmp_path)
    write_trace(
        TraceRecord(
            run_id="keep_child",
            timestamp="2026-09-16T12:02:00+00:00",
            query="When does the library close?",
            retrieved_chunks=(),
            answer="Saturday 10:00-16:00",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
            previous_answer="The library is on the moon.",
            recovery={"action": "rewrite", "reason": "first-pass", "source": "policy"},
            recovery_status="applied",
            parent_run_id="keep_parent",
        ),
        tmp_path,
    )
    with _client(tmp_path) as client:
        response = client.delete("/api/traces/keep_parent")
        assert response.status_code == 200, response.text
        assert response.json()["deleted"] == "keep_parent"
        assert response.json()["also_deleted"] == ["keep_child"]
        assert client.get("/api/traces/keep_parent").status_code == 404
        assert client.get("/api/traces/keep_child").status_code == 404
        assert client.get("/api/traces").json()["traces"] == []


def test_delete_child_leaves_parent_proposed(tmp_path: Path, monkeypatch) -> None:
    write_trace(_proposed_record("solo_parent"), tmp_path)
    write_trace(
        TraceRecord(
            run_id="solo_child",
            timestamp="2026-09-16T12:02:00+00:00",
            query="When does the library close?",
            retrieved_chunks=(),
            answer="Saturday 10:00-16:00",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
            recovery={"action": "rewrite", "reason": "first-pass", "source": "policy"},
            recovery_status="applied",
            parent_run_id="solo_parent",
        ),
        tmp_path,
    )
    with _client(tmp_path) as client:
        response = client.delete("/api/traces/solo_child")
        assert response.status_code == 200, response.text
        assert response.json()["also_deleted"] == []
        parent = client.get("/api/traces/solo_parent")
        assert parent.status_code == 200
        assert parent.json()["trace"]["recovery_status"] == "proposed"
        assert parent.json()["child_run_id"] is None

        def fake_execute_recover(application, run_id, action):
            chosen = action or "rewrite"
            path = write_trace(
                TraceRecord(
                    run_id="solo_child_2",
                    timestamp="2026-09-16T12:04:00+00:00",
                    query="When does the library close?",
                    retrieved_chunks=(),
                    answer="Saturday 10:00-16:00",
                    model="none",
                    embedding_model="fake-hash",
                    top_k=4,
                    previous_answer="The library is on the moon.",
                    recovery={"action": chosen, "reason": "first-pass", "source": "policy"},
                    recovery_status="applied",
                    parent_run_id=run_id,
                ),
                application.state.traces_dir,
            )
            return BaselineRunResult(
                run_id="solo_child_2",
                query="When does the library close?",
                answer="Saturday 10:00-16:00",
                retrieval=_empty_retrieval(),
                generation_model="none",
                embedding_model="fake-hash",
                trace_path=path,
            )

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr("swrag.api.app._execute_recover", fake_execute_recover)
        recovered = client.post("/api/runs/solo_parent/recover", json={"action": "rewrite"})
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["run_id"] == "solo_child_2"


def test_loop_confirm_without_api_key_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"question": "When does the library close?", "mode": "loop_confirm"},
        )
        assert response.status_code == 400
        assert "OPENAI_API_KEY" in response.json()["detail"]


def test_recover_without_api_key_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    write_trace(_proposed_record(), tmp_path)
    with _client(tmp_path) as client:
        response = client.post("/api/runs/ui_proposed/recover", json={"action": "rewrite"})
        assert response.status_code == 400
        assert "OPENAI_API_KEY" in response.json()["detail"]


def test_recover_missing_trace_is_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with _client(tmp_path) as client:
        response = client.post("/api/runs/does-not-exist/recover", json={})
        assert response.status_code == 404


def test_recover_rejects_unknown_action_and_unproposed_runs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    write_trace(_proposed_record(), tmp_path)
    write_trace(
        TraceRecord(
            run_id="ui_applied",
            timestamp="2026-09-16T12:01:00+00:00",
            query="When does the library close?",
            retrieved_chunks=(),
            answer="Saturday 10:00-16:00",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
            recovery={"action": "accept", "reason": "no first-pass failure", "source": "policy"},
            recovery_status="applied",
        ),
        tmp_path,
    )
    with _client(tmp_path) as client:
        unknown = client.post("/api/runs/ui_proposed/recover", json={"action": "fix_it"})
        assert unknown.status_code == 400
        not_proposed = client.post("/api/runs/ui_applied/recover", json={"action": "rewrite"})
        assert not_proposed.status_code == 409
        listing = client.get("/api/traces").json()["traces"]
        proposed = next(item for item in listing if item["run_id"] == "ui_proposed")
        assert proposed["recovery_status"] == "proposed"
        assert proposed["child_run_id"] is None


def test_recover_twice_is_409(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    write_trace(_proposed_record(), tmp_path)
    write_trace(
        TraceRecord(
            run_id="ui_child",
            timestamp="2026-09-16T12:02:00+00:00",
            query="When does the library close?",
            retrieved_chunks=(),
            answer="Saturday 10:00-16:00",
            model="none",
            embedding_model="fake-hash",
            top_k=4,
            previous_answer="The library is on the moon.",
            recovery={"action": "rewrite", "reason": "first-pass", "source": "policy"},
            recovery_status="applied",
            parent_run_id="ui_proposed",
        ),
        tmp_path,
    )
    with _client(tmp_path) as client:
        loaded = client.get("/api/traces/ui_proposed")
        assert loaded.status_code == 200
        assert loaded.json()["child_run_id"] == "ui_child"
        listing = client.get("/api/traces").json()["traces"]
        parent = next(item for item in listing if item["run_id"] == "ui_proposed")
        child = next(item for item in listing if item["run_id"] == "ui_child")
        assert parent["child_run_id"] == "ui_child"
        assert child["parent_run_id"] == "ui_proposed"
        response = client.post("/api/runs/ui_proposed/recover", json={"action": "rewrite"})
        assert response.status_code == 409


def test_loop_confirm_then_recover_writes_a_child(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_execute_run(application, question, mode, top_k):
        del top_k
        assert mode == "loop_confirm"
        path = write_trace(_proposed_record("confirm_parent"), application.state.traces_dir)
        return BaselineRunResult(
            run_id="confirm_parent",
            query=question,
            answer="The library is on the moon.",
            retrieval=_empty_retrieval(question),
            generation_model="none",
            embedding_model="fake-hash",
            trace_path=path,
        )

    def fake_execute_recover(application, run_id, action):
        assert run_id == "confirm_parent"
        chosen = action or "rewrite"
        path = write_trace(
            TraceRecord(
                run_id="confirm_child",
                timestamp="2026-09-16T12:03:00+00:00",
                query="When does the library close?",
                retrieved_chunks=(),
                answer="Saturday 10:00-16:00",
                model="none",
                embedding_model="fake-hash",
                top_k=4,
                previous_answer="The library is on the moon.",
                recovery={
                    "action": chosen,
                    "reason": "first-pass evidence insufficient: rewrite query and retrieve again",
                    "source": "policy",
                },
                verification={"outcome": "improved", "rationale": "test"},
                recovery_status="applied",
                parent_run_id=run_id,
            ),
            application.state.traces_dir,
        )
        return BaselineRunResult(
            run_id="confirm_child",
            query="When does the library close?",
            answer="Saturday 10:00-16:00",
            retrieval=_empty_retrieval(),
            generation_model="none",
            embedding_model="fake-hash",
            trace_path=path,
        )

    monkeypatch.setattr("swrag.api.app._execute_run", fake_execute_run)
    monkeypatch.setattr("swrag.api.app._execute_recover", fake_execute_recover)
    with _client(tmp_path) as client:
        first = client.post(
            "/api/runs",
            json={"question": "When does the library close?", "mode": "loop_confirm"},
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["trace"]["recovery_status"] == "proposed"
        assert body["trace"]["previous_answer"] is None
        recover = next(step for step in body["steps"] if step["id"] == "recover")
        assert recover["summary"] == "proposed: rewrite"
        parent_text = (tmp_path / "confirm_parent.json").read_text(encoding="utf-8")
        applied = client.post("/api/runs/confirm_parent/recover", json={"action": "rewrite"})
        assert applied.status_code == 200, applied.text
        child = applied.json()
        assert child["run_id"] == "confirm_child"
        assert child["trace"]["parent_run_id"] == "confirm_parent"
        assert child["trace"]["recovery_status"] == "applied"
        assert child["trace"]["verification"]["outcome"] == "improved"
        assert child["trace"]["previous_answer"] == "The library is on the moon."
        assert (tmp_path / "confirm_parent.json").read_text(encoding="utf-8") == parent_text
        again = client.post("/api/runs/confirm_parent/recover", json={"action": "rewrite"})
        assert again.status_code == 409


def _fake_confirm_run(run_id: str):
    def fake_execute_run(application, question, mode, top_k):
        del top_k
        fake_execute_run.seen.append(mode)
        path = write_trace(_proposed_record(run_id), application.state.traces_dir)
        return BaselineRunResult(
            run_id=run_id,
            query=question,
            answer="The library is on the moon.",
            retrieval=_empty_retrieval(question),
            generation_model="none",
            embedding_model="fake-hash",
            trace_path=path,
        )

    fake_execute_run.seen = []
    return fake_execute_run


def test_omitted_mode_defaults_to_loop_confirm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_execute_run = _fake_confirm_run("omit_parent")
    monkeypatch.setattr("swrag.api.app._execute_run", fake_execute_run)
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"question": "When does the library close?"},
        )
        assert response.status_code == 200, response.text
        assert fake_execute_run.seen == ["loop_confirm"]
        assert response.json()["trace"]["recovery_status"] == "proposed"


def test_explicit_loop_mode_is_still_auto_recover(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_execute_run = _fake_confirm_run("loop_parent")
    monkeypatch.setattr("swrag.api.app._execute_run", fake_execute_run)
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"question": "When does the library close?", "mode": "loop"},
        )
        assert response.status_code == 200, response.text
        assert fake_execute_run.seen == ["loop"]
