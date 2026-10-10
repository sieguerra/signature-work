"""Blinded human review. This module never fills in a label."""

from __future__ import annotations

import random
from collections import Counter

from swrag.recovery_benchmark.protocol import SEED
from swrag.verification.v2.benchmark import blind_review_row
from swrag.verification.v2.examples import Example
from swrag.verification.v2.protocol import CLASSES

HUMAN_LABELS = (*CLASSES, "unclear")
_ALIASES = {
    "improved": "improved",
    "unchanged": "unchanged",
    "still failing": "still_failing",
    "still_failing": "still_failing",
    "degraded": "degraded",
    "unclear": "unclear",
    "unclear / cannot determine": "unclear",
    "cannot determine": "unclear",
}
FORBIDDEN_REVIEW_KEYS = frozenset(
    {
        "gold_label",
        "outcome",
        "v1_outcome",
        "v2_outcome",
        "v2_label",
        "action",
        "actions",
        "path",
        "answerable",
        "answers",
        "expected",
        "diagnosis_class",
    }
)


class ReviewContamination(ValueError):
    """A blinded row carried a label or an action."""


def parse_human_label(value: object) -> str | None:
    """Map one reviewer choice. Blank is missing, not unclear."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text not in _ALIASES:
        raise ValueError(f"unknown human label {value!r}")
    return _ALIASES[text]


def select_review_ids(rows: list[dict], *, limit: int = 100, seed: int = SEED) -> list[str]:
    """Stratify recovered analysis runs. Deterministic. Does not assign labels."""
    recovered = [row for row in rows if row.get("recovered") and row.get("panel") != "future_holdout"]
    generator = random.Random(seed)
    buckets: dict[tuple[str, str, bool], list[dict]] = {}
    for row in recovered:
        key = (str(row.get("outcome")), str(row.get("action")), bool(row.get("answerable")))
        buckets.setdefault(key, []).append(row)
    for members in buckets.values():
        members.sort(key=lambda row: str(row["logical_id"]))
        generator.shuffle(members)
    picked: list[str] = []
    seen: set[str] = set()
    while len(picked) < limit:
        progressed = False
        for key in sorted(buckets):
            if len(picked) >= limit:
                break
            members = buckets[key]
            if not members:
                continue
            row = members.pop(0)
            logical_id = str(row["logical_id"])
            if logical_id in seen:
                continue
            seen.add(logical_id)
            picked.append(logical_id)
            progressed = True
        if not progressed:
            break
    return picked


def blinded_export(example: Example, *, review_id: str) -> dict[str, str]:
    """Question and the two states. No gold, verdict, or action."""
    row = {"review_id": review_id, **blind_review_row(example)}
    leaked = FORBIDDEN_REVIEW_KEYS & set(row)
    if leaked:
        raise ReviewContamination(", ".join(sorted(leaked)))
    return row


def assert_blind_payload(payload: dict) -> None:
    leaked = FORBIDDEN_REVIEW_KEYS & set(payload)
    if leaked:
        raise ReviewContamination(", ".join(sorted(leaked)))


def agreement(pairs: list[dict]) -> dict:
    """Human versus automatic gold. Unclear and blank labels are not votes."""
    used = []
    unclear = 0
    missing = 0
    for pair in pairs:
        human = parse_human_label(pair.get("human_label"))
        gold = pair.get("gold_label")
        if human is None:
            missing += 1
            continue
        if human == "unclear":
            unclear += 1
            continue
        if gold not in CLASSES:
            continue
        used.append({**pair, "human_label": human})
    matches = sum(1 for pair in used if pair["human_label"] == pair["gold_label"])
    return {
        "n_compared": len(used),
        "n_unclear_excluded": unclear,
        "n_missing_excluded": missing,
        "matches": matches,
        "rate": None if not used else matches / len(used),
        "by_gold_class": _by(used, "gold_label"),
        "by_answerability": _by(used, "answerable"),
        "by_action": _by(used, "action"),
        "disagreements": [
            {
                "review_id": pair.get("review_id"),
                "logical_id": pair.get("logical_id"),
                "human_label": pair["human_label"],
                "gold_label": pair["gold_label"],
                "answerable": pair.get("answerable"),
                "action": pair.get("action"),
            }
            for pair in used
            if pair["human_label"] != pair["gold_label"]
        ],
    }


def cohens_kappa(left: list[str], right: list[str]) -> dict | None:
    """Raw agreement and Cohen's kappa for two reviewers. None when empty."""
    if len(left) != len(right):
        raise ValueError("reviewer label lists differ in length")
    parsed_left = [parse_human_label(label) for label in left]
    parsed_right = [parse_human_label(label) for label in right]
    pairs = [
        (a, b)
        for a, b in zip(parsed_left, parsed_right, strict=True)
        if a is not None and b is not None and a != "unclear" and b != "unclear"
    ]
    n = len(pairs)
    if n == 0:
        return None
    matches = sum(1 for a, b in pairs if a == b)
    labels = sorted({label for pair in pairs for label in pair})
    count_left = Counter(a for a, _b in pairs)
    count_right = Counter(b for _a, b in pairs)
    chance = sum((count_left[label] / n) * (count_right[label] / n) for label in labels)
    kappa = 1.0 if chance == 1 else (matches / n - chance) / (1 - chance)
    return {"n": n, "agreement": matches / n, "kappa": kappa}


def _by(pairs: list[dict], key: str) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for pair in pairs:
        grouped.setdefault(str(pair.get(key)), []).append(pair)
    report = {}
    for name, members in sorted(grouped.items()):
        matches = sum(1 for pair in members if pair["human_label"] == pair["gold_label"])
        report[name] = {"n": len(members), "matches": matches, "rate": matches / len(members)}
    return report
