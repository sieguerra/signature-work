"""RAG quality metrics scored after a run: faithfulness, answer relevance, context relevance.

These are 0-1 scores for people reading a run, in the spirit of RAGAS. They are
separate from the runtime grounding judge: the loop never reads them, so they
cannot change what the loop decides. Like the judge, the scorer sees the
question, the retrieved passages and the answer, and never a gold answer.

One chat call per scored answer returns structured labels; the scores are
computed here from those labels, so every number traces back to a list the UI
can show (which claims were backed, which passages were on topic).

The scores are LLM-labelled and have not been checked against human labels.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from swrag.usage import record_chat

METRICS_VERSION = 1
_ABSTAIN_PREFIX = "i do not know"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_SYSTEM_PROMPT = """You label a retrieval-augmented answer so quality scores can be computed.
You see a question, numbered passages, and the generated answer. You have no
gold answer. Use only the passages as evidence; do not use outside knowledge.

Return a JSON object with exactly these keys:
- claims: list of objects {"claim": string, "supported": boolean, "passage": integer or null}.
  Split the answer into its separate factual claims (usually 1-5). A claim is
  supported only if a passage states it. "passage" is the number of the
  passage that states it, or null. Ignore citation brackets. If the answer
  makes no factual claim (for example it only says it does not know), return [].
- answer_relevance: integer 1-5. How directly the answer addresses what the
  question asks, regardless of whether it is correct. 5 = answers exactly
  what was asked; 3 = partly on topic or padded; 1 = does not address it.
- answer_relevance_reason: one short sentence.
- passages: list of objects {"passage": integer, "relevant": boolean}, one per
  passage. Relevant means the passage contains information that helps answer
  this question, not merely the same names or topic.

Do not invent passages or claims that are not in the answer."""


class _ChatClient(Protocol):
    chat: Any


@dataclass(frozen=True)
class ScoredAnswer:
    faithfulness: float | None
    answer_relevance: float | None
    context_relevance: float | None
    claims: tuple[dict[str, Any], ...]
    passages: tuple[dict[str, Any], ...]
    answer_relevance_reason: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "faithfulness": self.faithfulness,
            "answer_relevance": self.answer_relevance,
            "context_relevance": self.context_relevance,
            "claims": list(self.claims),
            "passages": list(self.passages),
            "answer_relevance_reason": self.answer_relevance_reason,
        }


def is_abstention(answer: str) -> bool:
    return answer.strip().lower().startswith(_ABSTAIN_PREFIX)


def score_answer(
    *,
    question: str,
    answer: str,
    chunks: list[dict[str, Any]],
    client: _ChatClient,
    model: str,
) -> ScoredAnswer:
    """Label one answer against its passages and compute the three scores."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(question, answer, chunks)},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    record_chat(response)
    labels = _parse(response.choices[0].message.content or "")
    return scores_from_labels(labels, answer=answer, chunks=chunks)


def scores_from_labels(
    labels: dict[str, Any],
    *,
    answer: str,
    chunks: list[dict[str, Any]],
) -> ScoredAnswer:
    """Turn the scorer's labels into 0-1 scores. Pure; tested without an API call."""
    abstained = is_abstention(answer) or not answer.strip()

    claims: list[dict[str, Any]] = []
    for item in labels.get("claims") or []:
        if not isinstance(item, dict) or not str(item.get("claim") or "").strip():
            continue
        passage = _passage_ref(item.get("passage"), len(chunks))
        claims.append(
            {
                "claim": str(item["claim"]).strip(),
                "supported": item.get("supported") is True,
                "chunk_id": chunks[passage - 1].get("chunk_id") if passage else None,
            }
        )
    if abstained:
        claims = []
    faithfulness = (
        sum(1 for claim in claims if claim["supported"]) / len(claims) if claims else None
    )

    relevance: float | None = None
    rating = labels.get("answer_relevance")
    if not abstained and isinstance(rating, (int, float)) and not isinstance(rating, bool):
        relevance = (min(5.0, max(1.0, float(rating))) - 1.0) / 4.0

    marks: dict[int, bool] = {}
    for item in labels.get("passages") or []:
        if not isinstance(item, dict):
            continue
        passage = _passage_ref(item.get("passage"), len(chunks))
        if passage:
            marks[passage] = item.get("relevant") is True
    passages = tuple(
        {"chunk_id": chunk.get("chunk_id"), "relevant": marks.get(index, False)}
        for index, chunk in enumerate(chunks, start=1)
    )
    context_relevance = (
        sum(1 for item in passages if item["relevant"]) / len(passages) if passages else None
    )

    return ScoredAnswer(
        faithfulness=faithfulness,
        answer_relevance=relevance,
        context_relevance=context_relevance,
        claims=tuple(claims),
        passages=passages,
        answer_relevance_reason="" if abstained else str(labels.get("answer_relevance_reason") or "").strip(),
    )


def score_trace(payload: dict[str, Any], *, client: _ChatClient, model: str) -> dict[str, Any]:
    """Score the final answer, and the first try too when the loop changed the answer."""
    question = str(payload.get("query") or "")
    final_chunks = _chunks(payload.get("retrieved_chunks"))
    result: dict[str, Any] = {
        "run_id": str(payload.get("run_id") or ""),
        "version": METRICS_VERSION,
        "scorer": "llm-quality-metrics",
        "model": model,
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "final": score_answer(
            question=question,
            answer=str(payload.get("answer") or ""),
            chunks=final_chunks,
            client=client,
            model=model,
        ).as_payload(),
        "first": None,
    }
    previous = payload.get("previous_answer")
    if previous is not None and payload.get("parent_run_id") is None and _was_recovered(payload):
        first_chunks = _chunks(payload.get("previous_retrieved_chunks")) or final_chunks
        result["first"] = score_answer(
            question=question,
            answer=str(previous),
            chunks=first_chunks,
            client=client,
            model=model,
        ).as_payload()
    return result


def _was_recovered(payload: dict[str, Any]) -> bool:
    if payload.get("recovery_attempts"):
        return True
    recovery = payload.get("recovery") if isinstance(payload.get("recovery"), dict) else {}
    return payload.get("recovery_status") != "proposed" and recovery.get("action") not in (None, "accept")


def _chunks(value: object) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)] if isinstance(value, list) else []


def _passage_ref(value: object, count: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    index = int(value)
    return index if 1 <= index <= count else None


def _user_prompt(question: str, answer: str, chunks: list[dict[str, Any]]) -> str:
    passages = "\n\n".join(
        f"[{index}] {chunk.get('title') or chunk.get('doc_id') or ''}\n{chunk.get('text') or ''}"
        for index, chunk in enumerate(chunks, start=1)
    ) or "(no passages)"
    generated = answer.strip() or "(no answer)"
    return f"Question:\n{question}\n\nPassages:\n{passages}\n\nGenerated answer:\n{generated}"


def _parse(raw: str) -> dict[str, Any]:
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"quality scorer returned invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("quality scorer JSON must be an object")
    return payload
