"""Recovery benchmark accounting. No live model calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swrag.evaluation.scoring import score_answer
from swrag.recovery_benchmark.demo import demo_question_ids, load_demo_manifest
from swrag.recovery_benchmark.gold import paraphrase_label, paraphrase_rank
from swrag.recovery_benchmark.inventory import (
    DemoContamination,
    QuestionRecord,
    load_questions,
    questions_to_generate,
    runtime_inputs,
)
from swrag.recovery_benchmark.protocol import DEMO_CORPUS_ID, SEED
from swrag.recovery_benchmark.review import (
    agreement,
    assert_blind_payload,
    cohens_kappa,
    parse_human_label,
    select_review_ids,
)
from swrag.recovery_benchmark.scoring import (
    HoldoutLeak,
    build_metrics,
    composition,
    proportion_interval,
    render_summary,
    score_trace,
    score_tree,
)
from swrag.recovery_benchmark.split import assign_split, normalize_question, token_set, jaccard
from swrag.types import GoldQuestion
from swrag.verification.v2.benchmark import blind_review_row
from swrag.verification.v2.examples import Example
from swrag.verification.v2.gold_transition import label_answers, quality_rank
from swrag.verification.v2.transitions import StateView, Transition

ROOT = Path(__file__).resolve().parents[1]


def _record(
    logical_suffix: str,
    question: str,
    *,
    corpus: str = "harbor",
    answerable: bool = True,
    source: str = "questions.jsonl",
    question_id: str | None = None,
) -> QuestionRecord:
    qid = question_id or logical_suffix
    return QuestionRecord(
        corpus_id=corpus,
        domain="test",
        group="test",
        question_id=qid,
        question=question,
        answerable=answerable,
        answers=("560",) if answerable else (),
        supporting_doc_ids=("doc",) if answerable else (),
        source=source,
        gold_path=f"datasets/{corpus}/gold/{source}",
        logical_id=f"{corpus}:{source}:{qid}",
    )


def _chunk() -> dict:
    return {
        "chunk_id": "doc::c000",
        "doc_id": "doc",
        "title": "Doc",
        "text": "The library lists 560 seats.",
        "score": 0.4,
    }


def _trace(question_id: str, before: str, after: str, actions: list[str]) -> dict:
    attempts = []
    for action in actions:
        attempts.append(
            {
                "action": action,
                "answer": after,
                "executed": True,
                "answer_relation": "generated",
                "evidence_relation": "unchanged",
                "evaluation_source": "judge",
                "verification": {"outcome": "still_failing"},
            }
        )
    return {
        "query": "How many seats does the library list?",
        "question_id": question_id,
        "answer": after,
        "model": "gpt-4o-mini",
        "trace_schema_version": 2,
        "initial": {
            "answer": before,
            "retrieved_chunks": [_chunk()],
            "diagnosis": {"failure_class": "unsupported_generation"},
            "latency_ms": 1000,
        },
        "retrieved_chunks": [_chunk()],
        "recovery_attempts": attempts,
        "verification": {"outcome": "improved"},
        "latency_ms": 2500,
        "usage": {
            "chat_calls": 4,
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "embedding_tokens": 10,
            "tokens_observed": True,
        },
    }


def _row(record: QuestionRecord, panel: str = "analysis") -> dict:
    payload = record.as_dict()
    payload["panel"] = panel
    payload["duplicate_of"] = None
    return payload


def test_exact_duplicates_count_once_and_share_a_panel() -> None:
    left = _record("a", "How many seats does the library list?", question_id="q1")
    right = _record(
        "b",
        "How many seats does the library list?",
        corpus="dku",
        question_id="q9",
        source="recovery.jsonl",
    )
    split = assign_split((left, right), ROOT)
    runnable = [row for row in split["questions"] if not row["duplicate_of"]]
    assert len(runnable) == 1
    assert split["n_exact_duplicates_dropped"] == 1
    panels = {row["panel"] for row in split["questions"]}
    assert len(panels) == 1


def test_near_duplicates_stay_in_one_panel() -> None:
    left = _record("a", "What is the weekday headway on Line Amber today?", question_id="n1")
    right = _record("b", "What is the weekday headway on Line Amber today now?", question_id="n2")
    assert jaccard(token_set(left.question), token_set(right.question)) >= 0.9
    split = assign_split((left, right), ROOT)
    panels = {row["panel"] for row in split["questions"]}
    assert len(panels) == 1


def test_split_is_reproducible() -> None:
    records = tuple(
        _record(
            f"q{index}",
            f"Unique benchmark question number {index} about dock {index}",
            question_id=f"q{index}",
        )
        for index in range(30)
    )
    first = assign_split(records, ROOT)
    second = assign_split(records, ROOT)
    assert [row["panel"] for row in first["questions"]] == [row["panel"] for row in second["questions"]]
    assert first["n_future_holdout"] > 0
    assert first["n_analysis"] > first["n_future_holdout"]


def test_phase6_observed_questions_are_not_in_the_future_holdout() -> None:
    split = assign_split(load_questions(ROOT), ROOT)
    observed_paths = {
        "datasets/kestrel-aero/gold/first-pass-fail.jsonl",
        "datasets/kestrel-aero/gold/recovery.jsonl",
        "datasets/dku/gold/first-pass-fail.jsonl",
        "datasets/dku/gold/recovery.jsonl",
    }
    leaked = [
        row["logical_id"]
        for row in split["questions"]
        if row["gold_path"] in observed_paths and row["panel"] == "future_holdout"
    ]
    assert leaked == []
    assert split["n_future_holdout"] > 0
    assert all(record.corpus_id != DEMO_CORPUS_ID for record in load_questions(ROOT))


def test_demo_questions_never_enter_the_benchmark() -> None:
    questions = load_questions(ROOT)
    demo_ids = demo_question_ids(ROOT)
    assert demo_ids
    assert demo_ids.isdisjoint({record.question_id for record in questions})
    demo_row = _row(_record("x", "demo", corpus=DEMO_CORPUS_ID, question_id="rdemo-accept"))
    demo_row["gold_path"] = "datasets/recovery-demo/gold/questions.jsonl"
    with pytest.raises(DemoContamination):
        questions_to_generate([demo_row])


def test_generate_list_excludes_holdout_and_duplicates() -> None:
    keep = _row(_record("keep", "Unique keep question about berth 4", question_id="keep"))
    hold = _row(
        _record("hold", "Unique hold question about berth 9", question_id="hold"),
        panel="future_holdout",
    )
    copy = _row(_record("copy", "Unique keep question about berth 4", question_id="copy"))
    copy["duplicate_of"] = keep["logical_id"]
    selected = questions_to_generate([keep, hold, copy])
    assert [row["question_id"] for row in selected] == ["keep"]


def test_runtime_inputs_carry_no_gold() -> None:
    record = _record("q", "How many seats?", question_id="q")
    assert runtime_inputs(record) == {"question": "How many seats?"}


def test_attempts_do_not_inflate_question_level_n() -> None:
    record = _record("q", "How many seats does the library list?", question_id="q")
    trace = _trace(
        "q",
        "I do not know based on the retrieved documents.",
        "The library lists 560 seats.",
        ["rewrite", "expand"],
    )
    run_row, attempts = score_trace(trace, _row(record))
    assert run_row is not None
    assert run_row["recovered"] is True
    assert run_row["action"] == "multi"
    assert run_row["outcome"] == "improved"
    assert len(attempts) == 2
    metrics = build_metrics([run_row], attempts)
    assert metrics["n_recovered_logical_runs"] == 1
    assert metrics["n_attempt_rows"] == 2
    assert metrics["outcome_counts"]["improved"] == 1


def test_holdout_trace_is_not_scored(tmp_path: Path) -> None:
    record = _record("q", "How many seats does the library list?", question_id="q")
    with pytest.raises(HoldoutLeak):
        score_trace(
            _trace("q", "about forty", "The library lists 560 seats.", ["rewrite"]),
            _row(record, "future_holdout"),
        )
    split = {"questions": [{**_row(record, "future_holdout"), "duplicate_of": None}]}
    corpus = tmp_path / "harbor" / "questions" / "traces"
    corpus.mkdir(parents=True)
    (corpus / "run.json").write_text(
        json.dumps(_trace("q", "about forty", "The library lists 560 seats.", ["rewrite"])),
        encoding="utf-8",
    )
    run_rows, attempt_rows, skipped = score_tree(split, tmp_path)
    assert run_rows == []
    assert attempt_rows == []
    assert skipped == [record.logical_id]


def test_outcome_and_action_breakdowns_keep_raw_counts() -> None:
    rows = []
    attempts = []
    specs = (
        (1, "about forty", "The library lists 560 seats.", "rewrite"),
        (2, "The library lists 560 seats.", "about forty", "expand"),
        (3, "about forty", "about fifty", "abstain"),
    )
    for index, before, after, action in specs:
        record = _record(f"q{index}", "How many seats does the library list?", question_id=f"q{index}")
        run_row, attempt_rows = score_trace(_trace(f"q{index}", before, after, [action]), _row(record))
        rows.append(run_row)
        attempts.extend(attempt_rows)
    metrics = build_metrics(rows, attempts)
    assert metrics["n_recovered_logical_runs"] == 3
    assert metrics["by_action"]["rewrite"]["n"] == 1
    assert metrics["by_action"]["expand"]["counts"]["degraded"] == 1
    assert metrics["outcome_counts"]["improved"] == 1
    assert metrics["outcome_counts"]["degraded"] == 1
    assert metrics["outcome_counts"]["still_failing"] == 1
    packed = {"questions": [_row(_record("q", "Unique dock question 3", question_id="q"))]}
    text = render_summary(metrics, composition(packed), skipped_holdout=[])
    assert "Independent recovered logical runs: **3**." in text


def test_answerable_and_unanswerable_are_separate() -> None:
    answerable = _record("a", "How many seats does the library list?", question_id="a")
    missing = _record("b", "What is the espresso model?", question_id="b", answerable=False)
    good, _attempts = score_trace(
        _trace("a", "about forty", "The library lists 560 seats.", ["rewrite"]),
        _row(answerable),
    )
    safe, _attempts = score_trace(
        _trace(
            "b",
            "a deluxe espresso",
            "I do not know based on the retrieved documents.",
            ["rewrite"],
        ),
        _row(missing),
    )
    metrics = build_metrics([good, safe], [])
    assert metrics["by_answerability"]["answerable"]["n"] == 1
    assert metrics["by_answerability"]["unanswerable"]["n"] == 1
    assert metrics["by_answerability"]["answerable"]["counts"]["improved"] == 1
    assert metrics["by_answerability"]["unanswerable"]["counts"]["improved"] == 1
    assert metrics["abstention"]["unanswerable_abstained"] == 1
    assert metrics["abstention"]["answerable_abstained"] == 0


def test_bootstrap_interval_collapses_when_every_label_matches() -> None:
    stats = proportion_interval(["improved", "improved", "improved"], "improved", samples=20, seed=SEED)
    assert stats["count"] == 3
    assert stats["rate"] == 1
    assert stats["low"] == 1
    assert stats["high"] == 1


def test_human_unclear_is_excluded_from_agreement() -> None:
    assert parse_human_label("Still failing") == "still_failing"
    assert parse_human_label("Unclear / cannot determine") == "unclear"
    assert parse_human_label("  ") is None
    with pytest.raises(ValueError):
        parse_human_label("maybe")
    report = agreement(
        [
            {"human_label": "improved", "gold_label": "improved", "answerable": True, "action": "rewrite"},
            {"human_label": "unchanged", "gold_label": "improved", "answerable": False, "action": "expand"},
            {"human_label": "unclear", "gold_label": "degraded", "answerable": True, "action": "rewrite"},
            {"human_label": "", "gold_label": "improved", "answerable": True, "action": "rewrite"},
        ]
    )
    assert report["n_compared"] == 2
    assert report["n_unclear_excluded"] == 1
    assert report["n_missing_excluded"] == 1
    assert report["matches"] == 1
    assert report["by_action"]["rewrite"]["n"] == 1


def test_cohen_kappa_for_two_reviewers() -> None:
    perfect = cohens_kappa(["improved", "degraded"], ["improved", "degraded"])
    assert perfect is not None
    assert perfect["agreement"] == 1
    assert perfect["kappa"] == 1
    partial = cohens_kappa(
        ["improved", "improved", "degraded", "unchanged"],
        ["improved", "degraded", "degraded", "unchanged"],
    )
    assert partial is not None
    assert partial["n"] == 4
    assert partial["agreement"] == 0.75


def test_blind_review_rejects_labels_and_actions() -> None:
    with pytest.raises(Exception):
        assert_blind_payload({"question": "q", "action": "rewrite"})
    transition = Transition(
        level="run",
        question="How many seats?",
        before=StateView(answer="before", chunks=(_chunk(),), evidence_known=True),
        after=StateView(answer="after", chunks=(_chunk(),), evidence_known=True),
        action="rewrite",
        executed=True,
        schema_version=2,
    )
    example = Example(
        transition=transition,
        gold_label="improved",
        v1_outcome="improved",
        answerable=True,
        panel="analysis",
        split="analysis",
        source="questions.jsonl",
    )
    blinded = blind_review_row(example)
    assert set(blinded) == {
        "question",
        "before_evidence",
        "before_answer",
        "after_evidence",
        "after_answer",
    }


def test_review_sample_is_deterministic_and_does_not_label() -> None:
    rows = []
    for index in range(12):
        rows.append(
            {
                "logical_id": f"id-{index}",
                "recovered": True,
                "panel": "analysis",
                "outcome": ["improved", "unchanged", "still_failing", "degraded"][index % 4],
                "action": ["rewrite", "expand", "regenerate"][index % 3],
                "answerable": index % 2 == 0,
            }
        )
    assert select_review_ids(rows, limit=8) == select_review_ids(rows, limit=8)
    assert len(select_review_ids(rows, limit=8)) == 8
    assert "label" not in rows[0]


def test_demo_manifest_is_marked_off_benchmark() -> None:
    manifest = load_demo_manifest(ROOT)
    assert manifest["benchmark"] is False
    assert {case["question_id"] for case in manifest["cases"]} == demo_question_ids(ROOT)


def test_primary_gold_ignores_partial_token_overlap() -> None:
    gold = GoldQuestion(
        question_id="g",
        question="q",
        answerable=True,
        answers=("alpha bravo charlie delta",),
    )
    contained = score_answer("alpha bravo charlie delta echo", gold)
    assert contained.contains_answer is True
    assert quality_rank(contained) == 2
    partial = score_answer("alpha bravo only", gold)
    assert partial.contains_answer is False
    assert quality_rank(partial) == 0
    assert paraphrase_rank(partial) == 0
    assert label_answers("wrong topic", "alpha bravo only", gold) == "still_failing"
    assert paraphrase_label("wrong topic", "alpha bravo only", gold) == "still_failing"


def test_normalize_question_collapses_case_and_space() -> None:
    assert normalize_question("  How   Many ") == "how many"
