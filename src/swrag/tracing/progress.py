"""Per-stage timing and live progress for one run.

A run opens a ``Recorder`` with ``recording()``. Pipeline code marks its
stages with ``stage("retrieve")`` and so on. Outside a recording those calls
do nothing, so the pipeline, the experiment runner, and the tests behave as
before.

The recorder keeps every finished stage with its start offset and duration
from the start of the run, which ``write_run`` stores on the trace as
``stage_timings``. An optional listener receives each start and end as it
happens, which is how the streaming endpoint reports live progress.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from typing import Any

STAGES = ("retrieve", "generate", "judge", "diagnose", "recover", "verify")

Listener = Callable[[dict[str, Any]], None]

_current: ContextVar[Recorder | None] = ContextVar("swrag_progress", default=None)


class Recorder:
    def __init__(self, listener: Listener | None = None) -> None:
        self._t0 = time.perf_counter()
        self._listener = listener
        self._attempt: int | None = None
        self.stages: list[dict[str, Any]] = []

    def _offset_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000, 1)

    def _emit(self, event: dict[str, Any]) -> None:
        if self._listener is None:
            return
        try:
            self._listener(event)
        except Exception:
            # A broken listener (a closed stream) must never fail the run.
            self._listener = None

    @contextmanager
    def stage(self, name: str, **meta: Any) -> Iterator[None]:
        started = self._offset_ms()
        base = {"stage": name, "attempt": self._attempt, **meta}
        self._emit({"type": "stage_start", **base, "started_ms": started})
        status = "ok"
        try:
            yield
        except BaseException:
            status = "error"
            raise
        finally:
            ended = self._offset_ms()
            record = {**base, "started_ms": started, "duration_ms": round(ended - started, 1), "status": status}
            self.stages.append(record)
            self._emit({"type": "stage_end", **record})

    @contextmanager
    def attempt(self, index: int) -> Iterator[None]:
        previous = self._attempt
        self._attempt = index
        try:
            yield
        finally:
            self._attempt = previous

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self.stages)


@contextmanager
def recording(listener: Listener | None = None) -> Iterator[Recorder]:
    recorder = Recorder(listener)
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


def stage(name: str, **meta: Any):
    recorder = _current.get()
    return recorder.stage(name, **meta) if recorder is not None else nullcontext()


def attempt(index: int):
    recorder = _current.get()
    return recorder.attempt(index) if recorder is not None else nullcontext()


def snapshot() -> tuple[dict[str, Any], ...] | None:
    recorder = _current.get()
    return recorder.snapshot() if recorder is not None else None
