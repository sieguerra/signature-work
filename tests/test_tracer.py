"""Trace writer tests (no API)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swrag.tracing.tracer import write_trace
from swrag.types import TraceRecord


def _record(run_id: str) -> TraceRecord:
    return TraceRecord(
        run_id=run_id,
        timestamp="2026-09-10T00:00:00+00:00",
        query="When does the library close?",
        retrieved_chunks=(
            {
                "chunk_id": "harbor-library::c000",
                "doc_id": "harbor-library",
                "title": "Harbor Library",
                "score": 0.9,
                "text": "Saturday: 10:00–16:00",
            },
        ),
        answer="Saturday 10:00–16:00",
        model="none",
        embedding_model="fake-hash",
        top_k=4,
    )


def test_write_trace_creates_json_with_required_fields(tmp_path: Path) -> None:
    path = write_trace(_record("run_aaa"), tmp_path)
    assert path.name == "run_aaa.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "run_id",
        "timestamp",
        "query",
        "retrieved_chunks",
        "answer",
        "model",
        "embedding_model",
        "top_k",
    ):
        assert key in payload
    assert payload["run_id"] == "run_aaa"


def test_second_run_writes_a_new_file_and_does_not_overwrite(tmp_path: Path) -> None:
    first = write_trace(_record("run_one"), tmp_path)
    second = write_trace(_record("run_two"), tmp_path)
    assert first != second
    assert first.exists() and second.exists()
    with pytest.raises(FileExistsError):
        write_trace(_record("run_one"), tmp_path)
