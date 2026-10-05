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
    version = payload.get("trace_schema_version")
    if isinstance(version, int) and not isinstance(version, bool) and version > 2:
        return [
            _step(
                "query",
                "query",
                "Query",
                query or "(empty)",
                "ok",
                {"query": query, "unsupported_schema": True},
            )
        ]
    rewritten = payload.get("rewritten_query")
    previous_answer = payload.get("previous_answer")
    previous_chunks = payload.get("previous_retrieved_chunks")
    chunks = list(payload.get("retrieved_chunks") or ())
    recovered = _is_recovered(payload)
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

    after_retrieve: dict[str, Any] | None = None
    if previous_chunks:
        first = list(previous_chunks)
        steps.append(
            _retrieve_step(
                "retrieve-first",
                "Retrieve (first pass)",
                first,
                payload,
                pass_name="first",
                include_signal=True,
            )
        )
        after_retrieve = _retrieve_step(
            "retrieve",
            "Retrieve (after recovery)",
            chunks,
            payload,
            pass_name="after_recovery",
        )
    else:
        retrieve_payload: dict[str, Any] = {
            "top_k": payload.get("top_k"),
            "embedding_model": payload.get("embedding_model"),
            "chunks": chunks,
        }
        if payload.get("retrieval_signal") is not None:
            retrieve_payload["retrieval_signal"] = payload.get("retrieval_signal")
        if rewritten:
            retrieve_payload["note"] = (
                "chunks are post-recovery; first-pass chunks were not stored"
            )
        steps.append(
            _step(
                "retrieve",
                "retrieve",
                "Retrieve",
                _chunk_summary(chunks),
                "ok" if chunks else "empty",
                retrieve_payload,
            )
        )

    answer = str(payload.get("answer") or "")
    model = str(payload.get("model") or "")
    generate_skipped = model == "none" and not answer.strip()
    if recovered:
        first_text = str(previous_answer)
        steps.append(
            _step(
                "generate-first",
                "generate",
                "Generate (first pass)",
                first_text.splitlines()[0][:96] if first_text else "(empty)",
                "ok" if first_text.strip() else "empty",
                {"answer": first_text, "pass": "first"},
            )
        )
        _append_recover(steps, payload, rewritten, previous_answer)
        if after_retrieve is not None:
            steps.append(after_retrieve)
        steps.append(
            _generate_after(answer, model, generate_skipped, payload)
        )
        _append_evaluate(steps, payload, after_recovery=True)
        _append_diagnose(steps, payload, after_recovery=True)
        _append_verify(steps, payload)
        return steps

    if after_retrieve is not None:
        steps.append(after_retrieve)

    steps.append(
        _step(
            "generate",
            "generate",
            "Generate",
            "skipped" if generate_skipped else (answer.splitlines()[0][:96] if answer else "(empty)"),
            "skipped" if generate_skipped else ("ok" if answer.strip() else "empty"),
            {"answer": answer, "model": model},
        )
    )
    _append_evaluate(steps, payload, after_recovery=False)
    _append_diagnose(steps, payload, after_recovery=False)
    _append_recover(steps, payload, rewritten, previous_answer)
    _append_verify(steps, payload)
    return steps


