# Judge audit (issue #38)

ADR 003 requires a **hand-audited sample** of LLM-judge decisions, with
agreement stated as counts and `n`. This folder holds the template. Do not
overwrite `experiments/results/20260910T070623/`.

## How to label

1. Export a blank sheet from loop traces. Human fields stay null, and gold is not copied:

   ```bash
   python scripts/score_judge_audit.py export experiments/output/<run>/traces -o experiments/judge-audit/<date>/labels.jsonl
   ```

2. Pick at least 30 rows (mix accept / rewrite / abstain if you have them). Recovered runs export two rows: `stage: "first_pass"` is the judge call that chose to recover, `stage: "final"` is the one verification compared against. Label both; `score` reports agreement per stage.
3. For each row, read **only** question + evidence + answer. Do **not** open gold.
4. Fill `human_sufficient` and `human_supported` as `true` or `false`.
5. Score the filled file. It refuses to run while any human field is blank:

   ```bash
   python scripts/score_judge_audit.py score experiments/judge-audit/<date>/labels.jsonl
   ```

6. Commit the filled file. Report the raw counts, not a thesis conclusion.

Cursor must not invent the human labels.
