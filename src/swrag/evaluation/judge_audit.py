"""Blank judge-audit sheets and agreement counts.

Human labels are never filled here. Gold answers are never read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_audit_rows(traces_dir: str | Path) -> list[dict[str, Any]]:
    """Unlabeled rows for each judge call a trace stores.

    Every trace with a runtime judge gets a ``final`` row. A recovered trace
    also gets a ``first_pass`` row, because that call is the one that chose to
    recover. ``human_sufficient`` and ``human_supported`` are always null.
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
        run_id = str(payload.get("run_id") or path.stem)
        question = str(payload.get("query") or "")
        first_pass = payload.get("first_pass_evaluation")
        if isinstance(first_pass, dict) and payload.get("previous_answer") is not None:
            rows.append(
                _row(
                    run_id,
                    "first_pass",
                    question,
                    payload.get("previous_answer"),
                    payload.get("previous_retrieved_chunks") or payload.get("retrieved_chunks"),
                    first_pass,
                )
            )
        rows.append(
            _row(
                run_id,
                "final",
                question,
                payload.get("answer"),
                payload.get("retrieved_chunks"),
                evaluation,
            )
        )
    return rows


def _row(
    run_id: str,
    stage: str,
    question: str,
    answer: Any,
    chunks: Any,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    evidence = "\n\n".join(
        str(chunk.get("text") or "") for chunk in (chunks or []) if isinstance(chunk, dict)
    )
    return {
        "run_id": run_id,
        "stage": stage,
        "question": question,
        "answer": str(answer or ""),
        "evidence": evidence,
        "judge_sufficient": evaluation.get("evidence_sufficient"),
        "judge_supported": evaluation.get("answer_supported"),
        "human_sufficient": None,
        "human_supported": None,
        "notes": "",
    }


def score_audit(path: str | Path) -> dict[str, Any]:
    """Count agreement between human labels and the stored judge flags.

    Raises if any human field is missing. This function does not guess labels.
    Rows with a ``stage`` are also counted per stage under ``by_stage``.
    """
    rows = _load_rows(Path(path))
    if not rows:
        raise ValueError("audit file has no rows")
    for index, row in enumerate(rows):
        if not isinstance(row.get("human_sufficient"), bool) or not isinstance(
            row.get("human_supported"), bool
        ):
            raise ValueError(
                f"row {index} is missing human_sufficient or human_supported; do not invent labels"
            )
    counts: dict[str, Any] = _agreement(rows)
    stages = sorted({str(row["stage"]) for row in rows if row.get("stage")})
    if stages:
        counts["by_stage"] = {
            stage: _agreement([row for row in rows if row.get("stage") == stage])
            for stage in stages
        }
    return counts


def _agreement(rows: list[dict[str, Any]]) -> dict[str, int]:
    agree_sufficient = sum(1 for row in rows if row["human_sufficient"] is row.get("judge_sufficient"))
    agree_supported = sum(1 for row in rows if row["human_supported"] is row.get("judge_supported"))
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
