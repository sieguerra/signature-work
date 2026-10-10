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
from swrag.tracing.schema import (
    ANSWER_ABSTAINED,
    ANSWER_GENERATED,
    ANSWER_KEPT_PREVIOUS,
    ANSWER_NONE,
    EVAL_CARRIED,
    EVAL_JUDGE,
    EVAL_PROBE,
    EVIDENCE_REPLACED,
    EVIDENCE_UNCHANGED,
    EVIDENCE_WIDENED,
    attempt_record,
    initial_from_trace,
    initial_snapshot,
)
from swrag.usage import usage_checkpoint, usage_delta
from swrag.retrieval.memory_index import InMemoryIndex
from swrag.recovery.expand import next_top_k
from swrag.recovery.gap_signal import CONFLICT, GapAssessment, blocking_assessment
from swrag.recovery.policy import (
    ABSTAIN,
    ACCEPT,
    ACTIONS,
    DEFAULT_POLICY,
    canonical_policy,
    EXPAND,
    REGENERATE,
    REWRITE,
    normalize_policy,
    select_next_recovery,
    select_recovery,
    uses_gap_block,
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
    Verification,
)
from swrag.verification.runtime import IMPROVED, STILL_FAILING, verify_runtime

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
    answer_relation: str = "unchanged"
    evidence_relation: str = EVIDENCE_UNCHANGED
    evaluation_source: str = EVAL_CARRIED
    executed: bool = True
    search_query: str | None = None


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
    run_mode: str = "loop",
    recovery_policy: str = DEFAULT_POLICY,
    prepared_state: QueryState | None = None,
) -> BaselineRunResult:
    """Run the automatic loop and write one trace. Never overwrites history.

    ``max_recoveries`` is the number of applied actions, not a boolean. A
    successful repair stops early. Default 1 preserves the V1 one-shot loop.
    """
    started = time.perf_counter()
    policy = canonical_policy(recovery_policy)
    resolved_index = index if index is not None else build_corpus_index(corpus_dir, embedder)
    pass_started = time.perf_counter()
    if prepared_state is None:
        state, decision = _first_pass_state(
            query,
            corpus_dir=corpus_dir,
            top_k=top_k,
            embedder=embedder,
            generate=generate,
            generator=generator,
            judge=judge,
            index=resolved_index,
            policy=policy,
        )
    else:
        state = prepared_state
        decision = select_recovery(
            state.diagnosis,
            state.runtime_evaluation,
            state.retrieval_signal,
            policy=policy,
        )
    first_latency = _elapsed_ms(pass_started)
    first_eval = state.runtime_evaluation
    first_answer = state.generation.answer
    first_chunks = chunks_payload(state.retrieval)
    first_state = state

    if uses_gap_block(policy) and decision.action == ACCEPT:
        blocked = blocking_assessment(query, state.generation.answer, _evidence_texts(state))
        if blocked is not None and blocked.label == CONFLICT:
            stopped = _policy_stop(state, blocked)
            return write_run(
                stopped.state,
                output_dir=output_dir,
                question_id=question_id,
                recovery=stopped.decision,
                recovery_status=RECOVERY_APPLIED,
                latency_ms=_elapsed_ms(started),
                agent_config=agent_config,
                run_mode=run_mode,
                recovery_policy=policy,
            )

    if max_recoveries < 1 or not _should_apply(decision.action, attempts_so_far=0):
        return write_run(
            state,
            output_dir=output_dir,
            question_id=question_id,
            recovery=decision,
            recovery_status=RECOVERY_APPLIED,
            latency_ms=_elapsed_ms(started),
            agent_config=agent_config,
            run_mode=run_mode,
            recovery_policy=policy,
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
        usage_before = usage_checkpoint()
        attempt_started = time.perf_counter()
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
        attempt_latency = _elapsed_ms(attempt_started)
        attempt_usage = usage_delta(usage_before, usage_checkpoint())
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
        attempts.append(
            _attempt_payload(
                len(attempts),
                applied,
                latency_ms=attempt_latency,
                usage=attempt_usage,
            )
        )

        if uses_gap_block(policy):
            blocked = blocking_assessment(
                query,
                state.generation.answer,
                _evidence_texts(state),
            )
            if blocked is not None:
                usage_before = usage_checkpoint()
                attempt_started = time.perf_counter()
                applied = _policy_stop(state, blocked)
                attempt_latency = _elapsed_ms(attempt_started)
                attempt_usage = usage_delta(usage_before, usage_checkpoint())
                last_applied = applied
                state = applied.state
                used.append(ABSTAIN)
                attempts.append(
                    _attempt_payload(
                        len(attempts),
                        applied,
                        latency_ms=attempt_latency,
                        usage=attempt_usage,
                    )
                )
                break

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
            policy=policy,
            question=query,
            evidence_texts=_evidence_texts(state),
        )
        if nxt is None:
            break
        if nxt.attributed_class is None and applied.decision.attributed_class is not None:
            nxt = replace(nxt, attributed_class=applied.decision.attributed_class)
        current_decision = nxt

    if last_applied is not None and _needs_terminal_abstain(last_applied.decision, state):
        usage_before = usage_checkpoint()
        attempt_started = time.perf_counter()
        applied = _terminal_abstain(state, last_applied.decision)
        attempt_latency = _elapsed_ms(attempt_started)
        attempt_usage = usage_delta(usage_before, usage_checkpoint())
        last_applied = applied
        state = applied.state
        used.append(ABSTAIN)
        attempts.append(
            _attempt_payload(
                len(attempts),
                applied,
                latency_ms=attempt_latency,
                usage=attempt_usage,
            )
        )

    if last_applied is None:
        return write_run(
            state,
            output_dir=output_dir,
            question_id=question_id,
            recovery=decision,
            recovery_status=RECOVERY_APPLIED,
            latency_ms=_elapsed_ms(started),
            agent_config=agent_config,
            run_mode=run_mode,
            recovery_policy=policy,
        )

    overall_verification = last_applied.verification
    if first_eval is not None and state.runtime_evaluation is not None:
        if is_abstention(state.generation.answer) and (
            not state.runtime_evaluation.evidence_sufficient
            or state.runtime_evaluation.span_rejections
        ):
            overall_verification = Verification(outcome=STILL_FAILING, rationale=_ABSTAIN_RATIONALE)
        else:
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
        run_mode=run_mode,
        recovery_policy=policy,
        initial=_initial_from_state(first_state, first_latency),
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
    run_mode: str = "loop_confirm",
    recovery_policy: str = DEFAULT_POLICY,
) -> BaselineRunResult:
    """Evaluate and select a recovery without applying it."""
    started = time.perf_counter()
    policy = canonical_policy(recovery_policy)
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
        policy=policy,
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
        run_mode=run_mode,
        recovery_policy=policy,
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
    usage_before = usage_checkpoint()
    attempt_started = time.perf_counter()
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
    attempt = _attempt_payload(
        0,
        applied,
        latency_ms=_elapsed_ms(attempt_started),
        usage=usage_delta(usage_before, usage_checkpoint()),
    )
    parent_eval = _evaluation_from_payload(parent.get("runtime_evaluation"))
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
        recovery_attempts=(attempt,),
        first_pass_evaluation=parent_eval,
        run_mode="loop_confirm",
        initial=initial_from_trace(parent),
        recovery_policy=normalize_policy(str(parent.get("recovery_policy") or "")) or DEFAULT_POLICY,
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
    policy: str = DEFAULT_POLICY,
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
        policy=policy,
    )


