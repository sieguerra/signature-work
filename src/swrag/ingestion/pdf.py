"""Extract text from a local PDF, keeping 1-based page identity."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError


class PdfExtractError(ValueError):
    """The file is not a readable PDF (corrupt, encrypted, or empty bytes)."""


def extract_pdf_pages(path: str | Path) -> list[tuple[int, str]]:
    """Return ``(page_number, text)`` for pages with extractable text.

    Page numbers are 1-based. Pages whose extracted text is empty are omitted.
    Unreadable files raise ``PdfExtractError`` so the loader can skip or fail
    closed instead of indexing an empty stand-in.
    """
    pdf_path = Path(path)
    try:
        reader = PdfReader(str(pdf_path))
    except (PdfReadError, PdfStreamError, OSError, ValueError) as error:
        raise PdfExtractError(f"{pdf_path.name}: {error}") from error

    if getattr(reader, "is_encrypted", False):
        try:
            decrypted = reader.decrypt("")
        except Exception as error:  # noqa: BLE001 — pypdf raises several types here
            raise PdfExtractError(f"{pdf_path.name}: encrypted ({error})") from error
        if decrypted == 0:
            raise PdfExtractError(f"{pdf_path.name}: encrypted")

    pages: list[tuple[int, str]] = []
    try:
        total = len(reader.pages)
    except Exception as error:  # noqa: BLE001
        raise PdfExtractError(f"{pdf_path.name}: {error}") from error

    if total == 0:
        return []

    for index, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception as error:  # noqa: BLE001
            raise PdfExtractError(f"{pdf_path.name} page {index}: {error}") from error
        text = raw.strip()
        if text:
            pages.append((index, text))
    return pages
