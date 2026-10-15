"""Issue #147: a capped expand does not use the budget; empty slices are None. No live calls."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.experiments.runner import _mean
from swrag.orchestration.loop import _budget_spent, run_with_recovery
from swrag.retrieval.fake_embedder import FakeEmbedder
from tests.test_trace_hardening import CORPUS, _eval, _FixedIndex, _Generator, _Judge


class _Rewriter:
    def rewrite(self, *, question, retrieval):
        return "library opening hours Saturday"


def test_a_capped_expand_leaves_the_budget_for_the_next_action(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        top_k=20,
        embedder=FakeEmbedder(),
        generator=_Generator("Saturday hours."),
        judge=_Judge(*([_eval(sufficient=False, supported=None)] * 8)),
        index=_FixedIndex(0.5),
        max_recoveries=1,
        rewriter=_Rewriter(),
        recovery_policy="v2a_expand_first",
    )
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    steps = [(item["action"], item["executed"]) for item in payload["recovery_attempts"]]
    # Before #147 the no-op expand spent the only recovery and the run gave up.
    assert steps == [("expand", False), ("rewrite", True)]
    assert payload["verification"]["outcome"] == "still_failing"


def test_budget_counts_only_real_attempts_and_bounds_no_ops() -> None:
    noop = {"action": "expand", "executed": False}
    skipped_rewrite = {"action": "rewrite", "executed": False}
    real = {"action": "regenerate", "executed": True}
    assert not _budget_spent([noop], 1)
    assert _budget_spent([noop, real], 1)
    assert _budget_spent([skipped_rewrite], 1)
    assert _budget_spent([noop, noop, noop], 1)


def test_an_empty_slice_has_no_mean() -> None:
    assert _mean([]) is None
    assert _mean([True, False]) == 0.5
