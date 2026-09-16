"""LLM-as-judge grounding signals (ADR 003).

One chat completion returns both flags. Sufficiency is judged from the
question and evidence only; support is judged from the generated answer
against the same evidence. The prompt never includes gold answers.

After the model returns, a deterministic span check can force
``answer_supported`` to false when a checkable fact in the answer is absent
from the retrieved chunk text. That constraint is what issue #32 uses to stop
a lenient judge from first-pass accepting an answer that "sounds right."
"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from swrag.config import ProviderConfig, load_provider_config
from swrag.types import RetrievalResult, RuntimeEvaluation, ScoredChunk
from swrag.usage import record_chat

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_CITATION = re.compile(r"\[[^\[\]]+\]")
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b", re.IGNORECASE)
_ORDINAL = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)
_SPEC = re.compile(r"\b(?:AMS\s*)?\d{4}[A-Z]\b", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"\b\d{3,}\b")
_ABSTAIN_PREFIX = "i do not know"

_SYSTEM_PROMPT = """You are a grounding judge for retrieval-augmented generation.
You will see a question, retrieved evidence, and optionally a generated answer.
You have no gold answer. You must not use knowledge outside the evidence.
A fluent or "correct-looking" answer is not support.

Return a JSON object with exactly these keys:
- evidence_sufficient: boolean. True only if the retrieved evidence text
  itself contains the specific facts needed to answer THIS question.
  Nearby documents about a similar entity, a superseded notice, or a
  related campus do not count unless they state the asked-for fact.
  Decide this from the question and evidence alone. Ignore the generated
  answer.
- answer_supported: boolean or null. Null if no answer was generated. True
  only if every factual claim in the generated answer appears in the
  evidence text. Numbers, clock times, phone numbers, emails, floor
  numbers, seat counts, and specification letters in the answer must occur
  in the evidence. If a claim is absent from the chunk text, answer_supported
  is false even if the claim sounds plausible. An explicit abstention
  ("I do not know") asserts no facts, so it is supported. Saying that the
  evidence does not contain a requested fact is also supported, as long as
  the answer does not then invent that fact.
- sufficiency_rationale: short string (one or two sentences).
- support_rationale: short string (one or two sentences), or empty if
  answer_supported is null.

