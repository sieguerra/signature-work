"""Refuse to rewrite research results that are committed to git (#144).

``experiments/results/`` snapshots are protected by the harness itself. Other
committed research folders (recovery benchmark runs, the gap-aware panels)
were written with ``exist_ok=True`` and could be silently replaced by a rerun.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def committed_files(path: Path) -> list[str]:
    """Git-tracked files under ``path``; empty when git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", str(path)],
            cwd=path if path.is_dir() else path.parent,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def refuse_committed(path: Path, *, overwrite: bool) -> None:
    """Exit if ``path`` holds committed files, unless the caller opted in."""
    if overwrite or not path.exists():
        return
    tracked = committed_files(path)
    if tracked:
        raise SystemExit(
            f"{path} holds {len(tracked)} committed file(s); refusing to overwrite them. "
            "Use a new run id or output folder, or pass --overwrite-committed if you mean to replace them."
        )
