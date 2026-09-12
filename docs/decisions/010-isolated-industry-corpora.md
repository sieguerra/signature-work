# 010 — Isolated industry corpora and UI toggle

- decision: Keep **one corpus in the index at a time**. Add several fictional industry worlds as separate folders, selectable in the explorer. Do not concatenate them into a single mixed retrieve.
- date: 2026-09-10
- status: accepted (student asked for more data across niches, with no overlap)

## Context

Harbor (11 notes) and DKU (14 notes) are small. The explorer always indexed one folder. Mixing every new industry into that folder would make retrieval a cross-domain jumble and would hide the near-neighbour traps inside each world.

ADR 003 used fiction so the model could not already know the answers. DKU reopened leakage on purpose (ADR 009). New industry text is **fictional** so gold stays local.

## Alternatives considered

1. **Isolated folders + UI toggle** (this ADR) — no overlap at retrieve time; traces stored per corpus id.
2. **One mixed mega-index** — more documents in every top-4, but a water-utility question can retrieve a streetcar timetable.
3. **Real scraped industry websites** — more “current,” heavier leakage and copyright risk (ADR 009 rejected HTML dumps).

## Tradeoffs

Fiction means the demo is not a live DKU-style campus crawl. Isolation means the loop cannot be tested on cross-domain retrieval failure unless we add a later mixed condition on purpose.

## Final choice

- `datasets/registry.json` lists every selectable corpus
- New worlds under `datasets/<id>/corpus/` with gold at `datasets/<id>/gold/questions.jsonl`
- Harbor and DKU paths unchanged
- UI select switches `corpus_dir`, clears the in-memory index, and points traces at `experiments/output/<id>/`
- No vector database

## Reason for the choice

The student asked for more niches **and** a way to pick one topic so documents do not overlap. Separate indexes are the smaller mechanism.
