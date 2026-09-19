"""Runtime projects and document uploads. No live OpenAI."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.projects import create_project, safe_upload_name

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"
FIXTURE_PDF = ROOT / "tests" / "fixtures" / "two-page-notice.pdf"


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        corpus_dir=CORPUS,
        traces_dir=tmp_path / "traces",
        traces_root=tmp_path / "traces-root",
        projects_root=tmp_path / "projects",
    )
    return TestClient(app)


def test_safe_upload_name_rejects_paths() -> None:
    try:
        safe_upload_name("../secret.txt")
        assert False, "should have rejected"
    except ValueError:
        pass
    try:
        safe_upload_name("note.exe")
        assert False, "should have rejected"
    except ValueError:
        pass
    assert safe_upload_name("hours.txt") == "hours.txt"


def test_create_project_is_writable_and_isolated(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post("/api/projects", json={"name": "Harbor Demo"})
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["project"]["writable"] is True
        assert body["project"]["id"] == "harbor-demo"
        listing = client.get("/api/corpora").json()["corpora"]
        ids = [item["id"] for item in listing]
        assert "harbor" in ids
        assert "harbor-demo" in ids
        meta = client.get("/api/meta").json()
        assert meta["writable"] is True
        assert meta["corpus_id"] == "harbor-demo"


def test_builtin_corpus_rejects_uploads(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        blocked = client.post(
            "/api/documents",
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
        assert blocked.status_code == 400
        assert "read-only" in blocked.json()["detail"]


def test_project_upload_and_retrieve(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post("/api/projects", json={"name": "Uploads"})
        uploaded = client.post(
            "/api/documents",
            files={"file": ("library.txt", b"The library is open Saturday 10:00-16:00.\n", "text/plain")},
        )
        assert uploaded.status_code == 200, uploaded.text
        names = [item["name"] for item in uploaded.json()["documents"]]
        assert names == ["library.txt"]
        pdf = client.post(
            "/api/documents",
            files={"file": ("two-page-notice.pdf", FIXTURE_PDF.read_bytes(), "application/pdf")},
        )
        assert pdf.status_code == 200, pdf.text
        run = client.post(
            "/api/runs",
            json={"question": "When is the library open on Saturday?", "mode": "retrieve_only"},
        )
        assert run.status_code == 200, run.text
        chunks = run.json()["trace"]["retrieved_chunks"]
        assert chunks
        assert any("library" in (chunk.get("doc_id") or "") for chunk in chunks)
        deleted = client.delete("/api/documents/library.txt")
        assert deleted.status_code == 200
        remaining = [item["name"] for item in deleted.json()["documents"]]
        assert "library.txt" not in remaining


def test_cannot_delete_builtin_as_a_project(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.delete("/api/projects/harbor")
        assert response.status_code == 400


def test_projects_do_not_share_documents(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        first = client.post("/api/projects", json={"name": "Alpha"})
        assert first.status_code == 200
        uploaded = client.post(
            "/api/documents",
            files={"file": ("alpha.txt", b"Alpha only hours Saturday.\n", "text/plain")},
        )
        assert uploaded.status_code == 200
        second = client.post("/api/projects", json={"name": "Beta"})
        assert second.status_code == 200
        docs = client.get("/api/documents").json()["documents"]
        assert docs == []
        leaked = client.get("/api/documents").json()
        names = [item["name"] for item in leaked["documents"]]
        assert "alpha.txt" not in names


def test_project_config_round_trip_and_trace_snapshot(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post("/api/projects", json={"name": "Configured"})
        assert created.status_code == 200
        project_id = created.json()["active_id"]
        saved = client.patch(
            f"/api/projects/{project_id}/config",
            json={
                "instructions": "Prefer Saturday hours.",
                "chat_model": "gpt-4o-mini",
                "top_k": 2,
            },
        )
        assert saved.status_code == 200, saved.text
        config = saved.json()["project"]["config"]
        assert config["instructions"] == "Prefer Saturday hours."
        assert config["top_k"] == 2
        meta = client.get("/api/meta").json()
        assert "api_key" not in meta
        assert meta["agent_config"]["instructions"] == "Prefer Saturday hours."
        client.post(
            "/api/documents",
            files={"file": ("hours.txt", b"Saturday 10:00-16:00.\n", "text/plain")},
        )
        run = client.post(
            "/api/runs",
            json={"question": "When is it open Saturday?", "mode": "retrieve_only"},
        )
        assert run.status_code == 200, run.text
        snapshot = run.json()["trace"]["agent_config"]
        assert snapshot["instructions"] == "Prefer Saturday hours."
        assert snapshot["chat_model"] == "gpt-4o-mini"
        assert snapshot["top_k"] == 2
        blocked = client.patch(
            f"/api/projects/{project_id}/config",
            json={"instructions": "", "chat_model": "not-a-model", "top_k": 4},
        )
        assert blocked.status_code == 400


def test_corrupt_pdf_upload_is_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post("/api/projects", json={"name": "Pdf Check"})
        response = client.post(
            "/api/documents",
            files={"file": ("broken.pdf", b"%PDF-1.4 not a real file", "application/pdf")},
        )
        assert response.status_code == 400
        docs = client.get("/api/documents").json()["documents"]
        assert docs == []


def test_create_project_helper_writes_documents_dir(tmp_path: Path) -> None:
    entry = create_project(
        "Local",
        root=ROOT,
        traces_root=tmp_path / "out",
        base=tmp_path / "projects",
    )
    assert entry.writable is True
    assert (tmp_path / "projects" / entry.id / "documents").is_dir()
