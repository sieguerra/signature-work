"""Paragraph-aware chunking with a character budget and small overlap."""

from __future__ import annotations

import re

from swrag.types import Chunk, Document

DEFAULT_MAX_CHARS = 500
DEFAULT_OVERLAP = 80
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def chunk_documents(
    documents: list[Document],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, max_chars=max_chars, overlap=overlap))
    return chunks


def chunk_document(
    document: Document,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be >= 0 and < max_chars")

    windows = _windows(document.text, max_chars=max_chars, overlap=overlap)
    chunks: list[Chunk] = []
    for index, (start, end, text) in enumerate(windows):
        chunks.append(
            Chunk(
                chunk_id=f"{document.doc_id}::c{index:03d}",
                doc_id=document.doc_id,
                title=document.title,
                text=text,
                start_char=start,
                end_char=end,
            )
        )
    return chunks


def _windows(text: str, *, max_chars: int, overlap: int) -> list[tuple[int, int, str]]:
    units = _paragraph_units(text, max_chars=max_chars, overlap=overlap)
    if not units:
        return [(0, 0, "")]

    windows: list[tuple[int, int, str]] = []
    current_start, current_end, first = units[0]
    current_parts = [first]

    def emit() -> None:
        joined = "\n\n".join(part for part in current_parts if part).strip()
        windows.append((current_start, current_end, joined))

    for start, end, piece in units[1:]:
        candidate_len = len("\n\n".join([*current_parts, piece]))
        if candidate_len <= max_chars:
            current_parts.append(piece)
            current_end = end
            continue
        emit()
        overlap_start = max(current_start, current_end - overlap)
        overlap_text = text[overlap_start:current_end].strip() if overlap else ""
        if overlap_text:
            current_parts = [overlap_text, piece]
            current_start = overlap_start
            if len("\n\n".join(current_parts)) > max_chars:
                current_parts = [piece]
                current_start = start
        else:
            current_parts = [piece]
            current_start = start
        current_end = end

    emit()
    return windows


def _paragraph_units(
    text: str, *, max_chars: int, overlap: int
) -> list[tuple[int, int, str]]:
    units: list[tuple[int, int, str]] = []
    last = 0
    for match in _PARAGRAPH_SPLIT.finditer(text):
        units.extend(
            _units_from_block(text, last, match.start(), max_chars=max_chars, overlap=overlap)
        )
        last = match.end()
    units.extend(
        _units_from_block(text, last, len(text), max_chars=max_chars, overlap=overlap)
    )
    return units


def _units_from_block(
    text: str,
    block_start: int,
    block_end: int,
    *,
    max_chars: int,
    overlap: int,
) -> list[tuple[int, int, str]]:
    block = text[block_start:block_end]
    stripped = block.strip()
    if not stripped:
        return []
    inner_start = block_start + block.find(stripped)
    inner_end = inner_start + len(stripped)
    if len(stripped) <= max_chars:
        return [(inner_start, inner_end, stripped)]
    return _split_long(text, inner_start, inner_end, max_chars=max_chars, overlap=overlap)


def _split_long(
    text: str,
    start: int,
    end: int,
    *,
    max_chars: int,
    overlap: int,
) -> list[tuple[int, int, str]]:
    pieces: list[tuple[int, int, str]] = []
    cursor = start
    while cursor < end:
        piece_end = min(cursor + max_chars, end)
        piece = text[cursor:piece_end].strip()
        if piece:
            pieces.append((cursor, piece_end, piece))
        if piece_end >= end:
            break
        cursor = max(piece_end - overlap, cursor + 1)
    return pieces
