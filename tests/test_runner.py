"""Experiment runner tests. No API calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swrag.experiments.runner import run_experiment
from swrag.evaluation.scripted_judge import ScriptedJudge
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import GoldQuestion

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"
GOLD = ROOT / "datasets" / "gold" / "questions.jsonl"


def _perfect_answer(question: GoldQuestion) -> tuple[str, str, tuple[str, ...], str | None]:
    """Answer every question correctly, abstaining where required."""
    answer = question.answers[0] if question.answerable else "I do not know."
    return answer, f"canned-{question.question_id}", question.supporting_doc_ids, None


def _always_abstain(question: GoldQuestion) -> tuple[str, str, tuple[str, ...], str | None]:
    return "I do not know.", f"canned-{question.question_id}", (), None


def test_perfect_answers_score_one(tmp_path: Path) -> None:
    summary = run_experiment(
        gold_path=GOLD,
        corpus_dir=CORPUS,
        output_root=tmp_path,
        answer_fn=_perfect_answer,
        run_label="perfect",
    )
    assert summary.exact_match == pytest.approx(1.0)
    assert summary.answerable_exact_match == pytest.approx(1.0)
    assert summary.unanswerable_abstention_rate == pytest.approx(1.0)
    assert summary.answerable_abstention_rate == pytest.approx(0.0)
    assert summary.total == summary.answerable_total + summary.unanswerable_total


def test_always_abstaining_splits_the_classes(tmp_path: Path) -> None:
    """The point of per-class reporting: one number would hide this."""
    summary = run_experiment(
        gold_path=GOLD,
        corpus_dir=CORPUS,
        output_root=tmp_path,
        answer_fn=_always_abstain,
        run_label="abstain",
    )
    assert summary.unanswerable_abstention_rate == pytest.approx(1.0)
    assert summary.answerable_exact_match == pytest.approx(0.0)
    # An aggregate alone would look like partial success on a useless system.
    assert 0.0 < summary.exact_match < 1.0


def test_summary_is_written_and_reloadable(tmp_path: Path) -> None:
    run_experiment(
        gold_path=GOLD,
        corpus_dir=CORPUS,
        output_root=tmp_path,
        answer_fn=_perfect_answer,
        run_label="written",
    )
    path = tmp_path / "written" / "summary.json"
    assert path.exists()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_label"] == "written"
    assert len(payload["outcomes"]) == payload["total"]
    assert "base_url" in payload["provider"]


def test_refuses_to_overwrite_a_previous_run(tmp_path: Path) -> None:
    kwargs = dict(
        gold_path=GOLD,
        corpus_dir=CORPUS,
        output_root=tmp_path,
        answer_fn=_perfect_answer,
        run_label="collide",
    )
    run_experiment(**kwargs)
    with pytest.raises(FileExistsError):
        run_experiment(**kwargs)


def test_retrieval_hit_rate_ignores_unanswerable_questions(tmp_path: Path) -> None:
    summary = run_experiment(
        gold_path=GOLD,
        corpus_dir=CORPUS,
        output_root=tmp_path,
        answer_fn=_perfect_answer,
        run_label="hits",
    )
    # _perfect_answer reports the supporting docs as retrieved, so every
    # question that has supporting docs counts as a hit.
    assert summary.retrieval_hit_rate == pytest.approx(1.0)


def test_real_pipeline_runs_retrieval_only(tmp_path: Path) -> None:
    """End to end through the real pipeline with a fake embedder and no generation."""
    summary = run_experiment(
        gold_path=GOLD,
        corpus_dir=CORPUS,
        output_root=tmp_path,
        top_k=3,
        embedder=FakeEmbedder(),
        generate=False,
        run_label="retrieve-only",
    )
    assert summary.total >= 6
    traces = list((tmp_path / "retrieve-only" / "traces").glob("*.json"))
    assert len(traces) == summary.total

    trace = json.loads(traces[0].read_text(encoding="utf-8"))
    assert trace["question_id"] is not None
    assert trace["provider"]["base_url"]


def test_pipeline_traces_include_runtime_evaluation_when_a_judge_is_passed(tmp_path: Path) -> None:
    summary = run_experiment(
        gold_path=GOLD,
        corpus_dir=CORPUS,
        output_root=tmp_path,
        top_k=3,
        embedder=FakeEmbedder(),
        generate=False,
        run_label="judged",
        judge=ScriptedJudge(evidence_sufficient=False),
    )
    traces = list((tmp_path / "judged" / "traces").glob("*.json"))
    assert len(traces) == summary.total
    payload = json.loads(traces[0].read_text(encoding="utf-8"))
    assert payload["runtime_evaluation"]["evidence_sufficient"] is False
    assert payload["runtime_evaluation"]["answer_supported"] is None
    assert "answers" not in payload
