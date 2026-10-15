"""Public demo mode: what a shared deployment may and may not do.

Turned on with ``GROUNDLOOP_DEMO=1``. A public deployment is one shared
server, so it pins the active system, refuses every change (systems,
documents, config, keys, deletions, paid quality scoring), caps live runs per
day, and keeps local details (absolute paths, the provider endpoint) out of
responses. The research code is untouched; this only gates the HTTP surface.
"""

from __future__ import annotations

import os
import threading
from datetime import date
from typing import Any

DEFAULT_DAILY_RUNS = 25

# (method, path, exact?) pairs a public visitor may not call.
_BLOCKED: tuple[tuple[str, str, bool], ...] = (
    ("POST", "/api/corpus", True),
    ("POST", "/api/projects", True),
    ("POST", "/api/projects/", False),
    ("PATCH", "/api/projects/", False),
    ("DELETE", "/api/projects/", False),
    ("GET", "/api/projects/", False),
    ("POST", "/api/documents", True),
    ("DELETE", "/api/documents/", False),
    ("DELETE", "/api/traces", True),
    ("DELETE", "/api/traces/", False),
    ("POST", "/api/traces/", False),
    # External evaluations call the judge (model money) and write traces.
    ("POST", "/api/v1/", False),
)

_RUNS: tuple[tuple[str, bool], ...] = (
    ("/api/runs", True),
    ("/api/runs/stream", True),
    ("/api/runs/", False),
)

_PRIVATE_KEYS = {"corpus_dir", "traces_dir", "base_url"}

READ_ONLY_DETAIL = "This is a public demo, so it is read-only. Run Groundloop locally to change systems or data."
GENERIC_ERROR = "The run could not finish. Please try again in a moment."


def demo_enabled() -> bool:
    return os.environ.get("GROUNDLOOP_DEMO", "").strip().lower() in {"1", "true", "yes", "on"}


def _matches(path: str, prefix: str, exact: bool) -> bool:
    return path == prefix if exact else path.startswith(prefix)


def is_blocked(method: str, path: str) -> bool:
    return any(method == m and _matches(path, p, exact) for m, p, exact in _BLOCKED)


def is_run(method: str, path: str) -> bool:
    return method == "POST" and any(_matches(path, p, exact) for p, exact in _RUNS)


class RunBudget:
    """Live runs allowed per calendar day (server time). In memory: a restart resets it."""

    def __init__(self, per_day: int) -> None:
        self.per_day = max(0, per_day)
        self._day = date.today()
        self._used = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> RunBudget:
        raw = os.environ.get("GROUNDLOOP_DAILY_RUNS", "")
        try:
            per_day = int(raw) if raw.strip() else DEFAULT_DAILY_RUNS
        except ValueError:
            per_day = DEFAULT_DAILY_RUNS
        return cls(per_day)

    def _roll(self) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._used = 0

    def take(self) -> bool:
        with self._lock:
            self._roll()
            if self._used >= self.per_day:
                return False
            self._used += 1
            return True

    def give_back(self) -> None:
        """Return a run that was rejected before it did any work."""
        with self._lock:
            self._used = max(0, self._used - 1)

    def left(self) -> int:
        with self._lock:
            self._roll()
            return max(0, self.per_day - self._used)


def scrub(value: Any, root: str | None = None) -> Any:
    """Drop private keys and make absolute paths under ``root`` relative."""
    if isinstance(value, dict):
        return {key: scrub(item, root) for key, item in value.items() if key not in _PRIVATE_KEYS}
    if isinstance(value, list):
        return [scrub(item, root) for item in value]
    if isinstance(value, str) and root and root in value:
        return value.replace(root.rstrip("/") + "/", "").replace(root, ".")
    return value
