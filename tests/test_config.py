"""Provider configuration tests. No API calls."""

from __future__ import annotations

import pytest

from swrag.config import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    OPENAI_BASE_URL,
    load_provider_config,
)

_ENV_VARS = (
    "OPENAI_CHAT_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_point_at_official_openai() -> None:
    config = load_provider_config()
    assert config.chat_model == DEFAULT_CHAT_MODEL
    assert config.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert config.base_url == OPENAI_BASE_URL
    assert config.is_official_openai
    assert not config.api_key_present


def test_env_overrides_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "some-other-model")
    monkeypatch.setenv("OPENAI_API_KEY", "unused-in-this-test")

    config = load_provider_config()
    assert config.base_url == "https://example.invalid/v1"
    assert config.chat_model == "some-other-model"
    assert config.api_key_present
    assert not config.is_official_openai


def test_empty_env_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # An unset key in .env reads as "" and must not become the base URL.
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "")

    config = load_provider_config()
    assert config.base_url == OPENAI_BASE_URL
    assert config.chat_model == DEFAULT_CHAT_MODEL


def test_trailing_slash_still_counts_as_official(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", OPENAI_BASE_URL + "/")
    assert load_provider_config().is_official_openai


def test_trace_payload_never_contains_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-appear")
    payload = load_provider_config().as_trace_payload()

    assert "sk-must-not-appear" not in str(payload)
    assert payload["api_key_present"] is True
    assert payload["base_url"] == OPENAI_BASE_URL
