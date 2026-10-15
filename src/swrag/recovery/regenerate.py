"""Constrained regeneration: the one applied V1 recovery (ADR 006)."""

from __future__ import annotations

from openai import OpenAI

from swrag.config import ProviderConfig, load_provider_config, openai_client
from swrag.generation.openai_generator import _format_evidence
from swrag.types import GenerationResult, RetrievalResult
from swrag.usage import record_chat

_REGENERATE_PROMPT = """You are repairing an unsupported RAG answer.
Write a NEW answer using only the provided evidence chunks. Do not copy the
previous answer. Drop every claim that is not in the evidence, including
numbers, times, and names that do not appear in the chunks.
If the evidence answers only part of the question, answer that part and say
you do not know the rest based on the retrieved documents. If the evidence
is not enough for any part, say you do not know based on the retrieved
documents.
When you use a chunk, mention its chunk_id in brackets."""


class ConstrainedRegenerator:
    """Same retrieval, new answer, tighter grounding instruction."""

    def __init__(
        self,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
        config: ProviderConfig | None = None,
    ) -> None:
        resolved = config or load_provider_config()
        self.model_name = model or resolved.chat_model
        self._client = client or openai_client(resolved.base_url)

    def regenerate(
        self,
        *,
        question: str,
        retrieval: RetrievalResult,
        previous_answer: str,
    ) -> GenerationResult:
        evidence = _format_evidence(retrieval)
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": _REGENERATE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Evidence:\n{evidence}\n\n"
                        f"Previous unsupported answer:\n{previous_answer}"
                    ),
                },
            ],
            temperature=0,
        )
        record_chat(response)
        message = response.choices[0].message.content or ""
        return GenerationResult(answer=message.strip(), model=self.model_name)
