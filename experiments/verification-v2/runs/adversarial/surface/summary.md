# Verification benchmark (surface)

Protocol `verification-v2-2026-10-06`. Seed 20261006.

This file is an offline experiment record. It does not change runtime verification.

| Metric | V1 | V2 |
|---|---:|---:|
| accuracy | n/a | n/a |
| macro_f1 | n/a | n/a |
| improved_precision | n/a | n/a |
| improved_recall | n/a | n/a |
| false_improvement_rate | n/a | n/a |

Decided coverage: 0.000 on n=17.
Uncertainty rate: 1.000.
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

Config: `{"call_model": false, "candidate": "surface", "live_max_recoveries": 2, "live_top_k": 1, "model": null, "n_examples": 17, "panel": "adversarial", "protocol": "verification-v2-2026-10-06", "seed": 20261006, "split": "all"}`
