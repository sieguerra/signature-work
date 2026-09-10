"""Query rewrite for a second retrieve (ADR 007)."""

from __future__ import annotations

from openai import OpenAI

from swrag.config import ProviderConfig, load_provider_config
from swrag.generation.openai_generator import _format_evidence
from swrag.types import RetrievalResult

_REWRITE_PROMPT = """You rewrite search queries for a retriever.
The current retrieved evidence may be the wrong documents.
Rewrite the question to improve retrieval. Keep the same meaning.
Prefer explicit entity names and distinctive terms already in the question.
Do not answer the question. Do not use facts that are not in the question.
Return only the rewritten query, with no quotes or preamble."""


class LLMQueryRewriter:
    """OpenAI-compatible rewriter. The rewritten string is a search query only."""

    def __init__(
        self,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
        config: ProviderConfig | None = None,
    ) -> None:
        resolved = config or load_provider_config()
        self.model_name = model or resolved.chat_model
        self._client = client or OpenAI(base_url=resolved.base_url)

    def rewrite(self, *, question: str, retrieval: RetrievalResult) -> str:
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": _REWRITE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Current evidence (may be wrong):\n{_format_evidence(retrieval)}"
                    ),
                },
            ],
            temperature=0,
        )
        raw = (response.choices[0].message.content or "").strip().strip('"').strip("'")
        return raw or question


class ScriptedRewriter:
    """Returns a predetermined query. Never calls a model. Never reads gold."""

    def __init__(self, rewritten: str) -> None:
        self._rewritten = rewritten

    def rewrite(self, *, question: str, retrieval: RetrievalResult) -> str:
        del question, retrieval
        return self._rewritten
