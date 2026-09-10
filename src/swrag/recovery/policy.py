"""Recovery controller: select an action from a diagnosis (ADR 006 / 007)."""

from __future__ import annotations

from swrag.diagnosis.diagnose import EVIDENCE_INSUFFICIENCY, UNSUPPORTED_GENERATION
from swrag.types import Diagnosis, RecoveryDecision, RuntimeEvaluation

REGENERATE = "regenerate"
REWRITE = "rewrite"
ABSTAIN = "abstain"
ACCEPT = "accept"

ACTIONS = frozenset({REGENERATE, REWRITE, ABSTAIN, ACCEPT})


def select_recovery(
    diagnosis: Diagnosis | None,
    evaluation: RuntimeEvaluation | None = None,
) -> RecoveryDecision:
    """Choose accept, abstain, rewrite, or regenerate. Never reads gold labels."""
    if diagnosis is not None and diagnosis.failure_class == UNSUPPORTED_GENERATION:
        return RecoveryDecision(
            action=REGENERATE,
            reason="unsupported_generation: regenerate constrained to retrieved evidence",
        )
    if diagnosis is not None and diagnosis.failure_class == EVIDENCE_INSUFFICIENCY:
        return RecoveryDecision(
            action=ABSTAIN,
            reason="evidence_insufficiency after rewrite: stop, do not generate from it",
        )
    if evaluation is not None and not evaluation.evidence_sufficient:
        return RecoveryDecision(
            action=REWRITE,
            reason="first-pass evidence insufficient: rewrite query and retrieve again",
        )
    return RecoveryDecision(
        action=ACCEPT,
        reason="no first-pass failure to recover from",
    )
