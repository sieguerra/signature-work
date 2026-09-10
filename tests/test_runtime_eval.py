"""Runtime grounding-judge tests. No live API calls."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.evaluation.llm_judge import LLMJudge, build_judge_prompt
from swrag.evaluation.scripted_judge import ScriptedJudge
from swrag.pipeline.baseline import run_query
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import Chunk, RetrievalResult, ScoredChunk

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
