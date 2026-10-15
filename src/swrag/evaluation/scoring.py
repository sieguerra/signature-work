"""Offline correctness scoring.

ADR 003 fixes Exact Match and F1 against short gold answers as the offline
ground truth for "did recovery actually help". These functions must never be
called from the runtime accept/retry/abstain path: doing so would let the
system read gold labels and contaminate the central measurement (Huang et al.,
ICLR 2024).

Normalisation follows the usual SQuAD convention (lowercase, strip punctuation
and articles, collapse whitespace) so results are comparable to how extractive
QA is normally scored, with one addition for this corpus: clock times and
ranges are canonicalised first (issue #130). SQuAD's punctuation stripping
turns ``12:00-18:00`` into the single token ``12001800``, so a correct
``12:00 to 18:00`` scored 0. Ranges written with ``-``, an en or em dash,
``to``, ``until`` or ``through`` become two time tokens, and ``08:00`` and
``8:00`` normalise alike, in both the prediction and the gold answer.
"""

from __future__ import annotations

import re
import string
from collections import Counter

from swrag.types import AnswerScore, GoldQuestion

_ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_PUNCTUATION = str.maketrans("", "", string.punctuation)
_CITATION = re.compile(r"\[[^\[\]]+\]")
_TIME = r"(\d{1,2}):(\d{2})"
_TIME_RANGE = re.compile(_TIME + r"\s*(?:-|\u2013|\u2014|to|until|through)\s*" + _TIME, re.IGNORECASE)
_LEADING_ZERO_TIME = re.compile(r"\b0(\d):(\d{2})\b")
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})

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
    # Refusals the model also writes (issue #131).
    "does not specify",
    "do not specify",
    "does not contain",
    "do not contain",
)


def canonicalize_times(text: str) -> str:
    """Write clock ranges as two separate times and drop a leading zero.

    ``12:00 to 18:00``, ``12:00 - 18:00``, ``12:00\u201318:00`` and
    ``12:00-18:00`` all become ``12:00 18:00``; ``08:00`` becomes ``8:00``.
    A single gold time then matches inside a range, and a range matches
    however it was punctuated.
    """
    text = _TIME_RANGE.sub(lambda m: f"{m.group(1)}:{m.group(2)} {m.group(3)}:{m.group(4)}", text)
    return _LEADING_ZERO_TIME.sub(r"\1:\2", text)


def normalize_answer(text: str) -> str:
    """Canonicalise times, lowercase, drop punctuation and articles, collapse whitespace."""
    lowered = canonicalize_times(text).lower()
    without_punctuation = lowered.translate(_PUNCTUATION)
    without_articles = _ARTICLES.sub(" ", without_punctuation)
    return " ".join(without_articles.split())


def looks_like_abstention(answer: str) -> bool:
    """Whether an answer reads as a refusal rather than an attempt.

    A heuristic, deliberately conservative: it matches explicit refusal phrases
    only. Its error rate should be reported alongside any result that depends
    on it.
    """
    lowered = answer.translate(_QUOTES).lower()
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
    # A hedge such as "not mentioned elsewhere" is not a refusal when the
    # answer states the gold fact (issue #131). Offline only: gold is read
    # here, never at runtime.
    if abstained is None and did_abstain and gold.answerable and contains_answer(prediction, gold.answers):
        did_abstain = False

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
