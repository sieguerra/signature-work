# Human review rubric

Written before any review labels were collected.

The reviewer compares the BEFORE state with the AFTER state. The page shows the question, the retrieved evidence, and the answer on each side. It does not show the automatic label, the verifier label, the recovery action, or whether the case was expected to improve.

Do not open `human_review_key.jsonl`, `review_key.jsonl`, `gate_features.jsonl`, or `run_results.jsonl` while reviewing. Those files contain the automatic label.

## What to judge

Correctness. Does the answer address the question?

Grounding. Are the factual claims supported by the evidence on that side?

Completeness. Does the response contain enough to satisfy the question?

Unsupported specificity. Does it invent a number, date, name, or other claim the evidence does not support?

Abstention. If the evidence cannot support an answer, is refusing appropriate?

Then decide whether AFTER is materially better than BEFORE.

## Two judgments

Judgment A is the BEFORE state, on its own.

Correct / acceptable answer. The answer addresses the question and the claims a reader would rely on are supported by the before evidence.

Appropriate abstention. The evidence does not support a specific answer, and the response refuses instead of inventing one. An appropriate abstention does not need more recovery.

Incorrect / unsupported answer. The response gives a specific claim the evidence does not support, or it answers a different question.

Incomplete but not enough. Some of the response is useful, and it still fails to answer the question. This state needed recovery.

Unclear. The before state cannot be judged from what is shown.

Judgment B is the transition, comparing AFTER with BEFORE.

## When recovery was needed

Written before any necessity rate is calculated.

A run needed recovery when Judgment A is incorrect or incomplete. A correct answer did not need recovery. An appropriate abstention did not need recovery. Unclear is not counted as either.

This is a property of the before state. It is not the automatic gold label, and it is not whether the runtime verifier said the run improved.

## Labels

Improved. AFTER is materially better.

Unchanged. The useful content is the same. A different wording of the same right answer, or the same wrong answer, is unchanged.

Still failing. Both sides fail the question. A different wrong answer is still failing.

Degraded. AFTER is materially worse.

Unclear / cannot determine. The two states cannot be compared from the evidence shown.

## Do not reward

Length, nicer writing, confidence, or extra detail, unless that change actually makes the answer more correct or more useful.

## Runs that did not recover

A second packet shows only the question, the before evidence, and the before answer. Judge the before state with Judgment A. There is no transition.

The reserved future holdout is not in either packet.

## One reviewer

If only one person reviews, that is one reading. It is not a consensus. A second reviewer exports a separate file from the same packet. Agreement is computed only after both files exist, and the page does not show the other person's labels.
