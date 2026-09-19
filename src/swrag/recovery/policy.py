"""Recovery controller: select an action from a diagnosis (ADR 006 / 007)."""

from __future__ import annotations

from swrag.diagnosis.diagnose import EVIDENCE_INSUFFICIENCY, UNSUPPORTED_GENERATION
from swrag.evaluation.retrieval_signal import RetrievalSignal
from swrag.types import Diagnosis, RecoveryDecision, RuntimeEvaluation

REGENERATE = "regenerate"
REWRITE = "rewrite"
ABSTAIN = "abstain"
ACCEPT = "accept"

ACTIONS = frozenset({REGENERATE, REWRITE, ABSTAIN, ACCEPT})

TRIGGER_JUDGE = "judge"
TRIGGER_RETRIEVAL_SIGNAL = "retrieval_signal"


def select_recovery(
    diagnosis: Diagnosis | None,
    evaluation: RuntimeEvaluation | None = None,
    signal: RetrievalSignal | None = None,
) -> RecoveryDecision:
    """Choose accept, abstain, rewrite, or regenerate. Never reads gold labels.

    ``signal`` is a judge-independent read of retrieval quality (issue #64).
    Without it, a run is only ever repaired when the judge admits a failure, so
    a single lenient judge call silently disables the whole system. The signal
    can propose a repair on a run the judge was willing to accept.
    """
    if diagnosis is not None and diagnosis.failure_class == UNSUPPORTED_GENERATION:
        return RecoveryDecision(
            action=REGENERATE,
            reason="unsupported_generation: regenerate constrained to retrieved evidence",
            trigger=TRIGGER_JUDGE,
        )
    if diagnosis is not None and diagnosis.failure_class == EVIDENCE_INSUFFICIENCY:
        return RecoveryDecision(
            action=ABSTAIN,
            reason="evidence_insufficiency after rewrite: stop, do not generate from it",
            trigger=TRIGGER_JUDGE,
        )
    if evaluation is not None and not evaluation.evidence_sufficient:
        return RecoveryDecision(
            action=REWRITE,
            reason="first-pass evidence insufficient: rewrite query and retrieve again",
            trigger=TRIGGER_JUDGE,
        )
    # Only second-guess a judgement that was actually made. With no evaluation
    # there is no verdict to disagree with, and proposing a repair here would
    # drag retrieve-only runs into needing a rewriter and an API key.
    if evaluation is not None and signal is not None and signal.is_weak:
        return RecoveryDecision(
            action=REWRITE,
            reason=(
                "judge raised no failure, but retrieval looks unreliable: "
                f"{signal.reason}"
            ),
            trigger=TRIGGER_RETRIEVAL_SIGNAL,
        )
    return RecoveryDecision(
        action=ACCEPT,
        reason="no first-pass failure to recover from",
    )
