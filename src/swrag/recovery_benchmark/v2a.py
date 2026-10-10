"""Offline reads of the v2A policies. This module does not run the model.

Trigger metrics replay ``select_recovery`` on stored first-pass signals.
They do not read gold, and they do not change the live default policy.
"""

from __future__ import annotations

from collections import Counter

from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.evaluation.retrieval_signal import RetrievalSignal
from swrag.recovery.policy import (
    ACCEPT,
    DEFAULT_POLICY,
    POLICIES,
    normalize_policy,
    select_recovery,
)
from swrag.recovery_benchmark.necessity import (
    ACCEPTABLE_BEFORE,
    NEEDED_BEFORE,
    parse_before_label,
    parse_human_label,
)
from swrag.types import RuntimeEvaluation

PROMOTION_RULES = (
    "On the human-reviewed development rows, gate precision is higher than v1 "
    "or unnecessary interventions are fewer.",
    "Every human-needed run that v1 triggered is still triggered.",
    "Fresh conditional success, scored offline on the same first-pass states, "
    "is at least the v1 rate.",
    "Fresh degraded count does not rise.",
    "Recovery cost or added latency is lower, or the increase is small beside a gain.",
)


def replay_action(row: dict, policy: str = DEFAULT_POLICY) -> str:
    """First action the named policy would choose from stored first-pass signals."""
    chosen = normalize_policy(policy)
    if chosen not in POLICIES:
        raise ValueError(chosen)
    evaluation = _evaluation(row)
    signal = _signal(row)
    diagnosis = diagnose_runtime(evaluation) if evaluation is not None else None
    return select_recovery(diagnosis, evaluation, signal, policy=chosen).action


def retrospective_report(rows: list[dict], policies: tuple[str, ...]) -> dict:
    """Human-label trigger metrics. Unclear before-states stay out of the rates.

    A run the policy would not start keeps the before answer. Historical
    transition labels are used only for runs whose first action is unchanged,
    because a different action needs a fresh generation.
    """
    if any(row.get("panel") == "future_holdout" for row in rows):
        raise ValueError("future holdout cannot be used to score a policy")
    report = {}
    for policy in policies:
        report[policy] = _one_policy(rows, policy)
    return report


def _one_policy(rows: list[dict], policy: str) -> dict:
    decided = []
    unclear = 0
    for row in rows:
        before = parse_before_label(row.get("before_state"))
        if before is None or before == "unclear":
            if before == "unclear":
                unclear += 1
            continue
        action = replay_action(row, policy)
        historical = str(row.get("historical_action") or "")
        decided.append(
            {
                **row,
                "before_state": before,
                "action": action,
                "triggered": action != ACCEPT,
                "action_unchanged": action == historical,
            }
        )
    triggered = [row for row in decided if row["triggered"]]
    needed = [row for row in decided if row["before_state"] in NEEDED_BEFORE]
    needed_triggered = [row for row in triggered if row["before_state"] in NEEDED_BEFORE]
    acceptable_triggered = [row for row in triggered if row["before_state"] in ACCEPTABLE_BEFORE]
    missed = [row for row in needed if not row["triggered"]]
    comparable = [
        row
        for row in triggered
        if row["action_unchanged"] and parse_human_label(row.get("transition")) not in (None, "unclear")
    ]
    transitions = Counter(parse_human_label(row.get("transition")) for row in comparable)
    return {
        "policy": policy,
        "n_decided": len(decided),
        "n_unclear_excluded": unclear,
        "triggered": len(triggered),
        "needed": len(needed),
        "needed_triggered": len(needed_triggered),
        "needed_missed": [str(row.get("question_id") or "") for row in missed],
        "gate_precision": _rate(len(needed_triggered), len(triggered)),
        "unnecessary_recovery": len(acceptable_triggered),
        "unnecessary_rate": _rate(len(acceptable_triggered), len(triggered)),
        "historical_transitions_still_applicable": len(comparable),
        "historical_improved": transitions["improved"],
        "historical_degraded": transitions["degraded"],
        "note": (
            "Precision uses the frozen human before-state. Transition counts "
            "include only runs whose first action did not change."
        ),
    }


def _evaluation(row: dict) -> RuntimeEvaluation | None:
    if "evidence_sufficient" not in row:
        return None
    return RuntimeEvaluation(
        evidence_sufficient=bool(row.get("evidence_sufficient")),
        answer_supported=row.get("answer_supported"),
        sufficiency_rationale="replay",
        support_rationale="replay",
        judge="replay",
        model="replay",
    )


def _signal(row: dict) -> RetrievalSignal | None:
    if "ambiguous_top" not in row and "weak_top" not in row:
        return None
    return RetrievalSignal(
        top_score=row.get("top_score"),
        runner_up_score=row.get("runner_up_score"),
        relative_margin=row.get("relative_margin"),
        weak_top=bool(row.get("weak_top")),
        ambiguous_top=bool(row.get("ambiguous_top")),
        reason="replay",
    )


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
