# 004 — Corpus difficulty and distractor design

- decision: Add distractor documents with heavy lexical overlap, written before any results are collected.
- date: 2026-09-10
- status: accepted (student-confirmed, GitHub issue #19)

## Context

Smoke-testing the Phase 0 harness gave a **retrieval hit rate of 1.000** on the seed gold set. Verified per question: every answerable question retrieved its supporting document at rank 1, even with the crude hash `FakeEmbedder`.

The cause is the corpus, not the retriever. `datasets/corpus/` held five documents on five unrelated topics — a library, a lab, a shuttle, a canteen, an archive group — so any query lexically overlapped exactly one of them.

This is a problem for ADR 002. If retrieval never fails, the retrieval-insufficiency failure class never occurs, the query-rewrite recovery has nothing to act on, and the recovery experiment collapses to "does regeneration help." That is a substantially smaller project than the one ADR 002 describes.

## Alternatives considered

1. **Add distractor documents with heavy topical overlap** — near-neighbour documents sharing vocabulary with existing ones, so retrieval has to discriminate. Keeps control and zero pretraining leakage. Still hand-built and small, and needs care in the write-up so it does not read as tuning the benchmark to the result.
2. **Grow the corpus to 50–200 documents** so lexical collisions arise naturally. Difficulty is emergent rather than designed, but it is a large amount of writing and raises embedding cost per run.
3. **Use a public corpus** — realistic difficulty and comparable numbers, but reintroduces pretraining leakage, which is exactly what ADR 003 chose a fictional corpus to avoid. Leakage damages the corpus-gap class most, since a model may "know" an answer the corpus does not contain.
4. **Keep the easy corpus and narrow the taxonomy to two classes** — honest and free, but drops the query-rewrite recovery and narrows the project.

## Tradeoffs

Option 1 carries one serious methodological risk: **writing documents until retrieval breaks is indistinguishable, after the fact, from tuning a benchmark until it produces the desired result.** Nothing in the artifact itself separates the two.

The mitigation is ordering, committed to in advance and on the record:

- Distractors are written **before** any evaluation results are collected.
- They are designed against a **stated rule**, not against observed failures of the system under test.
- They are **not revised** in response to results. If they turn out to be too weak or too strong, that is reported as a finding, not corrected by editing the corpus.

This ADR exists to date-stamp that commitment while no results exist yet.

## The design rule

Distractors must create **lexical confusion for the retriever without creating factual ambiguity for a reader**.

Concretely, each distractor shares vocabulary, entity types, and question shapes with an existing document, but describes a **distinctly named** entity with **different facts**. So:

- Retrieval can plausibly return the wrong document — the failure we need to be reachable.
- Once the correct document is read, the gold answer is still unique and unambiguous — so Exact Match remains valid and the failure is attributable.

A consequence, discovered while applying the rule: **every gold question must name its entity explicitly.** A question like "how long is a booking held before it is cancelled?" was unambiguous with one lab in the corpus and becomes ambiguous with two. This is a constraint on question writing, recorded in `datasets/gold/README.md`.

Deliberately **not** included: documents that contradict each other about the *same* entity without any way to tell which is current. That produces genuinely ambiguous gold answers and a fourth failure class (conflicting evidence) that V1 does not scope. The one stale document included is explicitly marked superseded and dated, so the current fact remains determinable.

## Final choice

Add distractor documents to `datasets/corpus/` following the rule above, before the real gold set is written and before any results are collected. Keep the taxonomy at three classes.

## Reason for the choice

It makes a known failure mode reachable without giving up the two properties the fictional corpus was chosen for in ADR 003: unambiguous gold answers, and no pretraining leakage. Options 2 and 3 each sacrifice one of those, and option 4 sacrifices a third of the project.

The pre-registration commitment above is what makes this defensible rather than convenient. It should be restated in the write-up's limitations section, not buried here.