_ABSTAIN_RATIONALE = (
    "evidence stayed insufficient after recovery; the loop abstained instead of answering"
)


def _needs_terminal_abstain(last: RecoveryDecision, state: QueryState) -> bool:
    """The loop ended on a fresh answer the judge cannot ground in sufficient evidence.

    Only expand and regenerate end with a newly generated answer; a failed
    rewrite already picks between keeping and abstaining. The same rule applies
    here: a supported answer that is not a refusal is kept (gold-027), a
    refusal is normalized to the abstention, anything else abstains.
    """
    evaluation = state.runtime_evaluation
    if last.action not in {EXPAND, REGENERATE} or evaluation is None:
        return False
    answer = state.generation.answer.strip()
    if answer == ABSTAIN_ANSWER:
        return False
    # A rejected clock is not grounded, even when the judge called the
    # evidence sufficient because a nearby time was present.
    if evaluation.span_rejections:
        return True
    if evaluation.evidence_sufficient:
        return False
    return is_abstention(answer) or evaluation.answer_supported is not True


def _terminal_abstain(state: QueryState, last: RecoveryDecision) -> _Applied:
    """Replace an ungrounded answer with the abstention once retries are spent.

    Abstaining changes no evidence, so it runs outside ``max_recoveries`` and
    makes no judge call: sufficiency is carried over and support is left null
    because there is no answer to support.
    """
    evaluation = state.runtime_evaluation
    if evaluation is not None and evaluation.span_rejections:
        reason = (
            f"{last.action} stated a fact the retrieved text does not contain; "
            "abstain instead of answering"
        )
    else:
        reason = f"{last.action} ended with insufficient evidence; abstain instead of answering"
    decision = RecoveryDecision(
        action=ABSTAIN,
        reason=reason,
        attributed_class=last.attributed_class,
        source=SOURCE_POLICY,
        trigger=last.trigger,
        outcome_note="replaced the last answer with the abstention; no judge call",
    )
    abstained = QueryState(
        query=state.query,
        retrieval=state.retrieval,
        generation=GenerationResult(answer=ABSTAIN_ANSWER, model="abstain"),
        runtime_evaluation=(
            replace(
                evaluation,
                answer_supported=None,
                support_rationale="The loop abstained, so there is no answer to support.",
            )
            if evaluation is not None
            else None
        ),
        diagnosis=state.diagnosis,
        retrieval_signal=state.retrieval_signal,
    )
    return _Applied(
        abstained,
        decision,
        Verification(outcome=STILL_FAILING, rationale=_ABSTAIN_RATIONALE),
        state.generation.answer,
        None,
        None,
        answer_relation=ANSWER_ABSTAINED,
        evidence_relation=EVIDENCE_UNCHANGED,
        evaluation_source=EVAL_CARRIED,
    )


