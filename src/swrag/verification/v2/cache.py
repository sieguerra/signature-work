"""File cache for verifier model responses.

The key covers the candidate, prompt version, parser version, model, and the
verifier view. A change to any of those misses the cache. The cache stores
the raw completion, and the caller parses it, so a parser fix does not replay
a stale label.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(
    *,
    candidate: str,
    prompt_version: str,
    parser_version: str,
    model: str,
    temperature: float,
    view: dict[str, Any],
    order: str | None = None,
) -> str:
    payload = {
        "candidate": candidate,
        "prompt_version": prompt_version,
        "parser_version": parser_version,
        "model": model,
        "temperature": temperature,
        "order": order,
        "view": view,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / key[:2] / f"{key}.json"


def read_cache(cache_dir: Path | None, key: str) -> dict[str, Any] | None:
    if cache_dir is None:
        return None
    path = cache_path(cache_dir, key)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_cache(cache_dir: Path | None, key: str, record: dict[str, Any]) -> None:
    if cache_dir is None:
        return
    path = cache_path(cache_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
