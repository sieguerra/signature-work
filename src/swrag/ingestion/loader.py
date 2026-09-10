"""Load local text documents from a corpus directory."""

from __future__ import annotations

from pathlib import Path

from swrag.types import Document


def load_documents(corpus_dir: str | Path) -> list[Document]:
    """Load every ``.txt`` file in ``corpus_dir`` (non-recursive)."""
    directory = Path(corpus_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Corpus directory not found: {directory}")

    documents: list[Document] = []
    for path in sorted(directory.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        documents.append(
            Document(
                doc_id=path.stem,
                title=_title_from_stem(path.stem),
                path=str(path.resolve()),
                text=text,
            )
        )
    if not documents:
        raise ValueError(f"No .txt files found in {directory}")
    return documents


def _title_from_stem(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").strip().title()
