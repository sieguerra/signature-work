"""HTTP adapter over the callable RAG core. Owns no retrieval or recovery logic."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from swrag.api.store import delete_all_traces, delete_trace, eval_counts, list_traces, load_trace
from swrag.config import load_provider_config
from swrag.corpus_registry import (
    CorpusEntry,
    assert_corpus_readable,
    default_corpus_id,
    get_corpus,
    load_registry,
    traces_dir_for,
)
from swrag.orchestration.loop import run_with_recovery
from swrag.pipeline.baseline import build_corpus_index, run_query
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.tracing.steps import trace_to_steps

MODES = frozenset({"loop", "baseline", "retrieve_only"})


class RunRequest(BaseModel):
    question: str = Field(min_length=1)
    mode: str = "loop"
    top_k: int = Field(default=4, ge=1, le=20)


class CorpusSelectRequest(BaseModel):
    id: str = Field(min_length=1)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def web_dir() -> Path:
    return repo_root() / "web"


def create_app(
    *,
    corpus_dir: str | Path | None = None,
    traces_dir: str | Path | None = None,
    traces_root: str | Path | None = None,
    corpus_id: str | None = None,
) -> FastAPI:
    """Build the UI server. The RAG packages stay importable without FastAPI."""
    load_dotenv(repo_root() / ".env")
    root = repo_root()
    resolved_traces_root = Path(traces_root) if traces_root else root / "experiments" / "output"

    if corpus_dir is not None:
        entry = _entry_for_explicit_dir(Path(corpus_dir), root)
        traces_locked = True
        resolved_traces = Path(traces_dir) if traces_dir else traces_dir_for(entry.id, resolved_traces_root)
    else:
        entry = get_corpus(corpus_id or default_corpus_id(root=root), root=root)
        traces_locked = traces_dir is not None
        resolved_traces = Path(traces_dir) if traces_dir else traces_dir_for(entry.id, resolved_traces_root)

    static = web_dir()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.repo_root = root
        app.state.traces_root = resolved_traces_root
        app.state.traces_locked = traces_locked
        app.state.indexes = {}
        app.state.index_lock = threading.RLock()
        _activate(app, entry, resolved_traces)
        yield

    application = FastAPI(title="swrag trace explorer", lifespan=lifespan)

    @application.get("/api/meta")
    def meta() -> dict[str, Any]:
        config = load_provider_config()
        payload = config.as_trace_payload()
        payload["corpus_dir"] = str(application.state.corpus_dir)
        payload["traces_dir"] = str(application.state.traces_dir)
        payload["corpus_id"] = application.state.corpus_id
        payload["corpus_label"] = application.state.corpus_label
        payload["corpus_industry"] = application.state.corpus_industry
        payload["examples"] = list(application.state.examples)
        payload["doc_count"] = application.state.doc_count
        return payload

    @application.get("/api/corpora")
    def corpora() -> dict[str, Any]:
        return {
            "active_id": application.state.corpus_id,
            "corpora": [item.as_payload() for item in load_registry(root=application.state.repo_root)],
        }

    @application.post("/api/corpus")
    def select_corpus(body: CorpusSelectRequest) -> dict[str, Any]:
        try:
            selected = get_corpus(body.id.strip(), root=application.state.repo_root)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"unknown corpus {body.id!r}") from error
        try:
            assert_corpus_readable(selected)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        next_traces = (
            application.state.traces_dir
            if application.state.traces_locked
            else traces_dir_for(selected.id, application.state.traces_root)
        )
        with application.state.index_lock:
            _activate(application, selected, next_traces)
        return {
            "active_id": application.state.corpus_id,
            "corpus": selected.as_payload(),
            "traces_dir": str(application.state.traces_dir),
        }

    @application.get("/api/eval")
    def eval_panel() -> dict[str, Any]:
        return eval_counts(application.state.traces_dir)

    @application.get("/api/traces")
    def traces() -> dict[str, Any]:
        return {"traces": list_traces(application.state.traces_dir)}

    @application.delete("/api/traces")
    def remove_all_traces() -> dict[str, Any]:
        return {"deleted": delete_all_traces(application.state.traces_dir)}

    @application.get("/api/traces/{run_id}")
    def get_trace(run_id: str) -> dict[str, Any]:
        payload = load_trace(application.state.traces_dir, run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return {"trace": payload, "steps": trace_to_steps(payload)}

    @application.delete("/api/traces/{run_id}")
    def remove_trace(run_id: str) -> dict[str, Any]:
        if not delete_trace(application.state.traces_dir, run_id):
            raise HTTPException(status_code=404, detail="trace not found")
        return {"deleted": run_id}

    @application.post("/api/runs")
    def create_run(body: RunRequest) -> dict[str, Any]:
        question = body.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="question is required")
        if body.mode not in MODES:
            raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(MODES)}")
        retrieve_only = body.mode == "retrieve_only"
        if not retrieve_only and not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="OPENAI_API_KEY is not set. Use retrieve-only mode, or add a key to .env.",
            )
        try:
            with application.state.index_lock:
                result = _execute_run(application, question, body.mode, body.top_k)
        except FileExistsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

        payload = load_trace(application.state.traces_dir, result.run_id)
        if payload is None:
            raise HTTPException(status_code=500, detail="run finished but the trace was not readable")
        return {
            "run_id": result.run_id,
            "answer": result.answer,
            "trace": payload,
            "steps": trace_to_steps(payload),
        }

    if static.is_dir():
        @application.get("/")
        def index() -> FileResponse:
            return FileResponse(static / "index.html")

        application.mount("/static", StaticFiles(directory=static), name="static")

    return application


def _activate(application: FastAPI, entry: CorpusEntry, traces: Path) -> None:
    traces.mkdir(parents=True, exist_ok=True)
    application.state.corpus_id = entry.id
    application.state.corpus_label = entry.label
    application.state.corpus_industry = entry.industry
    application.state.corpus_dir = entry.corpus_dir
    application.state.examples = entry.examples
    application.state.doc_count = entry.doc_count
    application.state.traces_dir = Path(traces)
    application.state.indexes = {}


def _entry_for_explicit_dir(corpus_dir: Path, root: Path) -> CorpusEntry:
    resolved = corpus_dir.resolve()
    for entry in load_registry(root=root):
        if entry.corpus_dir.resolve() == resolved:
            return entry
    return CorpusEntry(
        id="custom",
        label="Custom corpus",
        industry="",
        group="Custom",
        corpus_dir=resolved,
        gold_path=None,
        examples=(),
        fictional=True,
    )


def _execute_run(application: FastAPI, question: str, mode: str, top_k: int):
    retrieve_only = mode == "retrieve_only"
    index = _index_for(application, retrieve_only=retrieve_only)
    kwargs: dict[str, Any] = {
        "corpus_dir": application.state.corpus_dir,
        "output_dir": application.state.traces_dir,
        "top_k": top_k,
        "index": index,
        "generate": not retrieve_only,
        "embedder": FakeEmbedder() if retrieve_only else None,
    }
    if mode == "loop":
        from swrag.evaluation.llm_judge import LLMJudge

        kwargs["judge"] = LLMJudge()
        return run_with_recovery(question, **kwargs)
    return run_query(question, **kwargs)


def _index_for(application: FastAPI, *, retrieve_only: bool):
    key = (application.state.corpus_id, "fake" if retrieve_only else "openai")
    with application.state.index_lock:
        cached = application.state.indexes.get(key)
        if cached is not None:
            return cached
        embedder = FakeEmbedder() if retrieve_only else None
        index = build_corpus_index(application.state.corpus_dir, embedder)
        application.state.indexes[key] = index
        return index


app = create_app()
