"""Scripted decision vectors for the pre-schema loop and the current loop.

The compared fields are runtime decisions. Schema metadata is not included.
Both trees expose the same ``run_query`` / ``run_with_recovery`` arguments
used here. ``run_mode`` is intentionally not passed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from swrag.orchestration.loop import run_with_recovery
from swrag.pipeline.baseline import run_query
from swrag.recovery.rewrite import ScriptedRewriter
from swrag.retrieval.fake_embedder import FakeEmbedder
from swrag.types import GenerationResult, RetrievalResult, RuntimeEvaluation

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "corpus"


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
    def __init__(self) -> None:
        self.calls = 0

    def regenerate(self, *, question: str, retrieval: RetrievalResult, previous_answer: str) -> GenerationResult:
        del question, retrieval, previous_answer
        self.calls += 1
        return GenerationResult(answer="Saturday 10:00-16:00", model="regen")


class _Rewriter:
    def __init__(self, text: str) -> None:
        self.calls = 0
        self._inner = ScriptedRewriter(text)

    def rewrite(self, *, question: str, retrieval: RetrievalResult) -> str:
        self.calls += 1
        return self._inner.rewrite(question=question, retrieval=retrieval)


def _vector(name: str, result, judge: _Judge | None, generator: _Generator | None, rewriter: _Rewriter | None, regenerator: _Regenerator | None) -> dict:
    evaluation = result.runtime_evaluation
    diagnosis = result.diagnosis
    recovery = result.recovery
    verification = result.verification
    payload = {}
    if result.trace_path is not None:
        import json

        payload = json.loads(Path(result.trace_path).read_text(encoding="utf-8"))
    attempts = payload.get("recovery_attempts") or []
    probe = payload.get("probe_evaluation") if isinstance(payload.get("probe_evaluation"), dict) else None
    first = payload.get("first_pass_evaluation") if isinstance(payload.get("first_pass_evaluation"), dict) else None
    signal = payload.get("retrieval_signal") if isinstance(payload.get("retrieval_signal"), dict) else None
    return {
        "name": name,
        "doc_ids": [item.chunk.doc_id for item in result.retrieval.chunks],
        "answer": result.answer,
        "model": result.generation_model,
        "previous_answer": result.previous_answer,
        "rewritten_query": result.rewritten_query,
        "action": None if recovery is None else recovery.action,
        "attempt_actions": [item.get("action") for item in attempts if isinstance(item, dict)],
        "evaluation": None
        if evaluation is None
        else {
            "evidence_sufficient": evaluation.evidence_sufficient,
            "answer_supported": evaluation.answer_supported,
        },
        "first_pass_evaluation": None
        if first is None
        else {
            "evidence_sufficient": first.get("evidence_sufficient"),
            "answer_supported": first.get("answer_supported"),
        },
        "diagnosis": None if diagnosis is None else diagnosis.failure_class,
        "verification": None if verification is None else verification.outcome,
        "probe_sufficient": None if probe is None else probe.get("evidence_sufficient"),
        "probe_supported": None if probe is None else probe.get("answer_supported"),
        "weak_top": None if signal is None else signal.get("weak_top"),
        "ambiguous_top": None if signal is None else signal.get("ambiguous_top"),
        "final_doc_ids": [
            item.get("doc_id")
            for item in payload.get("retrieved_chunks") or []
            if isinstance(item, dict)
        ],
        "judge_calls": 0 if judge is None else judge.calls,
        "generate_calls": 0 if generator is None else generator.calls,
        "rewrite_calls": 0 if rewriter is None else rewriter.calls,
        "regenerate_calls": 0 if regenerator is None else regenerator.calls,
    }


def run_all() -> list[dict]:
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        generator = _Generator("Saturday hours.")
        result = run_query(
            "When is the library open?",
            corpus_dir=CORPUS,
            output_dir=output / "retrieve",
            embedder=FakeEmbedder(),
            generate=False,
        )
        rows.append(_vector("retrieve_only", result, None, None, None, None))

        generator = _Generator("Saturday hours.")
        result = run_query(
            "When is the library open?",
            corpus_dir=CORPUS,
            output_dir=output / "baseline",
            embedder=FakeEmbedder(),
            generator=generator,  # type: ignore[arg-type]
        )
        rows.append(_vector("baseline", result, None, generator, None, None))

        judge = _Judge(_eval(sufficient=True, supported=True))
        generator = _Generator("Saturday hours.")
        result = run_with_recovery(
            "When is the library open?",
            corpus_dir=CORPUS,
            output_dir=output / "accept",
            embedder=FakeEmbedder(),
            generator=generator,  # type: ignore[arg-type]
            judge=judge,
            max_recoveries=2,
        )
        rows.append(_vector("accept", result, judge, generator, None, None))

        judge = _Judge(_eval(sufficient=True, supported=False), _eval(sufficient=True, supported=True))
        generator = _Generator("The library is on the moon.")
        regenerator = _Regenerator()
        result = run_with_recovery(
            "When is the Harbor Institute Library open on Saturday?",
            corpus_dir=CORPUS,
            output_dir=output / "regenerate",
            embedder=FakeEmbedder(),
            generator=generator,  # type: ignore[arg-type]
            regenerator=regenerator,
            judge=judge,
        )
        rows.append(_vector("regenerate", result, judge, generator, None, regenerator))

        judge = _Judge(_eval(sufficient=False, supported=False), _eval(sufficient=True, supported=None), _eval(sufficient=True, supported=True))
        generator = _Generator("answer A", "answer B")
        rewriter = _Rewriter("library saturday hours")
        result = run_with_recovery(
            "When is the library open?",
            corpus_dir=CORPUS,
            output_dir=output / "rewrite_ok",
            embedder=FakeEmbedder(),
            generator=generator,  # type: ignore[arg-type]
            rewriter=rewriter,
            judge=judge,
            max_recoveries=1,
        )
        rows.append(_vector("rewrite_sufficient", result, judge, generator, rewriter, None))

        judge = _Judge(_eval(sufficient=False, supported=True), _eval(sufficient=False, supported=None))
        generator = _Generator("Saturday hours.")
        rewriter = _Rewriter("library saturday hours")
        result = run_with_recovery(
            "When is the library open?",
            corpus_dir=CORPUS,
            output_dir=output / "rewrite_keep",
            embedder=FakeEmbedder(),
            generator=generator,  # type: ignore[arg-type]
            rewriter=rewriter,
            judge=judge,
            max_recoveries=1,
        )
        rows.append(_vector("rewrite_insufficient_keep", result, judge, generator, rewriter, None))

        judge = _Judge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=None),
            _eval(sufficient=False, supported=False),
            _eval(sufficient=True, supported=True),
        )
        generator = _Generator("answer A", "answer B", "answer C")
        rewriter = _Rewriter("library saturday hours")
        result = run_with_recovery(
            "When is the library open?",
            corpus_dir=CORPUS,
            output_dir=output / "rewrite_expand",
            top_k=4,
            embedder=FakeEmbedder(),
            generator=generator,  # type: ignore[arg-type]
            rewriter=rewriter,
            judge=judge,
            max_recoveries=2,
        )
        rows.append(_vector("rewrite_expand", result, judge, generator, rewriter, None))

        judge = _Judge(
            _eval(sufficient=False, supported=False),
            _eval(sufficient=False, supported=None),
            _eval(sufficient=False, supported=False),
        )
        generator = _Generator("Hangar 2, bay C.", "The fine is $5 per day.")
        rewriter = _Rewriter("late return fine")
        result = run_with_recovery(
            "What is the late-return fine?",
            corpus_dir=CORPUS,
            output_dir=output / "abstain",
            top_k=1,
            embedder=FakeEmbedder(),
            generator=generator,  # type: ignore[arg-type]
            rewriter=rewriter,
            judge=judge,
            max_recoveries=2,
        )
        rows.append(_vector("abstain", result, judge, generator, rewriter, None))
    return rows


if __name__ == "__main__":
    import json

    print(json.dumps(run_all(), indent=2))
