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
        css = client.get("/static/styles.css")
        assert css.status_code == 200
        assert "--bg:" in css.text
        js = client.get("/static/app.js")
        assert js.status_code == 200
        assert "example-chips" in js.text
