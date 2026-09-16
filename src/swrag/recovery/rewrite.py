"""Query rewrite for a second retrieve (ADR 007)."""

from __future__ import annotations

import re

from openai import OpenAI

from swrag.config import ProviderConfig, load_provider_config
from swrag.generation.openai_generator import _format_evidence
from swrag.types import RetrievalResult
from swrag.usage import record_chat

_REWRITE_PROMPT = """You rewrite search queries for a retriever.
The current retrieved evidence may be the wrong documents.
Rewrite the question to improve retrieval. Keep the same meaning.
Prefer explicit entity names and distinctive terms already in the question.
Do not expand abbreviations. Keep tokens such as DKU or dku as written
unless that expansion already appears in the question.
Do not invent institution names (university, college, institute) that are
not already in the question.
Do not answer the question. Do not use facts that are not in the question.
Return only the rewritten query, with no quotes or preamble."""

_INSTITUTION_TOKENS = frozenset({"university", "college", "institute"})
_TOKEN = re.compile(r"[A-Za-z0-9]+")


def guard_rewritten_query(question: str, rewritten: str) -> str:
    """Drop a rewrite that invents an institution name not in the question."""
    cleaned = (rewritten or "").strip()
    if not cleaned:
        return question
    extra = _tokens(cleaned) - _tokens(question)
    if extra & _INSTITUTION_TOKENS:
        return question
    return cleaned


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN.finditer(text or "")}


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
        record_chat(response)
        raw = (response.choices[0].message.content or "").strip().strip('"').strip("'")
        return guard_rewritten_query(question, raw or question)


class ScriptedRewriter:
    """Returns a predetermined query. Never calls a model. Never reads gold."""

    def __init__(self, rewritten: str) -> None:
        self._rewritten = rewritten

    def rewrite(self, *, question: str, retrieval: RetrievalResult) -> str:
        del question, retrieval
        return self._rewritten
