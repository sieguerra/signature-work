# Verification benchmark (surface)

Protocol `verification-v2-2026-10-06`. Seed 20261006.

This file is an offline experiment record. It does not change runtime verification.

| Metric | V1 | V2 |
|---|---:|---:|
| accuracy | 0.364 | n/a |
| macro_f1 | 0.369 | n/a |
| improved_precision | 0.750 | n/a |
| improved_recall | 1.000 | n/a |
| false_improvement_rate | 0.250 | n/a |

Decided coverage: 0.000 on n=11.
Uncertainty rate: 1.000.
Unavailable rate: 0.000.
Position inconsistency: n/a.

V1 confusion rows are gold and columns are predictions, in the order
improved, unchanged, still_failing, degraded.

```
{
  "improved": {
    "improved": 3,
    "unchanged": 0,
    "still_failing": 0,
    "degraded": 0
  },
  "unchanged": {
    "improved": 1,
    "unchanged": 0,
    "still_failing": 6,
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

Config: `{"call_model": false, "candidate": "surface", "live_max_recoveries": 2, "live_top_k": 1, "model": null, "n_examples": 11, "panel": "archive", "protocol": "verification-v2-2026-10-06", "seed": 20261006, "split": "all"}`
