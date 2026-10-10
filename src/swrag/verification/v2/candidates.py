"""Shadow verifiers. None of these are called by the recovery loop.

Candidates
----------
surface
    Negative control. Answer text alone cannot separate a correct rewrite
    from a different wrong answer, so this candidate always returns uncertain.
coverage
    Deterministic. Checkable facts must occur in the evidence already stored
    on the trace, and content-token overlap must clear a frozen threshold.
    No gold, no model.
pointwise
    Two independent rubric judgments, one for each state, then a deterministic
    rank comparison. The model never sees both answers in one prompt, so this
    candidate has no presentation order to swap.
pairwise
    One comparison prompt, run in both orders. Disagreement is uncertain.
    The order that agrees is not silently preferred.

A model failure, invalid payload, or unknown label is ``unavailable``. It is
never rewritten as unchanged or still_failing.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from swrag.evaluation.llm_judge import facts_missing_from_evidence
from swrag.types import Chunk, RetrievalResult, ScoredChunk
from swrag.verification.v2.cache import cache_key, read_cache, write_cache
from swrag.verification.v2.payload import assert_no_gold, verifier_view
from swrag.verification.v2.protocol import (
    COVERAGE_GROUNDED,
    COVERAGE_MIN_CONTENT_TOKENS,
    CLASSES,
)
from swrag.verification.v2.transitions import Transition

PARSER_VERSION = "1"
TEMPERATURE = 0.0

SURFACE_VERSION = "surface-2026-10-06"
COVERAGE_VERSION = "coverage-2026-10-06"
POINTWISE_VERSION = "pointwise-2026-10-06"
PAIRWISE_VERSION = "pairwise-2026-10-06"

POINTWISE_SYSTEM = """You judge one retrieval-augmented answer against the evidence supplied with it.
You have no gold answer and no other answer to compare. Do not use outside knowledge.
Do not reward length, style, eloquence, or a confident tone.

Return a JSON object with exactly these keys:
- evidence_can_answer: boolean. True only if the evidence text states the specific fact the question asks for.
- claims_supported: one of "supported", "partial", "unsupported", "no_claims".
  "no_claims" is for an abstention that asserts no fact.
  "supported" means every factual claim is stated in the evidence.
- addresses_question: boolean. True if the response answers the question that was asked, or properly abstains.
- abstention: boolean. True if the response declines to answer.
- unsupported_specifics: boolean. True if the response adds a number, date, name, or other specific fact that the evidence does not state.
- rationale_codes: array of short snake_case strings. Diagnostic only.

Do not add other keys. Do not wrap the JSON in markdown."""

PAIRWISE_SYSTEM = """You compare two retrieval-augmented responses to the same question.
You have no gold answer. Do not use outside knowledge.
Do not reward length, style, eloquence, or a confident tone.
If the two response texts are the same, do not prefer the one with more evidence.

Judge only these criteria:
1. Does the response answer from its own evidence, or properly abstain when that evidence cannot answer?
2. Are its factual claims stated in its own evidence?
3. Does it avoid specific facts that its evidence does not state?
4. An abstention is better than an invented answer, and worse than a supported answer to an answerable question.

Return a JSON object with exactly these keys:
- relation: one of "first_better", "second_better", "equivalent", "both_insufficient".
  "equivalent" means both are acceptable, or they are the same response.
  "both_insufficient" means both fail the criteria above.
- rationale_codes: array of short snake_case strings. Diagnostic only.

