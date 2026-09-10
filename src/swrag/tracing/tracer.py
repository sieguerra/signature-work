"""Write one JSON trace file per run (never overwrite an existing file)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from swrag.types import TraceRecord


def write_trace(record: TraceRecord, output_dir: str | Path) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.run_id}.json"
    if path.exists():
        raise FileExistsError(f"Trace already exists (refusing to overwrite): {path}")
    payload = asdict(record)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
