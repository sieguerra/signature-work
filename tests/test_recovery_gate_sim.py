"""Offline gate candidates. They do not change the live policy."""

from __future__ import annotations

import pytest

from swrag.recovery_benchmark.gate_sim import (
    CANDIDATES,
    adopt,
    simulate,
    triggers_current,
    triggers_ignore_margin,
    triggers_stop_abstention,
    triggers_two_signals,
)


def _rows() -> list[dict]:
    return [
        {
            "panel": "analysis",
            "triggered": True,
            "logical_id": "bad-abstain",
            "before_state": "incorrect",
            "evidence_sufficient": False,
            "answer_supported": True,
            "weak_top": False,
            "ambiguous_top": False,
            "before_abstained": True,
            "added_latency_ms": 100,
            "attempts": [{"chat_calls": 2, "prompt_tokens": 10, "completion_tokens": 1, "embedding_tokens": 1}],
        },
        {
            "panel": "analysis",
            "triggered": True,
            "logical_id": "margin-ok",
            "before_state": "correct",
            "evidence_sufficient": True,
            "answer_supported": True,
            "weak_top": False,
            "ambiguous_top": True,
            "before_abstained": False,
            "added_latency_ms": 50,
            "attempts": [{"chat_calls": 1, "prompt_tokens": 10, "completion_tokens": 1, "embedding_tokens": 1}],
        },
    ]


def test_candidates_and_adoption() -> None:
    rows = _rows()
    assert triggers_current(rows[0]) is True
    assert triggers_stop_abstention(rows[0]) is False
    assert triggers_ignore_margin(rows[1]) is False
    assert triggers_two_signals(rows[0]) is False
    with pytest.raises(ValueError):
        simulate([{**rows[0], "panel": "future_holdout"}], triggers_current)
    results = {name: simulate(rows, rule) for name, rule in CANDIDATES.items()}
    assert results["stop_explicit_abstention"]["needed_missed"] == 1
    assert results["ignore_ambiguous_margin"]["needed_missed"] == 0
    assert results["ignore_ambiguous_margin"]["triggered_runs_skipped"] == 1
    assert adopt(results) == "ignore_ambiguous_margin"
