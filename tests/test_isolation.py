"""Project isolation across API, traces, documents, and the index cache.

Issue #80. These tests use an unlocked traces root so each workspace writes
under ``traces_root / corpus_id``. Passing ``traces_dir=`` would hide leaks.
No live OpenAI.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from swrag.api.app import _index_for, create_app
from swrag.tracing.tracer import write_trace
from swrag.types import TraceRecord


def _unlocked(tmp_path: Path) -> TestClient:
    app = create_app(
        traces_root=tmp_path / "traces-root",
        projects_root=tmp_path / "projects",
    )
    return TestClient(app)


def test_index_cache_key_includes_corpus_and_directory(tmp_path: Path) -> None:
    alpha = tmp_path / "alpha-docs"
    beta = tmp_path / "beta-docs"
    alpha.mkdir()
    beta.mkdir()
    (alpha / "a.txt").write_text("ALPHASECRETTOKEN Saturday hours.\n", encoding="utf-8")
    (beta / "b.txt").write_text("BETASECRETTOKEN Tuesday hours.\n", encoding="utf-8")
    app = create_app(
        traces_root=tmp_path / "traces-root",
        projects_root=tmp_path / "projects",
    )
    with TestClient(app) as client:
        application = client.app
        application.state.indexes = {}
        application.state.writable = True
        application.state.corpus_id = "alpha"
        application.state.corpus_dir = alpha
        first = _index_for(application, retrieve_only=True)
        application.state.corpus_id = "beta"
        application.state.corpus_dir = beta
        second = _index_for(application, retrieve_only=True)
        assert first is not second
        leaked = second.search("ALPHASECRETTOKEN", top_k=4)
        assert not any("ALPHASECRETTOKEN" in scored.chunk.text for scored in leaked.chunks)
        keys = set(application.state.indexes)
        assert any(item[0] == "alpha" for item in keys)
        assert any(item[0] == "beta" for item in keys)
        assert any(str(alpha.resolve()) in item for item in keys)


def test_project_a_cannot_read_delete_or_recover_project_b_runs(tmp_path: Path) -> None:
    with _unlocked(tmp_path) as client:
        first = client.post("/api/projects", json={"name": "Iso Alpha"})
        assert first.status_code == 200, first.text
        alpha_id = first.json()["project"]["id"]
        uploaded = client.post(
            "/api/documents",
            files={
                "file": (
                    "alpha.txt",
                    b"ALPHASECRETTOKEN the alpha library is open Saturday.\n",
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 200, uploaded.text
        alpha_run = client.post(
            "/api/runs",
            json={"question": "ALPHASECRETTOKEN Saturday?", "mode": "retrieve_only"},
        )
        assert alpha_run.status_code == 200, alpha_run.text
        alpha_run_id = alpha_run.json()["run_id"]
        alpha_chunks = alpha_run.json()["trace"]["retrieved_chunks"]
        assert any("ALPHASECRETTOKEN" in (chunk.get("text") or "") for chunk in alpha_chunks)

        second = client.post("/api/projects", json={"name": "Iso Beta"})
        assert second.status_code == 200, second.text
        beta_id = second.json()["project"]["id"]
        assert beta_id != alpha_id
        docs = client.get("/api/documents").json()["documents"]
        assert docs == []
        leaked_docs = [item["name"] for item in docs]
        assert "alpha.txt" not in leaked_docs

        client.post(
            "/api/documents",
            files={
                "file": (
                    "beta.txt",
                    b"BETASECRETTOKEN the beta hangar is closed Tuesday.\n",
                    "text/plain",
                )
            },
        )
        beta_run = client.post(
            "/api/runs",
            json={"question": "BETASECRETTOKEN Tuesday?", "mode": "retrieve_only"},
        )
        assert beta_run.status_code == 200, beta_run.text
        beta_chunks = beta_run.json()["trace"]["retrieved_chunks"]
        assert any("BETASECRETTOKEN" in (chunk.get("text") or "") for chunk in beta_chunks)
        assert not any("ALPHASECRETTOKEN" in (chunk.get("text") or "") for chunk in beta_chunks)

        listing = client.get("/api/traces").json()["traces"]
        listed_ids = {item["run_id"] for item in listing}
        assert alpha_run_id not in listed_ids
        guessed = client.get(f"/api/traces/{alpha_run_id}")
        assert guessed.status_code == 404
        deleted = client.delete(f"/api/traces/{alpha_run_id}")
        assert deleted.status_code == 404
        recovered = client.post(f"/api/runs/{alpha_run_id}/recover", json={})
        assert recovered.status_code == 404

        traces_root = tmp_path / "traces-root"
        write_trace(
            TraceRecord(
                run_id="beta_proposed",
                timestamp="2026-09-21T00:00:00+00:00",
                query="ignored",
                retrieved_chunks=(),
                answer="guess",
                model="none",
                embedding_model="fake-hash",
                top_k=4,
                recovery={"action": "rewrite", "reason": "insufficient"},
                recovery_status="proposed",
            ),
            traces_root / beta_id,
        )
        switched = client.post("/api/corpus", json={"id": alpha_id})
        assert switched.status_code == 200, switched.text
        assert client.get("/api/traces/beta_proposed").status_code == 404
        assert client.delete("/api/traces/beta_proposed").status_code == 404
        assert client.post("/api/runs/beta_proposed/recover", json={}).status_code == 404
        alpha_again = client.post(
            "/api/runs",
            json={"question": "ALPHASECRETTOKEN Saturday?", "mode": "retrieve_only"},
        )
        assert alpha_again.status_code == 200, alpha_again.text
        texts = [chunk.get("text") or "" for chunk in alpha_again.json()["trace"]["retrieved_chunks"]]
        assert any("ALPHASECRETTOKEN" in text for text in texts)
        assert not any("BETASECRETTOKEN" in text for text in texts)
        assert (traces_root / alpha_id / f"{alpha_run_id}.json").is_file()
        assert not (traces_root / beta_id / f"{alpha_run_id}.json").exists()


def test_locked_shared_traces_dir_is_not_the_isolation_default(tmp_path: Path) -> None:
    """A client that does not lock traces_dir must isolate by corpus id."""
    app = create_app(
        traces_root=tmp_path / "traces-root",
        projects_root=tmp_path / "projects",
    )
    with TestClient(app) as client:
        assert client.app.state.traces_locked is False
        created = client.post("/api/projects", json={"name": "Lock Check"})
        assert created.status_code == 200
        project_id = created.json()["project"]["id"]
        meta = client.get("/api/meta").json()
        assert meta["traces_dir"].endswith(project_id)
        assert meta["traces_dir"] != str(tmp_path / "traces-root")
