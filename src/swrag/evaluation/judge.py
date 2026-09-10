"""Runtime grounding-judge interface.

ADR 003: the runtime signal is independent of gold labels. Implementations
must accept only the question, the generated answer, and the retrieved
evidence. A later MiniCheck-style NLI judge can replace the LLM judge without
touching the controller, as long as it satisfies this protocol.
"""

from __future__ import annotations

from typing import Protocol

from swrag.types import RetrievalResult, RuntimeEvaluation


class GroundingJudge(Protocol):
    """Produce evidence-sufficiency and answer-support signals."""

    def judge(
        self,
        *,
        question: str,
        answer: str,
        retrieval: RetrievalResult,
    ) -> RuntimeEvaluation:
        """Return structured grounding flags.

        ``answer`` may be empty (retrieve-only). In that case
        ``answer_supported`` should be ``None``.
        """
        ...
