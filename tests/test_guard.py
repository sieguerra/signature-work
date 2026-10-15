"""Committed research folders are not overwritten by default (#144)."""

from __future__ import annotations

from pathlib import Path

import pytest

from swrag.experiments.guard import refuse_committed

ROOT = Path(__file__).resolve().parents[1]


def test_a_folder_with_committed_files_is_refused() -> None:
    committed = ROOT / "experiments" / "results"
    with pytest.raises(SystemExit, match="committed file"):
        refuse_committed(committed, overwrite=False)
    refuse_committed(committed, overwrite=True)


def test_new_or_untracked_folders_are_allowed(tmp_path: Path) -> None:
    refuse_committed(tmp_path / "does-not-exist", overwrite=False)
    (tmp_path / "scratch").mkdir()
    refuse_committed(tmp_path / "scratch", overwrite=False)
