"""Versioned public API for customer agents (issues #78 / #79).

Dashboard ``/api/*`` routes stay unauthenticated. Everything under ``/api/v1``
requires a project-scoped key.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from swrag.api.credentials import StoredKey, find_active_key
from swrag.api.external import (
    MAX_BODY_BYTES,
    ExternalPayloadError,
    evaluate_external,
    evaluation_payload,
    parse_external_body,
    unavailable_actions_payload,
)
from swrag.api.store import load_trace
from swrag.corpus_registry import traces_dir_for
from swrag.evaluation.judge import GroundingJudge


def build_v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/evaluations")
    async def create_evaluation(request: Request) -> dict[str, Any]:
        key = _require_key(request)
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="request body is too large")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=400, detail="body must be JSON") from error
        try:
            query, answer, contexts, metadata = parse_external_body(payload)
        except ExternalPayloadError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        judge = _judge_for(request)
        traces = traces_dir_for(key.project_id, request.app.state.traces_root)
        traces.mkdir(parents=True, exist_ok=True)
        result, state, decision = evaluate_external(
            query=query,
            answer=answer,
            contexts=contexts,
            judge=judge,
            output_dir=traces,
            project_id=key.project_id,
            metadata=metadata,
        )
        return evaluation_payload(
            result=result,
            state=state,
            decision=decision,
            project_id=key.project_id,
        )

    @router.get("/evaluations/{run_id}")
    def get_evaluation(run_id: str, request: Request) -> dict[str, Any]:
        key = _require_key(request)
        traces = traces_dir_for(key.project_id, request.app.state.traces_root)
        payload = load_trace(traces, run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="evaluation not found")
        return {
            "run_id": payload.get("run_id"),
            "project_id": key.project_id,
            "answer": payload.get("answer"),
            "evaluation": payload.get("runtime_evaluation"),
            "diagnosis": payload.get("diagnosis"),
            "retrieval_signal": payload.get("retrieval_signal"),
            "recovery": payload.get("recovery"),
            "recovery_status": payload.get("recovery_status"),
            "unavailable_actions": unavailable_actions_payload(),
            "trace": payload,
        }

    return router


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="missing or invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_token(request: Request) -> str:
    authorization = request.headers.get("authorization") or ""
    scheme, _, remainder = authorization.partition(" ")
    if scheme.lower() == "bearer" and remainder.strip():
        return remainder.strip()
    return (request.headers.get("x-api-key") or "").strip()


def _require_key(request: Request) -> StoredKey:
    token = _extract_token(request)
    if not token:
        raise unauthorized()
    record = find_active_key(
        token,
        root=request.app.state.repo_root,
        base=request.app.state.projects_root,
    )
    if record is None:
        raise unauthorized()
    return record


def _judge_for(request: Request) -> GroundingJudge:
    injected = getattr(request.app.state, "grounding_judge", None)
    if injected is not None:
        return injected
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY is not set. Add a key to .env, or use retrieve-only mode in the playground.",
        )
    from swrag.evaluation.llm_judge import LLMJudge

    return LLMJudge()