Do not invent evidence. Do not mention a gold answer."""


class LLMJudge:
    """OpenAI-compatible chat judge. Swappable behind GroundingJudge."""

    def __init__(
        self,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
        config: ProviderConfig | None = None,
    ) -> None:
        resolved = config or load_provider_config()
        self.model_name = model or resolved.chat_model
        self.base_url = resolved.base_url
        self._client = client or OpenAI(base_url=resolved.base_url)

    def judge(
        self,
        *,
        question: str,
        answer: str,
        retrieval: RetrievalResult,
    ) -> RuntimeEvaluation:
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(question, answer, retrieval)},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        record_chat(response)
        raw = response.choices[0].message.content or ""
        payload = _parse_judge_payload(raw)
        has_answer = bool(answer.strip())
        sufficient = payload["evidence_sufficient"]
        if not isinstance(sufficient, bool):
            raise ValueError("evidence_sufficient must be a JSON boolean")
        evaluation = RuntimeEvaluation(
            evidence_sufficient=sufficient,
            answer_supported=(
                _optional_bool(payload.get("answer_supported")) if has_answer else None
            ),
            sufficiency_rationale=str(payload.get("sufficiency_rationale") or "").strip(),
            support_rationale=str(payload.get("support_rationale") or "").strip(),
            judge="llm-judge",
            model=self.model_name,
        )
        return constrain_support_to_evidence(evaluation, answer=answer, retrieval=retrieval)


def extract_checkable_facts(answer: str) -> tuple[str, ...]:
    """Pull times, emails, ordinals, spec letters, and 3+ digit numbers.

    Citation brackets are stripped first so chunk ids are not treated as facts.
    """
    text = _CITATION.sub(" ", answer)
    found: list[str] = []
    seen: set[str] = set()
    for pattern in (_TIME, _EMAIL, _ORDINAL, _SPEC, _LONG_NUMBER):
        for match in pattern.finditer(text):
            token = match.group(0).strip()
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(token)
    return tuple(found)


def facts_missing_from_evidence(
    answer: str,
    retrieval: RetrievalResult,
) -> tuple[str, ...]:
    """Return checkable answer facts that do not occur in retrieved text."""
    blob = _evidence_blob(retrieval)
    missing: list[str] = []
    for fact in extract_checkable_facts(answer):
        if not _fact_in_evidence(fact, blob):
            missing.append(fact)
    return tuple(missing)


def constrain_support_to_evidence(
    evaluation: RuntimeEvaluation,
    *,
    answer: str,
    retrieval: RetrievalResult,
) -> RuntimeEvaluation:
    """Force unsupported when a checkable fact is absent from chunk text.

    Abstentions and empty answers are left unchanged. The LLM flag still
    stands when every extracted fact is present in the evidence.
    """
    if evaluation.answer_supported is None:
        return evaluation
    stripped = answer.strip()
    if not stripped or stripped.lower().startswith(_ABSTAIN_PREFIX):
        return evaluation
    missing = facts_missing_from_evidence(stripped, retrieval)
    if not missing:
        return evaluation
    listed = ", ".join(missing)
    note = f"Span check rejected support: {listed} is not in the retrieved evidence."
    rationale = evaluation.support_rationale
    support_rationale = f"{note} {rationale}".strip() if rationale else note
    return RuntimeEvaluation(
        evidence_sufficient=evaluation.evidence_sufficient,
        answer_supported=False,
        sufficiency_rationale=evaluation.sufficiency_rationale,
        support_rationale=support_rationale,
        judge=evaluation.judge,
        model=evaluation.model,
    )


def _evidence_blob(retrieval: RetrievalResult) -> str:
    if not retrieval.chunks:
        return ""
    return " ".join(_normalize(scored.chunk.text) for scored in retrieval.chunks)


def _normalize(text: str) -> str:
    return text.lower().replace("–", "-").replace("—", "-").replace("−", "-")


def _fact_in_evidence(fact: str, blob: str) -> bool:
    token = _normalize(fact)
    if token and token in blob:
        return True
    if _TIME.fullmatch(fact):
        hours, minutes = fact.split(":")
        unpadded = f"{int(hours)}:{minutes}"
        padded = f"{int(hours):02d}:{minutes}"
        if unpadded in blob or padded in blob:
            return True
    compact_fact = re.sub(r"\s+", "", token)
    compact_blob = re.sub(r"\s+", "", blob)
    return bool(compact_fact) and compact_fact in compact_blob


def _user_prompt(question: str, answer: str, retrieval: RetrievalResult) -> str:
    generated = answer.strip() if answer.strip() else "(no answer generated)"
    return (
        f"Question:\n{question}\n\n"
        f"Evidence:\n{_format_evidence(retrieval)}\n\n"
        f"Generated answer:\n{generated}"
    )


def _format_evidence(retrieval: RetrievalResult) -> str:
    if not retrieval.chunks:
        return "(no chunks retrieved)"
    parts: list[str] = []
    for scored in retrieval.chunks:
        chunk = scored.chunk
        parts.append(
            f"[{chunk.chunk_id}] title={chunk.title} score={scored.score:.4f}\n{chunk.text}"
        )
    return "\n\n".join(parts)


def _parse_judge_payload(raw: str) -> dict[str, Any]:
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"grounding judge returned invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("grounding judge JSON must be an object")
    if "evidence_sufficient" not in payload:
        raise ValueError("grounding judge JSON missing 'evidence_sufficient'")
    return payload


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"expected boolean or null, got {type(value).__name__}")


# Used in tests to inspect prompt construction without an API call.
def build_judge_prompt(question: str, answer: str, chunks: tuple[ScoredChunk, ...]) -> str:
    retrieval = RetrievalResult(
        query=question,
        chunks=chunks,
        top_k=len(chunks),
        embedding_model="none",
    )
    return _user_prompt(question, answer, retrieval)
