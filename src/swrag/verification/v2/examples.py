"""Join a transition to offline gold only after a verifier has been called.

Candidates never import this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from swrag.evaluation.gold import load_gold_set
from swrag.types import GoldQuestion
from swrag.verification.v2.gold_transition import label_answers
from swrag.verification.v2.protocol import CLASSES
from swrag.verification.v2.transitions import Transition, transitions_from_trace


@dataclass(frozen=True)
class Example:
    """One scored transition. ``gold_label`` is not a verifier input."""

    transition: Transition
    gold_label: str
    v1_outcome: str | None
    answerable: bool
    panel: str
    split: str
    source: str
    failure_class: str | None = None


def stored_v1(payload: dict, transition: Transition) -> str | None:
    """Read the verdict Verification v1 already wrote. Do not recompute it."""
    if transition.level == "attempt" and transition.attempt_index is not None:
        attempts = payload.get("recovery_attempts") or []
        if transition.attempt_index >= len(attempts):
            return None
        return _class(attempts[transition.attempt_index].get("verification"))
    return _class(payload.get("verification"))


def examples_from_trace(
    payload: dict,
    gold_by_id: dict[str, GoldQuestion],
    *,
    panel: str,
    split: str,
    corpus_id: str | None,
    source: str,
) -> tuple[Example, ...]:
    found: list[Example] = []
    for transition in transitions_from_trace(payload, corpus_id=corpus_id):
        gold = _match_gold(transition, gold_by_id)
        if gold is None:
            continue
        bound = _bind(transition, gold)
        found.append(
            Example(
                transition=bound,
                gold_label=label_answers(bound.before.answer, bound.after.answer, gold),
                v1_outcome=stored_v1(payload, bound),
                answerable=gold.answerable,
                panel=panel,
                split=split,
                source=source,
                failure_class=bound.after.diagnosis_class or bound.before.diagnosis_class,
            )
        )
    return tuple(found)


def examples_from_trace_dir(
    traces_dir: Path,
    gold_paths: tuple[str, ...],
    *,
    root: Path,
    panel: str,
    split: str,
    corpus_id: str,
) -> tuple[Example, ...]:
    gold_by_id = load_gold_index(gold_paths, root=root)
    found: list[Example] = []
    for path in sorted(traces_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        found.extend(
            examples_from_trace(
                payload,
                gold_by_id,
                panel=panel,
                split=split,
                corpus_id=corpus_id,
                source=str(path),
            )
        )
    return tuple(found)


def load_gold_index(paths: tuple[str, ...], *, root: Path) -> dict[str, GoldQuestion]:
    index: dict[str, GoldQuestion] = {}
    for relative in paths:
        for question in load_gold_set(root / relative):
            index[question.question_id] = question
    return index


def prediction_row(example: Example, prediction: object) -> dict:
    """Attach gold after the prediction exists. The row is an experiment record."""
    from swrag.verification.v2.candidates import Prediction

    if not isinstance(prediction, Prediction):
        raise TypeError("prediction must come from a shadow candidate")
    transition = example.transition
    return {
        "panel": example.panel,
        "split": example.split,
        "source": example.source,
        "question_id": transition.question_id,
        "level": transition.level,
        "action": transition.action,
        "answerable": example.answerable,
        "failure_class": example.failure_class,
        "gold_label": example.gold_label,
        "v1_outcome": example.v1_outcome,
        "v2_status": prediction.status,
        "v2_outcome": prediction.outcome,
        "v2_error": prediction.error,
        "rationale_codes": list(prediction.rationale_codes),
        "diagnostic": prediction.diagnostic,
        "candidate": prediction.candidate,
        "prompt_version": prediction.prompt_version,
        "model": prediction.model,
        "model_calls": prediction.model_calls,
        "prompt_tokens": prediction.prompt_tokens,
        "completion_tokens": prediction.completion_tokens,
        "latency_ms": prediction.latency_ms,
        "position_consistent": prediction.position_consistent,
        "answer_model": transition.after.answer_model,
        "abstention_origin_after": prediction.signals.get("abstention_origin_after"),
        "signals": prediction.signals,
    }


def _bind(transition: Transition, gold: GoldQuestion) -> Transition:
    if transition.question_id:
        return transition
    return Transition(
        level=transition.level,
        question=transition.question,
        before=transition.before,
        after=transition.after,
        action=transition.action,
        executed=transition.executed,
        schema_version=transition.schema_version,
        question_id=gold.question_id,
        corpus_id=transition.corpus_id,
        attempt_index=transition.attempt_index,
    )


def _match_gold(transition: Transition, gold_by_id: dict[str, GoldQuestion]) -> GoldQuestion | None:
    if transition.question_id and transition.question_id in gold_by_id:
        return gold_by_id[transition.question_id]
    matches = [item for item in gold_by_id.values() if item.question == transition.question]
    if len(matches) == 1:
        return matches[0]
    return None


def _class(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("outcome")
    if isinstance(value, str) and value in CLASSES:
        return value
    return None
