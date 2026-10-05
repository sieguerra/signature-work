"""Read-only reliability overview over logical runs.

A trace file is not a user run. Confirm mode writes a parent trace and a
recovery child; those files are one logical run. Auto recovery keeps every
attempt inside one trace. ``summary.json`` is never a run, and this module
does not read gold answers or experiment batch summaries.

Formulas
--------
observed runs
    Every logical run, including retrieve-only and unjudged baseline.

judged runs
    Logical runs with a runtime evaluation (``evidence_sufficient`` present
    on the first pass or the final state).

recovery required
    Judged runs where a non-``accept`` action is still proposed, or where at
    least one non-``accept`` action was applied.
    Rate = that count / judged runs. ``accept`` is not recovery.

verified improved
    Applied logical recoveries whose final verification outcome is
    ``improved``, divided by applied logical recoveries that have a final
    verification outcome.
    Pending proposals, ``accept``, and applied recoveries with no outcome
    are outside the denominator.

unresolved
    Logical runs with a still-pending non-``accept`` proposal, or whose
    final verification is ``still_failing`` or ``degraded``.
    ``unchanged`` is not unresolved. Abstain is not unresolved by itself;
    it counts only when the verification outcome is ``still_failing`` or
    ``degraded``.

runtime signals
    Share of judged runs whose judge flag is true. ``answer_supported``
    null is omitted, not treated as false. Initial and final denominators
    can differ. These are runtime judge signals, not ground-truth accuracy.

latency
    Median of per-run latency. A run's latency is the sum of ``latency_ms``
    on its trace and any recovery child. Runs with no numeric latency are
    left out of the median.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from swrag.api.store import load_trace_payloads

_ACCEPT = frozenset({"", "accept", "none"})
_OUTCOMES = ("improved", "unchanged", "still_failing", "degraded")
_DIAGNOSIS_ORDER = (
    "unsupported_generation",
    "retrieval_miss",
    "evidence_insufficiency",
)
_ATTENTION_RANK = {"degraded": 0, "still_failing": 1, "pending": 2}
_ATTENTION_LIMIT = 8
_ACTIVITY_LIMIT = 8


@dataclass
class LogicalRun:
    """One user run, possibly spanning a parent trace and recovery children."""

    traces: list[dict[str, Any]] = field(default_factory=list)

    @property
    def root(self) -> dict[str, Any]:
        return self.traces[0]

    @property
    def root_id(self) -> str:
        return str(self.root.get("run_id") or "")

    @property
    def is_orphan_child(self) -> bool:
        return bool(self.root.get("parent_run_id"))


def overview_for_traces(traces_dir: str | Path) -> dict[str, Any]:
    """Aggregate the traces in one system directory. Does not mutate files."""
    payloads = load_trace_payloads(traces_dir)
    runs = group_logical_runs(payloads)
    return aggregate_overview(runs)


def logical_run_history(traces_dir: str | Path) -> dict[str, Any]:
    """Every logical run, oldest-independent, newest first.

    Confirm-mode children stay inside the parent run. The list is for opening
    one run in the test console, not for aggregate rates.
    """
    runs = group_logical_runs(load_trace_payloads(traces_dir))
    rows = []
    for run in runs:
        row = _activity_row(run)
        row["trace_ids"] = [
            str(trace.get("run_id") or "") for trace in run.traces if trace.get("run_id")
        ]
        rows.append(row)
    return {"runs": rows}


def group_logical_runs(payloads: list[dict[str, Any]]) -> list[LogicalRun]:
    """Join confirm-mode children onto the parent that started the run.

    A payload with no ``parent_run_id`` starts a logical run. Every trace
    whose ``parent_run_id`` chain leads back to that start is part of the
    same run. A child whose parent file is missing stays one run by itself
    and is not paired with an empty parent. Auto-recovery traces have no
    parent, so they stay one run.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            continue
        by_id[run_id] = payload

    children: dict[str, list[dict[str, Any]]] = {}
    for payload in by_id.values():
        parent_id = payload.get("parent_run_id")
        if not parent_id:
            continue
        children.setdefault(str(parent_id), []).append(payload)

    def descendants(start_id: str, seen: set[str]) -> list[dict[str, Any]]:
        ordered: list[dict[str, Any]] = []
        pending = sorted(children.get(start_id, []), key=_timestamp)
        while pending:
            node = pending.pop(0)
            node_id = str(node.get("run_id") or "")
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            ordered.append(node)
            pending.extend(sorted(children.get(node_id, []), key=_timestamp))
        return ordered

    seen: set[str] = set()
    grouped: list[LogicalRun] = []
    roots = [payload for payload in by_id.values() if not payload.get("parent_run_id")]
    for root in sorted(roots, key=_timestamp):
        root_id = str(root.get("run_id") or "")
        if not root_id or root_id in seen:
            continue
        seen.add(root_id)
        grouped.append(LogicalRun(traces=[root, *descendants(root_id, seen)]))

    for payload in sorted(by_id.values(), key=_timestamp):
        run_id = str(payload.get("run_id") or "")
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        grouped.append(LogicalRun(traces=[payload, *descendants(run_id, seen)]))

    grouped.sort(key=lambda run: _latest_timestamp(run), reverse=True)
    return grouped


