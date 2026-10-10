# Verification v2

Shadow research on whether a second verifier can tell, better than Verification v1, that a recovery actually improved a response. v2 does not choose recovery, stop recovery, or replace the stored v1 verdict.

Protocol version: `verification-v2-2026-10-06`. Seed: `20261006`.

## Verification v1

`verify_runtime` in `src/swrag/verification/runtime.py` compares two `RuntimeEvaluation` values. It does not see the answer text, the evidence text, or gold.

1. If `evidence_sufficient` goes from false to true, the outcome is `improved`.
2. If it goes from true to false, the outcome is `degraded`.
3. Otherwise `answer_supported is True` is compared the same way. Null support is not false, so null to null does not count as a change.
4. If the after-state has `answer_supported is False`, or evidence is still insufficient, the outcome is `still_failing`.
5. Otherwise the outcome is `unchanged`.

The loop then overrides the run-level verdict. If the final answer abstains and the final evidence is not sufficient, `run_with_recovery` stores `still_failing` even when the flag comparison would say something else. Attempt verification is the step comparison and does not get that override. A top-level verdict compares the first pass with the final state. It does not say which attempt caused the change.

Abstention text is `I do not know based on the retrieved documents.` The controller's `is_abstention` is a prefix check. A model can generate that sentence with `answer_relation: generated`. That is not an `abstained` action. A probe evaluation has `answer_supported: null` and is not an answer judgment. A carried evaluation is the previous judgment, not a new one. `executed: false` means the action was selected and not applied.

The grounding judge and the generator both use the configured chat model (`LLMJudge` and `OpenAIGenerator` read the same provider config). They can be the same model. The judge prompt is the system string in `src/swrag/evaluation/llm_judge.py`. After the model returns, `constrain_support_to_evidence` forces `answer_supported` false when a checkable fact (clock time, email, ordinal, specification token, or a number of three or more digits) is absent from the chunk text. Abstentions are left alone.

v1 is consumed by the loop's stop rule, the trace's `verification` field, Overview, and the flight recorder. Offline, `experiments/benchmark.py` `_verdict_agrees` treats v1 as correct when `improved` lines up with a positive gold F1 delta, `degraded` with a negative delta, `unchanged` with a zero delta, and `still_failing` with a non-positive delta. That agreement rule is not the gold label used here.

## What "improved" means here

Gold is the existing offline scorer in `src/swrag/evaluation/scoring.py`: normalized contains-answer for answerable questions, and abstention for unanswerable questions. Exact match and token F1 are recorded by the experiment runner and are not the transition label. A higher F1 that still does not contain a gold answer stays a failure.

Ranks, fixed before any v2 score:

| Situation | Rank |
|---|---|
| Answerable and the answer contains a gold string and is not an abstention | 2 |
| Unanswerable and the answer abstains | 2 |
| Answerable and the answer abstains | 1 |
| Anything else | 0 |

The transition label:

| Rank change | Label |
|---|---|
| After higher than before | `improved` |
| After lower than before | `degraded` |
| Both rank 2 | `unchanged` |
| Both below rank 2 and equal | `still_failing` |

So a wrong answer that becomes a different wrong answer is `still_failing`. Two correct answers are `unchanged`. An answerable correct answer that becomes an abstention is `degraded`. An unanswerable invented answer that becomes an abstention is `improved`. An answerable unsupported answer that becomes an abstention is `improved` on this scale: rank 0 to rank 1. It is safer and still not the right answer. The label does not call that pair `unchanged`.

This inherits the known weakness of contains-answer. A wrong answer that quotes the gold string counts as correct. A correct paraphrase that does not contain the gold string counts as wrong. `subtle_degradation` in the adversarial file is that second case, and the label stays `degraded` rather than being edited after the fact.

Gold scores the text the user received. Controller versus generated abstention is a schema fact for the verifier, not a second gold class. Both abstentions on an unanswerable question are `unchanged`.

## What v2 is allowed to see

The question, both answers, the evidence text stored on the trace, `answer_relation`, `evidence_relation`, `evaluation_source`, the action, and whether the attempt executed. It does not see `answerable`, gold answers, supporting document ids, exact match, contains-answer, F1, the v1 verdict, or the experiment summary. `verifier_view` rejects those keys if they appear on a chunk. Probe and carried evaluations are visible as `evaluation_source` and are not copied in as `answer_supported`.

## Candidates

Thresholds below were chosen before scoring.

