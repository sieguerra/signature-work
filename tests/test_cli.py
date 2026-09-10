"""CLI foundation path: retrieve-only without an API key."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "run_baseline.py"


def test_cli_retrieve_only_writes_trace_without_api_key(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--retrieve-only",
            "--question",
            "When is the Harbor Institute Library open on Saturday?",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    traces = list(tmp_path.glob("*.json"))
    assert len(traces) == 1
    assert "harbor-library" in completed.stdout
    assert "--retrieve-only" in completed.stdout
