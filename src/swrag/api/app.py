"""HTTP adapter over the callable RAG core. Owns no retrieval or recovery logic."""

from __future__ import annotations

import json
import os
import queue
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from swrag.api.credentials import create_api_key, list_api_keys, revoke_api_key
from swrag.api.public import READ_ONLY_DETAIL, RunBudget, demo_enabled, is_blocked, is_run, scrub
from swrag.api.overview import logical_run_history, overview_for_traces
from swrag.api.store import (
    delete_all_traces,
    delete_trace,
    eval_counts,
    find_child_run_id,
    list_traces,
    load_quality,
    load_trace,
    save_quality,
)
from swrag.api.v1 import build_v1_router
from swrag.config import load_provider_config
from swrag.tracing import progress
from swrag.usage import capture_usage
from swrag.evaluation.quality_metrics import score_trace
from swrag.corpus_registry import (
    CorpusEntry,
    assert_corpus_readable,
    default_corpus_id,
    traces_dir_for,
)
from swrag.generation.openai_generator import OpenAIGenerator
from swrag.ingestion.loader import corpus_file_count
from swrag.orchestration.loop import RecoveryNotApplicable, apply_recovery, run_first_pass, run_with_recovery
from swrag.pipeline.baseline import build_corpus_index, run_query
from swrag.projects import (
    MAX_UPLOAD_BYTES,
    create_project,
    delete_project,
    get_workspace,
    list_documents,
    list_workspaces,
    read_document_text,
    safe_upload_name,
    update_project_config,
    validate_uploaded_file,
)
from swrag.recovery.policy import ACTIONS, resolve_product_policy
from swrag.usage import estimated_list_cost
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.retrieval.memory_index import InMemoryIndex
from swrag.tracing.steps import trace_to_steps

MODES = frozenset({"loop", "loop_confirm", "baseline", "retrieve_only"})


class RunRequest(BaseModel):
    question: str = Field(min_length=1)
    mode: str = "loop_confirm"
    top_k: int = Field(default=4, ge=1, le=20)
    recovery_policy: str | None = None


class RecoverRequest(BaseModel):
    action: str | None = None


class CorpusSelectRequest(BaseModel):
    id: str = Field(min_length=1)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ProjectConfigRequest(BaseModel):
    instructions: str = ""
    chat_model: str = "gpt-4o-mini"
    top_k: int = Field(default=4, ge=1, le=20)
    behavior: dict[str, Any] | None = None
    recovery_policy: str | None = None