def _last_attempt_field(payload: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(payload, dict):
        return None
    attempts = [item for item in payload.get("recovery_attempts") or [] if isinstance(item, dict)]
    if not attempts:
        return None
    return attempts[-1].get(key)


def _is_recovered(payload: dict[str, Any]) -> bool:
    """True when this trace already applied a V1 recovery, not only a proposal."""
    if payload.get("previous_answer"):
        return True
    if payload.get("rewritten_query"):
        return True
    if payload.get("previous_retrieved_chunks"):
        return True
    recovery = payload.get("recovery") if isinstance(payload.get("recovery"), dict) else {}
    action = recovery.get("action")
    if payload.get("recovery_status") == "applied" and action in {
        "regenerate",
        "rewrite",
        "expand",
        "abstain",
    }:
        return True
    verification = payload.get("verification")
    return isinstance(verification, dict) and bool(verification.get("outcome"))


def _retrieve_step(
    step_id: str,
    title: str,
    chunks: list[Any],
    payload: dict[str, Any],
    *,
    pass_name: str,
    include_signal: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "top_k": payload.get("top_k"),
        "embedding_model": payload.get("embedding_model"),
        "chunks": chunks,
        "pass": pass_name,
    }
    if include_signal and payload.get("retrieval_signal") is not None:
        body["retrieval_signal"] = payload.get("retrieval_signal")
    return _step(
        step_id,
        "retrieve",
        title,
        _chunk_summary(chunks),
        "ok" if chunks else "empty",
        body,
    )


def _generate_after(
    answer: str,
    model: str,
    generate_skipped: bool,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    relation = _last_attempt_field(payload, "answer_relation")
    executed = _last_attempt_field(payload, "executed")
    if executed is False:
        title = "Selected, not executed"
        status = "skipped"
        detail = "the controller selected a recovery and it did not run"
    elif relation == "kept_previous":
        title = "Kept previous answer"
        status = "ok" if answer.strip() else "empty"
        detail = answer.splitlines()[0][:96] if answer else "(empty)"
    elif relation == "abstained":
        title = "Abstained"
        status = "warn"
        detail = answer.splitlines()[0][:96] if answer else "(empty)"
    elif relation in {"unchanged", "none"}:
        title = "Answer unchanged"
        status = "ok" if answer.strip() else "empty"
        detail = answer.splitlines()[0][:96] if answer else "(empty)"
    else:
        title = "Generate (after recovery)"
        status = "skipped" if generate_skipped else ("ok" if answer.strip() else "empty")
        detail = "skipped" if generate_skipped else (answer.splitlines()[0][:96] if answer else "(empty)")
    body = {
        "answer": answer,
        "model": model,
        "pass": "after_recovery",
    }
    if relation:
        body["answer_relation"] = relation
    return _step("generate", "generate", title, detail, status, body)


def _append_evaluate(
    steps: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    after_recovery: bool,
) -> None:
    evaluation = payload.get("runtime_evaluation")
    if not isinstance(evaluation, dict):
        return
    sufficient = evaluation.get("evidence_sufficient")
    supported = evaluation.get("answer_supported")
    summary = f"sufficient={_flag(sufficient)}  supported={_flag(supported)}"
    status = "ok" if sufficient and supported is not False else "warn"
    eval_payload = dict(evaluation)
    title = "Evaluate"
    if after_recovery:
        title = "Evaluate (after recovery)"
        source = _last_attempt_field(payload, "evaluation_source")
        if source == "carried":
            eval_payload["note"] = "flags were carried forward; this was not a new judge call"
        elif source == "judge":
            eval_payload["note"] = "flags are from the judge call on this attempt's answer"
        elif source == "probe" or (payload.get("rewritten_query") and supported is None):
            eval_payload["note"] = (
                "flags are from the rewrite retrieve probe "
                "(no answer was generated on that retrieve)"
            )
        else:
            eval_payload["note"] = "flags are from the last judge call (after recovery)"
        probe = payload.get("probe_evaluation")
        if isinstance(probe, dict):
            eval_payload["probe_evaluation"] = probe
    steps.append(_step("evaluate", "evaluate", title, summary, status, eval_payload))


def _append_diagnose(
    steps: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    after_recovery: bool,
) -> None:
    diagnosis = payload.get("diagnosis")
    if not isinstance(diagnosis, dict):
        return
    klass = diagnosis.get("failure_class")
    title = "Diagnose (after recovery)" if after_recovery else "Diagnose"
    steps.append(
        _step(
            "diagnose",
            "diagnose",
            title,
            _diagnose_summary(diagnosis, after_recovery=after_recovery),
            "warn" if klass else "ok",
            diagnosis,
        )
    )


def _append_recover(
    steps: list[dict[str, Any]],
    payload: dict[str, Any],
    rewritten: Any,
    previous_answer: Any,
) -> None:
    recovery = payload.get("recovery")
    if not isinstance(recovery, dict) or not recovery.get("action"):
        return
    action = str(recovery.get("action"))
    status_label = payload.get("recovery_status")
    attempts = payload.get("recovery_attempts")
    if isinstance(attempts, list) and len(attempts) > 1:
        summary = " → ".join(
            str(item.get("action") or "")
            for item in attempts
            if isinstance(item, dict)
        )
    else:
        summary = f"proposed: {action}" if status_label == "proposed" else action
    status = "ok" if action == "accept" else "warn" if action != "abstain" else "empty"
    steps.append(
        _step(
            "recover",
            "recover",
            "Recover",
            summary,
            status,
            {
                **recovery,
                "rewritten_query": rewritten,
                "previous_answer": previous_answer,
                "recovery_status": status_label,
                "recovery_attempts": attempts,
            },
        )
    )


def _append_verify(steps: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    verification = payload.get("verification")
    if not isinstance(verification, dict) or not verification.get("outcome"):
        return
    outcome = str(verification.get("outcome"))
    status = "ok" if outcome == "improved" else "warn" if outcome == "unchanged" else "error"
    steps.append(_step("verify", "verify", "Verify", outcome, status, verification))


def _chunk_summary(chunks: list[Any]) -> str:
    return f"{len(chunks)} chunk" if len(chunks) == 1 else f"{len(chunks)} chunks"


def _diagnose_summary(diagnosis: dict[str, Any], *, after_recovery: bool) -> str:
    """First-pass miss vs gap is deferred; that is not a missing diagnosis."""
    klass = diagnosis.get("failure_class")
    if klass:
        return str(klass)
    rationale = str(diagnosis.get("rationale") or "").lower()
    if "not diagnosed on the first pass" in rationale or "not split on first pass" in rationale:
        return "deferred until rewrite"
    if "no generated answer" in rationale:
        return "no generated answer"
    if "sufficient and the answer was supported" in rationale:
        return "no failure"
    if after_recovery:
        return "no class claimed"
    return "no class claimed"


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
