"""External evaluation adapter. No live OpenAI."""

from __future__ import annotations

from pathlib import Path

import pytest

from swrag.api.external import (
    MAX_CONTEXTS,
    ExternalPayloadError,
    evaluate_external,
    parse_external_body,
    query_state_from_external,
    unavailable_actions_payload,
)
from swrag.evaluation.scripted_judge import ScriptedJudge
from swrag.recovery.policy import EXPAND, REWRITE


def test_parse_rejects_oversized_and_malformed_payloads() -> None:
    with pytest.raises(ExternalPayloadError, match="JSON object"):
        parse_external_body([])
    with pytest.raises(ExternalPayloadError, match="query is required"):
        parse_external_body({"query": "  ", "answer": "a", "contexts": []})
    with pytest.raises(ExternalPayloadError, match="answer is required"):
        parse_external_body({"query": "hours?", "contexts": []})
    with pytest.raises(ExternalPayloadError, match="contexts is required"):
        parse_external_body({"query": "hours?", "answer": "closed"})
    with pytest.raises(ExternalPayloadError, match="at most"):
        parse_external_body(
            {
                "query": "hours?",
                "answer": "closed",
                "contexts": [{"text": "x"}] * (MAX_CONTEXTS + 1),
            }
        )
    with pytest.raises(ExternalPayloadError, match="text must be a string"):
        parse_external_body(
            {"query": "hours?", "answer": "closed", "contexts": [{"text": 12}]}
        )


def test_adapter_builds_query_state_without_applying_recovery(tmp_path: Path) -> None:
    judge = ScriptedJudge(evidence_sufficient=False, answer_supported=False)
    query, answer, contexts, metadata = parse_external_body(
        {
            "query": "When is the library open on Saturday?",
            "answer": "It is open until midnight.",
            "contexts": [
                {
                    "chunk_id": "hours::c000",
                    "doc_id": "hours",
                    "title": "Hours",
                    "text": "Saturday 10:00-16:00.",
                    "score": 0.81,
                }
            ],
            "metadata": {"agent": "langchain"},
        }
    )
    state = query_state_from_external(
        query=query, answer=answer, contexts=contexts, judge=judge
    )
    assert state.runtime_evaluation is not None
    assert state.runtime_evaluation.evidence_sufficient is False
    assert state.diagnosis is not None
    result, written, decision = evaluate_external(
        query=query,
        answer=answer,
        contexts=contexts,
        judge=judge,
        output_dir=tmp_path,
        project_id="demo",
        metadata=metadata,
    )
    assert written.runtime_evaluation is not None
    assert decision.action == REWRITE
    assert result.trace_path is not None
    payload = result.trace_path.read_text(encoding="utf-8")
    assert "langchain" in payload
    assert "midnight" in payload
    assert REWRITE in unavailable_actions_payload()
    assert EXPAND in unavailable_actions_payload()
