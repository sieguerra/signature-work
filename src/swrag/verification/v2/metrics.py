"""Deterministic verification metrics. No model calls."""

from __future__ import annotations

import random
from collections import Counter
from math import comb
from typing import Iterable

from swrag.verification.v2.protocol import BOOTSTRAP_ALPHA, BOOTSTRAP_SAMPLES, CLASSES, SEED

DECIDED = "decided"
UNCERTAIN = "uncertain"
UNAVAILABLE = "unavailable"


def confusion_matrix(
    gold: Iterable[str],
    predicted: Iterable[str],
    *,
    classes: tuple[str, ...] = CLASSES,
) -> dict[str, dict[str, int]]:
    """Rows are gold, columns are predictions. Both must already be class labels."""
    matrix = {label: {column: 0 for column in classes} for label in classes}
    for truth, guess in zip(gold, predicted, strict=True):
        if truth not in matrix or guess not in matrix:
            raise ValueError(f"label outside {classes}: {truth!r} / {guess!r}")
        matrix[truth][guess] += 1
    return matrix


def class_counts(matrix: dict[str, dict[str, int]], label: str) -> tuple[int, int, int]:
    """Return true positives, false positives, false negatives for one class."""
    true_positive = matrix[label][label]
    false_positive = sum(matrix[other][label] for other in matrix if other != label)
    false_negative = sum(count for other, count in matrix[label].items() if other != label)
    return true_positive, false_positive, false_negative


