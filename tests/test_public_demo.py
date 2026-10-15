"""Public demo mode (GROUNDLOOP_DEMO=1). No live OpenAI calls."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.api.public import RunBudget, is_blocked, is_run, scrub

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"
QUESTION = {"question": "When is the Harbor Institute Library open on Saturday?", "mode": "retrieve_only"}


@pytest.fixture
def demo_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROUNDLOOP_DEMO", "1")
    monkeypatch.setenv("GROUNDLOOP_DAILY_RUNS", "2")
    with TestClient(create_app(corpus_dir=CORPUS, traces_dir=tmp_path)) as client:
        yield client


def test_every_change_is_refused(demo_client: TestClient) -> None:
    calls = [
        ("post", "/api/corpus", {"json": {"id": "dku"}}),
        ("post", "/api/projects", {"json": {"name": "x"}}),
        ("delete", "/api/projects/anything", {}),
        ("patch", "/api/projects/anything/config", {"json": {}}),
        ("post", "/api/projects/anything/keys", {"json": {}}),
        ("delete", "/api/traces", {}),
        ("delete", "/api/traces/some-run", {}),
        ("post", "/api/traces/some-run/quality", {}),
        ("delete", "/api/documents/note.txt", {}),
    ]
    for method, path, kwargs in calls:
        response = getattr(demo_client, method)(path, **kwargs)
        assert response.status_code == 403, (method, path, response.status_code)
        assert "read-only" in response.json()["detail"]


def test_live_runs_stop_at_the_daily_cap(demo_client: TestClient) -> None:
    assert demo_client.get("/api/meta").json()["demo"] == {"enabled": True, "daily_runs": 2, "runs_left": 2}
    assert demo_client.post("/api/runs", json=QUESTION).status_code == 200
    assert demo_client.post("/api/runs/stream", json=QUESTION).status_code == 200
    capped = demo_client.post("/api/runs", json=QUESTION)
    assert capped.status_code == 429
    assert "live runs for today" in capped.json()["detail"]
    assert demo_client.get("/api/meta").json()["demo"]["runs_left"] == 0


def test_responses_carry_no_local_paths_or_provider_endpoint(demo_client: TestClient) -> None:
    meta = demo_client.get("/api/meta").json()
    assert "corpus_dir" not in meta and "traces_dir" not in meta and "base_url" not in meta
    run = demo_client.post("/api/runs", json=QUESTION).json()
    assert str(ROOT) not in str(run)
    assert "base_url" not in str(run)


def test_the_picker_only_lists_the_pinned_system(demo_client: TestClient) -> None:
    payload = demo_client.get("/api/corpora").json()
    assert [item["id"] for item in payload["corpora"]] == [payload["active_id"]]


def test_demo_mode_is_off_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROUNDLOOP_DEMO", raising=False)
    with TestClient(create_app(corpus_dir=CORPUS, traces_dir=tmp_path)) as client:
        assert client.get("/api/meta").json()["demo"]["enabled"] is False
        assert client.delete("/api/traces").status_code != 403


def test_rules_and_helpers() -> None:
    assert is_blocked("DELETE", "/api/traces/x") and not is_blocked("GET", "/api/traces/x")
    assert is_blocked("POST", "/api/traces/x/quality") and not is_blocked("GET", "/api/traces/x/quality")
    assert is_run("POST", "/api/runs/stream") and is_run("POST", "/api/runs/abc/recover") and not is_run("GET", "/api/runs")
    budget = RunBudget(1)
    assert budget.take() and not budget.take() and budget.left() == 0
    assert scrub({"a": "/home/u/repo/x.txt", "base_url": "https://p", "n": [{"traces_dir": "/x"}]}, "/home/u/repo") == {
        "a": "x.txt",
        "n": [{}],
    }


def test_deployment_settings_come_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "harbor").mkdir()
    monkeypatch.setenv("GROUNDLOOP_TRACES_ROOT", str(tmp_path))
    monkeypatch.setenv("GROUNDLOOP_SYSTEM", "harbor")
    with TestClient(create_app()) as client:
        meta = client.get("/api/meta").json()
    assert meta["corpus_id"] == "harbor"
    assert meta["traces_dir"] == str(tmp_path / "harbor")


def test_demo_blocks_external_evaluations_and_hides_route_docs(demo_client: TestClient) -> None:
    response = demo_client.post("/api/v1/evaluations", json={"query": "q", "answer": "a", "contexts": [{"text": "t"}]})
    assert response.status_code == 403
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert demo_client.get(path).status_code == 404


def test_rejected_requests_do_not_use_up_the_demo_budget(demo_client: TestClient) -> None:
    assert demo_client.post("/api/runs", json={}).status_code == 422
    assert demo_client.post("/api/runs", json={"question": "q", "mode": "nope"}).status_code == 400
    assert demo_client.get("/api/meta").json()["demo"]["runs_left"] == 2
