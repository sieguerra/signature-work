"""Resolve schema-v2 before/after states. This module does not score gold."""

from __future__ import annotations

from dataclasses import dataclass

from swrag.tracing.schema import (
    ANSWER_ABSTAINED,
    ANSWER_GENERATED,
    evidence_for_attempt,
    future_schema,
    schema_version,
)

CONTROLLER_ABSTENTION = "controller"
GENERATED_ABSTENTION = "generated"


@dataclass(frozen=True)
class StateView:
    """One side of a transition, as the trace recorded it."""

    answer: str
    chunks: tuple[dict, ...]
    evidence_known: bool
    answer_relation: str | None = None
    evidence_relation: str | None = None
    evaluation_source: str | None = None
    answer_model: str | None = None
    diagnosis_class: str | None = None


@dataclass(frozen=True)
class Transition:
    """A recovery step or a whole run. Gold and the v1 verdict are not fields."""

    level: str
    question: str
    before: StateView
    after: StateView
    action: str | None
    executed: bool
    schema_version: int
    question_id: str | None = None
    corpus_id: str | None = None
    attempt_index: int | None = None


def transitions_from_trace(payload: dict, *, corpus_id: str | None = None) -> tuple[Transition, ...]:
    """Attempt-level and run-level transitions for one trace.

    ``executed: false`` attempts are omitted. A future schema is omitted.
    A probe or carried evaluation is kept on the state so a caller can see
    it, but this function does not treat it as a new answer judgment.
    """
    if not isinstance(payload, dict) or future_schema(payload):
        return ()
    version = schema_version(payload)
    question = str(payload.get("query") or "")
    question_id = payload.get("question_id")
    question_id = str(question_id) if question_id else None
    if version >= 2 and isinstance(payload.get("initial"), dict):
        return _version_two(payload, question, question_id, corpus_id, version)
    return _legacy_run(payload, question, question_id, corpus_id, version)


def abstention_origin(answer: str, answer_relation: str | None) -> str | None:
    """Distinguish a controller abstain from abstention text the model generated.

    The canonical sentence alone is not a controller abstain. Origin is None
    when the text is not an abstention.
    """
    if not _looks_abstained(answer):
        return None
    if answer_relation == ANSWER_ABSTAINED:
        return CONTROLLER_ABSTENTION
    if answer_relation == ANSWER_GENERATED:
        return GENERATED_ABSTENTION
    return None


def _version_two(
    payload: dict,
    question: str,
    question_id: str | None,
    corpus_id: str | None,
    version: int,
) -> tuple[Transition, ...]:
    initial = payload["initial"]
    attempts = [item for item in payload.get("recovery_attempts") or [] if isinstance(item, dict)]
    found: list[Transition] = []
    initial_answer = str(initial.get("answer") or "")
    initial_chunks = _chunk_list(initial.get("retrieved_chunks"))
    for index, attempt in enumerate(attempts):
        if attempt.get("executed") is False:
            continue
        before_answer, before_relation, before_model = _answer_before(attempts, index, initial)
        before_chunks = initial_chunks if index == 0 else evidence_for_attempt(payload, index - 1)
        after_chunks = evidence_for_attempt(payload, index)
        found.append(
            Transition(
                level="attempt",
                question=question,
                before=StateView(
                    answer=before_answer,
                    chunks=tuple(before_chunks),
                    evidence_known=True,
                    answer_relation=before_relation,
                    answer_model=before_model,
                    diagnosis_class=_diagnosis_class(initial if index == 0 else attempts[index - 1]),
                ),
                after=StateView(
                    answer=str(attempt.get("answer") or ""),
                    chunks=tuple(after_chunks),
                    evidence_known=True,
                    answer_relation=_text_or_none(attempt.get("answer_relation")),
                    evidence_relation=_text_or_none(attempt.get("evidence_relation")),
                    evaluation_source=_text_or_none(attempt.get("evaluation_source")),
                    answer_model=_text_or_none(attempt.get("answer_model")),
                    diagnosis_class=_diagnosis_class(attempt),
                ),
                action=_text_or_none(attempt.get("action")),
                executed=True,
                schema_version=version,
                question_id=question_id,
                corpus_id=corpus_id,
                attempt_index=index,
            )
        )
    executed = [item for item in attempts if item.get("executed") is not False]
    if not executed:
        return tuple(found)
    final_chunks = _chunk_list(payload.get("retrieved_chunks"))
    found.append(
        Transition(
            level="run",
            question=question,
            before=StateView(
                answer=initial_answer,
                chunks=tuple(initial_chunks),
                evidence_known=True,
                answer_model=_text_or_none(initial.get("model")),
                diagnosis_class=_diagnosis_class(initial),
            ),
            after=StateView(
                answer=str(payload.get("answer") or ""),
                chunks=tuple(final_chunks),
                evidence_known=True,
                answer_relation=_text_or_none(executed[-1].get("answer_relation")),
                evidence_relation=_text_or_none(executed[-1].get("evidence_relation")),
                evaluation_source=_text_or_none(executed[-1].get("evaluation_source")),
                answer_model=_text_or_none(payload.get("model")),
                diagnosis_class=_diagnosis_class(payload),
            ),
            action=_text_or_none(executed[-1].get("action")) if len(executed) == 1 else "multi",
            executed=True,
            schema_version=version,
            question_id=question_id,
            corpus_id=corpus_id,
            attempt_index=None,
        )
    )
    return tuple(found)


def _legacy_run(
    payload: dict,
    question: str,
    question_id: str | None,
    corpus_id: str | None,
    version: int,
) -> tuple[Transition, ...]:
    previous = payload.get("previous_answer")
    if not previous:
        return ()
    before_chunks = payload.get("previous_retrieved_chunks")
    after_chunks = payload.get("retrieved_chunks")
    known = isinstance(before_chunks, list) and isinstance(after_chunks, list)
    return (
        Transition(
            level="run",
            question=question,
            before=StateView(
                answer=str(previous),
                chunks=tuple(before_chunks) if isinstance(before_chunks, list) else (),
                evidence_known=known,
            ),
            after=StateView(
                answer=str(payload.get("answer") or ""),
                chunks=tuple(after_chunks) if isinstance(after_chunks, list) else (),
                evidence_known=known,
                answer_model=_text_or_none(payload.get("model")),
            ),
            action=_recovery_action(payload),
            executed=True,
            schema_version=version,
            question_id=question_id,
            corpus_id=corpus_id,
        ),
    )


def _answer_before(attempts: list[dict], index: int, initial: dict) -> tuple[str, str | None, str | None]:
    for cursor in range(index - 1, -1, -1):
        if attempts[cursor].get("executed") is False:
            continue
        return (
            str(attempts[cursor].get("answer") or ""),
            _text_or_none(attempts[cursor].get("answer_relation")),
            _text_or_none(attempts[cursor].get("answer_model")),
        )
    return str(initial.get("answer") or ""), None, _text_or_none(initial.get("model"))


def _chunk_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _diagnosis_class(node: dict) -> str | None:
    diagnosis = node.get("diagnosis")
    if isinstance(diagnosis, dict):
        failure = diagnosis.get("failure_class")
        return str(failure) if failure else None
    failure = node.get("diagnosis_class")
    return str(failure) if failure else None


def _recovery_action(payload: dict) -> str | None:
    recovery = payload.get("recovery")
    if isinstance(recovery, dict) and recovery.get("action"):
        return str(recovery["action"])
    action = payload.get("recovery_action")
    return str(action) if action else None


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _looks_abstained(answer: str) -> bool:
    return answer.strip().lower().startswith("i do not know")
