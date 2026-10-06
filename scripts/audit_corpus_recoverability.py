"""Offline corpus search for the recoverability audit. Not used by the runtime."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.ingestion.chunker import chunk_documents
from swrag.ingestion.loader import load_documents
from swrag.recovery_benchmark.recoverability import lexical_order, supporting_rank

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "experiments/recovery-benchmark/recoverability/phase8b-20261007/audit.jsonl"
OUT = ROOT / "experiments/recovery-benchmark/recoverability/phase8b-20261007/retrieval_diagnostics.json"

CORPUS = {
    "dku": ROOT / "datasets/dku/corpus",
    "harbor": ROOT / "datasets/corpus",
    "saltwind-coop": ROOT / "datasets/saltwind-coop/corpus",
    "nimbus-seed": ROOT / "datasets/nimbus-seed/corpus",
    "northhaven-water": ROOT / "datasets/northhaven-water/corpus",
    "porthaven-port": ROOT / "datasets/porthaven-port/corpus",
}

ALTERNATES = {
    "dku-053": ["DKU library street address", "No. 8 Duke Avenue library"],
    "dku-012": ["DKU library email", "dkulibrary@dukekunshan.edu.cn"],
    "dku-045": ["DKU library phone number", "2021 library handbook phone"],
    "dku-055": ["DKU campus acres", "200 acres campus"],
}
EXTRA_PHRASES = {
    "dku-045": ["(+86) 0512-36658756", "(0512) 3665-7027"],
    "seed-009": ["3 harbor credits", "4 harbor credits"],
}


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    rows = [json.loads(line) for line in AUDIT.read_text().splitlines() if line.strip()]
    chunks_by_corpus = {}
    for corpus_id, directory in CORPUS.items():
        documents = load_documents(directory)
        chunks = chunk_documents(documents)
        chunks_by_corpus[corpus_id] = [
            {"doc_id": chunk.doc_id, "title": chunk.title, "text": chunk.text} for chunk in chunks
        ]
    indexes = _semantic_indexes(chunks_by_corpus)
    diagnostics = []
    for row in rows:
        chunks = chunks_by_corpus[row["corpus_id"]]
        snippet = row.get("supporting_passage") or ""
        ordered = lexical_order(chunks, row["question"])
        lexical = supporting_rank([chunk["text"] for chunk in ordered], snippet) if snippet else None
        semantic = _semantic_ranks(indexes.get(row["corpus_id"]), row, snippet)
        extra = {}
        for phrase in EXTRA_PHRASES.get(row["question_id"], []):
            extra[phrase] = {
                "lexical_rank": supporting_rank([chunk["text"] for chunk in ordered], phrase),
                "semantic_rank": _phrase_rank(indexes.get(row["corpus_id"]), row["question"], phrase),
            }
        diagnostics.append(
            {
                "question_id": row["question_id"],
                "corpus_answerability": row["corpus_answerability"],
                "lexical_support_rank": lexical,
                "semantic": semantic,
                "lexical_top_document": ordered[0]["doc_id"] if ordered else "",
                "extra_phrases": extra,
            }
        )
    OUT.write_text(json.dumps(diagnostics, indent=2) + "\n")
    print(f"wrote {OUT}")
    for item in diagnostics:
        semantic = item["semantic"]
        print(
            item["question_id"],
            item["corpus_answerability"],
            "lexical",
            item["lexical_support_rank"],
            "semantic",
            None if semantic is None else semantic.get("original_rank"),
            "top20",
            None if semantic is None else semantic.get("in_top_20"),
            "top50",
            None if semantic is None else semantic.get("in_top_50"),
        )


def _phrase_rank(index, query: str, phrase: str) -> int | None:
    if index is None:
        return None
    result = index.search(query, top_k=len(index._chunks))
    return supporting_rank([item.chunk.text for item in result.chunks], phrase)


def _semantic_indexes(chunks_by_corpus: dict) -> dict:
    from swrag.pipeline.baseline import build_corpus_index

    indexes = {}
    for corpus_id, directory in CORPUS.items():
        if chunks_by_corpus[corpus_id]:
            indexes[corpus_id] = build_corpus_index(directory)
    return indexes


def _semantic_ranks(index, row: dict, snippet: str) -> dict | None:
    if index is None:
        return None
    queries = [row["question"], *ALTERNATES.get(row["question_id"], [])]
    ranks = {}
    first = None
    for name, query in zip(("original", "alternate_1", "alternate_2"), queries, strict=False):
        result = index.search(query, top_k=len(index._chunks))
        texts = [item.chunk.text for item in result.chunks]
        rank = supporting_rank(texts, snippet) if snippet else None
        scores = [round(item.score, 4) for item in result.chunks[:2]]
        entry = {
            "query": query,
            "rank": rank,
            "top_score": scores[0] if scores else None,
            "runner_up_score": scores[1] if len(scores) > 1 else None,
            "top_documents": [item.chunk.doc_id for item in result.chunks[:5]],
        }
        ranks[name] = entry
        if name == "original":
            margin = None
            if len(scores) == 2 and scores[0]:
                margin = round((scores[0] - scores[1]) / scores[0], 4)
            first = {
                **entry,
                "relative_margin": margin,
                "in_top_4": rank is not None and rank <= 4,
                "in_top_12": rank is not None and rank <= 12,
                "in_top_20": rank is not None and rank <= 20,
                "in_top_50": rank is not None and rank <= 50,
                "beyond_50": rank is None or rank > 50,
            }
    return {"original_rank": None if first is None else first["rank"], "queries": ranks, **(first or {})}


if __name__ == "__main__":
    main()