def aggregate_overview(runs: list[LogicalRun]) -> dict[str, Any]:
    """Build the overview payload. Rates are null when the denominator is 0."""
    judged = [run for run in runs if _is_judged(run)]
    required = [run for run in judged if _recovery_required(run)]
    applied = [run for run in runs if _applied_actions(run)]
    verified = [(run, _final_outcome(run)) for run in applied]
    verified = [(run, outcome) for run, outcome in verified if outcome]
    improved = [run for run, outcome in verified if outcome == "improved"]
    unresolved = [run for run in runs if _attention_kind(run)]

    outcome_counts = {name: 0 for name in _OUTCOMES}
    other_outcomes = 0
    for _run, outcome in verified:
        if outcome in outcome_counts:
            outcome_counts[outcome] += 1
        else:
            other_outcomes += 1

    diagnoses: dict[str, int] = {}
    for run in runs:
        for name in _diagnosis_classes(run):
            diagnoses[name] = diagnoses.get(name, 0) + 1

    applied_actions: dict[str, int] = {}
    pending_actions: dict[str, int] = {}
    for run in runs:
        for action in _applied_actions(run):
            applied_actions[action] = applied_actions.get(action, 0) + 1
        pending = _pending_action(run)
        if pending:
            pending_actions[pending] = pending_actions.get(pending, 0) + 1

    latencies = [value for value in (_latency(run) for run in runs) if value is not None]
    # Newest first, then stable-sort so degraded outranks still_failing, then pending.
    attention = sorted(unresolved, key=lambda run: _latest_timestamp(run), reverse=True)
    attention.sort(key=lambda run: _ATTENTION_RANK.get(_attention_kind(run) or "", 9))

    activity = sorted(runs, key=lambda run: _latest_timestamp(run), reverse=True)

    return {
        "observed_runs": len(runs),
        "judged_runs": len(judged),
        "recovery_required": _rate(len(required), len(judged)),
        "verified_improved": _rate(len(improved), len(verified)),
        "unresolved": len(unresolved),
        "unchanged": outcome_counts["unchanged"],
        "summary": _summary(len(judged), len(required), len(improved), len(verified)),
        "outcomes": {
            **outcome_counts,
            "other": other_outcomes,
            "with_outcome": len(verified),
            "applied": len(applied),
        },
        "signals": {
            "evidence_sufficient": {
                "initial": _signal_rate(judged, "evidence_sufficient", initial=True),
                "final": _signal_rate(judged, "evidence_sufficient", initial=False),
            },
            "answer_supported": {
                "initial": _signal_rate(judged, "answer_supported", initial=True),
                "final": _signal_rate(judged, "answer_supported", initial=False),
            },
            "note": (
                "Runtime judge signals, not ground-truth accuracy. "
                "Null answer_supported is omitted, not counted as false."
            ),
        },
        "diagnoses": _ordered_counts(diagnoses, _DIAGNOSIS_ORDER),
        "applied_actions": _ordered_counts(
            applied_actions, ("rewrite", "expand", "regenerate", "abstain")
        ),
        "pending_actions": _ordered_counts(
            pending_actions, ("rewrite", "expand", "regenerate", "abstain")
        ),
        "needs_attention": [_attention_row(run) for run in attention[:_ATTENTION_LIMIT]],
        "recent_activity": [_activity_row(run) for run in activity[:_ACTIVITY_LIMIT]],
        "latency": {
            "median_ms": statistics.median(latencies) if latencies else None,
            "runs": len(latencies),
            "definition": (
                "Median of per-run latency. A run's latency is the sum of "
                "latency_ms on its trace and any recovery child. Runs with no "
                "numeric latency are excluded."
            ),
        },
    }


