"""Write one JSON trace file per run (never overwrite an existing file)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from swrag.types import TraceRecord


def write_trace(record: TraceRecord, output_dir: str | Path) -> Path:
    """Persist one trace.

    The bytes go to a sibling partial file, are flushed and fsynced, then
    linked into ``{run_id}.json``. ``os.link`` fails if that name already
    exists, so a crash cannot truncate a finished trace and a second writer
    cannot replace one. A leftover partial is not named ``*.json``, so the
    trace loader does not read it as a completed run.
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.run_id}.json"
    if path.exists():
        raise FileExistsError(f"Trace already exists (refusing to overwrite): {path}")
    partial = directory / f".{record.run_id}.json.partial"
    payload = asdict(record)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    partial.unlink(missing_ok=True)
    try:
        with partial.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(partial, path)
        except FileExistsError:
            raise FileExistsError(f"Trace already exists (refusing to overwrite): {path}") from None
        _fsync_directory(directory)
    finally:
        partial.unlink(missing_ok=True)
    return path


def _fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
