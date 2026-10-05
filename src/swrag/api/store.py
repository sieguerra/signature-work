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


def load_trace_payloads(traces_dir: str | Path) -> list[dict[str, Any]]:
    """Full trace objects under ``traces_dir``.

    Skips ``summary.json``, ``comparison.json``, and ``config.json``. A file
    is a trace only when it has ``run_id`` and ``query``.
    """
    items: list[dict[str, Any]] = []
    for path in _iter_trace_paths(traces_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_trace_payload(payload):
            continue
        items.append(payload)
    return items


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
                "recovery_status": payload.get("recovery_status"),
                "parent_run_id": payload.get("parent_run_id"),
                "recovery_source": recovery.get("source"),
            }
        )
    children = {
        str(item["parent_run_id"]): str(item["run_id"])
        for item in items
        if item.get("parent_run_id")
    }
    for item in items:
        item["child_run_id"] = children.get(str(item["run_id"]))
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


def find_child_run_id(traces_dir: str | Path, parent_run_id: str) -> str | None:
    """Return the recovered child run_id, if one exists. Does not mutate files."""
    if not _safe_run_id(parent_run_id):
        return None
    root = Path(traces_dir)
    if not root.exists():
        return None
    for path in _iter_trace_paths(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_trace_payload(payload):
            continue
        if payload.get("parent_run_id") == parent_run_id:
            return str(payload["run_id"])
    return None


def delete_trace(traces_dir: str | Path, run_id: str) -> list[str]:
    """Delete ``run_id`` and its recovered child, if any. Empty if missing."""
    if not _safe_run_id(run_id):
        return []
    deleted: list[str] = []
    child_id = find_child_run_id(traces_dir, run_id)
    if child_id and _delete_one(traces_dir, child_id):
        deleted.append(child_id)
    if _delete_one(traces_dir, run_id):
        deleted.insert(0, run_id)
    return deleted


def _delete_one(traces_dir: str | Path, run_id: str) -> bool:
    """Unlink ``{run_id}.json`` and its quality scores. Does not follow parent/child links."""
    root = Path(traces_dir)
    if not root.exists() or not _safe_run_id(run_id):
        return False
    delete_quality(root, run_id)
    root_resolved = root.resolve()
    found = False
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
        found = True
    return found


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
        delete_quality(traces_dir, str(payload["run_id"]))
        deleted += 1
    return deleted


def eval_counts(traces_dir: str | Path) -> dict[str, Any]:
    """Counts for the active traces directory. Does not read gold or Harbor snapshots."""
    by_action: dict[str, int] = {}
    by_verification: dict[str, int] = {}
    n = 0
    abstain = 0
    proposed = 0
    latencies: list[float] = []
    runs: list[dict[str, Any]] = []
    for path in _iter_trace_paths(traces_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_trace_payload(payload):
            continue
        n += 1
        row = _chart_row(payload)
        row["quality"] = _quality_row(traces_dir, row["run_id"])
        runs.append(row)
        recovery = payload.get("recovery") if isinstance(payload.get("recovery"), dict) else {}
        verification = (
            payload.get("verification") if isinstance(payload.get("verification"), dict) else {}
        )
        action = str(recovery.get("action") or "none")
        if payload.get("recovery_status") == "proposed":
            proposed += 1
        else:
            by_action[action] = by_action.get(action, 0) + 1
        outcome = verification.get("outcome")
        if outcome:
            key = str(outcome)
            by_verification[key] = by_verification.get(key, 0) + 1
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
        "proposed": proposed,
        "by_action": by_action,
        "by_verification": by_verification,
        "abstain": abstain,
        "mean_latency_ms": (sum(latencies) / len(latencies) if latencies else None),
        "batch_summary": batch_summary,
        "traces_dir": str(Path(traces_dir)),
        "runs": sorted(runs, key=lambda row: row["timestamp"]),
    }


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _chart_row(payload: dict[str, Any]) -> dict[str, Any]:
    """One run reduced to what the evaluation charts plot. Runtime signals only, no gold."""
    recovery = _dict(payload.get("recovery"))
    final = _dict(payload.get("runtime_evaluation"))
    first = _dict(payload.get("first_pass_evaluation")) or final
    attempts = [item for item in payload.get("recovery_attempts") or [] if isinstance(item, dict)]
    status = payload.get("recovery_status")
    if attempts:
        path = [str(item.get("action")) for item in attempts if item.get("action")]
    elif status != "proposed" and recovery.get("action") not in (None, "accept"):
        path = [str(recovery["action"])]
    else:
        path = []
    failure_class = next(
        (item.get("attributed_class") for item in attempts if item.get("attributed_class")),
        None,
    ) or recovery.get("attributed_class") or _dict(payload.get("diagnosis")).get("failure_class")
    answer = str(payload.get("answer") or "")
    first_answer = str(payload.get("previous_answer") or "") if path and payload.get("previous_answer") is not None else answer
    latency = payload.get("latency_ms")
    return {
        "run_id": str(payload["run_id"]),
        "timestamp": str(payload.get("timestamp") or ""),
        "query": str(payload.get("query") or "")[:140],
        "status": status,
        "proposed_action": recovery.get("action") if status == "proposed" else None,
        "path": path,
        "verification": _dict(payload.get("verification")).get("outcome"),
        "failure_class": failure_class,
        "first_sufficient": first.get("evidence_sufficient"),
        "first_supported": first.get("answer_supported"),
        "final_sufficient": final.get("evidence_sufficient"),
        "final_supported": final.get("answer_supported"),
        "abstained": answer.strip() == ABSTAIN_ANSWER or payload.get("model") == "abstain",
        "first_abstained": first_answer.strip() == ABSTAIN_ANSWER,
        "has_answer": bool(answer.strip()),
        "latency_ms": float(latency) if isinstance(latency, (int, float)) else None,
        "parent_run_id": payload.get("parent_run_id"),
    }


QUALITY_DIR = "quality"
QUALITY_KEYS = ("faithfulness", "answer_relevance", "context_relevance")


def _quality_path(traces_dir: str | Path, run_id: str) -> Path:
    return Path(traces_dir) / QUALITY_DIR / f"{run_id}.quality.json"


def load_quality(traces_dir: str | Path, run_id: str) -> dict[str, Any] | None:
    """Saved quality scores for ``run_id``, or None when it has not been scored."""
    if not _safe_run_id(run_id):
        return None
    path = _quality_path(traces_dir, run_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def save_quality(traces_dir: str | Path, run_id: str, scores: dict[str, Any]) -> None:
    if not _safe_run_id(run_id):
        raise ValueError(f"unsafe run id: {run_id!r}")
    path = _quality_path(traces_dir, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scores, indent=2), encoding="utf-8")


def delete_quality(traces_dir: str | Path, run_id: str) -> None:
    if _safe_run_id(run_id):
        _quality_path(traces_dir, run_id).unlink(missing_ok=True)


def _quality_row(traces_dir: str | Path, run_id: str) -> dict[str, Any] | None:
    saved = load_quality(traces_dir, run_id)
    if saved is None:
        return None
    final = _dict(saved.get("final"))
    first = _dict(saved.get("first"))
    row: dict[str, Any] = {key: final.get(key) for key in QUALITY_KEYS}
    row["first"] = {key: first.get(key) for key in QUALITY_KEYS} if first else None
    return row
