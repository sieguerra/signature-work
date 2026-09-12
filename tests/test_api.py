"""HTTP adapter tests. No live OpenAI calls."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.tracing.tracer import write_trace
from swrag.types import TraceRecord

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
        assert "answers" not in saved


def test_index_page_and_assets_are_served(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Trace explorer" in page.text
        assert "delete-all-runs" in page.text
        css = client.get("/static/styles.css")
        assert css.status_code == 200
        assert "--bg:" in css.text
        js = client.get("/static/app.js")
        assert js.status_code == 200
        assert "example-chips" in js.text
        assert "run-delete" in js.text
        assert "deleteAllRuns" in js.text
        assert "switchCorpus" in js.text
        assert 'id="corpus"' in page.text


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
