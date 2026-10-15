"""Wrong-source check and per-condition retrieval depth. No live calls."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.evaluation.llm_judge import attributed_sources, constrain_source_attribution, wrong_source
from swrag.experiments.benchmark import run_benchmark
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import RuntimeEvaluation

ROOT = Path(__file__).resolve().parents[1]
ASKED_CMG = "How many hours did the 1948 Black Mast Gale last according to the Coastal Memory Group?"


def test_an_answer_that_credits_another_source_is_rejected() -> None:
    answer = 'According to the Storm Ledger Unit, the 1948 "Black Mast Gale" lasted 19 hours.'
    assert wrong_source(ASKED_CMG, answer) == "Storm Ledger Unit"
    accepted = RuntimeEvaluation(evidence_sufficient=True, answer_supported=True, sufficiency_rationale="", support_rationale="", judge="llm-judge", model="m")
    checked = constrain_source_attribution(accepted, question=ASKED_CMG, answer=answer)
    assert checked.answer_supported is False
    assert checked.span_rejections == ("source: Storm Ledger Unit",)


def test_the_check_leaves_right_or_hedged_sources_alone() -> None:
    assert wrong_source(ASKED_CMG, "According to the Coastal Memory Group, it lasted 19 hours.") is None
    both = "According to the Storm Ledger Unit it lasted 19 hours; the Coastal Memory Group holds nothing after 1940."
    assert wrong_source(ASKED_CMG, both) is None
    assert wrong_source("When does the library open?", "According to the Harbor Desk, 09:00.") is None
    assert attributed_sources("according to the Storm Ledger Unit, and According to Kestrel Aero") == (
        "Storm Ledger Unit",
        "Kestrel Aero",
    )


def test_each_condition_can_set_its_own_depth(tmp_path: Path) -> None:
    config = tmp_path / "sweep.json"
    config.write_text(
        json.dumps(
            {
                "name": "sweep",
                "gold_path": "datasets/gold/questions.jsonl",
                "corpus_dir": "datasets/corpus",
                "top_k": 4,
                "conditions": [
                    {"id": "baseline_k1", "mode": "baseline", "top_k": 1},
                    {"id": "baseline_k8", "mode": "baseline", "top_k": 8},
                ],
            }
        ),
        encoding="utf-8",
    )
    comparison = run_benchmark(
        config_path=config,
        output_root=tmp_path / "out",
        results_root=tmp_path / "results",
        embedder=FakeEmbedder(),
        generate=False,
        run_label="sweep",
        repo_root=ROOT,
    )
    assert comparison["conditions"]["baseline_k1"]["top_k"] == 1
    assert comparison["conditions"]["baseline_k8"]["top_k"] == 8
    first = comparison["paired_outcomes"][0]
    assert len(first["baseline_k1"]["retrieved_doc_ids"]) <= 1 < len(first["baseline_k8"]["retrieved_doc_ids"])
