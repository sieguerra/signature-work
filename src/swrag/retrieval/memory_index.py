"""In-memory cosine-similarity index."""

from __future__ import annotations

import math
from typing import Sequence

from swrag.retrieval.embedder import Embedder
from swrag.types import Chunk, RetrievalResult, ScoredChunk


class InMemoryIndex:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._chunks: list[Chunk] = []
        self._vectors: list[list[float]] = []

    @property
    def embedding_model(self) -> str:
        return self._embedder.model_name

    def add(self, chunks: Sequence[Chunk]) -> None:
        pending = list(chunks)
        if not pending:
            return
        vectors = self._embedder.embed([chunk.text for chunk in pending])
        if len(vectors) != len(pending):
            raise ValueError("Embedder returned the wrong number of vectors")
        self._chunks.extend(pending)
        self._vectors.extend(vectors)

    def search(self, query: str, *, top_k: int = 4) -> RetrievalResult:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not self._chunks:
            return RetrievalResult(
                query=query,
                chunks=(),
                top_k=top_k,
                embedding_model=self.embedding_model,
            )
        query_vector = self._embedder.embed([query])[0]
        scored = [
            ScoredChunk(chunk=chunk, score=_cosine(query_vector, vector))
            for chunk, vector in zip(self._chunks, self._vectors, strict=True)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return RetrievalResult(
            query=query,
            chunks=tuple(scored[:top_k]),
            top_k=top_k,
            embedding_model=self.embedding_model,
        )


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Vector dimensions do not match")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)
