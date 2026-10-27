# 002 — Contribution framing and retrieval depth

- decision: Frame the contribution as **recovery verification quality**, and scope V1 to **single-hop retrieval**.
- date: 2026-09-10
- status: accepted (student-confirmed)

## Context

A literature pass in GitHub issue #15 found that the monitor → diagnose → recover → verify loop is no longer unexplored. Two 2026 preprints are close neighbours:

- **Self-Healing Agentic Orchestrators** (arXiv:2606.01416, June 2026) implements a monitor–detect–diagnose–recover–verify loop with explicit recovery budgets, and reports 98.8% task success against 94.5% for retry-only.
- **AgentDebugX** (arXiv:2607.18754, July 2026) organises agent debugging as Detect → Attribute → Recover → Rerun.

Both report **task success after recovery**. Neither reports how accurate the verification step itself is. That gap is the opening this project takes.

Separately, **When Failures Propagate / AgenticRAG-FP** (arXiv:2608.20627, August 2026) reports that post-hoc coverage-based diagnosis scores 0.91 at hop 1 and 0.00 at hops 2 and 3. Diagnosis accuracy collapses once a failure has propagated across hops.

Neither preprint is peer-reviewed. They establish that the area is active and constrain the positioning; they do not by themselves support thesis claims.

## Alternatives considered

### Contribution framing

1. **Verification quality** — measure whether a recovery helped, hurt, or changed nothing, and report degradation honestly. Distinct from prior work, which reports aggregate success. Risk: requires a trustworthy offline ground truth to score verification against.
2. **Natural vs. injected failures** — diagnose failures arising naturally on a real corpus rather than injected faults. Honest differentiator, but weaker as a claim: "different setup" is not "new finding," and natural failures are harder to obtain in balanced quantities.
3. **Per-failure-class credit** — following the LayerRAG-Bench principle, credit a recovery only for repairing its target class. Strong methodology, but closer to replication of a stated principle than an independent contribution.
4. **Cost-bounded recovery** — which recoveries are worth their token budget. Already central to Self-Healing Orchestrators and AB-RAG; least differentiated.

### Retrieval depth

1. **Single-hop** — one retrieval per query. Diagnosis stays measurable; matches the AgenticRAG-FP evidence.
2. **Iterative multi-hop** — more realistic and more impressive, but diagnosis accuracy is documented to collapse with depth, which would undermine the verification measurements this project depends on.
3. **Single-hop with a multi-hop stretch goal** — hedges, but risks half-finishing both.

## Tradeoffs

Choosing verification quality means the project lives or dies on having a defensible ground truth for "did recovery actually help." That makes the gold set (issue #5) load-bearing rather than incidental, and it means a **negative result is still a result**: showing that verification is unreliable would be a genuine finding.

Choosing single-hop gives up multi-hop realism. Multi-hop QA is where agentic RAG is usually benchmarked, so this narrows comparability with existing benchmarks and may read as a modest scope. The counter-argument is on record: measuring verification at a depth where diagnosis is known to be near-random would produce uninterpretable results.

## Final choice

- **Contribution:** verification quality — measure and report whether recovery helped, hurt, or did nothing, including cases where recovery degrades the answer.
- **Depth:** single retrieval per query for V1. Multi-hop is out of scope, not deferred.

## Reason for the choice

Prior work optimises recovery and reports the aggregate outcome. Nothing found so far asks whether the system's own judgement that "recovery worked" is correct. That question is smaller than building a better agent, which fits a single-semester scope, and it is answerable with the single-hop pipeline already built in PR #14.

Consequences for later work:

- Results must be reported **per failure class**, not as a single aggregate (LayerRAG-Bench principle). Affects issue #12.
- Runtime accept/retry/abstain signals must not read gold labels; correctness labels are for offline scoring only. Follows Huang et al. (ICLR 2024). Affects issues #6 and #9.
- The gold set must support scoring recovery outcomes, not just answer correctness. Affects issue #5.
