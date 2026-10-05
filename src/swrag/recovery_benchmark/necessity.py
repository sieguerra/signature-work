"""Human before-state and transition labels for the recovery-gate audit.

This module does not choose a label. Blank is missing, not unclear.
Unclear is excluded from rates.

A run needed recovery when the reviewer marked the BEFORE state incorrect
or materially incomplete. A correct answer did not. An appropriate
abstention did not, unless the reviewer instead marked it incorrect or
incomplete. That definition is the one in ``docs/recovery-review-rubric.md``.
"""

from __future__ import annotations

import random
from collections import Counter

from swrag.recovery_benchmark.protocol import (
    BOOTSTRAP_ALPHA,
    BOOTSTRAP_SAMPLES,
    DEMO_CORPUS_ID,
    PRICE_PER_MILLION,
    SEED,
)
from swrag.recovery_benchmark.review import ReviewContamination, parse_human_label
from swrag.recovery_benchmark.scoring import proportion_interval
from swrag.verification.v2.protocol import CLASSES

BEFORE_LABELS = (
    "correct",
    "appropriate_abstention",
    "incorrect",
    "incomplete",
    "unclear",
)
NEEDED_BEFORE = frozenset({"incorrect", "incomplete"})
ACCEPTABLE_BEFORE = frozenset({"correct", "appropriate_abstention"})
NONTRIGGER_LIMIT = 40

_BEFORE_ALIASES = {
    "correct": "correct",
    "correct / acceptable answer": "correct",
    "acceptable": "correct",
    "appropriate abstention": "appropriate_abstention",
    "appropriate_abstention": "appropriate_abstention",
    "incorrect": "incorrect",
    "incorrect / unsupported answer": "incorrect",
    "unsupported": "incorrect",
    "incomplete": "incomplete",
    "incomplete but partially useful": "incomplete",
    "incomplete but materially insufficient": "incomplete",
    "unclear": "unclear",
}

# Loaded by mistake into the review page. The page rejects these keys.
FORBIDDEN_REVIEW_KEYS = frozenset(
    {
        "gold_label",
        "gold_label_paraphrase",
        "gold_label_grounded",
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
        "recommended",
        "recommended_label",
        "diagnosis_class",
        "logical_id",
        "evidence_sufficient",
        "answer_supported",
        "weak_top",
        "ambiguous_top",
    }
)


