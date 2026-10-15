"""Issue #148: the keyless fake embedder handles non-ASCII text. No live calls."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

from swrag.retrieval.fake_embedder import FakeEmbedder, _tokens

ROOT = Path(__file__).resolve().parents[1]


def _old_vector(text: str, dim: int = 4096) -> list[float]:
    """The pre-#148 tokenizer, kept here to prove English is unchanged."""
    from swrag.retrieval.fake_embedder import _STOPWORDS

    vector = [0.0] * dim
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if token not in _STOPWORDS:
            vector[int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim] += 1.0
    return vector


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def test_ascii_corpus_text_embeds_exactly_as_before() -> None:
    embedder = FakeEmbedder()
    files = sorted((ROOT / "datasets").rglob("*.txt"))[:40] + sorted((ROOT / "datasets").rglob("*.md"))[:20]
    texts = [path.read_text(encoding="utf-8", errors="ignore") for path in files]
    texts = [text for text in texts if text.isascii()]
    assert texts
    for text in texts:
        assert embedder.embed([text])[0] == _old_vector(text)


def test_tokens_keep_accents_and_split_cjk_into_bigrams() -> None:
    assert _tokens("Café OPENS at 9_30") == ["café", "opens", "at", "9", "30"]
    assert _tokens("图书馆开放时间") == ["图书", "书馆", "馆开", "开放", "放时", "时间"]
    assert _tokens("馆") == ["馆"]
    assert _tokens("DKU图书馆") == ["dku", "图书", "书馆"]


def test_a_chinese_query_ranks_the_matching_chunk_first() -> None:
    embedder = FakeEmbedder()
    query, *chunks = embedder.embed(["图书馆周六开放时间", "图书馆周六开放时间是上午九点到下午五点。", "食堂的午餐菜单每天更新。"])
    assert _cosine(query, chunks[0]) > 0.0
    assert _cosine(query, chunks[0]) > _cosine(query, chunks[1])
    cafe_query, cafe_doc = embedder.embed(["café hours", "The café opens at noon."])
    assert _cosine(cafe_query, cafe_doc) > 0.0
