"""Turn a flat trace JSON object into a waterfall of steps.

The stored trace is one record, not nested spans. The UI (and tests) use this
mapping so the explorer can look like a LangSmith-style timeline without the
pipeline knowing about the frontend.
"""

from __future__ import annotations

from typing import Any


def trace_to_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive ordered steps from a ``TraceRecord`` JSON dict."""
    steps: list[dict[str, Any]] = []
    query = str(payload.get("query") or "")
    rewritten = payload.get("rewritten_query")
    steps.append(
        _step(
            "query",
            "query",
            "Query",
            query or "(empty)",
            "ok",
            {
                "query": query,
                "rewritten_query": rewritten,
                "question_id": payload.get("question_id"),
            },
        )
    )

    chunks = list(payload.get("retrieved_chunks") or ())
    steps.append(
        _step(
            "retrieve",
            "retrieve",
            "Retrieve",
            f"{len(chunks)} chunk" if len(chunks) == 1 else f"{len(chunks)} chunks",
            "ok" if chunks else "empty",
            {
                "top_k": payload.get("top_k"),
                "embedding_model": payload.get("embedding_model"),
                "chunks": chunks,
            },
        )
    )

    answer = str(payload.get("answer") or "")
    model = str(payload.get("model") or "")
    generate_skipped = model == "none" and not answer.strip()
    steps.append(
        _step(
            "generate",
            "generate",
            "Generate",
            "skipped" if generate_skipped else (answer.splitlines()[0][:96] if answer else "(empty)"),
            "skipped" if generate_skipped else ("ok" if answer.strip() else "empty"),
            {
                "answer": answer,
                "model": model,
                "previous_answer": payload.get("previous_answer"),
            },
        )
    )

    evaluation = payload.get("runtime_evaluation")
    if isinstance(evaluation, dict):
        sufficient = evaluation.get("evidence_sufficient")
        supported = evaluation.get("answer_supported")
        summary = f"sufficient={_flag(sufficient)}  supported={_flag(supported)}"
        status = "ok" if sufficient and supported is not False else "warn"
        steps.append(
            _step("evaluate", "evaluate", "Evaluate", summary, status, evaluation)
        )

    diagnosis = payload.get("diagnosis")
    if isinstance(diagnosis, dict):
        klass = diagnosis.get("failure_class")
        steps.append(
            _step(
                "diagnose",
                "diagnose",
                "Diagnose",
                str(klass) if klass else "no class claimed",
                "warn" if klass else "ok",
                diagnosis,
            )
        )

    recovery = payload.get("recovery")
    if isinstance(recovery, dict) and recovery.get("action"):
        action = str(recovery.get("action"))
        status = "ok" if action == "accept" else "warn" if action != "abstain" else "empty"
        steps.append(
            _step(
                "recover",
                "recover",
                "Recover",
                action,
                status,
                {
                    **recovery,
                    "rewritten_query": rewritten,
                    "previous_answer": payload.get("previous_answer"),
                },
            )
        )

    verification = payload.get("verification")
    if isinstance(verification, dict) and verification.get("outcome"):
        outcome = str(verification.get("outcome"))
        status = "ok" if outcome == "improved" else "warn" if outcome == "unchanged" else "error"
        steps.append(_step("verify", "verify", "Verify", outcome, status, verification))

    return steps


def _step(
    step_id: str,
    kind: str,
    title: str,
    summary: str,
    status: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": step_id,
        "kind": kind,
        "title": title,
        "summary": summary,
        "status": status,
        "payload": payload,
    }


def _flag(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "n/a"
