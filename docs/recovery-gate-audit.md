# Recovery gate audit

The live recovery policy is unchanged. Verification v1 and Verification v2 are unchanged. The 39-question future holdout was not run, scored, or labeled.

## Needed recovery

Defined before any rate, in `docs/recovery-review-rubric.md`.

A run needed recovery when a person judges the before state incorrect or materially incomplete. A correct answer did not. An appropriate abstention did not. Unclear is excluded.

## Review

Open `tools/recovery-review/index.html` from a local server started in that directory. Two packets:

- Triggered runs. All 60. Before state and transition.
- Runs that did not recover. 40 of the 126 analysis accepts, stratified by corpus and answerability, seed `20261006`. Before state only.

The page does not pre-select a label. Export `human_labels_<reviewer>.jsonl` and copy it to `experiments/recovery-benchmark/runs/phase75-20261006/human_labels.jsonl`. A second file can be saved as `human_labels_reviewer2.jsonl`. Then run `scripts/score_recovery_gate.py`.

No human file is in the repository. The rates that depend on it are not filled in.

## What the traces show, without a human label

Of the 60 triggered runs, the first-pass signals fall into three groups.

- 40 began with insufficient evidence and an answer that already started with "I do not know". This group includes `dku-053`, `dku-055`, and `dku-012`, the three cases where a later expand quoted the gold span. It also includes most of the runs Phase 7 called already abstained.
- 10 began with insufficient evidence and a specific answer, not that abstention prefix. This group includes `seed-009`.
- 10 were accepted by the judge as sufficient and supported, and recovery fired only because the top two retrieval scores were within the 2% margin. `dku-045` is in this group. `weak_top` did not fire on any of the 60.

All 126 runs that did not recover had sufficient evidence, a supported answer, and neither weak nor ambiguous retrieval. Against its own signals, the gate missed none of those 126. That is not a human miss rate.

Attempt cost of those signal groups, list price, not an invoice:

| Signal group | Runs | Recovery chat calls | Added latency | Estimated cost |
|---|---:|---:|---:|---:|
| Insufficient evidence and an abstention | 40 | 160 | 407 s | $0.025 |
| Insufficient evidence and a specific answer | 10 | 42 | 80 s | $0.007 |
| Ambiguous margin on a judge-accepted answer | 10 | 20 | 36 s | $0.004 |

These are not yet "unnecessary" costs. The abstention group contains both the likely gating waste and three of the gold-improved runs.

## Candidates, not selected

Scored only as "which of the 60 would this rule skip", including which automatic-gold improvements it would drop. No rule is adopted.

- Stop recovering an explicit abstention when evidence is insufficient. Skips 40. Drops the gold improvements `dku-053`, `dku-055`, and `dku-012`.
- Do not recover a judge-accepted supported answer only because the margin is tight. Skips 10. Drops the gold improvement `dku-045`.
- Require two warning signals. Skips 57. Keeps `dku-053` and `seed-009` under automatic gold, and drops `dku-055`, `dku-012`, and `dku-045`.

Stopping every abstention would also stop the expand successes that started as abstentions. The runtime cannot see which of those abstentions were answerable.
