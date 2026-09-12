"""Parse ``[chunk_id]`` citations against retrieved chunk ids.

Used by tests and documented for the explorer. The UI duplicates the same
match rule in ``web/app.js`` so it can run without importing Python.
"""

from __future__ import annotations

import re

_BRACKET = re.compile(r"\[([^\[\]]+)\]")


def citation_spans(text: str, chunk_ids: set[str] | frozenset[str]) -> list[tuple[str, str | None]]:
    """Split ``text`` into (segment, linked_chunk_id_or_none) pieces.

    A bracket token is linked only when it exactly matches a stored chunk id.
    Unknown ``[not-a-chunk]`` stays visible as plain text. Adjacent citations
    are separate spans.
    """
    if not text:
        return []
    known = set(chunk_ids)
    pieces: list[tuple[str, str | None]] = []
    cursor = 0
    for match in _BRACKET.finditer(text):
        if match.start() > cursor:
            pieces.append((text[cursor : match.start()], None))
        token = match.group(1)
        if token in known:
            pieces.append((match.group(0), token))
        else:
            pieces.append((match.group(0), None))
        cursor = match.end()
    if cursor < len(text):
        pieces.append((text[cursor:], None))
    return pieces
