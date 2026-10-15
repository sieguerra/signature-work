"""OpenAI chat generation from retrieved chunks."""

from __future__ import annotations

from openai import OpenAI

from swrag.config import ProviderConfig, load_provider_config, openai_client
from swrag.types import GenerationResult, RetrievalResult
from swrag.usage import record_chat

_SYSTEM_PROMPT = """You are a baseline RAG assistant.
Answer the user using only the provided evidence chunks.
If the evidence is insufficient, say you do not know based on the retrieved documents.
When you use a chunk, mention its chunk_id in brackets, for example [harbor-library::c000].
Do not invent facts that are not in the evidence."""


def compose_system_prompt(instructions: str = "") -> str:
    """Grounding rules first; optional project instructions cannot override them."""
    extra = instructions.strip()
    if not extra:
        return _SYSTEM_PROMPT
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        "Additional project instructions (still never invent facts):\n"
        f"{extra}"
    )


class OpenAIGenerator:
    def __init__(
        self,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
        config: ProviderConfig | None = None,
        instructions: str = "",
    ) -> None:
        resolved = config or load_provider_config()
        self.model_name = model or resolved.chat_model
        self.base_url = resolved.base_url
        self.instructions = instructions
        self._client = client or openai_client(resolved.base_url)

    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        evidence = _format_evidence(retrieval)
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": compose_system_prompt(self.instructions)},
                {
                    "role": "user",
                    "content": f"Question:\n{query}\n\nEvidence:\n{evidence}",
                },
            ],
            temperature=0,
        )
        record_chat(response)
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
