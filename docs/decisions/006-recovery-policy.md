# 006 — Recovery policy (first implemented action)

- decision: Bind one recovery per V1 class; **implement regenerate-constrained-to-evidence first** for `unsupported_generation`. Accept and abstain are terminal outcomes, not extra generative recoveries.
- date: 2026-09-10
- status: accepted (follows student-confirmed ADR 005; GitHub issue #9)

## Context

Issue #9 requires a controller and **one** recovery action, not a library. ADR 005 already implied a different recovery per class. First-pass diagnosis (#8) can emit only `unsupported_generation`. Query-rewrite cannot fire until that diagnosis exists; abstain is the right response to insufficient evidence but is a stop decision, not a generation repair.

## Alternatives considered

1. **Regenerate constrained to evidence** (this ADR) — matches the only first-pass class. Cheap: same retrieval, one extra generate. Does not fix retrieval misses.
2. **Query rewrite + retrieve again first** — needed for `retrieval_miss` and for splitting miss vs corpus-gap, but the detector for that class is not implemented yet. Building it now would be a recovery with nothing to select it.
3. **Implement all three recoveries at once** — matches the implied map, violates issue #9's "one action" cap and the V1 rule of few reliable mechanisms.

## Policy (V1 map)

| Failure class | Action | Status |
|---|---|---|
| `unsupported_generation` | regenerate from the same evidence, constrained not to repeat unsupported claims | **implemented** |
| `evidence_insufficiency` | abstain (stop; do not regenerate from empty evidence) | represented as an outcome |
| `retrieval_miss` | rewrite query, retrieve again | deferred until diagnosis can emit this class |
| no first-pass failure | accept | represented as an outcome |

The controller must not read gold labels. Whether regenerate actually helped is a **verification** question (issue #10), scored at runtime against the judge and offline against gold in the experiment harness.

## Tradeoffs

Starting with regenerate means the first recovery experiment will under-represent retrieval failure, which is the class the distractor corpus was built to produce. That is accepted for this slice: a recovery that cannot be selected is dead code. Query-rewrite is the next recovery, not a silent extra in this one.

## Final choice

Controller outcomes: `regenerate`, `abstain`, `accept`. The only applied recovery in this slice is constrained regeneration for `unsupported_generation`.

## Reason for the choice

It is the only action that the current detector can request. It keeps accept/abstain visible in the trace so the later loop (issue #11) has somewhere to stop.