`surface` (`surface-2026-10-06`) is a negative control. Answer text alone cannot tell a correct rewrite from a different mistake, so it always returns `uncertain`. It is not eligible for selection.

`coverage` (`coverage-2026-10-06`) is deterministic. A non-abstaining answer is grounded (rank 2) when it has at least one content token, at least half of those tokens occur in its own evidence, and every checkable fact from the existing span checker occurs in that evidence. An abstention with no invented checkable fact is rank 1. Anything else is rank 0. Missing evidence is `unavailable`, not a class. Identical answer text whose ranks disagree is `uncertain`, so a wider evidence set cannot by itself be called an improvement.

`pointwise` (`pointwise-2026-10-06`) asks the rubric once for the before state and once for the after state. The model does not see both answers together. Structured fields set the same ranks: a fully supported answer that the evidence can support is rank 2, an abstention when the evidence cannot answer is rank 1, and an abstention that invents a fact or abstains when the evidence can answer is rank 0. The comparison is the deterministic rank rule. Free-text rationale codes are stored and do not decide the label. There is no numeric confidence.

`pairwise` (`pairwise-2026-10-06`) asks which response is better under the same rubric, in both orders. `equivalent` maps to `unchanged`. `both_insufficient` maps to `still_failing`. If the two orders disagree, the result is `uncertain`. One order is not silently kept.

Model failures, empty output, invalid JSON, refusals, rate limits, and unknown labels are `unavailable`. They are not mapped to `unchanged` or `still_failing`.

Not built, because they do not fit this measurement:

- A preference prompt that rewards helpfulness or length, as in an unadapted MT-Bench judge.
- RAGAS context recall, which needs a reference answer inside the metric.
- A fine-tuned judge. There is no training split large enough to fit one without using the test questions.
- A five-call ensemble. There is no calibration set, and the cost would dominate a two-call judge.
- A self-reported probability. It would not be calibrated.

## Research that set those choices

Zheng et al. (NeurIPS 2023, [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)) show position bias and verbosity bias in LLM judges, and they treat a decision that flips when the order is swapped as a tie. Pairwise v2 does that. Pointwise v2 avoids a single paired prompt so there is no order to swap. The rubric forbids credit for length, style, or confidence.

