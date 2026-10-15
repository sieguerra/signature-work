# Rescored benchmark snapshots

Frozen snapshots in `experiments/results/` are unchanged. These are the same stored answers
scored again with the current offline scorer (see `scripts/rescore_snapshots.py`). No model calls.

## 20260910T070623 (v1_baseline_vs_loop)

| Metric | Baseline stored | Baseline rescored | Eval stored | Eval rescored |
|:--|:--|:--|:--|:--|
| answerable_exact_match | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| answerable_contains_answer | 0.8636 | 1.0000 | 0.8636 | 1.0000 |
| answerable_f1 | 0.2169 | 0.2548 | 0.2190 | 0.2568 |
| unanswerable_abstention_rate | 0.4000 | 0.6667 | 0.4000 | 0.6667 |
| answerable_abstention_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Questions whose score changed: 14

- `gold-020` (baseline): contains True to True, abstained False to False, f1 0.2667 to 0.2857
- `seed-011` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `seed-012` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `gold-025` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.2353
- `seed-007` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.1667
- `seed-008` (baseline): contains False to True, abstained False to True, f1 0.0 to 1.0
- `gold-030` (baseline): contains False to True, abstained False to True, f1 0.0 to 1.0
- `gold-020` (eval_guided): contains True to True, abstained False to False, f1 0.2667 to 0.2857
- `seed-011` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `seed-012` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `gold-025` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.2353
- `seed-007` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.1667
- `seed-008` (eval_guided): contains False to True, abstained False to True, f1 0.0 to 1.0
- `gold-030` (eval_guided): contains False to True, abstained False to True, f1 0.0 to 1.0

## 20260927T151157 (v3_kestrel_expand_vs_loop)

| Metric | Baseline stored | Baseline rescored | Eval stored | Eval rescored |
|:--|:--|:--|:--|:--|
| answerable_exact_match | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| answerable_contains_answer | 0.2500 | 0.7500 | 0.7500 | 1.0000 |
| answerable_f1 | 0.0833 | 0.1733 | 0.2512 | 0.3226 |
| unanswerable_abstention_rate | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| answerable_abstention_rate | 0.5000 | 0.2500 | 0.0000 | 0.0000 |

Questions whose score changed: 3

- `ka-020` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.2857
- `ka-023` (baseline): contains False to True, abstained True to False, f1 0.0 to 0.0741
- `ka-020` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.2857

## 20260927T151544 (v3_dku_expand_vs_loop)

| Metric | Baseline stored | Baseline rescored | Eval stored | Eval rescored |
|:--|:--|:--|:--|:--|
| answerable_exact_match | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| answerable_contains_answer | 0.5000 | 0.5000 | 1.0000 | 1.0000 |
| answerable_f1 | 0.1709 | 0.1709 | 0.3334 | 0.3334 |
| unanswerable_abstention_rate | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| answerable_abstention_rate | 0.5000 | 0.5000 | 0.0000 | 0.0000 |

Questions whose score changed: 0


## 20261010T202849 (v4_kestrel_full_current_loop)

| Metric | Baseline stored | Baseline rescored | Eval stored | Eval rescored |
|:--|:--|:--|:--|:--|
| answerable_exact_match | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| answerable_contains_answer | 0.9167 | 1.0000 | 0.9167 | 1.0000 |
| answerable_f1 | 0.2677 | 0.2955 | 0.2698 | 0.2976 |
| unanswerable_abstention_rate | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| answerable_abstention_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Questions whose score changed: 2

- `ka-005` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `ka-005` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.3333

## 20261010T203115 (v4_dku_full_current_loop)

| Metric | Baseline stored | Baseline rescored | Eval stored | Eval rescored |
|:--|:--|:--|:--|:--|
| answerable_exact_match | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| answerable_contains_answer | 0.7667 | 0.9667 | 0.8000 | 1.0000 |
| answerable_f1 | 0.2091 | 0.2531 | 0.2061 | 0.2501 |
| unanswerable_abstention_rate | 0.8000 | 1.0000 | 0.9000 | 1.0000 |
| answerable_abstention_rate | 0.0333 | 0.0333 | 0.0000 | 0.0000 |

Questions whose score changed: 17

- `dku-006` (baseline): contains False to True, abstained False to False, f1 0.1333 to 0.3077
- `dku-007` (baseline): contains False to True, abstained False to False, f1 0.25 to 0.2857
- `dku-008` (baseline): contains True to True, abstained False to False, f1 0.1111 to 0.2
- `dku-011` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.2222
- `dku-015` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.2667
- `dku-016` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.2667
- `dku-017` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.2667
- `dku-032` (baseline): contains False to True, abstained False to True, f1 0.0 to 1.0
- `dku-034` (baseline): contains False to True, abstained False to True, f1 0.0 to 1.0
- `dku-006` (eval_guided): contains False to True, abstained False to False, f1 0.1333 to 0.3077
- `dku-007` (eval_guided): contains False to True, abstained False to False, f1 0.25 to 0.2857
- `dku-008` (eval_guided): contains True to True, abstained False to False, f1 0.1111 to 0.2
- `dku-011` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.2222
- `dku-015` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.2667
- `dku-016` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.2667
- `dku-017` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.2667
- `dku-032` (eval_guided): contains False to True, abstained False to True, f1 0.0 to 1.0

## 20261010T203121 (v4_harbor_full_current_loop)

| Metric | Baseline stored | Baseline rescored | Eval stored | Eval rescored |
|:--|:--|:--|:--|:--|
| answerable_exact_match | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| answerable_contains_answer | 0.8636 | 1.0000 | 0.8636 | 1.0000 |
| answerable_f1 | 0.2190 | 0.2568 | 0.2190 | 0.2568 |
| unanswerable_abstention_rate | 0.4000 | 0.6667 | 0.5000 | 0.7778 |
| answerable_abstention_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Questions whose score changed: 14

- `gold-020` (baseline): contains True to True, abstained False to False, f1 0.2667 to 0.2857
- `seed-011` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `seed-012` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `gold-025` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.2353
- `seed-007` (baseline): contains False to True, abstained False to False, f1 0.0 to 0.1667
- `seed-008` (baseline): contains False to True, abstained False to True, f1 0.0 to 1.0
- `gold-030` (baseline): contains False to True, abstained False to True, f1 0.0 to 1.0
- `gold-020` (eval_guided): contains True to True, abstained False to False, f1 0.2667 to 0.2857
- `seed-011` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `seed-012` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.3333
- `gold-025` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.2353
- `seed-007` (eval_guided): contains False to True, abstained False to False, f1 0.0 to 0.1667
- `seed-008` (eval_guided): contains False to True, abstained False to True, f1 0.0 to 1.0
- `gold-030` (eval_guided): contains False to True, abstained False to True, f1 0.0 to 1.0

