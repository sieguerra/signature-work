"""Offline recovery-gate candidates.

These functions read stored first-pass signals. They do not change the live
policy. A candidate is not adopted because it triggers less often. Skipping
a run a human called genuinely bad is a miss, and a miss blocks adoption.
"""

from __future__ import annotations

from swrag.recovery_benchmark.necessity import (
    NEEDED_BEFORE,
    unnecessary_cost,
    parse_before_label,
)
from swrag.recovery_benchmark.review import parse_human_label


def triggers_current(row: dict) -> bool:
    """Frozen first-pass gate, read back from the trace signals."""
    if row.get("evidence_sufficient") is False:
        return True
    if row.get("evidence_sufficient") is True and (row.get("weak_top") or row.get("ambiguous_top")):
        return True
    return False


def triggers_stop_abstention(row: dict) -> bool:
    """Do not recover an explicit abstention when evidence is insufficient.

    A supported or unsupported specific answer still follows the frozen gate.
    """
    if row.get("evidence_sufficient") is False and row.get("before_abstained"):
        return False
    return triggers_current(row)


def triggers_ignore_margin(row: dict) -> bool:
    """Do not recover a judge-accepted supported answer only because the top two scores are close."""
    if (
        row.get("evidence_sufficient") is True
        and row.get("answer_supported") is True
        and not row.get("weak_top")
    ):
        return False
    return triggers_current(row)


def triggers_two_signals(row: dict) -> bool:
    """Recover only when two independent warnings are present.

    Warnings are insufficient evidence, an unsupported answer, a weak top
    score, and an ambiguous top margin. One warning is not enough.
    """
    warnings = 0
    if row.get("evidence_sufficient") is False:
        warnings += 1
    if row.get("answer_supported") is False:
        warnings += 1
    if row.get("weak_top"):
        warnings += 1
    if row.get("ambiguous_top"):
        warnings += 1
    return warnings >= 2


CANDIDATES = {
    "current": triggers_current,
    "stop_explicit_abstention": triggers_stop_abstention,
    "ignore_ambiguous_margin": triggers_ignore_margin,
    "require_two_signals": triggers_two_signals,
}


def simulate(rows: list[dict], rule) -> dict:
    """Score one candidate against human before-state labels.

    Future-holdout rows are refused. Runs without a decided before label are
    counted and left out of the rates.
    """
    if any(row.get("panel") == "future_holdout" for row in rows):
        raise ValueError("future holdout cannot be used to score a gate")
    decided = []
    missing = 0
    for row in rows:
        before = parse_before_label(row.get("before_state"))
        if before is None or before == "unclear":
            missing += 1
            continue
        decided.append({**row, "before_state": before, "would_trigger": bool(rule(row))})
    triggered = [row for row in decided if row["would_trigger"]]
    needed_triggered = [row for row in triggered if row["before_state"] in NEEDED_BEFORE]
    needed = [row for row in decided if row["before_state"] in NEEDED_BEFORE]
    missed_needed = [row for row in needed if not row["would_trigger"]]
    skipped_triggered = [
        row for row in decided if row.get("triggered") and not row["would_trigger"]
    ]
    saved = unnecessary_cost(
        [{**row, "before_state": "correct", "triggered": True} for row in skipped_triggered]
    )
    precision_n = len(triggered)
    return {
        "n_decided": len(decided),
        "n_missing_or_unclear": missing,
        "would_trigger": precision_n,
        "trigger_precision": None if precision_n == 0 else len(needed_triggered) / precision_n,
        "needed": len(needed),
        "needed_still_triggered": len(needed_triggered),
        "needed_missed": len(missed_needed),
        "missed_ids": [row.get("logical_id") for row in missed_needed],
        "triggered_runs_skipped": len(skipped_triggered),
        "estimated_chat_calls_saved": saved["chat_calls"],
        "estimated_latency_ms_saved": saved["added_latency_ms"],
        "estimated_usd_saved": saved["estimated_usd"],
    }


def margin_only_effects(rows: list[dict]) -> dict:
    """What the frozen margin rule would skip. It does not change the live gate.

    A skipped run whose human transition is improved is reported even when the
    before state was already acceptable. That is not the same as missing a bad run.
    """
    if any(row.get("panel") == "future_holdout" for row in rows):
        raise ValueError("future holdout cannot be used to score a gate")
    skipped = []
    for row in rows:
        before = parse_before_label(row.get("before_state"))
        if before is None or before == "unclear":
            continue
        if not row.get("triggered") or triggers_ignore_margin(row):
            continue
        transition = parse_human_label(row.get("transition"))
        skipped.append({**row, "before_state": before, "transition": transition})
    saved = unnecessary_cost(
        [{**row, "before_state": "correct", "triggered": True} for row in skipped]
    )
    def ids(predicate) -> list[str]:
        return [str(row.get("question_id") or row.get("logical_id") or "") for row in skipped if predicate(row)]

    return {
        "recoveries_prevented": len(skipped),
        "bad_runs_lost": ids(lambda row: row["before_state"] in NEEDED_BEFORE),
        "improved_runs_skipped": ids(lambda row: row.get("transition") == "improved"),
        "degraded_runs_prevented": ids(lambda row: row.get("transition") == "degraded"),
        "chat_calls_saved": saved["chat_calls"],
        "latency_ms_saved": saved["added_latency_ms"],
        "estimated_usd_saved": saved["estimated_usd"],
        "implemented": False,
    }


def adopt(results: dict[str, dict]) -> str | None:
    """Return a candidate only when it skips some current triggers and misses no bad run.

    ``current`` is the baseline and is not a proposal. No candidate is
    returned when every alternative still misses a run the human called bad.
    """
    current = results.get("current") or {}
    current_triggers = current.get("would_trigger")
    chosen = None
    for name, result in results.items():
        if name == "current":
            continue
        if result.get("needed_missed"):
            continue
        if not result.get("triggered_runs_skipped"):
            continue
        if current_triggers is not None and result.get("would_trigger", 0) >= current_triggers:
            continue
        if chosen is None or result["would_trigger"] < results[chosen]["would_trigger"]:
            chosen = name
    return chosen
