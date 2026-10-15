"""Deterministic bag-of-tokens embedder for tests (no API)."""

from __future__ import annotations

import hashlib
import re
from typing import Sequence

# Letters and digits in any script. On ASCII text this is exactly the old
# [a-z0-9]+ (after lower()), so English rankings do not move (issue #148).
_TOKEN = re.compile(r"[^\W_]+")
# Chinese and Japanese are written without spaces, so a run of these
# characters is one "word" to the pattern above. Split such runs into
# overlapping character bigrams, the usual offline choice for CJK text.
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
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
        for token in _tokens(text):
            if token in _STOPWORDS:
                continue
            bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
            vector[bucket] += 1.0
        return vector


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _TOKEN.findall(text.lower()):
        start = 0
        for run in _CJK.finditer(word):
            if run.start() > start:
                tokens.append(word[start:run.start()])
            chars = run.group()
            tokens.extend(chars[i : i + 2] for i in range(max(1, len(chars) - 1)))
            start = run.end()
        if start < len(word):
            tokens.append(word[start:])
    return tokens
