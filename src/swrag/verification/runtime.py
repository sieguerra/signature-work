"""Runtime verification: did recovery help, hurt, or change nothing?

Uses the grounding judge flags only. Gold labels are for offline scoring of
whether this verdict itself was correct (ADR 002 / ADR 003).
"""

from __future__ import annotations

from swrag.types import RuntimeEvaluation, Verification

IMPROVED = "improved"
UNCHANGED = "unchanged"
DEGRADED = "degraded"
STILL_FAILING = "still_failing"

OUTCOMES = frozenset({IMPROVED, UNCHANGED, DEGRADED, STILL_FAILING})


def verify_runtime(
    before: RuntimeEvaluation,
    after: RuntimeEvaluation,
) -> Verification:
    """Compare pre/post answer-support. Sufficiency is expected to stay put
    for regenerate (same evidence).
    """
    before_ok = before.answer_supported is True
    after_ok = after.answer_supported is True

    if after_ok and not before_ok:
        return Verification(
            outcome=IMPROVED,
            rationale="answer_supported became true after recovery",
        )
    if before_ok and not after_ok:
        return Verification(
            outcome=DEGRADED,
            rationale="answer_supported became false after recovery",
        )
    if after.answer_supported is False:
        return Verification(
            outcome=STILL_FAILING,
            rationale="answer remained unsupported after recovery",
        )
    return Verification(
        outcome=UNCHANGED,
        rationale="runtime support flags did not change",
    )