def _summary(judged: int, required: int, improved: int, verified: int) -> str:
    if judged <= 0:
        return "No judged runs yet."
    sentence = f"{required} of {judged} judged runs required recovery."
    if verified <= 0:
        return f"{sentence} Not enough recovery data yet to summarize recovery performance."
    return f"{sentence} {improved} of {verified} applied recoveries were verified as improved."


def _rate(count: int, total: int) -> dict[str, Any]:
    if total <= 0:
        return {"count": 0, "total": 0, "rate": None}
    return {"count": count, "total": total, "rate": count / total}


def _is_judged(run: LogicalRun) -> bool:
    return _initial_eval(run) is not None or _final_eval(run) is not None


def _recovery_required(run: LogicalRun) -> bool:
    return bool(_applied_actions(run) or _pending_action(run))


def _attention_kind(run: LogicalRun) -> str | None:
    outcome = _final_outcome(run) if _applied_actions(run) else None
    if outcome == "degraded":
        return "degraded"
    if outcome == "still_failing":
        return "still_failing"
    if _pending_action(run):
        return "pending"
    return None


def _applied_actions(run: LogicalRun) -> list[str]:
    actions: list[str] = []
    for trace in run.traces:
        actions.extend(_applied_actions_on_trace(trace))
    return actions


def _applied_actions_on_trace(trace: dict[str, Any]) -> list[str]:
    attempts = [item for item in trace.get("recovery_attempts") or [] if isinstance(item, dict)]
    if attempts:
        return [
            action
            for item in attempts
            if (action := _action_name(item.get("action"))) not in _ACCEPT
        ]
    if trace.get("recovery_status") == "proposed":
        return []
    action = _action_name(_recovery(trace).get("action"))
    if action in _ACCEPT:
        return []
    return [action]


def _pending_action(run: LogicalRun) -> str | None:
    if _applied_actions(run):
        return None
    for trace in run.traces:
        if trace.get("recovery_status") != "proposed":
            continue
        action = _action_name(_recovery(trace).get("action"))
        if action not in _ACCEPT:
            return action
    return None


def _final_outcome(run: LogicalRun) -> str | None:
    found: str | None = None
    for trace in run.traces:
        if not _applied_actions_on_trace(trace):
            continue
        outcome = _outcome(trace)
        if outcome:
            found = outcome
    return found


def _outcome(trace: dict[str, Any]) -> str | None:
    verification = trace.get("verification")
    if not isinstance(verification, dict):
        return None
    outcome = verification.get("outcome")
    if outcome is None:
        return None
    text = str(outcome).strip()
    return text or None


def _initial_eval(run: LogicalRun) -> dict[str, Any] | None:
    for trace in run.traces:
        if trace.get("parent_run_id"):
            continue
        evaluation = _evaluation(trace.get("first_pass_evaluation")) or _evaluation(
            trace.get("runtime_evaluation")
        )
        if evaluation is not None:
            return evaluation
    for trace in run.traces:
        evaluation = _evaluation(trace.get("first_pass_evaluation"))
        if evaluation is not None:
            return evaluation
    return None


def _final_eval(run: LogicalRun) -> dict[str, Any] | None:
    for trace in reversed(run.traces):
        evaluation = _evaluation(trace.get("runtime_evaluation"))
        if evaluation is not None:
            return evaluation
    return None


def _evaluation(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict) or "evidence_sufficient" not in value:
        return None
    if not isinstance(value.get("evidence_sufficient"), bool):
        return None
    return value


