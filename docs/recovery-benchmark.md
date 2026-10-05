# Recovery benchmark protocol

Frozen before the expanded run was scored. The runtime recovery policy, the
Verification v1 judge, and the Verification v2 prompts are unchanged.

## Operating point

Test Console loop defaults:

- mode `loop`
- `top_k` 4
- `max_recoveries` 2
- chat model and embedding model from the existing environment

This is not the Phase 6 `top_k` 1 setting. That setting is left as a historical
operating point. It is not reused here to create more recovery cases.

## Two datasets

The research benchmark is the registered gold questions, except the corpus
`recovery-demo`. That corpus is a visual demonstration. Its manifest sets
`benchmark` to false. The runner raises if a demo question is offered for
generation, and the scorer raises if one is offered for a metric.

## Independent sample

The independent sample is one user question, one logical run. Attempt rows are
stored and can be counted, and they are not the sample size. A run with two
recovery actions is one question.

An exact duplicate question is kept once. No exact duplicates were found in
the registered files. Near duplicates are questions whose token Jaccard is at
least 0.9. They are placed in the same panel. None were found at that threshold.

## Gold

Primary label: `gold-rank-2026-10-06`.

This is the Phase 6 rank. An answerable answer is correct when it contains a
gold span and is not an abstention. An unanswerable abstention is correct.
Answerable abstention sits between those. Anything else fails. The transition
is improved, degraded, unchanged, or still failing by comparing the two ranks.
Token F1 inside a rank does not move the label.

Two comparison labels are computed and are not the success definition:

- `gold-f1-0.8-2026-10-06` also treats exact match or token F1 of at least 0.8
  as a textual hit. The threshold was chosen before this run. It does not
  understand a paraphrase such as "five hundred sixty" for "560", and it does
  not call a model.
- `gold-grounded-2026-10-06` drops a textual hit when gold names supporting
  documents and none of those documents are in the evidence.

No semantic model is used as gold. One was not independently validated, and a
model gold label would start to copy the verifier.

## Split

Seed `20261006`. The lead id of a duplicate group is holdout when the first
eight hex digits of `sha256("20261006:" + lead)` modulo 5 equal 0. That is
about one fifth of the questions that Phase 6 has not already scored.

Phase 6 already scored the Kestrel and DKU first-pass-fail and recovery files.
Those questions stay in the analysis panel. They are not a fresh holdout.

The future holdout is listed in `question_split.json` and is not generated and
not scored in this phase. Later Verification v2 work can use it. This phase
does not open it to choose a prompt or a threshold.

## What is reported

Recovery success is the share of applied-recovery logical runs whose primary
label is improved. Unchanged, still failing, degraded, and abstention are
reported separately. Abstention on an unanswerable question can be improved
under the primary rank. Appropriateness is also reported as its own count.

Stored failure class is reported as written. A missing class stays missing.

Verification v1 is the verdict already stored on the trace. Verification v2 is
the frozen pairwise candidate from Phase 6 (`pairwise-2026-10-06`). It is
scored after the traces exist. It is not tuned.

## Human review

The rubric is `docs/recovery-review-rubric.md`. The page is
`tools/recovery-review/index.html`. It loads the blinded sample and does not
receive a suggested label. Labels are not filled by a model.

## Recorded run

Run id `phase7-20261006`. The protocol above was not edited to fit these
numbers.

225 registered questions. Zero exact duplicates. Zero near-duplicates at
Jaccard 0.9. Analysis panel: 186 questions (137 answerable, 49 unanswerable),
all generated. Future holdout reserved and not generated: 39 (30 answerable,
9 unanswerable).

Of the 186, 126 accepted with no recovery. Independent recovered logical
runs: 60. That is below the target of 100. The registered corpora at top-k 4
did not produce more recovery cases. Questions were not paraphrased to raise
the count. Attempt rows: 123. Those rows are not the sample size.

Primary outcomes on the 60, with a 90% bootstrap interval:

- improved 5/60 = 0.083 (0.033 to 0.133)
- unchanged 48/60 = 0.800 (0.717 to 0.883)
- still failing 4/60 = 0.067 (0.017 to 0.117)
- degraded 3/60 = 0.050 (0.017 to 0.100)

Final abstention: 41/60. Unanswerable abstained 40/45. Answerable abstained
1/15.

Action buckets, one label per run: expand 10 (improved 1, unchanged 8,
degraded 1); multi 50 (improved 4, unchanged 40, still failing 4, degraded 2).
Regenerate occurred zero times. Rewrite never occurred as the only action.
Abstain occurred only as the third step of rewrite, then expand, then abstain
(13 runs).

Paths: rewrite then expand, 37 runs, final improved 3. Rewrite then expand
then abstain, 13 runs, final improved 1.

The comparison gold labels agreed with the primary label on all 60 runs.
Neither the F1 rule nor the supporting-document rule changed an outcome.
`dku-008` (14:00-18:00 versus "14:00 to 18:00") stays degraded under both.
That is a label artifact. The gold rules were not edited after the run.

Stored initial `diagnosis_class` is null on all 60 recovered runs. No
retrieval-miss or evidence-insufficiency count is reported for the first
state.

Human labels were not collected. The blinded sample has 60 rows and no chosen
label. Agreement with automatic gold is not measured. One reviewer was not
available, and a model was not used to fill the form.

Verification v1 on the 60, from the stored verdict: accuracy 0.217, improved
precision 0.600, recall 0.600, false-improvement rate 0.400. It predicted
improved 5 times (3 true). It never predicted degraded. It called 40 of 48
unchanged runs still failing.

Frozen pairwise v2, not tuned: strict accuracy 0.833, decided accuracy 0.877
on 57 of 60, improved precision 1.0, recall 0.6, false-improvement rate 0.
It predicted improved 3 times, all true, and it never predicted still failing.
The perfect precision is the result of rarely saying improved. This is not a
reason to replace v1.

The recorded `human_reviewed_subset` has n 0 because of a logical-id join
(`questions` versus `questions.jsonl`). The sample is the same 60 runs, so
that subset is the run-level result. The model was not called again.
