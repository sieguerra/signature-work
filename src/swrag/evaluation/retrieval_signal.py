"""A retrieval-quality signal that does not consult the grounding judge.

Issue #64. Every repair in the loop used to be gated on the judge admitting a
failure, which makes one lenient judge call a single point of failure for the
whole self-healing system: if it says the answer is fine, nothing downstream
ever looks again. In the committed Harbor snapshot that produced 27 accepts out
of 32 questions and zero repairs on an answerable question.

This module derives two signals from retrieval scores alone. It calls no model,
reads no gold label, and does not see the generated answer, so it can disagree
with the judge.

``weak_top``
    The best chunk is barely similar to the query, so there is probably nothing
    relevant in the index for this question.

``ambiguous_top``
    The best two chunks score almost identically. The corpora are built with
    dated near-neighbours — a superseded notice beside the current one — where
    the wanted document *is* retrieved but ranks second. Hit rate cannot see
    that failure; margin can.

The thresholds below are **provisional and uncalibrated**. Both raw values are
written to every trace so they can be calibrated from recorded runs rather than
guessed at again.
"""

from __future__ import annotations

from dataclasses import dataclass

from swrag.types import RetrievalResult

DEFAULT_MIN_TOP_SCORE = 0.15
DEFAULT_MIN_RELATIVE_MARGIN = 0.02


@dataclass(frozen=True)
class RetrievalSignal:
    """Judge-independent read of how good a retrieve looks."""

    top_score: float | None
    runner_up_score: float | None
    relative_margin: float | None
    weak_top: bool
    ambiguous_top: bool
    reason: str
    detector: str = "retrieval-score"

    @property
    def is_weak(self) -> bool:
        return self.weak_top or self.ambiguous_top

    def as_trace_payload(self) -> dict[str, object]:
        return {
            "top_score": self.top_score,
            "runner_up_score": self.runner_up_score,
            "relative_margin": self.relative_margin,
            "weak_top": self.weak_top,
            "ambiguous_top": self.ambiguous_top,
            "reason": self.reason,
            "detector": self.detector,
        }


def retrieval_signal(
    retrieval: RetrievalResult,
    *,
    min_top_score: float = DEFAULT_MIN_TOP_SCORE,
    min_relative_margin: float = DEFAULT_MIN_RELATIVE_MARGIN,
) -> RetrievalSignal:
    """Score a retrieve without consulting the judge, the answer, or gold."""
    scores = [scored.score for scored in retrieval.chunks]
    if not scores:
        return RetrievalSignal(
            top_score=None,
            runner_up_score=None,
            relative_margin=None,
            weak_top=True,
            ambiguous_top=False,
            reason="no chunks were retrieved",
        )

    top = scores[0]
    runner_up = scores[1] if len(scores) > 1 else None
    margin = _relative_margin(top, runner_up)

    weak_top = top < min_top_score
    ambiguous_top = margin is not None and margin < min_relative_margin

    return RetrievalSignal(
        top_score=top,
        runner_up_score=runner_up,
        relative_margin=margin,
        weak_top=weak_top,
        ambiguous_top=ambiguous_top,
        reason=_reason(
            top=top,
            margin=margin,
            weak_top=weak_top,
            ambiguous_top=ambiguous_top,
            min_top_score=min_top_score,
            min_relative_margin=min_relative_margin,
        ),
    )


def _relative_margin(top: float, runner_up: float | None) -> float | None:
    """Gap between the top two, as a fraction of the top score.

    Relative rather than absolute so the threshold survives a change of
    embedding model, which moves the absolute scale of cosine scores.
    """
    if runner_up is None:
        return None
    if top <= 0:
        return 0.0
    return (top - runner_up) / top


def _reason(
    *,
    top: float,
    margin: float | None,
    weak_top: bool,
    ambiguous_top: bool,
    min_top_score: float,
    min_relative_margin: float,
) -> str:
    parts: list[str] = []
    if weak_top:
        parts.append(f"top score {top:.3f} is below {min_top_score:.3f}")
    if ambiguous_top and margin is not None:
        parts.append(
            f"top two chunks are within {margin:.1%}, below {min_relative_margin:.1%}"
        )
    if not parts:
        return "retrieval looks healthy"
    return "; ".join(parts)