class ProjectKeyCreateRequest(BaseModel):
    scope: str = "evaluations"


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
    projects_root: str | Path | None = None,
) -> FastAPI:
    """Build the UI server. The RAG packages stay importable without FastAPI."""
    load_dotenv(repo_root() / ".env")
    root = repo_root()
    # Deployments point these at committed demo data (see render.yaml).
    traces_root = traces_root or os.environ.get("GROUNDLOOP_TRACES_ROOT") or None
    corpus_id = corpus_id or os.environ.get("GROUNDLOOP_SYSTEM") or None
    if traces_root is not None and not Path(traces_root).is_absolute():
        traces_root = root / traces_root
    resolved_traces_root = Path(traces_root) if traces_root else root / "experiments" / "output"
    resolved_projects_root = Path(projects_root) if projects_root else root / "experiments" / "projects"

    if corpus_dir is not None:
        entry = _entry_for_explicit_dir(Path(corpus_dir), root)
        traces_locked = True
        resolved_traces = Path(traces_dir) if traces_dir else traces_dir_for(entry.id, resolved_traces_root)
    else:
        entry = get_workspace(
            corpus_id or default_corpus_id(root=root),
            root=root,
            traces_root=resolved_traces_root,
            base=resolved_projects_root,
        )
        traces_locked = traces_dir is not None
        resolved_traces = Path(traces_dir) if traces_dir else traces_dir_for(entry.id, resolved_traces_root)

    static = web_dir()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.repo_root = root
        app.state.traces_root = resolved_traces_root
        app.state.projects_root = resolved_projects_root
        app.state.traces_locked = traces_locked
        app.state.indexes = {}
        app.state.index_lock = threading.RLock()
        if not hasattr(app.state, "quality_scorer"):
            app.state.quality_scorer = _default_quality_scorer
        _activate(app, entry, resolved_traces)
        yield

    application = FastAPI(title="Groundloop", lifespan=lifespan)
    application.state.demo = demo_enabled()
    application.state.run_budget = RunBudget.from_env()

    @application.middleware("http")
    async def public_demo(request: Request, call_next):
        """Gate the API for a shared public deployment (GROUNDLOOP_DEMO=1)."""
        if not application.state.demo:
            return await call_next(request)
        method, path = request.method, request.url.path
        if is_blocked(method, path):
            return JSONResponse(status_code=403, content={"detail": READ_ONLY_DETAIL})
        if is_run(method, path) and not application.state.run_budget.take():
            per_day = application.state.run_budget.per_day
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"The public demo has used its {per_day} live runs for today. "
                    "Browse the recorded runs, or come back tomorrow."
                },
            )
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if path.startswith("/api/") and content_type.startswith("application/json"):
            body = b"".join([chunk async for chunk in response.body_iterator])
            data = scrub(json.loads(body or b"null"), str(repo_root()))
            return JSONResponse(content=data, status_code=response.status_code)
        return response

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
        payload["writable"] = bool(application.state.writable)
        payload["agent_config"] = application.state.agent_config
        payload["demo"] = {
            "enabled": bool(application.state.demo),
            "daily_runs": application.state.run_budget.per_day if application.state.demo else None,
            "runs_left": application.state.run_budget.left() if application.state.demo else None,
        }
        return payload

    def _workspace_kwargs() -> dict[str, Path]:
        return {
            "root": application.state.repo_root,
            "traces_root": application.state.traces_root,
            "base": application.state.projects_root,
        }

    @application.get("/api/corpora")
    def corpora() -> dict[str, Any]:
        items = [item.as_payload() for item in list_workspaces(**_workspace_kwargs())]
        if application.state.demo:
            # A public demo is pinned to the system it started on.
            items = [item for item in items if item.get("id") == application.state.corpus_id]
        return {"active_id": application.state.corpus_id, "corpora": items}

    @application.post("/api/corpus")
    def select_corpus(body: CorpusSelectRequest) -> dict[str, Any]:
        try:
            selected = get_workspace(body.id.strip(), **_workspace_kwargs())
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"unknown corpus {body.id!r}") from error
        if not selected.writable:
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

    @application.post("/api/projects")
    def add_project(body: ProjectCreateRequest) -> dict[str, Any]:
        try:
            created = create_project(
                body.name,
                root=application.state.repo_root,
                traces_root=application.state.traces_root,
                base=application.state.projects_root,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        next_traces = (
            application.state.traces_dir
            if application.state.traces_locked
            else traces_dir_for(created.id, application.state.traces_root)
        )
        with application.state.index_lock:
            _activate(application, created, next_traces)
        return {"project": created.as_payload(), "active_id": created.id}

    @application.delete("/api/projects/{project_id}")
    def remove_project(project_id: str) -> dict[str, Any]:
        try:
            delete_project(
                project_id,
                root=application.state.repo_root,
                base=application.state.projects_root,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id!r}") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if application.state.corpus_id == project_id:
            fallback = get_workspace(
                default_corpus_id(root=application.state.repo_root),
                **_workspace_kwargs(),
            )
            next_traces = (
                application.state.traces_dir
                if application.state.traces_locked
                else traces_dir_for(fallback.id, application.state.traces_root)
            )
            with application.state.index_lock:
                _activate(application, fallback, next_traces)
        return {"deleted": project_id, "active_id": application.state.corpus_id}

    @application.patch("/api/projects/{project_id}/config")
    def save_project_config(project_id: str, body: ProjectConfigRequest) -> dict[str, Any]:
        try:
            updated = update_project_config(
                project_id,
                body.model_dump(),
                root=application.state.repo_root,
                traces_root=application.state.traces_root,
                base=application.state.projects_root,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id!r}") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if application.state.corpus_id == updated.id:
            next_traces = (
                application.state.traces_dir
                if application.state.traces_locked
                else traces_dir_for(updated.id, application.state.traces_root)
            )
            with application.state.index_lock:
                _activate(application, updated, next_traces)
        return {"project": updated.as_payload(), "active_id": application.state.corpus_id}

    @application.get("/api/projects/{project_id}/keys")
    def project_keys(project_id: str) -> dict[str, Any]:
        try:
            records = list_api_keys(project_id, **_workspace_kwargs())
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id!r}") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"keys": [item.as_public_payload() for item in records]}

    @application.post("/api/projects/{project_id}/keys")
    def add_project_key(
        project_id: str, body: ProjectKeyCreateRequest | None = None
    ) -> dict[str, Any]:
        request = body or ProjectKeyCreateRequest()
        try:
            token, record = create_api_key(
                project_id,
                scope=request.scope.strip() or "evaluations",
                **_workspace_kwargs(),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id!r}") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"key": token, "record": record.as_public_payload()}

    @application.delete("/api/projects/{project_id}/keys/{key_id}")
    def remove_project_key(project_id: str, key_id: str) -> dict[str, Any]:
        try:
            record = revoke_api_key(project_id, key_id, **_workspace_kwargs())
        except KeyError as error:
            raise HTTPException(status_code=404, detail="key not found") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"revoked": record.as_public_payload()}

    @application.get("/api/documents")
    def documents() -> dict[str, Any]:
        return {
            "writable": bool(application.state.writable),
            "documents": list_documents(Path(application.state.corpus_dir)),
        }

    @application.get("/api/documents/{name}")
    def document_text(name: str) -> dict[str, Any]:
        try:
            safe = safe_upload_name(name)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        path = Path(application.state.corpus_dir) / safe
        if not path.is_file():
            raise HTTPException(status_code=404, detail="document not found")
        try:
            text = read_document_text(path)
        except (UnicodeDecodeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"name": safe, "text": text}

    @application.post("/api/documents")
    async def upload_document(file: UploadFile = File(...)) -> dict[str, Any]:
        if not application.state.writable:
            raise HTTPException(
                status_code=400,
                detail="Built-in corpora are read-only. Create a project to upload documents.",
            )
        raw_name = file.filename or ""
        try:
            name = safe_upload_name(raw_name)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="file is empty")
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
            )
        dest = Path(application.state.corpus_dir) / name
        dest.write_bytes(data)
        try:
            validate_uploaded_file(dest)
        except (ValueError, UnicodeDecodeError) as error:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(error)) from error
        _invalidate_indexes(application)
        application.state.doc_count = corpus_file_count(application.state.corpus_dir)
        return {"uploaded": name, "documents": list_documents(Path(application.state.corpus_dir))}

    @application.delete("/api/documents/{name}")
    def remove_document(name: str) -> dict[str, Any]:
        if not application.state.writable:
            raise HTTPException(
                status_code=400,
                detail="Built-in corpora are read-only. Create a project to remove documents.",
            )
        try:
            safe = safe_upload_name(name)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        path = Path(application.state.corpus_dir) / safe
        if not path.is_file():
            raise HTTPException(status_code=404, detail="document not found")
        path.unlink()
        _invalidate_indexes(application)
        application.state.doc_count = corpus_file_count(application.state.corpus_dir)
        return {"deleted": safe, "documents": list_documents(Path(application.state.corpus_dir))}

    @application.get("/api/eval")
    def eval_panel() -> dict[str, Any]:
        return eval_counts(application.state.traces_dir)

    @application.get("/api/overview")
    def overview_panel() -> dict[str, Any]:
        return overview_for_traces(application.state.traces_dir)

    @application.get("/api/logical-runs")
    def logical_runs() -> dict[str, Any]:
        return logical_run_history(application.state.traces_dir)

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
        return _run_payload(application.state.traces_dir, payload)

    @application.get("/api/traces/{run_id}/quality")
    def get_quality(run_id: str) -> dict[str, Any]:
        if load_trace(application.state.traces_dir, run_id) is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return {"quality": load_quality(application.state.traces_dir, run_id)}

    @application.post("/api/traces/{run_id}/quality")
    def score_quality(run_id: str) -> dict[str, Any]:
        payload = load_trace(application.state.traces_dir, run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="trace not found")
        if not str(payload.get("answer") or "").strip():
            raise HTTPException(status_code=400, detail="retrieve-only runs have no answer to score")
        client, model = application.state.quality_scorer()
        try:
            scores = score_trace(payload, client=client, model=model)
        except ValueError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        save_quality(application.state.traces_dir, run_id, scores)
        return {"quality": scores}

    @application.delete("/api/traces/{run_id}")
    def remove_trace(run_id: str) -> dict[str, Any]:
        deleted = delete_trace(application.state.traces_dir, run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="trace not found")
        return {
            "deleted": run_id,
            "also_deleted": [item for item in deleted if item != run_id],
        }

    def _checked_question(body: RunRequest) -> str:
        question = body.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="question is required")
        if body.mode not in MODES:
            raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(MODES)}")
        retrieve_only = body.mode == "retrieve_only"
        needs_key = body.mode in {"loop", "loop_confirm", "baseline"}
        if needs_key and not retrieve_only and not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="OPENAI_API_KEY is not set. Use retrieve-only mode, or add a key to .env.",
            )
        return question

    def _run_and_load(body: RunRequest, question: str, listener=None) -> dict[str, Any]:
        """Execute one run under a progress recording and return its public payload."""
        try:
            with application.state.index_lock, capture_usage(), progress.recording(listener):
                result = _execute_run(
                    application,
                    question,
                    body.mode,
                    body.top_k,
                    body.recovery_policy,
                )
        except FileExistsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

        payload = load_trace(application.state.traces_dir, result.run_id)
        if payload is None:
            raise HTTPException(status_code=500, detail="run finished but the trace was not readable")
        return {
            "run_id": result.run_id,
            "answer": result.answer,
            **_public_run(application.state.traces_dir, payload),
        }

    @application.post("/api/runs")
    def create_run(body: RunRequest) -> dict[str, Any]:
        return _run_and_load(body, _checked_question(body))

    @application.post("/api/runs/stream")
    def create_run_stream(body: RunRequest) -> StreamingResponse:
        """Same run as POST /api/runs, reported as Server-Sent Events.

        Each stage sends ``stage_start`` and ``stage_end`` as it happens (with
        offsets and durations in ms). The last event is ``done`` with the same
        payload POST /api/runs returns, or ``error`` with a status and detail.
        """
        question = _checked_question(body)
        events: queue.Queue = queue.Queue()

        def worker() -> None:
            try:
                result = _run_and_load(body, question, listener=events.put)
                if application.state.demo:
                    result = scrub(result, str(repo_root()))
                events.put({"type": "done", "run": result})
            except HTTPException as error:
                events.put({"type": "error", "status": error.status_code, "detail": error.detail})
            except Exception as error:  # pragma: no cover - defensive
                events.put({"type": "error", "status": 500, "detail": str(error)})
            finally:
                events.put(None)

        threading.Thread(target=worker, name="swrag-run-stream", daemon=True).start()

        def stream():
            yield ": run started\n\n"
            while True:
                item = events.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.post("/api/runs/{run_id}/recover")
    def recover_run(run_id: str, body: RecoverRequest | None = None) -> dict[str, Any]:
        request = body or RecoverRequest()
        parent = load_trace(application.state.traces_dir, run_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="trace not found")
        if not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="OPENAI_API_KEY is not set. Use retrieve-only mode, or add a key to .env.",
            )
        if parent.get("parent_run_id"):
            raise HTTPException(status_code=409, detail="cannot apply recovery to a recovered child run")
        if parent.get("recovery_status") != "proposed":
            raise HTTPException(status_code=409, detail="recovery is not proposed on this run")
        if find_child_run_id(application.state.traces_dir, run_id):
            raise HTTPException(status_code=409, detail="recovery was already applied for this run")
        recovery = parent.get("recovery") if isinstance(parent.get("recovery"), dict) else {}
        if not recovery.get("action"):
            raise HTTPException(status_code=409, detail="parent has no proposed recovery")
        action = (request.action or "").strip() or None
        if action is not None and action not in ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"action must be one of {sorted(ACTIONS)}",
            )
        try:
            with application.state.index_lock, capture_usage():
                result = _execute_recover(application, run_id, action)
        except RecoveryNotApplicable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except FileExistsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

        payload = load_trace(application.state.traces_dir, result.run_id)
        if payload is None:
            raise HTTPException(status_code=500, detail="run finished but the trace was not readable")
        return {
            "run_id": result.run_id,
            "answer": result.answer,
            **_public_run(application.state.traces_dir, payload),
        }

    application.include_router(build_v1_router())

    if static.is_dir():
        @application.get("/")
        def index() -> FileResponse:
            # Revalidate the page on every load. Scripts are cache-busted with
            # ?v= in index.html, which only works if index.html itself is fresh.
            return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})

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
    application.state.writable = bool(entry.writable)
    application.state.agent_config = dict(entry.config) if entry.writable and entry.config else None
    application.state.traces_dir = Path(traces)
    application.state.indexes = {}


