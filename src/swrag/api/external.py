"""Adapt an externally produced RAG run into the internal evaluation shape.

Issue #78. Customer agents submit query, answer, and contexts. This module
builds a synthetic ``QueryState``, runs the existing judge and diagnosis, and
writes a trace. It does not retrieve, rewrite, or expand: those need an index
the customer did not give us.
"""

from __future__ import annotations

from typing import Any

from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.evaluation.judge import GroundingJudge
from swrag.evaluation.retrieval_signal import retrieval_signal
from swrag.pipeline.baseline import QueryState, write_run
from swrag.recovery.policy import EXPAND, REWRITE, select_recovery
from swrag.types import Chunk, GenerationResult, RetrievalResult, ScoredChunk

UNAVAILABLE_EXTERNAL_ACTIONS = {
    REWRITE: "rewrite needs a corpus index; this evaluation was submitted without one",
    EXPAND: "expand needs a corpus index; this evaluation was submitted without one",
}

MAX_CONTEXTS = 20
MAX_QUERY_CHARS = 4000
MAX_ANSWER_CHARS = 16000
MAX_CHUNK_CHARS = 4000
MAX_ID_CHARS = 120
MAX_TITLE_CHARS = 200
MAX_METADATA_KEYS = 16
MAX_METADATA_KEY_CHARS = 64
MAX_METADATA_VALUE_CHARS = 500
MAX_BODY_BYTES = 256_000


class ExternalPayloadError(ValueError):
    """Raised for a request that should become an HTTP 4xx."""


def parse_external_body(
    raw: object,
) -> tuple[str, str, list[dict[str, Any]], dict[str, Any] | None]:
    """Validate and normalize a POST /api/v1/evaluations body."""
    if not isinstance(raw, dict):
        raise ExternalPayloadError("body must be a JSON object")
    query = raw.get("query")
    if not isinstance(query, str):
        raise ExternalPayloadError("query must be a string")
    query = query.strip()
    if not query:
        raise ExternalPayloadError("query is required")
    if len(query) > MAX_QUERY_CHARS:
        raise ExternalPayloadError(f"query must be at most {MAX_QUERY_CHARS} characters")
    if "answer" not in raw:
        raise ExternalPayloadError("answer is required")
    if not isinstance(raw["answer"], str):
        raise ExternalPayloadError("answer must be a string")
    answer = raw["answer"]
    if len(answer) > MAX_ANSWER_CHARS:
        raise ExternalPayloadError(f"answer must be at most {MAX_ANSWER_CHARS} characters")
    contexts = raw.get("contexts")
    if contexts is None:
        raise ExternalPayloadError("contexts is required")
    if not isinstance(contexts, list):
        raise ExternalPayloadError("contexts must be a list")
    if len(contexts) > MAX_CONTEXTS:
        raise ExternalPayloadError(f"contexts must have at most {MAX_CONTEXTS} items")
    parsed: list[dict[str, Any]] = []
    for index, item in enumerate(contexts):
        if not isinstance(item, dict):
            raise ExternalPayloadError(f"contexts[{index}] must be an object")
        text = item.get("text")
        if not isinstance(text, str):
            raise ExternalPayloadError(f"contexts[{index}].text must be a string")
        if len(text) > MAX_CHUNK_CHARS:
            raise ExternalPayloadError(
                f"contexts[{index}].text must be at most {MAX_CHUNK_CHARS} characters"
            )
        chunk_id = item.get("chunk_id", "")
        doc_id = item.get("doc_id", "")
        title = item.get("title", "")
        if chunk_id is None:
            chunk_id = ""
        if doc_id is None:
            doc_id = ""
        if title is None:
            title = ""
        if not isinstance(chunk_id, str):
            raise ExternalPayloadError(f"contexts[{index}].chunk_id must be a string")
        if not isinstance(doc_id, str):
            raise ExternalPayloadError(f"contexts[{index}].doc_id must be a string")
        if not isinstance(title, str):
            raise ExternalPayloadError(f"contexts[{index}].title must be a string")
        if len(chunk_id) > MAX_ID_CHARS:
            raise ExternalPayloadError(
                f"contexts[{index}].chunk_id must be at most {MAX_ID_CHARS} characters"
            )
        if len(doc_id) > MAX_ID_CHARS:
            raise ExternalPayloadError(
                f"contexts[{index}].doc_id must be at most {MAX_ID_CHARS} characters"
            )
        if len(title) > MAX_TITLE_CHARS:
            raise ExternalPayloadError(
                f"contexts[{index}].title must be at most {MAX_TITLE_CHARS} characters"
            )
        score = item.get("score")
        if score is not None:
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ExternalPayloadError(f"contexts[{index}].score must be a number")
        page = item.get("page")
        if page is not None:
            if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                raise ExternalPayloadError(f"contexts[{index}].page must be a positive integer")
        parsed.append(
            {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "title": title,
                "text": text,
                "score": None if score is None else float(score),
                "page": page,
            }
        )
    metadata = _parse_metadata(raw.get("metadata"))
    return query, answer, parsed, metadata


def query_state_from_external(
    *,
    query: str,
    answer: str,
    contexts: list[dict[str, Any]],
    judge: GroundingJudge,
) -> QueryState:
    """Build the internal state the judge already knows how to score."""
    retrieval = _retrieval_from_contexts(query, contexts)
    generation = GenerationResult(answer=answer, model="external")
    evaluation = judge.judge(question=query, answer=answer, retrieval=retrieval)
    diagnosis = diagnose_runtime(evaluation)
    return QueryState(
        query=query,
        retrieval=retrieval,
        generation=generation,
        runtime_evaluation=evaluation,
        diagnosis=diagnosis,
        retrieval_signal=retrieval_signal(retrieval),
    )


def evaluate_external(
    *,
    query: str,
    answer: str,
    contexts: list[dict[str, Any]],
    judge: GroundingJudge,
    output_dir,
    project_id: str,
    metadata: dict[str, Any] | None = None,
):
    """Judge, diagnose, propose a recovery, and write a trace. Do not apply it."""
    state = query_state_from_external(
        query=query, answer=answer, contexts=contexts, judge=judge
    )
    decision = select_recovery(
        state.diagnosis, state.runtime_evaluation, state.retrieval_signal
    )
    extra: dict[str, Any] = {
        "source": "external_evaluation",
        "project_id": project_id,
    }
    if metadata:
        extra["metadata"] = metadata
    result = write_run(
        state,
        output_dir=output_dir,
        recovery=decision,
        recovery_status="proposed",
        agent_config=extra,
    )
    return result, state, decision


def unavailable_actions_payload() -> dict[str, str]:
    return dict(UNAVAILABLE_EXTERNAL_ACTIONS)


def evaluation_payload(
    *,
    result,
    state: QueryState,
    decision,
    project_id: str,
) -> dict[str, Any]:
    evaluation = state.runtime_evaluation
    diagnosis = state.diagnosis
    signal = state.retrieval_signal
    return {
        "run_id": result.run_id,
        "project_id": project_id,
        "answer": result.answer,
        "evaluation": evaluation.as_trace_payload() if evaluation is not None else None,
        "diagnosis": diagnosis.as_trace_payload() if diagnosis is not None else None,
        "retrieval_signal": signal.as_trace_payload() if signal is not None else None,
        "recovery": decision.as_trace_payload() if decision is not None else None,
        "recovery_status": "proposed",
        "unavailable_actions": unavailable_actions_payload(),
        "note": (
            "Recovery is proposed, not applied. rewrite and expand need a "
            "corpus index this endpoint does not have."
        ),
    }


def _parse_metadata(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ExternalPayloadError("metadata must be an object")
    if len(raw) > MAX_METADATA_KEYS:
        raise ExternalPayloadError(f"metadata must have at most {MAX_METADATA_KEYS} keys")
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key or len(key) > MAX_METADATA_KEY_CHARS:
            raise ExternalPayloadError(
                f"metadata keys must be strings of at most {MAX_METADATA_KEY_CHARS} characters"
            )
        if value is None or isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, float):
            cleaned[key] = value
        elif isinstance(value, str):
            if len(value) > MAX_METADATA_VALUE_CHARS:
                raise ExternalPayloadError(
                    f"metadata[{key}] must be at most {MAX_METADATA_VALUE_CHARS} characters"
                )
            cleaned[key] = value
        else:
            raise ExternalPayloadError(
                "metadata values must be strings, numbers, booleans, or null"
            )
    return cleaned


def _retrieval_from_contexts(query: str, contexts: list[dict[str, Any]]) -> RetrievalResult:
    scored: list[ScoredChunk] = []
    for index, item in enumerate(contexts):
        text = str(item.get("text") or "")
        chunk = Chunk(
            chunk_id=str(item.get("chunk_id") or f"external::{index:03d}"),
            doc_id=str(item.get("doc_id") or f"external-{index:03d}"),
            title=str(item.get("title") or ""),
            text=text,
            start_char=0,
            end_char=len(text),
            page=_optional_page(item.get("page")),
        )
        score = item.get("score")
        numeric = float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else 0.0
        scored.append(ScoredChunk(chunk=chunk, score=numeric))
    return RetrievalResult(
        query=query,
        chunks=tuple(scored),
        top_k=len(scored) if scored else 1,
        embedding_model="external",
    )


def _optional_page(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    return None
