"""In-memory ranking tests with FakeEmbedder (no API)."""

from __future__ import annotations

from swrag.ingestion.chunker import chunk_document
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.retrieval.memory_index import InMemoryIndex
from swrag.types import Document


def test_query_ranks_overlapping_chunk_above_unrelated_chunk() -> None:
    library = Document(
        doc_id="library",
        title="Library",
        path="library.txt",
        text="The harbor library closes at 21:00 on weekdays. Quiet study is on level 3.",
    )
    canteen = Document(
        doc_id="canteen",
        title="Canteen",
        path="canteen.txt",
        text="The cafeteria serves fennel tofu dumplings on Wednesday lunch only.",
    )
    index = InMemoryIndex(FakeEmbedder())
    index.add(chunk_document(library) + chunk_document(canteen))

    result = index.search("what time does the harbor library close", top_k=2)
    assert result.chunks
    assert result.chunks[0].chunk.doc_id == "library"
    assert result.chunks[0].score > result.chunks[1].score
    assert result.embedding_model == "fake-hash"
