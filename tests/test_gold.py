"""Gold-set loader tests. No API calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swrag.evaluation.gold import load_gold_set

GOLD = Path(__file__).resolve().parents[1] / "datasets" / "gold" / "questions.jsonl"


def _write(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "gold.jsonl"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_loads_the_seed_gold_set() -> None:
    questions = load_gold_set(GOLD)
    assert len(questions) >= 6
    assert any(question.answerable for question in questions)
    assert any(not question.answerable for question in questions)


def test_seed_set_answers_obey_the_answerable_flag() -> None:
    for question in load_gold_set(GOLD):
        assert bool(question.answers) == question.answerable


def test_skips_comments_and_blank_lines(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "# a comment",
        "",
        json.dumps({"question_id": "a", "question": "q", "answerable": False}),
    )
    assert len(load_gold_set(path)) == 1


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_gold_set(tmp_path / "absent.jsonl")


def test_empty_file_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "# only a comment")
    with pytest.raises(ValueError, match="empty"):
        load_gold_set(path)


def test_invalid_json_reports_the_line_number(tmp_path: Path) -> None:
    path = _write(tmp_path, "{not json")
    with pytest.raises(ValueError, match=r"gold\.jsonl:1"):
        load_gold_set(path)


def test_duplicate_question_id_raises(tmp_path: Path) -> None:
    row = json.dumps({"question_id": "dup", "question": "q", "answerable": False})
    path = _write(tmp_path, row, row)
    with pytest.raises(ValueError, match="duplicate"):
        load_gold_set(path)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, json.dumps({"question_id": "a", "question": "q"}))
    with pytest.raises(ValueError, match="answerable"):
        load_gold_set(path)


def test_answerable_without_answers_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        json.dumps({"question_id": "a", "question": "q", "answerable": True, "answers": []}),
    )
    with pytest.raises(ValueError, match="at least one"):
        load_gold_set(path)


def test_unanswerable_with_answers_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        json.dumps({"question_id": "a", "question": "q", "answerable": False, "answers": ["x"]}),
    )
    with pytest.raises(ValueError, match="empty"):
        load_gold_set(path)
