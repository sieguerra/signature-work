"""Recovery-gate audit: human labels, sampling, and offline candidates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swrag.recovery_benchmark.necessity import (
    FORBIDDEN_REVIEW_KEYS,
    action_on_needed,
    assert_analysis_ids,
    assert_blind_payload,
    bootstrap_rate,
    credited_action,
    gate_contingency,
    gating_report,
    miss_report,
    needed_recovery,
    parse_before_label,
    select_nontrigger_ids,
    transition_agreement,
    unchanged_needed_groups,
    unnecessary_cost,
    validate_label_file,
)
from swrag.recovery_benchmark.review import ReviewContamination, parse_human_label

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "tools" / "recovery-review" / "packet"
HTML = ROOT / "tools" / "recovery-review" / "index.html"


def test_before_label_blank_is_missing_and_unclear_is_kept() -> None:
    assert parse_before_label("  ") is None
    assert parse_before_label(None) is None
    assert parse_before_label("Appropriate abstention") == "appropriate_abstention"
    assert parse_before_label("Incomplete but materially insufficient") == "incomplete"
    assert parse_before_label("unclear") == "unclear"
    with pytest.raises(ValueError):
        parse_before_label("maybe")


def test_transition_label_blank_is_missing() -> None:
    assert parse_human_label("") is None
    assert parse_human_label("Still failing") == "still_failing"
    assert parse_human_label("Unclear / cannot determine") == "unclear"


def test_needed_recovery_definition() -> None:
    assert needed_recovery("incorrect") is True
    assert needed_recovery("incomplete") is True
    assert needed_recovery("correct") is False
    assert needed_recovery("appropriate_abstention") is False
    assert needed_recovery("unclear") is None
    assert needed_recovery(None) is None


def test_unclear_is_excluded_from_necessity_and_conditional_success() -> None:
    rows = [
        {"triggered": True, "before_state": "incorrect", "transition": "improved"},
        {"triggered": True, "before_state": "correct", "transition": "unchanged"},
        {"triggered": True, "before_state": "appropriate_abstention", "transition": "unchanged"},
        {"triggered": True, "before_state": "unclear", "transition": "improved"},
        {"triggered": True, "before_state": "", "transition": "degraded"},
        {"triggered": True, "before_state": "incomplete", "transition": "unclear"},
        {"triggered": True, "before_state": "incorrect", "transition": "still_failing"},
    ]
    report = gating_report(rows)
    assert report["n_triggered"] == 7
    assert report["n_decided_before"] == 5
    assert report["n_before_unclear_excluded"] == 1
    assert report["n_before_missing_excluded"] == 1
    assert report["needed"] == 3
    assert report["already_correct"] == 1
    assert report["appropriate_abstention"] == 1
    assert report["necessity_rate"] == 3 / 5
    assert report["unnecessary_rate"] == 2 / 5
    assert report["gate_precision"] == 3 / 5
    assert report["gate_recall"] is None
    assert report["conditional"]["n_needed"] == 3
    assert report["conditional"]["n_decided_transition"] == 2
    assert report["conditional"]["improved"] == 1
    assert report["conditional"]["still_failing"] == 1
    assert report["conditional"]["success_rate"] == 0.5


def test_nontrigger_sample_is_deterministic_and_skips_holdout_and_demo() -> None:
    rows = []
    for index in range(30):
        rows.append(
            {
                "logical_id": f"c{index % 3}:questions.jsonl:q{index}",
                "corpus_id": f"c{index % 3}",
                "recovered": index % 5 == 0,
                "panel": "analysis",
                "answerable": index % 2 == 0,
            }
        )
    rows.append(
        {
            "logical_id": "hold",
            "corpus_id": "dku",
            "recovered": False,
            "panel": "future_holdout",
            "answerable": True,
        }
    )
    rows.append(
        {
            "logical_id": "demo",
            "corpus_id": "recovery-demo",
            "recovered": False,
            "panel": "analysis",
            "answerable": True,
        }
    )
    first = select_nontrigger_ids(rows, limit=8)
    assert first == select_nontrigger_ids(rows, limit=8)
    assert "hold" not in first
    assert "demo" not in first
    assert len(first) == 8
    with pytest.raises(ReviewContamination):
        assert_analysis_ids(["hold"], holdout_ids={"hold"})


def test_miss_rate_uses_only_nontriggered_reviews() -> None:
    rows = [
        {"triggered": False, "before_state": "incorrect"},
        {"triggered": False, "before_state": "correct"},
        {"triggered": False, "before_state": "unclear"},
        {"triggered": True, "before_state": "incorrect"},
    ]
    report = miss_report(rows)
    assert report["n_reviewed"] == 3
    assert report["n_decided"] == 2
    assert report["needed"] == 1
    assert report["miss_rate"] == 0.5


def test_unnecessary_cost_counts_recovery_attempts_only() -> None:
    rows = [
        {
            "triggered": True,
            "before_state": "appropriate_abstention",
            "added_latency_ms": 1000,
            "attempts": [
                {"chat_calls": 2, "prompt_tokens": 1000, "completion_tokens": 100, "embedding_tokens": 50}
            ],
        },
        {
            "triggered": True,
            "before_state": "incorrect",
            "added_latency_ms": 9000,
            "attempts": [
                {"chat_calls": 9, "prompt_tokens": 9000, "completion_tokens": 900, "embedding_tokens": 90}
            ],
        },
    ]
    cost = unnecessary_cost(rows)
    assert cost["n"] == 1
    assert cost["chat_calls"] == 2
    assert cost["added_latency_ms"] == 1000
    assert cost["estimated_usd"] > 0


def test_rewrite_is_not_credited_when_expand_wrote_the_final_answer() -> None:
    attempts = [
        {"action": "rewrite", "after_answer": "I do not know."},
        {"action": "expand", "after_answer": "No. 8 Duke Avenue"},
    ]
    assert credited_action(attempts, "improved") == "expand"
    assert credited_action(attempts, "unchanged") is None
    assert credited_action(attempts, "unclear") is None
    report = action_on_needed(
        [
            {
                "triggered": True,
                "before_state": "incorrect",
                "transition": "improved",
                "path": "rewrite>expand",
                "attempts": attempts,
            }
        ]
    )
    assert report["rewrite>expand"]["credited_action"]["expand"] == 1
    assert "rewrite" not in report["rewrite>expand"]["credited_action"]


def test_human_gold_agreement_excludes_unclear() -> None:
    pairs = [
        {"transition": "improved", "gold_label": "improved", "logical_id": "a"},
        {"transition": "unchanged", "gold_label": "degraded", "logical_id": "dku:questions.jsonl:dku-008"},
        {"transition": "unclear", "gold_label": "improved", "logical_id": "c"},
        {"transition": "", "gold_label": "unchanged", "logical_id": "d"},
    ]
    report = transition_agreement(pairs)
    assert report["n_compared"] == 2
    assert report["matches"] == 1
    assert report["n_unclear_excluded"] == 1
    assert report["n_missing_excluded"] == 1
    assert report["confusion_human_columns"]["degraded"]["unchanged"] == 1
    assert report["disagreements"][0]["logical_id"].endswith("dku-008")


def test_bootstrap_rate_collapses_when_every_flag_matches() -> None:
    report = bootstrap_rate([True, True, True])
    assert report["count"] == 3
    assert report["rate"] == 1
    assert report["low"] == 1
    assert report["high"] == 1


def test_blind_packet_and_page_hide_automatic_labels() -> None:
    assert_blind_payload({"review_id": "R001", "question": "q", "before_answer": "a"})
    with pytest.raises(ReviewContamination):
        assert_blind_payload({"question": "q", "v2_outcome": "improved"})
    page = HTML.read_text(encoding="utf-8")
    assert "recommended label" not in page.lower()
    for key in ("gold_label", "v1_outcome", "v2_outcome", "action"):
        assert key in page
    for name in ("triggered.jsonl", "nontrigger.jsonl"):
        path = PACKET / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            assert FORBIDDEN_REVIEW_KEYS.isdisjoint(row)
            assert "before_state" not in row
            assert "transition" not in row


def test_completed_nontrigger_file_matches_ids_and_rejects_gold() -> None:
    labels = [
        {"review_id": "N001", "before_state": "correct", "transition": ""},
        {"review_id": "N002", "before_state": "unclear", "transition": ""},
    ]
    validate_label_file(labels, expected_ids={"N001", "N002"})
    with pytest.raises(ValueError):
        validate_label_file(labels[:1], expected_ids={"N001", "N002"})
    with pytest.raises(ReviewContamination):
        validate_label_file(
            [{"review_id": "N001", "before_state": "correct", "gold_label": "improved"}],
            expected_ids={"N001"},
        )


def test_contingency_excludes_unclear_and_keeps_the_sample_separate() -> None:
    rows = [
        {"triggered": True, "before_state": "incorrect"},
        {"triggered": True, "before_state": "correct"},
        {"triggered": True, "before_state": "unclear"},
        {"triggered": False, "before_state": "incomplete"},
        {"triggered": False, "before_state": "appropriate_abstention"},
        {"triggered": False, "before_state": "unclear"},
    ]
    table = gate_contingency(rows)
    assert table["triggered_needed"] == 1
    assert table["triggered_not_needed"] == 1
    assert table["not_triggered_needed"] == 1
    assert table["not_triggered_not_needed"] == 1
    assert table["n_unclear_excluded"] == {"triggered": 1, "not_triggered": 1}
    assert table["sampled_miss_rate"] == 0.5
    assert table["nontrigger_is_a_sample"] is True


def test_unchanged_needed_groups_do_not_credit_a_repeated_refusal() -> None:
    rows = [
        {
            "triggered": True,
            "before_state": "incorrect",
            "transition": "unchanged",
            "question_id": "same",
            "attempts": [
                {"action": "rewrite", "after_answer": "I do not know based on the retrieved documents."},
                {"action": "expand", "after_answer": "I do not know based on the retrieved documents."},
            ],
        },
        {
            "triggered": True,
            "before_state": "incorrect",
            "transition": "unchanged",
            "question_id": "reworded",
            "attempts": [
                {"action": "rewrite", "after_answer": "I do not know based on the retrieved documents."},
                {"action": "expand", "after_answer": "I do not know the tuition based on the retrieved documents."},
            ],
        },
        {
            "triggered": True,
            "before_state": "incorrect",
            "transition": "improved",
            "question_id": "fixed",
            "attempts": [
                {"action": "rewrite", "after_answer": "I do not know based on the retrieved documents."},
                {"action": "expand", "after_answer": "No. 8 Duke Avenue"},
            ],
        },
    ]
    groups = unchanged_needed_groups(rows)
    assert groups["refusal_unchanged_through_expand"] == ["same"]
    assert groups["expand_reworded_the_refusal"] == ["reworded"]
    assert groups["other"] == []
