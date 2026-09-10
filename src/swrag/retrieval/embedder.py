"""Embedding interface used by retrieval."""

from __future__ import annotations

from typing import Protocol, Sequence


class Embedder(Protocol):
    """Embed texts into dense vectors.

    Implementations must return one vector per input string, in the same order.
    """

    model_name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...
