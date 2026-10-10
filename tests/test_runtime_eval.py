"""Runtime grounding-judge tests. No live API calls."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.evaluation.llm_judge import (
    LLMJudge,
    build_judge_prompt,
    constrain_support_to_evidence,
    extract_checkable_facts,
    facts_missing_from_evidence,
)
from swrag.evaluation.scripted_judge import ScriptedJudge
from swrag.recovery.policy import REGENERATE, select_recovery
from swrag.pipeline.baseline import run_query
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import Chunk, RetrievalResult, RuntimeEvaluation, ScoredChunk

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "corpus"


def _chunk() -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(
            chunk_id="harbor-library::c000",
            doc_id="harbor-library",
            title="Harbor Library",
            text="Saturday: 10:00-16:00",
            start_char=0,
            end_char=22,
        ),
        score=0.9,
    )


def test_scripted_judge_never_requires_gold_fields() -> None:
    retrieval = RetrievalResult(
        query="q",
        chunks=(_chunk(),),
        top_k=1,
        embedding_model="fake-hash",
    )
    evaluation = ScriptedJudge(evidence_sufficient=False, answer_supported=False).judge(
        question="q",
        answer="something unsupported",
        retrieval=retrieval,
    )
    assert evaluation.evidence_sufficient is False
    assert evaluation.answer_supported is False
    assert evaluation.judge == "scripted"


def test_scripted_judge_leaves_support_null_when_no_answer() -> None:
    retrieval = RetrievalResult(
        query="q",
        chunks=(_chunk(),),
        top_k=1,
        embedding_model="fake-hash",
    )
    evaluation = ScriptedJudge().judge(question="q", answer="", retrieval=retrieval)
    assert evaluation.answer_supported is None


def test_run_query_attaches_runtime_evaluation_to_the_trace(tmp_path: Path) -> None:
    result = run_query(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        top_k=3,
        embedder=FakeEmbedder(),
        generate=False,
        judge=ScriptedJudge(evidence_sufficient=True, answer_supported=True),
    )
    assert result.runtime_evaluation is not None
    assert result.runtime_evaluation.evidence_sufficient is True
    assert result.runtime_evaluation.answer_supported is None

    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["runtime_evaluation"]["judge"] == "scripted"
    assert payload["runtime_evaluation"]["evidence_sufficient"] is True
    assert payload["runtime_evaluation"]["answer_supported"] is None
    assert "exact_match" not in payload
    assert "answers" not in payload
    assert payload["diagnosis"]["failure_class"] is None


def test_run_query_without_a_judge_records_null_runtime_evaluation(tmp_path: Path) -> None:
    result = run_query(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generate=False,
    )
    assert result.runtime_evaluation is None
    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["runtime_evaluation"] is None
    assert payload["diagnosis"] is None


def test_judge_prompt_contains_question_evidence_and_answer_not_gold() -> None:
    prompt = build_judge_prompt(
        "What are Saturday hours?",
        "10:00-16:00",
        (_chunk(),),
    )
    assert "What are Saturday hours?" in prompt
    assert "10:00-16:00" in prompt
    assert "harbor-library::c000" in prompt
    assert "gold" not in prompt.lower()
    assert "NJ-12" not in prompt


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self.content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


def test_llm_judge_parses_json_and_does_not_see_gold() -> None:
    client = _FakeClient(
        json.dumps(
            {
                "evidence_sufficient": True,
                "answer_supported": False,
                "sufficiency_rationale": "hours are in the chunk",
                "support_rationale": "answer invents a Tuesday slot",
            }
        )
    )
    judge = LLMJudge(model="gpt-4o-mini", client=client)
    retrieval = RetrievalResult(
        query="Saturday hours?",
        chunks=(_chunk(),),
        top_k=1,
        embedding_model="fake-hash",
    )
    evaluation = judge.judge(
        question="Saturday hours?",
        answer="Open until midnight on Tuesday",
        retrieval=retrieval,
    )
    assert evaluation.evidence_sufficient is True
    assert evaluation.answer_supported is False
    assert evaluation.judge == "llm-judge"
    user_content = client.chat.completions.calls[0]["messages"][1]["content"]
    assert "Saturday hours?" in user_content
    assert "gold" not in user_content.lower()


def test_llm_judge_system_prompt_rejects_plausible_ungrounded_claims() -> None:
    client = _FakeClient(
        json.dumps(
            {
                "evidence_sufficient": True,
                "answer_supported": True,
                "sufficiency_rationale": "hours are in the chunk",
                "support_rationale": "sounds like a library",
            }
        )
    )
    judge = LLMJudge(model="gpt-4o-mini", client=client)
    retrieval = RetrievalResult(
        query="Saturday hours?",
        chunks=(_chunk(),),
        top_k=1,
        embedding_model="fake-hash",
    )
    judge.judge(question="Saturday hours?", answer="10:00-16:00", retrieval=retrieval)
    system = client.chat.completions.calls[0]["messages"][0]["content"]
    assert "correct-looking" in system
    assert "chunk text" in system
    assert "does not contain a requested fact" in system


def test_extract_checkable_facts_ignores_citation_brackets() -> None:
    facts = extract_checkable_facts(
        "Saturday 10:00-16:00 [harbor-library::c000]. Email desk@harbor.example."
    )
    assert "10:00" in facts
    assert "16:00" in facts
    assert "desk@harbor.example" in facts
    assert not any("c000" in item for item in facts)


def test_span_check_overrides_lenient_llm_support() -> None:
    retrieval = RetrievalResult(
        query="Saturday hours?",
        chunks=(_chunk(),),
        top_k=1,
        embedding_model="fake-hash",
    )
    client = _FakeClient(
        json.dumps(
            {
                "evidence_sufficient": True,
                "answer_supported": True,
                "sufficiency_rationale": "the chunk lists Saturday hours",
                "support_rationale": "the hours sound right for a campus library",
            }
        )
    )
    judge = LLMJudge(model="gpt-4o-mini", client=client)
    evaluation = judge.judge(
        question="Saturday hours?",
        answer="Open 10:00-16:00 and the library has 800 seats.",
        retrieval=retrieval,
    )
    assert evaluation.evidence_sufficient is True
    assert evaluation.answer_supported is False
    assert "800" in evaluation.support_rationale
    assert facts_missing_from_evidence(
        "Open 10:00-16:00 and the library has 800 seats.",
        retrieval,
    ) == ("800",)


def test_span_check_keeps_support_when_facts_are_in_the_chunk() -> None:
    retrieval = RetrievalResult(
        query="Saturday hours?",
        chunks=(_chunk(),),
        top_k=1,
        embedding_model="fake-hash",
    )
    lenient = RuntimeEvaluation(
        evidence_sufficient=True,
        answer_supported=True,
        sufficiency_rationale="hours present",
        support_rationale="llm said yes",
        judge="llm-judge",
        model="fixture",
    )
    evaluation = constrain_support_to_evidence(
        lenient,
        answer="Saturday 10:00-16:00 [harbor-library::c000]",
        retrieval=retrieval,
    )
    assert evaluation.answer_supported is True
    assert evaluation.support_rationale == "llm said yes"


def test_span_check_skips_abstention() -> None:
    retrieval = RetrievalResult(
        query="q",
        chunks=(_chunk(),),
        top_k=1,
        embedding_model="fake-hash",
    )
    lenient = RuntimeEvaluation(
        evidence_sufficient=False,
        answer_supported=True,
        sufficiency_rationale="none",
        support_rationale="abstention",
        judge="llm-judge",
        model="fixture",
    )
    evaluation = constrain_support_to_evidence(
        lenient,
        answer="I do not know based on the retrieved documents.",
        retrieval=retrieval,
    )
    assert evaluation.answer_supported is True


def test_unsupported_fact_selects_regenerate() -> None:
    retrieval = RetrievalResult(
        query="Saturday hours?",
        chunks=(_chunk(),),
        top_k=1,
        embedding_model="fake-hash",
    )
    evaluation = constrain_support_to_evidence(
        RuntimeEvaluation(
            evidence_sufficient=True,
            answer_supported=True,
            sufficiency_rationale="hours present",
            support_rationale="lenient",
            judge="llm-judge",
            model="fixture",
        ),
        answer="Saturday 10:00-16:00 plus 800 extra seats.",
        retrieval=retrieval,
    )
    diagnosis = diagnose_runtime(evaluation)
    decision = select_recovery(diagnosis, evaluation)
    assert evaluation.answer_supported is False
    assert diagnosis.failure_class == "unsupported_generation"
    assert decision.action == REGENERATE


def test_twelve_hour_gloss_of_a_present_time_is_not_missing() -> None:
    retrieval = RetrievalResult(
        query="When does the meeting end?",
        chunks=(
            ScoredChunk(
                chunk=Chunk(
                    chunk_id="meetings::c000",
                    doc_id="meetings",
                    title="Meetings",
                    text="Monthly meeting: first Tuesday, 19:00, ice-plant break room.",
                    start_char=0,
                    end_char=58,
                ),
                score=0.9,
            ),
        ),
        top_k=1,
        embedding_model="none",
    )
    assert facts_missing_from_evidence("It starts at 7:00 PM.", retrieval) == ()
    missing = facts_missing_from_evidence(
        "The meeting ends at 20:00 (8:00 PM) since it starts at 19:00 (7:00 PM).",
        retrieval,
    )
    assert "20:00" in missing
    assert any(token.lower().startswith("8:00") for token in missing)
    assert "19:00" not in missing
    assert not any(token.lower().startswith("7:00") for token in missing)


def test_span_check_records_rejected_clocks() -> None:
    retrieval = RetrievalResult(
        query="When does the meeting end?",
        chunks=(
            ScoredChunk(
                chunk=Chunk(
                    chunk_id="meetings::c000",
                    doc_id="meetings",
                    title="Meetings",
                    text="Monthly meeting: first Tuesday, 19:00, ice-plant break room.",
                    start_char=0,
                    end_char=58,
                ),
                score=0.9,
            ),
        ),
        top_k=1,
        embedding_model="none",
    )
    evaluation = constrain_support_to_evidence(
        RuntimeEvaluation(
            evidence_sufficient=True,
            answer_supported=True,
            sufficiency_rationale="the start time is present",
            support_rationale="lenient",
            judge="llm-judge",
            model="fixture",
        ),
        answer="The meeting ends at 20:00 (8:00 PM).",
        retrieval=retrieval,
    )
    assert evaluation.evidence_sufficient is True
    assert evaluation.answer_supported is False
    assert evaluation.span_rejections


def test_span_check_accepts_unpadded_times_that_appear_padded() -> None:
    retrieval = RetrievalResult(
        query="Friday desk hours?",
        chunks=(
            ScoredChunk(
                chunk=Chunk(
                    chunk_id="dku-library-hours::c000",
                    doc_id="dku-library-hours",
                    title="DKU Library hours",
                    text="Monday-Friday: 09:00-21:00",
                    start_char=0,
                    end_char=26,
                ),
                score=0.9,
            ),
        ),
        top_k=1,
        embedding_model="none",
    )
    assert facts_missing_from_evidence("Friday desk 9:00-21:00", retrieval) == ()


def test_llm_judge_strips_markdown_fences() -> None:
    client = _FakeClient(
        "```json\n"
        '{"evidence_sufficient": false, "answer_supported": null, '
        '"sufficiency_rationale": "empty", "support_rationale": ""}\n'
        "```"
    )
    judge = LLMJudge(client=client)
    retrieval = RetrievalResult(
        query="q",
        chunks=(),
        top_k=0,
        embedding_model="none",
    )
    evaluation = judge.judge(question="q", answer="", retrieval=retrieval)
    assert evaluation.evidence_sufficient is False
    assert evaluation.answer_supported is None
