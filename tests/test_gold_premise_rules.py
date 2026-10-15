"""Issue #142: seed-007 relabel, false-premise rejections, near-neighbour traps. No live calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from swrag.evaluation.gold import _parse_question, load_gold_set
from swrag.evaluation.scoring import score_answer

ROOT = Path(__file__).resolve().parents[1]
HARBOR = {q.question_id: q for q in load_gold_set(ROOT / "datasets/gold/questions.jsonl")}
DKU = {q.question_id: q for q in load_gold_set(ROOT / "datasets/dku/gold/questions.jsonl")}


def test_seed_007_is_answerable_with_library_plaza() -> None:
    answer = "There is no shuttle stop at the boat museum. The closest shuttle stop is Library Plaza [tideline-shuttle::c001]."
    score = score_answer(answer, HARBOR["seed-007"])
    assert score.answerable and score.contains_answer and not score.abstained


@pytest.mark.parametrize(
    ("qid", "answer"),
    [
        ("gold-030", "A group room at the Saltmarsh Annex Library cannot be booked because there are no group rooms available there."),
        ("seed-008", "The Coastal Memory Group does not hold any storm records from 1955, as their records only go up to 1940."),
        ("dku-032", "Breakfast at Executive Dining does not have listed hours, indicating that there are no breakfast hours."),
    ],
)
def test_a_correct_premise_rejection_scores_as_an_abstention(qid: str, answer: str) -> None:
    gold = HARBOR.get(qid) or DKU[qid]
    score = score_answer(answer, gold)
    assert score.abstained and score.contains_answer and score.f1 == 1.0


def test_a_trap_beats_a_hedge_on_seed_009() -> None:
    hedge = "A standard meal at the Tide Canteen costs 3 harbor credits. However, the evidence does not specify the rest."
    assert not score_answer(hedge, HARBOR["seed-009"]).abstained
    assert score_answer("I do not know based on the retrieved documents.", HARBOR["seed-009"]).abstained


def test_an_explicit_abstain_flag_is_never_overridden() -> None:
    hedge = "It costs 3 harbor credits."
    assert score_answer(hedge, HARBOR["seed-009"], abstained=True).abstained
    rejection = "There are no group rooms."
    assert not score_answer(rejection, HARBOR["gold-030"], abstained=False).abstained


def test_rejections_and_traps_are_refused_on_answerable_rows() -> None:
    with pytest.raises(ValueError, match="unanswerable questions only"):
        _parse_question({"question_id": "x", "question": "q", "answerable": True, "answers": ["a"], "rejections": ["no"]}, "t")