def safe_divide(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def false_improvement_rate(matrix: dict[str, dict[str, int]]) -> float | None:
    """Among predicted improved, the fraction that were not gold-improved.

    Undefined when the verifier predicted improved zero times. That is not a
    rate of zero.
    """
    predicted = sum(matrix[truth]["improved"] for truth in matrix)
    if predicted == 0:
        return None
    false = predicted - matrix["improved"]["improved"]
    return false / predicted


def improved_precision(matrix: dict[str, dict[str, int]]) -> float | None:
    true_positive, false_positive, _false_negative = class_counts(matrix, "improved")
    return safe_divide(true_positive, true_positive + false_positive)


def improved_recall(matrix: dict[str, dict[str, int]]) -> float | None:
    true_positive, _false_positive, false_negative = class_counts(matrix, "improved")
    return safe_divide(true_positive, true_positive + false_negative)


def per_class(matrix: dict[str, dict[str, int]]) -> dict[str, dict[str, float | None]]:
    report: dict[str, dict[str, float | None]] = {}
    for label in matrix:
        true_positive, false_positive, false_negative = class_counts(matrix, label)
        precision = safe_divide(true_positive, true_positive + false_positive)
        recall = safe_divide(true_positive, true_positive + false_negative)
        report[label] = {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
            "support": true_positive + false_negative,
        }
    return report


def accuracy(matrix: dict[str, dict[str, int]]) -> float | None:
    total = sum(sum(row.values()) for row in matrix.values())
    if total == 0:
        return None
    correct = sum(matrix[label][label] for label in matrix)
    return correct / total


def macro_f1(matrix: dict[str, dict[str, int]]) -> float | None:
    """Unweighted mean of per-class F1 over classes that occur in the gold."""
    scores = []
    for label, row in per_class(matrix).items():
        support = row["support"] or 0
        if support == 0:
            continue
        scores.append(0.0 if row["f1"] is None else float(row["f1"]))
    if not scores:
        return None
    return sum(scores) / len(scores)


def weighted_f1(matrix: dict[str, dict[str, int]]) -> float | None:
    total = 0
    weighted = 0.0
    for row in per_class(matrix).values():
        support = int(row["support"] or 0)
        if support == 0:
            continue
        total += support
        weighted += support * (0.0 if row["f1"] is None else float(row["f1"]))
    if total == 0:
        return None
    return weighted / total


def summarize_predictions(rows: list[dict]) -> dict:
    """Score rows that carry gold_label, v1_outcome, v2_outcome, v2_status.

    Decided rows enter the confusion matrix. Uncertain and unavailable rows
    stay in the coverage counts and are not relabeled.
    """
    decided = [
        row
        for row in rows
        if row.get("v2_status") == DECIDED and row.get("v2_outcome") in CLASSES and row.get("gold_label") in CLASSES
    ]
    matrix = confusion_matrix(
        (row["gold_label"] for row in decided),
        (row["v2_outcome"] for row in decided),
    )
    v1_rows = [row for row in rows if row.get("v1_outcome") in CLASSES and row.get("gold_label") in CLASSES]
    v1_matrix = confusion_matrix(
        (row["gold_label"] for row in v1_rows),
        (row["v1_outcome"] for row in v1_rows),
    )
    status_counts = Counter(row.get("v2_status") for row in rows)
    return {
        "n": len(rows),
        "n_decided": len(decided),
        "coverage": safe_divide(len(decided), len(rows)),
        "uncertainty_rate": safe_divide(status_counts[UNCERTAIN], len(rows)),
        "unavailable_rate": safe_divide(status_counts[UNAVAILABLE], len(rows)),
        "accuracy_decided": accuracy(matrix),
        "strict_accuracy": _strict_accuracy(rows),
        "macro_f1": macro_f1(matrix),
        "weighted_f1": weighted_f1(matrix),
        "improved_precision": improved_precision(matrix),
        "improved_recall": improved_recall(matrix),
        "false_improvement_rate": false_improvement_rate(matrix),
        "per_class": per_class(matrix),
        "confusion_matrix": matrix,
        "v1": {
            "n": len(v1_rows),
            "accuracy": accuracy(v1_matrix),
            "macro_f1": macro_f1(v1_matrix),
            "weighted_f1": weighted_f1(v1_matrix),
            "improved_precision": improved_precision(v1_matrix),
            "improved_recall": improved_recall(v1_matrix),
            "false_improvement_rate": false_improvement_rate(v1_matrix),
            "per_class": per_class(v1_matrix),
            "confusion_matrix": v1_matrix,
        },
    }


def paired_bootstrap(
    rows: list[dict],
    *,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = SEED,
    alpha: float = BOOTSTRAP_ALPHA,
) -> dict:
    """Percentile intervals for v2, v1, and v2 − v1 on the same decided rows.

    A row counts only when both verifiers produced a class label. Small n is
    reported through a wide interval, not hidden.
    """
    paired = [
        row
        for row in rows
        if row.get("gold_label") in CLASSES
        and row.get("v1_outcome") in CLASSES
        and row.get("v2_status") == DECIDED
        and row.get("v2_outcome") in CLASSES
    ]
    if len(paired) < 2:
        return {"n": len(paired), "samples": 0, "intervals": None}
    generator = random.Random(seed)
    keys = (
        "accuracy",
        "macro_f1",
        "improved_precision",
        "false_improvement_rate",
        "improved_recall",
    )
    draws = {key: [] for key in keys}
    deltas = {key: [] for key in keys}
    for _ in range(samples):
        sample = [paired[generator.randrange(len(paired))] for _ in paired]
        v2_stats = _point(sample, "v2")
        v1_stats = _point(sample, "v1")
        for key in keys:
            draws[key].append(v2_stats[key])
            left = v1_stats[key]
            right = v2_stats[key]
            deltas[key].append(None if left is None or right is None else right - left)
    return {
        "n": len(paired),
        "samples": samples,
        "alpha": alpha,
        "v2": {key: _interval(draws[key], alpha) for key in keys},
        "delta_v2_minus_v1": {key: _interval(deltas[key], alpha) for key in keys},
    }


def mcnemar_exact(v1_correct: int, v2_correct_only: int) -> dict | None:
    """Exact McNemar test. Arguments are the off-diagonal counts b and c.

    ``v1_correct`` is v1 right and v2 wrong. ``v2_correct_only`` is v2 right
    and v1 wrong. Returns None when both are zero.
    """
    discordant = v1_correct + v2_correct_only
    if discordant == 0:
        return None
    smaller = min(v1_correct, v2_correct_only)
    tail = sum(comb(discordant, index) for index in range(smaller + 1)) / (2**discordant)
    return {
        "v1_only_correct": v1_correct,
        "v2_only_correct": v2_correct_only,
        "p_value": min(1.0, 2 * tail),
    }


def disagreement_counts(rows: list[dict]) -> dict[str, int]:
    v1_only = 0
    v2_only = 0
    both = 0
    neither = 0
    for row in rows:
        if row.get("gold_label") not in CLASSES:
            continue
        if row.get("v1_outcome") not in CLASSES or row.get("v2_status") != DECIDED:
            continue
        v1_hit = row["v1_outcome"] == row["gold_label"]
        v2_hit = row["v2_outcome"] == row["gold_label"]
        if v1_hit and v2_hit:
            both += 1
        elif v1_hit:
            v1_only += 1
        elif v2_hit:
            v2_only += 1
        else:
            neither += 1
    return {
        "both_correct": both,
        "v1_only_correct": v1_only,
        "v2_only_correct": v2_only,
        "both_wrong": neither,
    }


def _point(sample: list[dict], which: str) -> dict[str, float | None]:
    if which == "v1":
        matrix = confusion_matrix(
            (row["gold_label"] for row in sample),
            (row["v1_outcome"] for row in sample),
        )
    else:
        matrix = confusion_matrix(
            (row["gold_label"] for row in sample),
            (row["v2_outcome"] for row in sample),
        )
    return {
        "accuracy": accuracy(matrix),
        "macro_f1": macro_f1(matrix),
        "improved_precision": improved_precision(matrix),
        "false_improvement_rate": false_improvement_rate(matrix),
        "improved_recall": improved_recall(matrix),
    }


def _interval(values: list[float | None], alpha: float) -> dict | None:
    observed = [value for value in values if value is not None]
    if not observed:
        return None
    observed.sort()
    low_index = int((alpha / 2) * (len(observed) - 1))
    high_index = int((1 - alpha / 2) * (len(observed) - 1))
    return {"low": observed[low_index], "high": observed[high_index], "n_defined": len(observed)}


def _strict_accuracy(rows: list[dict]) -> float | None:
    scored = [row for row in rows if row.get("gold_label") in CLASSES]
    if not scored:
        return None
    correct = sum(
        1
        for row in scored
        if row.get("v2_status") == DECIDED and row.get("v2_outcome") == row["gold_label"]
    )
    return correct / len(scored)


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
