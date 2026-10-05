"""Schema v2 records what the loop did. It does not change the loop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swrag.api.overview import logical_run_history
from swrag.orchestration.loop import (
    ABSTAIN_ANSWER,
    _apply_expand,
    apply_recovery,
    run_first_pass,
    run_with_recovery,
)
from swrag.pipeline.baseline import QueryState, run_query
from swrag.recovery.policy import EXPAND
from swrag.recovery.rewrite import ScriptedRewriter
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.tracing.schema import (
    SCHEMA_VERSION,
    evidence_for_attempt,
    first_pass_diagnosis,
    schema_version,
)
from swrag.types import (
    Chunk,
    GenerationResult,
    RecoveryDecision,
    RetrievalResult,
    RuntimeEvaluation,
    ScoredChunk,
)

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "corpus"
GOLD_ONLY = (
    "answerable",
    "exact_match",
    "contains_answer",
    "supporting_doc_ids",
    "gold_path",
    "gold_f1",
    "verification_vs_gold",
)


def _eval(*, sufficient: bool, supported: bool | None) -> RuntimeEvaluation:
    return RuntimeEvaluation(
        evidence_sufficient=sufficient,
        answer_supported=supported,
        sufficiency_rationale="test",
        support_rationale="test",
        judge="scripted",
        model="none",
    )


class _Judge:
    def __init__(self, *results: RuntimeEvaluation) -> None:
        self._results = list(results)

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        return self._results.pop(0)


class _Generator:
    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)

    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return GenerationResult(answer=self._answers.pop(0), model="scripted")


class _Regenerator:
    def regenerate(self, *, question: str, retrieval: RetrievalResult, previous_answer: str) -> GenerationResult:
        del question, retrieval, previous_answer
        return GenerationResult(answer="Saturday 10:00-16:00", model="regen")


def _load(result) -> dict:
    return json.loads(result.trace_path.read_text(encoding="utf-8"))


def _assert_no_gold(payload: dict) -> None:
    encoded = json.dumps(payload)
    for key in GOLD_ONLY:
        assert f'"{key}"' not in encoded


def _assert_attempt_order(payload: dict) -> None:
    attempts = payload.get("recovery_attempts") or []
    assert [item["index"] for item in attempts] == list(range(len(attempts)))
    if not attempts:
        assert payload["initial"] is None
        return
    initial = payload["initial"]
    assert initial["query"] == payload["query"]
    last = attempts[-1]
    if last["executed"]:
        assert last["answer"] == payload["answer"]
        if last["runtime_evaluation"] is not None and payload["runtime_evaluation"] is not None:
            assert (
                last["runtime_evaluation"]["answer_supported"]
                == payload["runtime_evaluation"]["answer_supported"]
            )
    for item in attempts:
        if item["action"] == "accept":
            continue
        assert item["answer_relation"] in {
            "generated",
            "kept_previous",
            "abstained",
            "unchanged",
            "none",
        }
        if item["evidence_relation"] in {"replaced", "widened"}:
            assert item["retrieved_chunks"]
            assert evidence_for_attempt(payload, item["index"]) == item["retrieved_chunks"]
        else:
            assert "retrieved_chunks" not in item
        if item["verification"] is not None:
            assert item["verification"]["outcome"]
        if item["answer_relation"] == "generated":
            assert evidence_for_attempt(payload, item["index"])


def test_retrieve_only_records_mode_and_invents_no_attempt(tmp_path: Path) -> None:
    result = run_query(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generate=False,
        run_mode="retrieve_only",
    )
    payload = _load(result)
    assert payload["trace_schema_version"] == SCHEMA_VERSION
    assert payload["run_mode"] == "retrieve_only"
    assert payload["answer"] == ""
    assert payload["model"] == "none"
    assert payload["recovery_attempts"] is None
    assert payload["initial"] is None
    assert payload["runtime_evaluation"] is None
    _assert_attempt_order(payload)
    _assert_no_gold(payload)


def test_baseline_records_the_answer_and_no_recovery(tmp_path: Path) -> None:
    result = run_query(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_Generator("Saturday hours."),  # type: ignore[arg-type]
        run_mode="baseline",
    )
    payload = _load(result)
    assert payload["run_mode"] == "baseline"
    assert payload["answer"] == "Saturday hours."
    assert payload["recovery"] is None
    assert payload["recovery_attempts"] is None
    assert payload["initial"] is None
    _assert_no_gold(payload)


def test_accept_is_not_an_attempt(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_Generator("Saturday hours."),  # type: ignore[arg-type]
        judge=_Judge(_eval(sufficient=True, supported=True)),
        max_recoveries=2,
    )
    payload = _load(result)
    assert payload["run_mode"] == "loop"
    assert payload["recovery"]["action"] == "accept"
    assert payload["recovery_attempts"] is None
    assert payload["initial"] is None
    assert payload["verification"] is None
    _assert_attempt_order(payload)


def test_regenerate_keeps_evidence_and_the_first_diagnosis(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_Generator("The library is on the moon."),  # type: ignore[arg-type]
        regenerator=_Regenerator(),
        judge=_Judge(
            _eval(sufficient=True, supported=False),
            _eval(sufficient=True, supported=True),
        ),
    )
    payload = _load(result)
    attempt = payload["recovery_attempts"][0]
    assert result.answer == "Saturday 10:00-16:00"
    assert payload["verification"]["outcome"] == "improved"
    assert attempt["action"] == "regenerate"
    assert attempt["answer"] == "Saturday 10:00-16:00"
    assert attempt["answer_relation"] == "generated"
    assert attempt["evidence_relation"] == "unchanged"
    assert attempt["evaluation_source"] == "judge"
    assert attempt["source"] == "policy"
    assert attempt["verification"]["outcome"] == "improved"
    assert attempt["runtime_evaluation"]["answer_supported"] is True
    assert "retrieved_chunks" not in attempt
    assert evidence_for_attempt(payload, 0) == payload["initial"]["retrieved_chunks"]
    assert payload["initial"]["answer"] == "The library is on the moon."
    assert payload["initial"]["diagnosis"]["failure_class"] == "unsupported_generation"
    assert payload["diagnosis"]["failure_class"] is None
    assert first_pass_diagnosis(payload)["failure_class"] == "unsupported_generation"
    history = logical_run_history(tmp_path)
    assert history["runs"][0]["diagnoses"] == ["unsupported_generation"]
    _assert_attempt_order(payload)
    _assert_no_gold(payload)


def test_failed_rewrite_keeps_a_supported_answer_with_the_new_evidence(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_Generator("Saturday hours."),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("library saturday hours"),
        judge=_Judge(
            _eval(sufficient=False, supported=True),
            _eval(sufficient=False, supported=None),
        ),
        max_recoveries=1,
    )
    payload = _load(result)
    attempt = payload["recovery_attempts"][0]
    assert attempt["action"] == "rewrite"
    assert attempt["answer_relation"] == "kept_previous"
    assert attempt["answer"] == "Saturday hours."
    assert attempt["evidence_relation"] == "replaced"
    assert attempt["search_query"] == "library saturday hours"
    assert attempt["retrieved_chunks"]
    assert attempt["evaluation_source"] == "carried"
    assert attempt["probe_evaluation"]["evidence_sufficient"] is False
    assert attempt["probe_evaluation"]["answer_supported"] is None
    assert payload["initial"]["query"] == "When is the library open?"
    assert payload["initial"]["answer"] == "Saturday hours."
    assert payload["query"] == "When is the library open?"
    _assert_attempt_order(payload)


def test_rewrite_then_expand_keeps_each_answer_with_its_evidence(tmp_path: Path) -> None:
    result = run_with_recovery(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        top_k=4,
        embedder=FakeEmbedder(),
        generator=_Generator("answer A", "answer B", "answer C"),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("library saturday hours"),
        judge=_Judge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=None),
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=True),
        ),
        max_recoveries=2,
    )
    payload = _load(result)
    rewrite, expand = payload["recovery_attempts"]
    assert [item["action"] for item in payload["recovery_attempts"]] == ["rewrite", "expand"]
    assert payload["initial"]["answer"] == "answer A"
    assert rewrite["answer"] == "answer B"
    assert rewrite["answer_relation"] == "generated"
    assert rewrite["evidence_relation"] == "replaced"
    assert rewrite["search_query"] == "library saturday hours"
    assert rewrite["rewritten_query"] == "library saturday hours"
    assert rewrite["probe_evaluation"]["evidence_sufficient"] is True
    assert rewrite["probe_evaluation"]["answer_supported"] is None
    assert rewrite["runtime_evaluation"]["evidence_sufficient"] is False
    assert rewrite["evaluation_source"] == "judge"
    assert rewrite["verification"]["outcome"] == "still_failing"
    assert expand["answer"] == "answer C"
    assert expand["answer_relation"] == "generated"
    assert expand["evidence_relation"] == "widened"
    assert expand["search_query"] == "library saturday hours"
    assert expand["top_k"] == 12
    assert expand["parameters"]["from_k"] == 4
    assert expand["parameters"]["to_k"] == 12
    assert expand["runtime_evaluation"]["evidence_sufficient"] is True
    assert expand["runtime_evaluation"]["answer_supported"] is True
    assert expand["verification"]["outcome"] == "improved"
    assert payload["answer"] == "answer C"
    assert payload["verification"]["outcome"] == "improved"
    assert rewrite["verification"]["outcome"] != payload["verification"]["outcome"]
    assert evidence_for_attempt(payload, 0) == rewrite["retrieved_chunks"]
    assert evidence_for_attempt(payload, 1) == expand["retrieved_chunks"]
    assert payload["initial"]["diagnosis"]["failure_class"] is None
    assert "not diagnosed on the first pass" in payload["initial"]["diagnosis"]["rationale"]
    _assert_attempt_order(payload)
    _assert_no_gold(payload)

    legacy = json.loads(json.dumps(payload))
    legacy.pop("initial")
    legacy.pop("trace_schema_version")
    for attempt in legacy["recovery_attempts"]:
        for key in (
            "answer",
            "answer_model",
            "answer_relation",
            "evidence_relation",
            "evaluation_source",
            "executed",
            "runtime_evaluation",
            "diagnosis",
            "latency_ms",
            "retrieved_chunks",
            "probe_evaluation",
            "search_query",
            "source",
        ):
            attempt.pop(key, None)
    assert len(json.dumps(payload)) > len(json.dumps(legacy))
    assert len(json.dumps(payload)) < len(json.dumps(legacy)) * 5


def test_terminal_abstain_does_not_erase_the_expand_answer(tmp_path: Path) -> None:
    result = run_with_recovery(
        "What is the late-return fine?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        top_k=1,
        embedder=FakeEmbedder(),
        generator=_Generator("Hangar 2, bay C.", "The fine is $5 per day."),  # type: ignore[arg-type]
        rewriter=ScriptedRewriter("late return fine"),
        judge=_Judge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=False, supported=None),
            _eval(sufficient=False, supported=False),
        ),
        max_recoveries=2,
    )
    payload = _load(result)
    rewrite, expand, abstain = payload["recovery_attempts"]
    assert [item["action"] for item in payload["recovery_attempts"]] == ["rewrite", "expand", "abstain"]
    assert result.answer == ABSTAIN_ANSWER
    assert rewrite["answer_relation"] == "abstained"
    assert rewrite["answer"] == ABSTAIN_ANSWER
    assert expand["answer"] == "The fine is $5 per day."
    assert expand["answer_relation"] == "generated"
    assert abstain["answer"] == ABSTAIN_ANSWER
    assert abstain["answer_relation"] == "abstained"
    assert abstain["evidence_relation"] == "unchanged"
    assert abstain["evaluation_source"] == "carried"
    assert abstain["runtime_evaluation"]["answer_supported"] is None
    assert abstain["runtime_evaluation"]["evidence_sufficient"] is False
    assert payload["verification"]["outcome"] == "still_failing"
    assert "probe_evaluation" not in abstain
    _assert_attempt_order(payload)


def test_confirm_child_keeps_the_parent_as_initial_state(tmp_path: Path) -> None:
    parent = run_first_pass(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_Generator("On the moon."),  # type: ignore[arg-type]
        judge=_Judge(_eval(sufficient=False, supported=False)),
    )
    parent_payload = _load(parent)
    assert parent_payload["run_mode"] == "loop_confirm"
    assert parent_payload["recovery_status"] == "proposed"
    assert parent_payload["recovery"]["action"] == "rewrite"
    assert parent_payload["recovery_attempts"] is None
    assert parent_payload["initial"] is None
    assert parent_payload["diagnosis"]["failure_class"] is None

    child = apply_recovery(
        parent.run_id,
        output_dir=tmp_path,
        corpus_dir=CORPUS,
        action="regenerate",
        embedder=FakeEmbedder(),
        regenerator=_Regenerator(),
        judge=_Judge(_eval(sufficient=True, supported=True)),
    )
    child_payload = _load(child)
    assert child_payload["run_mode"] == "loop_confirm"
    assert child_payload["parent_run_id"] == parent.run_id
    assert child_payload["recovery"]["source"] == "operator"
    assert child_payload["initial"]["answer"] == "On the moon."
    assert child_payload["initial"]["diagnosis"]["failure_class"] is None
    assert child_payload["initial"]["retrieved_chunks"] == parent_payload["retrieved_chunks"]
    attempt = child_payload["recovery_attempts"][0]
    assert attempt["action"] == "regenerate"
    assert attempt["source"] == "operator"
    assert attempt["answer"] == "Saturday 10:00-16:00"
    assert attempt["answer_relation"] == "generated"
    history = logical_run_history(tmp_path)
    assert len(history["runs"]) == 1
    assert history["runs"][0]["logical_run_id"] == parent.run_id
    assert history["runs"][0]["source"] == "operator"
    _assert_attempt_order(child_payload)


def test_expand_at_the_cap_is_recorded_as_not_executed() -> None:
    chunk = Chunk(
        chunk_id="doc::c000",
        doc_id="doc",
        title="Doc",
        text="text",
        start_char=0,
        end_char=4,
    )
    retrieval = RetrievalResult(
        query="q",
        chunks=(ScoredChunk(chunk=chunk, score=0.5),),
        top_k=20,
        embedding_model="fake",
    )
    state = QueryState(
        query="q",
        retrieval=retrieval,
        generation=GenerationResult(answer="A", model="scripted"),
        runtime_evaluation=None,
        diagnosis=None,
    )
    applied = _apply_expand(
        state,
        RecoveryDecision(action=EXPAND, reason="cap", trigger="judge"),
        query="q",
        corpus_dir=CORPUS,
        top_k=20,
        embedder=None,
        generate=False,
        generator=None,
        judge=None,
        index=None,  # type: ignore[arg-type]
        search_query="q",
    )
    assert applied.executed is False
    assert applied.state.generation.answer == "A"
    assert applied.verification is None


def test_a_generation_error_after_retrieval_writes_no_trace(tmp_path: Path) -> None:
    class _Boom:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
            del query, retrieval
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("generation failed after the rewrite probe")
            return GenerationResult(answer="answer A", model="scripted")

    with pytest.raises(RuntimeError, match="generation failed"):
        run_with_recovery(
            "When is the library open?",
            corpus_dir=CORPUS,
            output_dir=tmp_path,
            embedder=FakeEmbedder(),
            generator=_Boom(),  # type: ignore[arg-type]
            rewriter=ScriptedRewriter("library saturday hours"),
            judge=_Judge(
                _eval(sufficient=False, supported=False),
                _eval(sufficient=True, supported=None),
            ),
            max_recoveries=1,
        )
    assert list(tmp_path.glob("*.json")) == []


def test_legacy_trace_is_not_given_a_first_pass_it_did_not_store() -> None:
    legacy = {
        "run_id": "old",
        "query": "q",
        "diagnosis": {"failure_class": "retrieval_miss", "rationale": "after"},
        "recovery_attempts": [{"index": 0, "action": "rewrite"}],
    }
    assert schema_version(legacy) == 1
    assert first_pass_diagnosis(legacy) is None
    proposed = {
        "run_id": "parent",
        "diagnosis": {"failure_class": "unsupported_generation"},
        "recovery_status": "proposed",
    }
    assert first_pass_diagnosis(proposed)["failure_class"] == "unsupported_generation"


def test_trace_does_not_contain_the_provider_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-should-not-leak")
    result = run_query(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generate=False,
        run_mode="retrieve_only",
    )
    encoded = result.trace_path.read_text(encoding="utf-8")
    assert "sk-test-secret-should-not-leak" not in encoded
    payload = json.loads(encoded)
    assert payload["provider"]["api_key_present"] is True
    assert "api_key" not in payload["provider"]
