"""Secondary gold labels. The primary rank stays in Verification v2.

These functions exist so the benchmark can show whether a stricter or a
slightly looser rule would have changed the labels. They are not used to
decide that a recovery succeeded.
"""

from __future__ import annotations

from swrag.evaluation.scoring import score_answer
from swrag.recovery_benchmark.protocol import PARAPHRASE_F1
from swrag.types import AnswerScore, GoldQuestion
from swrag.verification.v2.gold_transition import (
    DEGRADED,
    IMPROVED,
    STILL_FAILING,
    UNCHANGED,
    quality_rank,
)
from swrag.verification.v2.protocol import RANK_CORRECT


def paraphrase_rank(score: AnswerScore) -> int:
    """Phase 6 rank, plus exact match or token F1 at the frozen threshold.

    Numeric paraphrases such as "five hundred sixty" for "560" still miss.
    This rule does not call a model.
    """
    if not score.answerable and score.abstained:
        return RANK_CORRECT
    textual = score.contains_answer or score.exact_match or score.f1 >= PARAPHRASE_F1
    if score.answerable and textual and not score.abstained:
        return RANK_CORRECT
    if score.answerable and score.abstained:
        return 1
    return 0


def label_from_ranks(before_rank: int, after_rank: int) -> str:
    if after_rank > before_rank:
        return IMPROVED
    if after_rank < before_rank:
        return DEGRADED
    if after_rank == RANK_CORRECT:
        return UNCHANGED
    return STILL_FAILING


def paraphrase_label(before_answer: str, after_answer: str, gold: GoldQuestion) -> str:
    before = score_answer(before_answer, gold)
    after = score_answer(after_answer, gold)
    return label_from_ranks(paraphrase_rank(before), paraphrase_rank(after))


def grounded_label(
    before_answer: str,
    after_answer: str,
    gold: GoldQuestion,
    *,
    before_doc_ids: tuple[str, ...],
    after_doc_ids: tuple[str, ...],
    primary: str,
) -> str:
    """Primary label, except a text hit with no supporting document drops to a miss.

    When gold supplies no supporting ids, this equals ``primary``.
    """
    if not gold.supporting_doc_ids:
        return primary
    before = score_answer(before_answer, gold)
    after = score_answer(after_answer, gold)
    before_rank = quality_rank(before)
    after_rank = quality_rank(after)
    if before_rank == RANK_CORRECT and not _hits(before_doc_ids, gold.supporting_doc_ids):
        before_rank = 0
    if after_rank == RANK_CORRECT and not _hits(after_doc_ids, gold.supporting_doc_ids):
        after_rank = 0
    return label_from_ranks(before_rank, after_rank)


def _hits(doc_ids: tuple[str, ...], supporting: tuple[str, ...]) -> bool:
    return bool(set(doc_ids) & set(supporting))
