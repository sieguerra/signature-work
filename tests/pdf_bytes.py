"""Minimal multi-page PDFs with known strings. Used by tests and the fixture."""

from __future__ import annotations


def simple_text_pdf(page_texts: list[str]) -> bytes:
    """Build a tiny PDF-1.4 file whose pages contain ``page_texts`` as Helvetica."""
    if not page_texts:
        raise ValueError("need at least one page")

    font_id = 3
    page_ids = [4 + 2 * index for index in range(len(page_texts))]
    content_ids = [5 + 2 * index for index in range(len(page_texts))]
    bodies: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{_refs(page_ids)}] /Count {len(page_texts)} >>"
        ).encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_id, content_id, text in zip(page_ids, content_ids, page_texts, strict=True):
        stream = (
            f"BT /F1 12 Tf 72 720 Td ({_escape(text)}) Tj ET\n"
        ).encode("latin-1", "replace")
        bodies[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
        )
        bodies[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode("ascii")

    max_id = 3 + 2 * len(page_texts)
    out = bytearray(b"%PDF-1.4\n")
    offsets = {0: 0}
    for obj_id in range(1, max_id + 1):
        offsets[obj_id] = len(out)
        out.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        out.extend(bodies[obj_id])
        out.extend(b"\nendobj\n")
    xref_at = len(out)
    out.extend(f"xref\n0 {max_id + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, max_id + 1):
        out.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (
            f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def _refs(ids: list[int]) -> str:
    return " ".join(f"{obj_id} 0 R" for obj_id in ids)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
