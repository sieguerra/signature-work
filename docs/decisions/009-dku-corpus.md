# 009 — DKU corpus (second dataset)

- decision: Add a **Duke Kunshan University** corpus and gold set under `datasets/dku/`. Keep the Harbor Institute corpus and the #12 Harbor snapshot. Point the UI and new experiments at DKU.
- date: 2026-09-10
- status: accepted (student-requested DKU data after Harbor results existed)

## Context

Harbor Institute was fictional on purpose (ADR 003): no pretraining leakage, unambiguous gold. The first benchmark then showed retrieval hit rate 1.000 and 27/32 first-pass accepts. The student asked for a better dataset built from Duke Kunshan University public information.

Editing Harbor in response to those scores would violate ADR 004. A **new** dataset with a new id prefix (`dku-*`) does not overwrite Harbor.

## Alternatives considered

1. **Original short notes grounded in public DKU pages** (this ADR) — campus-relevant, still hand-checkable, distractors can be designed (Kunshan library vs Durham libraries; Academic Building dining vs Conference Center Halal; 2021 handbook vs 2026 hours; 2025 brochure vs current hours). Reintroduces leakage.
2. **Raw scraped HTML/PDF text in the repo** — closer to “grab the website,” heavier copyright risk, noisier gold.
3. **Stay on Harbor and only add more fictional questions** — no leakage, weaker as a DKU Signature Work demo.

## Tradeoffs

Leakage can make unanswerable tuition/officer questions look like generation failures when the model answers from memory. That must be reported. Documents are dated with retrieve day 2026-09-10; DKU pages can change.

Same-entity conflicts appear only when dated (2021 handbook; January 2025 brochure vs current hours page), following the ADR 004 rule.

## Final choice

- New tree: `datasets/dku/corpus/`, `datasets/dku/gold/questions.jsonl`
- Harbor paths unchanged
- New experiment config `experiments/configs/v2_dku_baseline_vs_loop.json`
- UI default corpus: DKU

## Reason for the choice

The student asked for DKU data. A second dataset preserves the Harbor result and still lets the loop be tested on near-neighbour campus facts.
