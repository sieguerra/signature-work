# Verification benchmark (pointwise)

Protocol `verification-v2-2026-10-06`. Seed 20261006.

This file is an offline experiment record. It does not change runtime verification.

| Metric | V1 | V2 |
|---|---:|---:|
| accuracy | 0.409 | 0.864 |
| macro_f1 | 0.392 | 0.632 |
| improved_precision | 0.667 | 1.000 |
| improved_recall | 1.000 | 1.000 |
| false_improvement_rate | 0.333 | 0.000 |

Decided coverage: 1.000 on n=22.
Uncertainty rate: 0.000.
Unavailable rate: 0.000.
Position inconsistency: n/a.

V1 confusion rows are gold and columns are predictions, in the order
improved, unchanged, still_failing, degraded.

```
{
  "improved": {
    "improved": 6,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  },
  "unchanged": {
    "improved": 3,
    "unchanged": 0,
    "still_failing": 10,
    "degraded": 0
  },
  "still_failing": {
    "improved": 0,
    "unchanged": 0,
    "still_failing": 3,
    "degraded": 0
  },
  "degraded": {
    "improved": 0,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  }
}
```

V2 confusion:

```
{
  "improved": {
    "improved": 6,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  },
  "unchanged": {
    "improved": 0,
    "unchanged": 13,
    "still_failing": 0,
    "degraded": 0
  },
  "still_failing": {
    "improved": 0,
    "unchanged": 3,
    "still_failing": 0,
    "degraded": 0
  },
  "degraded": {
    "improved": 0,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  }
}
```

Config: `{"call_model": true, "candidate": "pointwise", "live_max_recoveries": 2, "live_top_k": 1, "model": "gpt-4o-mini", "n_examples": 22, "panel": "live", "protocol": "verification-v2-2026-10-06", "seed": 20261006, "split": "test"}`
