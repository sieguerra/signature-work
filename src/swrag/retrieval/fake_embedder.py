"""Deterministic bag-of-tokens embedder for tests (no API)."""

from __future__ import annotations

import hashlib
import re
from typing import Sequence

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "the",
        "to",
        "when",
        "with",
    }
)


class FakeEmbedder:
    """Hash tokens into a fixed-size bag-of-words vector."""

    def __init__(self, *, dim: int = 4096) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim
        self.model_name = "fake-hash"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            if token in _STOPWORDS:
                continue
            bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
            vector[bucket] += 1.0
        return vector
