"""Deterministic question split. Exact copies are not counted twice."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from swrag.recovery_benchmark.inventory import QuestionRecord, observed_phase6_keys
from swrag.recovery_benchmark.protocol import (
    HOLDOUT_MODULUS,
    HOLDOUT_RESIDUE,
    NEAR_DUPLICATE_JACCARD,
    SEED,
)

_TOKEN = re.compile(r"[a-z0-9]+")


def normalize_question(text: str) -> str:
    return " ".join(text.lower().split())


def token_set(text: str) -> set[str]:
    return {match.group(0) for match in _TOKEN.finditer(text.lower()) if len(match.group(0)) >= 2}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def assign_split(records: tuple[QuestionRecord, ...] | list[QuestionRecord], root: Path) -> dict:
    """Return the split document. Same records and seed always give the same panels.

    Exact normalized duplicates contribute one runnable question. Near
    duplicates stay in one panel so a copy cannot sit in the future holdout
    while its twin sits in analysis. Phase 6 observed ids are analysis.
    """
    observed = observed_phase6_keys(root)
    items = list(records)
    parent = _clusters(items)
    groups: dict[str, list[QuestionRecord]] = {}
    for record in items:
        groups.setdefault(parent[record.logical_id], []).append(record)

    rows: list[dict] = []
    duplicate_groups: list[dict] = []
    for lead, members in sorted(groups.items()):
        members = sorted(members, key=lambda record: record.logical_id)
        panel, reason = _panel(members, observed)
        norms = {normalize_question(member.question) for member in members}
        exact = len(norms) == 1 and len(members) > 1
        if len(members) > 1:
            duplicate_groups.append(
                {
                    "lead": lead,
                    "logical_ids": [member.logical_id for member in members],
                    "exact": exact,
                    "panel": panel,
                }
            )
        keeper = members[0].logical_id
        for member in members:
            payload = member.as_dict()
            payload["normalized_question"] = normalize_question(member.question)
            payload["panel"] = panel
            payload["panel_reason"] = reason
            payload["duplicate_of"] = None if member.logical_id == keeper or not exact else keeper
            payload["near_duplicate_group"] = lead if len(members) > 1 else None
            rows.append(payload)

    analysis = [row for row in rows if row["panel"] == "analysis" and not row["duplicate_of"]]
    holdout = [row for row in rows if row["panel"] == "future_holdout" and not row["duplicate_of"]]
    return {
        "seed": SEED,
        "holdout_rule": f"sha256('{SEED}:' + lead_logical_id) hex[:8] % {HOLDOUT_MODULUS} == {HOLDOUT_RESIDUE}",
        "near_duplicate_jaccard": NEAR_DUPLICATE_JACCARD,
        "n_records": len(rows),
        "n_analysis": len(analysis),
        "n_future_holdout": len(holdout),
        "n_exact_duplicates_dropped": sum(1 for row in rows if row["duplicate_of"]),
        "duplicate_groups": duplicate_groups,
        "questions": rows,
    }


def holdout_fraction_bucket(logical_id: str) -> str:
    digest = hashlib.sha256(f"{SEED}:{logical_id}".encode()).hexdigest()
    if int(digest[:8], 16) % HOLDOUT_MODULUS == HOLDOUT_RESIDUE:
        return "future_holdout"
    return "analysis"


def _panel(members: list[QuestionRecord], observed: set[tuple[str, str]]) -> tuple[str, str]:
    if any((member.corpus_id, member.question_id) in observed for member in members):
        return "analysis", "phase6_observed"
    lead = min(member.logical_id for member in members)
    return holdout_fraction_bucket(lead), "hash"


def _clusters(items: list[QuestionRecord]) -> dict[str, str]:
    parent = {record.logical_id: record.logical_id for record in items}
    tokens = {record.logical_id: token_set(record.question) for record in items}
    norms = {record.logical_id: normalize_question(record.question) for record in items}

    def find(logical_id: str) -> str:
        while parent[logical_id] != logical_id:
            parent[logical_id] = parent[parent[logical_id]]
            logical_id = parent[logical_id]
        return logical_id

    def union(left: str, right: str) -> None:
        lead_left, lead_right = find(left), find(right)
        if lead_left == lead_right:
            return
        if lead_left < lead_right:
            parent[lead_right] = lead_left
        else:
            parent[lead_left] = lead_right

    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            same = norms[left.logical_id] == norms[right.logical_id]
            close = jaccard(tokens[left.logical_id], tokens[right.logical_id]) >= NEAR_DUPLICATE_JACCARD
            if same or close:
                union(left.logical_id, right.logical_id)
    return {logical_id: find(logical_id) for logical_id in parent}
