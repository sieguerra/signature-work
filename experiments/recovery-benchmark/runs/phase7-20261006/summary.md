# Recovery benchmark

Primary gold: `gold-rank-2026-10-06`.
Independent recovered logical runs: **60**.
Logical runs scored, including accepts: 186.
Attempt rows (not independent samples): 123.
Future holdout traces skipped: 0.

Rates below use recovered logical runs as the denominator.
A percentage from a very small count is not a precise estimate.

## Outcomes

- improved: 5/60 = 0.083 (90% bootstrap interval 0.033 to 0.133)
- unchanged: 48/60 = 0.800 (90% bootstrap interval 0.717 to 0.883)
- still_failing: 4/60 = 0.067 (90% bootstrap interval 0.017 to 0.117)
- degraded: 3/60 = 0.050 (90% bootstrap interval 0.017 to 0.100)

## By answerability

### answerable (n=15)

- improved: 4/15 = 0.267 (90% bootstrap interval 0.067 to 0.467)
- unchanged: 9/15 = 0.600 (90% bootstrap interval 0.400 to 0.800)
- still_failing: 1/15 = 0.067 (90% bootstrap interval 0.000 to 0.200)
- degraded: 1/15 = 0.067 (90% bootstrap interval 0.000 to 0.200)

### unanswerable (n=45)

- improved: 1/45 = 0.022 (90% bootstrap interval 0.000 to 0.067)
- unchanged: 39/45 = 0.867 (90% bootstrap interval 0.778 to 0.933)
- still_failing: 3/45 = 0.067 (90% bootstrap interval 0.000 to 0.133)
- degraded: 2/45 = 0.044 (90% bootstrap interval 0.000 to 0.111)

## By action

### expand (n=10)

- improved: 1/10 = 0.100 (90% bootstrap interval 0.000 to 0.300)
- unchanged: 8/10 = 0.800 (90% bootstrap interval 0.600 to 1.000)
- still_failing: 0/10 = 0.000 (90% bootstrap interval 0.000 to 0.000)
- degraded: 1/10 = 0.100 (90% bootstrap interval 0.000 to 0.300)

### multi (n=50)

- improved: 4/50 = 0.080 (90% bootstrap interval 0.020 to 0.140)
- unchanged: 40/50 = 0.800 (90% bootstrap interval 0.700 to 0.880)
- still_failing: 4/50 = 0.080 (90% bootstrap interval 0.020 to 0.140)
- degraded: 2/50 = 0.040 (90% bootstrap interval 0.000 to 0.100)

## Split

Analysis questions available to run: 186 (137 answerable, 49 unanswerable).
Future holdout reserved and not scored: 39 (30 answerable, 9 unanswerable).
