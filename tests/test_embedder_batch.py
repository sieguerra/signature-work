"""Embedding requests must be split so a large corpus can be indexed."""

from swrag.config import ProviderConfig
from swrag.retrieval.openai_embedder import OpenAIEmbedder, _EMBED_BATCH


class _Item:
    def __init__(self, index: int) -> None:
        self.index = index
        self.embedding = [float(index), 1.0]


class _Response:
    def __init__(self, count: int) -> None:
        self.data = [_Item(index) for index in range(count)]


class _Embeddings:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def create(self, *, model: str, input: list[str]) -> _Response:
        del model
        self.batches.append(list(input))
        return _Response(len(input))


class _Client:
    def __init__(self) -> None:
        self.embeddings = _Embeddings()


def test_embed_splits_a_large_corpus_into_batches() -> None:
    client = _Client()
    embedder = OpenAIEmbedder(
        client=client,
        config=ProviderConfig(api_key_present=False),
    )
    texts = [f"chunk-{index}" for index in range(_EMBED_BATCH + 3)]
    vectors = embedder.embed(texts)
    assert [len(batch) for batch in client.embeddings.batches] == [_EMBED_BATCH, 3]
    assert len(vectors) == len(texts)
    assert vectors[0] == [0.0, 1.0]
    assert vectors[_EMBED_BATCH] == [0.0, 1.0]