def _evidence_texts(state: QueryState) -> tuple[str, ...]:
    return tuple(item.chunk.text for item in state.retrieval.chunks)


def _safe_answer(decision: RecoveryDecision) -> str:
    parameters = decision.parameters or {}
    text = str(parameters.get("safe_answer") or "").strip()
    if text.lower().startswith("i do not know"):
        return text
    return ABSTAIN_ANSWER


def _policy_stop(state: QueryState, assessment: GapAssessment) -> _Applied:
    """Replace a conflicting or neighbor-fact answer. No extra model call."""
    decision = RecoveryDecision(
        action=ABSTAIN,
        reason=assessment.reason,
        attributed_class=None,
        source=SOURCE_POLICY,
        trigger="",
        outcome_note="replaced the answer because the retrieved evidence does not settle the question",
        parameters=assessment.as_parameters(forced_stop=False),
    )
    answer = _safe_answer(decision)
    evaluation = state.runtime_evaluation
    stopped = QueryState(
        query=state.query,
        retrieval=state.retrieval,
        generation=GenerationResult(answer=answer, model="abstain"),
        runtime_evaluation=(
            replace(
                evaluation,
                answer_supported=None,
                support_rationale="The loop abstained, so there is no answer to support.",
            )
            if evaluation is not None
            else None
        ),
        diagnosis=state.diagnosis,
        retrieval_signal=state.retrieval_signal,
    )
    return _Applied(
        stopped,
        decision,
        Verification(outcome=STILL_FAILING, rationale=_ABSTAIN_RATIONALE),
        state.generation.answer,
        None,
        None,
        answer_relation=ANSWER_ABSTAINED,
        evidence_relation=EVIDENCE_UNCHANGED,
        evaluation_source=EVAL_CARRIED,
    )


