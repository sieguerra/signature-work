# Results note (draft)

> **Draft for Sean to check and rewrite.** Claude compiled this on 2026-10-15
> at Sean's request (issue #101). Every number is copied from the named
> `comparison.json` or rescore report, and nothing here is a conclusion.
> Sean owns the claims: check each figure against its folder and rewrite the
> text in your own words before citing it.

The question the software records: does evaluation-guided recovery
(`eval_guided`, the loop) change answer quality relative to plain RAG
(`baseline`), and at what cost? Each benchmark runs both conditions on the
same questions with `gpt-4o-mini`.

## What "verification" means here

The runtime verdict (`improved`, `unchanged`, `still_failing`, `degraded`) is
`verify_runtime` in `src/swrag/verification/runtime.py`. It compares the
judge's two flags (`evidence_sufficient`, `answer_supported`) before and
after recovery. The same LLM judge produces both sides. It never reads gold.
Agreement between the judge and a person is measured in
`experiments/judge-audit/20261011/score.json` (issue #38): sufficient 39/40
and supported 39/40. Those human labels were confirmed after an AI review and
are not independent of it.

## Snapshots

| Folder | Config | Questions (answerable / unanswerable) | top_k | max_recoveries |
|:--|:--|:--|:--|:--|
| `20260910T070623` | `v1_baseline_vs_loop` (Harbor, older loop) | 32 (22 / 10) | 4 | 1 |
| `20260927T151157` | `v3_kestrel_expand_vs_loop` (stress test) | 5 (4 / 1) | 1 | 2 |
| `20260927T151544` | `v3_dku_expand_vs_loop` (stress test) | 5 (4 / 1) | 1 | 2 |
| `20261010T202849` | `v4_kestrel_full_current_loop` | 16 (12 / 4) | 4 | 2 |
| `20261010T203115` | `v4_dku_full_current_loop` | 40 (30 / 10) | 4 | 2 |
| `20261010T203121` | `v4_harbor_full_current_loop` | 32 (22 / 10) | 4 | 2 |
| `20261015-prompt-hardened-kestrel` | v4 Kestrel, hardened prompts (#161) | 16 (12 / 4) | 4 | 2 |
| `20261015-prompt-hardened-dku` | v4 DKU, hardened prompts | 40 (30 / 10) | 4 | 2 |
| `20261015-prompt-hardened-harbor` | v4 Harbor, hardened prompts, gold after #158 | 32 (23 / 9) | 4 | 2 |

`20260910T070623` is the older V1 loop. It is kept as recorded, not
rewritten.

## Quality and cost, as stored

Answerable contains-answer, unanswerable abstention rate, mean latency and
chat calls. Each cell is baseline / eval_guided.

| Folder | Contains-answer | Unanswerable abstention | Mean latency ms | Chat calls |
|:--|:--|:--|:--|:--|
| `20260910T070623` | 0.864 / 0.864 | 0.400 / 0.400 | 3261 / 7109 | 32 / 78 |
| `20260927T151157` | 0.250 / 0.750 | 1.000 / 1.000 | 4213 / 17190 | 5 / 22 |
| `20260927T151544` | 0.500 / 1.000 | 1.000 / 1.000 | 6699 / 11600 | 5 / 22 |
| `20261010T202849` | 0.917 / 0.917 | 1.000 / 1.000 | 2512 / 5977 | 16 / 48 |
| `20261010T203115` | 0.767 / 0.800 | 0.800 / 0.900 | 2797 / 6581 | 40 / 130 |
| `20261010T203121` | 0.864 / 0.864 | 0.400 / 0.500 | 2768 / 5940 | 32 / 92 |
| `20261015-prompt-hardened-kestrel` | 1.000 / 1.000 | 1.000 / 1.000 | 3823 / 10763 | 16 / 48 |
| `20261015-prompt-hardened-dku` | 0.967 / 1.000 | 1.000 / 1.000 | 4334 / 11131 | 40 / 130 |
| `20261015-prompt-hardened-harbor` | 1.000 / 1.000 | 0.667 / 0.667 | 4745 / 9869 | 32 / 96 |

Retrieval hit rate is 1.0 on both conditions in every full-set run. The two
27 September stress tests (top_k 1) are the exceptions: 0.75 / 1.0 for
Kestrel and 0.25 / 0.75 for DKU.

Three cautions for reading this table:
- The three 2026-10-15 runs ran at the same time, so their latencies are not
  comparable with the others. Their median latency is 3535 / 6661 (Kestrel),
  3781 / 7695 (DKU) and 4445 / 7740 (Harbor).
- Before #153 the loop reused the baseline's cached query embeddings, so
  embedding calls in the older folders are not comparable either.
- The stored numbers before 2026-10-15 used the older scorer and gold.

## Rescored with the current scorer and gold (no model calls)

`experiments/rescored/scoring-v3-gold-2026-10-15/report.md` rescored the same
stored answers. Three things changed: clock ranges (#130), refusal phrasing
(#131), and the #158 gold rules (seed-007 relabelled answerable, false-premise
rejections counted as abstentions, the seed-009 trap).

| Folder | Contains-answer, stored to rescored | Unanswerable abstention, stored to rescored |
|:--|:--|:--|
| `20260910T070623` | 0.864 / 0.864 to 1.000 / 1.000 | 0.400 / 0.400 to 0.667 / 0.667 |
| `20261010T202849` | 0.917 / 0.917 to 1.000 / 1.000 | 1.000 / 1.000, no change |
| `20261010T203115` | 0.767 / 0.800 to 0.967 / 1.000 | 0.800 / 0.900 to 1.000 / 1.000 |
| `20261010T203121` | 0.864 / 0.864 to 1.000 / 1.000 | 0.400 / 0.500 to 0.667 / 0.778 |

## Verification vs gold

Two agreement rules are reported (#132, #155):
- **F1 sign.** The verdict agrees when it moves the same way as gold F1.
- **Rank rule.** Each answer is ranked correct, abstained, or wrong, and the
  verdict agrees when it matches the gold rank transition.

| Folder | Verified runs | Verdicts | F1-sign agree / disagree | Rank rule, answerable agree / n | Rank rule, unanswerable agree / n |
|:--|:--|:--|:--|:--|:--|
| `20260910T070623` | 5 | still_failing 5 | not recorded | | |
| `20261010T203115` | 14 | unchanged 3, improved 1, still_failing 10 | 14 / 0 | | |
| `20261010T203121` | 7 | unchanged 1, still_failing 6 | 6 / 1 | | |
| `20261015-prompt-hardened-dku` | 14 | unchanged 3, improved 1, still_failing 10 | 14 / 0 | 4 / 4 | 0 / 10 |
| `20261015-prompt-hardened-harbor` | 8 | unchanged 1, improved 1, still_failing 6 | 7 / 1 | 1 / 1 | 1 / 7 |
| `20261015-prompt-hardened-kestrel` | 4 | still_failing 4 | 4 / 0 | none | 0 / 4 |

Almost all of the unanswerable disagreements under the rank rule are one
case: the runtime labels a kept abstention `still_failing` (evidence still
missing), while the rank rule labels it `unchanged` (correct both times).

Reporting choice, made on Sean's instruction: lead with the answerable-only
rank agreement and explain the unanswerable cell as a vocabulary difference.

## Limits

- The corpora are small and hand-built (Harbor, Kestrel), plus a DKU
  collection of 14 documents.
- There is one generator and judge model, `gpt-4o-mini`, behind a
  non-OpenAI-hosted endpoint (`base_url` in each snapshot).
- The judge is an LLM. Its human agreement sample is 40 calls and is not
  independent of an AI review (#38).
- Verification is the flag comparison in `verify_runtime`, not a gold check.
- The 27 September runs are 5-question stress tests at top_k 1.
- The recovery-gate review has one human reviewer, and no inter-rater
  agreement is measured (#107).
- seed-007, the premise-rejection phrases and the seed-009 trap were decided
  on 2026-10-15 under #142, after these answers were generated.
- Every table here is one run per configuration. There are no repeated
  seeds and no confidence intervals.

## Depth sweep (added 2026-10-16)

`experiments/rescored/v5-sweep-20261015/summary.md` summarizes nine live
runs (`20261015-v5-<collection>-r<1,2,3>`, commit `b125064`). Each runs
baseline and loop at top_k 1, 2 and 4, plus a plain baseline at top_k 8.

Contains-answer rate, mean of three repeats:

| | base k1 | loop k1 | base k2 | loop k2 | base k4 | loop k4 | base k8 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| Harbor | 0.870 | 1.000 | 0.913 | 0.986 | 1.000 | 1.000 | 1.000 |
| DKU | 0.809 | 0.966 | 0.933 | 1.000 | 0.966 | 1.000 | 1.000 |
| Kestrel | 0.917 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

- Across the 27 loop runs, the loop fixed 49 questions and broke 6 relative
  to the same-depth baseline.
- Of those 6, five are correct premise rejections the phrase lists miss, and
  one is real (seed-007 at k2).
- The k8 baseline costs 39 to 47 percent of the loop at k1.
- The rank-rule verdict agrees on 59 of 73 answerable recoveries.
- The gold-029 relabelling case is described in #164.
- One run dropped dku-020 after an API timeout.

