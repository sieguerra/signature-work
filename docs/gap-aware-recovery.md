# Recovery policies

Recovery policy and run mode are separate. Retrieve-only and baseline never apply a recovery policy. Confirm mode proposes one action and waits. Auto mode (`loop`) applies the selected policy.

The default is current v1. Nothing stored without an explicit choice changes to gap-aware.

## Current v1

Insufficient evidence rewrites the query first, then expands retrieval. This is `recovery_policy: "v1"`.

## Gap-aware guarded

Product name: `gap_aware`.

Internal name stored on traces: `v2c_gap_aware`.

The decision rules are the frozen Phase 8C candidate. This phase does not retune them.

On insufficient evidence the loop expands from the current top 4 to top 12. If the answer is then supported, it returns that answer. If not, a deterministic check of the retrieved text either allows one rewrite or stops. Uncertain evidence stops. A conflict or neighboring figure replaces an answer only when that answer states the contested value.

The user-facing stop says that bounded search did not find sufficient support. It does not say the corpus was proved empty. A conflict diagnosis stays on the trace and is not asserted as certain in the answer, because some Phase 8C stops were safe for the wrong reason.

Confirm mode still proposes the first action and applies only that action after confirmation. It does not run the rest of the chain by itself.

## Trace fields

Attempts may include `recovery_opportunity`, `stop_reason`, `gap_signal`, `conflict_signal`, `neighbor_signal`, and `decision_source`. These describe the bounded evidence in hand. They are not gold, human labels, answerability, stratum, or supporting rank.

`recovery_policy` on a trace is the internal name that ran. Missing means v1.

## Usage

Token fields are null and `tokens_observed` is false when the provider omits usage. That is unavailable, not zero. A list-price estimate is returned only when tokens were observed, and it is labeled `estimated`. The assumption is gpt-4o-mini at $0.15/1M input and $0.60/1M output, and text-embedding-3-small at $0.02/1M. That estimate is not an invoice.

## Known limits

- Some safe stops record a conflict or neighbor diagnosis when the sources simply omit the fact. The answer no longer states that diagnosis as fact.
- The Phase 8C sample is small: 4 recoverable cases and 6 corpus gaps on the new benchmark.
