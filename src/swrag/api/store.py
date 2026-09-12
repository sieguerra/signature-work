"""List and load JSON traces from disk. Does not run the pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from swrag.orchestration.loop import ABSTAIN_ANSWER

SKIP_NAMES = frozenset({"summary.json", "comparison.json", "config.json"})


def _safe_run_id(run_id: str) -> bool:
    """Reject empty ids, path separators, ``..``, and reserved summary names."""
    if not run_id or run_id in {name.removesuffix(".json") for name in SKIP_NAMES}:
        return False
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        return False
    return True


def _is_trace_payload(payload: object) -> bool:
    return isinstance(payload, dict) and "run_id" in payload and "query" in payload


def _iter_trace_paths(traces_dir: str | Path):
    """Yield JSON files under ``traces_dir`` that look like run traces."""
    root = Path(traces_dir)
    if not root.exists():
        return
    root_resolved = root.resolve()
    for path in root.rglob("*.json"):
        if path.name in SKIP_NAMES:
            continue
        try:
            path.resolve().relative_to(root_resolved)
        except ValueError:
            continue
        yield path


def list_traces(traces_dir: str | Path) -> list[dict[str, Any]]:
    """Newest-first summaries of every trace file under ``traces_dir``."""
    root = Path(traces_dir)
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in _iter_trace_paths(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_trace_payload(payload):
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
    if not root.exists() or not _safe_run_id(run_id):
        return None
    matches = list(root.rglob(f"{run_id}.json"))
    if not matches:
        return None
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not _is_trace_payload(payload):
        return None
    return payload


def delete_trace(traces_dir: str | Path, run_id: str) -> bool:
    """Delete ``{run_id}.json`` under ``traces_dir``. Returns False if missing."""
    root = Path(traces_dir)
    if not root.exists() or not _safe_run_id(run_id):
        return False
    root_resolved = root.resolve()
    deleted = False
    for path in root.rglob(f"{run_id}.json"):
        if path.name in SKIP_NAMES:
            continue
        try:
            path.resolve().relative_to(root_resolved)
        except ValueError:
            continue
        try:
            path.unlink()
        except OSError:
            continue
        deleted = True
    return deleted


def delete_all_traces(traces_dir: str | Path) -> int:
    """Delete every run trace under ``traces_dir``. Leaves summary files alone."""
    deleted = 0
    for path in list(_iter_trace_paths(traces_dir)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_trace_payload(payload):
            continue
        try:
            path.unlink()
        except OSError:
            continue
        deleted += 1
    return deleted


def eval_counts(traces_dir: str | Path) -> dict[str, Any]:
    """Counts for the active traces directory. Does not read gold or Harbor snapshots."""
    by_action: dict[str, int] = {}
    by_verification: dict[str, int] = {}
    n = 0
    abstain = 0
    latencies: list[float] = []
    for path in _iter_trace_paths(traces_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_trace_payload(payload):
            continue
        n += 1
        recovery = payload.get("recovery") if isinstance(payload.get("recovery"), dict) else {}
        verification = (
            payload.get("verification") if isinstance(payload.get("verification"), dict) else {}
        )
        action = str(recovery.get("action") or "none")
        outcome = str(verification.get("outcome") or "none")
        by_action[action] = by_action.get(action, 0) + 1
        by_verification[outcome] = by_verification.get(outcome, 0) + 1
        answer = str(payload.get("answer") or "")
        model = str(payload.get("model") or "")
        if answer.strip() == ABSTAIN_ANSWER or model == "abstain":
            abstain += 1
        latency = payload.get("latency_ms")
        if isinstance(latency, (int, float)):
            latencies.append(float(latency))
    batch_summary = None
    summary_path = Path(traces_dir) / "summary.json"
    if summary_path.is_file():
        try:
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict):
            batch_summary = loaded
    return {
        "n": n,
        "by_action": by_action,
        "by_verification": by_verification,
        "abstain": abstain,
        "mean_latency_ms": (sum(latencies) / len(latencies) if latencies else None),
        "batch_summary": batch_summary,
        "traces_dir": str(Path(traces_dir)),
    }
