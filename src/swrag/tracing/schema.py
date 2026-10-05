"""Trace schema v2: an immutable first pass plus ordered recovery attempts.

Version 1 is any file that omits ``trace_schema_version``. Those files stay
readable. New pipeline traces are version 2. This module is the compatibility
reader; ``write_run`` is the only writer that stamps the version.

A version-2 trace with ``initial`` null has one state: the top-level fields.
``initial`` is present only when a later attempt replaced that state, so the
first pass is not duplicated onto baseline and retrieve-only traces.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 2

# How the attempt's answer relates to the evidence stored for that attempt.
ANSWER_GENERATED = "generated"
ANSWER_KEPT_PREVIOUS = "kept_previous"
ANSWER_ABSTAINED = "abstained"
ANSWER_UNCHANGED = "unchanged"
ANSWER_NONE = "none"

# How the attempt's evidence relates to the previous evidence state.
EVIDENCE_REPLACED = "replaced"
EVIDENCE_WIDENED = "widened"
EVIDENCE_UNCHANGED = "unchanged"

# Which judge call the attempt's runtime_evaluation came from.
EVAL_JUDGE = "judge"
EVAL_PROBE = "probe"
EVAL_CARRIED = "carried"

RUN_MODES = frozenset({"retrieve_only", "baseline", "loop_confirm", "loop"})

_CHANGED_EVIDENCE = frozenset({EVIDENCE_REPLACED, EVIDENCE_WIDENED})


def schema_version(payload: dict[str, Any]) -> int:
    """1 when the file predates versioning or the field is null."""
    value = payload.get("trace_schema_version")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return 1
    return value


def initial_snapshot(
    *,
    query: str,
    retrieved_chunks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    answer: str,
    model: str,
    top_k: int | None,
    runtime_evaluation: dict[str, Any] | None,
    retrieval_signal: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    latency_ms: float | None,
) -> dict[str, Any]:
    """Immutable first-pass state. Callers must not update this dict later."""
    return {
        "query": query,
        "retrieved_chunks": [dict(chunk) for chunk in retrieved_chunks],
        "answer": answer,
        "model": model,
        "top_k": top_k,
        "runtime_evaluation": dict(runtime_evaluation) if runtime_evaluation else None,
        "retrieval_signal": dict(retrieval_signal) if retrieval_signal else None,
        "diagnosis": dict(diagnosis) if diagnosis else None,
        "latency_ms": latency_ms,
    }


def initial_from_trace(payload: dict[str, Any]) -> dict[str, Any]:
    """First pass copied from a confirm parent. The parent file is that state."""
    chunks = payload.get("retrieved_chunks")
    evaluation = payload.get("runtime_evaluation")
    signal = payload.get("retrieval_signal")
    diagnosis = payload.get("diagnosis")
    latency = payload.get("latency_ms")
    return initial_snapshot(
        query=str(payload.get("query") or ""),
        retrieved_chunks=list(chunks) if isinstance(chunks, list) else [],
        answer=str(payload.get("answer") or ""),
        model=str(payload.get("model") or ""),
        top_k=payload.get("top_k") if isinstance(payload.get("top_k"), int) else None,
        runtime_evaluation=evaluation if isinstance(evaluation, dict) else None,
        retrieval_signal=signal if isinstance(signal, dict) else None,
        diagnosis=diagnosis if isinstance(diagnosis, dict) else None,
        latency_ms=float(latency) if isinstance(latency, (int, float)) and not isinstance(latency, bool) else None,
    )


def attempt_record(
    *,
    index: int,
    action: str,
    reason: str,
    trigger: str,
    source: str,
    attributed_class: str | None,
    outcome_note: str,
    top_k: int,
    retrieved_doc_ids: list[str],
    verification: dict[str, Any] | None,
    answer: str,
    answer_model: str,
    answer_relation: str,
    evidence_relation: str,
    evaluation_source: str,
    executed: bool,
    runtime_evaluation: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    latency_ms: float,
    rewritten_query: str | None = None,
    parameters: dict[str, Any] | None = None,
    search_query: str | None = None,
    retrieved_chunks: list[dict[str, Any]] | None = None,
    probe_evaluation: dict[str, Any] | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """One completed recovery attempt. Step verification stays on ``verification``.

    Chunk text is stored only when this attempt replaced or widened evidence.
    ``evidence_relation`` ``unchanged`` means the evidence is the previous
    attempt's chunks, or ``initial.retrieved_chunks`` when this is the first.
    """
    row: dict[str, Any] = {
        "index": index,
        "action": action,
        "reason": reason,
        "trigger": trigger,
        "source": source,
        "attributed_class": attributed_class,
        "outcome_note": outcome_note,
        "top_k": top_k,
        "retrieved_doc_ids": list(retrieved_doc_ids),
        "verification": verification,
        "answer": answer,
        "answer_model": answer_model,
        "answer_relation": answer_relation,
        "evidence_relation": evidence_relation,
        "evaluation_source": evaluation_source,
        "executed": executed,
        "runtime_evaluation": runtime_evaluation,
        "diagnosis": diagnosis,
        "latency_ms": latency_ms,
    }
    if rewritten_query:
        row["rewritten_query"] = rewritten_query
    if parameters:
        row["parameters"] = dict(parameters)
    if search_query:
        row["search_query"] = search_query
    if evidence_relation in _CHANGED_EVIDENCE and retrieved_chunks is not None:
        row["retrieved_chunks"] = [dict(chunk) for chunk in retrieved_chunks]
    if probe_evaluation is not None:
        row["probe_evaluation"] = probe_evaluation
    if usage is not None:
        row["usage"] = dict(usage)
    return row


def first_pass_diagnosis(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Diagnosis from before recovery, when the file actually stored one.

    A legacy recovered trace keeps its final diagnosis on the top level. That
    class is not treated as the first pass. A confirm parent with no attempts
    still has its first-pass diagnosis on the top level.
    """
    initial = payload.get("initial")
    if isinstance(initial, dict) and isinstance(initial.get("diagnosis"), dict):
        return initial["diagnosis"]
    if payload.get("parent_run_id"):
        return None
    attempts = payload.get("recovery_attempts") or []
    if isinstance(attempts, list) and attempts:
        return None
    diagnosis = payload.get("diagnosis")
    return diagnosis if isinstance(diagnosis, dict) else None


def evidence_for_attempt(payload: dict[str, Any], index: int) -> list[dict[str, Any]]:
    """Chunks that produced the attempt, walking unchanged evidence backward."""
    attempts = [item for item in payload.get("recovery_attempts") or [] if isinstance(item, dict)]
    if index < 0 or index >= len(attempts):
        return []
    for cursor in range(index, -1, -1):
        attempt = attempts[cursor]
        if attempt.get("evidence_relation") in _CHANGED_EVIDENCE:
            chunks = attempt.get("retrieved_chunks")
            return list(chunks) if isinstance(chunks, list) else []
    initial = payload.get("initial")
    if isinstance(initial, dict) and isinstance(initial.get("retrieved_chunks"), list):
        return list(initial["retrieved_chunks"])
    previous = payload.get("previous_retrieved_chunks")
    if isinstance(previous, list):
        return list(previous)
    chunks = payload.get("retrieved_chunks")
    return list(chunks) if isinstance(chunks, list) else []