def _entry_for_explicit_dir(corpus_dir: Path, root: Path) -> CorpusEntry:
    resolved = corpus_dir.resolve()
    for entry in list_workspaces(root=root, traces_root=root / "experiments" / "output"):
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
        writable=False,
    )


def _execute_run(
    application: FastAPI,
    question: str,
    mode: str,
    top_k: int,
    recovery_policy: str | None,
):
    retrieve_only = mode == "retrieve_only"
    index = _index_for(application, retrieve_only=retrieve_only)
    policy = _selected_policy(application, recovery_policy)
    kwargs: dict[str, Any] = {
        "corpus_dir": application.state.corpus_dir,
        "output_dir": application.state.traces_dir,
        "top_k": top_k,
        "index": index,
        "generate": not retrieve_only,
        "embedder": FakeEmbedder() if retrieve_only else None,
        "agent_config": _agent_snapshot(application),
        "run_mode": mode,
        "recovery_policy": policy,
    }
    if not retrieve_only:
        kwargs["generator"] = _generator_for(application)
    if mode == "loop":
        from swrag.evaluation.llm_judge import LLMJudge

        kwargs["judge"] = LLMJudge()
        kwargs["max_recoveries"] = 2
        return run_with_recovery(question, **kwargs)
    if mode == "loop_confirm":
        from swrag.evaluation.llm_judge import LLMJudge

        kwargs["judge"] = LLMJudge()
        return run_first_pass(question, **kwargs)
    return run_query(question, **kwargs)


