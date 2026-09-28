"""Blank judge-audit sheets and agreement counts.

Human labels are never filled here. Gold answers are never read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_audit_rows(traces_dir: str | Path) -> list[dict[str, Any]]:
    """One unlabeled row per trace that has a runtime judge.

    ``human_sufficient`` and ``human_supported`` are always null.
    """
    directory = Path(traces_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        evaluation = payload.get("runtime_evaluation")
        if not isinstance(evaluation, dict):
            continue
        chunks = payload.get("retrieved_chunks") or []
        evidence = "\n\n".join(
            str(chunk.get("text") or "")
            for chunk in chunks
            if isinstance(chunk, dict)
        )
        rows.append(
            {
                "run_id": str(payload.get("run_id") or path.stem),
                "question": str(payload.get("query") or ""),
                "answer": str(payload.get("answer") or ""),
                "evidence": evidence,
                "judge_sufficient": evaluation.get("evidence_sufficient"),
                "judge_supported": evaluation.get("answer_supported"),
                "human_sufficient": None,
                "human_supported": None,
                "notes": "",
            }
        )
    return rows


def score_audit(path: str | Path) -> dict[str, int]:
    """Count agreement between human labels and the stored judge flags.

    Raises if any human field is missing. This function does not guess labels.
    """
    rows = _load_rows(Path(path))
    if not rows:
        raise ValueError("audit file has no rows")
    agree_sufficient = 0
    agree_supported = 0
    for index, row in enumerate(rows):
        human_sufficient = row.get("human_sufficient")
        human_supported = row.get("human_supported")
        if not isinstance(human_sufficient, bool) or not isinstance(human_supported, bool):
            raise ValueError(
                f"row {index} is missing human_sufficient or human_supported; do not invent labels"
            )
        if human_sufficient is row.get("judge_sufficient"):
            agree_sufficient += 1
        if human_supported is row.get("judge_supported"):
            agree_supported += 1
    n = len(rows)
    return {
        "n": n,
        "agree_sufficient": agree_sufficient,
        "disagree_sufficient": n - agree_sufficient,
        "agree_supported": agree_supported,
        "disagree_supported": n - agree_supported,
    }


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError("audit rows must be JSON objects")
        rows.append(payload)
    return rows
