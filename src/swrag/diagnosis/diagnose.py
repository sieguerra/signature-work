"""First-pass failure diagnosis from runtime grounding signals.

V1 class ids (student-confirmed, issue #7):

- ``retrieval_miss``
- ``evidence_insufficiency``
- ``unsupported_generation``

This module implements **one** class: ``unsupported_generation``. That is the
only class separable on a single retrieval pass without gold labels. The other
two both look like ``evidence_sufficient is False`` until a query-rewrite
recovery runs.
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


def diagnose_runtime(evaluation: RuntimeEvaluation) -> Diagnosis:
    """Map runtime flags to at most one V1 class.

    Does not read gold labels. Does not emit ``retrieval_miss`` or
    ``evidence_insufficiency``; those need the retrieval-recovery outcome.
    """
    diagnosis = _diagnose(evaluation)
    if diagnosis.failure_class is not None and diagnosis.failure_class not in V1_FAILURE_CLASSES:
        raise ValueError(f"unknown failure class {diagnosis.failure_class!r}")
    return diagnosis


def _diagnose(evaluation: RuntimeEvaluation) -> Diagnosis:
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
