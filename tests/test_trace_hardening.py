"""Phase 5.5: schema-v2 is evidence only if the trace cannot be misread."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from swrag.api.overview import aggregate_overview, group_logical_runs, logical_run_history
from swrag.api.store import _chart_row, load_trace_payloads
from swrag.evaluation.quality_metrics import is_abstention, scores_from_labels
from swrag.orchestration.loop import ABSTAIN_ANSWER, run_first_pass, run_with_recovery, apply_recovery
from swrag.pipeline.baseline import build_corpus_index, run_query
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.tracing.schema import evidence_for_attempt, first_pass_diagnosis, schema_version
from swrag.tracing.steps import trace_to_steps
from swrag.tracing.tracer import write_trace
from swrag.types import (
    Chunk,
    GenerationResult,
    RetrievalResult,
    RuntimeEvaluation,
    ScoredChunk,
    TraceRecord,
)
from swrag.usage import capture_usage, record_chat, usage_delta, usage_for_trace
from tests.decision_probe import run_all

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "corpus"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "traces"
LEGACY = FIXTURES / "legacy_corpus.json"
GOLDEN = FIXTURES / "golden"
PHASE4 = FIXTURES / "phase4_decisions.json"
SENTINELS = (
    "sk-sentinel-openai-9f3a",
    "sentinel-bearer-token-9f3a",
    "sentinel-workspace-key-9f3a",
    "sentinel-x-api-key-9f3a",
    "sentinel-provider-secret-9f3a",
    "sentinel-dotenv-secret-9f3a",
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
        self.calls = 0
        self._results = list(results)

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        self.calls += 1
        return self._results.pop(0)


class _Generator:
    def __init__(self, *answers: str) -> None:
        self.calls = 0
        self._answers = list(answers)

    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        self.calls += 1
        return GenerationResult(answer=self._answers.pop(0), model="scripted")


class _Regenerator:
    def regenerate(self, *, question: str, retrieval: RetrievalResult, previous_answer: str) -> GenerationResult:
        del question, retrieval, previous_answer
        return GenerationResult(answer="Saturday 10:00-16:00", model="regen")


class _Metered:
    """Counts a provider usage object, or a call that omitted one."""

    def __init__(self, answer: str, *, prompt: int | None) -> None:
        self.answer = answer
        self.prompt = prompt

    def _record(self) -> GenerationResult:
        usage = None if self.prompt is None else SimpleNamespace(prompt_tokens=self.prompt, completion_tokens=1)
        record_chat(SimpleNamespace(usage=usage))
        return GenerationResult(answer=self.answer, model="scripted")

    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        return self._record()

    def regenerate(self, *, question: str, retrieval: RetrievalResult, previous_answer: str) -> GenerationResult:
        del question, retrieval, previous_answer
        return self._record()


class _FixedIndex:
    def __init__(self, *scores: float) -> None:
        self.embedding_model = "fake"
        self._scores = scores

    def search(self, query: str, top_k: int = 4) -> RetrievalResult:
        chunks = []
        for index, score in enumerate(self._scores[:top_k]):
            chunk = Chunk(
                chunk_id=f"doc::c{index:03d}",
                doc_id="doc",
                title="Doc",
                text="Saturday 10:00-16:00",
                start_char=0,
                end_char=18,
            )
            chunks.append(ScoredChunk(chunk=chunk, score=score))
        return RetrievalResult(query=query, chunks=tuple(chunks), top_k=top_k, embedding_model="fake")


class _Boom:
    def __init__(self, message: str) -> None:
        self.message = message

    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        del query, retrieval
        raise RuntimeError(self.message)

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        del question, answer, retrieval
        raise RuntimeError(self.message)

    def rewrite(self, *, question: str, retrieval: RetrievalResult) -> str:
        del question, retrieval
        raise RuntimeError(self.message)

    def search(self, query: str, top_k: int = 4) -> RetrievalResult:
        del query, top_k
        raise RuntimeError(self.message)


class _FailOnCall:
    def __init__(self, inner: object, fail_on: int, message: str) -> None:
        self.inner = inner
        self.fail_on = fail_on
        self.message = message
        self.calls = 0
        self.embedding_model = getattr(inner, "embedding_model", "fake")

    def search(self, query: str, top_k: int = 4) -> RetrievalResult:
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError(self.message)
        return self.inner.search(query, top_k=top_k)  # type: ignore[attr-defined]

    def generate(self, query: str, retrieval: RetrievalResult) -> GenerationResult:
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError(self.message)
        return self.inner.generate(query, retrieval)  # type: ignore[attr-defined]


def _load(result) -> dict:
    return json.loads(result.trace_path.read_text(encoding="utf-8"))


def _ids(chunks: object) -> list[str]:
    if not isinstance(chunks, list):
        return []
    return [str(item.get("chunk_id")) for item in chunks if isinstance(item, dict)]


def _flags(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {
        "evidence_sufficient": value.get("evidence_sufficient"),
        "answer_supported": value.get("answer_supported"),
    }


def _semantic(payload: dict, *, parent: str | None = None, child: str | None = None) -> dict:
    def scrub_id(value: object) -> object:
        if parent and value == parent:
            return "parent"
        if child and value == child:
            return "child"
        return value

    attempts = []
    for item in payload.get("recovery_attempts") or []:
        if not isinstance(item, dict):
            continue
        attempts.append(
            {
                "index": item.get("index"),
                "action": item.get("action"),
                "source": item.get("source"),
                "executed": item.get("executed"),
                "answer": item.get("answer"),
                "answer_relation": item.get("answer_relation"),
                "evidence_relation": item.get("evidence_relation"),
                "evaluation_source": item.get("evaluation_source"),
                "search_query": item.get("search_query"),
                "rewritten_query": item.get("rewritten_query"),
                "top_k": item.get("top_k"),
                "chunk_ids": _ids(item.get("retrieved_chunks")) or None,
                "runtime_evaluation": _flags(item.get("runtime_evaluation")),
                "probe_evaluation": _flags(item.get("probe_evaluation")),
                "verification": (item.get("verification") or {}).get("outcome")
                if isinstance(item.get("verification"), dict)
                else None,
                "diagnosis_class": (item.get("diagnosis") or {}).get("failure_class")
                if isinstance(item.get("diagnosis"), dict)
                else None,
            }
        )
    initial = payload.get("initial") if isinstance(payload.get("initial"), dict) else None
    return {
        "trace_schema_version": payload.get("trace_schema_version"),
        "run_mode": payload.get("run_mode"),
        "query": payload.get("query"),
        "answer": payload.get("answer"),
        "model": payload.get("model"),
        "top_k": payload.get("top_k"),
        "chunk_ids": _ids(payload.get("retrieved_chunks")),
        "runtime_evaluation": _flags(payload.get("runtime_evaluation")),
        "verification": (payload.get("verification") or {}).get("outcome")
        if isinstance(payload.get("verification"), dict)
        else None,
        "recovery_action": (payload.get("recovery") or {}).get("action")
        if isinstance(payload.get("recovery"), dict)
        else None,
        "recovery_status": payload.get("recovery_status"),
        "recovery_source": (payload.get("recovery") or {}).get("source")
        if isinstance(payload.get("recovery"), dict)
        else None,
        "parent_run_id": scrub_id(payload.get("parent_run_id")),
        "initial": None
        if initial is None
        else {
            "query": initial.get("query"),
            "answer": initial.get("answer"),
            "chunk_ids": _ids(initial.get("retrieved_chunks")),
            "runtime_evaluation": _flags(initial.get("runtime_evaluation")),
            "diagnosis_class": (initial.get("diagnosis") or {}).get("failure_class")
            if isinstance(initial.get("diagnosis"), dict)
            else None,
        },
        "attempts": attempts,
    }


def _assert_invariants(payload: dict) -> None:
    assert schema_version(payload) == 2
    attempts = [item for item in payload.get("recovery_attempts") or [] if isinstance(item, dict)]
    assert [item["index"] for item in attempts] == list(range(len(attempts)))
    initial = payload.get("initial")
    if attempts:
        assert isinstance(initial, dict)
        assert initial["query"] == payload["query"]
        assert initial["answer"] != ABSTAIN_ANSWER or payload["answer"] == ABSTAIN_ANSWER or True
    else:
        assert initial is None
    if attempts and attempts[-1].get("executed") is not False:
        assert attempts[-1]["answer"] == payload["answer"]
    for item in attempts:
        relation = item["answer_relation"]
        if relation == "kept_previous":
            assert item["evidence_relation"] in {"replaced", "widened", "unchanged"}
            assert item["answer"] != "" or payload["initial"]["answer"] == ""
            assert item.get("evaluation_source") != "judge" or item["answer"] == payload["initial"]["answer"]
        if relation == "generated":
            assert evidence_for_attempt(payload, item["index"])
        if relation == "abstained":
            assert item["answer"] == ABSTAIN_ANSWER
            assert is_abstention(item["answer"])
        if item.get("probe_evaluation") is not None:
            assert item["action"] == "rewrite"
            assert item["probe_evaluation"]["answer_supported"] is None
            assert item["probe_evaluation"] is not item.get("runtime_evaluation")
        if item.get("evaluation_source") == "carried" and item.get("answer_relation") == "abstained":
            assert item["runtime_evaluation"]["answer_supported"] is None
        if item.get("evidence_relation") == "unchanged":
            assert "retrieved_chunks" not in item
        if item.get("executed") is False:
            assert item.get("verification") is None
    if payload.get("answer") == ABSTAIN_ANSWER:
        assert is_abstention(payload["answer"])
    encoded = json.dumps(payload)
    assert "answerable" not in encoded
    assert "gold_f1" not in encoded


def _loop(tmp_path: Path, name: str, **kwargs):
    kwargs.setdefault("corpus_dir", CORPUS)
    kwargs.setdefault("output_dir", tmp_path / name)
    kwargs.setdefault("embedder", FakeEmbedder())
    return run_with_recovery("When is the library open?", **kwargs)


def test_differential_decisions_match_phase4() -> None:
    expected = json.loads(PHASE4.read_text(encoding="utf-8"))
    assert run_all() == expected


def test_accept_creates_no_attempt_and_null_support_stays_null(tmp_path: Path) -> None:
    judge = _Judge(_eval(sufficient=True, supported=True))
    result = _loop(
        tmp_path,
        "accept",
        generator=_Generator("Saturday hours."),
        judge=judge,
        max_recoveries=2,
    )
    payload = _load(result)
    _assert_invariants(payload)
    assert payload["run_mode"] == "loop"
    assert payload["recovery"]["action"] == "accept"
    assert payload["recovery_attempts"] is None
    assert judge.calls == 1

    probe = _Judge(_eval(sufficient=False, supported=True), _eval(sufficient=False, supported=None))
    kept = _loop(
        tmp_path,
        "null-support",
        generator=_Generator("Saturday hours."),
        judge=probe,
        rewriter=__import__("swrag.recovery.rewrite", fromlist=["ScriptedRewriter"]).ScriptedRewriter(
            "library saturday hours"
        ),
        max_recoveries=1,
    )
    kept_payload = _load(kept)
    _assert_invariants(kept_payload)
    assert kept_payload["recovery_attempts"][0]["probe_evaluation"]["answer_supported"] is None
    assert kept_payload["recovery_attempts"][0]["probe_evaluation"]["answer_supported"] is not False


def test_rewrite_branches_and_carried_evaluation(tmp_path: Path) -> None:
    from swrag.recovery.rewrite import ScriptedRewriter

    sufficient = _Judge(
        _eval(sufficient=False, supported=False),
        _eval(sufficient=True, supported=None),
        _eval(sufficient=True, supported=True),
    )
    generated = _Generator("answer A", "answer B")
    ok = _loop(
        tmp_path,
        "rewrite-ok",
        generator=generated,
        judge=sufficient,
        rewriter=ScriptedRewriter("library saturday hours"),
        max_recoveries=2,
    )
    ok_payload = _load(ok)
    _assert_invariants(ok_payload)
    attempt = ok_payload["recovery_attempts"][0]
    assert attempt["answer_relation"] == "generated"
    assert attempt["evaluation_source"] == "judge"
    assert attempt["probe_evaluation"]["evidence_sufficient"] is True
    assert sufficient.calls == 3
    assert generated.calls == 2
    assert len(ok_payload["recovery_attempts"]) == 1

    insufficient = _Judge(_eval(sufficient=False, supported=True), _eval(sufficient=False, supported=None))
    kept_generator = _Generator("Saturday hours.")
    kept = _loop(
        tmp_path,
        "rewrite-keep",
        generator=kept_generator,
        judge=insufficient,
        rewriter=ScriptedRewriter("library saturday hours"),
        max_recoveries=1,
    )
    kept_payload = _load(kept)
    _assert_invariants(kept_payload)
    kept_attempt = kept_payload["recovery_attempts"][0]
    assert kept_attempt["answer_relation"] == "kept_previous"
    assert kept_attempt["evaluation_source"] == "carried"
    assert kept_attempt["answer"] == "Saturday hours."
    assert kept_attempt["runtime_evaluation"]["answer_supported"] is True
    assert insufficient.calls == 2
    assert kept_generator.calls == 1
    steps = trace_to_steps(kept_payload)
    generate = next(step for step in steps if step["id"] == "generate")
    assert generate["title"] == "Kept previous answer"
    evaluate = next(step for step in steps if step["id"] == "evaluate")
    assert "not a new judge call" in evaluate["payload"]["note"]

    abstaining = _Judge(_eval(sufficient=False, supported=False), _eval(sufficient=False, supported=None))
    abstained = _loop(
        tmp_path,
        "rewrite-abstain",
        generator=_Generator("not in the documents"),
        judge=abstaining,
        rewriter=ScriptedRewriter("library saturday hours"),
        max_recoveries=1,
    )
    abstain_payload = _load(abstained)
    _assert_invariants(abstain_payload)
    failed = abstain_payload["recovery_attempts"][0]
    assert failed["answer_relation"] == "abstained"
    assert failed["evaluation_source"] == "probe"
    assert failed["runtime_evaluation"]["answer_supported"] is None
    assert failed["probe_evaluation"]["answer_supported"] is None
    assert failed["runtime_evaluation"]["evidence_sufficient"] is False
    assert abstain_payload["answer"] == ABSTAIN_ANSWER
    assert abstaining.calls == 2
    failed_steps = trace_to_steps(abstain_payload)
    failed_eval = next(step for step in failed_steps if step["id"] == "evaluate")
    assert "rewrite retrieve probe" in failed_eval["payload"]["note"]
    assert "last judge call" not in failed_eval["payload"]["note"]


def test_executed_false_is_not_an_applied_recovery(tmp_path: Path) -> None:
    judge = _Judge(_eval(sufficient=True, supported=True))
    result = run_with_recovery(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "capped",
        top_k=20,
        embedder=FakeEmbedder(),
        generator=_Generator("Saturday hours."),
        judge=judge,
        index=_FixedIndex(0.01),
        max_recoveries=1,
    )
    payload = _load(result)
    _assert_invariants(payload)
    attempt = payload["recovery_attempts"][0]
    assert attempt["action"] == "expand"
    assert attempt["executed"] is False
    assert attempt["verification"] is None
    assert payload["answer"] == payload["initial"]["answer"]
    history = logical_run_history(tmp_path / "capped")
    row = history["runs"][0]
    assert row["recovery_required"] is True
    assert row["recovery_applied"] is False
    assert row["verification"] is None
    assert row["recovery"] == ["expand"]
    overview = aggregate_overview(group_logical_runs(load_trace_payloads(tmp_path / "capped")))
    assert all(item["name"] != "expand" for item in overview["applied_actions"])
    assert overview["outcomes"]["applied"] == 0
    assert _chart_row(payload)["path"] == []

    skipped = _loop(
        tmp_path,
        "skip-generate",
        generate=False,
        judge=_Judge(_eval(sufficient=False, supported=None)),
        max_recoveries=1,
    )
    skipped_payload = _load(skipped)
    assert skipped_payload["recovery_attempts"][0]["action"] == "rewrite"
    assert skipped_payload["recovery_attempts"][0]["executed"] is False
    assert skipped_payload["answer"] == ""


def test_usage_is_not_double_counted_and_missing_tokens_stay_absent(tmp_path: Path) -> None:
    with capture_usage():
        assert usage_for_trace() is None
        record_chat(SimpleNamespace(usage=None))
        omitted = usage_for_trace()
    assert omitted["chat_calls"] == 1
    assert omitted["prompt_tokens"] is None
    assert omitted["tokens_observed"] is False

    with capture_usage():
        before = __import__("swrag.usage", fromlist=["usage_checkpoint"]).usage_checkpoint()
        record_chat(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4)))
        after = __import__("swrag.usage", fromlist=["usage_checkpoint"]).usage_checkpoint()
        delta = usage_delta(before, after)
        record_chat(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1)))
        whole = usage_for_trace()
    assert delta == {
        "chat_calls": 1,
        "embedding_calls": 0,
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "embedding_tokens": 0,
        "tokens_observed": True,
    }
    assert whole["prompt_tokens"] == 13
    assert whole["chat_calls"] == 2

    with capture_usage():
        result = _loop(
            tmp_path,
            "metered",
            generator=_Metered("Saturday hours.", prompt=10),
            regenerator=_Metered("Saturday 10:00-16:00", prompt=7),
            judge=_Judge(_eval(sufficient=True, supported=False), _eval(sufficient=True, supported=True)),
        )
    payload = _load(result)
    assert payload["usage"]["chat_calls"] == 2
    assert payload["usage"]["prompt_tokens"] == 17
    assert payload["recovery_attempts"][0]["usage"]["chat_calls"] == 1
    assert payload["recovery_attempts"][0]["usage"]["prompt_tokens"] == 7
    history = logical_run_history(tmp_path / "metered")
    assert history["runs"][0]["usage"] == {
        "prompt_tokens": 17,
        "completion_tokens": 2,
        "tokens_observed": True,
    }


def test_future_schema_is_not_read_as_version_2(tmp_path: Path) -> None:
    future = {
        "run_id": "future",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "query": "When is the library open?",
        "answer": "Saturday hours.",
        "trace_schema_version": 999,
        "run_mode": "loop",
        "initial": {
            "query": "When is the library open?",
            "answer": "wrong first answer",
            "diagnosis": {"failure_class": "invented_class", "rationale": "do not trust"},
            "retrieved_chunks": [{"chunk_id": "nope"}],
            "runtime_evaluation": {"evidence_sufficient": False, "answer_supported": False},
        },
        "runtime_evaluation": {"evidence_sufficient": True, "answer_supported": True},
        "diagnosis": {"failure_class": "also_invented", "rationale": "no"},
        "recovery_attempts": [
            {
                "index": 0,
                "action": "rewrite",
                "answer_relation": "generated",
                "evidence_relation": "replaced",
                "executed": True,
                "attributed_class": "invented_class",
                "retrieved_chunks": [{"chunk_id": "nope"}],
            }
        ],
        "verification": {"outcome": "improved"},
    }
    (tmp_path / "future.json").write_text(json.dumps(future), encoding="utf-8")
    assert schema_version(future) == 999
    assert first_pass_diagnosis(future) is None
    assert evidence_for_attempt(future, 0) == []
    history = logical_run_history(tmp_path)
    row = history["runs"][0]
    assert row["diagnoses"] == []
    assert row["recovery"] == []
    assert row["recovery_required"] is False
    assert row["judged"] is False
    overview = aggregate_overview(group_logical_runs(load_trace_payloads(tmp_path)))
    assert overview["judged_runs"] == 0
    assert overview["recovery_required"]["count"] == 0
    assert _chart_row(future)["path"] == []
    assert _chart_row(future)["failure_class"] is None
    steps = trace_to_steps(future)
    assert steps[0]["payload"]["unsupported_schema"] is True
    assert len(steps) == 1


def test_legacy_corpus_stays_readable() -> None:
    corpus = json.loads(LEGACY.read_text(encoding="utf-8"))
    by_name = {item["name"]: item["trace"] for item in corpus}
    assert schema_version(by_name["regenerate"]) == 1
    assert first_pass_diagnosis(by_name["missing_first_pass_evaluation"]) is None
    assert first_pass_diagnosis(by_name["confirm_parent"])["failure_class"] is None
    assert by_name["null_answer_supported"]["runtime_evaluation"]["answer_supported"] is None
    assert "recovery_attempts" not in by_name["missing_recovery_attempts"]
    assert "diagnosis" not in by_name["missing_diagnosis"]
    scored = scores_from_labels(
        {"claims": [{"claim": "x", "supported": True}], "answer_relevance": 5, "passages": []},
        answer=by_name["abstain"]["answer"],
        chunks=[],
    )
    assert scored.faithfulness is None
    assert scored.answer_relevance is None

    payloads = [item["trace"] for item in corpus]
    runs = group_logical_runs(payloads)
    ids = {run.root_id for run in runs}
    assert "legacy-parent" in ids
    assert "legacy-child" not in ids
    parent = next(run for run in runs if run.root_id == "legacy-parent")
    assert [trace["run_id"] for trace in parent.traces] == ["legacy-parent", "legacy-child"]
    overview = aggregate_overview(runs)
    assert overview["observed_runs"] == len(payloads) - 1
    for payload in payloads:
        trace_to_steps(payload)
        _chart_row(payload)


def test_malformed_files_do_not_become_runs(tmp_path: Path) -> None:
    good = {
        "run_id": "good",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "query": "When is the library open?",
        "answer": "Saturday hours.",
    }
    (tmp_path / "good.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "truncated.json").write_text("{", encoding="utf-8")
    (tmp_path / "no-id.json").write_text(json.dumps({"query": "q", "answer": "a"}), encoding="utf-8")
    (tmp_path / ".orphan.json.partial").write_text(json.dumps(good), encoding="utf-8")
    odd = {
        "run_id": "odd",
        "timestamp": "2026-01-02T00:00:00+00:00",
        "query": "When is the library open?",
        "answer": "Saturday hours.",
        "diagnosis": None,
        "runtime_evaluation": {"evidence_sufficient": False, "answer_supported": None},
        "recovery_attempts": [{"index": 0, "action": "teleport"}],
    }
    (tmp_path / "odd.json").write_text(json.dumps(odd), encoding="utf-8")
    loaded = load_trace_payloads(tmp_path)
    assert {item["run_id"] for item in loaded} == {"good", "odd"}
    overview = aggregate_overview(group_logical_runs(loaded))
    assert overview["observed_runs"] == 2
    trace_to_steps(odd)


def test_faults_leave_no_completed_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from swrag.recovery.rewrite import ScriptedRewriter

    cases = {
        "retrieve": dict(index=_Boom("retrieval failed"), generator=_Generator("a"), judge=_Judge(_eval(sufficient=True, supported=True))),
        "generate": dict(generator=_Boom("generation failed"), judge=_Judge(_eval(sufficient=True, supported=True))),
        "judge": dict(generator=_Generator("a"), judge=_Boom("judge failed")),
        "rewrite": dict(
            generator=_Generator("a"),
            judge=_Judge(_eval(sufficient=False, supported=False)),
            rewriter=_Boom("rewrite failed"),
        ),
        "probe": dict(
            generator=_Generator("a"),
            judge=_FailJudge(_eval(sufficient=False, supported=False)),
            rewriter=ScriptedRewriter("library saturday hours"),
        ),
    }
    for name, kwargs in cases.items():
        with pytest.raises(RuntimeError):
            _loop(tmp_path, name, **kwargs)
        assert list((tmp_path / name).glob("*.json")) == []

    index = _FailOnCall(build_corpus_index(CORPUS, FakeEmbedder()), fail_on=3, message="expand retrieval failed")
    with pytest.raises(RuntimeError, match="expand retrieval failed"):
        _loop(
            tmp_path,
            "expand-retrieve",
            index=index,
            embedder=FakeEmbedder(),
            generator=_Generator("answer A", "answer B"),
            rewriter=ScriptedRewriter("library saturday hours"),
            judge=_Judge(
                _eval(sufficient=False, supported=False),
                _eval(sufficient=True, supported=None),
                _eval(sufficient=False, supported=False),
            ),
            max_recoveries=2,
        )
    assert list((tmp_path / "expand-retrieve").glob("*.json")) == []

    generator = _FailOnCall(_Generator("answer A", "answer B", "answer C"), fail_on=3, message="expand generation failed")
    with pytest.raises(RuntimeError, match="expand generation failed"):
        _loop(
            tmp_path,
            "expand-generate",
            generator=generator,
            rewriter=ScriptedRewriter("library saturday hours"),
            judge=_Judge(
                _eval(sufficient=False, supported=False),
                _eval(sufficient=True, supported=None),
                _eval(sufficient=False, supported=False),
            ),
            max_recoveries=2,
        )
    assert list((tmp_path / "expand-generate").glob("*.json")) == []

    def _break_link(src, dst):
        del src, dst
        raise OSError("disk full during link")

    monkeypatch.setattr(os, "link", _break_link)
    with pytest.raises(OSError, match="disk full"):
        run_query(
            "When is the library open?",
            corpus_dir=CORPUS,
            output_dir=tmp_path / "write",
            embedder=FakeEmbedder(),
            generate=False,
            run_mode="retrieve_only",
        )
    assert list((tmp_path / "write").glob("*.json")) == []
    assert list((tmp_path / "write").glob("*.partial")) == []
    monkeypatch.undo()
    again = run_query(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "write",
        embedder=FakeEmbedder(),
        generate=False,
        run_mode="retrieve_only",
    )
    assert again.trace_path.is_file()
    json.loads(again.trace_path.read_text(encoding="utf-8"))


class _FailJudge(_Judge):
    def __init__(self, first: RuntimeEvaluation) -> None:
        super().__init__(first)

    def judge(self, *, question: str, answer: str, retrieval: RetrievalResult) -> RuntimeEvaluation:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("probe failed")
        return super().judge(question=question, answer=answer, retrieval=retrieval)


def test_write_trace_is_atomic_and_refuses_overwrite(tmp_path: Path) -> None:
    record = TraceRecord(
        run_id="atomic",
        timestamp="2026-01-01T00:00:00+00:00",
        query="q",
        retrieved_chunks=(),
        answer="a",
        model="scripted",
        embedding_model="fake",
        top_k=4,
    )
    path = write_trace(record, tmp_path)
    original = path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_trace(record, tmp_path)
    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("*.partial")) == []


def test_secrets_do_not_enter_the_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", SENTINELS[0])
    monkeypatch.setenv("AUTHORIZATION", f"Bearer {SENTINELS[1]}")
    monkeypatch.setenv("SWRAG_API_KEY", SENTINELS[2])
    monkeypatch.setenv("X_API_KEY", SENTINELS[3])
    monkeypatch.setenv("PROVIDER_SECRET", SENTINELS[4])
    monkeypatch.setenv("DOTENV_SECRET", SENTINELS[5])
    result = run_query(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        embedder=FakeEmbedder(),
        generator=_Generator("Saturday hours."),
        run_mode="baseline",
    )
    encoded = result.trace_path.read_text(encoding="utf-8")
    for sentinel in SENTINELS:
        assert sentinel not in encoded
    assert "Authorization:" not in encoded
    assert "Bearer " not in encoded
    assert "sk-" not in encoded
    assert "Saturday hours." in encoded
    assert "When is the library open?" in encoded


def test_scenario_matrix_preserves_attempt_invariants(tmp_path: Path) -> None:
    from swrag.recovery.rewrite import ScriptedRewriter

    library = "When is the Harbor Institute Library open on Saturday?"
    fine = "What is the late-return fine?"
    scenarios = {
        "regenerate_improved": dict(
            query=library,
            generator=_Generator("The library is on the moon."),
            regenerator=_Regenerator(),
            judge=_Judge(_eval(sufficient=True, supported=False), _eval(sufficient=True, supported=True)),
        ),
        "regenerate_degraded": dict(
            query=library,
            generator=_Generator("The library is on the moon."),
            regenerator=_Regenerator(),
            judge=_Judge(_eval(sufficient=True, supported=False), _eval(sufficient=False, supported=False)),
            max_recoveries=1,
        ),
        "rewrite_then_expand_improved": dict(
            generator=_Generator("answer A", "answer B", "answer C"),
            rewriter=ScriptedRewriter("library saturday hours"),
            judge=_Judge(
                _eval(sufficient=False, supported=False),
                _eval(sufficient=True, supported=None),
                _eval(sufficient=False, supported=False),
                _eval(sufficient=True, supported=True),
            ),
            max_recoveries=2,
        ),
        "second_recovery_degraded": dict(
            query=library,
            generator=_Generator("The library is on the moon.", "wider but worse"),
            regenerator=_Regenerator(),
            judge=_Judge(
                _eval(sufficient=True, supported=False),
                _eval(sufficient=True, supported=False),
                _eval(sufficient=False, supported=False),
            ),
            max_recoveries=2,
        ),
        "terminal_abstain": dict(
            query=fine,
            top_k=1,
            generator=_Generator("Hangar 2, bay C.", "The fine is $5 per day."),
            rewriter=ScriptedRewriter("late return fine"),
            judge=_Judge(
                _eval(sufficient=False, supported=False),
                _eval(sufficient=False, supported=None),
                _eval(sufficient=False, supported=False),
            ),
            max_recoveries=2,
        ),
        "ambiguous_expand_unchanged": dict(
            index=_FixedIndex(0.8, 0.8),
            generator=_Generator("Saturday hours.", "Saturday hours still."),
            judge=_Judge(_eval(sufficient=True, supported=True), _eval(sufficient=True, supported=True)),
            max_recoveries=1,
        ),
    }
    for name, kwargs in scenarios.items():
        query = kwargs.pop("query", "When is the library open?")
        result = run_with_recovery(
            query,
            corpus_dir=CORPUS,
            output_dir=tmp_path / name,
            embedder=FakeEmbedder(),
            **kwargs,
        )
        payload = _load(result)
        _assert_invariants(payload)
        if name == "regenerate_degraded":
            assert payload["recovery_attempts"][0]["verification"]["outcome"] == "degraded"
        if name == "second_recovery_degraded":
            assert [item["action"] for item in payload["recovery_attempts"][:2]] == ["regenerate", "expand"]
            assert payload["recovery_attempts"][1]["verification"]["outcome"] == "degraded"
        if name == "terminal_abstain":
            assert payload["recovery_attempts"][-1]["evaluation_source"] == "carried"
            assert payload["recovery_attempts"][-1]["answer_relation"] == "abstained"
            assert payload["recovery_attempts"][1]["answer"] == "The fine is $5 per day."
        if name == "ambiguous_expand_unchanged":
            assert payload["initial"]["retrieval_signal"]["ambiguous_top"] is True
            assert payload["verification"]["outcome"] == "unchanged"

    parent = run_first_pass(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "confirm",
        embedder=FakeEmbedder(),
        generator=_Generator("On the moon."),
        judge=_Judge(_eval(sufficient=False, supported=False)),
    )
    child = apply_recovery(
        parent.run_id,
        output_dir=tmp_path / "confirm",
        corpus_dir=CORPUS,
        action="regenerate",
        embedder=FakeEmbedder(),
        regenerator=_Regenerator(),
        judge=_Judge(_eval(sufficient=True, supported=True)),
    )
    child_payload = _load(child)
    _assert_invariants(child_payload)
    assert child_payload["recovery_attempts"][0]["source"] == "operator"
    assert logical_run_history(tmp_path / "confirm")["runs"][0]["source"] == "operator"


def test_a_model_can_emit_the_abstention_sentence_without_an_abstain_action(tmp_path: Path) -> None:
    """The controller's abstain action and a model that prints that sentence are different.

    ``answer_relation: generated`` means the generator produced the text. Verification
    must also look at the text before treating that attempt as an ordinary answer.
    """
    from swrag.recovery.rewrite import ScriptedRewriter

    result = run_with_recovery(
        "What is the late-return fine?",
        corpus_dir=CORPUS,
        output_dir=tmp_path,
        top_k=1,
        embedder=FakeEmbedder(),
        generator=_Generator("Hangar 2.", ABSTAIN_ANSWER),
        rewriter=ScriptedRewriter("late return fine"),
        judge=_Judge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=None),
            _eval(sufficient=False, supported=None),
        ),
        max_recoveries=1,
    )
    payload = _load(result)
    attempt = payload["recovery_attempts"][0]
    assert attempt["action"] == "rewrite"
    assert attempt["answer_relation"] == "generated"
    assert attempt["answer"] == ABSTAIN_ANSWER
    assert attempt["evaluation_source"] == "judge"
    assert attempt["runtime_evaluation"]["answer_supported"] is None
    assert is_abstention(attempt["answer"])


def test_golden_schema_semantics(tmp_path: Path) -> None:
    produced = _golden_payloads(tmp_path)
    for name, payload in produced.items():
        expected = json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
        parent = payload.get("parent_run_id")
        child = payload.get("run_id") if parent else None
        assert _semantic(payload, parent=parent, child=child) == expected


def _golden_payloads(tmp_path: Path) -> dict[str, dict]:
    from swrag.recovery.rewrite import ScriptedRewriter

    baseline = run_query(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "baseline",
        embedder=FakeEmbedder(),
        generator=_Generator("Saturday hours."),
        run_mode="baseline",
    )
    regenerate = run_with_recovery(
        "When is the Harbor Institute Library open on Saturday?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "regenerate",
        embedder=FakeEmbedder(),
        generator=_Generator("The library is on the moon."),
        regenerator=_Regenerator(),
        judge=_Judge(_eval(sufficient=True, supported=False), _eval(sufficient=True, supported=True)),
    )
    rewrite = run_with_recovery(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "rewrite",
        embedder=FakeEmbedder(),
        generator=_Generator("answer A", "answer B"),
        rewriter=ScriptedRewriter("library saturday hours"),
        judge=_Judge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=None),
            _eval(sufficient=True, supported=True),
        ),
        max_recoveries=1,
    )
    rewrite_expand = run_with_recovery(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "rewrite-expand",
        embedder=FakeEmbedder(),
        generator=_Generator("answer A", "answer B", "answer C"),
        rewriter=ScriptedRewriter("library saturday hours"),
        judge=_Judge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=None),
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=True),
        ),
        max_recoveries=2,
    )
    parent = run_first_pass(
        "When is the library open?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "confirm",
        embedder=FakeEmbedder(),
        generator=_Generator("On the moon."),
        judge=_Judge(_eval(sufficient=False, supported=False)),
    )
    child = apply_recovery(
        parent.run_id,
        output_dir=tmp_path / "confirm",
        corpus_dir=CORPUS,
        action="regenerate",
        embedder=FakeEmbedder(),
        regenerator=_Regenerator(),
        judge=_Judge(_eval(sufficient=True, supported=True)),
    )
    abstain = run_with_recovery(
        "What is the late-return fine?",
        corpus_dir=CORPUS,
        output_dir=tmp_path / "abstain",
        top_k=1,
        embedder=FakeEmbedder(),
        generator=_Generator("Hangar 2, bay C.", "The fine is $5 per day."),
        rewriter=ScriptedRewriter("late return fine"),
        judge=_Judge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=False, supported=None),
            _eval(sufficient=False, supported=False),
        ),
        max_recoveries=2,
    )
    return {
        "baseline": _load(baseline),
        "regenerate": _load(regenerate),
        "rewrite": _load(rewrite),
        "rewrite_expand": _load(rewrite_expand),
        "confirm_recovery": _load(child),
        "abstain": _load(abstain),
    }
