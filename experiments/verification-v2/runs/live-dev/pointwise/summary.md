# Verification benchmark (pointwise)

Protocol `verification-v2-2026-10-06`. Seed 20261006.

This file is an offline experiment record. It does not change runtime verification.

| Metric | V1 | V2 |
|---|---:|---:|
| accuracy | 0.231 | 0.692 |
| macro_f1 | 0.289 | 0.481 |
| improved_precision | 0.500 | 0.500 |
| improved_recall | 1.000 | 1.000 |
| false_improvement_rate | 0.500 | 0.500 |

Decided coverage: 1.000 on n=13.
Uncertainty rate: 0.000.
Unavailable rate: 0.000.
Position inconsistency: n/a.

V1 confusion rows are gold and columns are predictions, in the order
improved, unchanged, still_failing, degraded.

```
{
  "improved": {
    "improved": 2,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  },
  "unchanged": {
    "improved": 2,
    "unchanged": 0,
    "still_failing": 8,
    "degraded": 0
  },
  "still_failing": {
    "improved": 0,
    "unchanged": 0,
    "still_failing": 1,
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
    "improved": 2,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  },
  "unchanged": {
    "improved": 2,
    "unchanged": 7,
    "still_failing": 1,
    "degraded": 0
  },
  "still_failing": {
    "improved": 0,
    "unchanged": 1,
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

Config: `{"call_model": true, "candidate": "pointwise", "live_max_recoveries": 2, "live_top_k": 1, "model": "gpt-4o-mini", "n_examples": 13, "panel": "live", "protocol": "verification-v2-2026-10-06", "seed": 20261006, "split": "dev"}`
