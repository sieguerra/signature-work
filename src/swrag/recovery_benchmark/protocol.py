"""Frozen recovery-benchmark protocol.

Written before the expanded run was scored. Do not retune these constants
against the results. A later change is a new experiment.
"""

from __future__ import annotations

PROTOCOL_VERSION = "recovery-benchmark-2026-10-06"
SEED = 20261006

# Product Test Console loop. Not the Phase 6 top_k=1 recovery-set operating
# point, and not a change to the recovery policy.
TOP_K = 4
MAX_RECOVERIES = 2

# Primary offline label. Identical to Verification v2 quality_rank.
# A paraphrase that does not contain a gold span is still a miss.
GOLD_PRIMARY = "gold-rank-2026-10-06"

# Comparison labels. They are not the success definition.
# 0.8 is high on purpose: a lower bar would treat shared topic words as a hit.
# Chosen before this benchmark was scored.
GOLD_PARAPHRASE = "gold-f1-0.8-2026-10-06"
PARAPHRASE_F1 = 0.8
GOLD_GROUNDED = "gold-grounded-2026-10-06"

# About one fifth of newly eligible questions, by a stable hash.
HOLDOUT_MODULUS = 5
HOLDOUT_RESIDUE = 0

# Phase 6 already scored these files. They stay in the analysis panel.
# They are not a fresh holdout for a later verifier.
PHASE6_OBSERVED_GOLD = (
    "datasets/kestrel-aero/gold/first-pass-fail.jsonl",
    "datasets/kestrel-aero/gold/recovery.jsonl",
    "datasets/dku/gold/first-pass-fail.jsonl",
    "datasets/dku/gold/recovery.jsonl",
)

DEMO_CORPUS_ID = "recovery-demo"
DEMO_MANIFEST = "datasets/recovery-demo/manifest.json"

# Sibling gold files that are questions. audit.jsonl is a substring log.
QUESTION_SOURCES = ("questions.jsonl", "recovery.jsonl", "first-pass-fail.jsonl")

NEAR_DUPLICATE_JACCARD = 0.9

BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_ALPHA = 0.10

# List-price estimates, not an invoice. Checked 2026-10-06.
# https://platform.openai.com/docs/pricing
PRICE_PER_MILLION = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "text-embedding-3-small": {"input": 0.02},
}

RUN_ID = "phase7-20261006"
