"""OpenAI embedding client."""

from __future__ import annotations

from typing import Sequence

from openai import OpenAI

from swrag.config import ProviderConfig, load_provider_config


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

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self.model_name,
            input=list(texts),
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]
