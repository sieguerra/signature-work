"""Scripted grounding judge for tests and API-free plumbing checks."""

from __future__ import annotations

from swrag.types import RetrievalResult, RuntimeEvaluation


class ScriptedJudge:
    """Returns predetermined flags. Never calls a model. Never reads gold."""

    def __init__(
        self,
        *,
        evidence_sufficient: bool = True,
        answer_supported: bool | None = True,
        sufficiency_rationale: str = "scripted",
        support_rationale: str = "scripted",
    ) -> None:
        self._evidence_sufficient = evidence_sufficient
        self._answer_supported = answer_supported
        self._sufficiency_rationale = sufficiency_rationale
        self._support_rationale = support_rationale

    def judge(
        self,
        *,
        question: str,
        answer: str,
        retrieval: RetrievalResult,
    ) -> RuntimeEvaluation:
        del question, retrieval  # interface requires these; scripted ignores them
        supported = self._answer_supported if answer.strip() else None
        support_rationale = (
            "no answer generated" if not answer.strip() else self._support_rationale
        )
        return RuntimeEvaluation(
            evidence_sufficient=self._evidence_sufficient,
            answer_supported=supported,
            sufficiency_rationale=self._sufficiency_rationale,
            support_rationale=support_rationale,
            judge="scripted",
            model="none",
        )
