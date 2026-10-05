"""Score shadow predictions and write the offline experiment report.

The promotion rule was frozen in ``protocol.py`` before held-out scoring.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from swrag.verification.v2.candidates import Prediction
from swrag.verification.v2.examples import Example, prediction_row
from swrag.verification.v2.metrics import (
    disagreement_counts,
    mcnemar_exact,
    paired_bootstrap,
    summarize_predictions,
)
from swrag.verification.v2.protocol import (
    MATERIAL_PRECISION_LIFT,
    MAX_MACRO_F1_DROP,
    MAX_MODEL_CALLS_PER_TRANSITION,
    MAX_POSITION_INCONSISTENCY,
    MIN_DECIDED_COVERAGE,
    MIN_DECIDED_FOR_PROMOTION,
    PRICE_PER_MILLION,
    PROTOCOL_VERSION,
    SEED,
)

BLIND_KEYS = (
    "question",
    "before_evidence",
    "before_answer",
    "after_evidence",
    "after_answer",
)


def score_examples(candidate: object, examples: tuple[Example, ...] | list[Example]) -> list[dict]:
    """Call the candidate on the transition only, then attach gold."""
    rows = []
    for example in examples:
        prediction = candidate.predict(example.transition)  # type: ignore[attr-defined]
        if not isinstance(prediction, Prediction):
            raise TypeError("shadow candidate returned a non-prediction")
        rows.append(prediction_row(example, prediction))
    return rows


def blind_review_row(example: Example) -> dict[str, str]:
    """What a human reviewer may see. No verdict, score, or gold label."""
    return {
        "question": example.transition.question,
        "before_evidence": _evidence_text(example.transition.before.chunks),
        "before_answer": example.transition.before.answer,
        "after_evidence": _evidence_text(example.transition.after.chunks),
        "after_answer": example.transition.after.answer,
    }


def select_on_development(summaries: dict[str, dict]) -> str | None:
    """Pick a candidate from development summaries only.

    Surface is a negative control and is not eligible. A candidate that never
    predicts ``improved`` has an undefined false-improvement rate and is not
    selected. Lowest false-improvement rate wins, then higher improved
    precision, then fewer model calls.
    """
    eligible: list[str] = []
    for name, summary in summaries.items():
        if name == "surface":
            continue
        if (summary.get("coverage") or 0) < MIN_DECIDED_COVERAGE:
            continue
        if summary.get("false_improvement_rate") is None:
            continue
        if (summary.get("n_decided") or 0) < 1:
            continue
        eligible.append(name)
    if not eligible:
        return None

    def sort_key(name: str) -> tuple:
        summary = summaries[name]
        return (
            summary["false_improvement_rate"],
            -(summary.get("improved_precision") or 0.0),
            summary.get("mean_model_calls") or 0,
            name,
        )

    return sorted(eligible, key=sort_key)[0]


def recommend(
    v1: dict,
    v2: dict | None,
    bootstrap: dict | None,
    *,
    position_inconsistency: float | None,
    model_calls: float,
    leakage_ok: bool,
    runtime_unchanged: bool,
    answerable_n: int,
    unanswerable_n: int,
) -> str:
    """Map held-out summaries to one promotion level.

    Fewer than ``MIN_DECIDED_FOR_PROMOTION`` decided test rows cannot support
    promotion. A worse false-improvement rate or worse improved precision on
    a large enough test is a reject. Replace requires the paired interval for
    improved precision to lie entirely above zero.
    """
    if not leakage_ok or not runtime_unchanged:
        return "REJECT"
    if v2 is None or (v2.get("n_decided") or 0) < MIN_DECIDED_FOR_PROMOTION:
        return "RESEARCH ONLY"
    if (v2.get("coverage") or 0) < MIN_DECIDED_COVERAGE:
        return "RESEARCH ONLY"

    v2_fir = v2.get("false_improvement_rate")
    v1_fir = v1.get("false_improvement_rate")
    v2_precision = v2.get("improved_precision")
    v1_precision = v1.get("improved_precision")
    v2_f1 = v2.get("macro_f1")
    v1_f1 = v1.get("macro_f1")
    fir_worse = _worse(v2_fir, v1_fir, lower_is_better=True)
    precision_worse = _worse(v2_precision, v1_precision, lower_is_better=False)
    if fir_worse or precision_worse:
        return "REJECT"

    precision_lift = (
        v2_precision is not None
        and v1_precision is not None
        and (v2_precision - v1_precision) >= MATERIAL_PRECISION_LIFT
    )
    fir_better = v2_fir is not None and v1_fir is not None and v2_fir < v1_fir
    f1_ok = v2_f1 is not None and v1_f1 is not None and (v1_f1 - v2_f1) <= MAX_MACRO_F1_DROP
    calls_ok = model_calls <= MAX_MODEL_CALLS_PER_TRANSITION
    position_ok = (
        position_inconsistency is None or position_inconsistency <= MAX_POSITION_INCONSISTENCY
    )
    slices_ok = answerable_n >= 3 and unanswerable_n >= 3
    interval = _precision_interval(bootstrap)
    interval_above_zero = interval is not None and interval["low"] is not None and interval["low"] > 0

    if precision_lift and fir_better and f1_ok and calls_ok and position_ok and slices_ok and interval_above_zero:
        return "REPLACE V1"
    if precision_lift and fir_better and f1_ok and calls_ok:
        return "GUARDED READY"
    strictly_better = (v2_fir is not None and v1_fir is not None and v2_fir < v1_fir) or (
        v2_precision is not None and v1_precision is not None and v2_precision > v1_precision
    )
    if strictly_better and f1_ok:
        return "SHADOW READY"
    return "RESEARCH ONLY"


def write_report(
    output_dir: Path,
    *,
    config: dict[str, Any],
    rows: list[dict],
    candidate: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_predictions(rows)
    summary["mean_model_calls"] = _mean(row.get("model_calls") for row in rows)
    bootstrap = paired_bootstrap(rows)
    counts = disagreement_counts(rows)
    mcnemar = mcnemar_exact(counts["v1_only_correct"], counts["v2_only_correct"])
    cost = _cost(rows, config.get("model"))
    breakdowns = {
        "level": _group(rows, "level"),
        "action": _group(rows, "action"),
        "answerable": _group(rows, "answerable"),
        "failure_class": _group(rows, "failure_class"),
    }
    analysis = error_analysis(rows)
    position = _position_rate(rows)
    payload = {
        "protocol": PROTOCOL_VERSION,
        "seed": SEED,
        "candidate": candidate,
        "summary": summary,
        "bootstrap": bootstrap,
        "mcnemar": mcnemar,
        "disagreement": counts,
        "cost_latency": cost,
        "position_inconsistency": position,
        "breakdowns": breakdowns,
        "error_counts": {name: len(items) for name, items in analysis.items()},
    }
    _write_json(output_dir / "config.json", config)
    _write_jsonl(output_dir / "predictions.jsonl", rows)
    _write_json(output_dir / "metrics.json", payload)
    _write_json(output_dir / "confusion_matrix.json", {
        "v1": summary["v1"]["confusion_matrix"],
        "v2": summary["confusion_matrix"],
        "class_order": ["improved", "unchanged", "still_failing", "degraded"],
    })
    _write_json(output_dir / "cost_latency.json", cost)
    _write_jsonl(output_dir / "errors.jsonl", _flat_errors(analysis))
    (output_dir / "summary.md").write_text(_markdown(config, payload), encoding="utf-8")
    return payload


def error_analysis(rows: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {
        "false_improved": [],
        "missed_improved": [],
        "degraded_as_improved": [],
        "still_failing_as_improved": [],
        "abstention_mistake": [],
        "v1_correct_v2_wrong": [],
        "v2_correct_v1_wrong": [],
        "position_inconsistent": [],
    }
    for row in rows:
        brief = _brief(row)
        gold = row.get("gold_label")
        v2 = row.get("v2_outcome")
        v1 = row.get("v1_outcome")
        decided = row.get("v2_status") == "decided"
        if decided and v2 == "improved" and gold != "improved":
            buckets["false_improved"].append(brief)
        if gold == "improved" and (not decided or v2 != "improved"):
            buckets["missed_improved"].append(brief)
        if decided and gold == "degraded" and v2 == "improved":
            buckets["degraded_as_improved"].append(brief)
        if decided and gold == "still_failing" and v2 == "improved":
            buckets["still_failing_as_improved"].append(brief)
        if _abstention_row(row) and decided and v2 != gold:
            buckets["abstention_mistake"].append(brief)
        if decided and v1 in ("improved", "unchanged", "still_failing", "degraded"):
            v1_hit = v1 == gold
            v2_hit = v2 == gold
            if v1_hit and not v2_hit:
                buckets["v1_correct_v2_wrong"].append(brief)
            if v2_hit and not v1_hit:
                buckets["v2_correct_v1_wrong"].append(brief)
        if row.get("position_consistent") is False:
            buckets["position_inconsistent"].append(brief)
    return buckets


def _markdown(config: dict, payload: dict) -> str:
    summary = payload["summary"]
    v1 = summary["v1"]
    lines = [
        f"# Verification benchmark ({payload['candidate']})",
        "",
        f"Protocol `{payload['protocol']}`. Seed {payload['seed']}.",
        "",
        "This file is an offline experiment record. It does not change runtime verification.",
        "",
        "| Metric | V1 | V2 |",
        "|---|---:|---:|",
    ]
    for key in (
        "accuracy",
        "macro_f1",
        "improved_precision",
        "improved_recall",
        "false_improvement_rate",
    ):
        v1_key = "accuracy" if key == "accuracy" else key
        v1_value = v1.get("accuracy") if key == "accuracy" else v1.get(key)
        v2_value = summary.get("accuracy_decided") if key == "accuracy" else summary.get(key)
        if key == "accuracy":
            v1_value = v1.get("accuracy")
            v2_value = summary.get("accuracy_decided")
        lines.append(f"| {key} | {_fmt(v1_value)} | {_fmt(v2_value)} |")
    lines.extend(
        [
            "",
            f"Decided coverage: {_fmt(summary.get('coverage'))} on n={summary.get('n')}.",
            f"Uncertainty rate: {_fmt(summary.get('uncertainty_rate'))}.",
            f"Unavailable rate: {_fmt(summary.get('unavailable_rate'))}.",
            f"Position inconsistency: {_fmt(payload.get('position_inconsistency'))}.",
            "",
            "V1 confusion rows are gold and columns are predictions, in the order",
            "improved, unchanged, still_failing, degraded.",
            "",
            "```",
            json.dumps(v1.get("confusion_matrix"), indent=2),
            "```",
            "",
            "V2 confusion:",
            "",
            "```",
            json.dumps(summary.get("confusion_matrix"), indent=2),
            "```",
            "",
            f"Config: `{json.dumps(config, sort_keys=True)}`",
            "",
        ]
    )
    return "\n".join(lines)


def _group(rows: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key))].append(row)
    return {name: summarize_predictions(items) for name, items in sorted(groups.items())}


def _position_rate(rows: list[dict]) -> float | None:
    judged = [row for row in rows if row.get("position_consistent") is not None]
    if not judged:
        return None
    inconsistent = sum(1 for row in judged if row["position_consistent"] is False)
    return inconsistent / len(judged)


def _cost(rows: list[dict], model: str | None) -> dict[str, Any]:
    calls = [int(row.get("model_calls") or 0) for row in rows]
    prompt = [row.get("prompt_tokens") for row in rows if isinstance(row.get("prompt_tokens"), int)]
    completion = [
        row.get("completion_tokens") for row in rows if isinstance(row.get("completion_tokens"), int)
    ]
    latency = [float(row["latency_ms"]) for row in rows if isinstance(row.get("latency_ms"), (int, float))]
    prompt_total = sum(prompt) if prompt else None
    completion_total = sum(completion) if completion else None
    return {
        "model": model,
        "n": len(rows),
        "model_calls_total": sum(calls),
        "model_calls_mean": _mean(calls),
        "prompt_tokens_total": prompt_total,
        "completion_tokens_total": completion_total,
        "tokens_observed": bool(prompt) or bool(completion),
        "estimated_cost_usd": _price(model, prompt_total, completion_total),
        "price_note": "List-rate estimate from protocol.PRICE_PER_MILLION. Not an invoice.",
        "latency_ms_p50": _percentile(latency, 50),
        "latency_ms_p95": _percentile(latency, 95),
    }


def _price(model: str | None, prompt: int | None, completion: int | None) -> float | None:
    rates = PRICE_PER_MILLION.get(model or "")
    if rates is None or prompt is None or completion is None:
        return None
    return (prompt / 1_000_000) * rates["input"] + (completion / 1_000_000) * rates["output"]


def _precision_interval(bootstrap: dict | None) -> dict | None:
    if not bootstrap:
        return None
    delta = bootstrap.get("delta_v2_minus_v1") or {}
    return delta.get("improved_precision")


def _worse(candidate: float | None, baseline: float | None, *, lower_is_better: bool) -> bool:
    if candidate is None or baseline is None:
        return False
    if lower_is_better:
        return candidate > baseline
    return candidate < baseline


def _evidence_text(chunks: tuple[dict, ...]) -> str:
    parts = []
    for chunk in chunks:
        text = str(chunk.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _abstention_row(row: dict) -> bool:
    codes = row.get("rationale_codes") or []
    if "abstention_changed" in codes:
        return True
    signals = row.get("signals") or {}
    return signals.get("before_rank") == 1 or signals.get("after_rank") == 1


def _brief(row: dict) -> dict:
    return {
        "question_id": row.get("question_id"),
        "level": row.get("level"),
        "action": row.get("action"),
        "answerable": row.get("answerable"),
        "gold_label": row.get("gold_label"),
        "v1_outcome": row.get("v1_outcome"),
        "v2_outcome": row.get("v2_outcome"),
        "v2_status": row.get("v2_status"),
        "rationale_codes": row.get("rationale_codes"),
        "source": row.get("source"),
    }


def _flat_errors(analysis: dict[str, list[dict]]) -> list[dict]:
    flat = []
    for name, items in analysis.items():
        for item in items:
            flat.append({"kind": name, **item})
    return flat


def _mean(values: Any) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((percentile / 100) * (len(ordered) - 1))
    return ordered[index]


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
