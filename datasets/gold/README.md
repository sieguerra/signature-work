# Gold set

Hand-written evaluation questions over `datasets/corpus/`, per ADR 003.

These answers are the **offline ground truth** for the whole project. Every
number in the final report traces back to this file, so it is student-authored
work and must be verified by hand against the corpus.

Per ADR 003, nothing in here may be read at runtime. The pipeline sees the
`question` field only; `answers` and `answerable` exist for offline scoring.

## Format

JSON Lines — one question per line. Blank lines and lines starting with `#` are
ignored, so the file can be grouped with comments.

| Field | Required | Meaning |
|---|---|---|
| `question_id` | yes | Unique, stable. Never reuse an id for a different question |
| `question` | yes | The question as asked. This is all the pipeline sees |
| `answerable` | yes | `true` if the corpus contains the answer, `false` otherwise |
| `answers` | if answerable | Acceptable short answers. Empty when `answerable` is `false` |
| `supporting_doc_ids` | no | Which corpus documents contain the answer. Used to check retrieval |
| `notes` | no | Why this question exists, or what makes it hard |

## Writing good questions

**Keep answers short.** Exact Match and F1 are computed after normalisation
(lowercase, punctuation and articles stripped). A gold answer of
`"Level 3"` is scorable; `"The quiet study floor is on Level 3"` is not.

**List aliases.** If `08:00-21:00` and `8am to 9pm` are both acceptable, put
both in `answers`. Under-listing aliases shows up as a false failure and will
pollute the failure taxonomy.

**Write unanswerable questions deliberately.** They are not filler — the
corpus-gap failure class does not exist without them, and the recovery for that
class is abstention. Aim for questions that *sound* answerable from the corpus
but are not, such as asking about a service the documents mention only to deny.

**Target the classes you want to measure.** A question whose answer sits in one
obvious chunk tests generation. A question whose answer needs an easily-missed
detail tests retrieval. Note which you intended in `notes`.

## Current state

`questions.jsonl` holds **seed examples only** — enough to exercise the loader
and scorer, not enough to evaluate anything. Issue #5 tracks writing the real
set (target roughly 40-60 questions, with a deliberate answerable/unanswerable
split).

Verify the seed rows against the corpus before trusting them.
