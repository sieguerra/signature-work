"""Evaluation.

Offline scoring against the gold set lives in ``gold`` and ``scoring``.
Runtime grounding signals live in ``judge`` / ``llm_judge`` / ``scripted_judge``.
A judge-independent retrieval-quality read lives in ``retrieval_signal``.

The two must stay separate: offline scoring reads gold labels, and runtime
signals must never do so (ADR 003).
"""

from swrag.evaluation.gold import load_gold_set
from swrag.evaluation.scoring import score_answer

__all__ = ["load_gold_set", "score_answer"]
