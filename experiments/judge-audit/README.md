# Judge audit (issue #38)

ADR 003 requires a **hand-audited sample** of LLM-judge decisions, with
agreement stated as counts and `n`. This folder holds the template. Do not
overwrite `experiments/results/20260910T070623/`.

## How to label

1. Copy `template.jsonl` to a dated file, e.g. `20260912/labels.jsonl`.
2. Pick at least 30 loop traces (mix accept / rewrite / abstain if you have them).
3. For each row, read **only** question + evidence + answer. Do **not** open gold.
4. Fill `human_sufficient` and `human_supported` (`true` / `false` / `null`).
5. Leave judge columns copied from `runtime_evaluation` on the trace.
6. Commit the filled file. Report raw agreement counts, not a thesis conclusion.

Cursor must not invent the human labels.
