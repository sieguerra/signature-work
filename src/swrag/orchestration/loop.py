"""Evaluation-guided loop: evaluate → diagnose → recover → verify.

One recovery attempt, then stop. Does not reimplement retrieval, judging, or
diagnosis. Does not read gold labels.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from swrag.diagnosis.diagnose import (
    EVIDENCE_INSUFFICIENCY,
    RETRIEVAL_MISS,
    diagnose_after_rewrite,
    diagnose_runtime,
)
from swrag.evaluation.judge import GroundingJudge
from swrag.generation.openai_generator import OpenAIGenerator
from swrag.pipeline.baseline import QueryState, build_corpus_index, execute_query, write_run
from swrag.retrieval.memory_index import InMemoryIndex
from swrag.recovery.policy import REGENERATE, REWRITE, select_recovery
from swrag.recovery.regenerate import ConstrainedRegenerator
from swrag.recovery.rewrite import LLMQueryRewriter
from swrag.retrieval.embedder import Embedder
from swrag.types import (
    BaselineRunResult,
    Diagnosis,
    GenerationResult,
    RecoveryDecision,
    RetrievalResult,
)
from swrag.verification.runtime import verify_runtime

ABSTAIN_ANSWER = "I do not know based on the retrieved documents."


class Regenerator(Protocol):
    """Structural type for tests; ConstrainedRegenerator satisfies this."""

    def regenerate(
        self,
        *,
        question: str,
        retrieval: RetrievalResult,
        previous_answer: str,
    ) -> GenerationResult: ...


class Rewriter(Protocol):
    def rewrite(self, *, question: str, retrieval: RetrievalResult) -> str: ...


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
    rewriter: Rewriter | None = None,
    question_id: str | None = None,
    max_recoveries: int = 1,
    index: InMemoryIndex | None = None,
) -> BaselineRunResult:
    """Run the loop and write one trace. Historical traces are never overwritten."""
    resolved_index = index if index is not None else build_corpus_index(corpus_dir, embedder)
    state = execute_query(
        query,
        corpus_dir=corpus_dir,
        top_k=top_k,
        embedder=embedder,
        generate=generate,
        generator=generator,
        judge=judge,
        index=resolved_index,
    )
    decision = select_recovery(state.diagnosis, state.runtime_evaluation)
    previous_answer = None
    verification = None
    rewritten_query = None

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

    elif decision.action == REWRITE and max_recoveries >= 1:
        previous_answer = state.generation.answer
        actor = rewriter or LLMQueryRewriter()
        rewritten_query = actor.rewrite(question=query, retrieval=state.retrieval)
        probe = execute_query(
            query,
            corpus_dir=corpus_dir,
            top_k=top_k,
            embedder=embedder,
            generate=False,
            judge=judge,
            search_query=rewritten_query,
            index=resolved_index,
        )
        before = state.runtime_evaluation
        after = probe.runtime_evaluation
        if after is not None and after.evidence_sufficient:
            if generate:
                producer = generator or OpenAIGenerator()
                repaired = producer.generate(query, probe.retrieval)
                post_eval = after
                post_diag = None
                if judge is not None:
                    post_eval = judge.judge(
                        question=query,
                        answer=repaired.answer,
                        retrieval=probe.retrieval,
                    )
                    post_diag = diagnose_runtime(post_eval)
                generation = repaired
            else:
                post_eval = after
                post_diag = (
                    diagnose_after_rewrite(before, after) if before is not None else None
                )
                generation = probe.generation
            if before is not None and post_eval is not None:
                verification = verify_runtime(before, post_eval)
            decision = RecoveryDecision(
                action=REWRITE,
                reason=decision.reason,
                attributed_class=RETRIEVAL_MISS,
            )
            state = QueryState(
                query=state.query,
                retrieval=probe.retrieval,
                generation=generation,
                runtime_evaluation=post_eval,
                diagnosis=post_diag,
            )
        else:
            if before is not None and after is not None:
                verification = verify_runtime(before, after)
                post_diag = diagnose_after_rewrite(before, after)
            else:
                post_diag = Diagnosis(
                    failure_class=EVIDENCE_INSUFFICIENCY,
                    rationale="rewrite did not yield sufficient evidence",
                    detector="rewrite-outcome",
                )
            decision = RecoveryDecision(
                action=REWRITE,
                reason=decision.reason,
                attributed_class=EVIDENCE_INSUFFICIENCY,
            )
            state = QueryState(
                query=state.query,
                retrieval=probe.retrieval,
                generation=GenerationResult(answer=ABSTAIN_ANSWER, model="abstain"),
                runtime_evaluation=after if after is not None else state.runtime_evaluation,
                diagnosis=post_diag,
            )

    return write_run(
        state,
        output_dir=output_dir,
        question_id=question_id,
        recovery=decision,
        verification=verification,
        previous_answer=previous_answer,
        rewritten_query=rewritten_query,
    )
