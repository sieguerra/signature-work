# Human review rubric

Written before any review labels were collected.

The reviewer compares the BEFORE state with the AFTER state. The page shows the question, the retrieved evidence, and the answer on each side. It does not show the automatic label, the verifier label, the recovery action, or whether the case was expected to improve.

Do not open `human_review_key.jsonl` or `run_results.jsonl` while reviewing. Those files contain the automatic label.

## What to judge

Correctness. Does the answer address the question?

Grounding. Are the factual claims supported by the evidence on that side?

Completeness. Does the response contain enough to satisfy the question?

Unsupported specificity. Does it invent a number, date, name, or other claim the evidence does not support?

Abstention. If the evidence cannot support an answer, is refusing appropriate?

Then decide whether AFTER is materially better than BEFORE.

## Labels

Improved. AFTER is materially better.

Unchanged. The useful content is the same. A different wording of the same right answer, or the same wrong answer, is unchanged.

Still failing. Both sides fail the question. A different wrong answer is still failing.

Degraded. AFTER is materially worse.

Unclear / cannot determine. The two states cannot be compared from the evidence shown.

## Do not reward

Length, nicer writing, confidence, or extra detail, unless that change actually makes the answer more correct or more useful.

## One reviewer

If only one person reviews, that is one reading. It is not a consensus. A second reviewer can load the same blinded file later. Agreement is computed only after both files exist.
