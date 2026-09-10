# 007 — Query-rewrite recovery

- decision: When first-pass evidence is insufficient, **rewrite the query and retrieve again**. The rewrite outcome attributes `retrieval_miss` vs `evidence_insufficiency`. Abstain only after rewrite still finds no sufficient evidence.
- date: 2026-09-10
- status: accepted (student requested; completes the ADR 005 / ADR 006 map)

## Context

ADR 006 implemented constrained regenerate because that was the only class first-pass diagnosis could emit. Insufficient evidence was mapped to abstain, which made the distractor corpus (ADR 004) idle: a retrieval miss never got a second retrieve.

ADR 005 already stated that miss vs corpus-gap cannot be split on the first pass, and that rewrite-then-retrieve is the discriminator.

## Alternatives considered

1. **Rewrite + second retrieve** (this ADR) — one extra embedding search, plus an LLM rewrite. Makes `retrieval_miss` selectable. Risk: a bad rewrite can make retrieval worse (must be recordable as `degraded`).
2. **Keep abstaining on first-pass insufficiency** — honest given current detectors, but throws away ADR 004.
3. **Blindly retrieve with a larger `top_k` instead of rewriting** — cheaper, does not test query rewrite, and does not change the query the index sees.

## Policy change

| Situation | Action |
|---|---|
| First pass: `unsupported_generation` | regenerate (ADR 006, unchanged) |
| First pass: evidence insufficient | **rewrite query, retrieve again** |
| After rewrite: evidence becomes sufficient | attribute `retrieval_miss`; generate from the new chunks |
| After rewrite: evidence still insufficient | attribute `evidence_insufficiency`; **abstain** (do not generate from the new empty evidence) |
| First pass: no failure | accept |

The original user question is what generation and the judge see. The rewritten string is used **only** as the retrieval query.

Runtime verification (issue #10) must treat sufficiency False→True as `improved`, not only `answer_supported`. Gold labels stay offline.

## Tradeoffs

Rewrite adds a second judge call and a second retrieve. A rewrite that drifts off the entity name can degrade retrieval; that is a result, not a bug to patch by editing the rewriter against scores.

Chaining rewrite then regenerate in one run is allowed only if `max_recoveries` is raised; V1 default remains one recovery, so a repaired miss whose new answer is unsupported stops there.

## Final choice

Implement query rewrite as the retrieval recovery. Abstain moves to *after* a failed rewrite. Constrained regenerate stays the unsupported-generation recovery.

## Reason for the choice

It is the recovery ADR 005 reserved for this class, and it is what makes the three-class taxonomy measurable rather than decorative.
