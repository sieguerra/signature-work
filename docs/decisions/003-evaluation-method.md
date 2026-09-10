# 003 — Evaluation method, ground truth, gold set, and provider

- decision: LLM-as-judge for runtime grounding signals; EM/F1 against gold for offline truth; hand-built corpus; provider swappable via config.
- date: 2026-09-10
- status: accepted (student-confirmed)

## Context

ADR 002 fixed the contribution as **recovery verification quality**: measuring whether the system's own verdict that "recovery worked" is correct. That requires two independent things — a runtime signal the system may use while deciding, and an offline truth the system may never see. This ADR fixes both, plus the data they run on and the model backend.

The four choices are recorded together because they constrain each other. In particular, the runtime signal and the offline truth must be independent, or the central measurement is circular.

## Alternatives considered

### Answer-support (grounding) check

1. **LLM-as-judge via API prompt** — trivial to build, no local inference, works on any provider. Costs money per call and carries documented position, verbosity, and self-preference biases (arXiv:2306.05685).
2. **MiniCheck-style local NLI model** (EMNLP 2024) — cheap, deterministic, fully reproducible. Requires local model hosting and a CPU fallback, and adds a dependency before any pipeline exists.
3. **Both behind one interface** — strongest methodologically, and judge/NLI disagreement would itself be a finding. Roughly double the work for V1.

### Offline ground truth for "did recovery help"

1. **Exact Match / F1 against short gold answers** — objective, cheap, reproducible, and directly comparable to Doctor-RAG's Repair Rate. Brittle on phrasing, and forces questions to have short answers.
2. **Manual judgement on every answer pair** — most trustworthy, but caps the study at roughly 100–200 questions.
3. **A separate LLM judge** — scales, but uses an LLM to validate an LLM. A committee will push on this.
4. **EM/F1 primary with a hand-audited sample** — hedge; keeps the objective primary metric and reports reliability.

### Gold set

1. **Hand-built on the existing fictional corpus** (`datasets/corpus/`) — total control, unambiguous gold answers, no pretraining leakage. Small, and not comparable to published numbers.
2. **SQuAD 2.0** — has built-in unanswerable questions that map onto the corpus-gap class, but is old and almost certainly in the model's pretraining data, which would contaminate the corpus-gap measurements specifically.
3. **RGB negative-rejection setting** — purpose-built for testing evidence rejection.
4. **Own corpus for development, public dataset for headline results.**

### Model provider

1. **Swappable via config, assume nothing** — proxy for development, verifiable provider for benchmark runs, backend recorded per run.
2. **Target the reseller proxy** — cheapest, but model provenance is unverifiable: there is no way to confirm a model named `gpt-4o-mini` is that model, or that the backend did not change mid-study.
3. **Official OpenAI only** — verifiable, blocks development until a real key exists.

## Tradeoffs

**The judge/EM-F1 pairing is the important one.** An LLM judge produces the runtime grounding signal; EM/F1 against gold produces the offline truth. Because the two are computed by different mechanisms from different inputs, the judge is never scoring its own output, and the central measurement — does the runtime verdict match the offline truth — stays non-circular. This is why option 1 for the grounding check is acceptable despite its known biases: the biases degrade the signal being measured, they do not corrupt the measuring instrument.

The costs accepted:

- **Judge bias is real and must be reported**, not assumed away. A hand-audited sample of judge decisions is required, with agreement stated as a number.
- **EM/F1 brittleness** constrains every gold question to a short, unambiguous answer. Questions must be written to that constraint from the start rather than retrofitted.
- **A hand-built corpus is not comparable to published benchmarks.** This must be stated as a limitation, and the work framed as a controlled study of verification behaviour rather than a leaderboard result. The compensating benefit is that pretraining leakage cannot explain away a corpus-gap result, which matters more here than comparability, because the corpus-gap class is where leakage would do the most damage.
- **Provider abstraction is a small amount of extra code** written before it is strictly needed. Justified because the trace must record which backend produced each result for any benchmark claim to be reproducible.

## Final choice

- **Runtime grounding signal:** LLM-as-judge via API prompt, behind an interface so a local NLI checker can replace it later without touching the controller.
- **Offline truth:** Exact Match and F1 against short gold answers. Never read at runtime.
- **Gold set:** hand-built, extending `datasets/corpus/`, with both answerable and unanswerable questions so the corpus-gap class exists.
- **Provider:** fully swappable via configuration. Model name and endpoint recorded in every trace.

## Reason for the choice

This is the smallest set of choices that makes the ADR 002 measurement possible without circularity, and every component runs on an API-only stack with no local GPU. The judge is replaceable, the truth is objective, the data is uncontaminated, and the backend is recorded.

Known risks carried forward:

- Judge reliability must be measured and reported, not asserted. Affects issue #6.
- Gold questions must have short answers by construction. Affects issue #5.
- Corpus size will limit statistical power; effect sizes should be reported with uncertainty rather than as point estimates. Affects issue #12.