Do not add other keys. Do not wrap the JSON in markdown."""

_STOPWORDS = frozenset(
    "a an the of to and in on for is are was were be at by with from that this it or as not do does based retrieved documents".split()
)
_ABSTAIN_PREFIX = "i do not know"


class ParseError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ChatClient(Protocol):
    def complete(self, *, system: str, user: str) -> "Completion":
        """Return the model text. Raise TimeoutError or a rate-limit error as itself."""


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class Prediction:
    candidate: str
    prompt_version: str
    model: str | None
    status: str
    outcome: str | None
    rationale_codes: tuple[str, ...] = ()
    diagnostic: str | None = None
    error: str | None = None
    model_calls: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float = 0.0
    position_consistent: bool | None = None
    signals: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "status": self.status,
            "outcome": self.outcome,
            "rationale_codes": list(self.rationale_codes),
            "diagnostic": self.diagnostic,
            "error": self.error,
            "model_calls": self.model_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": self.latency_ms,
            "position_consistent": self.position_consistent,
            "signals": self.signals,
        }


def label_from_ranks(
    before_answer: str,
    after_answer: str,
    before_rank: int,
    after_rank: int,
) -> tuple[str | None, str]:
    """Map two ranks to a transition class.

    Identical answer text whose ranks disagree is uncertain: the words the
    user saw did not change, so a rank change is not an improvement claim.
    Equal rank 0 remains a failure. Equal rank above 0 is unchanged.
    """
    if _normalize(before_answer) == _normalize(after_answer) and before_rank != after_rank:
        return None, "identical_text_rank_conflict"
    if after_rank > before_rank:
        return "improved", "rank_rose"
    if after_rank < before_rank:
        return "degraded", "rank_fell"
    if after_rank == 0:
        return "still_failing", "equal_failure"
    return "unchanged", "equal_acceptable"


class SurfaceVerifier:
    """Negative control. Text identity is not a quality judgment."""

    name = "surface"
    prompt_version = SURFACE_VERSION
    model = None

    def predict(self, transition: Transition) -> Prediction:
        view = verifier_view(transition)
        before = _normalize(view["before"]["answer"])
        after = _normalize(view["after"]["answer"])
        if before == after:
            code = "identical_text"
        elif _abstains(view["before"]["answer"]) != _abstains(view["after"]["answer"]):
            code = "abstention_changed"
        else:
            code = "text_changed"
        return _decided_like(
            self,
            status="uncertain",
            outcome=None,
            codes=(code,),
            signals={"abstention_origin_after": view["abstention_origin_after"]},
        )


class CoverageVerifier:
    """Fact-span and token-coverage comparison. Frozen threshold, no model."""

    name = "coverage"
    prompt_version = COVERAGE_VERSION
    model = None

    def predict(self, transition: Transition) -> Prediction:
        view = verifier_view(transition)
        before_rank = _coverage_rank(view["question"], view["before"])
        after_rank = _coverage_rank(view["question"], view["after"])
        if before_rank is None or after_rank is None:
            return _decided_like(
                self,
                status="unavailable",
                outcome=None,
                codes=("evidence_unavailable",),
                error="evidence_unavailable",
            )
        outcome, code = label_from_ranks(
            view["before"]["answer"],
            view["after"]["answer"],
            before_rank,
            after_rank,
        )
        if outcome is None:
            return _decided_like(
                self,
                status="uncertain",
                outcome=None,
                codes=(code,),
                signals={"before_rank": before_rank, "after_rank": after_rank},
            )
        return _decided_like(
            self,
            status="decided",
            outcome=outcome,
            codes=(code,),
            signals={"before_rank": before_rank, "after_rank": after_rank},
        )


class PointwiseVerifier:
    """Independent rubric scores, then the frozen rank comparison."""

    name = "pointwise"
    prompt_version = POINTWISE_VERSION

    def __init__(self, client: ChatClient, *, model: str, cache_dir: Any = None) -> None:
        self.client = client
        self.model = model
        self.cache_dir = cache_dir

    def predict(self, transition: Transition) -> Prediction:
        view = verifier_view(transition)
        if not view["before"]["evidence_known"] or not view["after"]["evidence_known"]:
            return _unavailable(self, "evidence_unavailable")
        try:
            before, before_usage = self._judge_state(view, "before")
            after, after_usage = self._judge_state(view, "after")
        except Exception as error:
            return _from_exception(self, error)
        before_rank = _pointwise_rank(before)
        after_rank = _pointwise_rank(after)
        outcome, code = label_from_ranks(
            view["before"]["answer"],
            view["after"]["answer"],
            before_rank,
            after_rank,
        )
        usage = _add_usage(before_usage, after_usage)
        if outcome is None:
            return _model_prediction(
                self,
                status="uncertain",
                outcome=None,
                codes=(code,),
                usage=usage,
                signals={"before_rank": before_rank, "after_rank": after_rank},
                diagnostic=_diagnostic(before, after),
            )
        return _model_prediction(
            self,
            status="decided",
            outcome=outcome,
            codes=(code,),
            usage=usage,
            signals={"before_rank": before_rank, "after_rank": after_rank},
            diagnostic=_diagnostic(before, after),
        )

    def _judge_state(self, view: dict[str, Any], side: str) -> tuple[dict[str, Any], Completion]:
        user = _single_state_prompt(view["question"], view[side])
        assert_no_gold({"user": user})
        completion = _cached_complete(
            self,
            system=POINTWISE_SYSTEM,
            user=user,
            order=side,
            view=view,
        )
        parsed = _parse_object(completion.text)
        _require_keys(
            parsed,
            ("evidence_can_answer", "claims_supported", "addresses_question", "abstention", "unsupported_specifics"),
        )
        if parsed["claims_supported"] not in {"supported", "partial", "unsupported", "no_claims"}:
            raise ParseError("unknown_label")
        for key in ("evidence_can_answer", "addresses_question", "abstention", "unsupported_specifics"):
            if not isinstance(parsed[key], bool):
                raise ParseError("invalid_json")
        return parsed, completion


class PairwiseVerifier:
    """Both presentation orders. Disagreement is uncertain."""

    name = "pairwise"
    prompt_version = PAIRWISE_VERSION

    def __init__(self, client: ChatClient, *, model: str, cache_dir: Any = None) -> None:
        self.client = client
        self.model = model
        self.cache_dir = cache_dir

    def predict(self, transition: Transition) -> Prediction:
        view = verifier_view(transition)
        if not view["before"]["evidence_known"] or not view["after"]["evidence_known"]:
            return _unavailable(self, "evidence_unavailable")
        try:
            first, first_usage = self._judge_order(view, "before_first")
            second, second_usage = self._judge_order(view, "after_first")
        except Exception as error:
            return _from_exception(self, error)
        usage = _add_usage(first_usage, second_usage)
        if first != second:
            return _model_prediction(
                self,
                status="uncertain",
                outcome=None,
                codes=("position_inconsistent",),
                usage=usage,
                position_consistent=False,
                signals={"before_first": first, "after_first": second},
            )
        return _model_prediction(
            self,
            status="decided",
            outcome=first,
            codes=("orders_agree",),
            usage=usage,
            position_consistent=True,
            signals={"before_first": first, "after_first": second},
        )

    def _judge_order(self, view: dict[str, Any], order: str) -> tuple[str, Completion]:
        if order == "before_first":
            left, right = view["before"], view["after"]
        else:
            left, right = view["after"], view["before"]
        user = _pair_prompt(view["question"], left, right)
        assert_no_gold({"user": user})
        completion = _cached_complete(
            self,
            system=PAIRWISE_SYSTEM,
            user=user,
            order=order,
            view=view,
        )
        parsed = _parse_object(completion.text)
        relation = parsed.get("relation")
        mapped = _map_relation(relation, order)
        return mapped, completion


def _coverage_rank(question: str, state: dict[str, Any]) -> int | None:
    if not state.get("evidence_known"):
        return None
    answer = str(state.get("answer") or "")
    chunks = state.get("evidence") or []
    if _abstains(answer) and not _missing_facts(question, answer, chunks):
        return 1
    if _missing_facts(question, answer, chunks):
        return 0
    tokens = _content_tokens(answer)
    if len(tokens) < COVERAGE_MIN_CONTENT_TOKENS:
        return 0
    if _coverage(tokens, chunks) >= COVERAGE_GROUNDED:
        return 2
    return 0


def _pointwise_rank(parsed: dict[str, Any]) -> int:
    if parsed["abstention"]:
        if parsed["unsupported_specifics"] or parsed["evidence_can_answer"]:
            return 0
        return 1
    supported = (
        parsed["claims_supported"] == "supported"
        and parsed["addresses_question"]
        and not parsed["unsupported_specifics"]
        and parsed["evidence_can_answer"]
    )
    return 2 if supported else 0


def _map_relation(relation: object, order: str) -> str:
    if relation == "equivalent":
        return "unchanged"
    if relation == "both_insufficient":
        return "still_failing"
    if relation == "first_better":
        return "degraded" if order == "before_first" else "improved"
    if relation == "second_better":
        return "improved" if order == "before_first" else "degraded"
    raise ParseError("unknown_label")


def _missing_facts(question: str, answer: str, chunks: list[dict]) -> bool:
    if not chunks:
        return bool(answer.strip()) and not _abstains(answer)
    retrieval = _retrieval(question, chunks)
    return bool(facts_missing_from_evidence(answer, retrieval))


def _coverage(tokens: list[str], chunks: list[dict]) -> float:
    evidence_tokens = set()
    for chunk in chunks:
        evidence_tokens.update(_content_tokens(str(chunk.get("text") or "")))
        evidence_tokens.update(_content_tokens(str(chunk.get("title") or "")))
    if not tokens:
        return 0.0
    return sum(1 for token in tokens if token in evidence_tokens) / len(tokens)


def _content_tokens(text: str) -> list[str]:
    return [
        token
        for token in _normalize(text).split()
        if len(token) > 2 and token not in _STOPWORDS
    ]


def _retrieval(question: str, chunks: list[dict]) -> RetrievalResult:
    scored: list[ScoredChunk] = []
    for index, row in enumerate(chunks):
        text = str(row.get("text") or "")
        scored.append(
            ScoredChunk(
                chunk=Chunk(
                    chunk_id=str(row.get("chunk_id") or f"c{index}"),
                    doc_id=str(row.get("doc_id") or ""),
                    title=str(row.get("title") or ""),
                    text=text,
                    start_char=0,
                    end_char=len(text),
                    page=row.get("page") if isinstance(row.get("page"), int) else None,
                ),
                score=float(row["score"]) if isinstance(row.get("score"), (int, float)) else 0.0,
            )
        )
    return RetrievalResult(
        query=question,
        chunks=tuple(scored),
        top_k=len(scored),
        embedding_model="trace",
    )


def _single_state_prompt(question: str, state: dict[str, Any]) -> str:
    return (
        f"Question:\n{question}\n\n"
        f"Evidence:\n{_evidence_block(state)}\n\n"
        f"Response:\n{state.get('answer') or '(empty)'}\n\n"
        f"Schema notes (do not treat a probe or a carried flag as a new answer judgment):\n"
        f"answer_relation={state.get('answer_relation')}\n"
        f"evidence_relation={state.get('evidence_relation')}\n"
        f"evaluation_source={state.get('evaluation_source')}"
    )


def _pair_prompt(question: str, first: dict[str, Any], second: dict[str, Any]) -> str:
    return (
        f"Question:\n{question}\n\n"
        f"Response 1:\n{_state_block(first)}\n\n"
        f"Response 2:\n{_state_block(second)}"
    )


def _state_block(state: dict[str, Any]) -> str:
    return (
        f"answer_relation={state.get('answer_relation')} "
        f"evidence_relation={state.get('evidence_relation')} "
        f"evaluation_source={state.get('evaluation_source')}\n"
        f"Evidence:\n{_evidence_block(state)}\n"
        f"Answer:\n{state.get('answer') or '(empty)'}"
    )


def _evidence_block(state: dict[str, Any]) -> str:
    chunks = state.get("evidence") or []
    if not chunks:
        return "(no evidence stored)"
    parts = []
    for chunk in chunks:
        title = chunk.get("title") or ""
        text = chunk.get("text") or ""
        parts.append(f"{title}\n{text}".strip())
    return "\n\n".join(parts)


def _cached_complete(verifier: Any, *, system: str, user: str, order: str, view: dict[str, Any]) -> Completion:
    key = cache_key(
        candidate=verifier.name,
        prompt_version=verifier.prompt_version,
        parser_version=PARSER_VERSION,
        model=verifier.model,
        temperature=TEMPERATURE,
        view=view,
        order=order,
    )
    cached = read_cache(verifier.cache_dir, key)
    if cached is not None and cached.get("prompt_version") == verifier.prompt_version:
        return Completion(
            text=str(cached.get("text") or ""),
            prompt_tokens=cached.get("prompt_tokens"),
            completion_tokens=cached.get("completion_tokens"),
            latency_ms=float(cached.get("latency_ms") or 0.0),
        )
    started = time.perf_counter()
    completion = verifier.client.complete(system=system, user=user)
    elapsed = (time.perf_counter() - started) * 1000.0
    if completion.latency_ms <= 0:
        completion = Completion(
            text=completion.text,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            latency_ms=elapsed,
        )
    write_cache(
        verifier.cache_dir,
        key,
        {
            "prompt_version": verifier.prompt_version,
            "model": verifier.model,
            "order": order,
            "text": completion.text,
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
            "latency_ms": completion.latency_ms,
        },
    )
    return completion


def _parse_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ParseError("empty")
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            if _refusal(stripped):
                raise ParseError("refusal")
            raise ParseError("invalid_json")
        try:
            value = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as error:
            raise ParseError("invalid_json") from error
    if not isinstance(value, dict):
        raise ParseError("invalid_json")
    return value


def _require_keys(payload: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if key not in payload:
            raise ParseError("invalid_json")


def _refusal(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in ("i can't", "i cannot", "i won’t", "i won't", "refuse"))


def _from_exception(verifier: Any, error: Exception) -> Prediction:
    if isinstance(error, ParseError):
        code = error.code
    elif isinstance(error, TimeoutError):
        code = "timeout"
    else:
        message = str(error).lower()
        if "rate limit" in message or "rate_limit" in message or "429" in message:
            code = "rate_limit"
        else:
            code = "api_error"
    return _unavailable(verifier, code)


def _unavailable(verifier: Any, code: str) -> Prediction:
    return _decided_like(verifier, status="unavailable", outcome=None, codes=(code,), error=code)


def _diagnostic(before: dict[str, Any], after: dict[str, Any]) -> str:
    before_codes = before.get("rationale_codes") or []
    after_codes = after.get("rationale_codes") or []
    return "before=" + ",".join(str(item) for item in before_codes) + " after=" + ",".join(
        str(item) for item in after_codes
    )


def _add_usage(left: Completion, right: Completion) -> Completion:
    return Completion(
        text="",
        prompt_tokens=_sum_optional(left.prompt_tokens, right.prompt_tokens),
        completion_tokens=_sum_optional(left.completion_tokens, right.completion_tokens),
        latency_ms=left.latency_ms + right.latency_ms,
    )


def _sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return (left or 0) + (right or 0)


def _model_prediction(
    verifier: Any,
    *,
    status: str,
    outcome: str | None,
    codes: tuple[str, ...],
    usage: Completion,
    signals: dict[str, Any] | None = None,
    diagnostic: str | None = None,
    position_consistent: bool | None = None,
) -> Prediction:
    if outcome is not None and outcome not in CLASSES:
        return _unavailable(verifier, "unknown_label")
    return Prediction(
        candidate=verifier.name,
        prompt_version=verifier.prompt_version,
        model=verifier.model,
        status=status,
        outcome=outcome,
        rationale_codes=codes,
        diagnostic=diagnostic,
        model_calls=2,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=usage.latency_ms,
        position_consistent=position_consistent,
        signals=signals or {},
    )


def _decided_like(
    verifier: Any,
    *,
    status: str,
    outcome: str | None,
    codes: tuple[str, ...],
    error: str | None = None,
    signals: dict[str, Any] | None = None,
) -> Prediction:
    return Prediction(
        candidate=verifier.name,
        prompt_version=verifier.prompt_version,
        model=getattr(verifier, "model", None),
        status=status,
        outcome=outcome,
        rationale_codes=codes,
        error=error,
        signals=signals or {},
    )


def _abstains(answer: str) -> bool:
    return answer.strip().lower().startswith(_ABSTAIN_PREFIX)


def _normalize(text: str) -> str:
    lowered = text.lower()
    without_punctuation = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(without_punctuation.split())
