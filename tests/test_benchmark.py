"""Issue #12 benchmark harness tests. No live API calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import pytest

from swrag.evaluation.scripted_judge import ScriptedJudge
from swrag.experiments.benchmark import load_benchmark_config, run_benchmark
from swrag.experiments.runner import run_experiment
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import GenerationResult, RetrievalResult, RuntimeEvaluation

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments" / "configs" / "v1_baseline_vs_loop.json"
GOLD = ROOT / "datasets" / "gold" / "questions.jsonl"
CORPUS = ROOT / "datasets" / "corpus"


class CountingEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[int] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(len(texts))
        return super().embed(texts)

    @property
    def corpus_add_calls(self) -> int:
        return sum(1 for size in self.calls if size > 1)


def test_config_resolves_paths_against_the_repo() -> None:
    payload = load_benchmark_config(CONFIG)
    assert payload["name"] == "v1_baseline_vs_loop"
    assert Path(payload["gold_path"]) == GOLD
    assert Path(payload["corpus_dir"]) == CORPUS
    assert [item["mode"] for item in payload["conditions"]] == ["baseline", "loop"]


def test_loop_mode_requires_a_judge(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="grounding judge"):
        run_experiment(
            gold_path=GOLD,
            corpus_dir=CORPUS,
            output_root=tmp_path,
            embedder=FakeEmbedder(),
            generate=False,
            mode="loop",
            run_label="no-judge",
        )


def test_benchmark_writes_comparison_and_refuses_overwrite(tmp_path: Path) -> None:
    kwargs = dict(
        config_path=CONFIG,
        output_root=tmp_path / "output",
        results_root=tmp_path / "results",
        embedder=FakeEmbedder(),
        generate=False,
        judge=ScriptedJudge(evidence_sufficient=True, answer_supported=None),
        run_label="v1",
        repo_root=ROOT,
    )
    comparison = run_benchmark(**kwargs)
    snapshot = tmp_path / "results" / "v1" / "comparison.json"
    assert snapshot.exists()
    assert comparison["condition_ids"] == ["baseline", "eval_guided"]
    assert comparison["quality"]["retrieval_hit_rate"]["baseline"] >= 0.0
    assert "delta" in comparison["quality"]["answerable_f1"]
    assert "by_runtime_outcome" in comparison["verification_vs_gold"]
    assert len(comparison["paired_outcomes"]) == comparison["conditions"]["baseline"]["total"]
    assert (tmp_path / "output" / "v1" / "baseline" / "summary.json").exists()
    assert (tmp_path / "output" / "v1" / "eval_guided" / "summary.json").exists()

    with pytest.raises(FileExistsError):
        run_benchmark(**kwargs)


def test_corpus_is_embedded_once_across_conditions(tmp_path: Path) -> None:
    embedder = CountingEmbedder()
    run_benchmark(
        config_path=CONFIG,
        output_root=tmp_path / "output",
        results_root=tmp_path / "results",
        embedder=embedder,
        generate=False,
        judge=ScriptedJudge(evidence_sufficient=True, answer_supported=None),
        run_label="once",
        repo_root=ROOT,
    )
    assert embedder.corpus_add_calls == 1


def _eval(*, sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="test",
        support_rationale="test",
        judge="scripted",
        model="none",
    )


class _SequenceJudge:
    def __init__(self, *results: RuntimeEvaluation) -> None:
        self._results = list(results)

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        return self._results.pop(0)


class _WrongGenerator:
    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return GenerationResult(answer="The library is on the moon.", model="canned")


class _RepairingRegenerator:
    def regenerate(
        self,
        *,
        question: str,
        retrieval: RetrievalResult,
        previous_answer: str,
    ) -> GenerationResult:
        del question, retrieval, previous_answer
        return GenerationResult(answer="Saturday 10:00-16:00", model="canned-repair")


def test_verification_table_joins_runtime_verdict_to_gold_f1(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        json.dumps(
            {
                "question_id": "q1",
                "question": "When is the Harbor Institute Library open on Saturday?",
                "answerable": True,
                "answers": ["Saturday 10:00-16:00"],
                "supporting_doc_ids": ["harbor-library"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "tiny",
                "gold_path": str(gold),
                "corpus_dir": str(CORPUS),
                "top_k": 4,
                "conditions": [
                    {"id": "baseline", "mode": "baseline"},
                    {"id": "eval_guided", "mode": "loop"},
                ],
            }
        ),
        encoding="utf-8",
    )
    comparison = run_benchmark(
        config_path=config_path,
        output_root=tmp_path / "output",
        results_root=tmp_path / "results",
        embedder=FakeEmbedder(),
        generate=True,
        generator=_WrongGenerator(),  # type: ignore[arg-type]
        regenerator=_RepairingRegenerator(),
        judge=_SequenceJudge(
            _eval(sufficient=True, supported=False),
            _eval(sufficient=True, supported=True),
        ),
        run_label="verify",
        repo_root=ROOT,
    )
    loop = comparison["paired_outcomes"][0]["eval_guided"]
    assert loop["verification_outcome"] == "improved"
    assert loop["f1_delta"] is not None
    assert loop["f1_delta"] > 0
    table = comparison["verification_vs_gold"]["by_runtime_outcome"]["improved"]
    assert table["n"] == 1
    assert table["gold_f1_up"] == 1
