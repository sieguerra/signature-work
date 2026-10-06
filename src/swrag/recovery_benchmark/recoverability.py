"""Offline corpus-answerability labels. The runtime does not import this module.

Answerability is a property of the source files, not of top-k retrieval.
"""

from __future__ import annotations

import math
import re
from collections import Counter

ANSWERABILITY = frozenset({"ANSWER_PRESENT", "ANSWER_ABSENT", "PARTIAL", "AMBIGUOUS"})
RECOVERABILITY = frozenset(
    {"RETRIEVAL_MISS", "GENERATION_FAILURE", "CORPUS_GAP", "AMBIGUOUS"}
)
SUCCESS_KIND = frozenset(
    {"ANSWER_RECOVERY", "SAFE_FAILURE_RECOVERY", "NOT_IMPROVED", "NOT_APPLICABLE"}
)
PHASE8A_HOLDOUT_STATUS = "phase8a_holdout_consumed"
RUNTIME_FORBIDDEN_FIELDS = frozenset(
    {
        "corpus_answerability",
        "recoverability_class",
        "supporting_passage",
        "supporting_rank",
        "benchmark_answerable",
    }
)

_TOKEN = re.compile(r"[a-z0-9]+")


def validate_audit_row(row: dict) -> None:
    """Raise if a row is missing its class, or a present answer has no source."""
    answerability = row.get("corpus_answerability")
    if answerability not in ANSWERABILITY:
        raise ValueError(f"invalid corpus_answerability: {answerability!r}")
    kind = row.get("recoverability_class")
    if kind not in RECOVERABILITY:
        raise ValueError(f"invalid recoverability_class: {kind!r}")
    success = row.get("success_kind")
    if success not in SUCCESS_KIND:
        raise ValueError(f"invalid success_kind: {success!r}")
    if answerability == "ANSWER_PRESENT":
        for field in ("supporting_document", "supporting_passage", "why_it_answers"):
            if not str(row.get(field) or "").strip():
                raise ValueError(f"ANSWER_PRESENT requires {field}")
    if answerability == "ANSWER_ABSENT":
        for field in ("search_terms", "documents_inspected", "lexical_result"):
            if not str(row.get(field) or "").strip():
                raise ValueError(f"ANSWER_ABSENT requires {field}")
    if answerability != "ANSWER_PRESENT" and kind == "RETRIEVAL_MISS":
        raise ValueError("a retrieval miss requires the answer to be present")
    if success == "ANSWER_RECOVERY" and answerability != "ANSWER_PRESENT":
        raise ValueError("answer recovery requires the answer to be present")


def recoverable_success(rows: list[dict]) -> dict:
    """Human-improved answer recoveries over bad runs whose answer is in the corpus.

    Safe-failure improvements are counted separately and are not the numerator.
    """
    bad = [row for row in rows if row.get("audit_set") == "human_bad"]
    for row in bad:
        validate_audit_row(row)
    present = [row for row in bad if row["corpus_answerability"] == "ANSWER_PRESENT"]
    answer_hits = [row for row in present if row["success_kind"] == "ANSWER_RECOVERY"]
    safe = [row for row in bad if row["success_kind"] == "SAFE_FAILURE_RECOVERY"]
    return {
        "n_human_bad": len(bad),
        "n_answer_present": len(present),
        "n_answer_absent": sum(row["corpus_answerability"] == "ANSWER_ABSENT" for row in bad),
        "n_partial": sum(row["corpus_answerability"] == "PARTIAL" for row in bad),
        "n_ambiguous_answerability": sum(row["corpus_answerability"] == "AMBIGUOUS" for row in bad),
        "n_retrieval_miss": sum(row["recoverability_class"] == "RETRIEVAL_MISS" for row in bad),
        "n_generation_failure": sum(row["recoverability_class"] == "GENERATION_FAILURE" for row in bad),
        "n_corpus_gap": sum(row["recoverability_class"] == "CORPUS_GAP" for row in bad),
        "n_other": sum(row["recoverability_class"] == "AMBIGUOUS" for row in bad),
        "answer_recoveries": len(answer_hits),
        "safe_failure_recoveries": len(safe),
        "conditional_success_on_recoverable": _rate(len(answer_hits), len(present)),
        "answer_recovery_rate_on_all_bad": _rate(len(answer_hits), len(bad)),
        "safe_failure_rate_on_all_bad": _rate(len(safe), len(bad)),
    }


def supporting_rank(ordered_texts: list[str], snippet: str) -> int | None:
    """1-based rank of the first text containing the snippet. None if it never appears."""
    needle = " ".join(snippet.casefold().split())
    if not needle:
        return None
    for index, text in enumerate(ordered_texts, start=1):
        if needle in " ".join(text.casefold().split()):
            return index
    return None


def lexical_order(chunks: list[dict], query: str) -> list[dict]:
    """Order chunks by a small BM25 score. Offline diagnostic, not the runtime index."""
    docs = [_tokens(str(chunk.get("text") or "")) for chunk in chunks]
    query_terms = _tokens(query)
    if not chunks or not query_terms:
        return list(chunks)
    df = Counter(term for doc in docs for term in set(doc))
    n_docs = len(docs)
    avg = sum(len(doc) for doc in docs) / n_docs
    scored = []
    for chunk, doc in zip(chunks, docs, strict=True):
        counts = Counter(doc)
        score = 0.0
        for term in query_terms:
            if term not in counts:
                continue
            idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            freq = counts[term]
            score += idf * (freq * 2.2) / (freq + 1.2 * (1 - 0.75 + 0.75 * len(doc) / avg))
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored]


def assert_runtime_payload_has_no_audit_fields(payload: dict) -> None:
    leaked = RUNTIME_FORBIDDEN_FIELDS & set(payload)
    if leaked:
        raise ValueError("runtime payload contains offline audit fields: " + ", ".join(sorted(leaked)))


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
