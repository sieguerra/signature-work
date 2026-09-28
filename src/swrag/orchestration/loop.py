"""Evaluation-guided loop: evaluate → diagnose → recover → verify.

``run_with_recovery`` honors ``max_recoveries`` as a real budget (issue #67).
The default stays 1 so existing Harbor/DKU configs and SequenceJudge tests do
not surprise-escalate. When the budget is greater than 1, a still-failing
attempt can escalate to a different action — usually ``expand`` (#68).

Confirm mode uses ``run_first_pass`` then ``apply_recovery`` so the explorer
can show a button before one operator-chosen action runs.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from swrag.diagnosis.diagnose import (
    EVIDENCE_INSUFFICIENCY,
    RETRIEVAL_MISS,
    diagnose_after_rewrite,
    diagnose_runtime,
)
from swrag.evaluation.judge import GroundingJudge
from swrag.evaluation.retrieval_signal import retrieval_signal
from swrag.generation.openai_generator import OpenAIGenerator
from swrag.pipeline.baseline import (
    QueryState,
    _elapsed_ms,
    build_corpus_index,
    chunks_payload,
    execute_query,
    write_run,
)
from swrag.retrieval.memory_index import InMemoryIndex
from swrag.recovery.expand import next_top_k
from swrag.recovery.policy import (
    ABSTAIN,
    ACCEPT,
    ACTIONS,
    EXPAND,
    REGENERATE,
    REWRITE,
    select_next_recovery,
    select_recovery,
)
from swrag.recovery.regenerate import ConstrainedRegenerator
from swrag.recovery.rewrite import LLMQueryRewriter
from swrag.retrieval.embedder import Embedder
from swrag.types import (
    BaselineRunResult,
    Chunk,
    Diagnosis,
    GenerationResult,
    RecoveryDecision,
    RetrievalResult,
    RuntimeEvaluation,
    ScoredChunk,
)
from swrag.verification.runtime import IMPROVED, verify_runtime

ABSTAIN_ANSWER = "I do not know based on the retrieved documents."
_ABSTAIN_PREFIX = "i do not know"
RECOVERY_PROPOSED = "proposed"
RECOVERY_APPLIED = "applied"
SOURCE_POLICY = "policy"
SOURCE_OPERATOR = "operator"
_APPLYABLE = frozenset({REGENERATE, REWRITE, EXPAND})


class RecoveryNotApplicable(ValueError):
    """Apply was refused: missing parent, not proposed, or unknown action."""


@dataclass(frozen=True)
class _Applied:
    state: QueryState
    decision: RecoveryDecision
    verification: Any
    previous_answer: str | None
    rewritten_query: str | None
    previous_retrieved_chunks: tuple[dict, ...] | None
    probe_evaluation: RuntimeEvaluation | None = None


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
    agent_config: dict[str, Any] | None = None,
) -> BaselineRunResult:
    """Run the automatic loop and write one trace. Never overwrites history.

    ``max_recoveries`` is the number of applied actions, not a boolean. A
    successful repair stops early. Default 1 preserves the V1 one-shot loop.
    """
    started = time.perf_counter()
    resolved_index = index if index is not None else build_corpus_index(corpus_dir, embedder)
    state, decision = _first_pass_state(
        query,
        corpus_dir=corpus_dir,
        top_k=top_k,
        embedder=embedder,
        generate=generate,
        generator=generator,
        judge=judge,
        index=resolved_index,
    )
    first_eval = state.runtime_evaluation
    first_answer = state.generation.answer
    first_chunks = chunks_payload(state.retrieval)

    if max_recoveries < 1 or not _should_apply(decision.action, attempts_so_far=0):
        return write_run(
            state,
            output_dir=output_dir,
            question_id=question_id,
            recovery=decision,
            recovery_status=RECOVERY_APPLIED,
            latency_ms=_elapsed_ms(started),
            agent_config=agent_config,
        )

    attempts: list[dict[str, Any]] = []
    used: list[str] = []
    current_decision = decision
    current_k = top_k
    search_query = query
    last_applied: _Applied | None = None
    rewritten_query: str | None = None
    probe_evaluation = None
    previous_chunks_to_store: tuple[dict, ...] | None = None

    while _should_apply(current_decision.action, attempts_so_far=len(attempts)):
        if len(attempts) >= max_recoveries:
            break
        applied = _apply_action(
            state,
            current_decision,
            query=query,
            corpus_dir=corpus_dir,
            top_k=current_k,
            embedder=embedder,
            generate=generate,
            generator=generator,
            judge=judge,
            regenerator=regenerator,
            rewriter=rewriter,
            index=resolved_index,
            search_query=search_query,
        )
        last_applied = applied
        state = applied.state
        used.append(current_decision.action)
        current_k = state.retrieval.top_k
        if applied.rewritten_query:
            rewritten_query = applied.rewritten_query
            search_query = applied.rewritten_query
        if applied.previous_retrieved_chunks and previous_chunks_to_store is None:
            previous_chunks_to_store = first_chunks
        if applied.probe_evaluation is not None:
            probe_evaluation = applied.probe_evaluation
        attempts.append(_attempt_payload(len(attempts), applied))

        overall = None
        if first_eval is not None and state.runtime_evaluation is not None:
            overall = verify_runtime(first_eval, state.runtime_evaluation)
            if overall.outcome == IMPROVED:
                break

        if len(attempts) >= max_recoveries:
            break
        nxt = select_next_recovery(
            last=applied.decision,
            verification=applied.verification,
            evaluation=state.runtime_evaluation,
            used=tuple(used),
            current_top_k=current_k,
        )
        if nxt is None:
            break
        if nxt.attributed_class is None and applied.decision.attributed_class is not None:
            nxt = replace(nxt, attributed_class=applied.decision.attributed_class)
        current_decision = nxt

    if last_applied is None:
        return write_run(
            state,
            output_dir=output_dir,
            question_id=question_id,
            recovery=decision,
            recovery_status=RECOVERY_APPLIED,
            latency_ms=_elapsed_ms(started),
            agent_config=agent_config,
        )

    overall_verification = last_applied.verification
    if first_eval is not None and state.runtime_evaluation is not None:
        overall_verification = verify_runtime(first_eval, state.runtime_evaluation)

    return write_run(
        last_applied.state,
        output_dir=output_dir,
        question_id=question_id,
        recovery=last_applied.decision,
        verification=overall_verification,
        previous_answer=first_answer if first_answer else last_applied.previous_answer,
        rewritten_query=rewritten_query,
        previous_retrieved_chunks=previous_chunks_to_store,
        recovery_status=RECOVERY_APPLIED,
        latency_ms=_elapsed_ms(started),
        probe_evaluation=probe_evaluation,
        agent_config=agent_config,
        recovery_attempts=tuple(attempts),
        first_pass_evaluation=first_eval,
    )


def run_first_pass(
    query: str,
    *,
    corpus_dir: str | Path,
    output_dir: str | Path,
    top_k: int = 4,
    embedder: Embedder | None = None,
    generate: bool = True,
    generator: OpenAIGenerator | None = None,
    judge: GroundingJudge | None = None,
    question_id: str | None = None,
    index: InMemoryIndex | None = None,
    agent_config: dict[str, Any] | None = None,
) -> BaselineRunResult:
    """Evaluate and select a recovery without applying it."""
    started = time.perf_counter()
    resolved_index = index if index is not None else build_corpus_index(corpus_dir, embedder)
    state, decision = _first_pass_state(
        query,
        corpus_dir=corpus_dir,
        top_k=top_k,
        embedder=embedder,
        generate=generate,
        generator=generator,
        judge=judge,
        index=resolved_index,
    )
    status = RECOVERY_APPLIED if decision.action == ACCEPT else RECOVERY_PROPOSED
    return write_run(
        state,
        output_dir=output_dir,
        question_id=question_id,
        recovery=decision,
        recovery_status=status,
        latency_ms=_elapsed_ms(started),
        agent_config=agent_config,
    )


def apply_recovery(
    parent_run_id: str,
    *,
    output_dir: str | Path,
    corpus_dir: str | Path,
    action: str | None = None,
    embedder: Embedder | None = None,
    generate: bool = True,
    generator: OpenAIGenerator | None = None,
    judge: GroundingJudge | None = None,
    regenerator: Regenerator | None = None,
    rewriter: Rewriter | None = None,
    question_id: str | None = None,
    index: InMemoryIndex | None = None,
    agent_config: dict[str, Any] | None = None,
) -> BaselineRunResult:
    """Apply one V1 action to a proposed first-pass trace. Writes a new file."""
    started = time.perf_counter()
    parent = _load_parent(output_dir, parent_run_id)
    if parent.get("parent_run_id"):
        raise RecoveryNotApplicable("cannot apply recovery to a recovered child run")
    if parent.get("recovery_status") != RECOVERY_PROPOSED:
        raise RecoveryNotApplicable("recovery is not proposed on this run")
    if _child_exists(output_dir, parent_run_id):
        raise RecoveryNotApplicable("recovery was already applied for this run")
    proposed = _decision_from_payload(parent.get("recovery"))
    if proposed is None or not proposed.action:
        raise RecoveryNotApplicable("parent has no proposed recovery")
    chosen = (action or proposed.action).strip()
    if chosen not in ACTIONS:
        raise RecoveryNotApplicable(f"unknown recovery action: {chosen}")
    decision = _decision_to_apply(proposed, chosen)
    state = _query_state_from_trace(parent)
    resolved_index = index if index is not None else build_corpus_index(corpus_dir, embedder)
    applied = _apply_action(
        state,
        decision,
        query=str(parent.get("query") or ""),
        corpus_dir=corpus_dir,
        top_k=int(parent.get("top_k") or 4),
        embedder=embedder,
        generate=generate,
        generator=generator,
        judge=judge,
        regenerator=regenerator,
        rewriter=rewriter,
        index=resolved_index,
    )
    return write_run(
        applied.state,
        output_dir=output_dir,
        question_id=question_id or parent.get("question_id"),
        recovery=applied.decision,
        verification=applied.verification,
        previous_answer=applied.previous_answer,
        rewritten_query=applied.rewritten_query,
        previous_retrieved_chunks=applied.previous_retrieved_chunks,
        recovery_status=RECOVERY_APPLIED,
        parent_run_id=parent_run_id,
        latency_ms=_elapsed_ms(started),
        probe_evaluation=applied.probe_evaluation,
        agent_config=agent_config if agent_config is not None else parent.get("agent_config"),
    )


def _first_pass_state(
    query: str,
    *,
    corpus_dir: str | Path,
    top_k: int,
    embedder: Embedder | None,
    generate: bool,
    generator: OpenAIGenerator | None,
    judge: GroundingJudge | None,
    index: InMemoryIndex,
) -> tuple[QueryState, RecoveryDecision]:
    state = execute_query(
        query,
        corpus_dir=corpus_dir,
        top_k=top_k,
        embedder=embedder,
        generate=generate,
        generator=generator,
        judge=judge,
        index=index,
    )
    return state, select_recovery(
        state.diagnosis,
        state.runtime_evaluation,
        state.retrieval_signal,
    )


def _should_apply(action: str, *, attempts_so_far: int) -> bool:
    """First-pass abstain stays a recorded stop; escalation abstain is applied."""
    if action in _APPLYABLE:
        return True
    return action == ABSTAIN and attempts_so_far > 0


def _attempt_payload(index: int, applied: _Applied) -> dict[str, Any]:
    decision = applied.decision
    retrieval = applied.state.retrieval
    row: dict[str, Any] = {
        "index": index,
        "action": decision.action,
        "reason": decision.reason,
        "trigger": decision.trigger,
        "attributed_class": decision.attributed_class,
        "outcome_note": decision.outcome_note,
        "top_k": retrieval.top_k,
        "retrieved_doc_ids": [scored.chunk.doc_id for scored in retrieval.chunks],
        "verification": (
            applied.verification.as_trace_payload() if applied.verification is not None else None
        ),
    }
    if applied.rewritten_query:
        row["rewritten_query"] = applied.rewritten_query
    if decision.parameters:
        row["parameters"] = dict(decision.parameters)
    return row


def _apply_expand(
    state: QueryState,
    decision: RecoveryDecision,
    *,
    query: str,
    corpus_dir: str | Path,
    top_k: int,
    embedder: Embedder | None,
    generate: bool,
    generator: OpenAIGenerator | None,
    judge: GroundingJudge | None,
    index: InMemoryIndex,
    search_query: str,
) -> _Applied:
    widened = next_top_k(top_k)
    if widened is None:
        return _Applied(state, decision, None, None, None, None)
    previous_answer = state.generation.answer
    previous_retrieved_chunks = chunks_payload(state.retrieval)
    nxt = execute_query(
        query,
        corpus_dir=corpus_dir,
        top_k=widened,
        embedder=embedder,
        generate=generate,
        generator=generator,
        judge=judge,
        search_query=search_query,
        index=index,
    )
    verification = None
    if state.runtime_evaluation is not None and nxt.runtime_evaluation is not None:
        verification = verify_runtime(state.runtime_evaluation, nxt.runtime_evaluation)
    next_decision = RecoveryDecision(
        action=EXPAND,
        reason=decision.reason,
        attributed_class=decision.attributed_class,
        source=decision.source,
        outcome_note=(
            f"widened top_k from {state.retrieval.top_k} to {nxt.retrieval.top_k}"
        ),
        trigger=decision.trigger,
        parameters={"from_k": state.retrieval.top_k, "to_k": nxt.retrieval.top_k},
    )
    next_state = QueryState(
        query=state.query,
        retrieval=nxt.retrieval,
        generation=nxt.generation,
        runtime_evaluation=(
            nxt.runtime_evaluation
            if nxt.runtime_evaluation is not None
            else state.runtime_evaluation
        ),
        diagnosis=nxt.diagnosis if nxt.diagnosis is not None else state.diagnosis,
        # Keep the first-pass signal: that is what overrode the judge (#64).
        retrieval_signal=state.retrieval_signal,
    )
    return _Applied(
        next_state,
        next_decision,
        verification,
        previous_answer,
        None,
        previous_retrieved_chunks,
    )


def _decision_to_apply(proposed: RecoveryDecision, chosen: str) -> RecoveryDecision:
    source = SOURCE_POLICY if chosen == proposed.action else SOURCE_OPERATOR
    return RecoveryDecision(
        action=chosen,
        reason=proposed.reason,
        attributed_class=proposed.attributed_class,
        source=source,
        trigger=proposed.trigger,
    )


def _apply_action(
    state: QueryState,
    decision: RecoveryDecision,
    *,
    query: str,
    corpus_dir: str | Path,
    top_k: int,
    embedder: Embedder | None,
    generate: bool,
    generator: OpenAIGenerator | None,
    judge: GroundingJudge | None,
    regenerator: Regenerator | None,
    rewriter: Rewriter | None,
    index: InMemoryIndex,
    search_query: str | None = None,
) -> _Applied:
    if decision.action == ACCEPT:
        return _Applied(state, decision, None, None, None, None)
    if decision.action == ABSTAIN:
        abstained = QueryState(
            query=state.query,
            retrieval=state.retrieval,
            generation=GenerationResult(answer=ABSTAIN_ANSWER, model="abstain"),
            runtime_evaluation=state.runtime_evaluation,
            diagnosis=state.diagnosis,
            retrieval_signal=state.retrieval_signal,
        )
        verification = None
        post_eval = state.runtime_evaluation
        if judge is not None:
            post_eval = judge.judge(
                question=query,
                answer=ABSTAIN_ANSWER,
                retrieval=state.retrieval,
            )
            post_diag = diagnose_runtime(post_eval)
            if state.runtime_evaluation is not None:
                verification = verify_runtime(state.runtime_evaluation, post_eval)
            abstained = QueryState(
                query=state.query,
                retrieval=state.retrieval,
                generation=GenerationResult(answer=ABSTAIN_ANSWER, model="abstain"),
                runtime_evaluation=post_eval,
                diagnosis=post_diag,
                retrieval_signal=state.retrieval_signal,
            )
        return _Applied(
            abstained,
            decision,
            verification,
            state.generation.answer,
            None,
            None,
        )
    if decision.action == REGENERATE:
        if not generate:
            return _Applied(state, decision, None, None, None, None)
        actor = regenerator or ConstrainedRegenerator()
        previous_answer = state.generation.answer
        repaired = actor.regenerate(
            question=query,
            retrieval=state.retrieval,
            previous_answer=previous_answer,
        )
        post_eval = None
        post_diag = None
        verification = None
        if judge is not None:
            post_eval = judge.judge(
                question=query,
                answer=repaired.answer,
                retrieval=state.retrieval,
            )
            post_diag = diagnose_runtime(post_eval)
            if state.runtime_evaluation is not None:
                verification = verify_runtime(state.runtime_evaluation, post_eval)
        next_state = QueryState(
            query=state.query,
            retrieval=state.retrieval,
            generation=repaired,
            runtime_evaluation=post_eval if post_eval is not None else state.runtime_evaluation,
            diagnosis=post_diag if post_diag is not None else state.diagnosis,
            retrieval_signal=state.retrieval_signal,
        )
        return _Applied(next_state, decision, verification, previous_answer, None, None)

    if decision.action == EXPAND:
        return _apply_expand(
            state,
            decision,
            query=query,
            corpus_dir=corpus_dir,
            top_k=top_k,
            embedder=embedder,
            generate=generate,
            generator=generator,
            judge=judge,
            index=index,
            search_query=search_query or query,
        )

    if decision.action != REWRITE:
        raise RecoveryNotApplicable(f"unknown recovery action: {decision.action}")

    # Rewriting calls a model, so it cannot run on a credential-free retrieve-only
    # run unless a rewriter was injected. Record the proposal and leave it
    # unapplied rather than breaking the no-API-key harness. ``regenerate`` above
    # skips on the same grounds.
    if not generate and rewriter is None:
        return _Applied(state, decision, None, None, None, None)

    previous_answer = state.generation.answer
    previous_retrieved_chunks = chunks_payload(state.retrieval)
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
        index=index,
    )
    before = state.runtime_evaluation
    after = probe.runtime_evaluation
    verification = None
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
            post_diag = diagnose_after_rewrite(before, after) if before is not None else None
            generation = probe.generation
        if before is not None and post_eval is not None:
            verification = verify_runtime(before, post_eval)
        next_decision = RecoveryDecision(
            action=REWRITE,
            reason=decision.reason,
            attributed_class=_attributed_class_after_rewrite(before, post_eval),
            source=decision.source,
            outcome_note=_rewrite_success_note(after, post_eval),
            trigger=decision.trigger,
        )
        next_state = QueryState(
            query=state.query,
            retrieval=probe.retrieval,
            generation=generation,
            runtime_evaluation=post_eval,
            diagnosis=post_diag,
            # Keep the first-pass signal: that is what overrode the judge (#64).
            # Post-rewrite scores live on the new retrieved chunks.
            retrieval_signal=state.retrieval_signal,
        )
        return _Applied(
            next_state,
            next_decision,
            verification,
            previous_answer,
            rewritten_query,
            previous_retrieved_chunks,
            probe_evaluation=after,
        )
    generation, outcome_note, kept_first_pass = _generation_after_failed_rewrite(state, before)

    # Attribution asks what the rewrite retrieved, so it always reads the probe.
    if before is not None and after is not None:
        post_diag = diagnose_after_rewrite(before, after)
    else:
        post_diag = Diagnosis(
            failure_class=EVIDENCE_INSUFFICIENCY,
            rationale="rewrite did not yield sufficient evidence",
            detector="rewrite-outcome",
        )

    # The probe generates no answer, so its answer_supported is None. Verifying a
    # kept first-pass answer against the probe would read that None as a lost
    # support flag and report a degradation that never happened. The first-pass
    # evaluation is the one that describes the answer actually being kept.
    post_eval = before if kept_first_pass and before is not None else after
    if before is not None and post_eval is not None:
        verification = verify_runtime(before, post_eval)

    next_decision = RecoveryDecision(
        action=REWRITE,
        reason=decision.reason,
        attributed_class=EVIDENCE_INSUFFICIENCY,
        source=decision.source,
        outcome_note=outcome_note,
        trigger=decision.trigger,
    )
    next_state = QueryState(
        query=state.query,
        retrieval=probe.retrieval,
        generation=generation,
        runtime_evaluation=post_eval if post_eval is not None else state.runtime_evaluation,
        diagnosis=post_diag,
        retrieval_signal=state.retrieval_signal,
    )
    return _Applied(
        next_state,
        next_decision,
        verification,
        previous_answer,
        rewritten_query,
        previous_retrieved_chunks,
        probe_evaluation=after,
    )


def _attributed_class_after_rewrite(
    before: RuntimeEvaluation | None,
    post_eval: RuntimeEvaluation | None,
) -> str | None:
    """Attribute the original failure from the evaluation verification also uses.

    Hardcoding ``retrieval_miss`` here let a trace claim the rewrite repaired
    retrieval while verification reported ``still_failing`` on the same run,
    because the two read different judge calls. Deriving the class from
    ``post_eval`` keeps one answer per run.
    """
    if before is None or post_eval is None:
        return RETRIEVAL_MISS
    return diagnose_after_rewrite(before, post_eval).failure_class


def _rewrite_success_note(
    probe_eval: RuntimeEvaluation | None,
    post_eval: RuntimeEvaluation | None,
) -> str:
    """Record when the probe and the post-recovery judge disagree on sufficiency."""
    if probe_eval is None or post_eval is None:
        return ""
    if probe_eval.evidence_sufficient == post_eval.evidence_sufficient:
        return ""
    return (
        "judge disagreement: the rewrite probe called the new evidence "
        f"{_sufficiency_word(probe_eval)}, the post-recovery judge called it "
        f"{_sufficiency_word(post_eval)}; attribution and verification both "
        "follow the post-recovery judge"
    )


def _sufficiency_word(evaluation: RuntimeEvaluation) -> str:
    return "sufficient" if evaluation.evidence_sufficient else "insufficient"


def is_abstention(answer: str) -> bool:
    """True for an explicit "I do not know" answer, however it was produced."""
    return answer.strip().lower().startswith(_ABSTAIN_PREFIX)


def _generation_after_failed_rewrite(
    state: QueryState,
    before: RuntimeEvaluation | None,
) -> tuple[GenerationResult, str, bool]:
    """Pick the answer to keep when a rewrite did not improve the evidence.

    Returns the generation, a note for the trace, and whether the first-pass
    answer was kept.

    Abstention is a decision, not a fallback. Discarding a first-pass answer the
    judge already called supported makes the run strictly less useful than doing
    nothing, so that answer is kept and the failed attempt is recorded instead.
    """
    abstained = GenerationResult(answer=ABSTAIN_ANSWER, model="abstain")
    answer = state.generation.answer.strip()
    if not answer:
        return (
            abstained,
            "rewrite did not improve evidence and there was no first-pass answer to keep",
            False,
        )
    if is_abstention(answer):
        return (
            abstained,
            "rewrite did not improve evidence and the first-pass answer already abstained",
            False,
        )
    if before is not None and before.answer_supported is True:
        return (
            state.generation,
            "rewrite did not improve evidence; kept the supported first-pass answer",
            True,
        )
    return (
        abstained,
        "rewrite did not improve evidence and the first-pass answer was not supported",
        False,
    )


def _decision_from_payload(payload: Any) -> RecoveryDecision | None:
    if not isinstance(payload, dict):
        return None
    action = payload.get("action")
    if not action:
        return None
    return RecoveryDecision(
        action=str(action),
        trigger=str(payload.get("trigger") or ""),
        reason=str(payload.get("reason") or ""),
        attributed_class=payload.get("attributed_class"),
        source=str(payload.get("source") or SOURCE_POLICY),
    )


def _evaluation_from_payload(payload: Any) -> RuntimeEvaluation | None:
    if not isinstance(payload, dict):
        return None
    supported = payload.get("answer_supported")
    if supported is not None:
        supported = bool(supported)
    return RuntimeEvaluation(
        evidence_sufficient=bool(payload.get("evidence_sufficient")),
        answer_supported=supported,
        sufficiency_rationale=str(payload.get("sufficiency_rationale") or ""),
        support_rationale=str(payload.get("support_rationale") or ""),
        judge=str(payload.get("judge") or ""),
        model=str(payload.get("model") or ""),
    )


def _diagnosis_from_payload(payload: Any) -> Diagnosis | None:
    if not isinstance(payload, dict):
        return None
    klass = payload.get("failure_class")
    return Diagnosis(
        failure_class=str(klass) if klass is not None else None,
        rationale=str(payload.get("rationale") or ""),
        detector=str(payload.get("detector") or "first-pass-runtime"),
    )


def _optional_page(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _query_state_from_trace(payload: dict[str, Any]) -> QueryState:
    chunks = []
    for item in payload.get("retrieved_chunks") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        chunk = Chunk(
            chunk_id=str(item.get("chunk_id") or ""),
            doc_id=str(item.get("doc_id") or ""),
            title=str(item.get("title") or ""),
            text=text,
            start_char=0,
            end_char=len(text),
            page=_optional_page(item.get("page")),
        )
        chunks.append(ScoredChunk(chunk=chunk, score=float(item.get("score") or 0.0)))
    nested = payload.get("generation") if isinstance(payload.get("generation"), dict) else {}
    retrieval = RetrievalResult(
        query=str(payload.get("query") or ""),
        chunks=tuple(chunks),
        top_k=int(payload.get("top_k") or 4),
        embedding_model=str(payload.get("embedding_model") or ""),
    )
    return QueryState(
        query=str(payload.get("query") or ""),
        retrieval=retrieval,
        generation=GenerationResult(
            answer=str(nested.get("answer") or payload.get("answer") or ""),
            model=str(nested.get("model") or payload.get("model") or ""),
        ),
        # Recomputed rather than read back: the stored scores are the source of
        # truth, so a replayed state cannot disagree with a freshly run one.
        retrieval_signal=retrieval_signal(retrieval),
        runtime_evaluation=_evaluation_from_payload(payload.get("runtime_evaluation")),
        diagnosis=_diagnosis_from_payload(payload.get("diagnosis")),
    )


def _safe_run_id(run_id: str) -> bool:
    if not run_id or run_id in {"summary", "comparison", "config"}:
        return False
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        return False
    return True


def _iter_trace_files(output_dir: str | Path):
    root = Path(output_dir)
    if not root.is_dir():
        return
    root_resolved = root.resolve()
    for path in root.rglob("*.json"):
        if path.name in {"summary.json", "comparison.json", "config.json"}:
            continue
        try:
            path.resolve().relative_to(root_resolved)
        except ValueError:
            continue
        yield path


def _load_parent(output_dir: str | Path, run_id: str) -> dict[str, Any]:
    if not _safe_run_id(run_id):
        raise RecoveryNotApplicable(f"run not found: {run_id}")
    matches = [
        path
        for path in _iter_trace_files(output_dir)
        if path.name == f"{run_id}.json"
    ]
    if not matches:
        raise RecoveryNotApplicable(f"run not found: {run_id}")
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecoveryNotApplicable(f"run not found: {run_id}") from error
    if not isinstance(payload, dict) or payload.get("run_id") != run_id:
        raise RecoveryNotApplicable(f"run not found: {run_id}")
    return payload


def _child_exists(output_dir: str | Path, parent_run_id: str) -> bool:
    for path in _iter_trace_files(output_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("parent_run_id") == parent_run_id:
            return True
    return False

