"""CLI foundation path: retrieve-only without an API key."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "scripts" / "run_baseline.py"
BENCHMARK = REPO / "scripts" / "run_benchmark.py"


def test_cli_retrieve_only_writes_trace_without_api_key(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    completed = subprocess.run(
        [
            sys.executable,
            str(BASELINE),
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


def test_cli_evaluate_without_api_key_fails(tmp_path: Path) -> None:
    env = os.environ.copy()
    # Empty, not missing: the script calls load_dotenv, which would restore a
    # real key from .env if the variable were simply deleted.
    env["OPENAI_API_KEY"] = ""
    completed = subprocess.run(
        [
            sys.executable,
            str(BASELINE),
            "--retrieve-only",
            "--evaluate",
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
    assert completed.returncode == 1
    assert "OPENAI_API_KEY" in completed.stderr
    assert list(tmp_path.glob("*.json")) == []


def test_benchmark_retrieve_only_writes_snapshot_without_api_key(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""
    completed = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK),
            "--retrieve-only",
            "--output-root",
            str(tmp_path / "output"),
            "--results-root",
            str(tmp_path / "results"),
            "--label",
            "cli-check",
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    snapshot = tmp_path / "results" / "cli-check" / "comparison.json"
    assert snapshot.exists()
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["condition_ids"] == ["baseline", "eval_guided"]
    assert "OPENAI_API_KEY" not in completed.stdout
