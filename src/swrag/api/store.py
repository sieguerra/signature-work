"""List and load JSON traces from disk. Does not run the pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SKIP_NAMES = frozenset({"summary.json", "comparison.json", "config.json"})


def list_traces(traces_dir: str | Path) -> list[dict[str, Any]]:
    """Newest-first summaries of every trace file under ``traces_dir``."""
    root = Path(traces_dir)
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in root.rglob("*.json"):
        if path.name in SKIP_NAMES:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or "run_id" not in payload or "query" not in payload:
            continue
        answer = str(payload.get("answer") or "")
        recovery = payload.get("recovery") if isinstance(payload.get("recovery"), dict) else {}
        verification = (
            payload.get("verification") if isinstance(payload.get("verification"), dict) else {}
        )
        diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
        items.append(
            {
                "run_id": str(payload["run_id"]),
                "timestamp": str(payload.get("timestamp") or ""),
                "query": str(payload.get("query") or ""),
                "answer_preview": answer.splitlines()[0][:140] if answer.strip() else "",
                "action": recovery.get("action"),
                "verification": verification.get("outcome"),
                "failure_class": diagnosis.get("failure_class"),
                "model": payload.get("model"),
            }
        )
    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return items


def load_trace(traces_dir: str | Path, run_id: str) -> dict[str, Any] | None:
    """Return the trace JSON for ``run_id``, or None if it is not on disk."""
    root = Path(traces_dir)
    if not root.exists() or "/" in run_id or "\\" in run_id:
        return None
    matches = list(root.rglob(f"{run_id}.json"))
    if not matches:
        return None
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload
