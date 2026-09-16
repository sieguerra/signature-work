"""Parse ``[chunk_id]`` citations against retrieved chunk ids.

Used by tests and documented for the explorer. The UI duplicates the same
match rule in ``web/app.js`` so it can run without importing Python.

A bracket token is linked only when it exactly matches a stored chunk id.
Tokens that look like ``{doc_id}::c{nnn}`` but are not in the retrieve list
are marked missing. Other square brackets stay plain text.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_BRACKET = re.compile(r"\[([^\[\]]+)\]")
_CHUNK_ID = re.compile(r"^[^\s\[\]]+::c\d+$")


class CitationSpan(NamedTuple):
    text: str
    chunk_id: str | None
    kind: str  # "text" | "link" | "missing"


def looks_like_chunk_id(token: str) -> bool:
    """True for the V1 chunk-id shape ``{doc_id}::c{nnn}``."""
    return bool(_CHUNK_ID.fullmatch(token))


def citation_spans(
    text: str, chunk_ids: set[str] | frozenset[str]
) -> list[CitationSpan]:
    """Split ``text`` into spans. Adjacent citations are separate spans."""
    if not text:
        return []
    known = set(chunk_ids)
    pieces: list[CitationSpan] = []
    cursor = 0
    for match in _BRACKET.finditer(text):
        if match.start() > cursor:
            pieces.append(CitationSpan(text[cursor : match.start()], None, "text"))
        token = match.group(1)
        raw = match.group(0)
        if token in known:
            pieces.append(CitationSpan(raw, token, "link"))
        elif looks_like_chunk_id(token):
            pieces.append(CitationSpan(raw, token, "missing"))
        else:
            pieces.append(CitationSpan(raw, None, "text"))
        cursor = match.end()
    if cursor < len(text):
        pieces.append(CitationSpan(text[cursor:], None, "text"))
    return pieces
