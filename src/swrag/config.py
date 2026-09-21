"""Model backend configuration.

ADR 003 requires the provider to be swappable and recorded in every trace, so
benchmark results can state which backend produced them. A reseller proxy and
official OpenAI can both serve a model called ``gpt-4o-mini``; only the endpoint
distinguishes them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_BASE_URL = "https://api.openai.com/v1"
ALLOWED_CHAT_MODELS = frozenset(
    {
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
    }
)


@dataclass(frozen=True)
class ProviderConfig:
    """Which models to call, and where."""

    chat_model: str = DEFAULT_CHAT_MODEL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    base_url: str = OPENAI_BASE_URL
    api_key_present: bool = False

    @property
    def is_official_openai(self) -> bool:
        return self.base_url.rstrip("/") == OPENAI_BASE_URL.rstrip("/")

    def as_trace_payload(self) -> dict[str, object]:
        """Backend fields recorded in a trace.

        These are the *configured* values. The ``model`` and ``embedding_model``
        fields on the trace itself record what actually ran, which differs when
        a fake embedder is injected for API-free runs.

        The API key is never included, only whether one was present.
        """
        return {
            "base_url": self.base_url,
            "official_openai": self.is_official_openai,
            "configured_chat_model": self.chat_model,
            "configured_embedding_model": self.embedding_model,
            "api_key_present": self.api_key_present,
        }


def load_provider_config() -> ProviderConfig:
    """Read backend settings from the environment."""
    return ProviderConfig(
        chat_model=os.environ.get("OPENAI_CHAT_MODEL") or DEFAULT_CHAT_MODEL,
        embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL,
        base_url=os.environ.get("OPENAI_BASE_URL") or OPENAI_BASE_URL,
        api_key_present=bool(os.environ.get("OPENAI_API_KEY")),
    )
