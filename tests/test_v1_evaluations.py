"""External evaluation HTTP contract and project-scoped keys. No live OpenAI."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.evaluation.scripted_judge import ScriptedJudge


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        traces_root=tmp_path / "traces-root",
        projects_root=tmp_path / "projects",
    )
    return TestClient(app)


def _scripted(client: TestClient) -> TestClient:
    client.app.state.grounding_judge = ScriptedJudge(
        evidence_sufficient=False, answer_supported=False
    )
    return client


def _create_project_with_key(client: TestClient, name: str) -> tuple[str, str]:
    created = client.post("/api/projects", json={"name": name})
    assert created.status_code == 200, created.text
    project_id = created.json()["project"]["id"]
    minted = client.post(f"/api/projects/{project_id}/keys", json={})
    assert minted.status_code == 200, minted.text
    body = minted.json()
    assert body["key"].startswith("swr_")
    return project_id, body["key"]


def test_dashboard_stays_unauthenticated_and_v1_requires_a_key(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _scripted(client)
        assert client.get("/api/meta").status_code == 200
        assert client.get("/api/traces").status_code == 200
        denied = client.post(
            "/api/v1/evaluations",
            json={"query": "hours?", "answer": "closed", "contexts": []},
        )
        assert denied.status_code == 401


def test_external_evaluation_returns_judge_flags_and_unavailable_actions(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _scripted(client)
        project_id, token = _create_project_with_key(client, "External")
        listed = client.get(f"/api/projects/{project_id}/keys")
        assert listed.status_code == 200
        assert "hash" not in listed.text
        assert token not in listed.text
        keys_file = tmp_path / "projects" / project_id / "keys.json"
        assert keys_file.is_file()
        assert token not in keys_file.read_text(encoding="utf-8")
        response = client.post(
            "/api/v1/evaluations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": "When is the library open on Saturday?",
                "answer": "It is open until midnight.",
                "contexts": [
                    {
                        "chunk_id": "hours::c000",
                        "doc_id": "hours",
                        "title": "Hours",
                        "text": "Saturday 10:00-16:00.",
                        "score": 0.4,
                    }
                ],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["project_id"] == project_id
        assert body["evaluation"]["evidence_sufficient"] is False
        assert body["diagnosis"]["detector"] == "first-pass-runtime"
        assert body["recovery"]["action"] == "rewrite"
        assert body["recovery_status"] == "proposed"
        assert "rewrite" in body["unavailable_actions"]
        assert "expand" in body["unavailable_actions"]
        run_id = body["run_id"]
        fetched = client.get(
            f"/api/v1/evaluations/{run_id}",
            headers={"X-Api-Key": token},
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["run_id"] == run_id
        assert fetched.json()["unavailable_actions"]["rewrite"]


def test_malformed_external_payload_is_400(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _scripted(client)
        _, token = _create_project_with_key(client, "Bad Payload")
        headers = {"Authorization": f"Bearer {token}"}
        missing = client.post(
            "/api/v1/evaluations",
            headers=headers,
            json={"query": "hours?", "answer": "no"},
        )
        assert missing.status_code == 400
        assert "contexts" in missing.json()["detail"]
        huge = client.post(
            "/api/v1/evaluations",
            headers=headers,
            json={
                "query": "hours?",
                "answer": "no",
                "contexts": [{"text": "x" * 4001}],
            },
        )
        assert huge.status_code == 400


def test_revoked_key_stops_working_and_cannot_read_another_project(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _scripted(client)
        project_a, token_a = _create_project_with_key(client, "Alpha Keys")
        project_b, token_b = _create_project_with_key(client, "Beta Keys")
        created = client.post(
            "/api/v1/evaluations",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "query": "Alpha secret question?",
                "answer": "classified",
                "contexts": [{"text": "Alpha only.", "doc_id": "alpha-doc"}],
            },
        )
        assert created.status_code == 200, created.text
        run_id = created.json()["run_id"]
        leaked = client.get(
            f"/api/v1/evaluations/{run_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert leaked.status_code == 404
        own = client.get(
            f"/api/v1/evaluations/{run_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert own.status_code == 200
        key_id = client.get(f"/api/projects/{project_a}/keys").json()["keys"][0]["id"]
        revoked = client.delete(f"/api/projects/{project_a}/keys/{key_id}")
        assert revoked.status_code == 200
        dead = client.get(
            f"/api/v1/evaluations/{run_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert dead.status_code == 401
        builtin = client.post("/api/projects/harbor/keys", json={})
        assert builtin.status_code == 400
        del project_b
