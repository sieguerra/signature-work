"""Recovery controller: select an action from a diagnosis (ADR 006)."""

from __future__ import annotations

from swrag.diagnosis.diagnose import UNSUPPORTED_GENERATION
from swrag.types import Diagnosis, RecoveryDecision, RuntimeEvaluation

REGENERATE = "regenerate"
ABSTAIN = "abstain"
ACCEPT = "accept"

ACTIONS = frozenset({REGENERATE, ABSTAIN, ACCEPT})


def select_recovery(
    diagnosis: Diagnosis | None,
    evaluation: RuntimeEvaluation | None = None,
) -> RecoveryDecision:
    """Choose accept, abstain, or regenerate. Never reads gold labels."""
    if diagnosis is not None and diagnosis.failure_class == UNSUPPORTED_GENERATION:
        return RecoveryDecision(
            action=REGENERATE,
            reason="unsupported_generation: regenerate constrained to retrieved evidence",
        )
    if evaluation is not None and not evaluation.evidence_sufficient:
        return RecoveryDecision(
            action=ABSTAIN,
            reason="evidence judged insufficient; do not regenerate from it",
        )
    return RecoveryDecision(
        action=ACCEPT,
        reason="no first-pass failure to recover from",
    )