def parse_before_label(value: object) -> str | None:
    """Map one before-state choice. Blank is missing, not unclear."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text not in _BEFORE_ALIASES:
        raise ValueError(f"unknown before-state label {value!r}")
    return _BEFORE_ALIASES[text]


def needed_recovery(before_label: str | None) -> bool | None:
    """True, false, or None when the before-state was unclear or missing."""
    if before_label in NEEDED_BEFORE:
        return True
    if before_label in ACCEPTABLE_BEFORE:
        return False
    return None


def assert_blind_payload(payload: dict) -> None:
    leaked = FORBIDDEN_REVIEW_KEYS & set(payload)
    if leaked:
        raise ReviewContamination(", ".join(sorted(leaked)))


def select_nontrigger_ids(rows: list[dict], *, limit: int = NONTRIGGER_LIMIT, seed: int = SEED) -> list[str]:
    """Stratify analysis runs that did not recover. Deterministic. No labels.

    Future-holdout rows and the visual demo corpus are never eligible.
    """
    pool = []
    for row in rows:
        if row.get("recovered"):
            continue
        if row.get("panel") == "future_holdout":
            continue
        if row.get("corpus_id") == DEMO_CORPUS_ID:
            continue
        pool.append(row)
    generator = random.Random(seed)
    buckets: dict[tuple[str, bool], list[dict]] = {}
    for row in pool:
        key = (str(row.get("corpus_id")), bool(row.get("answerable")))
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


def assert_analysis_ids(logical_ids: list[str], *, holdout_ids: set[str], demo_ids: set[str] | None = None) -> None:
    """Raise if a review packet contains the reserved holdout or the demo."""
    hit = sorted(set(logical_ids) & holdout_ids)
    if hit:
        raise ReviewContamination("future holdout in review packet: " + ", ".join(hit[:5]))
    demo_hit = sorted(set(logical_ids) & (demo_ids or set()))
    if demo_hit:
        raise ReviewContamination("demo question in review packet: " + ", ".join(demo_hit[:5]))


def gating_report(rows: list[dict]) -> dict:
    """Necessity, unnecessary recovery, and conditional success.

    Each row needs ``before_state`` and, for a triggered run, ``transition``.
    ``triggered`` selects the recovery-applied set. Unclear and blank labels
    are excluded from the rates and counted beside them.
    """
    triggered = [row for row in rows if row.get("triggered")]
    decided = []
    unclear = 0
    missing = 0
    for row in triggered:
        before = parse_before_label(row.get("before_state"))
        if before is None:
            missing += 1
            continue
        if before == "unclear":
            unclear += 1
            continue
        decided.append({**row, "before_state": before})
    needed = [row for row in decided if row["before_state"] in NEEDED_BEFORE]
    acceptable = [row for row in decided if row["before_state"] in ACCEPTABLE_BEFORE]
    by_before = Counter(row["before_state"] for row in decided)
    conditional = _conditional(needed)
    return {
        "definition": (
            "Needed recovery means the before state is incorrect or materially "
            "incomplete. A correct answer and an appropriate abstention do not."
        ),
        "n_triggered": len(triggered),
        "n_decided_before": len(decided),
        "n_before_unclear_excluded": unclear,
        "n_before_missing_excluded": missing,
        "needed": len(needed),
        "acceptable": len(acceptable),
        "already_correct": by_before["correct"],
        "appropriate_abstention": by_before["appropriate_abstention"],
        "other_acceptable": 0,
        "incorrect": by_before["incorrect"],
        "incomplete": by_before["incomplete"],
        "necessity_rate": _rate(len(needed), len(decided)),
        "unnecessary_rate": _rate(len(acceptable), len(decided)),
        "gate_precision": _rate(len(needed), len(decided)),
        "gate_recall": None,
        "gate_recall_note": (
            "Triggered runs alone cannot measure recall. "
            "Misses are estimated only from the reviewed non-trigger sample."
        ),
        "conditional": conditional,
        "human_labels_collected": bool(decided),
    }


def miss_report(rows: list[dict]) -> dict:
    """Before-state judgments on runs that did not trigger recovery."""
    pool = [row for row in rows if not row.get("triggered")]
    decided = []
    unclear = 0
    missing = 0
    for row in pool:
        before = parse_before_label(row.get("before_state"))
        if before is None:
            missing += 1
            continue
        if before == "unclear":
            unclear += 1
            continue
        decided.append(before)
    needed = sum(1 for label in decided if label in NEEDED_BEFORE)
    return {
        "n_reviewed": len(pool),
        "n_decided": len(decided),
        "n_unclear_excluded": unclear,
        "n_missing_excluded": missing,
        "needed": needed,
        "miss_rate": _rate(needed, len(decided)),
        "note": "This is the reviewed non-trigger sample, not the full set of accepts.",
    }


def transition_agreement(pairs: list[dict], *, reference: str = "gold_label") -> dict:
    """Human transition versus one automatic label. Unclear and blank are not votes."""
    used = []
    unclear = 0
    missing = 0
    for pair in pairs:
        human = parse_human_label(pair.get("transition") or pair.get("human_label"))
        other = pair.get(reference)
        if human is None:
            missing += 1
            continue
        if human == "unclear":
            unclear += 1
            continue
        if other not in CLASSES:
            continue
        used.append({**pair, "human_label": human, "gold_label": other})
    matches = sum(1 for pair in used if pair["human_label"] == pair["gold_label"])
    matrix = {label: {column: 0 for column in CLASSES} for label in CLASSES}
    for pair in used:
        matrix[pair["gold_label"]][pair["human_label"]] += 1
    return {
        "reference": reference,
        "n_compared": len(used),
        "n_unclear_excluded": unclear,
        "n_missing_excluded": missing,
        "matches": matches,
        "rate": _rate(matches, len(used)),
        "confusion_human_columns": matrix,
        "disagreements": [
            {
                "review_id": pair.get("review_id"),
                "logical_id": pair.get("logical_id"),
                "human_label": pair["human_label"],
                "reference_label": pair["gold_label"],
            }
            for pair in used
            if pair["human_label"] != pair["gold_label"]
        ],
    }


def unnecessary_cost(rows: list[dict]) -> dict:
    """Added recovery cost on runs a human called already acceptable.

    Token fields are the recovery attempts only, not the first pass.
    The dollar figure uses the frozen list price and is not an invoice.
    """
    kept = []
    for row in rows:
        if not row.get("triggered"):
            continue
        before = parse_before_label(row.get("before_state"))
        if before not in ACCEPTABLE_BEFORE:
            continue
        kept.append(row)
    return _cost_block(kept)


def credited_action(attempts: list[dict], transition: object) -> str | None:
    """Which action first produced the final answer, if the human says improved.

    A rewrite that did not yet show the final answer is not credited when a
    later expand did. Any transition other than improved credits nothing.
    """
    human = parse_human_label(transition)
    if human != "improved" or not attempts:
        return None
    final = _norm(attempts[-1].get("after_answer"))
    previous = ""
    for attempt in attempts:
        after = _norm(attempt.get("after_answer"))
        if after == final and previous != final:
            return str(attempt.get("action") or "") or None
        previous = after
    return str(attempts[-1].get("action") or "") or None


def action_on_needed(rows: list[dict]) -> dict[str, dict]:
    """Run-level human transitions for genuinely bad before states, by path.

    ``credited_action`` is the step that first wrote the final answer when
    the human transition is improved. It is not a rewrite credit for a path
    that only became the final answer at expand.
    """
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not row.get("triggered"):
            continue
        before = parse_before_label(row.get("before_state"))
        if before not in NEEDED_BEFORE:
            continue
        transition = parse_human_label(row.get("transition"))
        if transition is None or transition == "unclear":
            continue
        path = str(row.get("path") or "")
        grouped.setdefault(path, []).append({**row, "transition": transition})
    report = {}
    for path, members in sorted(grouped.items()):
        counts = Counter(row["transition"] for row in members)
        credits = Counter(
            credited_action(row.get("attempts") or [], row["transition"]) or "none"
            for row in members
        )
        report[path] = {
            "n": len(members),
            "improved": counts["improved"],
            "unchanged": counts["unchanged"],
            "still_failing": counts["still_failing"],
            "degraded": counts["degraded"],
            "credited_action": dict(credits),
        }
    return report


def bootstrap_rate(flags: list[bool], *, seed: int = SEED) -> dict:
    """Bootstrap a boolean rate. Empty input has no rate."""
    labels = ["yes" if flag else "no" for flag in flags]
    return proportion_interval(labels, "yes", samples=BOOTSTRAP_SAMPLES, seed=seed, alpha=BOOTSTRAP_ALPHA)


def _conditional(needed: list[dict]) -> dict:
    decided = []
    unclear = 0
    missing = 0
    for row in needed:
        transition = parse_human_label(row.get("transition"))
        if transition is None:
            missing += 1
            continue
        if transition == "unclear":
            unclear += 1
            continue
        decided.append(transition)
    counts = Counter(decided)
    return {
        "n_needed": len(needed),
        "n_decided_transition": len(decided),
        "n_transition_unclear_excluded": unclear,
        "n_transition_missing_excluded": missing,
        "improved": counts["improved"],
        "unchanged": counts["unchanged"],
        "still_failing": counts["still_failing"],
        "degraded": counts["degraded"],
        "success_rate": _rate(counts["improved"], len(decided)),
    }


def _cost_block(rows: list[dict]) -> dict:
    chat = prompt = completion = embedding = 0
    latency = 0.0
    for row in rows:
        for attempt in row.get("attempts") or []:
            chat += int(attempt.get("chat_calls") or 0)
            prompt += int(attempt.get("prompt_tokens") or 0)
            completion += int(attempt.get("completion_tokens") or 0)
            embedding += int(attempt.get("embedding_tokens") or 0)
        latency += float(row.get("added_latency_ms") or 0)
    prices = PRICE_PER_MILLION["gpt-4o-mini"]
    embed_price = PRICE_PER_MILLION["text-embedding-3-small"]["input"]
    usd = (
        prompt / 1_000_000 * prices["input"]
        + completion / 1_000_000 * prices["output"]
        + embedding / 1_000_000 * embed_price
    )
    n = len(rows)
    return {
        "n": n,
        "chat_calls": chat,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "embedding_tokens": embedding,
        "added_latency_ms": latency,
        "mean_added_latency_ms": None if n == 0 else latency / n,
        "estimated_usd": usd,
        "price_note": "list price estimate, not an invoice",
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _norm(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()
