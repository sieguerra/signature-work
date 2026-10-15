"""Load local text and PDF documents from a corpus directory."""

from __future__ import annotations

import logging
from pathlib import Path

from swrag.ingestion.pdf import PdfExtractError, extract_pdf_pages
from swrag.types import Document

logger = logging.getLogger(__name__)

_TEXT_SUFFIX = ".txt"
_PDF_SUFFIX = ".pdf"


def load_documents(corpus_dir: str | Path) -> list[Document]:
    """Load every ``.txt`` and ``.pdf`` file in ``corpus_dir`` (non-recursive).

    ``.txt`` files stay one document per file. Each PDF page with extractable
    text becomes its own document so chunks can carry a 1-based ``page``.
    Unreadable or empty PDFs are skipped with a warning. If nothing readable
    remains, this raises ``ValueError``.
    """
    directory = Path(corpus_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Corpus directory not found: {directory}")

    documents: list[Document] = []
    for path in corpus_files(directory):
        suffix = path.suffix.lower()
        if suffix == _TEXT_SUFFIX:
            document = _document_from_txt(path)
            if not document.text.strip():
                logger.warning("Skipping %s: no text", path.name)
                continue
            documents.append(document)
        elif suffix == _PDF_SUFFIX:
            documents.extend(_documents_from_pdf(path))

    if not documents:
        raise ValueError(f"No readable .txt or .pdf documents found in {directory}")
    return documents


def corpus_files(directory: str | Path) -> list[Path]:
    """``.txt`` and ``.pdf`` files in ``directory``, any extension case, by name.

    Uploads accept ``NOTE.TXT``; a case-sensitive glob used to skip it, so the
    file was stored but never indexed.
    """
    folder = Path(directory)
    if not folder.is_dir():
        return []
    return sorted(
        (
            path
            for path in folder.iterdir()
            # Dot-files are staging copies of uploads, never documents.
            if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in {_TEXT_SUFFIX, _PDF_SUFFIX}
        ),
        key=lambda path: path.name.lower(),
    )


def corpus_file_count(corpus_dir: str | Path) -> int:
    """Count ``.txt`` and ``.pdf`` files (not pages). Missing dirs count as 0."""
    return len(corpus_files(corpus_dir))


def _document_from_txt(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    return Document(
        doc_id=path.stem,
        title=_title_from_stem(path.stem),
        path=str(path.resolve()),
        text=text,
    )


def _documents_from_pdf(path: Path) -> list[Document]:
    try:
        pages = extract_pdf_pages(path)
    except PdfExtractError as error:
        logger.warning("Skipping PDF %s: %s", path.name, error)
        return []
    if not pages:
        logger.warning("Skipping PDF %s: no extractable text", path.name)
        return []
    documents: list[Document] = []
    title = _title_from_stem(path.stem)
    resolved = str(path.resolve())
    for page, text in pages:
        documents.append(
            Document(
                doc_id=f"{path.stem}::p{page}",
                title=title,
                path=resolved,
                text=text,
                page=page,
            )
        )
    return documents


def _title_from_stem(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").strip().title()
