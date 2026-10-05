"""Optional OpenAI usage counters for experiment cost reporting.

Wrappers record into a contextvar so tests and one-off CLI runs pay nothing
unless a caller opens :func:`capture_usage`. Token fields are 0 when a proxy
omits ``usage`` on the response.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Iterator


@dataclass
class UsageCounters:
    """Mutable totals for one captured region (one question, one condition, …)."""

    chat_calls: int = 0
    embedding_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0

    def snapshot(self) -> dict[str, int]:
        return {key: int(value) for key, value in asdict(self).items()}


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


def peek_usage() -> dict[str, int] | None:
    """Totals for the active capture, or None when nobody is recording."""
    counters = _CURRENT.get()
    if counters is None:
        return None
    return counters.snapshot()


def usage_delta(
    before: dict[str, int] | None,
    after: dict[str, int] | None,
) -> dict[str, int] | None:
    """Token and call counts incurred between two peeks. None if uncaptured."""
    if before is None or after is None:
        return None
    keys = (
        "chat_calls",
        "embedding_calls",
        "prompt_tokens",
        "completion_tokens",
        "embedding_tokens",
    )
    return {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in keys}


def record_chat(response: object) -> None:
    counters = _CURRENT.get()
    if counters is None:
        return
    counters.chat_calls += 1
    usage = getattr(response, "usage", None)
    if usage is None:
        return
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
    counters.embedding_tokens += _token_count(usage, "total_tokens", "prompt_tokens")


def _token_count(usage: object, *names: str) -> int:
    for name in names:
        value = getattr(usage, name, None)
        if value:
            return int(value)
    return 0