Panickssery, Bowman, and Feng (NeurIPS 2024, [arXiv:2404.13076](https://arxiv.org/abs/2404.13076)) show that a judge can prefer text from its own model. This project has one configured chat model, shared by generation and the v1 judge. A second judge model was not available, so self-preference is not isolated here. Same-model overlap is a limitation, not a measured bias coefficient.

Es et al. (RAGAS, [arXiv:2309.15217](https://arxiv.org/abs/2309.15217)) separate faithfulness to the retrieved context from answer correctness. FActScore (Min et al., EMNLP 2023, [arXiv:2305.14251](https://arxiv.org/abs/2305.14251)) is a precision over atomic claims and does not by itself penalize abstaining. Coverage v2 is a cheap faithfulness signal. It is not treated as correctness until the gold labels say so.

SQuAD 2.0 (Rajpurkar, Jia, and Liang, ACL 2018, [arXiv:1806.03822](https://arxiv.org/abs/1806.03822)) scores abstention as correct on unanswerable questions and incorrect on answerable ones. The rank table follows that, with the extra middle rank for an answerable abstention.

## Data and split

Gold questions on disk:

| Set | Questions | Answerable | Unanswerable |
|---|---:|---:|---:|
| Harbor `datasets/gold/questions.jsonl` | 32 | 22 | 10 |
| DKU questions | 40 | 30 | 10 |
| Each of eight industry `questions.jsonl` files | 16 | 12 | 4 |
| DKU and Kestrel `first-pass-fail.jsonl` | 5 each | 4 | 1 |
| DKU `recovery.jsonl` | 12 | 9 | 3 |
| Kestrel `recovery.jsonl` | 3 | 2 | 1 |

Committed experiment comparisons that actually contain a recovery transition:

| Run | Corpus | Transitions | v1 verdicts | Actions |
|---|---|---:|---|---|
| `20260910T070623` | Harbor | 5 | 5 `still_failing` | rewrite |
| `20260927T151157` | Kestrel | 3 | 2 `improved`, 1 `still_failing` | expand |
| `20260927T151544` | DKU | 3 | 2 `improved`, 1 `still_failing` | expand |

Eleven run-level transitions. No attempt-level record survives: the trace files are gone, so evidence text is gone. Those eleven are the archive panel. They are not the held-out test. Coverage and the model judges return `unavailable` on them because evidence is unknown.

The live panel, if generated, uses `top_k=1` and `max_recoveries=2`, which is the operating point in the 2026-09-27 configs and the note on the recovery questions. The product default remains `top_k=4`. Development is Kestrel `first-pass-fail.jsonl` plus `recovery.jsonl` (8 questions). The held-out test is DKU `first-pass-fail.jsonl` plus `recovery.jsonl` (17 questions). The two id sets are disjoint. Harbor is not used to choose a candidate. No random reshuffle: a four-class stratified split of eleven rows would not hold.

Completed traces are the only ones on disk. A run that throws before `write_run` leaves no file. The benchmark does not see those.

## Metrics and promotion

Primary: false-improvement rate (predicted `improved` that are not gold-`improved`) and improved precision. The rate is undefined when the verifier never says `improved`. It is not reported as zero.

Also: four-class accuracy on decided rows, strict accuracy that counts uncertain and unavailable as wrong, macro and weighted F1, the confusion matrix in the order improved / unchanged / still failing / degraded, per-class precision and recall, coverage, and breakdowns by attempt versus run, action, answerable versus unanswerable, and stored failure class. Missing diagnosis is left missing.

Uncertainty is a 90% paired bootstrap percentile interval, 1000 resamples, seed `20261006`, on rows both verifiers decided. McNemar's exact test is reported on the discordant correct/incorrect pairs.

Promotion, applied to the held-out live test only:

- Under 8 decided rows, or coverage under 0.5: `RESEARCH ONLY`, unless gold leaked or runtime behavior changed, which is `REJECT`.
- False-improvement rate or improved precision worse than v1, with at least 8 decided rows: `REJECT`.
- Improved precision at least 0.10 higher, false-improvement rate lower, macro F1 not more than 0.05 worse, at most 4 model calls, position inconsistency at most 0.20 when a pairwise judge was used, at least 3 answerable and 3 unanswerable rows, and the precision-difference interval entirely above 0: `REPLACE V1`.
- The same point estimates without the interval or the slice sizes: `GUARDED READY`.
- A smaller strict improvement that is not a regression: `SHADOW READY`.
- Otherwise: `RESEARCH ONLY`.

`surface` cannot be selected. Selection uses development summaries only.

## Human review

No human labels were collected. `blind_review_row` writes the question, both evidence texts, and both answers. It does not write v1, v2, or the gold label. A reviewer would use the same rank table as the gold rule and would be told that contains-answer can miss a paraphrase. That review is future work.

## How to run

```bash
python scripts/run_verification_benchmark.py --panel archive --candidate coverage
python scripts/run_verification_benchmark.py --panel adversarial --candidate all
python scripts/run_verification_benchmark.py --panel live --split dev --candidate all --generate --call-model
python scripts/run_verification_benchmark.py --panel live --split test --candidate all --generate --call-model
```

`--call-model` is what spends judge calls. `--generate` runs the existing recovery loop and writes traces under `experiments/verification-v2/traces/`, which is gitignored. The cache key includes the candidate, prompt version, parser version, model, temperature, order, and verifier view. Results land in `experiments/verification-v2/runs/`. Historical files in `experiments/results/` are not rewritten.

Cost in `cost_latency.json` is a list-rate estimate for `gpt-4o-mini` at $0.15 per million input tokens and $0.60 per million output tokens, from the OpenAI model page (checked 2026-10-06). It is not an invoice. Other models leave cost null.

## Results

Scored once. Prompts were not edited after the Kestrel development scores. The held-out DKU run was not used to change a threshold. A three-item development repeat, with the cache off, was run after the holdout and did not change any prompt.

### Archive baseline, Verification v1 only

Eleven historical run-level transitions. Evidence text is gone, so coverage and both model judges are `unavailable` (coverage 0). v1 against the rank labels:

| | |
|---|---:|
| n | 11 |
| accuracy | 0.364 |
| macro F1 | 0.369 |
| improved precision | 0.750 |
| improved recall | 1.000 |
| false-improvement rate | 0.250 |

Gold labels: 7 unchanged, 3 improved, 1 still failing, 0 degraded. v1 called 6 of the 7 unchanged cases `still_failing` and 1 of them `improved`. The false improvement is one case. This panel is too small, and it is not the holdout.

### Adversarial probe, coverage only

Seventeen constructed cases, kept out of the holdout metric. Coverage decided all 17. Accuracy 0.706, improved precision 0.750, false-improvement rate 0.250, degraded recall 1.000 on the five degraded cases. The false improvement is `evidence_up_answer_down`: a wrong answer that copies a longer evidence passage is called grounded. Coverage also missed `distractor_context` and `partial_support`, both gold-improved, because the wrong answer already overlapped the evidence. v1 has no flags on these cases, so there is no v1 comparison here.

### Live development, Kestrel, top_k 1

Eight questions were run. Four of them recovered, producing thirteen transitions. Selection, before DKU was scored: pairwise, because its false-improvement rate was 0.000 against 0.500 for coverage and pointwise. Pointwise matched coverage on all 13 labels. Pairwise was uncertain on 2 of 13 because the two orders disagreed (inconsistency 0.154).

### Live holdout, DKU, top_k 1

Seventeen questions were run. Seven questions produced an executed recovery, and those seven produced 22 transitions (15 attempt-level, 7 run-level). Ten questions never recovered and are not in this table. There is no degraded case. On this holdout, coverage, pointwise, and pairwise returned the same label on every row. The model judges added calls and did not change a decision.

Pooled, treating the 22 rows as if they were independent:

| Metric | V1 | V2 |
|---|---:|---:|
| Accuracy | 0.409 | 0.864 |
| Macro F1 | 0.392 | 0.632 |
| Improved precision | 0.667 | 1.000 |
| Improved recall | 1.000 | 1.000 |
| False-improvement rate | 0.333 | 0.000 |
| Still-failing recall | 1.000 | 0.000 |
| Unchanged recall | 0.000 | 1.000 |
| Answerable accuracy | 1.000 (n=9) | 0.667 (n=9) |
| Unanswerable accuracy | 0.000 (n=13) | 1.000 (n=13) |
| Model calls per row | 0 | 0 coverage, 2 pointwise, 2 pairwise |
| Median latency | 0 | 3.9 s pointwise, 2.9 s pairwise |
| P95 latency | 0 | 4.6 s pointwise, 3.6 s pairwise |
| Estimated cost, 22 rows | 0 | $0.0059 pointwise, $0.0073 pairwise |

The paired bootstrap 90% interval for improved precision (v2 minus v1) on these 22 rows is 0.091 to 0.625. McNemar's exact test on discordant rows is p=0.021 (v1 only correct 3, v2 only correct 13). The pre-registered `recommend` function returns `REPLACE V1` on this pooled table.

That conclusion does not survive the breakdowns the protocol already required.

Run level only, one row per question, n=7. Improved precision is 1.000 for v1 and for v2. False-improvement rate is 0.000 for both. The precision difference interval is 0 to 0. v2 accuracy is 1.000 and v1 accuracy is 0.429 because v1 labels a repeated correct abstention `still_failing` and v2 labels it `unchanged`. n=7 is under the promotion minimum of 8.

Attempt level is where v1's three false improvements sit: an expand step on an unanswerable question whose answer text did not become better. v2 called those `unchanged`. The same attempt slice is where v2 is wrong: three answerable rewrites whose answers stayed wrong are gold `still_failing`, v1 says `still_failing`, and v2 says `unchanged` because both sides received the same non-zero rank. Answerable accuracy favors v1 (1.000 against 0.667). Unanswerable accuracy favors v2 (1.000 against 0.000).

The 22-row interval is too narrow. Rows from the same question are not independent, and 13 of the 22 gold labels are `unchanged`.

### Other checks

Position swaps on the holdout: 0 disagreements in 22 pairwise judgments. On development: 2 of 13. The holdout agreement did not produce a label coverage would not have produced.

Repeatability: three development transitions, pairwise, two calls, cache off, temperature 0. All three labels matched, including the one `improved` label. That is not a variance estimate.

Self-preference: not isolated. Generated answers and both judges used `gpt-4o-mini`. Controller abstentions are tagged `abstain` and were not generated by that model.

No human labels were collected.

### Recommendation

`RESEARCH ONLY`.

The pooled rule says replace v1. The run-level primary metrics are a tie, the answerable slice gets worse, still-failing recall at attempt level drops from 1 to 0, the model judges do not beat the deterministic overlap rule on this holdout, and the adversarial probe still has a false improvement when a wrong answer copies new evidence. That is not evidence to replace the runtime verifier, and it is not yet evidence to log v2 as a shadow decision-maker. It is evidence that v1's flag comparison and this gold rank table disagree on repeated abstentions, and that a second judge did not resolve the disagreement beyond what token overlap already does.
