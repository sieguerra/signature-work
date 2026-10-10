# Verification benchmark (coverage)

Protocol `verification-v2-2026-10-06`. Seed 20261006.

This file is an offline experiment record. It does not change runtime verification.

| Metric | V1 | V2 |
|---|---:|---:|
| accuracy | n/a | 0.706 |
| macro_f1 | n/a | 0.692 |
| improved_precision | n/a | 0.750 |
| improved_recall | n/a | 0.500 |
| false_improvement_rate | n/a | 0.250 |

Decided coverage: 1.000 on n=17.
Uncertainty rate: 0.000.
Unavailable rate: 0.000.
Position inconsistency: n/a.

V1 confusion rows are gold and columns are predictions, in the order
improved, unchanged, still_failing, degraded.

```
{
  "improved": {
    "improved": 0,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  },
  "unchanged": {
    "improved": 0,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  },
  "still_failing": {
    "improved": 0,
    "unchanged": 0,
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

V2 confusion:

```
{
  "improved": {
    "improved": 3,
    "unchanged": 2,
    "still_failing": 0,
    "degraded": 1
  },
  "unchanged": {
    "improved": 0,
    "unchanged": 2,
    "still_failing": 0,
    "degraded": 0
  },
  "still_failing": {
    "improved": 1,
    "unchanged": 0,
    "still_failing": 2,
    "degraded": 1
  },
  "degraded": {
    "improved": 0,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 5
  }
}
```

Config: `{"call_model": false, "candidate": "coverage", "live_max_recoveries": 2, "live_top_k": 1, "model": null, "n_examples": 17, "panel": "adversarial", "protocol": "verification-v2-2026-10-06", "seed": 20261006, "split": "all"}`
