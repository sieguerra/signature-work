"""Offline scoring for gap-aware recovery. The runtime does not import this module."""

from __future__ import annotations

import hashlib
from collections import defaultdict

SPLIT_SEED = "20261007-gap"
HOLDOUT_RESIDUE = 0
HOLDOUT_MODULUS = 3

STRATA = (
    "expand_recoverable",
    "rewrite_recoverable",
    "corpus_gap",
    "partial",
    "neighbor_fact",
    "version_conflict",
    "already_supported",
)

SUBSTANTIVE = frozenset({"expand_recoverable", "rewrite_recoverable", "already_supported"})
ABSTAIN_STRATA = frozenset({"corpus_gap", "partial", "neighbor_fact"})
RUNTIME_FORBIDDEN = frozenset(
    {
        "stratum",
        "corpus_answerability",
        "recoverability_class",
        "supporting_passage",
        "supporting_rank",
        "human_before",
        "human_transition",
        "forbidden_substrings",
        "required_substrings",
        "both_values",
        "fair_rewrite_query",
        "benchmark_answerable",
    }
)


def assign_panels(rows: list[dict]) -> list[dict]:
    """Deterministic development/holdout split. Every stratum appears in both."""
    assigned = []
    for row in rows:
        panel = "holdout" if _residue(row["question_id"]) == HOLDOUT_RESIDUE else "development"
        assigned.append({**row, "panel": panel})
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for row in assigned:
        by_stratum[row["stratum"]].append(row)
    for stratum, group in by_stratum.items():
        if stratum not in STRATA:
            raise ValueError(f"unknown stratum: {stratum}")
        _cover(group)
    return assigned


def score_case(case: dict, answer: str, *, actions: list[str]) -> dict:
    """Score one finished answer against offline stratum metadata."""
    text = answer or ""
    refused = _refused(text)
    stratum = case["stratum"]
    forbidden = [item for item in case.get("forbidden_substrings") or [] if item and item in text]
    if stratum in SUBSTANTIVE:
        required = case.get("required_substrings") or []
        success = (not refused) and all(item in text for item in required) and not forbidden
        kind = "answer_recovery" if stratum != "already_supported" else "already_supported"
    elif stratum == "version_conflict":
        both = case.get("both_values") or []
        mentions_both = all(item in text for item in both) if both else False
        success = (refused or mentions_both) and not (forbidden and not mentions_both)
        kind = "conflict_stop"
    elif stratum in ABSTAIN_STRATA:
        success = refused and not forbidden
        kind = "safe_failure"
    else:
        raise ValueError(f"unknown stratum: {stratum}")
    non_abstain = [action for action in actions if action != "abstain"]
    return {
        "question_id": case["question_id"],
        "stratum": stratum,
        "panel": case.get("panel"),
        "success": success,
        "kind": kind,
        "refused": refused,
        "actions": list(actions),
        "rewrite_ran": "rewrite" in actions,
        "recovery_actions": len(non_abstain),
    }


def summarize(scored: list[dict]) -> dict:
    """Separate answer recovery from safe failure. Do not collapse them."""
    def rate(rows: list[dict]) -> dict:
        if not rows:
            return {"n": 0, "successes": 0, "rate": None}
        hits = sum(1 for row in rows if row["success"])
        return {"n": len(rows), "successes": hits, "rate": hits / len(rows)}

    by_stratum = {}
    for stratum in STRATA:
        by_stratum[stratum] = rate([row for row in scored if row["stratum"] == stratum])
    recoverable = [
        row for row in scored if row["stratum"] in {"expand_recoverable", "rewrite_recoverable"}
    ]
    gaps = [row for row in scored if row["stratum"] in {"corpus_gap", "partial"}]
    rewrites = [row for row in scored if row["rewrite_ran"]]
    useful = [
        row
        for row in rewrites
        if row["stratum"] == "rewrite_recoverable" and row["success"]
    ]
    gap_actions = sum(row["recovery_actions"] for row in gaps)
    return {
        "n": len(scored),
        "by_stratum": by_stratum,
        "answer_recovery": rate(recoverable),
        "safe_failure": rate(gaps),
        "rewrite_calls": len(rewrites),
        "rewrite_direct_successes": len(useful),
        "rewrite_direct_success_rate": (len(useful) / len(rewrites)) if rewrites else None,
        "recovery_actions_on_gaps": gap_actions,
    }


def assert_runtime_kwargs(kwargs: dict) -> None:
    leaked = RUNTIME_FORBIDDEN & set(kwargs)
    if leaked:
        raise ValueError("runtime call received offline fields: " + ", ".join(sorted(leaked)))


def _cover(group: list[dict]) -> None:
    panels = {row["panel"] for row in group}
    if "holdout" not in panels:
        move = max(group, key=lambda row: row["question_id"])
        if move["panel"] != "development":
            raise ValueError("cannot cover holdout")
        move["panel"] = "holdout"
    if "development" not in {row["panel"] for row in group}:
        move = min(group, key=lambda row: row["question_id"])
        move["panel"] = "development"


def _residue(question_id: str) -> int:
    digest = hashlib.sha256(f"{SPLIT_SEED}:{question_id}".encode()).hexdigest()
    return int(digest[:8], 16) % HOLDOUT_MODULUS


def _refused(answer: str) -> bool:
    return answer.strip().lower().startswith("i do not know")
