"""Offline correctness scoring.

ADR 003 fixes Exact Match and F1 against short gold answers as the offline
ground truth for "did recovery actually help". These functions must never be
called from the runtime accept/retry/abstain path: doing so would let the
system read gold labels and contaminate the central measurement (Huang et al.,
ICLR 2024).

Normalisation follows the usual SQuAD convention (lowercase, strip punctuation
and articles, collapse whitespace) so results are comparable to how extractive
QA is normally scored.
"""

from __future__ import annotations

import re
import string
from collections import Counter

from swrag.types import AnswerScore, GoldQuestion

_ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_PUNCTUATION = str.maketrans("", "", string.punctuation)
_CITATION = re.compile(r"\[[^\[\]]+\]")

# Heuristic abstention detection for the baseline pipeline, whose prompt asks the
# model to say it does not know. Phase 1 replaces this with an explicit abstain
# signal from the decision policy; until then this is the only way to tell an
# abstention from a wrong answer.
_ABSTENTION_MARKERS = (
    "i don't know",
    "i do not know",
    "cannot be determined",
    "not enough information",
    "insufficient evidence",
    "insufficient information",
    "no relevant information",
    "not mentioned",
    "not stated",
    "does not say",
    "do not have enough",
    "unable to answer",
)


def normalize_answer(text: str) -> str:
    """Lowercase, drop punctuation and articles, collapse whitespace."""
    lowered = text.lower()
    without_punctuation = lowered.translate(_PUNCTUATION)
    without_articles = _ARTICLES.sub(" ", without_punctuation)
    return " ".join(without_articles.split())


def looks_like_abstention(answer: str) -> bool:
    """Whether an answer reads as a refusal rather than an attempt.

    A heuristic, deliberately conservative: it matches explicit refusal phrases
    only. Its error rate should be reported alongside any result that depends
    on it.
    """
    lowered = answer.lower()
    return any(marker in lowered for marker in _ABSTENTION_MARKERS)


def exact_match(prediction: str, answers: tuple[str, ...]) -> bool:
    normalized = normalize_answer(prediction)
    return any(normalized == normalize_answer(answer) for answer in answers)


def contains_answer(prediction: str, answers: tuple[str, ...]) -> bool:
    """Whether a gold answer appears inside the prediction (Contain-Acc).

    Necessary because the generator returns prose with citations rather than a
    bare span, which drives strict Exact Match to near-zero. Lenient in the
    other direction: a long answer that happens to include the gold string
    counts as correct even if it also says other things.

    Citations are removed first and a gold alias must match whole words, so a
    short alias such as ``3`` or ``no`` is not found inside ``c003``, ``2026``,
    or ``not``.
    """
    words = normalize_answer(_CITATION.sub(" ", prediction)).split()
    if not words:
        return False
    for answer in answers:
        target = normalize_answer(answer).split()
        if not target:
            continue
        width = len(target)
        if any(words[i : i + width] == target for i in range(len(words) - width + 1)):
            return True
    return False


def token_f1(prediction: str, answers: tuple[str, ...]) -> float:
    """Best token-overlap F1 across acceptable answers."""
    if not answers:
        return 0.0
    return max(_single_f1(prediction, answer) for answer in answers)


def score_answer(
    prediction: str,
    gold: GoldQuestion,
    *,
    abstained: bool | None = None,
) -> AnswerScore:
    """Score one answer against its gold question.

    ``abstained`` should be passed explicitly once the decision policy exists.
    When omitted it is inferred with :func:`looks_like_abstention`.

    For unanswerable questions the correct behaviour is abstaining, so an
    abstention scores 1.0 and any attempted answer scores 0.0.
    """
    did_abstain = looks_like_abstention(prediction) if abstained is None else abstained

    if not gold.answerable:
        return AnswerScore(
            exact_match=did_abstain,
            contains_answer=did_abstain,
            f1=1.0 if did_abstain else 0.0,
            abstained=did_abstain,
            answerable=False,
        )

    if did_abstain:
        return AnswerScore(
            exact_match=False,
            contains_answer=False,
            f1=0.0,
            abstained=True,
            answerable=True,
        )

    return AnswerScore(
        exact_match=exact_match(prediction, gold.answers),
        contains_answer=contains_answer(prediction, gold.answers),
        f1=token_f1(prediction, gold.answers),
        abstained=False,
        answerable=True,
    )


def _single_f1(prediction: str, answer: str) -> float:
    predicted_tokens = normalize_answer(prediction).split()
    gold_tokens = normalize_answer(answer).split()
    if not predicted_tokens or not gold_tokens:
        # Both empty is a match; one empty is not.
        return float(predicted_tokens == gold_tokens)

    overlap = Counter(predicted_tokens) & Counter(gold_tokens)
    shared = sum(overlap.values())
    if shared == 0:
        return 0.0

    precision = shared / len(predicted_tokens)
    recall = shared / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)
