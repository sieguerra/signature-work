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
    """Compare pre/post flags.

    Sufficiency False→True counts as improved (query-rewrite repaired retrieval).
    Answer-support is the signal for constrained regenerate (same evidence).
    """
    if after.evidence_sufficient and not before.evidence_sufficient:
        return Verification(
            outcome=IMPROVED,
            rationale="evidence_sufficient became true after recovery",
        )
    if before.evidence_sufficient and not after.evidence_sufficient:
        return Verification(
            outcome=DEGRADED,
            rationale="evidence_sufficient became false after recovery",
        )

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
    if after.answer_supported is False or not after.evidence_sufficient:
        return Verification(
            outcome=STILL_FAILING,
            rationale="recovery did not produce a supported, sufficient result",
        )
    return Verification(
        outcome=UNCHANGED,
        rationale="runtime support and sufficiency flags did not change",
    )