def _execute_recover(application: FastAPI, run_id: str, action: str | None):
    from swrag.evaluation.llm_judge import LLMJudge

    index = _index_for(application, retrieve_only=False)
    return apply_recovery(
        run_id,
        output_dir=application.state.traces_dir,
        corpus_dir=application.state.corpus_dir,
        action=action,
        index=index,
        generate=True,
        judge=LLMJudge(),
        generator=_generator_for(application),
        agent_config=_agent_snapshot(application),
    )


def _default_quality_scorer() -> tuple[Any, str]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not set, so runs cannot be scored.")
    from openai import OpenAI

    config = load_provider_config()
    return OpenAI(base_url=config.base_url), config.chat_model


def _selected_policy(application: FastAPI, requested: str | None) -> str:
    """Request choice wins. A blank request uses the saved project choice, or v1."""
    if requested is not None and str(requested).strip():
        return resolve_product_policy(requested)
    config = application.state.agent_config
    stored = config.get("recovery_policy") if isinstance(config, dict) else None
    return resolve_product_policy(stored if isinstance(stored, str) else None)


def _public_run(traces_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
    attempts = payload.get("recovery_attempts") if isinstance(payload.get("recovery_attempts"), list) else []
    actions = [
        str(item.get("action"))
        for item in attempts
        if isinstance(item, dict) and item.get("action")
    ]
    return {
        **_run_payload(traces_dir, payload),
        "recovery_policy": payload.get("recovery_policy") or "v1",
        "recovery_actions": actions,
        "safe_stop": _payload_safe_stop(payload),
        "usage": usage,
        "cost_estimate": estimated_list_cost(usage),
    }


def _payload_safe_stop(payload: dict[str, Any]) -> bool:
    attempts = payload.get("recovery_attempts") if isinstance(payload.get("recovery_attempts"), list) else []
    for item in attempts:
        if isinstance(item, dict) and _has_stop_reason(item):
            return True
    recovery = payload.get("recovery")
    return isinstance(recovery, dict) and _has_stop_reason(recovery)


def _has_stop_reason(item: dict[str, Any]) -> bool:
    if str(item.get("action") or "") != "abstain":
        return False
    parameters = item.get("parameters")
    return isinstance(parameters, dict) and bool(str(parameters.get("stop_reason") or "").strip())


def _run_payload(traces_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace": payload,
        "steps": trace_to_steps(payload),
        "child_run_id": find_child_run_id(traces_dir, str(payload.get("run_id") or "")),
    }


def _agent_snapshot(application: FastAPI) -> dict[str, Any] | None:
    config = application.state.agent_config
    if not application.state.writable or not isinstance(config, dict):
        return None
    return dict(config)


def _generator_for(application: FastAPI) -> OpenAIGenerator:
    config = application.state.agent_config if isinstance(application.state.agent_config, dict) else {}
    model = str(config.get("chat_model") or "") or None
    if not application.state.writable:
        model = None
    return OpenAIGenerator(
        model=model,
        instructions=str(config.get("instructions") or ""),
    )


def _index_cache_key(application: FastAPI, *, retrieve_only: bool) -> tuple[str, str, str]:
    return (
        str(application.state.corpus_id),
        str(Path(application.state.corpus_dir).resolve()),
        "fake" if retrieve_only else "openai",
    )


def _index_for(application: FastAPI, *, retrieve_only: bool):
    key = _index_cache_key(application, retrieve_only=retrieve_only)
    with application.state.index_lock:
        cached = application.state.indexes.get(key)
        if cached is not None:
            return cached
        embedder = FakeEmbedder() if retrieve_only else None
        try:
            index = build_corpus_index(application.state.corpus_dir, embedder)
        except ValueError:
            if not application.state.writable:
                raise
            index = InMemoryIndex(embedder or FakeEmbedder())
        application.state.indexes[key] = index
        return index


def _invalidate_indexes(application: FastAPI) -> None:
    corpus_id = application.state.corpus_id
    with application.state.index_lock:
        for key in [item for item in application.state.indexes if item[0] == corpus_id]:
            del application.state.indexes[key]


app = create_app()
