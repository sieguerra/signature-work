"""Schema and metric tests for the offline recoverability audit."""

import json
from pathlib import Path

from swrag.orchestration import loop
from swrag.recovery import policy
from swrag.recovery_benchmark.recoverability import (
    PHASE8A_HOLDOUT_STATUS,
    assert_runtime_payload_has_no_audit_fields,
    lexical_order,
    recoverable_success,
    supporting_rank,
    validate_audit_row,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "experiments/recovery-benchmark/recoverability/phase8b-20261007/audit.jsonl"


def _row(**overrides):
    row = {
        "audit_set": "human_bad",
        "corpus_answerability": "ANSWER_ABSENT",
        "recoverability_class": "CORPUS_GAP",
        "success_kind": "NOT_IMPROVED",
        "search_terms": "wave",
        "documents_inspected": "weather-limit.txt",
        "lexical_result": "no number",
    }
    row.update(overrides)
    return row


def test_answerability_classes_and_present_requires_a_source():
    validate_audit_row(
        _row(
            corpus_answerability="ANSWER_PRESENT",
            recoverability_class="RETRIEVAL_MISS",
            success_kind="ANSWER_RECOVERY",
            supporting_document="hours.txt",
            supporting_passage="No. 8 Duke Avenue",
            why_it_answers="The page lists the address.",
        )
    )
    try:
        validate_audit_row(
            _row(
                corpus_answerability="ANSWER_PRESENT",
                recoverability_class="RETRIEVAL_MISS",
                success_kind="ANSWER_RECOVERY",
                supporting_document="",
                supporting_passage="",
                why_it_answers="",
            )
        )
    except ValueError as exc:
        assert "supporting_document" in str(exc)
    else:
        raise AssertionError("present without a source was accepted")


def test_absent_requires_a_search_record_and_miss_requires_presence():
    try:
        validate_audit_row(_row(search_terms=""))
    except ValueError as exc:
        assert "search_terms" in str(exc)
    else:
        raise AssertionError("absence without a search record was accepted")
    try:
        validate_audit_row(_row(recoverability_class="RETRIEVAL_MISS"))
    except ValueError as exc:
        assert "present" in str(exc)
    else:
        raise AssertionError("a miss was accepted without the answer")


def test_success_on_recoverable_separates_answer_recovery_from_safe_failure():
    rows = [
        _row(
            corpus_answerability="ANSWER_PRESENT",
            recoverability_class="RETRIEVAL_MISS",
            success_kind="ANSWER_RECOVERY",
            supporting_document="a",
            supporting_passage="fact",
            why_it_answers="it states the fact",
        ),
        _row(success_kind="SAFE_FAILURE_RECOVERY"),
        _row(),
    ]
    report = recoverable_success(rows)
    assert report["n_answer_present"] == 1
    assert report["answer_recoveries"] == 1
    assert report["safe_failure_recoveries"] == 1
    assert report["conditional_success_on_recoverable"] == 1.0
    assert report["answer_recovery_rate_on_all_bad"] == 1 / 3


def test_supporting_rank_is_one_based_and_missing_when_unseen():
    assert supporting_rank(["nope", "No.  8 Duke Avenue"], "no. 8 duke avenue") == 2
    assert supporting_rank(["lunch only"], "breakfast ends") is None


def test_lexical_order_surfaces_the_chunk_that_contains_the_query_terms():
    chunks = [
        {"text": "The cafeteria serves lunch."},
        {"text": "The library street address is No. 8 Duke Avenue."},
    ]
    ordered = lexical_order(chunks, "library street address")
    assert ordered[0]["text"].startswith("The library")


def test_offline_fields_cannot_enter_a_runtime_payload():
    assert_runtime_payload_has_no_audit_fields({"answer": "No. 8 Duke Avenue"})
    try:
        assert_runtime_payload_has_no_audit_fields({"corpus_answerability": "ANSWER_PRESENT"})
    except ValueError as exc:
        assert "corpus_answerability" in str(exc)
    else:
        raise AssertionError("an audit field was allowed into a runtime payload")
    assert "recoverability" not in Path(policy.__file__).read_text()
    assert "recoverability" not in Path(loop.__file__).read_text()


def test_phase8a_holdout_is_marked_consumed_and_the_next_holdout_is_unopened():
    status = json.loads((ROOT / "experiments/recovery-benchmark/holdout-status.json").read_text())
    assert status["phase8a_holdout"] == PHASE8A_HOLDOUT_STATUS == "phase8a_holdout_consumed"
    plan = json.loads(
        (ROOT / "experiments/recovery-benchmark/recoverability/future-holdout-plan.json").read_text()
    )
    assert plan["status"] == "designed_not_opened"
    assert plan["outcomes_inspected"] is False
    assert plan["question_ids"] == []


def test_committed_audit_rows_match_the_schema():
    rows = [json.loads(line) for line in AUDIT.read_text().splitlines() if line.strip()]
    bad = [row for row in rows if row["audit_set"] == "human_bad"]
    assert len(bad) == 15
    for row in rows:
        validate_audit_row(row)
    present = [row for row in bad if row["corpus_answerability"] == "ANSWER_PRESENT"]
    assert present
    assert all(row["success_kind"] == "ANSWER_RECOVERY" for row in present if row["human_transition"] == "improved")
    assert all(row["supporting_rank_bucket"] == "5-12" for row in present)
    report = recoverable_success(rows)
    assert report["conditional_success_on_recoverable"] == 1.0
    assert report["safe_failure_recoveries"] == 1
    assert report["n_corpus_gap"] == 13
