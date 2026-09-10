"""OpenAI chat generation from retrieved chunks."""

from __future__ import annotations

import os

from openai import OpenAI

from swrag.types import GenerationResult, RetrievalResult

DEFAULT_CHAT_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = """You are a baseline RAG assistant.
Answer the user using only the provided evidence chunks.
If the evidence is insufficient, say you do not know based on the retrieved documents.
When you use a chunk, mention its chunk_id in brackets, for example [harbor-library::c000].
Do not invent facts that are not in the evidence."""


class OpenAIGenerator:
    def __init__(
        self,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.model_name = model or os.environ.get("OPENAI_CHAT_MODEL", DEFAULT_CHAT_MODEL)
        self._client = client or OpenAI()

    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        evidence = _format_evidence(retrieval)
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Question:\n{query}\n\nEvidence:\n{evidence}",
                },
            ],
            temperature=0,
        )
        message = response.choices[0].message.content or ""
        return GenerationResult(answer=message.strip(), model=self.model_name)


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
