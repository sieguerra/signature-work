"""OpenAI embedding client."""

from __future__ import annotations

from typing import Sequence

from openai import OpenAI

from swrag.config import ProviderConfig, load_provider_config
from swrag.usage import record_embedding


class OpenAIEmbedder:
    def __init__(
        self,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
        config: ProviderConfig | None = None,
    ) -> None:
        resolved = config or load_provider_config()
        self.model_name = model or resolved.embedding_model
        self.base_url = resolved.base_url
        self._client = client or OpenAI(base_url=resolved.base_url)
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        missing = [text for text in texts if text not in self._cache]
        if missing:
            response = self._client.embeddings.create(
                model=self.model_name,
                input=missing,
            )
            record_embedding(response)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(missing):
                raise ValueError("Embedder returned the wrong number of vectors")
            for text, item in zip(missing, ordered, strict=True):
                self._cache[text] = list(item.embedding)
        return [list(self._cache[text]) for text in texts]
