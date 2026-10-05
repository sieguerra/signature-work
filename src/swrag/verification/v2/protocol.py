"""Frozen Verification v2 protocol.

Written before any candidate was scored. Do not retune these constants against
held-out results. A later change is a new experiment and must be labeled as one.
"""

from __future__ import annotations

PROTOCOL_VERSION = "verification-v2-2026-10-06"
SEED = 20261006

# Operating point of the live panel. Copied from the historical first-pass-fail
# configs (experiments/results/20260927T151157 and 20260927T151544). This does
# not change the product default, which remains top_k 4 and the loop's own
# max_recoveries default.
LIVE_TOP_K = 1
LIVE_MAX_RECOVERIES = 2

CLASSES = ("improved", "unchanged", "still_failing", "degraded")

# Offline quality ranks. See gold_transition.py. Not a verifier threshold.
RANK_CORRECT = 2
RANK_SAFER_ABSTENTION = 1
RANK_FAIL = 0

# Coverage candidate. Frozen before scoring. A non-abstaining answer is
# treated as grounded only when every checkable fact occurs in its evidence
# and at least this fraction of its content tokens occur there.
# One content token is enough: this project's gold answers are short spans,
# so a two-token minimum would mark a correct one-word answer as ungrounded.
COVERAGE_GROUNDED = 0.5
COVERAGE_MIN_CONTENT_TOKENS = 1

# Corpus holdout, not a random split of one file. n is too small to stratify
# four classes inside one corpus, and a corpus holdout keeps dev wording away
# from the test institution. Harbor is archive only: the 2026-09-10 comparison
# has verdicts but the trace files, and therefore the evidence text, are gone.
DEV_CORPUS = "kestrel-aero"
TEST_CORPUS = "dku"
ARCHIVE_CORPUS = "harbor"

DEV_GOLD = (
    "datasets/kestrel-aero/gold/first-pass-fail.jsonl",
    "datasets/kestrel-aero/gold/recovery.jsonl",
)
TEST_GOLD = (
    "datasets/dku/gold/first-pass-fail.jsonl",
    "datasets/dku/gold/recovery.jsonl",
)

# Pass criteria for promoting a shadow candidate. Set from the expected sample
# (about 10-30 real transitions) before the held-out run. A point-estimate
# lift is not enough: REPLACE_V1 also requires the paired bootstrap interval.
MIN_DECIDED_COVERAGE = 0.50
MIN_DECIDED_FOR_PROMOTION = 8
MATERIAL_PRECISION_LIFT = 0.10
MAX_MACRO_F1_DROP = 0.05
MAX_POSITION_INCONSISTENCY = 0.20
MAX_MODEL_CALLS_PER_TRANSITION = 4
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_ALPHA = 0.10  # 90% percentile interval

# Published list rates used only as a labeled estimate, never as an invoice.
# OpenAI gpt-4o-mini, checked 2026-10-06:
# https://platform.openai.com/docs/pricing
PRICE_PER_MILLION = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}
