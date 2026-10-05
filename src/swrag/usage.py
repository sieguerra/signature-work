"""Optional OpenAI usage counters for experiment cost reporting.

Wrappers record into a contextvar so tests and one-off CLI runs pay nothing
unless a caller opens :func:`capture_usage`. Token fields are 0 when a proxy
omits ``usage`` on the response.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass
class UsageCounters:
    """Mutable totals for one captured region (one question, one condition, …)."""

    chat_calls: int = 0
    embedding_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0
    # Responses that actually carried a usage object. Not part of snapshot().
    usage_observations: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "chat_calls": int(self.chat_calls),
            "embedding_calls": int(self.embedding_calls),
            "prompt_tokens": int(self.prompt_tokens),
            "completion_tokens": int(self.completion_tokens),
            "embedding_tokens": int(self.embedding_tokens),
        }


_CURRENT: ContextVar[UsageCounters | None] = ContextVar("swrag_usage", default=None)


@contextmanager
def capture_usage() -> Iterator[UsageCounters]:
    """Collect chat/embedding call counts and tokens until the block exits."""
    counters = UsageCounters()
    token = _CURRENT.set(counters)
    try:
        yield counters
    finally:
        _CURRENT.reset(token)


_COUNT_KEYS = (
    "chat_calls",
    "embedding_calls",
    "prompt_tokens",
    "completion_tokens",
    "embedding_tokens",
)


def peek_usage() -> dict[str, int] | None:
    """Totals for the active capture, or None when nobody is recording."""
    counters = _CURRENT.get()
    if counters is None:
        return None
    return counters.snapshot()


def usage_checkpoint() -> dict[str, int] | None:
    """Peek plus how many responses included a provider usage object."""
    counters = _CURRENT.get()
    if counters is None:
        return None
    point = counters.snapshot()
    point["usage_observations"] = int(counters.usage_observations)
    return point


def usage_for_trace() -> dict[str, int | bool | None] | None:
    """Usage worth persisting on a trace.

    None when capture is closed, or when it is open but no chat or embedding
    call was recorded. A call whose response omitted ``usage`` keeps the call
    count and sets token fields to null with ``tokens_observed`` false. A
    zero token count is written only when a usage object was actually seen.
    """
    point = usage_checkpoint()
    if point is None:
        return None
    if point["chat_calls"] == 0 and point["embedding_calls"] == 0:
        return None
    observed = int(point["usage_observations"]) > 0
    if not observed:
        return {
            "chat_calls": point["chat_calls"],
            "embedding_calls": point["embedding_calls"],
            "prompt_tokens": None,
            "completion_tokens": None,
            "embedding_tokens": None,
            "tokens_observed": False,
        }
    payload: dict[str, int | bool | None] = {key: point[key] for key in _COUNT_KEYS}
    payload["tokens_observed"] = True
    return payload


def usage_delta(
    before: dict[str, int] | None,
    after: dict[str, int] | None,
) -> dict[str, int | bool | None] | None:
    """Counts incurred between two checkpoints. None if uncaptured or empty.

    Pass :func:`usage_checkpoint` values. An empty window is omitted rather
    than stored as zeros. Token fields stay null when the window's calls did
    not include a provider usage object.
    """
    if before is None or after is None:
        return None
    delta = {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in _COUNT_KEYS}
    if all(value == 0 for value in delta.values()):
        return None
    observations = int(after.get("usage_observations", 0)) - int(before.get("usage_observations", 0))
    if observations <= 0:
        return {
            "chat_calls": delta["chat_calls"],
            "embedding_calls": delta["embedding_calls"],
            "prompt_tokens": None,
            "completion_tokens": None,
            "embedding_tokens": None,
            "tokens_observed": False,
        }
    payload: dict[str, int | bool | None] = dict(delta)
    payload["tokens_observed"] = True
    return payload


def record_chat(response: object) -> None:
    counters = _CURRENT.get()
    if counters is None:
        return
    counters.chat_calls += 1
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    counters.usage_observations += 1
    counters.prompt_tokens += _token_count(usage, "prompt_tokens", "input_tokens")
    counters.completion_tokens += _token_count(usage, "completion_tokens", "output_tokens")


def record_embedding(response: object) -> None:
    counters = _CURRENT.get()
    if counters is None:
        return
    counters.embedding_calls += 1
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    counters.usage_observations += 1
    counters.embedding_tokens += _token_count(usage, "total_tokens", "prompt_tokens")


def _token_count(usage: object, *names: str) -> int:
    for name in names:
        value = getattr(usage, name, None)
        if value:
            return int(value)
    return 0
