# 005 — V1 failure taxonomy

- decision: Restrict V1 to **three** failure classes — retrieval miss, evidence insufficiency (including corpus-gap), and unsupported generation.
- date: 2026-09-10
- status: accepted (student-confirmed, GitHub issue #7)

## Context

`docs/project-spec.md` listed six candidate classes. Issue #7 required a small V1 set, each with a definition and a detection method, before diagnosis or recovery is implemented.

ADR 002 requires results **per failure class**, and forbids reading gold labels at runtime. ADR 003 supplies two runtime signals (evidence sufficiency, answer support) and an offline truth (EM/F1 against gold). The taxonomy has to be separable with those signals. ADR 004 kept three classes so the distractor corpus has a failure mode to produce.

A class that cannot be detected, or that shares a recovery with another class, is not a V1 class.

## Alternatives considered

1. **Three classes** (this ADR) — retrieval miss, evidence insufficiency (corpus-gap folded in), unsupported generation. Each maps to a different recovery. Ranking and citation are deferred.
2. **The spec's six classes** — add ranking failure, citation failure, and keep corpus-gap separate from evidence insufficiency. Broader coverage of the spec, but V1 has no reliable ranking or citation detector, and corpus-gap is a special case of insufficiency rather than a distinct diagnosis.
3. **Two classes** — insufficiency vs unsupported generation. Simplest, but collapses retrieval miss into insufficiency, which drops the query-rewrite recovery and wastes the distractor documents from ADR 004.

## The three classes

Stable ids in parentheses are the names later code should use.

### Retrieval miss (`retrieval_miss`)

The corpus contains a supporting answer, but retrieval did not surface the supporting document (or the supporting span).

- **Offline detection:** gold `answerable` is true, `supporting_doc_ids` is non-empty, and none of those documents appear in the retrieved set.
- **Runtime detection:** the first-pass sufficiency judge reports that retrieved evidence cannot support an answer; after a query-rewrite and second retrieve, sufficiency becomes high. Runtime cannot split retrieval miss from evidence insufficiency on the first pass without reading gold labels, which ADR 002 forbids.
- **Implied recovery:** rewrite the query and retrieve again. Recovery policy itself is ADR 006 / issue #9.

### Evidence insufficiency (`evidence_insufficiency`)

Neither the retrieved evidence nor, after the allowed retrieval recovery, the corpus as reached can support an answer. This includes **corpus-gap**: gold `answerable` is false.

- **Offline detection:** gold `answerable` is false. (If a later gold item is answerable but every retrieved-and-rewritten set still lacks the supporting span, that is also this class; V1 does not need that case to exist.)
- **Runtime detection:** sufficiency remains low after the allowed retrieval recovery.
- **Implied recovery:** abstain. Do not regenerate an answer from insufficient evidence.

Corpus-gap is not a fourth class. Folding it in avoids a distinction that the first-pass runtime signals cannot make.

### Unsupported generation (`unsupported_generation`)

Retrieved evidence is sufficient to answer, but the generated answer is not grounded in that evidence.

- **Offline detection:** retrieval hit is true (supporting doc was retrieved) and the answer fails the gold score, or a hand audit shows the answer is not supported by the retrieved text even if it happens to match gold.
- **Runtime detection:** sufficiency judge reports enough evidence; answer-support judge reports the answer is not entailed by the retrieved chunks. This class *is* separable on the first pass.
- **Implied recovery:** regenerate constrained to the retrieved evidence.

## Deferred (not V1 classes)

- **Ranking failure** — the supporting document was retrieved but not used, or sat below an unused distractor. Detecting it needs a use/attribution signal V1 does not have. A ranking error that drops the supporting document out of `top_k` is already a retrieval miss.
- **Citation failure** — V1 gold answers are short strings. There is nothing to cite yet.
- **Separate corpus-gap class** — same runtime appearance and same recovery as evidence insufficiency.

If a deferred class becomes measurable, it gets its own ADR. It is not added by expanding a detector later without a new decision.

## Tradeoffs

Three classes give up ranking and citation, which the spec named. The cost is a narrower failure story. The gain is that every class has a detector path and a distinct recovery, which is the condition ADR 002's per-class reporting needs.

Keeping corpus-gap inside evidence insufficiency means the write-up must still **construct** unanswerable gold items (issue #5) and still **report** abstention on that subset. The class id does not change; the gold slice does.

The first-pass runtime tie between retrieval miss and evidence insufficiency is a real limit, not a temporary stub. V1 accepts it: diagnosis of those two classes is allowed to use the outcome of the retrieval recovery. Verification (issue #10) still scores whether that recovery helped, which is the measurement ADR 002 asked for.

## Final choice

V1 taxonomy, three classes:

1. `retrieval_miss`
2. `evidence_insufficiency` (includes corpus-gap)
3. `unsupported_generation`

Ranking failure, citation failure, and a separate corpus-gap class are out of V1.

## Reason for the choice

It is the smallest set that (a) uses only ADR 003's signals plus gold labels offline, (b) gives each class a different recovery, and (c) makes the ADR 004 distractors load-bearing rather than decorative. Six classes would invent detectors the project will not build. Two classes would throw away retrieval as a failure mode.

Consequences for later work:

- Issue #5 must include answerable items whose supporting docs can be missed, and unanswerable items for the insufficiency/abstain path.
- Issue #6 implements the two runtime judges; it does not invent extra classes.
- Issue #8 diagnoses with this taxonomy, including the first-pass tie noted above.
- Issue #9 / ADR 006 binds one recovery per class; this ADR does not freeze that policy, only the implication.
- Issue #12 reports per class, not a pooled accuracy.
