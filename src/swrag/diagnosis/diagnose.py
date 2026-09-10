"""Failure diagnosis from runtime grounding signals.

V1 class ids (student-confirmed, issue #7 / ADR 005):

- ``retrieval_miss``
- ``evidence_insufficiency``
- ``unsupported_generation``

``unsupported_generation`` is separable on the first pass. ``retrieval_miss``
and ``evidence_insufficiency`` are attributed only after a query-rewrite
recovery (ADR 007).
"""

from __future__ import annotations

from swrag.types import Diagnosis, RuntimeEvaluation

V1_FAILURE_CLASSES = frozenset(
    {
        "retrieval_miss",
        "evidence_insufficiency",
        "unsupported_generation",
    }
)

UNSUPPORTED_GENERATION = "unsupported_generation"
RETRIEVAL_MISS = "retrieval_miss"
EVIDENCE_INSUFFICIENCY = "evidence_insufficiency"


def diagnose_runtime(evaluation: RuntimeEvaluation) -> Diagnosis:
    """First-pass diagnosis. Does not read gold labels.

    Does not emit ``retrieval_miss`` or ``evidence_insufficiency``; those
    require ``diagnose_after_rewrite``.
    """
    diagnosis = _diagnose_first_pass(evaluation)
    return _checked(diagnosis)


def diagnose_after_rewrite(
    before: RuntimeEvaluation,
    after: RuntimeEvaluation,
) -> Diagnosis:
    """Attribute miss vs corpus-gap from the rewrite outcome."""
    if after.evidence_sufficient and not before.evidence_sufficient:
        return _checked(
            Diagnosis(
                failure_class=RETRIEVAL_MISS,
                rationale=(
                    "First-pass evidence was insufficient; after query rewrite "
                    "it became sufficient."
                ),
                detector="rewrite-outcome",
            )
        )
    if not after.evidence_sufficient:
        return _checked(
            Diagnosis(
                failure_class=EVIDENCE_INSUFFICIENCY,
                rationale=(
                    "Evidence remained insufficient after query rewrite "
                    "and a second retrieve."
                ),
                detector="rewrite-outcome",
            )
        )
    return diagnose_runtime(after)


def _checked(diagnosis: Diagnosis) -> Diagnosis:
    if diagnosis.failure_class is not None and diagnosis.failure_class not in V1_FAILURE_CLASSES:
        raise ValueError(f"unknown failure class {diagnosis.failure_class!r}")
    return diagnosis


def _diagnose_first_pass(evaluation: RuntimeEvaluation) -> Diagnosis:
    if evaluation.answer_supported is None and not evaluation.evidence_sufficient:
        return Diagnosis(
            failure_class=None,
            rationale=(
                "Evidence was judged insufficient. retrieval_miss vs "
                "evidence_insufficiency is not diagnosed on the first pass."
            ),
        )
    if evaluation.answer_supported is None:
        return Diagnosis(
            failure_class=None,
            rationale="No generated answer, so answer support cannot be judged.",
        )
    if evaluation.evidence_sufficient and evaluation.answer_supported is False:
        return Diagnosis(
            failure_class=UNSUPPORTED_GENERATION,
            rationale=(
                "Retrieved evidence was judged sufficient, but the answer was "
                "not supported by that evidence."
            ),
        )
    if not evaluation.evidence_sufficient:
        return Diagnosis(
            failure_class=None,
            rationale=(
                "Evidence was judged insufficient. retrieval_miss vs "
                "evidence_insufficiency is not diagnosed on the first pass."
            ),
        )
    return Diagnosis(
        failure_class=None,
        rationale="Evidence was sufficient and the answer was supported.",
    )
