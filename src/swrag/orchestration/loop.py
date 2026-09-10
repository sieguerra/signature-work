"""Evaluation-guided loop: evaluate → diagnose → recover → verify.

One recovery attempt, then stop (accept / abstain / max retries). Does not
reimplement retrieval, judging, or diagnosis. Does not read gold labels.
"""

from __future__ import annotations

from pathlib import Path

from typing import Protocol

from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.evaluation.judge import GroundingJudge
from swrag.generation.openai_generator import OpenAIGenerator
from swrag.pipeline.baseline import QueryState, execute_query, write_run
from swrag.recovery.policy import REGENERATE, select_recovery
from swrag.recovery.regenerate import ConstrainedRegenerator
from swrag.retrieval.embedder import Embedder
from swrag.types import BaselineRunResult, GenerationResult, RetrievalResult
from swrag.verification.runtime import verify_runtime


class Regenerator(Protocol):
    """Structural type for tests; ConstrainedRegenerator satisfies this."""

    def regenerate(
        self,
        *,
        question: str,
        retrieval: RetrievalResult,
        previous_answer: str,
    ) -> GenerationResult: ...


def run_with_recovery(
    query: str,
    *,
    corpus_dir: str | Path,
    output_dir: str | Path,
    top_k: int = 4,
    embedder: Embedder | None = None,
    generate: bool = True,
    generator: OpenAIGenerator | None = None,
    judge: GroundingJudge | None = None,
    regenerator: Regenerator | None = None,
    question_id: str | None = None,
    max_recoveries: int = 1,
) -> BaselineRunResult:
    """Run the loop and write one trace. Historical traces are never overwritten."""
    state = execute_query(
        query,
        corpus_dir=corpus_dir,
        top_k=top_k,
        embedder=embedder,
        generate=generate,
        generator=generator,
        judge=judge,
    )
    decision = select_recovery(state.diagnosis, state.runtime_evaluation)
    previous_answer = None
    verification = None

    if decision.action == REGENERATE and max_recoveries >= 1 and generate:
        actor = regenerator or ConstrainedRegenerator()
        previous_answer = state.generation.answer
        repaired = actor.regenerate(
            question=query,
            retrieval=state.retrieval,
            previous_answer=previous_answer,
        )
        post_eval = None
        post_diag = None
        if judge is not None:
            post_eval = judge.judge(
                question=query,
                answer=repaired.answer,
                retrieval=state.retrieval,
            )
            post_diag = diagnose_runtime(post_eval)
            if state.runtime_evaluation is not None:
                verification = verify_runtime(state.runtime_evaluation, post_eval)
        state = QueryState(
            query=state.query,
            retrieval=state.retrieval,
            generation=repaired,
            runtime_evaluation=post_eval if post_eval is not None else state.runtime_evaluation,
            diagnosis=post_diag if post_diag is not None else state.diagnosis,
        )

    return write_run(
        state,
        output_dir=output_dir,
        question_id=question_id,
        recovery=decision,
        verification=verification,
        previous_answer=previous_answer,
    )
