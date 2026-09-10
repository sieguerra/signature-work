"""Evaluation.

Offline scoring against the gold set lives here (``gold``, ``scoring``).
Runtime signals -- evidence sufficiency and answer support -- arrive in Phase 1.

The two must stay separate: offline scoring reads gold labels, and runtime
signals must never do so.
"""
