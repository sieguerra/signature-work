"""Recovery controller: select an action from a diagnosis (ADR 006 / 007)."""

from __future__ import annotations

from swrag.diagnosis.diagnose import EVIDENCE_INSUFFICIENCY, UNSUPPORTED_GENERATION
from swrag.evaluation.retrieval_signal import RetrievalSignal
from swrag.recovery.expand import next_top_k
from swrag.recovery.gap_signal import assess_evidence
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

# Research policies. The product loop defaults to v1 and does not switch itself.
POLICY_V1 = "v1"
POLICY_V2A_MARGIN = "v2a_margin"
POLICY_V2A_EXPAND_FIRST = "v2a_expand_first"
POLICY_V2A_COMBINED = "v2a_combined"
POLICY_V2C_EXPAND_STOP = "v2c_expand_stop"
POLICY_V2C_GAP_AWARE = "v2c_gap_aware"
POLICIES = frozenset(
    {
        POLICY_V1,
        POLICY_V2A_MARGIN,
        POLICY_V2A_EXPAND_FIRST,
        POLICY_V2A_COMBINED,
        POLICY_V2C_EXPAND_STOP,
        POLICY_V2C_GAP_AWARE,
    }
)
DEFAULT_POLICY = POLICY_V1

# Product choices. ``gap_aware`` is the guarded opt-in. It maps to the frozen
# Phase 8C policy and is not the default.
PRODUCT_CURRENT = "v1"
PRODUCT_GAP_AWARE = "gap_aware"
_PRODUCT_TO_INTERNAL = {
    PRODUCT_CURRENT: POLICY_V1,
    PRODUCT_GAP_AWARE: POLICY_V2C_GAP_AWARE,
    POLICY_V2C_GAP_AWARE: POLICY_V2C_GAP_AWARE,
}


def resolve_product_policy(policy: str | None) -> str:
    """Map an explicit product choice onto the internal policy name.

    A blank value is v1. Research-only names such as the margin gate are
    rejected here so a product caller cannot turn them on by accident.
    """
    if policy is None or str(policy).strip() == "":
        return POLICY_V1
    chosen = str(policy).strip()
    if chosen not in _PRODUCT_TO_INTERNAL:
        allowed = ", ".join(sorted({PRODUCT_CURRENT, PRODUCT_GAP_AWARE}))
        raise ValueError(f"recovery_policy must be one of {allowed}")
    return _PRODUCT_TO_INTERNAL[chosen]


def canonical_policy(policy: str | None) -> str:
    """Accept a product name or an internal research name."""
    text = "" if policy is None else str(policy).strip()
    if text in _PRODUCT_TO_INTERNAL:
        return _PRODUCT_TO_INTERNAL[text]
    return normalize_policy(policy)


def normalize_policy(policy: str | None) -> str:
    """Return a known policy name. Blank means the current product policy."""
    chosen = DEFAULT_POLICY if policy is None or str(policy).strip() == "" else str(policy).strip()
    if chosen not in POLICIES:
        raise ValueError(f"unknown recovery policy: {chosen}")
    return chosen


def uses_margin_gate(policy: str) -> bool:
    return normalize_policy(policy) in {POLICY_V2A_MARGIN, POLICY_V2A_COMBINED}


def uses_expand_first(policy: str) -> bool:
    return normalize_policy(policy) in {POLICY_V2A_EXPAND_FIRST, POLICY_V2A_COMBINED}


def opens_with_expand(policy: str) -> bool:
    """Insufficient evidence expands before any rewrite."""
    chosen = normalize_policy(policy)
    return uses_expand_first(chosen) or chosen in {POLICY_V2C_EXPAND_STOP, POLICY_V2C_GAP_AWARE}


def uses_gap_block(policy: str) -> bool:
    """Candidate B replaces a conflicting or neighbor-fact answer with a stop."""
    return normalize_policy(policy) == POLICY_V2C_GAP_AWARE


def margin_only_trigger(
    evaluation: RuntimeEvaluation | None,
    signal: RetrievalSignal | None,
) -> bool:
    """True only when the ambiguous margin is the sole reason to intervene.

    Insufficient evidence, an unsupported answer, a weak top score, or a
    missing judgement are not this case. The signal itself is unchanged.
    """
    if evaluation is None or signal is None:
        return False
    if not evaluation.evidence_sufficient or evaluation.answer_supported is not True:
        return False
    if signal.weak_top or not signal.ambiguous_top:
        return False
    return True


