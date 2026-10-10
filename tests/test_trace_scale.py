"""How far the JSON trace directory stays usable. Not a performance budget."""

from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path

from swrag.api.overview import aggregate_overview, group_logical_runs, logical_run_history
from swrag.api.store import load_trace_payloads

SIZES = (1000, 5000, 10000)


def _trace(index: int) -> dict:
    kind = index % 4
    base = {
        "run_id": f"scale-{index:05d}",
        "timestamp": f"2026-01-01T00:{index % 60:02d}:{index % 60:02d}+00:00",
        "query": "When is the library open?",
        "answer": "Saturday hours.",
        "model": "scripted",
        "retrieved_chunks": [{"chunk_id": "hours::c000", "doc_id": "hours", "text": "Saturday 10:00-16:00"}],
        "trace_schema_version": 2,
        "run_mode": "baseline",
    }
    if kind == 1:
        base.update(
            {
                "run_mode": "loop",
                "previous_answer": "On the moon.",
                "initial": {"query": base["query"], "answer": "On the moon.", "retrieved_chunks": base["retrieved_chunks"]},
                "recovery_attempts": [
                    {
                        "index": 0,
                        "action": "regenerate",
                        "executed": True,
                        "answer": "Saturday hours.",
                        "answer_relation": "generated",
                        "evidence_relation": "unchanged",
                        "evaluation_source": "judge",
                    }
                ],
                "verification": {"outcome": "improved"},
            }
        )
    elif kind == 2:
        base.update(
            {
                "run_mode": "loop",
                "rewritten_query": "library saturday hours",
                "initial": {"query": base["query"], "answer": "Saturday hours.", "retrieved_chunks": base["retrieved_chunks"]},
                "recovery_attempts": [
                    {
                        "index": 0,
                        "action": "rewrite",
                        "executed": True,
                        "answer": "Saturday hours.",
                        "answer_relation": "kept_previous",
                        "evidence_relation": "replaced",
                        "evaluation_source": "carried",
                        "search_query": "library saturday hours",
                        "retrieved_chunks": base["retrieved_chunks"],
                    }
                ],
            }
        )
    elif kind == 3:
        base.update(
            {
                "run_mode": "loop",
                "initial": {"query": base["query"], "answer": "A", "retrieved_chunks": base["retrieved_chunks"]},
                "recovery_attempts": [
                    {
                        "index": 0,
                        "action": "rewrite",
                        "executed": True,
                        "answer": "B",
                        "answer_relation": "generated",
                        "evidence_relation": "replaced",
                        "retrieved_chunks": base["retrieved_chunks"],
                    },
                    {
                        "index": 1,
                        "action": "expand",
                        "executed": True,
                        "answer": "Saturday hours.",
                        "answer_relation": "generated",
                        "evidence_relation": "widened",
                        "retrieved_chunks": base["retrieved_chunks"],
                    },
                ],
            }
        )
    return base


def _measure(directory: Path, count: int) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (directory / f"scale-{index:05d}.json").write_text(json.dumps(_trace(index)), encoding="utf-8")
    size = sum(path.stat().st_size for path in directory.glob("*.json"))
    tracemalloc.start()
    started = time.perf_counter()
    history = logical_run_history(directory)
    history_s = time.perf_counter() - started
    started = time.perf_counter()
    overview = aggregate_overview(group_logical_runs(load_trace_payloads(directory)))
    overview_s = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "runs": count,
        "files": len(history["runs"]),
        "directory_bytes": size,
        "history_s": round(history_s, 3),
        "overview_s": round(overview_s, 3),
        "peak_bytes": peak,
        "observed_runs": overview["observed_runs"],
    }


def test_json_trace_directory_scale(tmp_path: Path) -> None:
    rows = []
    for count in SIZES:
        rows.append(_measure(tmp_path / str(count), count))
    print("TRACE_SCALE " + json.dumps(rows))
    assert rows[-1]["files"] == 10000
    assert rows[-1]["observed_runs"] == 10000
    assert rows[-1]["history_s"] < 120
    assert rows[-1]["overview_s"] < 120


def test_realistic_trace_size_ceiling() -> None:
    chunk = {
        "chunk_id": "manual::c000",
        "doc_id": "manual.pdf",
        "title": "Harbor manual",
        "text": "Saturday 10:00-16:00. " * 200,
        "page": 12,
        "start_char": 0,
        "end_char": 4000,
    }
    chunks = [{**chunk, "chunk_id": f"manual::c{index:03d}", "page": index + 1} for index in range(20)]
    attempt = {
        "index": 0,
        "action": "rewrite",
        "executed": True,
        "answer": "Saturday hours. " * 40,
        "answer_relation": "generated",
        "evidence_relation": "replaced",
        "evaluation_source": "judge",
        "retrieved_chunks": chunks,
        "runtime_evaluation": {"evidence_sufficient": True, "answer_supported": True},
        "usage": {"chat_calls": 1, "prompt_tokens": 800, "completion_tokens": 120, "tokens_observed": True},
    }
    payload = {
        "trace_schema_version": 2,
        "run_mode": "loop",
        "query": "When is the library open?",
        "answer": attempt["answer"],
        "retrieved_chunks": chunks,
        "initial": {"query": "When is the library open?", "answer": "A", "retrieved_chunks": chunks},
        "recovery_attempts": [dict(attempt, index=0), dict(attempt, index=1, action="expand", evidence_relation="widened")],
        "usage": {"chat_calls": 3, "prompt_tokens": 2400, "completion_tokens": 360, "tokens_observed": True},
    }
    size = len(json.dumps(payload).encode("utf-8"))
    print(f"TRACE_SIZE_BYTES {size}")
    assert size > 27_500
    assert size < 5_000_000
