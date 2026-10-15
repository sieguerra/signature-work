"""OpenAI embedding client."""

from __future__ import annotations

from typing import Sequence

from openai import OpenAI

from swrag.config import ProviderConfig, load_provider_config, openai_client
from swrag.usage import record_embedding

# One embeddings request stays under the provider's input-array limit.
# Corpus indexing sends every chunk through this method.
_EMBED_BATCH = 128


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
        self._client = client or openai_client(resolved.base_url)
        self._cache: dict[str, list[float]] = {}

    def clear_cache(self) -> None:
        """Forget cached vectors so the next condition pays for its own queries."""
        self._cache.clear()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        missing = [text for text in texts if text not in self._cache]
        for start in range(0, len(missing), _EMBED_BATCH):
            batch = missing[start : start + _EMBED_BATCH]
            response = self._client.embeddings.create(
                model=self.model_name,
                input=batch,
            )
            record_embedding(response)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(batch):
                raise ValueError("Embedder returned the wrong number of vectors")
            for text, item in zip(batch, ordered, strict=True):
                self._cache[text] = list(item.embedding)
        return [list(self._cache[text]) for text in texts]
