"""Per-stage timing and the streaming run endpoint. No live OpenAI calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.tracing import progress

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"


def test_stages_are_recorded_with_offsets_and_reported_live() -> None:
    events: list[dict] = []
    with progress.recording(events.append) as recorder:
        with progress.stage("retrieve", top_k=4):
            pass
        with progress.attempt(0), progress.stage("recover", action="regenerate"):
            with progress.stage("generate"):
                pass
        snapshot = progress.snapshot()

    assert [item["stage"] for item in recorder.stages] == ["retrieve", "generate", "recover"]
    assert snapshot == recorder.snapshot()
    retrieve, generate, recover = recorder.stages
    assert retrieve["attempt"] is None and retrieve["top_k"] == 4
    assert generate["attempt"] == 0 and recover["action"] == "regenerate"
    assert all(item["duration_ms"] >= 0 and item["status"] == "ok" for item in recorder.stages)
    assert recover["started_ms"] <= generate["started_ms"]
    assert [(e["type"], e["stage"]) for e in events] == [
        ("stage_start", "retrieve"),
        ("stage_end", "retrieve"),
        ("stage_start", "recover"),
        ("stage_start", "generate"),
        ("stage_end", "generate"),
        ("stage_end", "recover"),
    ]


def test_a_failing_stage_is_marked_and_the_error_still_raises() -> None:
    with progress.recording() as recorder:
        with pytest.raises(RuntimeError):
            with progress.stage("judge"):
                raise RuntimeError("model down")
    assert recorder.stages[0]["status"] == "error"


def test_outside_a_recording_stages_do_nothing() -> None:
    with progress.stage("retrieve"):
        pass
    assert progress.snapshot() is None


def test_a_broken_listener_does_not_fail_the_run() -> None:
    def boom(_event: dict) -> None:
        raise BrokenPipeError

    with progress.recording(boom) as recorder:
        with progress.stage("retrieve"):
            pass
        with progress.stage("generate"):
            pass
    assert [item["stage"] for item in recorder.stages] == ["retrieve", "generate"]


def _sse(text: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


def test_streaming_run_reports_stages_then_the_finished_run(tmp_path: Path) -> None:
    with TestClient(create_app(corpus_dir=CORPUS, traces_dir=tmp_path)) as client:
        response = client.post(
            "/api/runs/stream",
            json={"question": "When is the Harbor Institute Library open on Saturday?", "mode": "retrieve_only"},
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _sse(response.text)

    assert [(e["type"], e.get("stage")) for e in events[:2]] == [("stage_start", "retrieve"), ("stage_end", "retrieve")]
    done = events[-1]
    assert done["type"] == "done"
    assert done["run"]["run_id"]

    saved = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert [item["stage"] for item in saved["stage_timings"]] == ["retrieve"]
    assert saved["stage_timings"][0]["duration_ms"] >= 0


def test_streaming_run_validates_like_the_plain_endpoint(tmp_path: Path) -> None:
    with TestClient(create_app(corpus_dir=CORPUS, traces_dir=tmp_path)) as client:
        response = client.post("/api/runs/stream", json={"question": "   ", "mode": "retrieve_only"})
        assert response.status_code == 400


def test_plain_run_also_saves_stage_timings(tmp_path: Path) -> None:
    with TestClient(create_app(corpus_dir=CORPUS, traces_dir=tmp_path)) as client:
        response = client.post(
            "/api/runs",
            json={"question": "When is the Harbor Institute Library open on Saturday?", "mode": "retrieve_only"},
        )
        assert response.status_code == 200, response.text
    saved = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert saved["stage_timings"][0]["stage"] == "retrieve"
