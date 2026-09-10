# Architecture Decision Records

Major project decisions should be recorded here.

Each decision should include:

- decision
- context
- alternatives considered
- tradeoffs
- final choice
- reason for the choice
- date

Recorded:

- [001-first-slice-stack.md](001-first-slice-stack.md) — Python, in-memory embeddings, OpenAI (2026-09-10)
- [002-contribution-and-scope.md](002-contribution-and-scope.md) — verification quality as the contribution, single-hop V1 (2026-09-10)
- [003-evaluation-method.md](003-evaluation-method.md) — LLM judge at runtime, EM/F1 offline, own corpus, swappable provider (2026-09-10)
- [004-corpus-difficulty.md](004-corpus-difficulty.md) — distractor documents, written before any results (2026-09-10)
- [005-failure-taxonomy.md](005-failure-taxonomy.md) — three V1 classes: retrieval miss, evidence insufficiency, unsupported generation (2026-09-10)
- [006-recovery-policy.md](006-recovery-policy.md) — regenerate first for unsupported generation; accept/abstain as outcomes (2026-09-10)

Later examples (not yet written):

- 007-vector-database.md
- 008-agent-framework.md

