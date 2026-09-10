"""Offline scoring tests. No API calls."""

from __future__ import annotations

import pytest

from swrag.evaluation.scoring import (
    contains_answer,
    exact_match,
    looks_like_abstention,
    normalize_answer,
    token_f1,
)
from swrag.evaluation.scoring import score_answer
from swrag.types import GoldQuestion


def _answerable(*answers: str) -> GoldQuestion:
    return GoldQuestion(
        question_id="q1",
        question="irrelevant",
        answerable=True,
        answers=tuple(answers),
    )


def _unanswerable() -> GoldQuestion:
    return GoldQuestion(question_id="q2", question="irrelevant", answerable=False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("The Level 3", "level 3"),
        ("  NJ-12 ", "nj12"),
        ("an apple, a pear.", "apple pear"),
        ("", ""),
    ],
)
def test_normalize_answer(raw: str, expected: str) -> None:
    assert normalize_answer(raw) == expected


def test_exact_match_ignores_case_articles_and_punctuation() -> None:
    assert exact_match("the Level 3.", ("Level 3",))
    assert not exact_match("Level 4", ("Level 3",))


def test_exact_match_accepts_any_alias() -> None:
    assert exact_match("3", ("Level 3", "3"))


def test_contains_answer_finds_gold_inside_prose() -> None:
    prediction = "The quiet study floor is Level 3 [harbor-library::c000]."
    assert contains_answer(prediction, ("Level 3",))
    assert not exact_match(prediction, ("Level 3",))


def test_contains_answer_rejects_empty_prediction() -> None:
    assert not contains_answer("", ("Level 3",))


def test_token_f1_partial_overlap_is_between_zero_and_one() -> None:
    score = token_f1("open 10:00 to 16:00 on Saturday", ("10:00 to 16:00",))
    assert 0.0 < score < 1.0


def test_token_f1_no_overlap_is_zero() -> None:
    assert token_f1("completely unrelated", ("Level 3",)) == 0.0


def test_token_f1_without_answers_is_zero() -> None:
    assert token_f1("anything", ()) == 0.0


def test_looks_like_abstention_detects_refusals() -> None:
    assert looks_like_abstention("I don't know based on the retrieved documents.")
    assert looks_like_abstention("There is not enough information to answer.")
    assert not looks_like_abstention("The lab code is NJ-12.")


def test_score_answerable_correct() -> None:
    score = score_answer("NJ-12", _answerable("NJ-12"))
    assert score.exact_match
    assert score.contains_answer
    assert score.f1 == pytest.approx(1.0)
    assert not score.abstained
    assert score.answerable


def test_score_answerable_prose_is_lenient_only_on_contains() -> None:
    score = score_answer("The lab code is NJ-12 [north-jetty-lab::c000].", _answerable("NJ-12"))
    assert not score.exact_match
    assert score.contains_answer


def test_score_answerable_abstention_scores_zero() -> None:
    score = score_answer("I do not know.", _answerable("NJ-12"))
    assert not score.exact_match
    assert not score.contains_answer
    assert score.f1 == 0.0
    assert score.abstained


def test_score_unanswerable_rewards_abstention() -> None:
    score = score_answer("I do not know based on the documents.", _unanswerable())
    assert score.exact_match
    assert score.f1 == pytest.approx(1.0)
    assert score.abstained
    assert not score.answerable


def test_score_unanswerable_punishes_a_confident_answer() -> None:
    score = score_answer("The nearest stop is Library Plaza.", _unanswerable())
    assert not score.exact_match
    assert score.f1 == 0.0
    assert not score.abstained


def test_explicit_abstained_flag_overrides_the_heuristic() -> None:
    # The text reads like a real answer, but the policy says it abstained.
    score = score_answer("NJ-12", _answerable("NJ-12"), abstained=True)
    assert score.abstained
    assert not score.exact_match
