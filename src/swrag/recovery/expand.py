"""Widen top_k and retrieve again. No LLM, same question.

Issue #68. ``regenerate`` cannot supply a missing fact, and ``rewrite`` spends
a model call on a new query. Expanding the current retrieve is the cheap
evidence-changing action: keep the search text, ask the index for more
neighbours, generate from that set if generation is on.
"""

from __future__ import annotations

DEFAULT_EXPAND_CAP = 20
DEFAULT_EXPAND_FLOOR = 8


def next_top_k(
    current: int,
    *,
    cap: int = DEFAULT_EXPAND_CAP,
    floor: int = DEFAULT_EXPAND_FLOOR,
) -> int | None:
    """Return a strictly larger ``top_k``, or ``None`` when already at the cap.

    ``k=1`` becomes 8 so a near-neighbour sitting just outside a one-chunk
    retrieve can enter the evidence. Later expansions multiply, then stop
    rather than no-op at the cap.
    """
    if current < 1:
        current = 1
    candidate = min(cap, max(current * 3, current + 4, floor))
    if candidate <= current:
        return None
    return candidate
