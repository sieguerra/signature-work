"""Offline transition labels. Gold stays in this module and the benchmark scorer.

Verifier candidates must not import this module. The rank rules were fixed
before any v2 prediction was computed. F1 movement inside a rank is ignored
on purpose: a different wrong answer is still failing, and a paraphrase that
does not contain a gold string is not credited as correct.
"""

from __future__ import annotations

from swrag.evaluation.scoring import score_answer
from swrag.types import AnswerScore, GoldQuestion
from swrag.verification.v2.protocol import CLASSES, RANK_CORRECT

IMPROVED = "improved"
UNCHANGED = "unchanged"
STILL_FAILING = "still_failing"
DEGRADED = "degraded"


def quality_rank(score: AnswerScore) -> int:
    """Map one offline score to a rank. Higher is better for the user.

    Unanswerable + abstention is correct (rank 2), following the SQuAD 2.0
    convention that abstaining on an unanswerable question scores as a hit.
    Answerable + abstention is the middle rank: safer than an invented answer,
    worse than a correct one. Every other attempt is a failure (rank 0).
    """
    if not score.answerable and score.abstained:
        return RANK_CORRECT
    if score.answerable and score.contains_answer and not score.abstained:
        return RANK_CORRECT
    if score.answerable and score.abstained:
        return 1
    return 0


def transition_label(before: AnswerScore, after: AnswerScore) -> str:
    """Label one before → after pair. Both scores must be the same question."""
    if before.answerable != after.answerable:
        raise ValueError("before and after scores are for different answerability")
    before_rank = quality_rank(before)
    after_rank = quality_rank(after)
    if after_rank > before_rank:
        return IMPROVED
    if after_rank < before_rank:
        return DEGRADED
    if after_rank == RANK_CORRECT:
        return UNCHANGED
    return STILL_FAILING


def label_answers(
    before_answer: str,
    after_answer: str,
    gold: GoldQuestion,
    *,
    before_abstained: bool | None = None,
    after_abstained: bool | None = None,
) -> str:
    """Score both answers, then label the transition.

    Abstention flags default to the text heuristic in ``score_answer``. Pass
    them only when the caller already knows the user-visible text is an
    abstention. Controller versus generated origin is not a gold distinction:
    gold scores what the user received.
    """
    before = score_answer(before_answer, gold, abstained=before_abstained)
    after = score_answer(after_answer, gold, abstained=after_abstained)
    label = transition_label(before, after)
    if label not in CLASSES:
        raise RuntimeError(f"labeler returned {label!r}")
    return label
