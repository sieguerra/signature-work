"""OpenAI embedding client."""

from __future__ import annotations

import os
from typing import Sequence

from openai import OpenAI

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIEmbedder:
    def __init__(
        self,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.model_name = model or os.environ.get(
            "OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        )
        self._client = client or OpenAI()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self.model_name,
            input=list(texts),
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]
