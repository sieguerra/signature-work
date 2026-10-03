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
    assert rows[0]["stage"] == "final"


def test_export_adds_the_first_pass_judge_call_for_recovered_runs(tmp_path: Path) -> None:
    trace = {
        "run_id": "run-2",
        "query": "Which ship reached Whitby?",
        "previous_answer": "I cannot tell from the evidence.",
        "previous_retrieved_chunks": [{"text": "A storm hit the coast."}],
        "first_pass_evaluation": {"evidence_sufficient": False, "answer_supported": None},
        "answer": "The Demeter.",
        "retrieved_chunks": [{"text": "The Demeter came into Whitby harbour."}],
        "runtime_evaluation": {"evidence_sufficient": True, "answer_supported": True},
    }
    (tmp_path / "run-2.json").write_text(json.dumps(trace), encoding="utf-8")
    rows = export_audit_rows(tmp_path)
    assert [row["stage"] for row in rows] == ["first_pass", "final"]
    first, final = rows
    assert first["answer"] == "I cannot tell from the evidence."
    assert first["evidence"] == "A storm hit the coast."
    assert first["judge_sufficient"] is False
    assert final["evidence"] == "The Demeter came into Whitby harbour."
    assert all(row["human_sufficient"] is None for row in rows)


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


def test_score_splits_agreement_by_stage(tmp_path: Path) -> None:
    rows = [
        {"stage": "first_pass", "human_sufficient": False, "human_supported": False,
         "judge_sufficient": True, "judge_supported": False},
        {"stage": "final", "human_sufficient": True, "human_supported": True,
         "judge_sufficient": True, "judge_supported": True},
    ]
    path = tmp_path / "staged.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    counts = score_audit(path)
    assert counts["n"] == 2
    assert counts["by_stage"]["first_pass"]["disagree_sufficient"] == 1
    assert counts["by_stage"]["final"]["agree_sufficient"] == 1