def _signal_rate(runs: list[LogicalRun], key: str, *, initial: bool) -> dict[str, Any]:
    values: list[bool] = []
    for run in runs:
        evaluation = _initial_eval(run) if initial else _final_eval(run)
        if evaluation is None or key not in evaluation:
            continue
        flag = evaluation.get(key)
        if isinstance(flag, bool):
            values.append(flag)
    if not values:
        return {"true": 0, "total": 0, "rate": None}
    truthy = sum(1 for value in values if value)
    return {"true": truthy, "total": len(values), "rate": truthy / len(values)}


def _diagnosis_classes(run: LogicalRun) -> list[str]:
    found: set[str] = set()
    for trace in run.traces:
        diagnosis = trace.get("diagnosis")
        if isinstance(diagnosis, dict):
            _add_class(found, diagnosis.get("failure_class"))
        for attempt in trace.get("recovery_attempts") or []:
            if isinstance(attempt, dict):
                _add_class(found, attempt.get("attributed_class"))
        _add_class(found, _recovery(trace).get("attributed_class"))
    return _ordered_names(found, _DIAGNOSIS_ORDER)


def _add_class(found: set[str], value: object) -> None:
    if not isinstance(value, str):
        return
    text = value.strip()
    if text and text.lower() != "none":
        found.add(text)


def _latency(run: LogicalRun) -> float | None:
    values = [_number(trace.get("latency_ms")) for trace in run.traces]
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return float(sum(numbers))


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _attention_row(run: LogicalRun) -> dict[str, Any]:
    kind = _attention_kind(run)
    pending = _pending_action(run)
    actions = _applied_actions(run)
    return {
        "kind": kind,
        "logical_run_id": run.root_id,
        "inspect_run_id": _inspect_id(run),
        "query": _query(run),
        "timestamp": _latest_timestamp(run),
        "diagnoses": _diagnosis_classes(run),
        "action": pending or (actions[-1] if actions else None),
        "actions": actions,
        "pending": pending is not None,
        "verification": _final_outcome(run) if actions else None,
    }


def _activity_row(run: LogicalRun) -> dict[str, Any]:
    actions = _applied_actions(run)
    pending = _pending_action(run)
    return {
        "logical_run_id": run.root_id,
        "inspect_run_id": _inspect_id(run),
        "query": _query(run),
        "timestamp": _latest_timestamp(run),
        "initial_state": _initial_state(run),
        "recovery": actions,
        "recovery_pending": pending,
        "verification": _final_outcome(run) if actions else None,
        "latency_ms": _latency(run),
    }


def _inspect_id(run: LogicalRun) -> str:
    if _pending_action(run):
        for trace in run.traces:
            if trace.get("recovery_status") == "proposed":
                return str(trace.get("run_id") or run.root_id)
    for trace in reversed(run.traces):
        if _applied_actions_on_trace(trace):
            return str(trace.get("run_id") or run.root_id)
    return run.root_id


def _initial_state(run: LogicalRun) -> str:
    evaluation = _initial_eval(run)
    if evaluation is None:
        return "not_judged"
    if evaluation.get("evidence_sufficient") is False:
        return "evidence_insufficient"
    supported = evaluation.get("answer_supported")
    if supported is False:
        return "answer_unsupported"
    if supported is True:
        return "answer_supported"
    if evaluation.get("evidence_sufficient") is True:
        return "evidence_sufficient"
    return "not_judged"


def _query(run: LogicalRun) -> str:
    return str(run.root.get("query") or "").strip()[:140]


def _recovery(trace: dict[str, Any]) -> dict[str, Any]:
    recovery = trace.get("recovery")
    return recovery if isinstance(recovery, dict) else {}


def _action_name(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _timestamp(payload: dict[str, Any]) -> str:
    return str(payload.get("timestamp") or "")


def _latest_timestamp(run: LogicalRun) -> str:
    stamps = [_timestamp(trace) for trace in run.traces]
    return max(stamps) if stamps else ""


def _ordered_counts(counts: dict[str, int], preferred: tuple[str, ...]) -> list[dict[str, Any]]:
    names = _ordered_names(set(counts), preferred)
    return [{"name": name, "count": counts[name]} for name in names if counts.get(name)]


def _ordered_names(names: set[str], preferred: tuple[str, ...]) -> list[str]:
    head = [name for name in preferred if name in names]
    tail = sorted(name for name in names if name not in preferred)
    return head + tail
