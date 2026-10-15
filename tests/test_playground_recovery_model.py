"""Issue #143 item 2: recovery in an editable system uses that system's model. No live calls."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from swrag.api import app as app_module
from swrag.api.app import create_app
from swrag.config import ProviderConfig
from swrag.recovery.regenerate import _REGENERATE_PROMPT, ConstrainedRegenerator, compose_regenerate_prompt

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"
CONFIG = ProviderConfig(base_url=None, chat_model="env-model", embedding_model="e")


def _actors(application) -> dict[str, object]:
    actors = app_module._recovery_actors(application)
    return {name: getattr(actor, "model_name") for name, actor in actors.items()} | {
        "instructions": actors["regenerator"].instructions,
        "generator": app_module._generator_for(application).model_name,
    }


def test_an_editable_system_recovers_on_its_own_model_and_instructions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-real")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "env-model")
    app = create_app(traces_root=tmp_path / "traces", projects_root=tmp_path / "projects")
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Play"}).json()["active_id"]
        saved = client.patch(
            f"/api/projects/{project_id}/config",
            json={"instructions": "Answer in one sentence.", "chat_model": "gpt-4o", "top_k": 4},
        )
        assert saved.status_code == 200, saved.text
        got = _actors(app)
    assert got == {
        "judge": "gpt-4o",
        "regenerator": "gpt-4o",
        "rewriter": "gpt-4o",
        "instructions": "Answer in one sentence.",
        "generator": "gpt-4o",
    }


def test_a_built_in_corpus_keeps_the_environment_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-real")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "env-model")
    app = create_app(corpus_dir=CORPUS, traces_dir=tmp_path)
    with TestClient(app):
        got = _actors(app)
    assert {got[name] for name in ("judge", "regenerator", "rewriter", "generator")} == {"env-model"}
    assert got["instructions"] == ""


def test_the_regenerate_prompt_is_unchanged_without_instructions() -> None:
    assert compose_regenerate_prompt("") == _REGENERATE_PROMPT
    assert compose_regenerate_prompt("  \n") == _REGENERATE_PROMPT
    composed = compose_regenerate_prompt("Answer in one sentence.")
    assert composed.startswith(_REGENERATE_PROMPT) and composed.endswith("Answer in one sentence.")


def test_the_regenerator_sends_the_composed_prompt() -> None:
    sent: list[dict] = []

    class _Completions:
        def create(self, **kwargs):
            sent.append(kwargs)
            message = SimpleNamespace(content="New answer.")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    regenerator = ConstrainedRegenerator(model="m", client=client, config=CONFIG, instructions="Be brief.")
    retrieval = SimpleNamespace(chunks=[])
    regenerator.regenerate(question="q", retrieval=retrieval, previous_answer="old")
    assert sent[0]["model"] == "m"
    assert sent[0]["messages"][0]["content"] == compose_regenerate_prompt("Be brief.")
