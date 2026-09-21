"""Recovery controller: select an action from a diagnosis (ADR 006 / 007)."""

from __future__ import annotations

from swrag.diagnosis.diagnose import EVIDENCE_INSUFFICIENCY, UNSUPPORTED_GENERATION
from swrag.evaluation.retrieval_signal import RetrievalSignal
from swrag.recovery.expand import next_top_k
from swrag.types import Diagnosis, RecoveryDecision, RuntimeEvaluation
from swrag.verification.runtime import IMPROVED

REGENERATE = "regenerate"
REWRITE = "rewrite"
EXPAND = "expand"
ABSTAIN = "abstain"
ACCEPT = "accept"

ACTIONS = frozenset({REGENERATE, REWRITE, EXPAND, ABSTAIN, ACCEPT})

TRIGGER_JUDGE = "judge"
TRIGGER_RETRIEVAL_SIGNAL = "retrieval_signal"


def select_recovery(
    diagnosis: Diagnosis | None,
    evaluation: RuntimeEvaluation | None = None,
    signal: RetrievalSignal | None = None,
) -> RecoveryDecision:
    """Choose accept, abstain, rewrite, expand, or regenerate. Never reads gold.

    ``signal`` is a judge-independent read of retrieval quality (issue #64).
    Without it, a run is only ever repaired when the judge admits a failure, so
    a single lenient judge call silently disables the whole system. The signal
    can propose a repair on a run the judge was willing to accept.

    First-pass insufficiency still selects ``rewrite`` so ADR 007 can split
    retrieval miss from corpus gap. A weak retrieval the judge accepted selects
    ``expand`` instead: widening ``top_k`` changes the evidence without a
    rewrite model call (issue #68).
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
            action=EXPAND,
            reason=(
                "judge raised no failure, but retrieval looks unreliable: "
                f"{signal.reason}; widen top_k and retrieve again"
            ),
            trigger=TRIGGER_RETRIEVAL_SIGNAL,
        )
    return RecoveryDecision(
        action=ACCEPT,
        reason="no first-pass failure to recover from",
    )


def select_next_recovery(
    *,
    last: RecoveryDecision,
    verification: object | None,
    evaluation: RuntimeEvaluation | None,
    used: tuple[str, ...],
    current_top_k: int,
) -> RecoveryDecision | None:
    """Pick a different action after an attempt that did not repair the run.

    Never repeats an action already in ``used``. ``expand`` is the preferred
    follow-up because it is the evidence-changing step that does not need a
    rewriter. ``max_recoveries`` is enforced by the orchestrator, not here.
    """
    if last.action in {ACCEPT, ABSTAIN}:
        return None
    outcome = getattr(verification, "outcome", None)
    if outcome == IMPROVED:
        return None
    if (
        evaluation is not None
        and evaluation.evidence_sufficient
        and evaluation.answer_supported is True
    ):
        return None

    used_set = frozenset(used)
    trigger = last.trigger or TRIGGER_JUDGE

    if last.action in {REWRITE, REGENERATE} and EXPAND not in used_set:
        widened = next_top_k(current_top_k)
        if widened is not None:
            return RecoveryDecision(
                action=EXPAND,
                reason=(
                    f"{last.action} did not improve the result; "
                    f"widen top_k from {current_top_k} to {widened} and retrieve again"
                ),
                trigger=trigger,
            )

    if last.action == EXPAND:
        if (
            evaluation is not None
            and evaluation.evidence_sufficient
            and evaluation.answer_supported is False
            and REGENERATE not in used_set
        ):
            return RecoveryDecision(
                action=REGENERATE,
                reason="wider evidence still produced an unsupported answer; regenerate constrained to it",
                trigger=trigger,
            )
        if ABSTAIN not in used_set:
            return RecoveryDecision(
                action=ABSTAIN,
                reason="expanded retrieval did not repair the failure; stop",
                trigger=trigger,
            )
        return None

    if (
        last.action == REWRITE
        and REGENERATE not in used_set
        and evaluation is not None
        and evaluation.evidence_sufficient
    ):
        return RecoveryDecision(
            action=REGENERATE,
            reason="rewrite found evidence but the answer was still unsupported",
            trigger=trigger,
        )

    if ABSTAIN not in used_set:
        return RecoveryDecision(
            action=ABSTAIN,
            reason="no unused evidence-changing action remains; stop",
            trigger=trigger,
        )
    return None
