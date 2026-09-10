"""Usage capture tests. No live API calls."""

from __future__ import annotations

from types import SimpleNamespace

from swrag.usage import capture_usage, record_chat, record_embedding


def test_record_is_a_noop_outside_capture() -> None:
    record_chat(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=9, completion_tokens=3)))
    record_embedding(SimpleNamespace(usage=SimpleNamespace(total_tokens=11)))


def test_capture_usage_counts_calls_and_tokens() -> None:
    with capture_usage() as counters:
        record_chat(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4)))
        record_chat(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1)))
        record_embedding(SimpleNamespace(usage=SimpleNamespace(total_tokens=7)))
    assert counters.snapshot() == {
        "chat_calls": 2,
        "embedding_calls": 1,
        "prompt_tokens": 12,
        "completion_tokens": 5,
        "embedding_tokens": 7,
    }
    record_chat(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=100)))
    assert counters.chat_calls == 2
