"""The object a shadow verifier is allowed to see.

Gold fields are rejected by key, wherever they are nested. The question text
is allowed. A rubric may use the English word "answerable"; that word is not
a gold field.
"""

from __future__ import annotations

import json
from typing import Any

from swrag.verification.v2.transitions import Transition, abstention_origin

FORBIDDEN_KEYS = frozenset(
    {
        "answerable",
        "answers",
        "exact_match",
        "contains_answer",
        "gold_f1",
        "f1",
        "f1_delta",
        "previous_f1",
        "supporting_doc_ids",
        "gold_path",
        "verification_vs_gold",
        "reference_answer",
        "expected_output",
        "gold_label",
        "v1_outcome",
        "notes",
    }
)


class GoldLeakageError(ValueError):
    """A verifier input contained an offline gold field."""


def verifier_view(transition: Transition) -> dict[str, Any]:
    """JSON-ready view. Does not include verdicts, scores, or gold."""
    view = {
        "level": transition.level,
        "question": transition.question,
        "action": transition.action,
        "executed": transition.executed,
        "schema_version": transition.schema_version,
        "attempt_index": transition.attempt_index,
        "before": _state_view(transition.before),
        "after": _state_view(transition.after),
        "abstention_origin_before": abstention_origin(
            transition.before.answer, transition.before.answer_relation
        ),
        "abstention_origin_after": abstention_origin(
            transition.after.answer, transition.after.answer_relation
        ),
    }
    assert_no_gold(view)
    return view


def render_prompt(system: str, user: str, forbidden_strings: tuple[str, ...] = ()) -> str:
    """Join a prompt and reject gold strings that are not the question itself."""
    text = system + "\n" + user
    assert_no_gold(json.loads(json.dumps({"system": system, "user": user})))
    for secret in forbidden_strings:
        if secret and secret in text:
            raise GoldLeakageError(f"gold string entered a verifier prompt: {secret!r}")
    return text


def assert_no_gold(value: object) -> None:
    """Walk a JSON-like object and reject forbidden keys."""
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in FORBIDDEN_KEYS:
                raise GoldLeakageError(f"forbidden gold field {key!r}")
            assert_no_gold(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            assert_no_gold(item)


def _state_view(state: object) -> dict[str, Any]:
    from swrag.verification.v2.transitions import StateView

    if not isinstance(state, StateView):
        raise TypeError("state must be a StateView")
    return {
        "answer": state.answer,
        "evidence": [_public_chunk(chunk) for chunk in state.chunks],
        "evidence_known": state.evidence_known,
        "answer_relation": state.answer_relation,
        "evidence_relation": state.evidence_relation,
        "evaluation_source": state.evaluation_source,
        "answer_model": state.answer_model,
        "diagnosis_class": state.diagnosis_class,
    }


def _public_chunk(chunk: dict) -> dict[str, Any]:
    """Keep the text the model saw. Drop anything that is not passage content."""
    assert_no_gold(chunk)
    public: dict[str, Any] = {}
    for key in ("chunk_id", "doc_id", "title", "text", "score", "page"):
        if key in chunk:
            public[key] = chunk[key]
    return public
