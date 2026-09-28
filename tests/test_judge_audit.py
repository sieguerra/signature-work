"""Judge-audit export stays unlabeled, and scoring refuses to invent labels."""

import json
from pathlib import Path

import pytest

from swrag.evaluation.judge_audit import export_audit_rows, score_audit


def test_export_leaves_human_labels_blank_and_omits_gold(tmp_path: Path) -> None:
    trace = {
        "run_id": "run-1",
        "query": "When is the library open?",
        "answer": "Saturday.",
        "retrieved_chunks": [{"text": "Open Saturday.", "title": "hours"}],
        "runtime_evaluation": {"evidence_sufficient": True, "answer_supported": False},
        "gold_answers": ["should not be copied"],
    }
    (tmp_path / "run-1.json").write_text(json.dumps(trace), encoding="utf-8")
    rows = export_audit_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["human_sufficient"] is None
    assert rows[0]["human_supported"] is None
    assert rows[0]["judge_sufficient"] is True
    assert rows[0]["judge_supported"] is False
    assert "gold" not in json.dumps(rows[0])
    assert "Open Saturday." in rows[0]["evidence"]


def test_score_refuses_blank_labels(tmp_path: Path) -> None:
    path = tmp_path / "blank.jsonl"
    path.write_text(
        json.dumps(
            {
                "human_sufficient": None,
                "human_supported": None,
                "judge_sufficient": True,
                "judge_supported": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="do not invent labels"):
        score_audit(path)


def test_score_counts_agreement(tmp_path: Path) -> None:
    path = tmp_path / "filled.jsonl"
    path.write_text(
        "\n".join(
            [
                "# comment",
                json.dumps(
                    {
                        "human_sufficient": True,
                        "human_supported": False,
                        "judge_sufficient": True,
                        "judge_supported": True,
                    }
                ),
                json.dumps(
                    {
                        "human_sufficient": False,
                        "human_supported": False,
                        "judge_sufficient": False,
                        "judge_supported": False,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    counts = score_audit(path)
    assert counts == {
        "n": 2,
        "agree_sufficient": 2,
        "disagree_sufficient": 0,
        "agree_supported": 1,
        "disagree_supported": 1,
    }
