"""LLM-as-judge grounding signals (ADR 003).

One chat completion returns both flags. Sufficiency is judged from the
question and evidence only; support is judged from the generated answer
against the same evidence. The prompt never includes gold answers.
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

_SYSTEM_PROMPT = """You are a grounding judge for retrieval-augmented generation.
You will see a question, retrieved evidence, and optionally a generated answer.
You have no gold answer and must not use knowledge outside the evidence.

Return a JSON object with exactly these keys:
- evidence_sufficient: boolean. True only if the retrieved evidence contains
  enough information to answer the question correctly. Decide this from the
  question and evidence alone. Ignore the generated answer.
- answer_supported: boolean or null. Null if no answer was generated. True
  only if every factual claim in the generated answer is supported by the
  evidence. An explicit abstention ("I do not know") asserts no facts, so it
  is supported. A correct-looking answer that is not in the evidence is not
  supported.
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
        return RuntimeEvaluation(
            evidence_sufficient=sufficient,
            answer_supported=(
                _optional_bool(payload.get("answer_supported")) if has_answer else None
            ),
            sufficiency_rationale=str(payload.get("sufficiency_rationale") or "").strip(),
            support_rationale=str(payload.get("support_rationale") or "").strip(),
            judge="llm-judge",
            model=self.model_name,
        )


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