def select_recovery(
    diagnosis: Diagnosis | None,
    evaluation: RuntimeEvaluation | None = None,
    signal: RetrievalSignal | None = None,
    policy: str = DEFAULT_POLICY,
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
    chosen = normalize_policy(policy)
    if evaluation is not None and not evaluation.evidence_sufficient:
        if opens_with_expand(chosen):
            return RecoveryDecision(
                action=EXPAND,
                reason=(
                    "first-pass evidence insufficient: expand the original query "
                    "before any rewrite"
                ),
                trigger=TRIGGER_JUDGE,
                parameters={"policy": chosen, "search_query": "original"},
            )
        return RecoveryDecision(
            action=REWRITE,
            reason="first-pass evidence insufficient: rewrite query and retrieve again",
            trigger=TRIGGER_JUDGE,
            parameters=None if chosen == POLICY_V1 else {"policy": chosen},
        )
    # Only second-guess a judgement that was actually made. With no evaluation
    # there is no verdict to disagree with, and proposing a repair here would
    # drag retrieve-only runs into needing a rewriter and an API key.
    if evaluation is not None and signal is not None and signal.is_weak:
        if margin_only_trigger(evaluation, signal) and uses_margin_gate(chosen):
            return RecoveryDecision(
                action=ACCEPT,
                reason=(
                    "evidence is sufficient and the answer is supported; "
                    "ambiguous top-two margin was observed and did not trigger recovery"
                ),
                trigger=TRIGGER_RETRIEVAL_SIGNAL,
                parameters={
                    "policy": chosen,
                    "ambiguous_top_observed": True,
                    "intervened_on_margin": False,
                },
            )
        return RecoveryDecision(
            action=EXPAND,
            reason=(
                "judge raised no failure, but retrieval looks unreliable: "
                f"{signal.reason}; widen top_k and retrieve again"
            ),
            trigger=TRIGGER_RETRIEVAL_SIGNAL,
            parameters=None if chosen == POLICY_V1 else {"policy": chosen},
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
    policy: str = DEFAULT_POLICY,
    question: str = "",
    evidence_texts: tuple[str, ...] = (),
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
    chosen = normalize_policy(policy)

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
        if uses_expand_first(chosen) and REWRITE not in used_set:
            return RecoveryDecision(
                action=REWRITE,
                reason=(
                    "expand on the original query did not repair the failure; "
                    f"rewrite and retrieve again at the expanded top_k {current_top_k}"
                ),
                trigger=trigger,
                parameters={
                    "policy": chosen,
                    "search_query": "rewritten",
                    "rewrite_top_k": "expanded",
                    "top_k": current_top_k,
                },
            )
        if chosen in {POLICY_V2C_EXPAND_STOP, POLICY_V2C_GAP_AWARE} and ABSTAIN not in used_set:
            return _after_expand_v2c(
                chosen,
                trigger=trigger,
                question=question,
                evidence_texts=evidence_texts,
                used=used_set,
                current_top_k=current_top_k,
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


def _after_expand_v2c(
    chosen: str,
    *,
    trigger: str,
    question: str,
    evidence_texts: tuple[str, ...],
    used: frozenset[str],
    current_top_k: int,
) -> RecoveryDecision:
    """Expand has already run. Stop, or rewrite only on a query-mismatch signal."""
    assessment = assess_evidence(question, evidence_texts)
    forced_stop = chosen == POLICY_V2C_EXPAND_STOP
    if chosen == POLICY_V2C_GAP_AWARE and assessment.allows_rewrite and REWRITE not in used:
        return RecoveryDecision(
            action=REWRITE,
            reason=assessment.reason,
            trigger=trigger,
            parameters={
                **assessment.as_parameters(forced_stop=False),
                "policy": chosen,
                "search_query": "rewritten",
                "rewrite_top_k": "expanded",
                "top_k": current_top_k,
            },
        )
    return RecoveryDecision(
        action=ABSTAIN,
        reason=assessment.as_parameters(forced_stop=forced_stop)["stop_reason"],
        trigger=trigger,
        parameters={**assessment.as_parameters(forced_stop=forced_stop), "policy": chosen},
    )
