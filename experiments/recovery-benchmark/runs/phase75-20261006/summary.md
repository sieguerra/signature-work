# Human gate review

One reviewer (`reviewer-1`). Labels were not edited after scoring.

60 of 60 triggered runs are labeled. The 40 runs that did not recover were not labeled. 19 triggered before-states are unclear and are left out of the rates below. No second reviewer. The 39-question future holdout was not used.

## Decided triggered runs (41)

Needed recovery: 15 (14 incorrect, 1 incomplete).
Already acceptable: 26 (22 correct, 4 appropriate abstentions).
Gate precision: 15/41 = 0.366.
Unnecessary recovery: 26/41 = 0.634.

Among the 15 needed runs, the transition was improved 3, unchanged 12, still failing 0, degraded 0.
Conditional success: 3/15 = 0.200.

The three improved needed runs are `dku-053`, `dku-012`, and `sw-016`. On all three, rewrite still abstained and the expand step wrote the final answer. `sw-016` remains an explanation that no wave height is printed.

## Spotlight labels

| Case | Before | Transition | Automatic gold |
|---|---|---|---|
| dku-053 | incorrect | improved | improved |
| dku-012 | incorrect | improved | improved |
| dku-055 | correct | degraded | improved |
| dku-045 | correct | degraded | improved |
| seed-009 | correct | degraded | improved |
| dku-008 | correct | unchanged | degraded |
| dku-032 | appropriate abstention | improved | degraded |
| ls-016 | appropriate abstention | improved | degraded |
| nw-015 | unclear | unclear | still failing |
| og-016 | correct | unchanged | still failing |
| gold-030 | appropriate abstention | improved | still failing |
| og-004 | appropriate abstention | improved | still failing |

Human versus primary gold on 59 decided transitions: 37 matches, 0.627. The paraphrase and grounded rules match the primary rule on these runs, so they agree with the human at the same rate.

## Gate candidates

Only `ignore_ambiguous_margin` skips any triggered runs without skipping a run the reviewer called bad. It skips 8 decided runs, saves 16 chat calls, about 29 seconds, and about $0.004. It does not skip `dku-053` or `dku-012`.

Stopping explicit abstentions skips all 15 runs the reviewer called bad, including those two. Requiring two warning signals skips 13 of the 15.