def _should_apply(action: str, *, attempts_so_far: int) -> bool:
    """First-pass abstain stays a recorded stop; escalation abstain is applied."""
    if action in _APPLYABLE:
        return True
    return action == ABSTAIN and attempts_so_far > 0


def _initial_from_state(state: QueryState, latency_ms: float) -> dict[str, Any]:
    evaluation = state.runtime_evaluation
    diagnosis = state.diagnosis
    signal = state.retrieval_signal
    return initial_snapshot(
        query=state.query,
        retrieved_chunks=chunks_payload(state.retrieval),
        answer=state.generation.answer,
        model=state.generation.model,
        top_k=state.retrieval.top_k,
        runtime_evaluation=evaluation.as_trace_payload() if evaluation is not None else None,
        retrieval_signal=signal.as_trace_payload() if signal is not None else None,
        diagnosis=diagnosis.as_trace_payload() if diagnosis is not None else None,
        latency_ms=latency_ms,
    )


def _attempt_payload(
    index: int,
    applied: _Applied,
    *,
    latency_ms: float,
    usage: dict[str, int | bool | None] | None,
) -> dict[str, Any]:
    decision = applied.decision
    retrieval = applied.state.retrieval
    evaluation = applied.state.runtime_evaluation
    diagnosis = applied.state.diagnosis
    chunks = None
    if applied.evidence_relation in {EVIDENCE_REPLACED, EVIDENCE_WIDENED}:
        chunks = list(chunks_payload(retrieval))
    return attempt_record(
        index=index,
        action=decision.action,
        reason=decision.reason,
        trigger=decision.trigger,
        source=decision.source,
        attributed_class=decision.attributed_class,
        outcome_note=decision.outcome_note,
        top_k=retrieval.top_k,
        retrieved_doc_ids=[scored.chunk.doc_id for scored in retrieval.chunks],
        verification=(
            applied.verification.as_trace_payload() if applied.verification is not None else None
        ),
        answer=applied.state.generation.answer,
        answer_model=applied.state.generation.model,
        answer_relation=applied.answer_relation,
        evidence_relation=applied.evidence_relation,
        evaluation_source=applied.evaluation_source,
        executed=applied.executed,
        runtime_evaluation=evaluation.as_trace_payload() if evaluation is not None else None,
        diagnosis=diagnosis.as_trace_payload() if diagnosis is not None else None,
        latency_ms=latency_ms,
        rewritten_query=applied.rewritten_query,
        parameters=decision.parameters,
        search_query=applied.search_query,
        retrieved_chunks=chunks,
        probe_evaluation=(
            applied.probe_evaluation.as_trace_payload()
            if applied.probe_evaluation is not None
            else None
        ),
        usage=usage,
    )


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
        return _Applied(state, decision, None, None, None, None, executed=False)
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
        parameters={
            **(decision.parameters or {}),
            "from_k": state.retrieval.top_k,
            "to_k": nxt.retrieval.top_k,
        },
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
        answer_relation=ANSWER_GENERATED if generate else ANSWER_NONE,
        evidence_relation=EVIDENCE_WIDENED,
        evaluation_source=EVAL_JUDGE if nxt.runtime_evaluation is not None else EVAL_CARRIED,
        search_query=search_query,
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
        return _Applied(state, decision, None, None, None, None, executed=False)
    if decision.action == ABSTAIN:
        answer = _safe_answer(decision)
        abstained = QueryState(
            query=state.query,
            retrieval=state.retrieval,
            generation=GenerationResult(answer=answer, model="abstain"),
            runtime_evaluation=state.runtime_evaluation,
            diagnosis=state.diagnosis,
            retrieval_signal=state.retrieval_signal,
        )
        verification = None
        post_eval = state.runtime_evaluation
        if judge is not None:
            post_eval = judge.judge(
                question=query,
                answer=answer,
                retrieval=state.retrieval,
            )
            post_diag = diagnose_runtime(post_eval)
            if state.runtime_evaluation is not None:
                verification = verify_runtime(state.runtime_evaluation, post_eval)
            abstained = QueryState(
                query=state.query,
                retrieval=state.retrieval,
                generation=GenerationResult(answer=answer, model="abstain"),
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
            answer_relation=ANSWER_ABSTAINED,
            evidence_relation=EVIDENCE_UNCHANGED,
            evaluation_source=EVAL_JUDGE if judge is not None else EVAL_CARRIED,
        )
    if decision.action == REGENERATE:
        if not generate:
            return _Applied(state, decision, None, None, None, None, executed=False)
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
        return _Applied(
            next_state,
            decision,
            verification,
            previous_answer,
            None,
            None,
            answer_relation=ANSWER_GENERATED,
            evidence_relation=EVIDENCE_UNCHANGED,
            evaluation_source=EVAL_JUDGE if judge is not None else EVAL_CARRIED,
        )

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
        return _Applied(state, decision, None, None, None, None, executed=False)

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
            parameters=decision.parameters,
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
            answer_relation=ANSWER_GENERATED if generate else ANSWER_NONE,
            evidence_relation=EVIDENCE_REPLACED,
            evaluation_source=EVAL_JUDGE if generate and judge is not None else EVAL_PROBE,
            search_query=rewritten_query,
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
        if is_abstention(generation.answer) and not post_eval.evidence_sufficient:
            # Ending on an abstention with still-insufficient evidence is the
            # same outcome run_with_recovery records, and the null support flag
            # behind it is not a degradation.
            verification = Verification(outcome=STILL_FAILING, rationale=_ABSTAIN_RATIONALE)
        else:
            verification = verify_runtime(before, post_eval)

    next_decision = RecoveryDecision(
        action=REWRITE,
        reason=decision.reason,
        attributed_class=EVIDENCE_INSUFFICIENCY,
        source=decision.source,
        outcome_note=outcome_note,
        trigger=decision.trigger,
        parameters=decision.parameters,
    )
    next_state = QueryState(
        query=state.query,
        retrieval=probe.retrieval,
        generation=generation,
        runtime_evaluation=post_eval if post_eval is not None else state.runtime_evaluation,
        diagnosis=post_diag,
        retrieval_signal=state.retrieval_signal,
    )
    kept = kept_first_pass and before is not None
    return _Applied(
        next_state,
        next_decision,
        verification,
        previous_answer,
        rewritten_query,
        previous_retrieved_chunks,
        probe_evaluation=after,
        answer_relation=ANSWER_KEPT_PREVIOUS if kept else ANSWER_ABSTAINED,
        evidence_relation=EVIDENCE_REPLACED,
        evaluation_source=EVAL_CARRIED if kept or after is None else EVAL_PROBE,
        search_query=rewritten_query,
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
    raw_rejections = payload.get("span_rejections") or ()
    if not isinstance(raw_rejections, (list, tuple)):
        raw_rejections = ()
    return RuntimeEvaluation(
        evidence_sufficient=bool(payload.get("evidence_sufficient")),
        answer_supported=supported,
        sufficiency_rationale=str(payload.get("sufficiency_rationale") or ""),
        support_rationale=str(payload.get("support_rationale") or ""),
        judge=str(payload.get("judge") or ""),
        model=str(payload.get("model") or ""),
        span_rejections=tuple(str(item) for item in raw_rejections),
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

